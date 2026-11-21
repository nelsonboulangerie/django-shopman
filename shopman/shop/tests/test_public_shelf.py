"""A vitrine pública só avisa quando o estado público de um SKU muda (#2784).

O canal ``shelf-<canal>`` leva o SKU, então não pode contar vendas: o aviso sai quando
muda o que qualquer visitante já vê (o estado do card, as últimas unidades, o dia da
promessa), e só para o canal que tem vitrine pública (registrado pelo storefront).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache

from shopman.shop.handlers import _sse_emitters
from shopman.shop.services import public_shelf


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    before = set(public_shelf._PUBLIC_CHANNELS)
    public_shelf._PUBLIC_CHANNELS.clear()
    public_shelf.register_public_channel("web")
    yield
    public_shelf._PUBLIC_CHANNELS.clear()
    public_shelf._PUBLIC_CHANNELS.update(before)
    cache.clear()


def _shelf_events(send_event) -> list[tuple]:
    return [call.args for call in send_event.call_args_list if call.args[0].startswith("shelf-")]


def test_dez_vendas_que_nao_mudam_o_estado_publico_nao_geram_aviso():
    state = ("available", None, "2026-11-21")
    with (
        patch.object(public_shelf, "public_signature", return_value=state),
        patch.object(public_shelf, "bundles_using", return_value=[]),
        patch.object(_sse_emitters, "_channels_for_sku", return_value=["web", "balcao"]),
        patch("django_eventstream.send_event") as send_event,
    ):
        # A primeira leitura não tem lembrança: sai um aviso (barato), e fica lembrada.
        _sse_emitters._publish_for_sku("CRO", event_type="stock-update", payload={"sku": "CRO"})
        assert _shelf_events(send_event) == [("shelf-web", "shelf-update", {"sku": "CRO"})]
        send_event.reset_mock()

        for _ in range(10):
            _sse_emitters._publish_for_sku("CRO", event_type="stock-update", payload={"sku": "CRO"})

        assert _shelf_events(send_event) == []
        # O canal cru continua recebendo tudo (operador, menuboard).
        assert sum(1 for c in send_event.call_args_list if c.args[0] == "stock-web") == 10


def test_quando_o_estado_publico_muda_sai_um_aviso_com_o_sku():
    states = iter([
        ("available", None, "2026-11-21"),
        ("low_stock", 2, "2026-11-21"),
        ("low_stock", 2, "2026-11-21"),
        ("low_stock", 1, "2026-11-21"),
        ("unavailable", None, "2026-11-22"),
    ])
    with (
        patch.object(public_shelf, "public_signature", side_effect=lambda *a, **k: next(states)),
        patch.object(public_shelf, "bundles_using", return_value=[]),
        patch.object(_sse_emitters, "_channels_for_sku", return_value=["web"]),
        patch("django_eventstream.send_event") as send_event,
    ):
        for _ in range(5):
            _sse_emitters._publish_for_sku("CRO", event_type="stock-update", payload={"sku": "CRO"})

    # Cinco leituras, quatro estados diferentes: quatro avisos (a repetida não sai).
    assert _shelf_events(send_event) == [("shelf-web", "shelf-update", {"sku": "CRO"})] * 4


def test_o_pacote_que_usa_o_item_tem_aviso_com_o_proprio_sku():
    # O pão não muda de estado público, mas "restam 2 pacotes" vira "resta 1".
    signatures = {
        "PAO": [("available", None, "2026-11-21")] * 2,
        "PACOTE": [("low_stock", 2, "2026-11-21"), ("low_stock", 1, "2026-11-21")],
    }

    def signature(sku, **_):
        return signatures[sku].pop(0)

    with (
        patch.object(public_shelf, "public_signature", side_effect=signature),
        patch.object(public_shelf, "bundles_using", return_value=["PACOTE"]),
        patch.object(_sse_emitters, "_channels_for_sku", return_value=["web"]),
        patch("django_eventstream.send_event") as send_event,
    ):
        _sse_emitters._publish_for_sku("PAO", event_type="stock-update", payload={"sku": "PAO"})
        send_event.reset_mock()
        _sse_emitters._publish_for_sku("PAO", event_type="stock-update", payload={"sku": "PAO"})

    assert _shelf_events(send_event) == [("shelf-web", "shelf-update", {"sku": "PACOTE"})]


def test_canal_sem_vitrine_publica_nem_e_lido():
    with patch.object(public_shelf, "public_signature") as signature:
        changed = public_shelf.changed_channels("CRO", ["balcao", "ifood"])

    assert changed == []
    signature.assert_not_called()


def test_falha_ao_ler_conta_como_mudanca_e_nao_lembra():
    with patch.object(public_shelf, "public_signature", side_effect=RuntimeError("sem estoque")):
        assert public_shelf.changed_channels("CRO", ["web"]) == ["web"]
        assert public_shelf.changed_channels("CRO", ["web"]) == ["web"]


@pytest.mark.django_db
def test_lista_do_canal_mudou_avisa_a_vitrine_inteira():
    with patch("django_eventstream.send_event") as send_event:
        _sse_emitters._publish_surface_changed("web")

    assert ("shelf-web", "shelf-update", {}) in [c.args for c in send_event.call_args_list]
