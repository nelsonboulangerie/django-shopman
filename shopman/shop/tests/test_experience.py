"""OC-20: o servidor decide a versão (R4 do WP-RELEASE-01).

Prova a precedência inteira de ``shopman.shop.services.experience.resolve``
(kill switch, prazo, ambiente, aderência, coorte, padrão), a aderência por sessão
e por cliente, a geração que reatribui e o esquema que a ``RuleConfig`` recusa.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import RuleConfig
from shopman.shop.policies.experience import (
    EXPERIENCE_RULE_PATH,
    MAX_LIFETIME_DAYS,
    ExperienceRule,
    ExperienceRuleError,
)
from shopman.shop.rules.engine import load_rule
from shopman.shop.services import experience

pytestmark = pytest.mark.django_db

SURFACE = "storefront"


def _params(**overrides) -> dict:
    params = {
        "ref": "para-quando",
        "surface": SURFACE,
        "variants": ["a", "b"],
        "default": "a",
        "cohorts": {"internal": [], "pilot": []},
        "allocation": {"b": 0},
        "salt": "para-quando-1",
        "owner": "Engenharia",
        "hypothesis": "Perguntar o dia antes da lista reduz a sacola recusada com a loja fechada.",
        "metrics": ["sacola_recusada"],
        "remove_after": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "generation": 1,
    }
    params.update(overrides)
    return params


def _rule(*, enabled: bool = True, ref: str = "experience.para-quando", **overrides) -> RuleConfig:
    return RuleConfig.objects.create(
        ref=ref,
        rule_path=EXPERIENCE_RULE_PATH,
        label="Para quando primeiro",
        enabled=enabled,
        params=_params(**overrides),
    )


def _update(rule: RuleConfig, **overrides) -> None:
    rule.params = {**rule.params, **overrides}
    rule.save()


def _customer(ref: str) -> Customer:
    return Customer.objects.create(ref=ref, first_name=ref)


def _request(customer: Customer | None = None, session: SessionStore | None = None):
    request = RequestFactory().get("/api/v1/storefront/shell/")
    request.session = session if session is not None else SessionStore()
    request.customer = SimpleNamespace(subject_id=customer.uuid) if customer else None
    return request


def _login(customer: Customer, session: SessionStore) -> None:
    """O que o ``user_logged_in`` faz: a sessão ganha a aderência do cliente."""
    experience.remember(_request(customer, session), customer.ref)


def _variant(request) -> str | None:
    found = {a.ref: a for a in experience.resolve(request, SURFACE)}
    return found["para-quando"].variant if "para-quando" in found else None


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


# ── Precedência ──────────────────────────────────────────────────────


def test_without_experiments_resolve_is_empty_and_touches_nothing():
    request = _request(_customer("CLI-A"))
    assert experience.resolve(request, SURFACE) == ()
    assert experience.SESSION_KEY not in request.session


def test_kill_switch_wins_over_cohort():
    """Regra desligada: o experimento some (ausente = padrão), mesmo para a coorte."""
    alvo = _customer("CLI-INT")
    rule = _rule(cohorts={"internal": ["CLI-INT"]})
    assert _variant(_request(alvo)) == "b"

    rule.enabled = False
    rule.save()

    assert _variant(_request(alvo)) is None


def test_kill_switch_beats_the_session_stickiness():
    alvo = _customer("CLI-INT")
    rule = _rule(cohorts={"internal": ["CLI-INT"]})
    session = SessionStore()
    _login(alvo, session)
    assert _variant(_request(alvo, session)) == "b"

    rule.enabled = False
    rule.save()

    assert _variant(_request(alvo, session)) is None


def test_expired_rule_resolves_default_and_alerts_the_operator():
    from shopman.backstage.models import OperatorAlert

    alvo = _customer("CLI-INT")
    rule = _rule(cohorts={"internal": ["CLI-INT"]})
    session = SessionStore()
    _login(alvo, session)
    assert _variant(_request(alvo, session)) == "b"

    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    _update(rule, remove_after=yesterday)

    [assignment] = experience.resolve(_request(alvo, session), SURFACE)
    assert assignment.variant == "a"
    assert assignment.reason == experience.REASON_EXPIRED

    # O GET só lê: o aviso sai do worker.
    alerts = OperatorAlert.objects.filter(type="integration_config_drift")
    assert alerts.count() == 0

    from django.core.management import call_command

    call_command("alert_expired_experiments")
    assert alerts.count() == 1
    assert "para-quando" in alerts.get().message
    assert "—" not in alerts.get().message

    # O ciclo seguinte do worker não empilha aviso.
    call_command("alert_expired_experiments")
    assert alerts.count() == 1


def test_worker_runs_the_expiry_check():
    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

    assert "alert_expired_experiments" in MAINTENANCE_COMMANDS


def test_worker_is_silent_while_experiments_are_on_time():
    _rule()
    assert experience.alert_expired_experiments() == 0


def test_environment_outside_the_list_resolves_default():
    alvo = _customer("CLI-INT")
    _rule(cohorts={"internal": ["CLI-INT"]}, environments=["staging"])

    with override_settings(SHOPMAN_ENVIRONMENT="production"):
        [assignment] = experience.resolve(_request(alvo), SURFACE)
    assert (assignment.variant, assignment.reason) == ("a", experience.REASON_ENVIRONMENT)

    with override_settings(SHOPMAN_ENVIRONMENT="staging"):
        assert _variant(_request(alvo)) == "b"


def test_cohorts_see_the_candidate_and_everyone_else_the_default():
    _customer("CLI-INT")
    _customer("CLI-PIL")
    _customer("CLI-OUT")
    _rule(cohorts={"internal": ["CLI-INT"], "pilot": ["CLI-PIL"]})

    reasons = {}
    for ref in ("CLI-INT", "CLI-PIL", "CLI-OUT"):
        [assignment] = experience.resolve(_request(Customer.objects.get(ref=ref)), SURFACE)
        reasons[ref] = (assignment.variant, assignment.reason)

    assert reasons == {
        "CLI-INT": ("b", experience.REASON_INTERNAL),
        "CLI-PIL": ("b", experience.REASON_PILOT),
        "CLI-OUT": ("a", experience.REASON_DEFAULT),
    }


def test_anonymous_always_sees_the_default_and_gets_no_session():
    """D2: nenhum cliente anônimo nas coortes; a gêmea pública fica sem sessão."""
    _rule(cohorts={"internal": ["CLI-INT"]})
    request = _request(None)

    [assignment] = experience.resolve(request, SURFACE)

    assert (assignment.variant, assignment.reason) == ("a", experience.REASON_DEFAULT)
    assert not request.session.modified
    assert experience.SESSION_KEY not in request.session


def test_internal_cohort_comes_from_the_operator_link_function():
    """A coorte interna é DERIVADA por uma função única: trocá-la basta."""
    operador = _customer("CLI-OPERADOR")
    _rule()  # nenhuma lista à mão

    assert _variant(_request(operador)) == "a"
    with patch.object(experience, "operator_customer_refs", return_value=frozenset({"CLI-OPERADOR"})):
        [assignment] = experience.resolve(_request(operador), SURFACE)
    assert (assignment.variant, assignment.reason) == ("b", experience.REASON_INTERNAL)


def test_operator_link_is_empty_until_the_owner_decides():
    """Hoje não há ligação operador → cliente (ver docstring); a função diz isso."""
    assert experience.operator_customer_refs() == frozenset()


def test_no_request_input_chooses_the_variant():
    """D1: query, cabeçalho e cookie não escolhem versão; só a coorte decide."""
    fora = _customer("CLI-OUT")
    _rule()
    request = RequestFactory().get(
        "/api/v1/storefront/shell/?variant=b&experience=b&para-quando=b",
        HTTP_X_EXPERIENCE="b",
        HTTP_COOKIE="shopman_experience=b; variant=b",
    )
    request.session = SessionStore()
    request.customer = SimpleNamespace(subject_id=fora.uuid)

    assert _variant(request) == "a"


# ── Aderência ────────────────────────────────────────────────────────


def test_reload_never_alternates_even_if_the_cohort_changes_mid_session():
    alvo = _customer("CLI-ALVO")
    rule = _rule()
    session = SessionStore()
    _login(alvo, session)
    assert session[experience.SESSION_KEY] == {"para-quando": {"variant": "a", "generation": 1}}

    seen = [_variant(_request(alvo, session)) for _ in range(5)]
    assert seen == ["a"] * 5

    # Entrou na coorte no meio da sessão: esta sessão continua onde estava.
    _update(rule, cohorts={"internal": ["CLI-ALVO"]})
    [assignment] = experience.resolve(_request(alvo, session), SURFACE)
    assert (assignment.variant, assignment.reason) == ("a", experience.REASON_SESSION)


def test_resolve_only_reads_the_session():
    """A leitura não grava (``test_read_side_never_writes``): a aderência nasce no login."""
    alvo = _customer("CLI-ALVO")
    _rule(cohorts={"pilot": ["CLI-ALVO"]})
    session = SessionStore()

    for _ in range(3):
        assert _variant(_request(alvo, session)) == "b"
    assert not session.modified
    assert experience.SESSION_KEY not in session

    _login(alvo, session)
    session.save()
    session.modified = False
    assert _variant(_request(alvo, session)) == "b"
    assert not session.modified


def test_login_without_experiments_writes_nothing():
    alvo = _customer("CLI-ALVO")
    session = SessionStore()
    _login(alvo, session)
    assert experience.SESSION_KEY not in session


def test_same_customer_gets_the_same_variant_on_two_devices():
    alvo = _customer("CLI-ALVO")
    _rule(cohorts={"pilot": ["CLI-ALVO"]})
    celular, computador = SessionStore(), SessionStore()
    _login(alvo, celular)
    _login(alvo, computador)

    assert _variant(_request(alvo, celular)) == _variant(_request(alvo, computador)) == "b"
    assert celular[experience.SESSION_KEY] == computador[experience.SESSION_KEY]


def test_generation_bump_discards_stickiness_and_reassigns():
    alvo = _customer("CLI-ALVO")
    rule = _rule()
    session = SessionStore()
    _login(alvo, session)
    assert _variant(_request(alvo, session)) == "a"

    _update(rule, cohorts={"internal": ["CLI-ALVO"]})
    assert _variant(_request(alvo, session)) == "a"  # aderente

    _update(rule, generation=2)
    [assignment] = experience.resolve(_request(alvo, session), SURFACE)
    assert (assignment.variant, assignment.reason) == ("b", experience.REASON_INTERNAL)

    _login(alvo, session)
    assert session[experience.SESSION_KEY]["para-quando"] == {"variant": "b", "generation": 2}


def test_staff_login_records_nothing():
    """Sessão de operador (``is_staff``) não é cliente da loja: sai sem consulta."""
    request = _request(None)
    experience.on_user_logged_in(None, request=request, user=SimpleNamespace(is_staff=True))
    assert experience.SESSION_KEY not in request.session


def test_other_surface_experiments_are_not_resolved_here():
    alvo = _customer("CLI-INT")
    _rule(cohorts={"internal": ["CLI-INT"]}, surface="pos")
    assert experience.resolve(_request(alvo), SURFACE) == ()


# ── A regra recusa o que não governa ────────────────────────────────


def test_rule_loads_through_the_engine():
    rule = _rule()
    loaded = load_rule(rule)
    assert isinstance(loaded, ExperienceRule)
    assert loaded.rule_type == "experience"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"remove_after": None}, "remove_after"),
        ({"owner": ""}, "owner"),
        ({"hypothesis": ""}, "hypothesis"),
        ({"remove_after": "amanhã"}, "AAAA-MM-DD"),
        ({"variants": ["a"]}, "exatamente duas"),
        ({"variants": ["a", "a"]}, "exatamente duas"),
        ({"default": "c"}, "'default'"),
        ({"allocation": {"b": 5}}, "D2"),
        ({"allocation": {"c": 0}}, "allocation.c"),
        ({"cohorts": {"todos": []}}, "desconhecida"),
        ({"cohorts": {"pilot": "CLI-1"}}, "cohorts.pilot"),
        ({"generation": 0}, "generation"),
        ({"environments": ["marte"]}, "environments"),
        ({"surface": "Loja Nova"}, "surface"),
        ({"chave_nova": True}, "não conhece"),
    ],
)
def test_validate_params_refuses(overrides, fragment):
    with pytest.raises(ExperienceRuleError, match=fragment):
        ExperienceRule.validate_params(_params(**overrides))


def test_remove_after_is_at_most_90_days_ahead():
    today = timezone.localdate()
    ExperienceRule.validate_params(_params(remove_after=(today + timedelta(days=MAX_LIFETIME_DAYS)).isoformat()))
    with pytest.raises(ExperienceRuleError, match="90 dias"):
        ExperienceRule.validate_params(
            _params(remove_after=(today + timedelta(days=MAX_LIFETIME_DAYS + 1)).isoformat())
        )


def test_ruleconfig_save_refuses_through_clean():
    with pytest.raises(ValidationError):
        _rule(allocation={"b": 10})


def test_expired_rule_can_still_be_switched_off():
    """O kill switch nunca é recusado: data vencida passa no save."""
    rule = _rule()
    _update(rule, remove_after=(timezone.localdate() - timedelta(days=10)).isoformat())
    rule.enabled = False
    rule.save()
    assert RuleConfig.objects.get(pk=rule.pk).enabled is False
