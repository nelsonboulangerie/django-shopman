"""Projection dos cenários com IA — o que a tela do B.I. lê (§7.1 da fundação).

Lista os relatórios versionados e diz se o botão "gerar" pode existir
(``configured``): oferecer e falhar depois ensina o gestor a não confiar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BIScenario:
    title: str
    proposal: str
    basis: tuple[str, ...]
    unknowns: tuple[str, ...]


@dataclass(frozen=True)
class BIScenarioReportView:
    id: int
    generated_at: str  # ISO, local
    focus: str
    focus_label: str
    window_from: str
    window_to: str
    model: str
    status: str  # done | failed
    duration_ms: int
    requested_by: str
    scenarios: tuple[BIScenario, ...]
    error: str


@dataclass(frozen=True)
class BIScenarioFocus:
    key: str
    label: str


@dataclass(frozen=True)
class BIScenariosPage:
    configured: bool
    focuses: tuple[BIScenarioFocus, ...]
    reports: tuple[BIScenarioReportView, ...]


def report_view(report) -> BIScenarioReportView:
    from django.utils import timezone

    return BIScenarioReportView(
        id=report.pk,
        generated_at=timezone.localtime(report.generated_at).isoformat(),
        focus=report.focus,
        focus_label=report.get_focus_display(),
        window_from=report.window_from.isoformat(),
        window_to=report.window_to.isoformat(),
        model=report.model,
        status=report.status,
        duration_ms=report.duration_ms,
        requested_by=report.requested_by.get_username() if report.requested_by_id else "",
        scenarios=tuple(
            BIScenario(
                title=str(item.get("title", "")),
                proposal=str(item.get("proposal", "")),
                basis=tuple(str(b) for b in item.get("basis", [])),
                unknowns=tuple(str(u) for u in item.get("unknowns", [])),
            )
            for item in (report.scenarios or [])
        ),
        error=report.error,
    )


def build_bi_scenarios(*, limit: int = 20) -> BIScenariosPage:
    from shopman.backstage.bi.scenarios import is_configured
    from shopman.backstage.models import BIScenarioReport

    reports = BIScenarioReport.objects.select_related("requested_by").order_by("-generated_at")[:limit]
    return BIScenariosPage(
        configured=is_configured(),
        focuses=tuple(BIScenarioFocus(key=key, label=label) for key, label in BIScenarioReport.Focus.choices),
        reports=tuple(report_view(report) for report in reports),
    )
