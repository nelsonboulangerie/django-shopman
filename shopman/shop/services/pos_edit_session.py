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

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Session

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
    from shopman.shop.services import operator_orders, order_edit
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
        if item.qty != item.qty.to_integral_value():
            line["weighed"] = {"entry": "weight", "weight_g": int(item.qty * 1000)}
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


def _marker(order, *, revision: str, operator_username: str) -> dict:
    return {
        "order_ref": order.ref,
        "base_revision": revision,
        "started_by": operator_username,
        "started_at": timezone.now().isoformat(),
    }
