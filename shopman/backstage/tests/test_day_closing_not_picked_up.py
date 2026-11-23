"""Fechamento do dia com pedido aberto: AVISA e não trava (#2684, #3169).

Decisão da coordenação em 22/11/2026, reversível: o fechamento avisa e oferece o
gesto em lote, não trava (substitui o padrão da resposta 5 do mapa do "Não
retirado", de 17/11). O que esta suíte prende:

- nenhum pedido aberto segura o dia: o fechamento grava as listas e fecha;
- os prontos não retirados aparecem com o que cabe a cada um (``resolve``,
  ``in_time``, ``owner``) e o valor DELE, nunca uma soma;
- "Encerrar todos como não retirado" é um gesto próprio, opcional, assinado por um
  Gerente: encerra cada pedido pelo serviço do Gestor; PIN errado, tela velha ou
  pedido novo na lista recusam o gesto inteiro;
- os pedidos abertos que não ficaram prontos (novo, aceito, em preparo, a entrega)
  aparecem com o caminho de cada um: cancelar, remarcar ou concluir;
- o pedido combinado para depois do dia não entra em lista nenhuma.
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


def _aberto(ref: str, status: str, *, channel_ref: str = "web", data: dict | None = None) -> Order:
    return Order.objects.create(
        ref=ref, channel_ref=channel_ref, session_key=f"sk-{ref}", status=status, total_q=935,
        data={"fulfillment_type": "pickup", "payment": {"method": "cash"}, "customer": {"name": "Rita"}, **(data or {})},
        snapshot={"lifecycle": {"transitions": world.TRANSITIONS}, "items": []},
    )


# ── Nada trava ──────────────────────────────────────────────────────────────


def test_pronto_nao_retirado_aparece_e_o_dia_fecha_mesmo_assim(paes, relogio, user):
    relogio(10)
    order = world.ready_order("FD-AVISA", [("CROIS", 1, 935)], data=_today_at("10:00-10:30"))

    relogio(19)
    closing = build_day_closing()
    (row,) = closing.pending_ready_orders
    assert (row.ref, row.state) == ("FD-AVISA", "resolve")
    assert row.promised_display == "Combinado para 10h"
    assert row.money_sentence == "O pedido não foi pago: não há dinheiro a devolver."
    assert row.revision

    _fechar(user)

    order.refresh_from_db()
    assert order.status == Order.Status.READY  # segue aberto: aparece de novo no Gestor amanhã
    record = DayClosing.objects.get().data
    assert [r["ref"] for r in record["pending_ready_orders"]] == ["FD-AVISA"]
    assert "ready_orders_resolution" not in record


def test_pedidos_abertos_que_nao_ficaram_prontos_aparecem_com_o_caminho_de_cada_um(paes, relogio, user):
    relogio(9)
    _aberto("FD-NOVO", Order.Status.NEW)
    _aberto("FD-ACEITO", Order.Status.ACCEPTED)
    _aberto("FD-PREPARO", Order.Status.PREPARING)
    _aberto("FD-IFOOD", Order.Status.NEW, channel_ref="ifood")
    _aberto("FD-SAIDA", Order.Status.READY, data={"fulfillment_type": "delivery"})
    _aberto("FD-RUA", Order.Status.DISPATCHED, data={"fulfillment_type": "delivery"})
    _aberto("FD-AMANHA", Order.Status.ACCEPTED, data=_today_at("09:00-09:30", days=1))

    relogio(19)
    rows = {row.ref: row for row in build_day_closing().pending_open_orders}

    assert "FD-AMANHA" not in rows
    assert {ref: row.path for ref, row in rows.items()} == {
        "FD-NOVO": "cancel_or_reschedule",
        "FD-ACEITO": "cancel_or_reschedule",
        "FD-PREPARO": "conclude_or_cancel",
        "FD-IFOOD": "cancel",
        "FD-SAIDA": "conclude",
        "FD-RUA": "conclude",
    }
    assert rows["FD-NOVO"].path_sentence == "Cancele ou remarque no Gestor."
    assert rows["FD-PREPARO"].path_sentence == "Já está na Cozinha: conclua ou cancele no Gestor."
    assert rows["FD-RUA"].path_sentence == "Conclua no Gestor quando a entrega chegar."
    assert rows["FD-PREPARO"].status_label == "Em preparo"
    assert rows["FD-NOVO"].customer_name == "Rita"

    _fechar(user)

    assert Order.objects.filter(status__in=["new", "accepted", "preparing", "ready", "dispatched"]).count() == 7
    record = DayClosing.objects.get().data["pending_open_orders"]
    assert {r["ref"] for r in record} == set(rows)


def test_o_pronto_de_retirada_fica_so_na_lista_dos_nao_retirados(paes, relogio):
    relogio(9)
    world.ready_order("FD-RETIRA", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    closing = build_day_closing()
    assert [row.ref for row in closing.pending_ready_orders] == ["FD-RETIRA"]
    assert closing.pending_open_orders == ()


def test_pedido_de_amanha_nao_entra(paes, relogio):
    relogio(10)
    world.ready_order("FD-AMANHA", [("CROIS", 1, 935)], data=_today_at("09:00-09:30", days=1))

    relogio(19)
    assert build_day_closing().pending_ready_orders == ()


def test_pedido_ainda_no_prazo_e_o_que_fica_com_o_dono_aparecem(paes, relogio, user):
    relogio(9)
    world.ready_order("FD-PRAZO", [("CROIS", 1, 935)], data=_today_at("18:30-19:00"))
    dono = world.ready_order("FD-DONO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    # O ciclo padrão do Orderman (canal sem ``lifecycle.transitions``): pronto não cancela.
    Order.objects.filter(pk=dono.pk).update(snapshot={"items": dono.snapshot["items"]})

    relogio(18, 45)
    rows = {row.ref: row for row in build_day_closing().pending_ready_orders}
    assert rows["FD-PRAZO"].state == "in_time"
    assert "libera às" in rows["FD-PRAZO"].reason
    assert rows["FD-DONO"].state == "owner"
    assert rows["FD-DONO"].reason == "Este canal não permite encerrar um pedido pronto como não retirado."

    _fechar(user)
    assert DayClosing.objects.exists()


# ── O gesto em lote, opcional ───────────────────────────────────────────────


def test_encerrar_todos_encerra_cada_um_pelo_servico_do_gestor(paes, relogio, user, manager):
    relogio(9)
    a = world.ready_order("FD-A", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    b = world.ready_order("FD-B", [("CROIS", 2, 935)], data=_today_at("09:30-10:00"))
    world.pay(b, "pix")

    relogio(19)
    record = closing_service.resolve_not_picked_up(user=user, release=_assinatura(manager, build_day_closing()))

    assert record["approved_by"] == "gerente"
    assert record["requested_by"] == "fecha"
    assert record["orders"] == ["FD-A", "FD-B"]
    for order in (a, b):
        order.refresh_from_db()
        assert order.status == Order.Status.CANCELLED
        assert order.data["cancellation_reason_key"] == "not_picked_up"
        assert order.data["no_show"]["approved_by"] == "gerente"
        assert order.data["no_show"]["actor"] == "fecha"
    # O gesto não fecha o dia: quem fecha é o fechamento, depois, se quiser.
    assert not DayClosing.objects.exists()
    assert build_day_closing().pending_ready_orders == ()


def test_pin_errado_nao_encerra_nada(paes, relogio, user, manager):
    from shopman.shop.services.pos_intent import PosIntentError

    relogio(9)
    order = world.ready_order("FD-PIN", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    with pytest.raises(PosIntentError):
        closing_service.resolve_not_picked_up(user=user, release=_assinatura(manager, build_day_closing(), pin="0000"))

    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_pedido_que_mudou_depois_da_leitura_recusa_o_gesto_inteiro(paes, relogio, user, manager):
    relogio(9)
    primeiro = world.ready_order("FD-PRIMEIRO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    velho = world.ready_order("FD-VELHA", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    stale = _assinatura(manager, build_day_closing())
    world.pay(velho, "pix")  # o dinheiro do gesto mudou depois que a tela leu

    with pytest.raises(closing_service.NotPickedUpBatchRefused, match="mudou depois"):
        closing_service.resolve_not_picked_up(user=user, release=stale)
    for order in (primeiro, velho):
        order.refresh_from_db()
        assert order.status == Order.Status.READY  # uma transação: nenhum encerrado


def test_pedido_novo_que_a_tela_nao_mostrou_recusa(paes, relogio, user, manager):
    relogio(9)
    world.ready_order("FD-VISTO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    relogio(19)
    assinatura = _assinatura(manager, build_day_closing())
    world.ready_order("FD-NOVO", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    with pytest.raises(closing_service.NotPickedUpBatchRefused, match="ainda não mostrava"):
        closing_service.resolve_not_picked_up(user=user, release=assinatura)


def test_sem_nada_a_encerrar_o_gesto_recusa(paes, relogio, user, manager):
    relogio(19)
    with pytest.raises(closing_service.NotPickedUpBatchRefused, match="Não há pedido pronto"):
        closing_service.resolve_not_picked_up(
            user=user, release={"orders": [], "manager_approval": {"username": manager.username, "pin": "4321"}},
        )


# ── A tela ──────────────────────────────────────────────────────────────────


def _gerencia(user):
    from django.contrib.auth.models import Permission

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(Permission.objects.get(content_type__app_label="backstage", codename="perform_closing"))


def test_cada_linha_mostra_o_valor_dela_e_nada_somado(paes, relogio, client, user):
    """Regra do dono (21/11/2026): o valor de cada registro, nunca o agregado."""
    relogio(9)
    for ref in ("FD-V1", "FD-V2"):
        order = world.ready_order(ref, [("CROIS", 1, 935)], data=_today_at("09:00-09:30"), held=False)
        world.pay(order, "cash")
    _aberto("FD-V3", Order.Status.ACCEPTED)

    _gerencia(user)
    client.force_login(user)
    relogio(19)
    body = client.get("/api/v1/backstage/closing/").json()["closing"]

    rows = body["pending_ready_orders"]
    assert [row["ref"] for row in rows] == ["FD-V1", "FD-V2"]
    assert all("R$ 9,35" in row["money_sentence"] for row in rows)
    assert [row["ref"] for row in body["pending_open_orders"]] == ["FD-V3"]
    assert "R$ 18,70" not in str(body)
    assert "has_pending_ready_orders" not in body
    assert not any(key.endswith("_total") or key.endswith("_sum") for key in body if "orders" in key)


def test_o_fechamento_pela_api_fecha_com_pedido_aberto(paes, relogio, client, user):
    relogio(9)
    world.ready_order("FD-API", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))
    _aberto("FD-API-2", Order.Status.PREPARING)

    _gerencia(user)
    client.force_login(user)
    relogio(19)
    response = client.post("/api/v1/backstage/closing/", {"quantities": {}}, content_type="application/json")

    assert response.status_code == 200, response.content
    assert DayClosing.objects.exists()


def test_o_gesto_em_lote_pela_api(paes, relogio, client, user, manager):
    relogio(9)
    order = world.ready_order("FD-API-LOTE", [("CROIS", 1, 935)], data=_today_at("09:00-09:30"))

    _gerencia(user)
    client.force_login(user)
    relogio(19)
    url = "/api/v1/backstage/closing/not-picked-up/"
    stale = _assinatura(manager, build_day_closing())
    world.pay(order, "pix")
    refused = client.post(url, stale, content_type="application/json")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "not_picked_up_refused"

    response = client.post(url, _assinatura(manager, build_day_closing()), content_type="application/json")
    assert response.status_code == 200, response.content
    assert response.json()["orders"] == ["FD-API-LOTE"]
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
