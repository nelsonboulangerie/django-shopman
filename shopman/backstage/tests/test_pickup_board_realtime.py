"""O painel de retirada recebe o push da cozinha (ADR-016).

Queixa do dono (13/10/2026, de novo): o status da cozinha não chegava em tempo
real ao painel de retirada. Medido no alpha: o painel assinava
``backstage-orders-main``, e

1. a TV abre o painel sem sessão de operador (ou com a do caixa): o canal
   respondia ``stream-error`` "Permission denied", e a tela vivia do poll;
2. mesmo com permissão, o Pronto da cozinha numa COMANDA (que é ``Session``, não
   ``Order``) não publicava nada naquele canal;
3. e a venda do balcão (``PDV-...``) tinha o aviso cortado de propósito, porque o
   canal é do Gestor.

O painel ganha um canal próprio, público e de corpo vazio: o push só diz
"mudou", e o painel refaz o GET público, que é a verdade.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import resolve
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.eventstream import ShopmanChannelManager
from shopman.shop.handlers._sse_emitters import PICKUP_BOARD_CHANNEL

pytestmark = pytest.mark.django_db


@pytest.fixture
def enviados(monkeypatch):
    sent: list[tuple[str, str, dict]] = []

    def fake_send_event(channel, event_type, payload, *args, **kwargs):
        sent.append((channel, event_type, payload))

    monkeypatch.setattr("django_eventstream.send_event", fake_send_event)
    return sent


def _no_painel(sent):
    return [(t, p) for c, t, p in sent if c == PICKUP_BOARD_CHANNEL]


def test_a_tv_sem_sessao_le_o_canal_do_painel():
    manager = ShopmanChannelManager()
    assert manager.can_read_channel(AnonymousUser(), PICKUP_BOARD_CHANNEL) is True
    assert manager.can_read_channel(None, PICKUP_BOARD_CHANNEL) is True
    # Efêmero: a verdade é o GET, não há histórico a retomar.
    assert manager.is_channel_reliable(PICKUP_BOARD_CHANNEL) is False


def test_o_stream_do_painel_mora_ao_lado_do_get_publico():
    match = resolve("/api/v1/backstage/kds/pickup/events/")
    assert match.kwargs == {"channels": [PICKUP_BOARD_CHANNEL]}


def test_o_pronto_da_cozinha_numa_comanda_avisa_o_painel(enviados, django_capture_on_commit_callbacks):
    estacao = KDSInstance.objects.create(ref="bancada", name="Bancada", type="prep")
    with django_capture_on_commit_callbacks(execute=True):
        ticket = KDSTicket.objects.create(
            session_key="sess-comanda",
            kds_instance=estacao,
            items=[{"line_id": "L-1", "sku": "PAO", "name": "Pão", "qty": 1}],
            status="pending",
        )
    assert _no_painel(enviados), "disparar para a cozinha já põe a comanda em preparo"

    for status in ("in_progress", "done", "pending", "cancelled"):  # iniciar, Pronto, Desfazer, cancelar
        enviados.clear()
        with django_capture_on_commit_callbacks(execute=True):
            ticket.status = status
            ticket.save(update_fields=["status"])
        avisos = _no_painel(enviados)
        assert avisos, f"o painel não soube do ticket em {status}"
        # Corpo vazio: nada que o GET público não mostre.
        assert all(p == {} for _, p in avisos)
        assert all(t == "pickup-board-update" for t, _ in avisos)


def test_a_venda_do_balcao_tambem_avisa_o_painel(enviados, django_capture_on_commit_callbacks):
    """O Gestor não vê a venda do balcão; o painel de retirada vê."""
    order = Order.objects.create(
        ref="PDV-PAINEL-1",
        channel_ref="pdv",
        status="preparing",
        total_q=1000,
        data={"origin_channel": "pos", "pos": {"sales_mode": "counter"}},
    )
    enviados.clear()
    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status("ready")

    assert _no_painel(enviados) == [("pickup-board-update", {})]
    # O corte do Gestor continua: a venda do balcão não vai para a fila dele.
    assert not [c for c, _, _ in enviados if c.startswith("backstage-orders")]
