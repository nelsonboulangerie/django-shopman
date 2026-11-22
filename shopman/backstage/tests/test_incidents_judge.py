"""O classificador em cascata: barato primeiro, capaz se faltar confiança, gente no fim."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shopman.backstage.incidents import act, judge
from shopman.backstage.incidents.remedies import BY_KEY, Verdict
from shopman.backstage.models import IncidentAction, OperatorAlert
from shopman.shop import ai
from shopman.shop.models import AIConnection, Shop

pytestmark = pytest.mark.django_db

FISCAL = BY_KEY["fiscal_requeue"]
JUDGE = Verdict("judge", "o emissor recusou a nota", evidence="Resposta do emissor: Rejeição 108: Serviço Paralisado Momentaneamente")


class _Alert:
    type = "fiscal_emit_failed"


def _resolved(purpose, protocol="jev"):
    return ai.Resolved(ref=f"{purpose}-conn", protocol=protocol, base_url="", api_key="k", model="m", customer_text_approved=False)


def _reading(choice, confidence, cost=30, purpose="incident"):
    return judge.Reading(choice=choice, confidence=confidence, cost_usd_micros=cost, label=f"ia:{purpose}:x/m")


def test_cheap_tier_decides_when_confident():
    with (
        patch.object(ai, "resolve", side_effect=lambda p: _resolved(p)),
        patch.object(judge, "ask", return_value=_reading("act", 0.93)) as ask,
    ):
        verdict, decided_by, confidence, cost = judge.judge(_Alert(), FISCAL, JUDGE)
    assert verdict.kind == "act"
    assert decided_by.startswith("ia:incident:")
    assert confidence == 0.93 and cost == 30
    assert ask.call_count == 1


def test_low_confidence_escalates_to_the_capable_tier():
    readings = [_reading("act", 0.55), _reading("people", 0.9, cost=400, purpose="incident_review")]
    with (
        patch.object(ai, "resolve", side_effect=lambda p: _resolved(p)),
        patch.object(judge, "ask", side_effect=readings),
    ):
        verdict, decided_by, confidence, cost = judge.judge(_Alert(), FISCAL, JUDGE)
    assert verdict.kind == "no" and "contador" in verdict.reason
    assert decided_by.startswith("ia:incident_review:")
    assert cost == 430


def test_nobody_confident_stays_with_people_and_says_so():
    with (
        patch.object(ai, "resolve", side_effect=lambda p: _resolved(p)),
        patch.object(judge, "ask", side_effect=[_reading("act", 0.6), _reading("act", 0.7)]),
    ):
        verdict, _by, confidence, _cost = judge.judge(_Alert(), FISCAL, JUDGE)
    assert verdict.kind == "no" and "não teve confiança" in verdict.reason
    assert confidence == 0.7


def test_without_any_model_the_rule_verdict_stands():
    with patch.object(ai, "resolve", side_effect=ai.AINotConfigured("sem conexão")):
        verdict, decided_by, confidence, cost = judge.judge(_Alert(), FISCAL, JUDGE)
    assert verdict is JUDGE and decided_by == "regra" and confidence is None and cost == 0


def test_provider_failure_falls_to_the_next_tier():
    with (
        patch.object(ai, "resolve", side_effect=lambda p: _resolved(p)),
        patch.object(judge, "ask", side_effect=[TimeoutError(), _reading("act", 0.95, purpose="incident_review")]),
    ):
        verdict, decided_by, _c, _cost = judge.judge(_Alert(), FISCAL, JUDGE)
    assert verdict.kind == "act" and decided_by.startswith("ia:incident_review:")


def test_parsers_accept_only_the_closed_options():
    options = FISCAL.judge_criteria
    payload = {"answers": {"remedio": {"type": "choice", "choice": "act", "probabilities": {"act": 0.9, "people": 0.1}, "confidence": 0.85}}}
    assert judge.parse_jev_choice(payload, options=options) == ("act", 0.85)
    with pytest.raises(ValueError):
        judge.parse_jev_choice({"answers": {"remedio": {"choice": "rm -rf", "probabilities": {"rm -rf": 1}}}}, options=options)
    assert judge.parse_json_choice('ok {"choice": "people", "confidence": 0.8}') == ("people", 0.8)
    with pytest.raises(ValueError):
        judge.parse_json_choice('{"choice": "restart", "confidence": 1}')


def test_evidence_leaves_without_long_numbers_or_emails():
    text = judge.mask("CPF 123.456.789-09 do cliente ana@example.com recusado; chave 35261112345678000199")
    assert "123" not in text and "ana@" not in text and "3526" not in text


def test_act_step_uses_the_model_and_records_who_decided():
    from datetime import timedelta  # noqa: F401

    from django.utils import timezone  # noqa: F401
    from shopman.orderman.models import Directive, Order

    from shopman.shop.directives import FISCAL_EMIT_NFCE

    Shop.objects.create(name="Loja")
    order = Order.objects.create(ref="NFCE-IA", status="completed", total_q=1000,
        data={"fiscal": {"issue_document": True}, "payment": {"method": "cash", "amount_q": 1000}})
    fiscal = Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", attempts=1, error_code="terminal",
        payload={"order_ref": order.ref, "emitter_answer": "Rejeição 108: Serviço Paralisado Momentaneamente"})
    alert = OperatorAlert.objects.create(type="fiscal_emit_failed", severity="critical", message="x", order_ref=order.ref)

    def fake_judge(alert, remedy, verdict):
        return Verdict("act", "o emissor recusou por indisponibilidade passageira (leitura do modelo)"), "ia:incident:jev/jev-1", 0.92, 30

    with patch.object(act, "_judge", return_value=fake_judge):
        act.step(alert.pk, judge=act._judge())

    fiscal.refresh_from_db()
    assert fiscal.status == "queued"
    action = IncidentAction.objects.get()
    assert (action.outcome, action.decided_by, action.confidence) == ("ran", "ia:incident:jev/jev-1", 0.92)
    assert action.cost_usd_micros == 30


def test_decision_role_is_jev_only_and_reading_role_is_llm_only():
    """Jev e LLM não se trocam (dono, 21/11): cada papel só aceita o seu formato."""
    Shop.objects.create(name="Loja", ai_routes={"default": {"connection": "ds-teste"}})
    AIConnection.objects.update(is_active=False)
    for ref, name, protocol, model in (("jev-teste", "Jev", "jev", "jev-1"), ("ds-teste", "DeepSeek", "anthropic", "deepseek-flash")):
        connection = AIConnection(ref=ref, name=name, protocol=protocol, model=model)
        connection.set_api_key("chave-sintetica")
        connection.save()
    assert ai.resolve("incident").ref == "jev-teste"
    assert ai.resolve("incident_review").ref == "ds-teste"

    shop = Shop.objects.get()
    shop.ai_routes = {"incident": {"connection": "ds-teste"}, "incident_review": {"connection": "jev-teste"}}
    shop.save()
    with pytest.raises(ai.AINotConfigured):
        ai.resolve("incident")
    with pytest.raises(ai.AINotConfigured):
        ai.resolve("incident_review")


def test_without_jev_the_llm_alone_decides():
    """Só LLM é arranjo válido: sem Jev, a leitura decide sozinha."""
    def resolve(purpose):
        if purpose == "incident":
            raise ai.AINotConfigured("sem Jev")
        return _resolved(purpose, protocol="anthropic")

    with (
        patch.object(ai, "resolve", side_effect=resolve),
        patch.object(judge, "ask", return_value=_reading("act", 0.9, purpose="incident_review")) as ask,
    ):
        verdict, decided_by, _c, _cost = judge.judge(_Alert(), FISCAL, JUDGE)
    assert verdict.kind == "act" and decided_by.startswith("ia:incident_review:")
    assert ask.call_count == 1


def test_confident_jev_never_wakes_the_llm():
    with (
        patch.object(ai, "resolve", side_effect=lambda p: _resolved(p)) as resolve,
        patch.object(judge, "ask", return_value=_reading("people", 0.97)),
    ):
        judge.judge(_Alert(), FISCAL, JUDGE)
    assert [call.args[0] for call in resolve.call_args_list] == ["incident"]
