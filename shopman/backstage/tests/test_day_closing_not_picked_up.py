"""Fechamento do dia com pedido pronto que ninguém veio buscar (#2684, WP-G11).

Decisão do plano do Gestor (seção 10, pergunta 5 do mapa do "Não retirado"): o
fechamento segura enquanto houver pedido pronto de retirada não resolvido, lista
os pedidos e resolve com UMA autorização de Gerente, aplicando a cada um o mesmo
"Não retirado" do Gestor. O que esta suíte prende:

- o pedido cujo "Não retirado" já pode ser feito SEGURA o dia (409
  ``pending_ready_orders``), e a assinatura encerra todos de uma vez, cada um pelo
  serviço do Gestor, gravando quem assinou no fechamento;
- o pedido ainda no prazo e o que fica com o Dono aparecem e não seguram;
- o pedido combinado para depois do dia não entra;
- a tela velha (pedido que mudou, pedido novo na lista) é recusada inteira;
- com produção aberta também, um PIN só vale para as duas liberações;
- cada linha mostra o valor DELE, nunca uma soma.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.services import closing as closing_service
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]


@pytest.fixture
def relogio(monkeypatch):
    def set_now(hour: int, minute: int = 0, *, days: int = 0):
        moment = world.at(hour, minute, days=days)
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment

    return set_now


@pytest.fixture
def paes():
    world.make_shop()
    world.product("CROIS", price_q=935)
    world.lot("CROIS")


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="fecha", password="x")


@pytest.fixture
def manager(db):
    from django.contrib.auth.models import Permission
    from shopman.doorman.models import PinCredential

    manager = get_user_model().objects.create_user(username="gerente", password="x", is_staff=True)
    manager.user_permissions.add(Permission.objects.get(content_type__app_label="cashman", codename="adjust_shift"))
    PinCredential.set_for(manager, "4321")
    return manager


def _today_at(slot: str, *, days: int = 0) -> dict:
    return {"delivery_date": (timezone.localdate() + timedelta(days=days)).isoformat(), "delivery_time_slot": slot}


def _assinatura(manager, closing, *, pin: str = "4321") -> dict:
    return {
        "orders": [{"ref": row.ref, "revision": row.revision} for row in closing.pending_ready_orders if row.state == "resolve"],
        "manager_approval": {"username": manager.username, "pin": pin},
    }


def _fechar(user, **kwargs):
    return closing_service.perform_day_closing(user=user, items=[], quantities_by_sku={}, **kwargs)


def test_pedido_que_ja_pode_ser_nao_retirado_segura_o_dia(paes, relogio, user):
    relogio(10)
    world.ready_order("FD-SEGURA", [("CROIS", 1, 935)], data=_today_at("10:00-10:30"))

    relogio(19)
    closing = build_day_closing()
    assert closing.has_pending_ready_orders
    (row,) = closing.pending_ready_orders
    assert (row.ref, row.state) == ("FD-SEGURA", "resolve")
    assert row.promised_display == "Combinado para 10h"
    assert row.money_sentence == "O pedido não foi pago: não há dinheiro a devolver."
    assert row.revision

    with pytest.raises(closing_service.PendingReadyOrdersBlockClosing) as exc:
        _fechar(user)
    assert exc.value.code == "pending_ready_orders"
    assert "Um pedido pronto não foi retirado" in str(exc.value)
    assert not DayClosing.objects.exists()


def test_uma_assinatura_encerra_todos_pelo_servico_do_gestor(paes, relogio, user, manager):
    relogio(9)
    a = world.ready_order("FD-A", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    b = world.ready_order("FD-B", [("CROIS", 2, 935)], data=_today_at("09:30-10:00"))
    world.pay(b, "pix")

    relogio(19)
    closing = build_day_closing()
    _fechar(user, ready_orders_release=_assinatura(manager, closing))

    for order in (a, b):
        order.refresh_from_db()
        assert order.status == Order.Status.CANCELLED
        assert order.data["cancellation_reason_key"] == "not_picked_up"
        assert order.data["no_show"]["approved_by"] == "gerente"
        assert order.data["no_show"]["actor"] == "fecha"
    record = DayClosing.objects.get().data["ready_orders_resolution"]
    assert record["approved_by"] == "gerente"
    assert record["requested_by"] == "fecha"
    assert record["orders"] == ["FD-A", "FD-B"]


def test_pin_errado_nao_encerra_nada(paes, relogio, user, manager):
    from shopman.shop.services.pos_intent import PosIntentError

    relogio(9)
    order = world.ready_order("FD-PIN", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    with pytest.raises(PosIntentError):
        _fechar(user, ready_orders_release=_assinatura(manager, build_day_closing(), pin="0000"))

    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert not DayClosing.objects.exists()


def test_pedido_ainda_no_prazo_aparece_e_nao_segura(paes, relogio, user):
    relogio(10)
    world.ready_order("FD-PRAZO", [("CROIS", 1, 935)], data=_today_at("17:30-18:00"))

    relogio(17, 45)
    closing = build_day_closing()
    (row,) = closing.pending_ready_orders
    assert row.state == "in_time"
    assert "libera às 18h30" in row.reason
    assert not closing.has_pending_ready_orders

    _fechar(user)
    assert DayClosing.objects.get().data["ready_orders_resolution"] is None


def test_pedido_de_amanha_nao_entra(paes, relogio):
    relogio(10)
    world.ready_order("FD-AMANHA", [("CROIS", 1, 935)], data=_today_at("09:00-09:30", days=1))

    relogio(19)
    assert build_day_closing().pending_ready_orders == ()


def test_pedido_que_fica_com_o_dono_aparece_e_nao_segura(paes, relogio, user):
    relogio(9)
    order = world.ready_order("FD-DONO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    # O ciclo padrão do Orderman (canal sem ``lifecycle.transitions``): pronto não cancela.
    Order.objects.filter(pk=order.pk).update(snapshot={"items": order.snapshot["items"]})

    relogio(19)
    closing = build_day_closing()
    (row,) = closing.pending_ready_orders
    assert row.state == "owner"
    assert row.reason == "Este canal não permite encerrar um pedido pronto como não retirado."
    assert not closing.has_pending_ready_orders

    _fechar(user)
    assert DayClosing.objects.exists()


def test_pedido_que_mudou_depois_da_leitura_recusa_o_fechamento_inteiro(paes, relogio, user, manager):
    relogio(9)
    order = world.ready_order("FD-VELHA", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    stale = _assinatura(manager, build_day_closing())
    world.pay(order, "pix")  # o dinheiro do gesto mudou depois que a tela leu

    with pytest.raises(closing_service.PendingReadyOrdersBlockClosing, match="mudou depois"):
        _fechar(user, ready_orders_release=stale)
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert not DayClosing.objects.exists()


def test_pedido_novo_que_a_tela_nao_mostrou_recusa(paes, relogio, user, manager):
    relogio(9)
    world.ready_order("FD-VISTO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    assinatura = _assinatura(manager, build_day_closing())
    world.ready_order("FD-NOVO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    with pytest.raises(closing_service.PendingReadyOrdersBlockClosing, match="ainda não mostrava"):
        _fechar(user, ready_orders_release=assinatura)


def test_um_pin_so_com_producao_aberta(paes, relogio, user, manager, monkeypatch):
    from shopman.shop.services import pos as pos_service

    relogio(9)
    order = world.ready_order("FD-UM-PIN", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    monkeypatch.setattr(closing_service, "_pending_production_snapshot", lambda _day: [{"ref": "WO-1"}])
    checks = []
    real = pos_service.validate_manager_override
    monkeypatch.setattr(pos_service, "validate_manager_override", lambda *a, **k: checks.append(k["action"]) or real(*a, **k))

    relogio(19)
    approval = {"username": manager.username, "pin": "4321"}
    release = {"reason": "Fornada da noite", "manager_approval": approval}
    _fechar(user, production_release=release, ready_orders_release={**_assinatura(manager, build_day_closing()), "manager_approval": approval})

    assert checks == ["day_closing_release_production"]
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_cada_linha_mostra_o_valor_dela_e_nada_somado(paes, relogio, client, user):
    """Regra do dono (21/11/2026): o valor de cada registro, nunca o agregado."""
    from django.contrib.auth.models import Permission

    relogio(9)
    for ref in ("FD-V1", "FD-V2"):
        order = world.ready_order(ref, [("CROIS", 1, 935)], data=_today_at("09:00-09:30"), held=False)
        world.pay(order, "cash")

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(Permission.objects.get(content_type__app_label="backstage", codename="perform_closing"))
    client.force_login(user)
    relogio(19)
    body = client.get("/api/v1/backstage/closing/").json()["closing"]

    rows = body["pending_ready_orders"]
    assert [row["ref"] for row in rows] == ["FD-V1", "FD-V2"]
    assert all("R$ 9,35" in row["money_sentence"] for row in rows)
    assert "R$ 18,70" not in str(body)
    assert not any(key.endswith("_total") or key.endswith("_sum") for key in body if "ready" in key)
