"""
A loja lê a versão que o servidor decidiu, e a versão não vaza (OC-21, X14).

Contra a pilha real do harness (``scripts/run_storefront_e2e.sh``): loja Nuxt
compilada, BFF Nitro e Django semeado. O experimento ``prova-e2e`` nasce pelo
SERVIDOR (``seed_experience.py``, antes de o Django subir): uma ``RuleConfig`` com
o cliente ``CLI-003`` na coorte ``internal``. Nada no navegador escolhe a versão
(decisão D1 do dono): a cliente entra pelo código do SMS, como entra todo dia, e o
teste só olha o que a loja devolve.

O que se prova:

- quem está fora da coorte (``CLI-005``) e o anônimo veem a versão padrão ``a``;
- quem está na coorte vê ``b``, e recarregar não alterna;
- a resposta B é privada nas duas bordas do Nitro: o documento SSR (que embute o
  shell no payload) e a API do shell pelo BFF saem ``private, no-store``. No
  documento, quem garante é a regra de sessão (#3474): versão fora da padrão só
  existe com sessão, e todo documento com sessão sai privado;
- documento com sessão é privado em qualquer rota, inclusive na versão padrão; o
  anônimo segue cacheável (#3474);
- o login gravou a aderência na sessão do servidor (``shopman_experience``);
- parâmetro de URL não troca a versão de ninguém.

Não há tela B (isso é o OC-33, depois da aprovação L2): o consumidor da versão no
navegador é a própria leitura do shell que a página faz pelo BFF.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from shopman.shop.services import storefront_links
from shopman.shop.tests.e2e.conftest import _in_thread
from shopman.shop.tests.e2e.seed_experience import (
    COHORT_CUSTOMER_PHONE,
    EXPERIMENT_REF,
    OUTSIDE_CUSTOMER_PHONE,
)

pw = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

pytestmark = pytest.mark.browser

SHELL_API = "/api/v1/storefront/shell/"

# A leitura que a própria página faz do shell, pelo BFF same-origin, com o cookie
# da sessão. Devolve a versão do experimento e o Cache-Control que o navegador viu.
_READ_SHELL = """
async (path) => {
  const response = await fetch(path, { credentials: 'include', headers: { accept: 'application/json' } })
  const body = await response.json()
  const items = (body && body.shell && body.shell.experience) || []
  return { status: response.status, cacheControl: response.headers.get('cache-control') || '', items }
}
"""


def _variant(items: list[dict]) -> str | None:
    found = [item for item in items if item.get("ref") == EXPERIMENT_REF]
    return found[0]["variant"] if found else None


def _read_shell(page, query: str = "") -> dict:
    return page.evaluate(_READ_SHELL, f"{SHELL_API}{query}")


def _open(page, store_base_url: str, path: str):
    response = page.goto(f"{store_base_url}{path}")
    assert response is not None and response.status == 200, f"{path}: {response and response.status}"
    return response


def _sign_in_by_sms(page, store_base_url: str, phone: str) -> None:
    """Entra pela tela, com o código que chegou fora do contrato HTTP, e volta ao cardápio."""
    otp_file_value = os.environ.get("SHOPMAN_E2E_OTP_FILE", "").strip()
    assert otp_file_value, "Defina SHOPMAN_E2E_OTP_FILE para o canal do harness E2E."
    otp_file = Path(otp_file_value)
    menu = storefront_links.path_menu()

    page.goto(f"{store_base_url}{storefront_links.path_login()}?next={menu}")
    expect(page.get_by_role("button", name="Prefere receber um código por SMS?")).to_be_visible()
    page.get_by_role("button", name="Prefere receber um código por SMS?").click()
    page.locator("#login-phone").fill(phone)
    page.locator("form:has(#login-phone) button[type='submit']").click()

    inputs = page.locator("form input[inputmode='numeric']")
    expect(inputs).to_have_count(6, timeout=15_000)
    expect(inputs.first).to_be_visible(timeout=15_000)
    code = ""
    for _ in range(50):
        if otp_file.exists():
            code = otp_file.read_text(encoding="utf-8").strip()
            if len(code) == 6 and code.isdigit():
                otp_file.unlink()
                break
        page.wait_for_timeout(100)
    assert len(code) == 6 and code.isdigit(), "O canal do harness E2E não entregou um OTP válido."
    for index, digit in enumerate(code):
        inputs.nth(index).fill(digit)
    page.wait_for_url(lambda url: urlparse(url).path == menu, timeout=20_000)


def _session_experience(django_db_blocker, context) -> dict:
    """A aderência que o servidor gravou na sessão desta cliente."""
    from django.conf import settings

    key = next(
        (c["value"] for c in context.cookies() if c["name"] == settings.SESSION_COOKIE_NAME),
        "",
    )
    assert key, "a cliente entrou e o navegador não tem a sessão do Django"

    def read():
        with django_db_blocker.unblock():
            from django.contrib.sessions.backends.db import SessionStore

            from shopman.shop.services.experience import SESSION_KEY

            return dict(SessionStore(session_key=key).get(SESSION_KEY) or {})

    return _in_thread(read)


def _is_private(cache_control: str) -> bool:
    directives = {part.strip().split("=")[0].lower() for part in cache_control.split(",")}
    return {"private", "no-store"} <= directives and "public" not in directives


# Páginas que o anônimo recebe sem ``no-store`` (cacheáveis) e que, com sessão,
# embutem o nome e a sacola da cliente no payload do Nuxt (#3474).
PUBLIC_WHEN_ANONYMOUS = (
    storefront_links.path_menu(),
    storefront_links.path_product("TRADI"),
    "/termos",
    "/privacidade",
    "/faq",
)


def _assert_session_documents_are_private(page, store_base_url: str) -> None:
    """#3474: com sessão, todo documento sai ``private, no-store``, em qualquer rota."""
    for path in (*PUBLIC_WHEN_ANONYMOUS, storefront_links.path_home()):
        document = _open(page, store_base_url, path)
        expect(page.locator("main").first).to_be_visible()
        cache = document.headers.get("cache-control") or ""
        assert _is_private(cache), f"{path} com sessão saiu '{cache}'"


class TestExperienceDecidedByTheServer:
    def test_anonymous_sees_the_default_and_the_url_does_not_choose(self, page, store_base_url):
        _open(page, store_base_url, storefront_links.path_menu())
        shell = _read_shell(page)
        assert _variant(shell["items"]) == "a"

        _open(page, store_base_url, f"{storefront_links.path_menu()}?experience=b&{EXPERIMENT_REF}=b")
        assert _variant(_read_shell(page, "?experience=b")["items"]) == "a"

    def test_customer_outside_the_cohort_sees_a(self, page, store_base_url, django_db_blocker):
        _sign_in_by_sms(page, store_base_url, OUTSIDE_CUSTOMER_PHONE)

        document = _open(page, store_base_url, storefront_links.path_menu())
        shell = _read_shell(page)
        assert _variant(shell["items"]) == "a"
        # Com sessão o documento é privado mesmo na versão padrão: ele embute o nome
        # e a sacola da cliente (#3474, regra de sessão, não de experimento).
        document_cache = document.headers.get("cache-control") or ""
        assert _is_private(document_cache), f"cardápio com sessão saiu '{document_cache}'"
        assert _session_experience(django_db_blocker, page.context)[EXPERIMENT_REF]["variant"] == "a"
        _assert_session_documents_are_private(page, store_base_url)

    def test_customer_in_the_cohort_sees_b_privately_and_reload_does_not_switch(
        self, page, store_base_url, django_db_blocker
    ):
        _sign_in_by_sms(page, store_base_url, COHORT_CUSTOMER_PHONE)

        # O login (comando) gravou a aderência; o GET do shell só lê.
        assert _session_experience(django_db_blocker, page.context)[EXPERIMENT_REF] == {
            "variant": "b",
            "generation": 1,
        }

        for attempt in range(3):
            document = _open(page, store_base_url, storefront_links.path_menu())
            document_cache = document.headers.get("cache-control") or ""
            assert _is_private(document_cache), f"recarga {attempt}: documento B saiu '{document_cache}'"

            shell = _read_shell(page)
            assert _variant(shell["items"]) == "b", f"recarga {attempt}: alternou para {shell['items']}"
            assert _is_private(shell["cacheControl"]), f"recarga {attempt}: shell B saiu '{shell['cacheControl']}'"

        # A home tem regra de rota própria (no-transform): continua, e ganha no-store.
        home = _open(page, store_base_url, storefront_links.path_home())
        home_cache = home.headers.get("cache-control") or ""
        assert _is_private(home_cache) and "no-transform" in home_cache, home_cache

        # Nenhum parâmetro tira ninguém da coorte.
        _open(page, store_base_url, f"{storefront_links.path_menu()}?experience=a&{EXPERIMENT_REF}=a")
        assert _variant(_read_shell(page, "?experience=a")["items"]) == "b"


class TestSessionDocumentIsNeverShared:
    """#3474: o documento SSR com sessão embute nome e sacola; nenhuma rota é de todos.

    O lado com sessão roda dentro de ``test_customer_outside_the_cohort_sees_a``
    (:func:`_assert_session_documents_are_private`): o mesmo telefone não pede um
    segundo código de SMS na mesma corrida (a espera de reenvio do Doorman).
    """

    def test_anonymous_document_keeps_its_cache_policy(self, page, store_base_url):
        for path in PUBLIC_WHEN_ANONYMOUS:
            document = _open(page, store_base_url, path)
            assert "no-store" not in (document.headers.get("cache-control") or ""), path
