"""QA visual v3 do Admin; browser local e dados totalmente sintéticos."""

import json
import sys
from pathlib import Path

from playwright.sync_api import Locator, sync_playwright

mode = sys.argv[1] if len(sys.argv) > 1 else "contained"
if mode not in {"contained", "return-enabled"}:
    raise SystemExit("mode deve ser contained ou return-enabled")

base = "http://127.0.0.1:58419"
artifact_dir = Path("evidence/conversational/browser-v3")
artifact_dir.mkdir(parents=True, exist_ok=True)
errors: list[str] = []
results: list[dict] = []


def visible_text_is_not_clipped(locator: Locator) -> bool:
    """Reprova ellipsis/overflow oculto nos textos que guiam o operador."""
    return locator.evaluate(
        """element => {
            const style = getComputedStyle(element);
            const hidden = ['hidden', 'clip'].includes(style.overflow) ||
                           ['hidden', 'clip'].includes(style.overflowX);
            const ellipsis = style.textOverflow === 'ellipsis';
            return !(element.scrollWidth > element.clientWidth && (hidden || ellipsis));
        }"""
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for username in ("synthetic-admin", "synthetic-viewer"):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        page.on(
            "console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None
        )
        page.goto(base + "/admin/login/?next=/admin/shop/conversation/", wait_until="networkidle")
        page.locator("input[name=username]").fill(username)
        page.locator("input[name=password]").fill("test-only-concierge-browser")
        page.locator("button[type=submit]").click()
        page.wait_for_url("**/admin/shop/conversation/")
        page.wait_for_load_state("networkidle")

        action = page.locator('option[value="return_to_concierge_selected"]')
        expected_action = mode == "return-enabled" and username == "synthetic-admin"
        assert bool(action.count()) == expected_action, (username, mode)
        if expected_action:
            page.locator('input[name="_selected_action"]').first.check()
            page.locator('select[name="action"]').select_option("return_to_concierge_selected")
            page.locator('button[name="index"]').click()
            page.wait_for_load_state("networkidle")
            assert "atendimento humano preservado" in page.inner_text("body")

        row_link = page.get_by_role("link", name="Cliente Sintético").first
        if not row_link.count():
            row_link = page.locator('a[href$="/change/"]').first
        row_link.click()
        page.wait_for_load_state("networkidle")

        body_text = page.inner_text("body")
        handoff_evidence = (
            "Não aplicada; atendimento humano preservado"
            if mode == "return-enabled"
            else "Não confirmada; atendimento humano preservado"
        )
        expected_texts = (
            "Cliente Sintético",
            "whatsapp / manychat (Ativo)",
            "direct_message / tiktok (Ativo)",
            "synthetic-browser-wa",
            "synthetic-browser-tiktok",
            "Escopo configurado; cliente não verificado",
            "Endereço autenticado do transporte",
            handoff_evidence,
        )
        for text in expected_texts:
            assert text in body_text, (username, text)

        # A conversa e o inline são somente leitura inclusive para superuser.
        assert page.locator('input[name="_save"]').count() == 0
        assert page.locator('input[name="_continue"]').count() == 0
        assert page.locator('input[name="_addanother"]').count() == 0
        assert page.locator("#transport_bindings-group input:not([type=hidden])").count() == 0
        assert page.locator("#transport_bindings-group select").count() == 0
        assert page.locator("#transport_bindings-group textarea").count() == 0

        tab = page.get_by_text("Transcrição", exact=True)
        if tab.count():
            tab.first.click()
        unknown = page.get_by_text("Envio desconhecido; não reenviar sem verificar", exact=True)
        accepted = page.get_by_text("Aceita pelo fornecedor; entrega não comprovada", exact=True)
        unknown.wait_for(state="visible")
        accepted.wait_for(state="visible")
        binding_subject = page.get_by_text("synthetic-browser-tiktok", exact=True).last
        handoff_status = page.get_by_text(handoff_evidence, exact=True).last

        desktop_checks = {
            "unknown_text_not_clipped": visible_text_is_not_clipped(unknown),
            "accepted_text_not_clipped": visible_text_is_not_clipped(accepted),
            "binding_subject_not_clipped": visible_text_is_not_clipped(binding_subject),
            "handoff_status_not_clipped": visible_text_is_not_clipped(handoff_status),
        }
        assert all(desktop_checks.values()), desktop_checks
        page.screenshot(path=artifact_dir / f"{mode}-{username}-desktop-1440.png", full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(250)
        unknown.wait_for(state="visible")
        accepted.wait_for(state="visible")
        mobile_checks = {
            "unknown_text_not_clipped": visible_text_is_not_clipped(unknown),
            "accepted_text_not_clipped": visible_text_is_not_clipped(accepted),
            "binding_subject_not_clipped": visible_text_is_not_clipped(binding_subject),
            "handoff_status_not_clipped": visible_text_is_not_clipped(handoff_status),
        }
        assert all(mobile_checks.values()), mobile_checks
        page.screenshot(path=artifact_dir / f"{mode}-{username}-mobile-390.png", full_page=True)

        results.append(
            {
                "mode": mode,
                "user": username,
                "return_action": expected_action,
                "save_controls": False,
                "bindings_inline_read_only": True,
                "bindings": ["manychat/whatsapp", "tiktok/direct_message"],
                "output_states": ["unknown", "accepted"],
                "desktop_1440": desktop_checks,
                "mobile_390": mobile_checks,
            }
        )
        context.close()
    browser.close()

evidence = {
    "contract_version": 3,
    "mode": mode,
    "database": "isolated PostgreSQL",
    "external_credentials": False,
    "provider_network": False,
    "results": results,
    "console_errors": errors,
}
Path(f"evidence/conversational/browser-v3-{mode}.json").write_text(
    json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(evidence, ensure_ascii=False, indent=2))
assert not errors, errors
