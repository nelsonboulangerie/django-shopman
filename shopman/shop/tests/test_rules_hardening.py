"""
Tests for WP-GAP-06 — RuleConfig RCE hardening.

Covers:
  1. Whitelist: non-whitelisted rule_path rejected.
  2. Import check: whitelisted but non-existent class rejected.
  3. Subclass check: class that doesn't inherit BaseRule rejected.
  4. Happy path: legitimate rule class accepted.
  5. Defense-in-depth: load_rule() rejects bypassed whitelist.
  6. Permission: staff without manage_rules perm gets 403 in admin.
  7. History: save creates a HistoricalRuleConfig record.
"""

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from shopman.shop.models import RuleConfig
from shopman.shop.rules.engine import load_rule


def _make_rule_config(**kwargs) -> RuleConfig:
    defaults = {
        "ref": "test-rule",
        "rule_path": "shopman.shop.rules.pricing.EmployeeRule",
        "label": "Test Rule",
        "enabled": True,
        "params": {},
        "priority": 0,
    }
    defaults.update(kwargs)
    return RuleConfig(**defaults)


class TestRuleConfigWhitelist(TestCase):
    """RuleConfig.clean() whitelist validation."""

    def test_rejects_non_whitelisted_path(self):
        rc = _make_rule_config(rule_path="os.system")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        errors = exc_info.value.message_dict
        assert "rule_path" in errors
        assert "não é permitido" in errors["rule_path"][0]

    def test_rejects_subprocess_path(self):
        rc = _make_rule_config(rule_path="subprocess.Popen")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        assert "rule_path" in exc_info.value.message_dict

    def test_rejects_whitelisted_module_nonexistent_class(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.pricing.NotARealClass")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        errors = exc_info.value.message_dict
        assert "rule_path" in errors
        assert "importar" in errors["rule_path"][0]

    def test_rejects_class_not_subclass_of_base_rule(self):
        """A class that is whitelisted in path but doesn't inherit BaseRule is rejected."""
        rc = _make_rule_config(rule_path="shopman.shop.rules.engine.CACHE_KEY")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        assert "rule_path" in exc_info.value.message_dict

    def test_accepts_legitimate_pricing_rule(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.pricing.EmployeeRule")
        rc.clean()  # must not raise

    def test_accepts_legitimate_validation_rule(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.validation.BusinessHoursRule")
        rc.clean()  # must not raise

    def test_accepts_legitimate_happy_hour_rule(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.pricing.HappyHourRule")
        rc.clean()  # must not raise


class TestLoadRuleDefenseInDepth(TestCase):
    """load_rule() rejects non-whitelisted paths even if clean() was bypassed."""

    def test_load_rule_rejects_bypassed_whitelist(self):
        rc = RuleConfig.__new__(RuleConfig)
        rc.rule_path = "os.system"
        rc.params = {}
        with pytest.raises(ValueError, match="whitelist"):
            load_rule(rc)

    def test_load_rule_accepts_whitelisted_path(self):
        rc = RuleConfig.__new__(RuleConfig)
        rc.rule_path = "shopman.shop.rules.pricing.EmployeeRule"
        rc.params = {}
        rule = load_rule(rc)
        from shopman.shop.rules.pricing import EmployeeRule
        assert isinstance(rule, EmployeeRule)


class TestRuleConfigAdminPermission(TestCase):
    """Staff without manage_rules perm cannot edit RuleConfigs."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff",
            password="pw",
            is_staff=True,
        )
        self.privileged_user = User.objects.create_user(
            username="rules_mgr",
            password="pw",
            is_staff=True,
        )
        perm = Permission.objects.get(codename="manage_rules")
        self.privileged_user.user_permissions.add(perm)

    def test_staff_without_perm_cannot_change(self):
        from django.contrib.admin.sites import AdminSite

        from shopman.shop.admin.rules import RuleConfigAdmin

        admin_instance = RuleConfigAdmin(RuleConfig, AdminSite())
        rf = RequestFactory()
        request = rf.get("/admin/shop/ruleconfig/")
        request.user = self.staff_user
        assert not admin_instance.has_change_permission(request)
        assert not admin_instance.has_add_permission(request)
        assert not admin_instance.has_delete_permission(request)

    def test_staff_with_perm_can_change(self):
        from django.contrib.admin.sites import AdminSite

        from shopman.shop.admin.rules import RuleConfigAdmin

        admin_instance = RuleConfigAdmin(RuleConfig, AdminSite())
        rf = RequestFactory()
        request = rf.get("/admin/shop/ruleconfig/")
        request.user = self.privileged_user
        assert admin_instance.has_change_permission(request)
        assert admin_instance.has_add_permission(request)
        assert admin_instance.has_delete_permission(request)


class TestRuleConfigHistory(TestCase):
    """simple-history tracks changes to RuleConfig."""

    def test_save_creates_historical_record(self):
        rc = RuleConfig.objects.create(
            ref="history-test",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="History Test",
            priority=99,
        )
        assert rc.history.count() == 1
        assert rc.history.first().history_type == "+"

    def test_update_creates_second_historical_record(self):
        rc = RuleConfig.objects.create(
            ref="history-update",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="Before",
            priority=99,
        )
        rc.label = "After"
        rc.save()
        assert rc.history.count() == 2
        latest = rc.history.first()
        assert latest.label == "After"
        assert latest.history_type == "~"

    def test_delete_creates_delete_historical_record(self):
        rc = RuleConfig.objects.create(
            ref="history-delete",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="To Delete",
            priority=99,
        )
        pk = rc.pk
        rc.delete()
        from shopman.shop.models.rules import RuleConfig as RC
        deleted_history = RC.history.filter(id=pk, history_type="-")
        assert deleted_history.exists()


class TestRulesManagersGroup(TestCase):
    """``setup_groups`` cria 'Rules Managers' com manage_rules e sem membros.

    O grupo nascia numa data migration e passou a nascer no comando — que é o dono
    único dos grupos e é chamado pelo release job. Estes testes exercem o comando,
    não o histórico de migrações: é o comando que precisa continuar certo.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("setup_groups", verbosity=0)

    def test_rules_managers_group_exists(self):
        from django.contrib.auth.models import Group
        assert Group.objects.filter(name="Rules Managers").exists()

    def test_rules_managers_group_has_manage_rules_perm(self):
        from django.contrib.auth.models import Group
        group = Group.objects.get(name="Rules Managers")
        assert group.permissions.filter(codename="manage_rules").exists()

    def test_rules_managers_group_has_no_members_by_default(self):
        from django.contrib.auth.models import Group
        group = Group.objects.get(name="Rules Managers")
        assert group.user_set.count() == 0


class TestEmployeeRuleParamRename:
    """⚠️ Um parâmetro obsoleto na `RuleConfig` DESLIGA a regra em silêncio.

    O engine instancia com `cls(**rule_config.params)` (`engine.py:143`) e o `_safe_load`
    engole o `TypeError` como WARNING (`engine.py:227`). Quando `group` virou `price_tier`,
    o desconto de funcionário parou de carregar num banco existente — sem erro na tela, sem
    ninguém sabendo. A migração `shop.0010` renomeia a chave nos dados.
    """

    @pytest.mark.django_db
    def test_the_rule_still_loads_with_the_current_param(self):
        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.engine import load_rule

        config = RuleConfig.objects.create(
            ref="employee_discount_atual",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="Desconto Funcionário",
            params={"discount_percent": 20, "price_tier": "staff"},
        )

        rule = load_rule(config)
        assert rule.price_tier == "staff"
        assert rule.discount_percent == 20

    @pytest.mark.django_db
    def test_the_obsolete_param_kills_the_rule_loudly(self):
        """Dado velho DESLIGA a regra — decisão REAFIRMADA pelo Pablo (2026-08-13).

        A faxina chegou a inverter este contrato (chave órfã ignorada, regra
        viva com defaults); o dono reafirmou o estrito: a regra roda exatamente
        como configurada ou não roda — nada de fallback inventado, nada de
        alias (`group` NÃO vira `price_tier`; a tradução é a migração 0010,
        testada abaixo).

        O que a revisão MANTEVE do aprendizado do incidente `da69c714` é o
        barulho: a morte não pode mais ser um WARNING perdido no log. Quem
        grita é o check `rules.load` do release-readiness (vermelho no
        CI/staging) e a coluna "carrega?" no Admin de RuleConfig — visível
        onde o dado velho mora.
        """
        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.engine import _safe_load, load_rule

        config = RuleConfig.objects.create(
            ref="employee_discount_velho",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="Desconto Funcionário",
            params={"discount_percent": 20, "group": "staff"},
        )

        # O motor: não carrega, e o erro NOMEIA a chave e o conserto.
        with pytest.raises(ValueError, match="group"):
            load_rule(config)
        assert _safe_load(config) is None

        # O barulho: o readiness enxerga a regra quebrada.
        import importlib.util
        import pathlib
        import sys

        spec = importlib.util.spec_from_file_location(
            "check_release_readiness",
            pathlib.Path(__file__).resolve().parents[3] / "scripts" / "check_release_readiness.py",
        )
        readiness = importlib.util.module_from_spec(spec)
        # @dataclass resolve annotations via sys.modules[__module__] — registrar
        # antes do exec, senão NoneType.__dict__ dentro do dataclasses.py.
        sys.modules[spec.name] = readiness
        try:
            spec.loader.exec_module(readiness)
        finally:
            sys.modules.pop(spec.name, None)
        check = readiness._rules_load_check()
        assert check.status == "failed"
        assert any(b["ref"] == "employee_discount_velho" for b in check.details["broken"])

    @pytest.mark.django_db
    def test_the_migration_renames_the_key_in_stored_params(self):
        """E a migração conserta o dado velho, nos dois sentidos."""
        import importlib

        from django.apps import apps as real_apps

        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.engine import _safe_load

        migration = importlib.import_module(
            "shopman.shop.migrations.0010_employee_rule_price_tier_param"
        )

        config = RuleConfig.objects.create(
            ref="employee_discount_migrado",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="Desconto Funcionário",
            params={"discount_percent": 15, "group": "staff"},
        )

        migration.forwards(real_apps, None)
        config.refresh_from_db()
        assert config.params == {"discount_percent": 15, "price_tier": "staff"}
        assert _safe_load(config) is not None  # a regra volta a carregar

        # O reverso existe porque migração de dados que não volta transforma rollback
        # em perda.
        migration.backwards(real_apps, None)
        config.refresh_from_db()
        assert config.params == {"discount_percent": 15, "group": "staff"}
