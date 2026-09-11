"""QA Chromium local. Nenhum envio ManyChat; configurações da seed são sintéticas."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

mode = sys.argv[1] if len(sys.argv) > 1 else "contained"
base = "http://127.0.0.1:58419"
errors = []
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for username in ("synthetic-admin", "synthetic-viewer"):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(base + "/admin/login/?next=/admin/shop/conversation/", wait_until="networkidle")
        page.locator("input[name=username]").fill(username)
        page.locator("input[name=password]").fill("test-only-concierge-browser")
        page.locator("button[type=submit]").click()
        page.wait_for_url("**/admin/shop/conversation/")
        page.wait_for_load_state("networkidle")
        action = page.locator('option[value="return_to_concierge_selected"]')
        expected = mode == "return-enabled" and username == "synthetic-admin"
        assert bool(action.count()) == expected, (username, mode, page.content())
        if expected:
            page.locator('input[name="_selected_action"]').first.check()
            page.locator('select[name="action"]').select_option("return_to_concierge_selected")
            page.locator('button[name="index"]').click()
            page.wait_for_load_state("networkidle")
            assert "atendimento humano preservado" in page.inner_text("body")
            page.screenshot(path="evidence/conversational/admin-return-unconfirmed.png", full_page=True)
        page.goto(base + "/admin/shop/conversation/1/change/", wait_until="networkidle")
        assert "Cliente Sintético" in page.inner_text("body")
        assert page.locator('input[name="_save"]').count() == 0
        # Tabs são o mecanismo nativo do Unfold; transcrição continua legível.
        tab = page.get_by_text("Transcrição", exact=True)
        if tab.count():
            tab.first.click()
        page.screenshot(path="evidence/conversational/admin-inspect.png", full_page=True)
        Path("evidence/conversational/admin-inspect.txt").write_text(page.inner_text("body"))
        page.get_by_text("Envio desconhecido; não reenviar sem verificar", exact=True).wait_for(state="visible")
        page.screenshot(path=f"evidence/conversational/admin-{mode}-{username}-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=f"evidence/conversational/admin-{mode}-{username}-mobile.png", full_page=True)
        results.append({"mode": mode, "user": username, "return_action": expected, "unknown_label": True, "save_control": False})
        context.close()
    browser.close()
print(json.dumps({"results": results, "console_errors": errors}, ensure_ascii=False, indent=2))
assert not errors, errors
