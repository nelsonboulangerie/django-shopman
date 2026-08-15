"""O `seed --flush` reconstrói exatamente as regras canônicas — e nada mais.

Regra órfã é regra que perdeu a classe. Quando o C6 (PR #152) apagou a `D1Rule` e
tirou o `d1_discount` do `RULE_CONFIGS`, a linha continuou no banco do staging,
porque o `_flush` apagava a *history* da `RuleConfig` e nunca a `RuleConfig`. O
resultado era um `WARNING rules.engine: Could not import ...` a cada boot, imune a
qualquer re-seed — só saiu por SQL na mão.

A regra vive de `rule_path` importável ([[feedback_rules_run_as_configured_or_not_at_all]]):
um caminho morto no banco é a única forma de a config divergir do código em
silêncio. Estes testes são a âncora de que `--flush` fecha essa porta.
"""

from __future__ import annotations

from io import StringIO

import pytest

from shopman.shop.models import Channel, RuleConfig

pytestmark = pytest.mark.django_db

ORPHAN_REF = "ghost_discount"
ORPHAN_PATH = "shopman.shop.rules.pricing.GhostRule"


def _seeder():
    from config.management.commands.seed import Command

    command = Command()
    command.stdout = StringIO()
    return command


def _make_orphan() -> RuleConfig:
    """Regra cuja classe não existe — o `d1_discount` de depois do C6.

    Via `bulk_create` porque `RuleConfig.save()` chama `full_clean()` e recusaria o
    caminho morto. É exatamente assim que a órfã nasce na vida real: a linha entrou
    válida e a classe morreu depois, sem ninguém tocar na linha.
    """
    orphan = RuleConfig(
        ref=ORPHAN_REF,
        rule_path=ORPHAN_PATH,
        label="Regra fantasma",
        params={},
        priority=99,
    )
    RuleConfig.objects.bulk_create([orphan])
    return orphan


def test_flush_rebuilds_exactly_the_canonical_rule_configs():
    seeder = _seeder()

    seeder._seed_rule_configs()
    canonical = set(RuleConfig.objects.values_list("ref", flat=True))
    assert canonical, "o seed precisa plantar alguma regra para este teste dizer algo"

    _make_orphan()

    seeder._flush()
    seeder._seed_rule_configs()

    assert set(RuleConfig.objects.values_list("ref", flat=True)) == canonical


def test_flush_leaves_the_audit_table_empty():
    """A history é limpa DEPOIS das linhas, senão o próprio flush a repovoa.

    Cada delete grava um tombstone pelo simple_history. Limpando antes, o `--flush`
    terminava com uma history de deleções — o oposto do que o comentário prometia.
    """
    seeder = _seeder()
    seeder._seed_rule_configs()
    assert RuleConfig.history.model.objects.exists()

    seeder._flush()

    assert RuleConfig.history.model.objects.count() == 0


def test_full_seed_flush_drops_an_orphan_rule_and_its_channel_links(monkeypatch):
    """Integração: o flush completo, com a M2M `channels` povoada.

    A `RuleConfig` é apagada *depois* dos `Channel` (bloco do orderman), então as
    linhas de `shop_ruleconfig_channels` já foram junto — este teste é quem cobra
    que a ordem continue funcionando.
    """
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")

    channel = Channel.objects.create(ref="balcao", name="Balcão")
    orphan = _make_orphan()
    orphan.channels.set([channel])

    from django.core.management import call_command

    call_command("seed", "--flush", stdout=StringIO())

    assert not RuleConfig.objects.filter(ref=ORPHAN_REF).exists()
    assert not RuleConfig.channels.through.objects.filter(ruleconfig_id=orphan.pk).exists()

    # Toda regra sobrevivente importa: é isto que o boot do engine cobra.
    for rule in RuleConfig.objects.all():
        rule.full_clean()
