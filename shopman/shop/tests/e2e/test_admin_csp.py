"""CSP do Admin provada com settings de produção (DEBUG=false).

"DEBUG local não prova CSP": o config/settings.py relaxa a política em DEBUG
(adiciona 'unsafe-inline' ao script-src), então todo inline `<script>`/handler
passa verde na máquina de dev e é BLOQUEADO em produção — e as telas
Django-rendered do Admin/Unfold são exatamente as expostas. Este teste roda no
job "Admin CSP (production settings)" do Omotenashi Gate, contra um Django de
pé com DJANGO_DEBUG=false, e:

  · navega o Admin logado (index, changelists, telas custom do admin_console),
    coletando `securitypolicyviolation` do documento e mensagens de console
    "Refused to ..." do Chromium;
  · falha em QUALQUER violação de CSP nas telas fora da lista de dívida;
  · assert que o header Content-Security-Policy NÃO tem 'unsafe-inline' no
    script-src — o contrato que o modo DEBUG afrouxa.

⚠️ Nenhuma rota escrita à mão: telas saem de `reverse()` (mesma razão do
test_storefront_e2e.py — rota renomeada tem que quebrar AQUI).

Requer servidor rodando (não entra no `make test`): o job sobe migrate + seed +
collectstatic + runserver com o mesmo bloco de envs do `check --deploy` do
Runtime Gate. Login usa o superuser `admin` que o seed cria, com a senha de
ADMIN_PASSWORD (obrigatória fora de DEBUG).

Rodar contra um servidor já de pé:

    ADMIN_PASSWORD=... pytest shopman/shop/tests/e2e/test_admin_csp.py \
        -m browser --operator-base-url=http://127.0.0.1:8001
"""

from __future__ import annotations

import os

import pytest
from django.urls import reverse

pw = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.browser


def _screens() -> dict[str, str]:
    """Telas navegadas: nome legível → path (via reverse, nunca à mão)."""
    return {
        "admin.index": reverse("admin:index"),
        "admin.ruleconfig.changelist": reverse("admin:shop_ruleconfig_changelist"),
        "admin.channel.changelist": reverse("admin:shop_channel_changelist"),
        "admin_console.settings_hub": reverse("admin_console_settings_hub"),
        "admin_console.copy_catalog": reverse("admin_console_copy_catalog"),
    }


# ── Dívida conhecida de CSP (inline que só quebra fora de DEBUG) ─────────────
#
# Tela aqui listada TEM violação real de CSP com DEBUG=false — o gate a reporta
# no log (para a dívida não sumir de vista) mas não reprova por ela, para o main
# não travar enquanto a tela não é consertada. Tela nova NÃO entra aqui: nasce
# limpa ou não passa. Auditoria de 26/08/2026: as telas navegadas (e também
# changeforms de RuleConfig/Channel/Terminal, badge, comprovante de caixa)
# renderizaram SEM violação fora de DEBUG — a lista nasce vazia de propósito.
KNOWN_CSP_DEBT: dict[str, str] = {}


CSP_INIT_SCRIPT = """
window.__cspViolations = [];
document.addEventListener('securitypolicyviolation', (e) => {
  window.__cspViolations.push(
    (e.violatedDirective || e.effectiveDirective || '?') + ' bloqueou ' +
    (e.blockedURI || 'inline') + (e.lineNumber ? (' @linha ' + e.lineNumber) : '')
  );
});
"""


@pytest.fixture
def admin_page(page, operator_base_url):
    """Página logada no /admin/ com coleta de violações de CSP armada."""
    password = os.environ.get("ADMIN_PASSWORD", "")
    assert password, (
        "ADMIN_PASSWORD ausente: o job precisa exportá-la (o seed fora de DEBUG "
        "exige senha forte, e o login do teste usa a mesma)."
    )

    console_refusals: list[str] = []
    page.add_init_script(CSP_INIT_SCRIPT)
    page.on(
        "console",
        lambda msg: console_refusals.append(msg.text)
        if msg.text.startswith("Refused to")
        else None,
    )

    index_path = reverse("admin:index")
    login_url = f"{operator_base_url}{reverse('admin:login')}?next={index_path}"
    page.goto(login_url, wait_until="networkidle")
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", password)
    page.click("input[type=submit], button[type=submit]")
    page.wait_for_load_state("networkidle")
    assert page.url.rstrip("/").endswith(index_path.rstrip("/")), (
        f"login no Admin falhou (parado em {page.url}) — "
        "ADMIN_PASSWORD divergente da senha do seed?"
    )
    return page, console_refusals


def _drain_violations(page, console_refusals: list[str]) -> list[str]:
    """Violações acumuladas desde a última coleta (documento + console)."""
    dom = page.evaluate(
        "() => { const v = window.__cspViolations || []; window.__cspViolations = []; return v; }"
    )
    console = list(console_refusals)
    console_refusals.clear()
    return list(dom) + console


def test_detector_catches_a_deliberate_violation(page, operator_base_url):
    """O harness pega violação de verdade — senão o verde de cima não vale nada.

    Serve (via route interception) uma página com CSP estrita e um `<script>`
    inline e exige que o listener registre a violação. Se um upgrade do
    Playwright/Chromium mudar o evento ou o timing, quebra AQUI — e não virando
    um gate que passa verde sem enxergar nada.
    """
    page.add_init_script(CSP_INIT_SCRIPT)
    sanity_url = f"{operator_base_url}/__csp_sanity__/"
    page.route(
        sanity_url,
        lambda route: route.fulfill(
            status=200,
            headers={
                "Content-Type": "text/html",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'",
            },
            body="<html><head></head><body><script>document.title='x'</script></body></html>",
        ),
    )
    page.goto(sanity_url, wait_until="networkidle")
    violations = page.evaluate("() => window.__cspViolations || []")
    assert violations, (
        "o detector não registrou a violação deliberada — o gate ficaria verde "
        "sem enxergar nada"
    )


def test_admin_screens_render_without_csp_violations(admin_page, operator_base_url):
    page, console_refusals = admin_page
    # O login também renderiza telas; zera o que ele acumulou antes de medir.
    _drain_violations(page, console_refusals)

    blocking: dict[str, list[str]] = {}
    tolerated: dict[str, list[str]] = {}
    for name, path in _screens().items():
        response = page.goto(f"{operator_base_url}{path}", wait_until="networkidle")
        assert response is not None and response.ok, (
            f"{name} não respondeu 200 em {path}: "
            f"{response.status if response else 'sem resposta'}"
        )

        # O contrato do header vale para TODAS as telas, dívida inclusive: é o
        # que o modo DEBUG afrouxa e o que o deploy serve de verdade.
        csp_header = response.header_value("content-security-policy")
        assert csp_header, f"{name} respondeu sem header Content-Security-Policy"
        script_src = next(
            (
                directive.strip()
                for directive in csp_header.split(";")
                if directive.strip().startswith("script-src")
            ),
            "",
        )
        assert script_src, f"{name}: CSP sem diretiva script-src: {csp_header}"
        assert "'unsafe-inline'" not in script_src, (
            f"{name}: script-src com 'unsafe-inline' fora de DEBUG — o relaxo de "
            f"dev vazou para produção: {script_src}"
        )

        violations = _drain_violations(page, console_refusals)
        if violations:
            (tolerated if name in KNOWN_CSP_DEBT else blocking)[name] = violations

    for name, violations in tolerated.items():
        print(f"\n⚠️ dívida de CSP conhecida em {name} ({KNOWN_CSP_DEBT[name]}):")
        for violation in violations:
            print(f"  · {violation}")

    assert not blocking, "Violações de CSP fora da lista de dívida:\n" + "\n".join(
        f"  {name}:\n" + "\n".join(f"    · {v}" for v in violations)
        for name, violations in blocking.items()
    )


def test_known_debt_list_does_not_rot(admin_page, operator_base_url):
    """Tela na lista de dívida que ficou LIMPA tem que sair da lista.

    Sem isto a lista só cresce: a exceção de hoje vira o buraco permanente de
    amanhã. Quando o conserto chegar, este teste força a remoção da entrada —
    e a tela volta a ser bloqueante para sempre.
    """
    page, console_refusals = admin_page
    _drain_violations(page, console_refusals)

    screens = _screens()
    stale = []
    for name in KNOWN_CSP_DEBT:
        path = screens.get(name)
        if path is None:
            stale.append(f"{name} (tela não existe mais na lista navegada)")
            continue
        page.goto(f"{operator_base_url}{path}", wait_until="networkidle")
        if not _drain_violations(page, console_refusals):
            stale.append(f"{name} (ficou limpa — remova de KNOWN_CSP_DEBT)")

    assert not stale, "Entradas obsoletas em KNOWN_CSP_DEBT:\n" + "\n".join(
        f"  · {item}" for item in stale
    )
