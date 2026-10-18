"""A Hora da Xepa vale só no balcão (decisão do dono, 14/10/2026, L3=1).

A Xepa é a liquidação de fim de dia de quem está na loja. Antes ela valia no
balcão e no WhatsApp (o seed listava todo canal menos o site) e a regra sem canal
nenhum valia em TODOS, site e iFood incluídos. Agora:

- a regra de horário só vale onde estiver listada: sem canal, não vale em lugar
  nenhum (``HappyHourRule.channels_required``);
- o seed lista só o PDV, e a migração ``0093`` faz o mesmo no banco vivo;
- a loja online não anuncia Xepa (nem faixa no cardápio, nem selo de produto).
"""

from __future__ import annotations

import dataclasses
import importlib
from datetime import timedelta
from io import StringIO

import pytest
from django.apps import apps
from django.core.cache import cache
from django.utils import timezone

from shopman.shop.models import Channel, RuleConfig

pytestmark = pytest.mark.django_db


def _wide_window() -> dict:
    now = timezone.localtime()
    return {
        "discount_percent": 25,
        "start": (now - timedelta(hours=1)).strftime("%H:%M"),
        "end": (now + timedelta(hours=1)).strftime("%H:%M"),
    }


def _xepa(*channels: Channel) -> RuleConfig:
    rule = RuleConfig.objects.create(
        ref="happy_hour",
        rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Hora da Xepa",
        params=_wide_window(),
        enabled=True,
    )
    rule.channels.set(channels)
    cache.clear()
    return rule


@pytest.fixture
def canais():
    refs = ("pdv", "web", "whatsapp", "ifood")
    return {ref: Channel.objects.create(ref=ref, name=ref, is_active=True) for ref in refs}


def test_xepa_sem_canal_listado_nao_vale_em_lugar_nenhum(canais):
    from shopman.shop.rules.engine import get_channel_rule_params

    _xepa()

    for ref in canais:
        assert get_channel_rule_params("happy_hour", ref) is None, ref


def test_xepa_listada_no_pdv_vale_so_no_pdv(canais):
    from shopman.shop.rules.engine import get_channel_rule_params

    _xepa(canais["pdv"])

    assert get_channel_rule_params("happy_hour", "pdv") is not None
    for ref in ("web", "whatsapp", "ifood"):
        assert get_channel_rule_params("happy_hour", ref) is None, ref


def test_outras_regras_sem_canal_continuam_valendo_em_todos(canais):
    """O "vazio = todos" segue sendo o padrão; só a Xepa pede canal listado."""
    from shopman.shop.rules.engine import get_channel_rule_params

    RuleConfig.objects.create(
        ref="business_hours",
        rule_path="shopman.shop.rules.validation.BusinessHoursRule",
        label="Horário de Funcionamento",
        params={},
        enabled=True,
    )
    cache.clear()

    assert get_channel_rule_params("business_hours", "whatsapp") is not None


def test_seed_lista_a_xepa_so_no_pdv():
    from config.management.commands.seed import NELSON_INSTANCE_DESCRIPTOR, Command

    command = Command()
    command.stdout = StringIO()
    command._materialize_instance(NELSON_INSTANCE_DESCRIPTOR)

    rule = RuleConfig.objects.get(ref="happy_hour")
    assert sorted(rule.channels.values_list("ref", flat=True)) == ["pdv"]


def test_migracao_tira_a_xepa_do_whatsapp_e_do_ifood(canais):
    rule = _xepa(canais["pdv"], canais["whatsapp"], canais["ifood"])
    outra = RuleConfig.objects.create(
        ref="business_hours",
        rule_path="shopman.shop.rules.validation.BusinessHoursRule",
        label="Horário de Funcionamento",
        params={},
    )
    outra.channels.set([canais["whatsapp"]])

    migration = importlib.import_module("shopman.shop.migrations.0093_xepa_so_no_balcao")
    migration.forwards(apps, None)

    assert sorted(rule.channels.values_list("ref", flat=True)) == ["pdv"]
    assert sorted(outra.channels.values_list("ref", flat=True)) == ["whatsapp"]


def test_migracao_poe_no_pdv_a_xepa_que_valia_em_todos(canais):
    rule = _xepa()

    migration = importlib.import_module("shopman.shop.migrations.0093_xepa_so_no_balcao")
    migration.forwards(apps, None)

    assert sorted(rule.channels.values_list("ref", flat=True)) == ["pdv"]


def test_migracao_sem_regra_de_xepa_nao_faz_nada(canais):
    migration = importlib.import_module("shopman.shop.migrations.0093_xepa_so_no_balcao")
    migration.forwards(apps, None)

    assert not RuleConfig.objects.filter(ref="happy_hour").exists()


def test_loja_online_nao_anuncia_xepa():
    from shopman.storefront.presentation.catalog import CatalogProjection

    campos = {field.name for field in dataclasses.fields(CatalogProjection)}
    assert "happy_hour" not in campos


def test_selo_de_produto_da_loja_nao_anuncia_xepa():
    from shopman.storefront.presentation.fomo import badges_for_product

    badges = badges_for_product(
        "PAO", availability={"has_happy_hour": True, "happy_hour_end": "18:00"},
        now=timezone.now(),
    )
    assert all(badge.type != "happy_hour" for badge in badges)
