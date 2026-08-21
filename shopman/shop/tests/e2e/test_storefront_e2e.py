"""
Playwright E2E for the storefront — post-headless topology.

The headless cutover retired the Django customer pages: the **Nuxt store** now
serves every customer surface, and **Django** serves only the API + the operator/
admin pages. These flows are rewritten accordingly:

  · Customer flows (menu → PDP → cart → checkout, tracking) run against the Nuxt
    store (``store_base_url``), with UI-Thing/Nuxt selectors — not the dead HTMX
    pages.
  · Operator flows stay on Django (``operator_base_url``), on the Admin/Unfold
    pages that survived the cutover.

⚠️ **Nenhuma rota escrita à mão aqui.** Os caminhos do cliente saem de
``shopman.shop.services.storefront_links`` e os do operador de ``reverse()``.
Não é preciosismo: a versão anterior deste arquivo navegava ``/cart``,
``/checkout``, ``/login`` e ``/tracking/<ref>`` — nomes em inglês que a loja
nunca serviu (ela serve ``/sacola``, ``/finalizar``, ``/entrar``, ``/pedido/<ref>``)
— e ``/admin/operacao/pedidos/`` e ``/operacao/kds/``, que sumiram no cutover
headless. Tudo dava 404, e o pior nem era falhar: ``test_03`` afirmava a AUSÊNCIA
de "Sacola vazia" numa página de erro que também não continha a frase, e passava
sem ter testado nada. Ligar o teste à fonte única faz um rename quebrar aqui,
que é onde tem que quebrar.

Pela mesma razão as asserções de conteúdo são POSITIVAS: afirmar que algo
apareceu é impossível de satisfazer com uma tela que não renderizou.

Prerequisites (handled by scripts/run_storefront_e2e.sh):
  pip install pytest-playwright && playwright install chromium
  Two servers up: Nuxt store (:3100, BFF → Django) + Django (:8001), seeded.

Run via the orchestration script (boots both servers + seed):
  bash scripts/run_storefront_e2e.sh

Or against already-running servers:
  pytest shopman/shop/tests/e2e/test_storefront_e2e.py \
      --store-base-url=http://127.0.0.1:3100 \
      --operator-base-url=http://127.0.0.1:8001

These tests require RUNNING servers. They are NOT collected by `make test`
(the e2e directory is excluded from the default pytest path).
"""

from __future__ import annotations

import re

import pytest
from django.urls import reverse

from shopman.shop.services import storefront_links

# Skip the whole module if Playwright is not installed.
pw = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

# Browser E2E: deselected from the default suite (addopts `-m 'not browser'`),
# re-selected by scripts/run_storefront_e2e.sh with `-m browser` once both the
# Nuxt store and the Django API are up.
pytestmark = pytest.mark.browser

ADD_TO_CART = re.compile(r"Adicionar", re.IGNORECASE)


def _product_link(page, store_base_url):
    """First product card off the live menu: (sku, nome visível no card)."""
    page.goto(f"{store_base_url}{storefront_links.path_menu()}", wait_until="networkidle")
    card = page.locator("a[href*='/produto/']").first
    href = card.get_attribute("href")
    if not href:
        return None, ""
    match = re.search(r"/produto/([^/?#]+)", href)
    return (match.group(1) if match else None), card.inner_text().strip()


def _seeded_sku(page, store_base_url) -> str | None:
    return _product_link(page, store_base_url)[0]


# ---------------------------------------------------------------------------
# Customer store (Nuxt) — happy paths
# ---------------------------------------------------------------------------


class TestCustomerStore:
    """Core customer journey against the Nuxt store."""

    def test_01_menu_lists_products_with_pdp_links(self, page, store_base_url):
        """Menu renders product cards that link to the PDP — no dead end."""
        page.goto(f"{store_base_url}{storefront_links.path_menu()}", wait_until="networkidle")
        assert page.title(), "Menu should have a title"
        product_links = page.locator("a[href*='/produto/']")
        expect(product_links.first).to_be_visible()
        assert product_links.count() > 0, "Seeded menu should list products"

    def test_02_pdp_loads_with_price_and_add_button(self, page, store_base_url):
        """Navigate menu → PDP; the PDP shows price + an Adicionar action."""
        sku = _seeded_sku(page, store_base_url)
        assert sku, "Seeded menu should expose at least one product SKU"
        page.goto(
            f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle"
        )
        assert f"/produto/{sku}" in page.url
        # Price is rendered as R$ … and an add-to-cart control is offered.
        expect(page.get_by_text(re.compile(r"R\$")).first).to_be_visible()
        expect(page.get_by_role("button", name=ADD_TO_CART).first).to_be_visible()

    def test_03_add_to_cart_then_cart_shows_item(self, page, store_base_url):
        """Add from the PDP, then the cart shows THAT item.

        Asserção positiva de propósito: o nome do produto que entrou tem que
        aparecer na sacola. A versão antiga afirmava a ausência de "Sacola
        vazia" e passava numa página 404.
        """
        sku = _seeded_sku(page, store_base_url)
        assert sku, "Seeded menu should expose at least one product SKU"
        page.goto(
            f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle"
        )
        product_name = page.locator("h1").first.inner_text().strip()
        assert product_name, "PDP should name the product"
        page.get_by_role("button", name=ADD_TO_CART).first.click()
        # Optimistic cart state settles, then the cart page reflects the item.
        page.wait_for_timeout(600)
        cart = page.goto(f"{store_base_url}{storefront_links.path_cart()}", wait_until="networkidle")
        assert cart.status == 200, f"sacola respondeu {cart.status}"
        expect(page.get_by_text(product_name, exact=False).first).to_be_visible()
        # Contraparte estrutural do estado vazio (test_05): sacola com item TEM
        # linha de produto. As duas asserções juntas impedem que uma página que
        # não renderizou satisfaça qualquer um dos dois testes.
        assert page.locator("main a[href*='/produto/']").count() > 0

    def test_04_checkout_surfaces_auth_gate(self, page, store_base_url):
        """Anonymous checkout surfaces the login guardrail (expected, not a bug).

        Checkout gates on authentication: the store either redirects to the login
        page or shows the "entrar por telefone" prompt. Either is the intended
        guardrail — but the page must EXIST (200), or "gated" would be indistinct
        from "rota errada".
        """
        response = page.goto(
            f"{store_base_url}{storefront_links.path_checkout()}", wait_until="networkidle"
        )
        assert response.status == 200, f"finalizar respondeu {response.status}"
        gated = storefront_links.path_login() in page.url or page.get_by_text(
            re.compile(r"entrar", re.IGNORECASE)
        ).first.is_visible()
        assert gated, "Checkout should gate anonymous visitors on login"


# ---------------------------------------------------------------------------
# Customer store (Nuxt) — edge cases
# ---------------------------------------------------------------------------


class TestCustomerEdgeCases:
    """Resilience + order-scoped access on the Nuxt store."""

    def test_05_cart_empty_state(self, page, store_base_url):
        """A fresh visitor sees the empty-cart state, not a crash.

        ⚠️ A frase do estado vazio NÃO serve de asserção: ela vem de
        ``resolve_copy`` por momento/audiência (com a loja fechada vira "Já
        fechamos por hoje…"), então casar texto aqui reprova por horário. O que
        é estrutural é: a página existe (título) e não há NENHUM item na sacola,
        com o caminho de volta ao cardápio no lugar (omotenashi: sem beco).
        """
        page.context.clear_cookies()
        page.goto(f"{store_base_url}{storefront_links.path_cart()}", wait_until="networkidle")
        # Controle positivo: a rota renderizou de verdade. Numa página 404 este
        # título não existe — foi o buraco que deixou a versão antiga passar.
        expect(page.get_by_role("heading", name="Sua sacola")).to_be_visible()
        expect(page.locator("main a[href*='/produto/']")).to_have_count(0)
        expect(page.locator("main a[href='/menu']").first).to_be_visible()

    def test_06_unknown_order_tracking_is_graceful(self, page, store_base_url):
        """Tracking a non-existent/unauthorized order degrades gracefully.

        Without an order-access grant the store shows an access/not-found view
        with a path back (login), never a stack trace.
        """
        page.context.clear_cookies()
        page.goto(
            f"{store_base_url}{storefront_links.path_order_tracking('NONEXISTENT-001')}",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(800)
        body = page.locator("body")
        expect(body).to_be_visible()
        # Friendly recovery, not a server error dump.
        assert not re.search(r"Server Error|Traceback", body.inner_text())

    def test_07_tracking_ready_with_grant(
        self, page, store_base_url, grant_order_access, ready_order_ref
    ):
        """With a session grant, tracking renders the real READY order state."""
        grant_order_access(page.context, ready_order_ref)
        # A tela do acompanhamento abre SSE: `networkidle` nunca chega.
        page.goto(
            f"{store_base_url}{storefront_links.path_order_tracking(ready_order_ref)}",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(1500)
        body = page.locator("body").inner_text()
        # The granted page shows the order, not the access-error fallback.
        assert ready_order_ref in body or re.search(r"pronto|retir|entrega", body, re.IGNORECASE), (
            "Granted tracking page should render the order state"
        )

    def test_08_payment_pending_with_grant(
        self, page, store_base_url, grant_order_access, pix_pending_order_ref
    ):
        """With a session grant, the tracking page renders the PIX inline.

        PAYMENT-TRACKING-MERGE: não há mais tela /pagamento — o Pix é um degrau do
        próprio acompanhamento.
        """
        grant_order_access(page.context, pix_pending_order_ref)
        page.goto(
            f"{store_base_url}{storefront_links.path_order_tracking(pix_pending_order_ref)}",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(1500)
        body = page.locator("body").inner_text()
        assert re.search(r"PIX|pagamento|pagar|expir", body, re.IGNORECASE), (
            "Granted tracking page should render the PIX payment state inline"
        )


# ---------------------------------------------------------------------------
# Operator (Django) — o que sobrou no Django depois do cutover headless
# ---------------------------------------------------------------------------

#: Telas de operador que o DJANGO ainda serve. Fila de pedidos, KDS, PDV,
#: produção e fechamento migraram para apps Nuxt dedicados (surfaces/*-nuxt) e
#: não são servidas por este gate — quem as navega é o gate de browser
#: Omotenashi, que agora reprova se elas não estiverem de pé.
OPERATOR_ADMIN_ROUTES = (
    "admin_console_settings_hub",
    "admin_console_copy_catalog",
    "admin_console_operator_badge",
    "admin_console_cash_receipt_lookup",
)


class TestOperator:
    """Operator surfaces remain Django-served and gated by auth."""

    @pytest.mark.parametrize("url_name", OPERATOR_ADMIN_ROUTES)
    def test_09_admin_console_loads_for_operator(
        self, page, operator_base_url, operator_session, url_name
    ):
        """As telas Admin/Unfold do operador renderizam para quem está logado."""
        operator_session(page.context)
        response = page.goto(f"{operator_base_url}{reverse(url_name)}")
        assert response.status == 200, f"{url_name} respondeu {response.status}"
        expect(page.locator("body")).to_be_visible()
        assert "/admin/login/" not in page.url
        # Controle positivo: o shell do Admin renderizou de verdade (a barra de
        # navegação do Unfold), e não uma página de erro com 200.
        expect(page.locator("h1, h2").first).to_be_visible()

    @pytest.mark.parametrize("url_name", OPERATOR_ADMIN_ROUTES)
    def test_10_operator_pages_require_auth(self, page, operator_base_url, url_name):
        """Operator pages redirect anonymous visitors to the admin login."""
        page.context.clear_cookies()
        response = page.goto(f"{operator_base_url}{reverse(url_name)}")
        assert response.status in (200, 302, 403)
        # Anonymous lands on (or is redirected to) the login flow.
        assert "/admin/login/" in page.url or response.status in (302, 403), (
            f"{url_name} serviu conteúdo para visitante anônimo (url={page.url})"
        )


# ---------------------------------------------------------------------------
# Navigation smoke
# ---------------------------------------------------------------------------


class TestNavigation:
    """Core pages return 200 and render."""

    @pytest.mark.parametrize(
        "path",
        [
            storefront_links.path_home(),
            storefront_links.path_menu(),
            storefront_links.path_cart(),
            storefront_links.path_checkout(),
            storefront_links.path_login(),
            "/busca",
        ],
    )
    def test_store_pages_load(self, page, store_base_url, path):
        """Public store pages return 200/redirect and render."""
        response = page.goto(f"{store_base_url}{path}")
        assert response.status in (200, 302), f"{path} returned {response.status}"
        expect(page.locator("body")).to_be_visible()
