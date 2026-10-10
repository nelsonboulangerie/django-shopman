"""A venda que o PDV fez SEM CONEXÃO e enviou depois: as decisões do dono (10/10/2026).

WP-PDV-SEM-CONEXAO §3.3. A fila do PDV reenvia o mesmo ``close_sale`` com
``offline_captured_at`` (a hora em que o balcão cobrou). O dinheiro já entrou;
o servidor não recusa a venda por uma mudança que aconteceu durante a queda.

**Preço (decisão D).** A venda é precificada NA HORA DA COBRANÇA: os modifiers
leem ``ctx["priced_at"]`` (``modifiers.pricing_now``). Se mesmo assim a conta do
servidor der outra (preço de catálogo editado durante a queda, linha pesada),
vale o total COBRADO, e a diferença fica no pedido (``pos.offline.pricing``), no
aviso do gerente e no relatório do caixa.

**Comanda mudada em outro dispositivo (decisão C).** A venda fecha EXATAMENTE as
linhas que este dispositivo cobrou (por ``line_id``). O que o outro dispositivo
acrescentou segue aberto numa comanda com o mesmo número. Linha que o outro tirou
ou cuja quantidade mudou: vale o cobrado, e o ajuste fica registrado. Comanda já
paga no outro dispositivo: as linhas que já estavam pagas não viram pedido de
novo; o resto sobe como venda de balcão; se TUDO já estava pago, nenhum pedido
nasce e a cobrança em dobro fica registrada no pedido pago, com aviso ao gerente.

**Proteção.** Só vale para a venda que passa nas travas da venda sem conexão
(sem desconto, sem taxa, sem entrega, sem encomenda, recebida em dinheiro ou na
maquininha) e cuja hora de cobrança é plausível: não está no futuro e não é mais
velha que 24 h nem que o turno aberto. Fora disso, a venda segue a régua de
sempre (precificada agora, ``total_changed`` e ``tab_revision_conflict``).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from shopman.utils.monetary import format_money, monetary_mult

logger = logging.getLogger(__name__)

#: Formas que se recebem sem rede (as mesmas da tela, ``OFFLINE_PAYMENT_METHODS``).
OFFLINE_PAYMENT_METHODS = frozenset({"cash", "credit", "debit", "external"})
#: Folga do relógio do dispositivo em relação ao do servidor.
CLOCK_SKEW = timedelta(minutes=5)
#: A venda guardada mais velha que ainda se precifica na hora da cobrança.
MAX_AGE = timedelta(hours=24)

ALERT_TYPE = "pos_offline_sale_adjusted"


# ── Elegibilidade ─────────────────────────────────────────────────────


def pricing_instant(payload: dict, *, now: datetime | None = None) -> datetime | None:
    """A hora em que a venda sem conexão foi cobrada, se ela pode valer; senão ``None``.

    ``None`` é "régua de sempre": venda com conexão, venda fora das travas ou com
    hora implausível. A hora vem do dispositivo, e por isso tem janela: um relógio
    adiantado ou uma fila esquecida por dias não decidem preço.
    """
    captured = _parse_instant(payload.get("offline_captured_at"))
    if captured is None or not _passes_offline_locks(payload):
        return None
    now = now or timezone.now()
    if captured > now + CLOCK_SKEW or captured < now - MAX_AGE:
        return None
    shift = _open_shift(payload)
    if shift is not None and shift.opened_at and captured < shift.opened_at - CLOCK_SKEW:
        return None
    return captured


def _parse_instant(value) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None else None


def _passes_offline_locks(payload: dict) -> bool:
    """As mesmas travas da tela (``offlineSaleBlockers``), conferidas no servidor."""
    from shopman.shop.services import pos

    if str(payload.get("sales_mode") or "counter") == "order":
        return False
    if pos._payload_fulfillment_type(payload) == "delivery":
        return False
    if str(payload.get("payment_collection") or "terminal") == "on_delivery":
        return False
    if pos._payload_manual_discount(payload):
        return False
    if any(isinstance(item, dict) and item.get("discount") for item in payload.get("items") or []):
        return False
    if pos._payload_delivery_fee_q(payload) > 0:
        return False
    methods = pos._payload_payment_method_set(payload)
    return bool(methods) and methods <= OFFLINE_PAYMENT_METHODS


def _open_shift(payload: dict):
    from shopman.cashman import Shift

    shift_id = payload.get("cash_shift_id")
    if not shift_id:
        return None
    return Shift.objects.filter(pk=shift_id).first()


def charged_payload_matches(payload: dict) -> bool:
    """A soma das linhas cobradas é o total que a tela cobrou? Sem isso, nada vale."""
    from shopman.shop.services import pos

    expected = payload.get("expected_total_q")
    if expected is None:
        return True
    return int(expected) == pos._payload_total_q(payload)


def charged_total_q(payload: dict) -> int:
    from shopman.shop.services import pos

    expected = payload.get("expected_total_q")
    return int(expected) if expected is not None else pos._payload_total_q(payload)


# ── Preço: vale o cobrado ─────────────────────────────────────────────


def pricing_record(*, charged_q: int, server_q: int, priced_at: datetime) -> dict:
    return {
        "priced_at": priced_at.isoformat(),
        "charged_total_q": int(charged_q),
        "server_total_q": int(server_q),
        "difference_q": int(charged_q) - int(server_q),
    }


def session_total_q(session) -> int:
    return sum(int(item.get("line_total_q") or 0) for item in (session.items or []))


# ── Comanda mudada em outro dispositivo ───────────────────────────────


@dataclass
class TabPlan:
    """O que a venda guardada faz com a comanda que mudou durante a queda."""

    outcome: str  # "lines_left_open" | "already_paid" | "already_paid_all" | "tab_cleared"
    tab_ref: str = ""
    tab_display: str = ""
    #: Linhas da comanda que NÃO foram cobradas aqui: seguem abertas.
    left_open: list[dict] = field(default_factory=list)
    #: Linhas cobradas aqui que o outro dispositivo tirou ou mudou: vale o cobrado.
    adjusted: list[dict] = field(default_factory=list)
    #: Linhas cobradas aqui que já estavam pagas no outro dispositivo.
    already_paid: list[dict] = field(default_factory=list)
    already_paid_q: int = 0
    paid_order_ref: str = ""
    #: Linhas que já estão na cozinha por outra sessão (não voltam ao KDS).
    inherited_fired: list[str] = field(default_factory=list)

    def record(self) -> dict:
        record = {"outcome": self.outcome, "tab_ref": self.tab_ref, "tab_display": self.tab_display}
        if self.left_open:
            record["left_open"] = [_public_line(line) for line in self.left_open]
        if self.adjusted:
            record["adjusted"] = self.adjusted
        if self.already_paid:
            record["already_paid"] = self.already_paid
            record["already_paid_q"] = self.already_paid_q
        if self.paid_order_ref:
            record["paid_order_ref"] = self.paid_order_ref
        return record


def _public_line(line: dict) -> dict:
    return {
        "line_id": str(line.get("line_id") or ""),
        "sku": str(line.get("sku") or ""),
        "name": str(line.get("name") or line.get("sku") or ""),
        "qty": _qty_json(line.get("qty")),
    }


def _qty(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _qty_json(value):
    qty = _qty(value)
    return int(qty) if qty == qty.to_integral_value() else float(qty)


def plan_open_tab(session, payload: dict) -> TabPlan:
    """A comanda ainda aberta, mudada em outro dispositivo: o que fecha e o que fica.

    Fecha o que foi COBRADO (as linhas do payload). Fica aberta, na mesma comanda,
    a linha que só a comanda tem (a que o outro dispositivo acrescentou). Uma linha
    que este dispositivo tirou sem conexão também aparece assim e fica aberta:
    deixar à vista é o lado seguro (nada some calado).

    Quantidade mudada lá numa linha cobrada aqui: vale o cobrado e só se registra
    (cenário raríssimo; o dono pediu o mínimo seguro, sem acerto de quantidade).
    """
    from shopman.shop.services import kds as kds_service
    from shopman.shop.services import pos

    charged = {str(item.get("line_id") or ""): item for item in payload.get("items") or [] if item.get("line_id")}
    fired = kds_service.fired_line_ids(session.session_key)
    plan = TabPlan(
        outcome="lines_left_open",
        tab_ref=pos._session_tab_ref(session),
        tab_display=pos._session_tab_display(session),
    )
    for item in session.items or []:
        line_id = str(item.get("line_id") or "")
        mine = charged.get(line_id)
        if mine is None:
            plan.left_open.append(dict(item))
            if line_id in fired:
                plan.inherited_fired.append(line_id)
            continue
        tab_qty, charged_qty = _qty(item.get("qty")), _qty(mine.get("qty"))
        if tab_qty == charged_qty:
            continue
        plan.adjusted.append({
            **_public_line(mine), "kind": "qty_changed_elsewhere",
            "charged_qty": _qty_json(charged_qty), "tab_qty": _qty_json(tab_qty),
        })
    tab_ids = {str(item.get("line_id") or "") for item in session.items or []}
    for line_id, mine in charged.items():
        if line_id not in tab_ids:
            plan.adjusted.append({**_public_line(mine), "kind": "removed_elsewhere", "charged_qty": _qty_json(mine.get("qty"))})
    if not plan.left_open and not plan.adjusted:
        plan.outcome = "revision_only"
    return plan


def plan_closed_tab(session, payload: dict) -> TabPlan:
    """A comanda já fechada (paga) ou limpa no outro dispositivo.

    Paga: as linhas cobradas aqui que já estão no pedido pago (mesmo ``line_id``)
    não viram pedido de novo, e saem do payload; o resto sobe como venda de
    balcão. Limpa (abandonada): tudo sobe como venda de balcão.
    """
    from shopman.orderman.models import Order

    from shopman.shop.services import kds as kds_service
    from shopman.shop.services import pos

    plan = TabPlan(outcome="tab_cleared", tab_ref=pos._session_tab_ref(session), tab_display=pos._session_tab_display(session))
    fired = kds_service.fired_line_ids(session.session_key)
    order = Order.objects.filter(session_key=session.session_key).order_by("-created_at").first() if session.state == "committed" else None
    charged = [item for item in payload.get("items") or [] if isinstance(item, dict)]
    if order is not None:
        paid_ids = set(order.items.values_list("line_id", flat=True))
        plan.paid_order_ref = order.ref
        keep = []
        for item in charged:
            line_id = str(item.get("line_id") or "")
            if line_id and line_id in paid_ids:
                amount_q = monetary_mult(_qty(item.get("qty")), int(item.get("unit_price_q") or 0))
                plan.already_paid.append({**_public_line(item), "amount_q": int(amount_q)})
                plan.already_paid_q += int(amount_q)
            else:
                keep.append(item)
        plan.outcome = "already_paid" if keep else "already_paid_all"
        charged = keep
    plan.inherited_fired = [str(item.get("line_id")) for item in charged if str(item.get("line_id") or "") in fired]
    return plan


def trim_payload_to(payload: dict, plan: TabPlan) -> None:
    """Tira do payload as linhas já pagas e acerta as formas ao novo total.

    O dinheiro das linhas já pagas entrou de novo, mas não é venda: não vai para o
    pedido nem para o livro do turno. Fica registrado (``already_paid_q``) e o
    gerente decide a devolução. As formas descem até o total novo pelo mesmo
    acerto do fechamento (o dinheiro primeiro).
    """
    from shopman.shop.services import pos

    paid_ids = {line["line_id"] for line in plan.already_paid}
    payload["items"] = [item for item in payload.get("items") or [] if str(item.get("line_id") or "") not in paid_ids]
    new_total = pos._payload_total_q(payload)
    payload["expected_total_q"] = new_total
    tenders = [dict(t) for t in payload.get("payment_tenders") or [] if isinstance(t, dict)]
    if tenders:
        pos._reconcile_tenders_to_total(tenders, new_total)
        payload["payment_tenders"] = [t for t in tenders if pos._int_q(t.get("amount_q")) > 0] or tenders[:1]
    payload.pop("tendered_q", None)
    # A venda não é mais da comanda (ela já fechou): sobe como balcão direto.
    for key in ("tab_session_key", "tab_ref", "expected_revision"):
        payload.pop(key, None)


def reopen_tab_with_leftovers(*, channel, config, plan: TabPlan, previous_data: dict, actor: str, operator_username: str):
    """A comanda segue viva com o que não foi cobrado: sessão nova, mesmo número.

    Roda na mesma transação da venda, DEPOIS do commit (a comanda antiga já não
    está aberta, e o número fica livre). As linhas entram pelo kernel, que as
    reprecifica como em qualquer salvar da comanda. A que já estava na cozinha
    entra como herdada (``kds_inherited_lines``): não volta ao KDS.
    """
    from shopman.shop.adapters.kds import KDS_INHERITED_KEY
    from shopman.shop.services import sessions as session_service

    if not plan.left_open:
        return None
    data = {
        "origin_channel": "pos",
        "fulfillment_type": "pickup",
        "tab_ref": plan.tab_ref,
        "tab_display": plan.tab_display,
        "pos_operator": operator_username,
        "last_touched_at": timezone.now().isoformat(),
    }
    for key in ("seating_spot_ref",):
        if previous_data.get(key):
            data[key] = previous_data[key]
    sales_mode = (previous_data.get("pos") or {}).get("sales_mode")
    if sales_mode:
        data["pos"] = {"sales_mode": sales_mode}
    if plan.inherited_fired:
        data[KDS_INHERITED_KEY] = list(plan.inherited_fired)
        data["fired_lines"] = sorted(plan.inherited_fired)
        data["fired_qty"] = {
            str(line["line_id"]): _qty_json(line.get("qty"))
            for line in plan.left_open
            if str(line.get("line_id")) in set(plan.inherited_fired)
        }
    session = session_service.create_session(channel.ref, handle_type="pos_tab", handle_ref=plan.tab_ref, data=data)
    ops = []
    for line in plan.left_open:
        op = {
            "op": "add_line",
            "line_id": str(line["line_id"]),
            "sku": line["sku"],
            "qty": line.get("qty", 1),
            "unit_price_q": int(line.get("unit_price_q") or 0),
        }
        if line.get("name"):
            op["name"] = line["name"]
        meta = {k: v for k, v in (line.get("meta") or {}).items() if not str(k).startswith("_")}
        if meta:
            op["meta"] = meta
        ops.append(op)
    session_service.modify_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=ops,
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )
    return session


def record_duplicate_on_paid_order(*, plan: TabPlan, payload: dict, captured_at: datetime, operator_username: str) -> str:
    """TUDO já estava pago: nenhum pedido nasce; a cobrança em dobro fica no pedido pago."""
    from shopman.orderman.models import Order

    from shopman.shop.services import pos

    order = Order.objects.select_for_update().get(ref=plan.paid_order_ref)
    data = dict(order.data or {})
    pos_data = dict(data.get("pos") or {})
    duplicates = list(pos_data.get("offline_duplicates") or [])
    key = pos._payload_client_request_id(payload)
    if not any(row.get("client_request_id") == key for row in duplicates):
        duplicates.append({
            "client_request_id": key,
            "captured_at": captured_at.isoformat(),
            "charged_total_q": int(plan.already_paid_q),
            "lines": plan.already_paid,
            "payment_methods": sorted(pos._payload_payment_method_set(payload)),
            "terminal_ref": str(payload.get("pos_terminal_ref") or ""),
            "shift_id": payload.get("cash_shift_id"),
            "operator": operator_username,
            "tab_ref": plan.tab_ref,
            "tab_display": plan.tab_display,
        })
    pos_data["offline_duplicates"] = duplicates
    data["pos"] = pos_data
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return order.ref


# ── O que o gerente e o operador leem ─────────────────────────────────


def _clock(iso: str) -> str:
    instant = _parse_instant(iso)
    return timezone.localtime(instant).strftime("%H:%M") if instant else ""


def _money(amount_q: int) -> str:
    return f"R$ {format_money(abs(int(amount_q)))}"


def manager_notes(order) -> list[str]:
    """As frases do gerente sobre a venda sem conexão deste pedido (vazio = nada a dizer)."""
    pos_data = (order.data or {}).get("pos") or {}
    return sale_notes(order) + duplicate_notes(order, pos_data.get("offline_duplicates") or [])


def sale_notes(order) -> list[str]:
    """O que a venda sem conexão QUE VIROU este pedido teve de ajuste (preço, comanda)."""
    pos_data = (order.data or {}).get("pos") or {}
    offline = pos_data.get("offline") or {}
    notes: list[str] = []
    when = _clock(offline.get("captured_at") or "")
    sale = f"A venda sem conexão das {when}" if when else "A venda sem conexão"
    pricing = offline.get("pricing") or {}
    diff = int(pricing.get("difference_q") or 0)
    if pricing and diff:
        direction = "acima" if diff > 0 else "abaixo"
        notes.append(
            f"{sale} (pedido {order.ref}) foi cobrada por {_money(pricing.get('charged_total_q') or 0)}; "
            f"pelos preços daquela hora seria {_money(pricing.get('server_total_q') or 0)}. "
            f"Valeu o cobrado: {_money(diff)} {direction} do preço."
        )
    tab = offline.get("tab") or {}
    tab_name = _tab_label(tab)
    outcome = tab.get("outcome")
    if outcome == "lines_left_open" and tab.get("left_open"):
        count = len(tab["left_open"])
        rest = (
            "1 item lançado em outro dispositivo segue aberto na comanda."
            if count == 1
            else f"{count} itens lançados em outro dispositivo seguem abertos na comanda."
        )
        notes.append(f"{sale} fechou na {tab_name} só os itens cobrados nela. {rest}")
    if outcome == "already_paid":
        notes.append(
            f"A {tab_name} já tinha sido paga em outro dispositivo (pedido {tab.get('paid_order_ref')}). "
            f"{sale} entrou só com os itens que não estavam pagos; "
            f"{_money(tab.get('already_paid_q') or 0)} foram cobrados de novo por itens já pagos. Devolva ao cliente."
        )
    if outcome == "tab_cleared":
        notes.append(f"A {tab_name} foi limpa em outro dispositivo durante a queda. {sale} entrou como venda de balcão.")
    for line in tab.get("adjusted") or []:
        name = line.get("name") or line.get("sku")
        if line.get("kind") == "removed_elsewhere":
            notes.append(f"{name}: o outro dispositivo tinha tirado da comanda, mas foi cobrado aqui. Valeu o cobrado.")
        else:
            notes.append(
                f"{name}: cobrado {_qty_json(line.get('charged_qty'))} aqui; "
                f"o outro dispositivo tinha {_qty_json(line.get('tab_qty'))}. Valeu o cobrado."
            )
    return notes


def duplicate_notes(order, rows: list[dict]) -> list[str]:
    """A cobrança em dobro de uma comanda que já estava paga neste pedido."""
    notes: list[str] = []
    for row in rows:
        row_when = _clock(row.get("captured_at") or "")
        notes.append(
            f"A {_tab_label(row)} já tinha sido paga neste pedido ({order.ref}) quando chegou a venda sem conexão"
            f"{' das ' + row_when if row_when else ''}, que cobrou de novo {_money(row.get('charged_total_q') or 0)} "
            "pelos mesmos itens. Nenhum pedido novo nasceu. Devolva ao cliente."
        )
    return notes


def _tab_label(row: dict) -> str:
    name = row.get("tab_display") or row.get("tab_ref")
    return f"comanda {name}" if name else "comanda"


def alert_manager(order_ref: str, *, duplicate_of: str = "") -> None:
    """Um aviso no Gestor com a frase do gerente. Nunca derruba a venda.

    ``duplicate_of``: a chave da venda guardada que achou a comanda já paga. O
    aviso fala só dela, não de tudo o que o pedido pago já viveu.
    """
    try:
        from shopman.orderman.models import Order

        from shopman.shop.adapters import alert as alert_adapter

        order = Order.objects.filter(ref=order_ref).first()
        if order is None:
            return
        if duplicate_of:
            rows = (order.data or {}).get("pos", {}).get("offline_duplicates") or []
            notes = duplicate_notes(order, [row for row in rows if row.get("client_request_id") == duplicate_of])
        else:
            notes = sale_notes(order)
        if not notes:
            return
        alert_adapter.create(ALERT_TYPE, "warning", " ".join(notes), order_ref=order_ref)
    except Exception:
        logger.exception("pos_offline_alert_failed order=%s", order_ref)


def deepcopy_payload(payload: dict) -> dict:
    return copy.deepcopy(payload)
