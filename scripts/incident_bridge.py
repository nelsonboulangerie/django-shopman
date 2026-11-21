#!/usr/bin/env python
"""Ponte de incidentes: todo alerta de produção vira issue com dono, e fecha sozinha.

Fontes (só leitura):
- o resumo de alertas da loja, ``GET /api/v1/backstage/incidents/`` com a
  credencial ``INCIDENTS_TOKEN`` (emitida por ``issue_incident_reader_credential``);
- as issues abertas do Sentry no projeto, quando ``SENTRY_AUTH_TOKEN`` lê issues.

Destino: issues com o label ``alerta`` no repositório (``GITHUB_TOKEN``).

Regras:
- Uma issue por incidente (tipo de alerta, ou issue do Sentry), sem duplicar. A
  ponte acha a sua pelo marcador ``<!-- incident:<fp> -->`` no corpo, e ADOTA uma
  issue aberta à mão cujo título cita o tipo (ex.: "Alerta: lifecycle_phase_stuck").
- O estado vive num comentário fixo, editado no lugar (não gera aviso por hora).
- Incidente verde há 24 h: a issue que a ponte abriu fecha; a adotada recebe o
  aviso de verde e fica para o PR que corrige a causa fechar.
- O mesmo tipo voltando 3 vezes em 7 dias ganha o label ``defeito-recorrente``:
  alerta que volta sempre é defeito, e a causa se corrige no código.
- Issue que a ponte abriu e voltou: reabre, com comentário.

Uso: ``python scripts/incident_bridge.py [--dry-run]``. Sem dependência além da
biblioteca padrão. Contrato: docs/reference/incidents.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

LABEL = "alerta"
RECURRING_LABEL = "defeito-recorrente"
GREEN_HOURS = 24
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
SEVERITY_WORDS = {"warning": "aviso", "error": "erro", "critical": "crítico"}
HTTP_TIMEOUT = 25


@dataclass
class Incident:
    fingerprint: str
    title: str
    adopt_token: str
    owner: str
    measures: str
    home: str
    is_open: bool
    severity: str = ""
    open_count: int = 0
    open_since: datetime | None = None
    green_since: datetime | None = None
    episodes: int = 0
    recurring: bool = False
    refs: list[str] = field(default_factory=list)
    link: str = ""
    remedy: dict = field(default_factory=dict)


@dataclass
class Action:
    kind: str
    issue: int | None
    detail: str


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def local(value: datetime | None) -> str:
    return value.astimezone(LOCAL_TZ).strftime("%d/%m %H:%M") if value else "sem registro"


def marker(fingerprint: str) -> str:
    return f"<!-- incident:{fingerprint} -->"


def status_marker(fingerprint: str) -> str:
    return f"<!-- incident-status:{fingerprint} -->"


# ── Fontes ───────────────────────────────────────────────────────────────────


def _get_json(url: str, *, token: str, scheme: str = "Bearer"):
    request = urllib.request.Request(url, headers={"Authorization": f"{scheme} {token}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310 - URL configurada
        return json.load(response), response.headers.get("Link", "")


def incidents_from_shop(payload: dict) -> list[Incident]:
    if payload.get("schema_version") != 1:
        raise RuntimeError(f"resumo de incidentes com schema desconhecido: {payload.get('schema_version')!r}")
    out = []
    for group in payload.get("groups", []):
        alert_type = group["type"]
        out.append(
            Incident(
                fingerprint=group["fingerprint"],
                title=f"Alerta: {alert_type} ({group['label']})",
                adopt_token=alert_type,
                owner=group["owner"],
                measures=f"{group['label']} (`{alert_type}`)",
                home=group.get("home") or "Admin, alertas operacionais",
                is_open=group["open_count"] > 0,
                severity=group["severity"],
                open_count=group["open_count"],
                open_since=parse_time(group.get("open_since")),
                green_since=parse_time(group.get("green_since")),
                episodes=group.get("episodes", 0),
                recurring=bool(group.get("recurring")),
                refs=list(group.get("order_refs") or []),
                remedy=dict(group.get("remedy") or {}),
            )
        )
    return out


def incidents_from_sentry(issues: list[dict], *, now: datetime) -> list[Incident]:
    """Issue do Sentry aberta e vista nas últimas 24 h é incidente aberto."""

    out = []
    for issue in issues:
        short_id = str(issue.get("shortId") or issue.get("id"))
        last_seen = parse_time(issue.get("lastSeen"))
        unresolved = issue.get("status") == "unresolved"
        is_open = unresolved and last_seen is not None and now - last_seen < timedelta(hours=GREEN_HOURS)
        out.append(
            Incident(
                fingerprint=f"sentry:{short_id}",
                title=f"Alerta: {short_id} (Sentry) {str(issue.get('title') or '')[:80]}".rstrip(),
                adopt_token=short_id,
                owner="Engenharia",
                measures=f"Issue do Sentry `{short_id}`: {issue.get('culprit') or issue.get('title') or ''}",
                home=str(issue.get("permalink") or "Sentry"),
                is_open=is_open,
                severity="critical" if issue.get("level") == "fatal" else "error",
                open_count=int(issue.get("count") or 0) if is_open else 0,
                open_since=parse_time(issue.get("firstSeen")) if is_open else None,
                green_since=None if is_open else last_seen,
                link=str(issue.get("permalink") or ""),
            )
        )
    return out


# ── GitHub ───────────────────────────────────────────────────────────────────


class GitHub:
    def __init__(self, *, repo: str, token: str, api: str = "https://api.github.com", dry_run: bool = False):
        self.repo = repo
        self.token = token
        self.api = api.rstrip("/")
        self.dry_run = dry_run

    def _call(self, method: str, path: str, body: dict | None = None):
        url = path if path.startswith("http") else f"{self.api}/repos/{self.repo}{path}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310 - api.github.com
            raw = response.read()
            return (json.loads(raw) if raw else None), response.headers.get("Link", "")

    def _paged(self, path: str) -> list[dict]:
        items: list[dict] = []
        url = f"{path}{'&' if '?' in path else '?'}per_page=100"
        for _ in range(50):
            page, link = self._call("GET", url)
            items.extend(page or [])
            found = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
            if not found:
                return items
            url = found.group(1)
        raise RuntimeError("paginação do GitHub não terminou")

    def alert_issues(self) -> list[dict]:
        issues = self._paged(f"/issues?state=all&labels={LABEL}")
        return [issue for issue in issues if "pull_request" not in issue]

    def comments(self, number: int) -> list[dict]:
        return self._paged(f"/issues/{number}/comments")

    def write(self, method: str, path: str, body: dict):
        if self.dry_run:
            return {"number": 0, "id": 0}
        return self._call(method, path, body)[0]


def find_issue(incident: Incident, issues: list[dict]) -> tuple[dict | None, bool]:
    """(issue, é da ponte). Prefere a aberta; adota só issue ABERTA escrita à mão."""

    own = [i for i in issues if marker(incident.fingerprint) in (i.get("body") or "")]
    own.sort(key=lambda i: (i["state"] != "open", -i["number"]))
    if own:
        return own[0], True
    token = re.compile(rf"(?<![\w-]){re.escape(incident.adopt_token)}(?![\w-])")
    adopted = [i for i in issues if i["state"] == "open" and token.search(i.get("title") or "")]
    adopted.sort(key=lambda i: i["number"])
    return (adopted[0], False) if adopted else (None, False)


def issue_body(incident: Incident) -> str:
    return "\n".join(
        [
            f"**O que mede:** {incident.measures}",
            f"**Dono:** {incident.owner}",
            f"**Onde se resolve:** {incident.home}",
            "",
            "Aberta pela ponte de incidentes (`scripts/incident_bridge.py`). O estado fica no "
            "comentário fixo abaixo, atualizado a cada rodada. A issue fecha sozinha depois de "
            f"{GREEN_HOURS} h verdes. Se o tipo voltar 3 vezes em 7 dias, ganha o label "
            f"`{RECURRING_LABEL}`: aí a causa se corrige no código.",
            "",
            marker(incident.fingerprint),
        ]
    )


def status_text(incident: Incident, *, now: datetime) -> str:
    if incident.is_open:
        head = f"**Aberto** desde {local(incident.open_since)} ({incident.open_count} em aberto)"
    else:
        head = f"**Verde** desde {local(incident.green_since)}"
    lines = [status_marker(incident.fingerprint), f"{head}. Conferido em {local(now)}.", ""]
    if incident.severity:
        lines.append(f"- Severidade: {SEVERITY_WORDS.get(incident.severity, incident.severity)}")
    if incident.episodes:
        lines.append(f"- Episódios em 7 dias: {incident.episodes}")
    if incident.refs:
        lines.append(f"- Pedidos: {', '.join(incident.refs)}")
    if incident.link:
        lines.append(f"- Sentry: {incident.link}")
    line = remedy_line(incident.remedy)
    if line:
        lines.append(line)
    return "\n".join(lines)


REMEDY_WORDS = (
    ("resolved", "resolveu"),
    ("not_resolved", "não resolveu"),
    ("ran", "conferindo"),
    ("would_run", "acionaria (sombra)"),
    ("refused", "o domínio recusou"),
    ("skipped", "ficou com gente"),
    ("ceiling", "teto"),
)


def remedy_line(remedy: dict) -> str:
    """O placar do remédio do domínio em uma linha, na ordem do que importa."""

    by_outcome = (remedy or {}).get("by_outcome") or {}
    parts = [f"{by_outcome[key]} {word}" for key, word in REMEDY_WORDS if by_outcome.get(key)]
    if not parts:
        return ""
    line = f"- Remédio do domínio ({remedy.get('label') or 'automático'}), 7 dias: {', '.join(parts)}"
    if remedy.get("ai_readings"):
        cost = f"{remedy.get('ai_cost_usd') or 0:.5f}".replace(".", ",")
        line += f"; {remedy['ai_readings']} leitura(s) de IA, US$ {cost}"
    return line


def _strip_conferido(text: str) -> str:
    return re.sub(r" Conferido em [^.]*\.", "", text)


def plan_and_apply(incidents: list[Incident], gh: GitHub, *, now: datetime) -> list[Action]:
    issues = gh.alert_issues()
    actions: list[Action] = []
    seen_issue_numbers: set[int] = set()

    for incident in incidents:
        issue, own = find_issue(incident, issues)
        green_long = (
            not incident.is_open
            and incident.green_since is not None
            and now - incident.green_since >= timedelta(hours=GREEN_HOURS)
        )
        if issue is None:
            if not incident.is_open:
                continue
            labels = [LABEL] + ([RECURRING_LABEL] if incident.recurring else [])
            created = gh.write("POST", "/issues", {"title": incident.title, "body": issue_body(incident), "labels": labels})
            actions.append(Action("abrir", created.get("number"), incident.fingerprint))
            if created.get("number"):
                gh.write("POST", f"/issues/{created['number']}/comments", {"body": status_text(incident, now=now)})
            continue

        number = issue["number"]
        seen_issue_numbers.add(number)
        if issue["state"] != "open":
            if own and incident.is_open:
                gh.write("PATCH", f"/issues/{number}", {"state": "open"})
                gh.write(
                    "POST",
                    f"/issues/{number}/comments",
                    {"body": f"Voltou em {local(incident.open_since)}. Reaberta pela ponte de incidentes."},
                )
                actions.append(Action("reabrir", number, incident.fingerprint))
            else:
                continue

        labels = {label["name"] for label in issue.get("labels", [])}
        if incident.recurring and RECURRING_LABEL not in labels:
            gh.write("POST", f"/issues/{number}/labels", {"labels": [RECURRING_LABEL]})
            gh.write(
                "POST",
                f"/issues/{number}/comments",
                {
                    "body": f"Voltou {incident.episodes} vezes em 7 dias. Isto é defeito: a causa se "
                    "corrige no código, não com remédio automático."
                },
            )
            actions.append(Action("recorrente", number, incident.fingerprint))

        _upsert_status(gh, number, incident, now=now, actions=actions)

        if green_long and issue["state"] == "open":
            if own:
                gh.write(
                    "POST",
                    f"/issues/{number}/comments",
                    {"body": f"Verde desde {local(incident.green_since)}, há mais de {GREEN_HOURS} h. Fechada pela ponte de incidentes."},
                )
                gh.write("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})
                actions.append(Action("fechar", number, incident.fingerprint))
            else:
                actions.append(Action("verde-adotada", number, incident.fingerprint))

    # Issue da ponte cujo incidente saiu da janela de 7 dias: verde há dias.
    feed = {incident.fingerprint for incident in incidents}
    for issue in issues:
        found = re.search(r"<!-- incident:(shop:[\w-]+) -->", issue.get("body") or "")
        if issue["state"] == "open" and found and found.group(1) not in feed and issue["number"] not in seen_issue_numbers:
            gh.write(
                "POST",
                f"/issues/{issue['number']}/comments",
                {"body": "Nenhum alerta deste tipo em 7 dias. Fechada pela ponte de incidentes."},
            )
            gh.write("PATCH", f"/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
            actions.append(Action("fechar", issue["number"], found.group(1)))
    return actions


def _upsert_status(gh: GitHub, number: int, incident: Incident, *, now: datetime, actions: list[Action]) -> None:
    text = status_text(incident, now=now)
    existing = next(
        (c for c in gh.comments(number) if status_marker(incident.fingerprint) in (c.get("body") or "")),
        None,
    )
    if existing is None:
        gh.write("POST", f"/issues/{number}/comments", {"body": text})
        actions.append(Action("estado", number, incident.fingerprint))
    elif _strip_conferido(existing["body"]) != _strip_conferido(text):
        gh.write("PATCH", f"/issues/comments/{existing['id']}", {"body": text})
        actions.append(Action("estado", number, incident.fingerprint))


# ── Entrada ──────────────────────────────────────────────────────────────────


def _sentry_issues(token: str) -> list[dict]:
    base = os.environ.get("SENTRY_API_BASE", "https://sentry.io").rstrip("/")
    org = os.environ.get("SENTRY_ORG", "nelson-boulangerie")
    project = os.environ.get("SENTRY_PROJECT", "shopman")
    query = urllib.parse.quote("is:unresolved environment:production")
    url = f"{base}/api/0/projects/{org}/{project}/issues/?query={query}&statsPeriod=14d&per_page=100"
    payload, _ = _get_json(url, token=token)
    return payload if isinstance(payload, list) else []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    url = os.environ.get("INCIDENTS_URL", "").strip()
    token = os.environ.get("INCIDENTS_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    missing = [name for name, value in (("INCIDENTS_URL", url), ("INCIDENTS_TOKEN", token),
                                        ("GITHUB_REPOSITORY", repo), ("GITHUB_TOKEN", gh_token)) if not value]
    if missing:
        print(f"::error::ponte de incidentes sem {', '.join(missing)}", file=sys.stderr)
        return 2

    now = datetime.now(UTC)
    payload, _ = _get_json(url, token=token)
    incidents = incidents_from_shop(payload)

    sentry_token = os.environ.get("SENTRY_AUTH_TOKEN", "").strip()
    if sentry_token:
        try:
            incidents += incidents_from_sentry(_sentry_issues(sentry_token), now=now)
        except urllib.error.HTTPError as exc:
            # Token sem escopo de issues (event:read): a loja segue; o aviso fica no log da rodada.
            print(f"::warning::Sentry recusou a leitura de issues (HTTP {exc.code}); só os alertas da loja nesta rodada")

    actions = plan_and_apply(incidents, GitHub(repo=repo, token=gh_token, dry_run=args.dry_run), now=now)
    open_now = sum(1 for incident in incidents if incident.is_open)
    print(f"incidentes: {len(incidents)} ({open_now} abertos); ações: {len(actions)}")
    for action in actions:
        print(f"- {action.kind} #{action.issue} {action.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
