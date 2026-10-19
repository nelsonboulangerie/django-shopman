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

#: Janela e percentual são obrigatórios na regra (A7-2): o teste os declara.
HAPPY_HOUR_PARAMS = {"discount_percent": 25, "start": "17:30", "end": "18:00"}


def _make_rule_config(**kwargs) -> RuleConfig:
    defaults = {
        "ref": "test-rule",
        "rule_path": "shopman.shop.rules.pricing.HappyHourRule",
        "label": "Test Rule",
        "enabled": True,
        "params": dict(HAPPY_HOUR_PARAMS),
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
        rc.rule_path = "shopman.shop.rules.pricing.HappyHourRule"
        rc.params = dict(HAPPY_HOUR_PARAMS)
        rule = load_rule(rc)
        from shopman.shop.rules.pricing import HappyHourRule
        assert isinstance(rule, HappyHourRule)


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

    def test_acoes_em_lote_tambem_exigem_manage_rules(self):
        """O portão tem de valer na PORTA, não só no formulário.

        ⚠️ Os `has_*_permission` acima gateiam a tela de edição. As ações em
        lote passam por FORA deles: `@admin.action` sem `permissions=` não é
        filtrada pelo Django (`contrib/admin/options.py`), aparece no seletor, e
        `get_actions` é o único portão de `response_action`.

        Consequência viva antes deste teste: a Gerente tem `view_ruleconfig` por
        `_ver("shop")` (`setup_groups.py`) e NÃO tem `manage_rules` — o portão do
        WP-GAP-06, que existe porque regra de preço EXECUTA expressão. Ela
        selecionava tudo e ligava/desligava regra de preço pelo seletor.

        Este teste bate na porta (`get_actions`), e não nos métodos: era
        justamente a diferença entre os dois que deixava o buraco passar verde.
        """
        from django.contrib.admin.sites import AdminSite

        from shopman.shop.admin.rules import RuleConfigAdmin

        admin_instance = RuleConfigAdmin(RuleConfig, AdminSite())
        rf = RequestFactory()

        request = rf.get("/admin/shop/ruleconfig/")
        request.user = self.staff_user
        acoes_sem_perm = admin_instance.get_actions(request)
        assert "enable_rules" not in acoes_sem_perm
        assert "disable_rules" not in acoes_sem_perm

        request.user = self.privileged_user
        acoes_com_perm = admin_instance.get_actions(request)
        assert "enable_rules" in acoes_com_perm
        assert "disable_rules" in acoes_com_perm

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
            rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="History Test",
            params=dict(HAPPY_HOUR_PARAMS),
            priority=99,
        )
        assert rc.history.count() == 1
        assert rc.history.first().history_type == "+"

    def test_update_creates_second_historical_record(self):
        rc = RuleConfig.objects.create(
            ref="history-update",
            rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="Before",
            params=dict(HAPPY_HOUR_PARAMS),
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
            rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="To Delete",
            params=dict(HAPPY_HOUR_PARAMS),
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



