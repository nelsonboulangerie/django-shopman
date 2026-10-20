"""A cascata não pode ENGOLIR chave de config que o runtime lê.

`ChannelConfig.for_channel` faz `from_dict(base).to_dict()`. O `from_dict` mapeia
campo a campo, então **toda chave de topo não declarada como campo é descartada em
silêncio** — o `Channel.config` do Admin guarda o valor, o `to_dict()` entrega sem
ele, e nada falha.

Foi assim que o `order_ref_prefix` nasceu morto: o seed gravava `"NB"` na loja
online, o `CommitService` lia a chave, o teste do orderman passava (ele entrega o
dict direto ao service, pulando a cascata) — e o pedido continuava saindo `WEB-`.

Este arquivo pina o CAMINHO INTEIRO, canal do banco → ref do pedido, que é o único
lugar onde esse defeito aparecia.
"""

from __future__ import annotations

import pytest
from shopman.orderman.tests.commit_support import seal_for

from shopman.shop.config import ChannelConfig

# Chaves de TOPO (fora dos 10 aspectos) que algum consumidor lê da config resolvida.
# Chave nova aqui obriga campo novo na ChannelConfig — é esse o pareamento que o
# `from_dict` quebra quando alguém esquece.
TOP_LEVEL_KEYS_THE_RUNTIME_READS = {
    "handle_label": "Comanda",
    "handle_placeholder": "Ex: 42",
    "short_name": "Site",
    "order_ref_prefix": "NB",
    "lifecycle": {"terminal_statuses": ["completed"]},
}


@pytest.mark.parametrize("key,value", sorted(TOP_LEVEL_KEYS_THE_RUNTIME_READS.items()))
def test_from_dict_round_trip_preserves_top_level_key(key, value):
    resolved = ChannelConfig.from_dict({key: value}).to_dict()
    assert resolved.get(key) == value, (
        f"'{key}' sumiu no round-trip da ChannelConfig — declare o campo e mapeie "
        "em from_dict, senão o valor do Admin nunca chega em quem o lê."
    )


@pytest.mark.django_db
def test_cascade_carries_order_ref_prefix_from_the_channel_row():
    """Canal do banco → config resolvida: o prefixo tem de atravessar."""
    from shopman.shop.models import Channel

    Channel.objects.update_or_create(
        ref="web",
        defaults={"name": "Loja online", "config": {"order_ref_prefix": "NB"}},
    )

    resolved = ChannelConfig.for_channel("web").to_dict()

    assert resolved["order_ref_prefix"] == "NB"


@pytest.mark.django_db
def test_pedido_da_loja_online_nasce_com_a_marca_no_ref():
    """O caminho inteiro: canal configurado no Admin → ref `NB-...` no commit."""
    from shopman.orderman.models import Session
    from shopman.orderman.services import CommitService

    from shopman.shop.models import Channel

    Channel.objects.update_or_create(
        ref="web",
        defaults={"name": "Loja online", "config": {"order_ref_prefix": "NB"}},
    )
    Session.objects.create(
        session_key="NB-PREFIX-E2E",
        channel_ref="web",
        state="open",
        rev=1,
        items=[{"line_id": "L1", "sku": "A", "qty": 1, "unit_price_q": 1000}],
    )

    result = CommitService.commit(
        session_key="NB-PREFIX-E2E",
        channel_ref="web",
        idempotency_key="nb-prefix-e2e",
        seal=seal_for("NB-PREFIX-E2E", "web"),
        channel_config=ChannelConfig.for_channel("web").to_dict(),
    )

    assert result.order_ref.startswith("NB-"), result.order_ref


# ── Chave desconhecida dentro de um aspecto: grita (laudo de soberania, A6-7) ──


def test_unknown_key_inside_an_aspect_is_refused_by_name():
    """`safty_margin: 9` era aceita e o canal seguia com o default, calado."""
    with pytest.raises(ValueError, match=r"stock: chave desconhecida safty_margin"):
        ChannelConfig.from_dict({"stock": {"safty_margin": 9}})


def test_aspect_that_is_not_an_object_is_refused():
    with pytest.raises(ValueError, match=r"payment deve ser um objeto"):
        ChannelConfig.from_dict({"payment": ["pix"]})


def test_shop_rule_policies_are_declared_not_swallowed():
    """As políticas da loja em `rules` têm leitor próprio (`shop_rule_q`): a seção
    as reconhece pelo nome e não as carrega; uma chave fora da lista grita."""
    from shopman.shop.config import SHOP_RULE_POLICY_KEYS

    config = ChannelConfig.from_dict({"rules": dict.fromkeys(SHOP_RULE_POLICY_KEYS, 100)})
    assert config.rules == ChannelConfig.Rules()
    with pytest.raises(ValueError, match=r"rules: chave desconhecida minimun_order_q"):
        ChannelConfig.from_dict({"rules": {"minimun_order_q": 100}})


@pytest.mark.django_db
def test_admin_refuses_channel_config_with_unknown_key():
    from django.core.exceptions import ValidationError

    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref="web", defaults={"name": "Loja online", "config": {"stock": {"safty_margin": 9}}},
    )
    with pytest.raises(ValidationError, match="safty_margin"):
        channel.full_clean()
