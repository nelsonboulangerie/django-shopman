"""Gestor de pedidos, beta 06/11/2026.

(a) a linha do tempo dizia "Customer cancellation requested", em inglês: tipo de
    evento sem rótulo caía no fallback que humaniza o código. A trava abaixo lê o
    código e reprova evento de pedido sem rótulo;
(b) recusar com o motivo pronto "Você pediu o cancelamento" gravava "Outro motivo";
    a recusa agora usa a lista única do cancelar, e grava a chave escolhida.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from shopman.orderman.models import Order

from shopman.backstage.projections import order_queue
from shopman.shop.models import Shop
from shopman.shop.services import operator_orders

REPO = Path(__file__).resolve().parents[3]

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

# ── (a) todo evento que o sistema grava no pedido tem rótulo em português ──

#: Onde o sistema grava evento de pedido. Fora: testes e migrações (história).
_SCAN_ROOTS = ("shopman", "packages", "config")
#: ``emit_event`` também existe na sessão do PDV (``Session``/``POSTab``), que tem
#: histórico próprio e não passa por esta linha do tempo.
_SESSION_EVENT_FILES = {"shopman/shop/services/pos.py"}
#: Tipos com rótulo próprio fora de ``_EVENT_LABELS``: a mudança de status vira o
#: nome do status novo.
_LABELLED_ELSEWHERE = set(order_queue._STATUS_EVENT_TYPES)


def _module_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    return constants


def _event_type_arg(call: ast.Call, *, keyword: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    if keyword == "event_type" and call.args:
        return call.args[0]
    return None


def _emitted_order_event_types() -> dict[str, set[str]]:
    """Tipo de evento → arquivos que o gravam, lidos do código (AST), não de uma lista."""
    found: dict[str, set[str]] = {}
    unresolved: list[str] = []
    for root in _SCAN_ROOTS:
        for path in (REPO / root).rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in rel or "/migrations/" in rel or "node_modules" in rel or rel in _SESSION_EVENT_FILES:
                continue
            source = path.read_text(encoding="utf-8")
            if "emit_event(" not in source and "_create_order_event(" not in source:
                continue
            tree = ast.parse(source)
            constants = _module_constants(tree)
            # ``def _emit(order, event_type)`` repassa: os tipos chegam pelas chamadas a ``_emit``.
            forwarders = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "emit_event"
                    and isinstance(_event_type_arg(call, keyword="event_type"), ast.Name)
                    and _event_type_arg(call, keyword="event_type").id in {a.arg for a in node.args.args}
                    for call in ast.walk(node)
                )
            }
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
                if name == "emit_event":
                    arg = _event_type_arg(call, keyword="event_type")
                    if isinstance(arg, ast.Name) and any(
                        isinstance(fn, ast.FunctionDef) and fn.name in forwarders and call in ast.walk(fn)
                        for fn in ast.walk(tree)
                    ):
                        continue
                elif name in forwarders:
                    arg = call.args[1] if len(call.args) > 1 else None
                elif name == "_create_order_event":
                    arg = _event_type_arg(call, keyword="type")
                else:
                    continue
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    value = arg.value
                elif isinstance(arg, ast.Name) and arg.id in constants:
                    value = constants[arg.id]
                else:
                    unresolved.append(f"{rel}:{call.lineno}")
                    continue
                found.setdefault(value, set()).add(rel)
    assert not unresolved, (
        "Evento de pedido com tipo que o teste não sabe ler (use literal ou constante do módulo): "
        + ", ".join(unresolved)
    )
    return found


def test_the_scan_finds_the_events_it_must_find():
    found = _emitted_order_event_types()
    # Sentinelas: um de cada forma (literal, constante, repasse por ``_emit``).
    assert "customer_contact_requested" in found
    assert "operator_comment" in found
    assert "ifood_accept_failed" in found
    assert "status_changed" in found


def test_every_order_event_the_system_writes_has_a_portuguese_label():
    found = _emitted_order_event_types()
    missing = sorted(
        f"{event_type} ({', '.join(sorted(files))})"
        for event_type, files in found.items()
        if event_type not in order_queue._EVENT_LABELS and event_type not in _LABELLED_ELSEWHERE
    )
    assert not missing, "Evento sem rótulo na linha do tempo do Gestor: " + "; ".join(missing)


def _timeline_labels(order: Order) -> list[str]:
    return [event.label for event in order_queue._build_timeline(order)]


@pytest.fixture
def web_order(db):
    return Order.objects.create(ref="NB-LINHA-1", channel_ref="web", status="accepted", total_q=2000)


def test_courier_status_reads_as_the_ride_step(web_order):
    web_order.emit_event(event_type="courier_status", actor="courier:webhook", payload={"status": "E", "id_mch": "1"})
    web_order.emit_event(event_type="courier_status", actor="courier:webhook", payload={"status": "?", "id_mch": "1"})

    labels = _timeline_labels(web_order)
    assert "TaOn: Saiu para entrega" in labels
    assert "Corrida da TaOn atualizada" in labels


# ── (b) a recusa usa a lista única de motivos e grava a chave escolhida ──


@pytest.fixture
def new_web_order(db):
    Shop.load() or Shop.objects.create(name="Loja")
    return Order.objects.create(ref="NB-RECUSA-1", channel_ref="web", status="new", total_q=2000)


def test_reject_with_the_customer_asked_records_customer_request(new_web_order):
    operator_orders.reject_order(
        new_web_order, reason="O cliente pediu", reason_key="customer_request", internal_note="ligou às 9h",
        actor="gestor:ana", rejected_by="operator",
    )

    new_web_order.refresh_from_db()
    assert new_web_order.status == "cancelled"
    assert new_web_order.data["cancellation_reason_key"] == "customer_request"
    assert new_web_order.data["cancellation_internal_note"] == "ligou às 9h"
    cancelled = [item for item in order_queue._build_timeline(new_web_order) if item.label == "Cancelado"]
    assert cancelled and cancelled[-1].detail.startswith("O cliente pediu")


def test_reject_outside_the_list_is_refused(new_web_order):
    with pytest.raises(ValueError):
        operator_orders.reject_order(
            new_web_order, reason="Forno quebrou agora", actor="gestor:ana", rejected_by="operator",
        )
    new_web_order.refresh_from_db()
    assert new_web_order.status == "new"


def test_reject_notice_reads_the_reviewed_sentence(new_web_order):
    from shopman.shop.services import cancel_reasons
    from shopman.shop.services.notification import _status_note

    operator_orders.reject_order(
        new_web_order, reason="Acabou um item", reason_key="out_of_stock", actor="gestor:ana", rejected_by="operator",
    )
    new_web_order.refresh_from_db()

    assert _status_note(new_web_order, "order_rejected", "Acabou um item") == cancel_reasons.cancel_reason("out_of_stock").customer_text


def test_contact_requested_says_which_door_it_came_from(web_order):
    web_order.emit_event("customer_contact_requested", actor="customer:self-service", payload={"rating": 2})
    web_order.emit_event(
        "customer_contact_requested", actor="customer:self-service", payload={"origin": "cancellation"}
    )

    labels = _timeline_labels(web_order)
    assert "Cliente avaliou mal e pediu para falar com o responsável" in labels
    assert "Cliente quis cancelar com o preparo começado e pediu para falar com o responsável" in labels
