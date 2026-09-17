"""O limiar de cerimônia do Marketing: proporção da base, teto de gasto e piso.

Ver ADR-032. A regra é uma frase: **o que chegar primeiro** entre 2% da base de clientes
e o teto de gasto do disparo, nunca abaixo do piso.
"""

from __future__ import annotations

import logging

import pytest
from django.core.cache import cache
from shopman.guestman.models import Customer

from shopman.shop.marketing_policy import (
    DEFAULT_CEREMONY_AUDIENCE_PERCENT,
    DEFAULT_CEREMONY_RECIPIENT_FLOOR,
    MarketingPolicy,
)
from shopman.shop.services.marketing_ceremony import (
    CUSTOMER_BASE_CACHE_KEY,
    ceremony_threshold,
    customer_base_size,
    invalidate_customer_base_size,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    invalidate_customer_base_size()
    yield
    invalidate_customer_base_size()


def _customer(ref: str, *, active: bool = True) -> Customer:
    return Customer.objects.create(
        ref=ref,
        first_name="Cliente",
        phone=f"+5543999{ref[-6:].rjust(6, '0')}",
        is_active=active,
    )


def test_threshold_is_a_share_of_the_base_not_a_number_carved_in_code():
    """Um limiar absoluto só está certo para UM tamanho de base.

    Com 2.500 clientes, 2% dá as mesmas 50 pessoas que a política anterior cravava no
    código — e é aí que a semelhança acaba: com 20.000, o mesmo 2% dá 400.
    """
    policy = MarketingPolicy()

    small = policy.ceremony_threshold(2_500)
    big = policy.ceremony_threshold(20_000)

    assert DEFAULT_CEREMONY_AUDIENCE_PERCENT == 2
    assert (small.typed, small.dual_control, small.binding) == (50, 500, "percent")
    assert (big.typed, big.dual_control, big.binding) == (400, 4_000, "percent")


def test_spend_ceiling_wins_when_it_arrives_first():
    """Duas contas, vale a menor. Numa base enorme, quem chega primeiro é o dinheiro."""
    policy = MarketingPolicy()

    threshold = policy.ceremony_threshold(1_000_000)

    # R$ 50,00 de teto ÷ R$ 0,07 por mensagem = 714 mensagens; 2% de um milhão = 20.000.
    assert threshold.from_percent == 20_000
    assert threshold.from_spend == 714
    assert (threshold.typed, threshold.binding) == (714, "spend")
    assert policy.estimated_cost_q(714) <= policy.ceremony_spend_limit_q


def test_an_empty_base_falls_to_the_floor_and_asks_for_more_ceremony_not_less():
    """Base vazia não pode abrir a porta — e não há divisão pela base em lugar nenhum."""
    policy = MarketingPolicy()

    threshold = policy.ceremony_threshold(0)

    assert threshold.typed == DEFAULT_CEREMONY_RECIPIENT_FLOOR
    assert threshold.binding == "floor"
    assert threshold.dual_control == DEFAULT_CEREMONY_RECIPIENT_FLOOR * 10
    # E uma base negativa (só chegaria por corrupção de dado) cai no mesmo lugar.
    assert policy.ceremony_threshold(-1).typed == DEFAULT_CEREMONY_RECIPIENT_FLOOR


def test_a_free_message_price_leaves_only_the_share_and_the_floor_deciding():
    """Custo zero não é "sem limite": some a conta do gasto, sobram fatia e piso."""
    policy = MarketingPolicy(direct_message_cost_q=0)

    threshold = policy.ceremony_threshold(2_500)

    assert threshold.from_spend is None
    assert (threshold.typed, threshold.binding) == (50, "percent")


def test_the_base_is_the_active_roll_and_forgetting_someone_removes_them():
    """Base de clientes = cadastro ATIVO. Anonimizar desliga ``is_active``."""
    _customer("CLI-BASE-1")
    _customer("CLI-BASE-2")
    esquecido = _customer("CLI-BASE-3")

    assert customer_base_size(refresh=True) == 3

    esquecido.is_active = False
    esquecido.save(update_fields=["is_active"])

    assert customer_base_size() == 2


def test_writing_a_customer_invalidates_the_cached_count_at_once():
    """O cache dura 60 s, mas quem mexe no cadastro o mata na hora.

    Cache de regra que mente já custou caro nesta casa; aqui a mentira mudaria se a tela
    pede senha ou não.
    """
    _customer("CLI-CACHE-1")
    assert customer_base_size() == 1
    assert cache.get(CUSTOMER_BASE_CACHE_KEY) == 1

    _customer("CLI-CACHE-2")

    assert cache.get(CUSTOMER_BASE_CACHE_KEY) is None
    assert customer_base_size() == 2


def test_the_shop_policy_is_read_from_the_admin_and_not_from_the_code():
    """Tudo ajustável no Admin: fatia, gasto, custo, piso e o múltiplo do duplo."""
    policy = MarketingPolicy.from_defaults({
        "marketing": {
            "ceremony_audience_percent": "5",
            "ceremony_spend_limit_q": 100_000,
            "direct_message_cost_q": 12,
            "ceremony_recipient_floor": 25,
            "ceremony_dual_control_multiple": 4,
        },
    })

    threshold = policy.ceremony_threshold(1_000)

    assert policy.ceremony_audience_percent == 5
    assert (threshold.from_percent, threshold.from_spend) == (50, 8_333)
    assert (threshold.typed, threshold.dual_control, threshold.binding) == (50, 200, "percent")


def test_a_hand_edited_junk_policy_falls_back_to_the_default_and_warns(caplog):
    """JSON editado à mão não vira política silenciosa: cai no padrão e grita."""
    # O logger do módulo não propaga para a raiz nesta configuração, então o handler do
    # caplog precisa ser pendurado nele — sem isso o teste "passaria" sem ouvir nada.
    policy_logger = logging.getLogger("shopman.shop.marketing_policy")
    policy_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level("WARNING", logger="shopman.shop.marketing_policy"):
            policy = MarketingPolicy.from_defaults({
                "marketing": {
                    "ceremony_audience_percent": "muito",
                    "ceremony_recipient_floor": 0,
                    "direct_message_cost_q": "de graça",
                },
            })
    finally:
        policy_logger.removeHandler(caplog.handler)

    assert policy.ceremony_audience_percent == DEFAULT_CEREMONY_AUDIENCE_PERCENT
    assert policy.ceremony_recipient_floor == DEFAULT_CEREMONY_RECIPIENT_FLOOR
    assert policy.direct_message_cost_q == 7
    assert "ceremony_audience_percent_unparseable" in caplog.text
    assert "ceremony_recipient_floor_invalid" in caplog.text
    assert "direct_message_cost_q_invalid" in caplog.text


def test_the_resolved_threshold_uses_the_live_base():
    _customer("CLI-LIVE-1")

    threshold = ceremony_threshold()

    assert threshold.base_size == 1
    # Uma pessoa de base: 2% dá zero, e o piso é quem responde.
    assert threshold.typed == DEFAULT_CEREMONY_RECIPIENT_FLOOR
