"""A versão da API do Stripe é fixa no adapter, não herdada do SDK (#1828).

Subir o pacote ``stripe`` não pode trocar, por tabela, a API de pagamento: cada major
do SDK fixa outra versão em toda chamada, e a versão muda a forma das respostas.
"""

from __future__ import annotations

import stripe

from shopman.shop.adapters import payment_stripe


def test_o_adapter_fala_a_versao_fixa_e_nao_a_do_sdk(monkeypatch):
    monkeypatch.setattr(payment_stripe, "_get_config", lambda: {"secret_key": "sk_test_fixo"})
    monkeypatch.setattr(stripe, "api_version", "versao-do-sdk")
    client = payment_stripe._get_stripe()
    assert client.api_version == payment_stripe.STRIPE_API_VERSION == "2026-08-26.dahlia"
