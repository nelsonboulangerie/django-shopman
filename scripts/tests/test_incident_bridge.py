from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("incident_bridge", ROOT / "scripts/incident_bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)

NOW = datetime(2026, 11, 21, 18, 0, tzinfo=UTC)


class FakeGitHub(bridge.GitHub):
    def __init__(self, issues, comments=None):
        super().__init__(repo="o/r", token="t")
        self.issues = issues
        self._comments = comments or {}
        self.calls = []
        self.next_number = 9000

    def alert_issues(self):
        return self.issues

    def comments(self, number):
        return self._comments.get(number, [])

    def write(self, method, path, body):
        self.calls.append((method, path, body))
        if method == "POST" and path == "/issues":
            self.next_number += 1
            return {"number": self.next_number}
        return {}


def _group(alert_type="webhook_failed", *, open_count=1, green_hours=None, episodes=1, recurring=False):
    return {
        "fingerprint": f"shop:{alert_type}",
        "type": alert_type,
        "label": "Webhook falhou",
        "owner": "Engenharia",
        "audience": "operations",
        "severity": "critical",
        "open_count": open_count,
        "open_since": (NOW - timedelta(hours=2)).isoformat() if open_count else None,
        "last_seen": (NOW - timedelta(hours=2)).isoformat(),
        "green_since": (NOW - timedelta(hours=green_hours)).isoformat() if green_hours else None,
        "episodes": episodes,
        "recurring": recurring,
        "home": "",
        "order_refs": ["IFOOD-1"],
    }


def _incidents(*groups):
    return bridge.incidents_from_shop({"schema_version": 1, "groups": list(groups)})


def _issue(number, title, *, body="", state="open", labels=("alerta",)):
    return {"number": number, "title": title, "body": body, "state": state, "labels": [{"name": n} for n in labels]}


def test_open_incident_without_issue_opens_one_with_marker_and_status():
    gh = FakeGitHub([])
    actions = bridge.plan_and_apply(_incidents(_group()), gh, now=NOW)
    assert [a.kind for a in actions] == ["abrir"]
    method, path, body = gh.calls[0]
    assert (method, path) == ("POST", "/issues")
    assert "<!-- incident:shop:webhook_failed -->" in body["body"]
    assert body["labels"] == ["alerta"]
    assert "Aberto" in gh.calls[1][2]["body"]


def test_hand_written_issue_is_adopted_not_duplicated_and_never_closed_by_the_bridge():
    gh = FakeGitHub([_issue(3029, "Alerta: lifecycle_phase_stuck")])
    bridge.plan_and_apply(_incidents(_group("lifecycle_phase_stuck")), gh, now=NOW)
    assert not any(path == "/issues" for _m, path, _b in gh.calls)

    gh = FakeGitHub([_issue(3029, "Alerta: lifecycle_phase_stuck")])
    actions = bridge.plan_and_apply(_incidents(_group("lifecycle_phase_stuck", open_count=0, green_hours=30)), gh, now=NOW)
    assert "verde-adotada" in [a.kind for a in actions]
    assert not any(b.get("state") == "closed" for _m, _p, b in gh.calls)


def test_adoption_matches_the_whole_type_only():
    gh = FakeGitHub([_issue(1, "Alerta: ifood_store_sync_failed_v2 outra coisa")])
    bridge.plan_and_apply(_incidents(_group("ifood_store_sync_failed")), gh, now=NOW)
    assert any(path == "/issues" for _m, path, _b in gh.calls)


def test_bridge_issue_closes_after_24h_green_but_not_before():
    own = _issue(10, "Alerta: webhook_failed", body="<!-- incident:shop:webhook_failed -->")
    gh = FakeGitHub([own])
    bridge.plan_and_apply(_incidents(_group(open_count=0, green_hours=5)), gh, now=NOW)
    assert not any(b.get("state") == "closed" for _m, _p, b in gh.calls)

    gh = FakeGitHub([own])
    actions = bridge.plan_and_apply(_incidents(_group(open_count=0, green_hours=25)), gh, now=NOW)
    assert "fechar" in [a.kind for a in actions]


def test_closed_bridge_issue_reopens_when_it_comes_back():
    own = _issue(10, "Alerta: webhook_failed", body="<!-- incident:shop:webhook_failed -->", state="closed")
    gh = FakeGitHub([own])
    actions = bridge.plan_and_apply(_incidents(_group()), gh, now=NOW)
    assert [a.kind for a in actions][0] == "reabrir"


def test_recurring_gets_the_label_once():
    own = _issue(10, "Alerta: webhook_failed", body="<!-- incident:shop:webhook_failed -->")
    gh = FakeGitHub([own])
    bridge.plan_and_apply(_incidents(_group(episodes=3, recurring=True)), gh, now=NOW)
    assert ("POST", "/issues/10/labels", {"labels": ["defeito-recorrente"]}) in gh.calls

    labelled = _issue(10, "Alerta: webhook_failed", body="<!-- incident:shop:webhook_failed -->",
                      labels=("alerta", "defeito-recorrente"))
    gh = FakeGitHub([labelled])
    bridge.plan_and_apply(_incidents(_group(episodes=3, recurring=True)), gh, now=NOW)
    assert not any(p.endswith("/labels") for _m, p, _b in gh.calls)


def test_status_comment_is_edited_in_place_only_when_the_state_changes():
    own = _issue(10, "Alerta: webhook_failed", body="<!-- incident:shop:webhook_failed -->")
    incident = _incidents(_group())[0]
    text = bridge.status_text(incident, now=NOW - timedelta(hours=1))
    gh = FakeGitHub([own], comments={10: [{"id": 77, "body": text}]})
    bridge.plan_and_apply([incident], gh, now=NOW)
    assert gh.calls == []


def test_bridge_issue_whose_type_left_the_window_closes():
    own = _issue(10, "Alerta: stock_low", body="<!-- incident:shop:stock_low -->")
    gh = FakeGitHub([own])
    actions = bridge.plan_and_apply([], gh, now=NOW)
    assert [a.kind for a in actions] == ["fechar"]


def test_sentry_issue_quiet_for_a_day_is_green():
    issues = [
        {"shortId": "SHOPMAN-12", "status": "unresolved", "lastSeen": (NOW - timedelta(hours=30)).isoformat(),
         "title": "Downtime detected", "level": "error"},
        {"shortId": "SHOPMAN-13", "status": "unresolved", "lastSeen": (NOW - timedelta(hours=1)).isoformat(),
         "firstSeen": (NOW - timedelta(hours=3)).isoformat(), "title": "KeyError", "level": "fatal", "count": "4"},
    ]
    quiet, loud = bridge.incidents_from_sentry(issues, now=NOW)
    assert quiet.is_open is False and quiet.green_since is not None
    assert loud.is_open is True and loud.severity == "critical"


def test_unknown_schema_fails_loudly():
    import pytest

    with pytest.raises(RuntimeError):
        bridge.incidents_from_shop({"schema_version": 2, "groups": []})


def test_status_shows_the_domain_remedy_score():
    group = _group()
    group["remedy"] = {"label": "Reprocessar a NFC-e", "by_outcome": {"resolved": 2, "not_resolved": 1, "skipped": 1}}
    text = bridge.status_text(_incidents(group)[0], now=NOW)
    assert "Remédio do domínio (Reprocessar a NFC-e), 7 dias: 2 resolveu, 1 não resolveu, 1 ficou com gente" in text
    assert bridge.remedy_line({}) == ""


def test_status_shows_ai_readings_and_cost():
    line = bridge.remedy_line({"label": "Reprocessar a NFC-e", "by_outcome": {"resolved": 1}, "ai_readings": 2, "ai_cost_usd": 0.00006})
    assert line.endswith("2 leitura(s) de IA, US$ 0,00006")
