"""Beta 05/11 (LOJA-07): o FAQ prometia pagamento, encomendas e alérgenos e não tinha.

As respostas novas saem da configuração da loja (formas de pagamento do canal,
janela de encomenda da casa, aviso de produção compartilhada), nunca de texto
inventado; sem a configuração, a pergunta não aparece.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.storefront.presentation import public_information as faq


def _config(*, method, preorder=True):
    return SimpleNamespace(payment=SimpleNamespace(method=method), stock=SimpleNamespace(preorder=preorder))


@pytest.fixture
def channel(monkeypatch):
    from shopman.shop.config import ChannelConfig

    state = {"config": _config(method=["pix", "card"])}
    monkeypatch.setattr(ChannelConfig, "for_channel", classmethod(lambda cls, ref: state["config"]))
    monkeypatch.setattr(faq, "channel_capabilities", lambda ref: SimpleNamespace(fulfillment_types=("pickup", "delivery")))
    from shopman.shop.projections import checkout_context

    monkeypatch.setattr(checkout_context, "preorder_config", lambda: (7, []))
    return state


def _faq(shop) -> dict[str, str]:
    items = faq._operational_faq(channel_ref="web", shop=shop, status={"label": ""}, opening_hours=())
    return {item.ref: item.answer for item in items}


def test_pagamento_encomenda_e_alergenos_saem_da_configuracao(channel):
    shop = SimpleNamespace(full_address="", phone_display="", email="", food_safety_notice="Produzimos com trigo, leite e ovos.")

    answers = _faq(shop)

    assert answers["payment"] == "Você paga com Pix ou cartão."
    assert answers["preorder"] == "Sim. Ao finalizar o pedido, você escolhe o dia, com até 7 dias de antecedência."
    assert answers["allergens"].startswith("Produzimos com trigo, leite e ovos.")
    assert all("—" not in answer for answer in answers.values())


def test_sem_configuracao_a_pergunta_nao_aparece(channel):
    channel["config"] = _config(method="external", preorder=False)
    shop = SimpleNamespace(full_address="", phone_display="", email="", food_safety_notice="")

    answers = _faq(shop)

    assert {"payment", "preorder", "allergens"}.isdisjoint(answers)
