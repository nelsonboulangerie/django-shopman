"""O `seed --flush` não pode custar a configuração dos terminais do balcão.

Medido em 22/08/2026: o flush apagava `cashman.Terminal` inteiro e o seed
replantava só `metadata["hardware"]` no `pdv-main` recriado por
`Terminal.default()`. Tudo o mais que a loja tinha declarado sumia —
`station`, `default_fulfillment_type`, `favorite_collection_refs`,
`auto_lock_seconds` — e um segundo balcão (ou um `totem-1`) simplesmente
deixava de existir.

O `station` é o pior dos quatro porque volta para um default INVISÍVEL: o
totem vira estação ATENDIDA e passa a exigir um PIN que não há ninguém para
digitar. Os outros voltam para um default que alguém vê na tela.

O contrato é o mesmo já usado para a curadoria de de-paras (`_relink_bi_aliases`):
o flush fotografa a config por `ref` e o seed re-mescla depois de recriar, com o
`hardware` do seed valendo só onde a loja não declarou nada.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.cashman.models import Terminal

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja_configurada(django_user_model):
    """Um balcão e um totem, ambos com config escrita por gente no Admin."""
    django_user_model.objects.create_user("totem-da-vitrine")
    balcao = Terminal.objects.create(
        ref="pdv-main",
        label="Balcão da rua",
        channel_ref="pdv",
        location_ref="frente",
        metadata={
            "default_fulfillment_type": "delivery",
            "favorite_collection_refs": ["paes", "doces"],
            "auto_lock_seconds": 30,
            # A loja comprou rolo de 58mm. O seed declara 80mm — e não pode
            # sobrescrever o que a loja sabe sobre o próprio papel.
            "hardware": {"printer": {"adapter": "driver", "model": "epson-tm-t20", "roll_width_mm": 58}},
        },
    )
    totem = Terminal.objects.create(
        ref="totem-1",
        label="Totem da vitrine",
        channel_ref="pdv",
        metadata={"station": {"mode": "autonomous", "operator": "totem-da-vitrine"}},
    )
    return balcao, totem


def test_flush_preserva_a_config_dos_terminais(loja_configurada, monkeypatch):
    balcao, totem = loja_configurada
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")

    call_command("seed", "--flush", stdout=StringIO())

    balcao = Terminal.objects.get(ref="pdv-main")
    # Config de tela: nada disto é dado de seed, é decisão da loja.
    assert balcao.metadata["default_fulfillment_type"] == "delivery"
    assert balcao.metadata["favorite_collection_refs"] == ["paes", "doces"]
    assert balcao.metadata["auto_lock_seconds"] == 30
    assert balcao.label == "Balcão da rua"
    assert balcao.location_ref == "frente"

    # Hardware: o que a loja declarou vence; o que ela não declarou o seed preenche.
    hardware = balcao.metadata["hardware"]
    assert hardware["printer"]["roll_width_mm"] == 58, "o seed sobrescreveu o rolo da loja"
    assert hardware["cash_drawer"]["adapter"] == "agent", "a gaveta do seed não preencheu a lacuna"


def test_flush_nao_apaga_terminal_que_o_seed_nao_recria(loja_configurada, monkeypatch):
    """`Terminal.default()` só recria `pdv-main`. O totem tem de sobreviver sozinho."""
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")

    call_command("seed", "--flush", stdout=StringIO())

    totem = Terminal.objects.filter(ref="totem-1").first()
    assert totem is not None, "o totem deixou de existir no reseed"
    assert totem.is_active is True
    assert totem.label == "Totem da vitrine"
    # A espécie da estação é o pior dos quatro: some para ATENDIDA, que é falha
    # fechada e silenciosa — um totem pedindo PIN a ninguém.
    assert totem.metadata["station"] == {"mode": "autonomous", "operator": "totem-da-vitrine"}
