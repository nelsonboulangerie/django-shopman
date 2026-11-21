"""B.I. — a seção IA (DEV-2026-067): gasto por papel e modelo em reais pela PTAX do dia,
a pauta da conferência, o que falta à casa e a alternativa segura. Só do Dono."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import DayClosing, OperatorAlert
from shopman.backstage.projections import bi_ai
from shopman.shop import concierge_reading
from shopman.shop.models import AiInvocation, Conversation, ConversationBinding, ConversationMessage, UsdBrlQuote

pytestmark = pytest.mark.django_db

FETCH = "shopman.shop.services.usd_brl.fetch_ptax"


def _perm(model, codename: str) -> Permission:
    return Permission.objects.get(content_type=ContentType.objects.get_for_model(model), codename=codename)


def _at(day, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=timezone.get_current_timezone())


def _call(day, *, purpose="concierge", model="deepseek-flash", cost=1_000_000, outcome="ok"):
    call = AiInvocation.objects.create(purpose=purpose, model=model, outcome=outcome, cost_usd_micros=cost)
    AiInvocation.objects.filter(pk=call.pk).update(created_at=_at(day))
    return call


def test_ai_panel_is_owner_only(client):
    """É gasto da casa e fala de cliente: ``view_bi`` sozinho não abre, como o Caixa."""
    from shopman.cashman.models import Shift

    user = User.objects.create_user("bi-ia", password="pw", is_staff=True)
    user.user_permissions.add(_perm(DayClosing, "view_bi"))
    client.force_login(user)
    assert client.get(reverse("api-backstage-bi-ai")).status_code == 403

    user.user_permissions.add(_perm(Shift, "audit_shift"))
    client.force_login(user)
    with mock.patch(FETCH, return_value={}):
        response = client.get(reverse("api-backstage-bi-ai"))
    assert response.status_code == 200
    assert response.json()["bi"]["conference_mode"] == "shadow"


def test_spend_by_role_and_model_in_reais_with_the_quote_used():
    today = timezone.localdate()
    day1, day2, day3 = today - timedelta(days=3), today - timedelta(days=2), today - timedelta(days=1)
    _call(day1, cost=1_000_000)
    _call(day2, cost=2_000_000)  # sem PTAX no dia (feriado): vale a do dia útil anterior
    _call(day3, purpose="decision", model="jev-latest", cost=500_000)
    _call(day3, purpose="decision", model="jev-latest", cost=0, outcome="budget_denied")

    rates = {day1: Decimal("5.0000"), day3: Decimal("6.0000")}
    with mock.patch(FETCH, return_value=rates) as fetch:
        report = bi_ai.build_bi_ai(date_from=day1, date_to=day3)
    assert fetch.call_count == 1  # uma chamada para o período

    rows = {(r.purpose, r.model): r for r in report.rows}
    concierge = rows[("concierge", "deepseek-flash")]
    assert concierge.purpose_label == "Concierge: atendimento no WhatsApp"
    assert (concierge.calls, concierge.cost_usd_micros, concierge.cost_brl_micros) == (2, 3_000_000, 15_000_000)
    jev = rows[("decision", "jev-latest")]
    assert (jev.calls, jev.denied, jev.cost_usd_micros, jev.cost_brl_micros) == (2, 1, 500_000, 3_000_000)

    days = {d.date: d for d in report.days}
    assert days[day2.isoformat()].rate == "5.0000"
    assert days[day2.isoformat()].quoted_on == day1.isoformat()
    assert report.cost_usd_micros == 3_500_000
    assert report.cost_brl_micros == 18_000_000
    assert not report.provisional_quotes

    # A cotação usada fica gravada: dia passado não muda de valor depois.
    assert UsdBrlQuote.objects.get(date=day2).quoted_on == day1
    with mock.patch(FETCH, side_effect=AssertionError("não deveria buscar de novo")):
        again = bi_ai.build_bi_ai(date_from=day1, date_to=day3)
    assert again.cost_brl_micros == 18_000_000


def test_api_down_uses_the_last_known_quote_marked_provisional():
    today = timezone.localdate()
    UsdBrlQuote.objects.create(date=today - timedelta(days=10), quoted_on=today - timedelta(days=10), sell_rate=Decimal("5.5000"))
    _call(today - timedelta(days=1), cost=1_000_000)
    with mock.patch(FETCH, side_effect=OSError("fora do ar")):
        report = bi_ai.build_bi_ai(date_from=today - timedelta(days=1), date_to=today)
    assert report.cost_brl_micros == 5_500_000
    assert report.provisional_quotes
    assert not UsdBrlQuote.objects.filter(date=today - timedelta(days=1)).exists()


def test_without_any_quote_the_reais_stay_empty_not_invented():
    today = timezone.localdate()
    _call(today - timedelta(days=1), cost=1_000_000)
    with mock.patch(FETCH, side_effect=OSError("fora do ar")):
        report = bi_ai.build_bi_ai(date_from=today - timedelta(days=1), date_to=today)
    assert report.cost_usd_micros == 1_000_000
    assert report.cost_brl_micros is None
    assert report.rows[0].cost_brl_micros is None


def _conversation():
    conversation = Conversation.objects.create(phone="+5543999990009", last_inbound_at=timezone.now())
    binding = ConversationBinding.objects.create(
        conversation=conversation, provider="manychat", account="bakery-primary", transport_channel="whatsapp",
        subject=f"sub-{conversation.pk}", connection_key="manychat-whatsapp-primary",
        status=ConversationBinding.Status.ACTIVE, identity_assurance="transport_subject",
    )
    return conversation, binding


def _message(conversation, binding, kind, text, at, envelope=None):
    role = ConversationMessage.Role.USER if kind == ConversationMessage.Kind.INBOUND else ConversationMessage.Role.ASSISTANT
    message = ConversationMessage.objects.create(
        conversation=conversation, binding=binding, role=role, kind=kind, text=text, envelope=envelope or {}
    )
    ConversationMessage.objects.filter(pk=message.pk).update(created_at=at)
    message.refresh_from_db()
    return message


def _fallback(*reasons):
    return {"conference": {
        "decision": "fallback",
        "checks": {
            "acceptable": {"status": "pass"},
            "correct": {"status": "pass"},
            "useful": {"status": "fail", "reason": reasons[0]},
            **({"extra": {"status": "unavailable", "reason": reasons[1]}} if len(reasons) > 1 else {}),
        },
    }}


def test_conference_agenda_and_fallbacks_with_the_customer_text_redacted():
    today = timezone.localdate()
    conversation, binding = _conversation()
    Kind = ConversationMessage.Kind
    base = _at(today, 9)
    _message(conversation, binding, Kind.INBOUND, "tem pão hoje?", base)
    _message(conversation, binding, Kind.REPLY, "Temos baguete. Quer reservar?", base + timedelta(minutes=1),
             {"conference": {"decision": "send", "checks": {"useful": {"status": "pass"}}}})
    _message(conversation, binding, Kind.INBOUND, "meu cpf é 123.456.789-09, emite a nota?", base + timedelta(minutes=5))
    _message(conversation, binding, Kind.INBOUND, "manda pra maria.silva@gmail.com", base + timedelta(minutes=6))
    _message(conversation, binding, Kind.REPLY, "Hoje temos ciabatta.", base + timedelta(minutes=7),
             _fallback("judge_off_target", "unconferred"))

    with mock.patch(FETCH, return_value={}):
        report = bi_ai.build_bi_ai(date_from=today, date_to=today)

    assert (report.conferred, report.would_fall) == (2, 1)
    assert {r.reason: r.count for r in report.reasons} == {"judge_off_target": 1, "unconferred": 1}
    assert report.reasons[0].label in {"Fala de outra coisa", "Ficou sem conferir (o juiz não respondeu)"}
    [fallback] = report.fallbacks
    # Só as falas que esta resposta respondeu, e redigidas pelo redator da Concierge.
    assert "tem pão hoje" not in fallback.customer_text
    assert "[documento omitido]" in fallback.customer_text
    assert "[email]" in fallback.customer_text
    assert "123.456.789-09" not in fallback.customer_text
    assert "gmail" not in fallback.customer_text
    assert fallback.reply_text == "Hoje temos ciabatta."
    assert fallback.reasons == ("Fala de outra coisa", "Ficou sem conferir (o juiz não respondeu)")
    assert fallback.admin_url.endswith(f"/{conversation.pk}/change/")


def test_without_the_redactor_the_customer_text_never_leaves(monkeypatch):
    """Falha fechada: sem o redator da Concierge registrado, o texto não sai."""
    monkeypatch.setattr(concierge_reading, "_redactor", [])
    today = timezone.localdate()
    conversation, binding = _conversation()
    Kind = ConversationMessage.Kind
    _message(conversation, binding, Kind.INBOUND, "meu telefone é 43 99999-0000", _at(today, 9))
    _message(conversation, binding, Kind.REPLY, "Anotado.", _at(today, 10), _fallback("no_next_step"))
    with mock.patch(FETCH, return_value={}):
        report = bi_ai.build_bi_ai(date_from=today, date_to=today)
    assert report.fallbacks[0].customer_text == bi_ai.OMITTED_TEXT


def test_what_the_house_lacks_groups_the_questions_passed_to_the_team():
    today = timezone.localdate()
    for message in (
        "“Vocês aceitam encomenda de bolo para 30 pessoas?”\nPrometemos responder até 15h.",
        "“vocês aceitam encomenda de bolo para 30 pessoas”\nA Concierge não prometeu prazo.",
        "1) “Tem estacionamento?”; 2) “Vocês aceitam encomenda de bolo para 30 pessoas?”\nPrometemos responder até 16h.",
    ):
        alert = OperatorAlert.objects.create(type=bi_ai.VERIFY_ALERT_TYPE, severity="warning", message=message)
        OperatorAlert.objects.filter(pk=alert.pk).update(created_at=_at(today, 11))
    OperatorAlert.objects.create(type="stock_low", severity="warning", message="“não é pergunta de cliente”")

    with mock.patch(FETCH, return_value={}):
        report = bi_ai.build_bi_ai(date_from=today, date_to=today)

    assert [(g.count, g.question) for g in report.gaps] == [
        (3, "Vocês aceitam encomenda de bolo para 30 pessoas?"),
        (1, "Tem estacionamento?"),
    ]
    assert "/admin/shop/faqentry/add/?question=" in report.gaps[0].admin_url
