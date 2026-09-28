"""A comanda virtual da edição de encomenda — a tela de venda do PDV em modo edição.

Decisão do dono (28/09/2026): o editor de itens É a própria tela de venda
(carrinho, grade, F7 recebimento, F8 data, cliente), não um editor novo. Para a
tela funcionar como funciona — autosave, prévia de taxa, chips de recebimento e
data —, ela precisa de uma sessão aberta; esta é ela.

A sessão é uma comanda que NÃO é comanda:

- ``handle_type = "pos_edit"``, ``handle_ref = <ref do pedido>`` e SEM
  ``data.tab_ref``: o quadro de comandas (``build_pos_tabs``) não a lista, e
  nenhum ``POSTab`` nasce para ela;
- ``data.pos_edit = {order_ref, base_revision, started_by, started_at}``: de
  qual pedido ela é a edição, e a revisão ``edit`` que ele tinha ao abrir;
- ``pricing_policy = "external"``: o item que já estava mostra o preço VENDIDO
  (o kernel não reprecifica pelo catálogo). Quem decide preço na gravação é o
  serviço de edição (``order_edit``), nunca a tela;
- não dispara cozinha (``fire_pos_tab`` recusa) e não fecha venda
  (``close_sale`` recusa): o gesto dela é "Salvar alterações", que chama a
  edição do pedido com a lista FINAL e os campos mudados;
- "Descartar alterações" abandona a sessão (``clear_pos_tab``) sem tocar no
  pedido.

Abrir de novo a edição do mesmo pedido RETOMA a comanda virtual quando o pedido
não mudou desde então; se mudou, a antiga é abandonada e outra nasce do pedido
como ele está.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order, Session

logger = logging.getLogger(__name__)

HANDLE_TYPE = "pos_edit"
DATA_KEY = "pos_edit"

REFUSAL_MESSAGE = "Esta é a edição de uma encomenda: use Salvar alterações (ou Descartar alterações)."


def is_edit_session(session) -> bool:
    if session is None:
        return False
    return getattr(session, "handle_type", "") == HANDLE_TYPE or bool((session.data or {}).get(DATA_KEY))


def edit_info(session) -> dict:
    return dict((session.data or {}).get(DATA_KEY) or {})


def open_edit_session(order, *, channel_ref: str, actor: str, operator_username: str) -> Session:
    """Abre (ou retoma) a comanda virtual pré-montada com a encomenda."""
    from shopman.shop.services import operator_orders, order_edit, weighed_sale
    from shopman.shop.services import pos as pos_service
    from shopman.shop.services import sessions as session_service
    from shopman.shop.services.pos_intent import PosIntentError, parse_pos_sale_intent

    code, reason = order_edit.state_refusal(order)
    if code:
        raise PosIntentError(code=code, message=reason, field="order", focus="cart")

    revision = operator_orders.operational_revision(order, field="edit")
    channel, config = pos_service._channel_and_config(channel_ref)
    with transaction.atomic():
        existing = list(
            Session.objects.select_for_update()
            .filter(channel_ref=channel.ref, handle_type=HANDLE_TYPE, handle_ref=order.ref, state="open")
            .order_by("-opened_at")
        )
        for index, session in enumerate(existing):
            if index == 0 and edit_info(session).get("base_revision") == revision:
                logger.info("pos_edit_session: retomada order=%s session=%s", order.ref, session.session_key)
                return session
            session.state = "abandoned"
            session.save(update_fields=["state", "updated_at"])

        session = session_service.create_session(
            channel.ref,
            handle_type=HANDLE_TYPE,
            handle_ref=order.ref,
            data={
                "origin_channel": "pos",
                "pos_operator": operator_username,
                "last_touched_at": timezone.now().isoformat(),
                DATA_KEY: _marker(order, revision=revision, operator_username=operator_username),
            },
        )
        # O preço que a tela mostra para o item que já estava é o VENDIDO.
        Session.objects.filter(pk=session.pk).update(pricing_policy="external")
        session.refresh_from_db()

        payload = parse_pos_sale_intent(cart_payload(order), for_commit=False).payload
        # O parser zera a quantidade da linha pesada (ela sai da etiqueta): a peça
        # que já estava volta com o peso e o preço VENDIDOS, e só a nova se resolve.
        pinned = pin_kept_lines(order, payload)
        weighed_sale.apply_to_payload(payload, channel=channel, skip_line_ids=pinned)
        ops = pos_service._replace_session_ops(session, payload, operator_username)
        ops.append({"op": "set_data", "path": DATA_KEY, "value": edit_info(session)})
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=ops,
            ctx={"actor": actor},
            channel_config=config.to_dict(),
        )
        session.refresh_from_db()
    logger.info("pos_edit_session: aberta order=%s session=%s", order.ref, session.session_key)
    return session


def cart_payload(order) -> dict:
    """A encomenda no formato do carrinho do PDV (a intenção de venda).

    Os itens são os VIGENTES (``order_composition``), com o ``line_id`` do pedido
    — é por ele que a edição reconhece "o que já estava" e mantém o preço
    vendido. A taxa de entrega não entra como item: na tela ela sai do
    recebimento (F7), como na venda.
    """
    from shopman.shop.services import order_composition
    from shopman.shop.services.order_helpers import json_quantity

    data = order.data or {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    items = []
    for item in order_composition.effective_items(order):
        meta = item.meta if isinstance(item.meta, dict) else {}
        if str(item.sku or "").startswith("__") or meta.get("type") == "delivery_fee":
            continue
        line = {
            "line_id": item.line_id,
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": json_quantity(item.qty),
            "unit_price_q": item.unit_price_q,
        }
        weighed = _weighed_entry(item)
        if weighed:
            line["weighed"] = weighed
        if meta.get("notes"):
            line["notes"] = str(meta["notes"])
        items.append(line)
    structured = data.get("delivery_address_structured") if isinstance(data.get("delivery_address_structured"), dict) else {}
    payload = {
        "items": items,
        "sales_mode": "order",
        "fulfillment_type": "delivery" if data.get("fulfillment_type") == "delivery" else "pickup",
        "delivery_address": str(data.get("delivery_address") or ""),
        "delivery_address_structured": structured,
        "delivery_date": str(data.get("delivery_date") or ""),
        "delivery_time_slot": str(data.get("delivery_time_slot") or ""),
        "order_notes": str(data.get("order_notes") or ""),
        "customer_name": str(customer.get("name") or ""),
        "customer_phone": str(customer.get("phone") or data.get("customer_phone") or ""),
        "customer_ref": str(data.get("customer_ref") or customer.get("ref") or ""),
        "fiscal_tax_id": str((data.get("fiscal") or {}).get("tax_id") or ""),
        "payment_method": str((data.get("payment") or {}).get("method") or ""),
    }
    if data.get("delivery_fee_override_q") is not None:
        payload["delivery_fee_override_q"] = data.get("delivery_fee_override_q")
    return payload


def _weighed_entry(item) -> dict | None:
    """O que o operador tinha em mãos quando a peça pesada foi vendida.

    A etiqueta (``label_q``) ou o peso (``weight_g``) do registro da linha
    (``meta.weighed``); sem registro, o peso sai da quantidade (kg → g).
    ``None`` para a linha por unidade.
    """
    meta = item.meta if isinstance(item.meta, dict) else {}
    recorded = meta.get("weighed") if isinstance(meta.get("weighed"), dict) else None
    if recorded is None and item.qty == item.qty.to_integral_value():
        return None
    weight_g = int((recorded or {}).get("weight_g") or 0) or int(item.qty * 1000)
    entry = {"entry": "weight", "weight_g": weight_g}
    if recorded and recorded.get("entry") == "label" and recorded.get("label_q"):
        entry = {"entry": "label", "label_q": int(recorded["label_q"]), "weight_g": weight_g}
    return entry


def pin_kept_lines(order, payload: dict) -> set[str]:
    """Devolve à peça pesada que JÁ ESTAVA o peso e o preço vendidos.

    Na comanda da edição, a linha pesada do pedido não se resolve de novo pela
    etiqueta: o peso dela é o que saiu da balança no dia da venda, e o preço do
    quilo é o vendido. Quem decide preço na gravação continua sendo o
    ``order_edit`` (pelo ``line_id``); isto só impede a comanda de mostrar outra
    peça no lugar. Devolve os ``line_id`` fixados, para o
    ``weighed_sale.apply_to_payload`` pular.
    """
    from shopman.shop.services import order_composition

    by_line = {item.line_id: item for item in order_composition.effective_items(order)}
    pinned: set[str] = set()
    for line in payload.get("items") or []:
        if not isinstance(line, dict):
            continue
        old = by_line.get(str(line.get("line_id") or ""))
        if old is None:
            continue
        weighed = _weighed_entry(old)
        if weighed is None:
            continue
        line["qty"] = old.qty
        line["unit_price_q"] = old.unit_price_q
        line["weighed"] = weighed
        pinned.add(old.line_id)
    return pinned


def pin_session_lines(session, payload: dict) -> set[str]:
    """:func:`pin_kept_lines` para o autosave da comanda da edição."""
    from shopman.orderman.models import Order

    order = Order.objects.filter(ref=edit_info(session).get("order_ref") or session.handle_ref).first()
    return pin_kept_lines(order, payload) if order is not None else set()


# ── Cancelar e refazer: a venda nova já montada ──────────────────────────────
#
# Com a NFC-e autorizada a encomenda não se edita (corrigir nota é outro
# documento fiscal): o caminho é cancelar e refazer. O cancelamento é o de
# sempre (política e PIN); o "refazer" é uma COMANDA DE VENDA comum, do quadro,
# pré-montada com a encomenda cancelada — itens, cliente, recebimento, data e
# observação — para o operador ajustar e fechar a venda nova. A montagem é a
# mesma da comanda virtual da edição (:func:`cart_payload`); o que muda é o
# destino: aqui nada é "o que já estava". O preço é o do catálogo de hoje, o
# pagamento é o da venda nova e a peça pesada se resolve de novo pela etiqueta.

REDO_TAB_PREFIX = "Refazer"


def redo_tab_ref(order) -> str:
    """A comanda do refazer leva o nome da encomenda: ``Refazer <ref>``."""
    return f"{REDO_TAB_PREFIX} {order.ref}"


@dataclass(frozen=True)
class RedoTab:
    session: Session
    #: A comanda já existia com itens (o operador voltou a ela): nada foi remontado.
    resumed: bool = False
    #: A data/janela antiga não vale mais: o aviso diz a razão e a data com que a comanda veio.
    schedule_dropped: str = ""


def open_redo_tab(order, *, channel_ref: str, actor: str, operator_username: str) -> RedoTab:
    """Abre a comanda de venda pré-montada com a encomenda cancelada.

    Só depois do cancelamento: refazer uma encomenda viva seria vender duas
    vezes. Idempotente — a mesma comanda é retomada enquanto estiver aberta, e a
    encomenda já refeita (venda fechada nessa comanda) não se refaz de novo.
    """
    from shopman.shop.services import pos as pos_service
    from shopman.shop.services.pos_intent import PosIntentError

    if order.channel_ref == "ifood":
        raise PosIntentError(
            code="marketplace_order", message="Pedido do iFood se refaz no iFood.", field="order", focus="cart",
        )
    if str(order.status) != Order.Status.CANCELLED:
        raise PosIntentError(
            code="order_not_cancelled",
            message="Refazer é depois de cancelar: esta encomenda ainda está valendo.",
            field="order",
            focus="cart",
        )
    tab_ref = redo_tab_ref(order)
    normalized = pos_service.normalize_tab_ref(tab_ref)
    redone = (
        Order.objects.filter(data__tab_ref=normalized)
        .exclude(pk=order.pk)
        .exclude(status__in=(Order.Status.CANCELLED, Order.Status.RETURNED))
        .order_by("-created_at")
        .first()
    )
    if redone is not None:
        raise PosIntentError(
            code="already_redone",
            message=f"Esta encomenda já foi refeita: é o pedido {redone.ref}.",
            field="order",
            focus="cart",
        )

    with transaction.atomic():
        session = pos_service.open_pos_tab(
            channel_ref=channel_ref, tab_ref=tab_ref, actor=actor, operator_username=operator_username,
        )
        if session.items:
            logger.info("pos_redo_tab: retomada order=%s session=%s", order.ref, session.session_key)
            return RedoTab(session=session, resumed=True)

        payload = redo_payload(order, channel_ref=channel_ref)
        dropped = _fit_schedule(payload)
        pos_service.save_pos_tab(
            channel_ref=channel_ref,
            payload={**payload, "tab_ref": normalized, "tab_session_key": session.session_key},
            actor=actor,
            operator_username=operator_username,
        )
        session.refresh_from_db()
    logger.info("pos_redo_tab: aberta order=%s session=%s", order.ref, session.session_key)
    return RedoTab(session=session, schedule_dropped=dropped)


def redo_payload(order, *, channel_ref: str) -> dict:
    """A encomenda cancelada no formato do carrinho de uma VENDA NOVA.

    Sem ``line_id`` (as linhas são novas), com o preço do catálogo de hoje no
    canal do balcão (o kernel reprecifica de qualquer jeito), sem forma de
    pagamento e sem "CPF na nota" (os dois são decididos no fechamento da venda
    nova). A peça
    pesada vai pela etiqueta; pelo peso só se a loja lança pelo peso — senão a
    etiqueta é o valor que a peça valia.
    """
    from shopman.shop.handlers.pricing import OffermanPricingBackend
    from shopman.shop.models import Channel
    from shopman.shop.services import weighed_sale

    payload = cart_payload(order)
    # Pagamento e "CPF na nota" são decisões de QUEM fecha a venda nova, no
    # fechamento (a regra da comanda reaberta): não voltam da encomenda velha.
    payload.pop("payment_method", None)
    payload.pop("fiscal_tax_id", None)
    channel = Channel.objects.filter(ref=channel_ref).first()
    backend = OffermanPricingBackend()
    by_weight = None
    items = []
    for line in payload["items"]:
        line = {key: value for key, value in line.items() if key != "line_id"}
        weighed = line.get("weighed")
        if weighed:
            if weighed.get("entry") == "weight":
                if by_weight is None:
                    by_weight = weighed_sale.weight_entry_enabled()
                if not by_weight:
                    weighed = {"entry": "label", "label_q": _piece_value_q(order, line)}
            line["weighed"] = {k: v for k, v in weighed.items() if k in ("entry", "label_q", "weight_g")}
        price = backend.get_price(line["sku"], channel, qty=1) if channel is not None else None
        if price:
            line["unit_price_q"] = int(price)
        items.append(line)
    payload["items"] = items
    return payload


def _piece_value_q(order, line: dict) -> int:
    """O valor da peça pesada vendida — a "etiqueta" dela quando não houve etiqueta."""
    from decimal import Decimal

    from shopman.utils.monetary import monetary_mult

    return int(monetary_mult(Decimal(str(line.get("qty") or 0)), int(line.get("unit_price_q") or 0)))


def _schedule_refusal(payload: dict) -> str:
    """A frase com que a régua da venda (``pos._validate_schedule``) recusa a data — ou ""."""
    from shopman.shop.services import pos as pos_service

    try:
        pos_service._validate_schedule(payload)
    except ValueError as exc:
        return str(exc)
    return ""


def _fit_schedule(payload: dict) -> str:
    """Traz para a comanda uma data que ainda vale; devolve o aviso (ou "").

    A encomenda sem data não guarda item (``pos_sales_mode``), então a data
    antiga que não vale mais (passou, a casa fecha, a janela lotou) não some: a
    comanda vem para a primeira data que a régua da venda aceita, sem horário, e
    o aviso diz isso por extenso para o operador confirmar com o cliente.
    """
    from datetime import timedelta

    from shopman.shop.services import preorder_dates
    from shopman.shop.services.pos_intent import PosIntentError

    reason = _schedule_refusal(payload)
    if not reason:
        return ""
    if payload.get("delivery_time_slot") and payload.get("delivery_date"):
        if not _schedule_refusal({**payload, "delivery_time_slot": ""}):
            payload["delivery_time_slot"] = ""
            return f"{reason} A comanda veio sem horário: confirme a janela com o cliente (F8)."
    today = timezone.localdate()
    for offset in range(preorder_dates.max_preorder_days() + 1):
        day = today + timedelta(days=offset)
        if _schedule_refusal({**payload, "delivery_date": day.isoformat(), "delivery_time_slot": ""}):
            continue
        payload["delivery_date"] = day.isoformat()
        payload["delivery_time_slot"] = ""
        return (
            f"{reason} A comanda veio para {day.strftime('%d/%m')}, sem horário: "
            "confirme a data com o cliente (F8)."
        )
    raise PosIntentError(
        code="no_preorder_date",
        message=f"{reason} Nenhuma data aceita encomenda agora: registre a venda nova sem pré-montar.",
        field="delivery_date",
        focus="schedule",
    )


def _marker(order, *, revision: str, operator_username: str) -> dict:
    return {
        "order_ref": order.ref,
        "base_revision": revision,
        "started_by": operator_username,
        "started_at": timezone.now().isoformat(),
    }
