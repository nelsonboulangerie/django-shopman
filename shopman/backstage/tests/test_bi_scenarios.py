"""Cenários com IA: só camada de leitura, resposta validada, relatório versionado (§7.1).

Cobre: as entradas não carregam pedido, cliente nem caixa; o prompt pede JSON
estrito e propor (nunca executar); uma rodada com transporte simulado grava o
relatório com hash; resposta fora do contrato vira `failed` com o motivo e a
resposta crua; sem credencial a API diz `configured=false` e recusa o POST; o
gate é `view_bi`.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.bi import scenarios
from shopman.backstage.models import BIScenarioReport, DayClosing, HistoricalSale
from shopman.backstage.tests.support import historical_batch

GOOD = json.dumps({
    "scenarios": [
        {
            "title": "Reforçar a quinta",
            "proposal": "Assar 20% a mais de croissant na quinta de manhã.",
            "basis": ["quinta 07/08 faturou R$ 1.200,00", "croissant é o primeiro do ranking"],
            "unknowns": ["não sei a sobra da quinta passada"],
        },
        {
            "title": "Segurar o sábado",
            "proposal": "Manter a fornada do sábado no patamar atual.",
            "basis": [],
            "unknowns": ["o clima do sábado"],
        },
    ]
})


@pytest.fixture
def history(db):
    local = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
    for offset in range(1, 10):
        HistoricalSale.objects.create(
            batch=historical_batch("yooga"), source="yooga", external_id=offset,
            occurred_at=local - timedelta(days=offset), total_q=120000, customer_name="Maria da Silva",
        )


@pytest.fixture
def viewer(db):
    user = User.objects.create_user("bi-ia", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi",
    ))
    return user


# ── Entradas ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_inputs_carry_aggregates_with_units_and_nothing_personal(history):
    today = timezone.localdate()
    for focus in ("sales", "production"):
        inputs = scenarios.gather_inputs(focus, today - timedelta(days=27), today)
        dumped = json.dumps(inputs, ensure_ascii=False)
        assert "Maria" not in dumped and "customer" not in dumped.lower()
        assert "cash" not in dumped.lower()  # apuração de caixa não entra: é auditoria
        assert inputs["focus"] == focus and inputs["window"]["to"] == today.isoformat()
    sales = scenarios.gather_inputs("sales", today - timedelta(days=27), today)
    assert sales["totals"]["revenue_q"] == 9 * 120000  # centavos, com o sufixo no nome
    assert "next_week_forecast" in sales  # presente ou com o motivo da ausência


def test_prompt_asks_for_strict_json_and_proposals_only():
    prompt = scenarios.build_prompt({"focus": "sales", "window": {"from": "a", "to": "b"}})
    assert '"scenarios"' in prompt and "unknowns" in prompt
    assert "PROPÕE" in scenarios.ANALYST_VOICE and "nunca" in scenarios.ANALYST_VOICE
    assert "travessão" in scenarios.ANALYST_VOICE


# ── Uma rodada ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
@override_settings(AI_ASSIST_API_KEY="test-key", AI_ASSIST_MODEL="claude-test")
def test_generate_records_a_versioned_report(history, viewer, monkeypatch):
    seen = {}

    def fake_suggest(prompt, *, max_tokens, voice):
        seen["prompt"], seen["voice"] = prompt, voice
        return "```json\n" + GOOD + "\n```"  # cerca de código tolerada

    monkeypatch.setattr("shopman.shop.services.copy_assist.suggest", fake_suggest)
    report = scenarios.generate(focus="sales", requested_by=viewer)
    assert report.status == BIScenarioReport.Status.DONE
    assert [s["title"] for s in report.scenarios] == ["Reforçar a quinta", "Segurar o sábado"]
    assert report.model == "claude-test" and report.requested_by == viewer
    assert len(report.inputs_hash) == 64 and report.inputs["focus"] == "sales"
    assert seen["voice"] == scenarios.ANALYST_VOICE  # a voz do analista, não a da marca
    assert '"scenarios"' in seen["prompt"]
    # A mesma pergunta, o mesmo hash: duas rodadas iguais são reproduzíveis.
    again = scenarios.generate(focus="sales", requested_by=viewer)
    assert again.inputs_hash == report.inputs_hash


@pytest.mark.django_db
@override_settings(AI_ASSIST_API_KEY="test-key")
def test_off_contract_answer_is_a_failed_report_never_an_invented_scenario(history, monkeypatch):
    monkeypatch.setattr("shopman.shop.services.copy_assist.suggest", lambda *a, **k: "Acho que vai vender bem.")
    report = scenarios.generate(focus="production")
    assert report.status == BIScenarioReport.Status.FAILED
    assert report.scenarios == [] and "JSON" in report.error
    assert report.raw_text == "Acho que vai vender bem."

    monkeypatch.setattr("shopman.shop.services.copy_assist.suggest", lambda *a, **k: json.dumps({"scenarios": []}))
    empty = scenarios.generate(focus="production")
    assert empty.status == BIScenarioReport.Status.FAILED


@pytest.mark.django_db
@override_settings(AI_ASSIST_API_KEY="")
def test_without_credential_generation_refuses_before_touching_anything(history):
    with pytest.raises(scenarios.ScenariosNotConfigured):
        scenarios.generate(focus="sales")
    assert BIScenarioReport.objects.count() == 0


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@override_settings(AI_ASSIST_API_KEY="")
def test_api_lists_and_declares_configuration(client, viewer, history):
    client.force_login(viewer)
    page = client.get(reverse("api-backstage-bi-scenarios")).json()["bi"]
    assert page["configured"] is False
    assert [f["key"] for f in page["focuses"]] == ["sales", "production"]
    assert client.post(reverse("api-backstage-bi-scenarios"), {"focus": "sales"}).status_code == 409


@pytest.mark.django_db
@override_settings(AI_ASSIST_API_KEY="test-key")
def test_api_generates_and_returns_the_report(client, viewer, history, monkeypatch):
    monkeypatch.setattr("shopman.shop.services.copy_assist.suggest", lambda *a, **k: GOOD)
    client.force_login(viewer)
    created = client.post(reverse("api-backstage-bi-scenarios"), {"focus": "production"})
    assert created.status_code == 201
    body = created.json()["bi"]
    assert body["status"] == "done" and len(body["scenarios"]) == 2 and body["requested_by"] == "bi-ia"
    assert client.post(reverse("api-backstage-bi-scenarios"), {"focus": "cash"}).status_code == 400
    listed = client.get(reverse("api-backstage-bi-scenarios")).json()["bi"]
    assert listed["reports"][0]["id"] == body["id"]


@pytest.mark.django_db
def test_api_requires_view_bi(client):
    bare = User.objects.create_user("sem-bi", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-bi-scenarios")).status_code == 403
    assert client.post(reverse("api-backstage-bi-scenarios"), {"focus": "sales"}).status_code == 403
