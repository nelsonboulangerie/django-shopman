"""Beta 06/11: a home prometia "até 7 dias" e o checkout aceitava 22.

O número da janela de encomenda tem uma fonte só, ``max_preorder_days`` da casa:
o mesmo teto do calendário do checkout e da recusa no servidor. A copy da faceta
de encomenda traz ``{window}`` e a home troca pelo valor configurado.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS, WILDCARD
from shopman.storefront.presentation import home


@pytest.fixture
def janela(monkeypatch):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.projections import checkout_context

    state = {"days": 30, "preorder": True}
    monkeypatch.setattr(
        ChannelConfig,
        "for_channel",
        classmethod(lambda cls, ref: SimpleNamespace(stock=SimpleNamespace(preorder=state["preorder"]))),
    )
    monkeypatch.setattr(checkout_context, "preorder_config", lambda: (state["days"], []))
    return state


def _copy() -> str:
    return OMOTENASHI_DEFAULTS["HOW_PREORDER_MESSAGE"][WILDCARD][WILDCARD].message


def test_a_copy_padrao_nao_carrega_numero_fixo():
    message = _copy()

    assert "{window}" in message
    assert "7 dias" not in message
    assert "18h" not in message
    assert "—" not in message


@pytest.mark.parametrize(
    ("days", "expected"),
    [(30, "até 30 dias de antecedência"), (7, "até 7 dias de antecedência"), (1, "até 1 dia de antecedência")],
)
def test_a_faceta_diz_a_janela_configurada(janela, days, expected):
    janela["days"] = days

    message = home._preorder_facet_message(_copy())

    assert expected in message
    assert "{window}" not in message


def test_sem_encomenda_no_canal_a_faceta_some(janela):
    janela["preorder"] = False

    assert home._preorder_facet_message(_copy()) == ""


def test_janela_zero_nao_promete_encomenda(janela):
    janela["days"] = 0

    assert home._preorder_facet_message(_copy()) == ""


def test_copy_editada_sem_marcador_sai_como_o_dono_escreveu(janela):
    assert home._preorder_facet_message("Encomende pelo WhatsApp.") == "Encomende pelo WhatsApp."
