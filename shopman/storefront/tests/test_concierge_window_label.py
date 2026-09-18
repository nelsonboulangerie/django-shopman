"""O concierge fala a janela como o cliente a combinou — pelas DUAS grades.

Partir o ref no hífen para a entrega dava "slot às 09" no WhatsApp: o canônico
de uma encomenda de ENTREGA vazando como texto. O resolvedor é um só
(``fulfillment_window.window_label``); quem decide é a FORMA do ref, não o
tipo de recebimento.
"""

from __future__ import annotations

import pytest

from shopman.storefront.concierge.tools import _fulfillment_payload, _slot_label

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("fulfillment_type", ["delivery", "pickup"])
def test_o_canonico_sai_com_o_rotulo_da_casa_em_qualquer_recebimento(fulfillment_type):
    assert _slot_label(fulfillment_type, "slot-09") == "A partir das 9h"


@pytest.mark.parametrize("fulfillment_type", ["delivery", "pickup"])
def test_a_meia_hora_sai_como_par_de_horas_em_qualquer_recebimento(fulfillment_type):
    assert _slot_label(fulfillment_type, "14:00-14:30") == "14:00 às 14:30"


def test_ref_desconhecido_sai_cru_e_vazio_sai_vazio():
    assert _slot_label("pickup", "manhã") == "manhã"
    assert _slot_label("pickup", "") == ""


def test_o_payload_de_fulfillment_carrega_o_rotulo_resolvido():
    payload = _fulfillment_payload({
        "fulfillment_type": "delivery",
        "delivery_date": "2026-09-20",
        "delivery_time_slot": "slot-12",
        "delivery_address": "Rua das Flores, 10",
    })

    assert payload["slot_ref"] == "slot-12"
    assert payload["slot_label"] == "A partir das 12h"
