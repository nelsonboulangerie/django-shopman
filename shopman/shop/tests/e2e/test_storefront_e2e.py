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

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

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
    expect(card).to_be_visible(timeout=15_000)
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

    def test_02a_search_escape_restores_trigger_focus(self, page, store_base_url):
        """Search keeps the keyboard user in context after closing the overlay."""
        page.goto(f"{store_base_url}{storefront_links.path_menu()}", wait_until="networkidle")
        trigger = page.get_by_role("button", name="Buscar no cardápio")
        trigger.click()
        searchbox = page.get_by_role("searchbox", name="Buscar no cardápio")
        expect(searchbox).to_be_focused()
        searchbox.fill("croissant")
        expect(page.get_by_role("heading", name="Croissant", exact=True).first).to_be_visible()
        searchbox.press("Escape")
        expect(trigger).to_be_focused()

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
        add_button = page.get_by_role("button", name=ADD_TO_CART).first
        add_button.focus()
        with page.expect_response(
            lambda response: "/api/v1/cart/skus/" in response.url
            and response.request.method == "PUT"
        ) as mutation:
            add_button.press("Enter")
        assert mutation.value.status == 200
        expect(page.get_by_role("button", name=re.compile(r"Aumentar", re.IGNORECASE)).first).to_be_focused()
        cart = page.goto(f"{store_base_url}{storefront_links.path_cart()}", wait_until="networkidle")
        assert cart.status == 200, f"sacola respondeu {cart.status}"
        expect(page.get_by_text(product_name, exact=False).first).to_be_visible()
        # Contraparte estrutural do estado vazio (test_05): sacola com item TEM
        # linha de produto. As duas asserções juntas impedem que uma página que
        # não renderizou satisfaça qualquer um dos dois testes.
        #
        # ⚠️ O seletor era `main a[href*='/produto/']`, e ele NUNCA olhou para a
        # linha da sacola: a linha não linka para a PDP. O único `/produto/` da
        # página vem do `CartUpsellRail`, então o teste afirmava "tem linha de
        # produto" e media "tem sugestão de adicional" — duas coisas diferentes,
        # e a segunda deixou de ser garantida quando o adicional passou a exigir
        # um motivo (WP-SUGESTÃO). `data-cart-line-item` é o que a intenção
        # sempre quis dizer.
        assert page.locator("main [data-cart-line-item]").count() > 0

    def test_03a_immediate_cart_navigation_waits_for_the_mutation(self, page, store_base_url):
        """The optimistic click becomes durable before client-side routing."""
        sku = _seeded_sku(page, store_base_url)
        assert sku
        page.goto(f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle")
        product_name = page.locator("h1").first.inner_text().strip()
        page.get_by_role("button", name=ADD_TO_CART).first.click()
        page.get_by_role("link", name="Ver sacola").click()
        page.wait_for_url(re.compile(r"/sacola$"), timeout=15_000)
        expect(page.get_by_text(product_name, exact=False).first).to_be_visible()

    def test_03b_tap_before_hydration_is_replayed_once(self, page, browser, store_base_url):
        """D1 (opção 3): o toque antes de o app hidratar não se perde.

        O JavaScript da loja fica PRESO na rede enquanto o cliente toca duas vezes
        no "Adicionar" que o servidor entregou. O botão tem de estar ativo, o toque
        tem de aparecer girando na hora, e quando o app fica pronto a sacola recebe
        UMA mutação, não zero (o toque morto de antes) nem duas.
        """
        sku = _seeded_sku(page, store_base_url)
        assert sku
        # Contexto novo, sem service worker: a visita ao cardápio acima instala o
        # worker do PWA, e o que ele serve do cache não passa pelo `route`, então o
        # bundle chegaria e a hidratação aconteceria antes do toque.
        context = browser.new_context(service_workers="block")
        page = context.new_page()
        held = []
        released = []

        def hold_bundle(route):
            if released:
                route.continue_()
            else:
                held.append(route)

        page.route(re.compile(r"/_nuxt/.+\.js(\?.*)?$"), hold_bundle)
        mutations = []
        page.on(
            "request",
            lambda request: mutations.append(request.url)
            if "/api/v1/cart/skus/" in request.url and request.method == "PUT"
            else None,
        )
        # `commit`, não `domcontentloaded`: script de módulo é adiado, e o
        # DOMContentLoaded espera por ele. Com o bundle preso, o evento não vem.
        page.goto(f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="commit")
        page.wait_for_selector("button[data-early-tap]", state="attached")
        add_button = page.locator("button[data-early-tap]").first
        expect(add_button).to_be_enabled()
        add_button.click()
        add_button.click()
        expect(add_button).to_have_attribute("data-early-tap-pending", "true")
        assert held, "o bundle do app deveria estar preso na rede"
        assert mutations == [], "nada pode ir à sacola antes de o app existir"

        with page.expect_response(
            lambda response: "/api/v1/cart/skus/" in response.url
            and response.request.method == "PUT",
            timeout=20_000,
        ) as mutation:
            released.append(True)
            for route in held:
                route.continue_()
        assert mutation.value.status == 200
        page.wait_for_load_state("networkidle")
        assert len(mutations) == 1, f"esperava 1 mutação, vieram {len(mutations)}"
        expect(page.locator("[data-early-tap-pending]")).to_have_count(0)
        context.close()

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

    def test_08a_storage_denied_keeps_cart_journey_usable(self, page, store_base_url):
        """Browser storage is optional; the server session remains canonical."""
        page.add_init_script(
            """
            for (const name of ['localStorage', 'sessionStorage']) {
              Object.defineProperty(window, name, {
                configurable: true,
                get () { throw new DOMException('blocked by browser policy', 'SecurityError') }
              })
            }
            """
        )
        sku = _seeded_sku(page, store_base_url)
        assert sku
        page.goto(f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle")
        product_name = page.locator("h1").first.inner_text().strip()
        with page.expect_response(lambda response: "/api/v1/cart/skus/" in response.url):
            page.get_by_role("button", name=ADD_TO_CART).first.click()
        page.goto(f"{store_base_url}{storefront_links.path_cart()}", wait_until="networkidle")
        expect(page.get_by_text(product_name, exact=False).first).to_be_visible()

    def test_08b_second_tab_reads_same_server_cart(self, page, store_base_url):
        """A second tab resumes the authorized cart without copying fields."""
        sku = _seeded_sku(page, store_base_url)
        assert sku
        page.goto(f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle")
        product_name = page.locator("h1").first.inner_text().strip()
        with page.expect_response(lambda response: "/api/v1/cart/skus/" in response.url):
            page.get_by_role("button", name=ADD_TO_CART).first.click()
        second = page.context.new_page()
        try:
            second.goto(f"{store_base_url}{storefront_links.path_cart()}", wait_until="networkidle")
            expect(second.get_by_text(product_name, exact=False).first).to_be_visible()
        finally:
            second.close()

    def test_08c_keyboard_focus_survives_narrow_zoomed_view(self, page, store_base_url):
        """The menu keeps a visible next action under a constrained viewport."""
        page.set_viewport_size({"width": 320, "height": 640})
        page.goto(f"{store_base_url}{storefront_links.path_menu()}", wait_until="networkidle")
        page.evaluate("document.documentElement.style.zoom = '200%'")
        for _ in range(20):
            page.keyboard.press("Tab")
            focused = page.locator(":focus")
            if focused.count() and focused.evaluate(
                "el => ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)"
            ):
                box = focused.bounding_box()
                assert box is not None
                assert box["x"] < 320 and box["x"] + box["width"] > 0
                return
        raise AssertionError("Nenhuma próxima ação recebeu foco por teclado")


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
        # Controle positivo: a tela renderizou de verdade, e não uma página de
        # erro com 200. O sinal é o TÍTULO da página (o `<h1>` de breadcrumb que
        # o Unfold monta a partir do `title` da view).
        #
        # ⚠️ Era `locator("h1, h2").first` e quebrou no bump do django-unfold
        # 0.92 → 0.107: a partir de alguma dessas treze minors os grupos da
        # barra lateral viraram `<h2>` clicável (`x-on:click="navigationOpen =
        # !navigationOpen"`), e eles vêm ANTES do `<h1>` no DOM. Com a lateral
        # recolhida, o `.first` passou a resolver para um `<h2>` `hidden` e as
        # quatro rotas falhavam com a página inteira renderizada corretamente
        # atrás. Ancorar no `<h1>` diz o que o teste quer dizer — "a página tem
        # título" — e não depende da ordem do chrome no DOM.
        expect(page.locator("h1").first).to_be_visible()

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
# Travessia viva cliente → operador (furo nº 3 da auditoria de 26/08)
# ---------------------------------------------------------------------------

#: Telefone de teste (BR: DDD 43 + celular). Número que o seed não usa: na 1ª
#: rodada o OTP CRIA o cliente (passo de boas-vindas incluso); em reruns contra
#: o mesmo banco o cliente já existe e o fluxo segue direto — os dois caminhos
#: são cobertos pelo teste.
LIVE_ORDER_PHONE = "43991840001"
LIVE_ORDER_NAME = "Cliente E2E"


def _is_checkout_url(url: str) -> bool:
    """O PATH é o checkout — imune ao ``?next=/finalizar`` da tela de login."""
    return urlparse(url).path == storefront_links.path_checkout()


def _authenticate_via_otp(page, phone: str = LIVE_ORDER_PHONE) -> None:
    """Entra pela UI usando um OTP recebido fora do contrato HTTP."""
    otp_file_value = os.environ.get("SHOPMAN_E2E_OTP_FILE", "").strip()
    assert otp_file_value, "Defina SHOPMAN_E2E_OTP_FILE para o canal do harness E2E."
    otp_file = Path(otp_file_value)
    expect(page.get_by_role("button", name="Prefere receber um código por SMS?")).to_be_visible()
    page.get_by_role("button", name="Prefere receber um código por SMS?").click()
    page.locator("#login-phone").fill(phone)
    page.locator("form:has(#login-phone) button[type='submit']").click()

    inputs = page.locator("form input[inputmode='numeric']")
    # O telefone BR também é numeric. Antes da troca de etapa, esperar só o
    # primeiro campo visível preenche o telefone e perde o primeiro dígito do OTP.
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

    # Cliente novo cai no passo de boas-vindas (nome); recorrente vai direto.
    # O momento de celebração leva ~1,4s antes do redirect para o `next`.
    # ⚠️ Comparar pelo PATH, nunca por substring da URL: a página de login é
    # `/entrar?next=/finalizar`, e um `"/finalizar" in page.url` "chega" ao
    # checkout ainda na porta.
    for _ in range(60):
        if _is_checkout_url(page.url):
            return
        welcome = page.locator("[data-login-welcome]")
        if welcome.count():
            page.locator("#welcome-name").fill(LIVE_ORDER_NAME)
            welcome.locator("button[type='submit']").click()
            page.wait_for_url(_is_checkout_url, timeout=15_000)
            return
        page.wait_for_timeout(300)
    raise AssertionError(f"Login não chegou ao checkout (url={page.url})")


def _checkout_action(page, name: str):
    """O botão que avança o checkout.

    ⚠️ Ele NÃO mora mais no rodapé de cada seção: a ação segue o foco e vive no
    card suspenso (`data-checkout-action-card`), único na tela. Procurar dentro
    de `[data-checkout-step=...]` dá timeout — foi assim que este teste caiu
    quando o card entrou.
    """
    return page.locator("[data-checkout-action-card]").get_by_role("button", name=name)


def _ensure_contact_saved(page) -> None:
    """Se o cartão de contato abriu em edição (cliente sem nome), completa-o."""
    name_input = page.locator("#checkout-name")
    if name_input.count() and name_input.first.is_visible():
        if not (name_input.first.input_value() or "").strip():
            name_input.first.fill(LIVE_ORDER_NAME)
        _checkout_action(page, "Salvar contato").click()


def _ensure_pickup_slot_selected(page) -> None:
    """Garante data + horário utilizáveis no passo "Quando".

    ⚠️ hora fixa + ``now()``: rodando à noite, os slots de HOJE já passaram
    todos — aí o teste muda para a próxima data disponível (opção que a
    projection sempre oferece) em vez de reprovar por horário de parede.
    """
    when = page.locator("[data-checkout-step='when']")
    # O passo precisa estar EXPANDIDO (é o ativo após o "Continuar" da retirada):
    # as datas rápidas sempre existem nele, então elas são o sinal de renderizado.
    expect(when.locator("[role='radio'][id^='checkout-date-']").first).to_be_visible(
        timeout=15_000
    )
    slot_radios = when.locator("[role='radio'][id^='checkout-slot-']")
    if not slot_radios.count():
        return  # canal sem slots de retirada: só a data (default já hidratado)

    def checked_and_enabled() -> bool:
        checked = when.locator("[role='radio'][id^='checkout-slot-'][aria-checked='true']")
        return bool(checked.count()) and checked.first.is_enabled()

    if not checked_and_enabled():
        date_radios = when.locator("[role='radio'][id^='checkout-date-']")
        if date_radios.count() > 1:
            date_radios.last.click()
        enabled_slot = when.locator(
            "[role='radio'][id^='checkout-slot-']:not([data-disabled])"
        ).first
        expect(enabled_slot).to_be_visible(timeout=15_000)
        enabled_slot.click()


class TestLiveOrderCrossing:
    """Um pedido NASCE pela UI e aparece do lado do operador.

    O furo que isto fecha: a suíte parava no auth-gate (test_04) e usava
    pedidos do SEED para tracking/pagamento — nenhum pedido atravessava vivo
    menu → PDP → sacola → OTP → checkout → fila do operador. Aqui o cliente é
    o Playwright clicando na loja Nuxt; a VERIFICAÇÃO do outro lado é a API
    crua do backstage (contrato independe da superfície), com a sessão de
    operador que o test_09 já usa.

    Confirmação otimista: o pedido web auto-confirma via directive worker, que
    NÃO roda neste gate — então o pedido é conferido no estado que o commit
    deixa (``new``; ``accepted`` tolerado caso um worker exista no ambiente).
    Pagamento PIX é ``post_commit``: o pedido fecha antes de pagar, e o Pix
    (mock em DEBUG) é um degrau do acompanhamento — nada a pagar aqui.
    """

    def test_11_live_pickup_order_reaches_operator_queue(
        self, playwright, page, store_base_url, operator_base_url, operator_session
    ):
        # Viewport de desktop comum. A altura artificial que existia aqui era
        # contorno para o tremor do ShopHeader (colapsar a status bar mudava a
        # altura da página, o browser corrigia o scroll e a barra oscilava). O
        # header agora tem altura constante no fluxo e desliza com translate, o
        # que tira a realimentação — então o teste volta a rolar como um cliente.
        page.set_viewport_size({"width": 1280, "height": 900})

        # ── Cliente: menu → PDP → sacola ─────────────────────────────
        sku = _seeded_sku(page, store_base_url)
        assert sku, "Seeded menu should expose at least one product SKU"
        page.goto(
            f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle"
        )
        product_name = page.locator("h1").first.inner_text().strip()
        assert product_name, "PDP should name the product"
        page.get_by_role("button", name=ADD_TO_CART).first.click()
        page.wait_for_timeout(600)

        # ── Identificação: o auth-gate do checkout é a PORTA, não o fim ──
        page.goto(f"{store_base_url}{storefront_links.path_checkout()}")
        page.wait_for_url(re.compile(re.escape(storefront_links.path_login())), timeout=15_000)
        _authenticate_via_otp(page)

        # ── Checkout: retirada → quando → pagamento → revisão ────────
        expect(page.locator("[data-checkout-step='fulfillment']")).to_be_visible(
            timeout=15_000
        )
        _ensure_contact_saved(page)
        pickup = page.locator("label[for='checkout-fulfillment-pickup']")
        assert pickup.count(), "Canal web semeado deve oferecer retirada"
        pickup.click()
        _checkout_action(page, "Continuar").click()

        _ensure_pickup_slot_selected(page)
        when_continue = _checkout_action(page, "Continuar")
        expect(when_continue).to_be_enabled(timeout=15_000)
        when_continue.click()

        pix = page.locator("label[for='checkout-payment-pix']")
        if pix.count():
            pix.click()
        _checkout_action(page, "Revisar pedido").click()

        sheet = page.get_by_role("dialog").filter(has_text="Revise seu pedido")
        expect(sheet).to_be_visible(timeout=15_000)
        sheet.get_by_role(
            "button", name=re.compile(r"enviar|confirmar", re.IGNORECASE)
        ).last.click()

        # O commit redireciona para o acompanhamento do pedido recém-criado.
        page.wait_for_url(re.compile(r"/pedido/"), timeout=30_000)
        match = re.search(r"/pedido/([^/?#]+)", page.url)
        assert match, f"URL de acompanhamento sem ref de pedido: {page.url}"
        order_ref = match.group(1)

        # ── Operador: o MESMO pedido na fila do backstage ────────────
        # Contexto de API ISOLADO com o cookie explícito do operador. Não dá
        # para usar o jar do navegador: a página de acompanhamento continua
        # aberta e viva (SSE + fetches), e as respostas dela re-gravam o
        # `sessionid` do CLIENTE no jar entre uma chamada e outra — a segunda
        # chamada sairia com a sessão errada e tomaria 403.
        cookie = operator_session(page.context)
        api = playwright.request.new_context(
            extra_http_headers={"Cookie": f"{cookie['name']}={cookie['value']}"}
        )
        try:
            queue_response = api.get(f"{operator_base_url}{reverse('api-backstage-orders')}")
            assert queue_response.status == 200, (
                f"Fila do operador respondeu {queue_response.status}"
            )
            assert order_ref in json.dumps(queue_response.json()), (
                f"Pedido {order_ref} criado pela loja não apareceu na fila do operador"
            )

            detail_response = api.get(
                f"{operator_base_url}"
                f"{reverse('api-backstage-order-detail', kwargs={'ref': order_ref})}"
            )
            assert detail_response.status == 200, (
                f"Detalhe do pedido respondeu {detail_response.status}"
            )
            order = detail_response.json()["order"]
        finally:
            api.dispose()
        assert order["ref"] == order_ref
        assert order["channel_ref"] == "web"
        assert order["fulfillment_type"] == "pickup"
        # Estado que o COMMIT deixa: `new` (auto-confirmação é do worker, que
        # este gate não sobe). `accepted` tolerado se um worker confirmar antes.
        assert order["status"] in {"new", "accepted"}, (
            f"Pedido nasceu em estado inesperado: {order['status']}"
        )
        item_names = " · ".join(item.get("name", "") for item in order["items"])
        assert product_name in item_names, (
            f"Item da PDP ({product_name!r}) não está no pedido do operador ({item_names!r})"
        )


# ---------------------------------------------------------------------------
# Dia 1: entrega + cartão até o acompanhamento (T13 do laudo de 23/10)
# ---------------------------------------------------------------------------

#: Telefone próprio do Dia 1: o cliente nasce neste teste (ou já existe, em
#: rerun contra o mesmo banco), sem herdar nada do pedido de retirada acima.
DAY_ONE_PHONE = "43991840002"
DAY_ONE_QTY = 4

#: Endereço digitado à mão (o CI não fala com Google Maps nem ViaCEP). O bairro
#: casa com a zona de exceção que o seed já cria ("Bela Suíça", taxa fixa), então
#: a entrega é aceita sem geocodificação. CEP 860xx fica fora da zona excluída
#: (862xx) do mesmo seed.
DAY_ONE_ADDRESS = {
    "#address-route": "Rua Jorge Velho",
    "#address-number": "140",
    "#address-neighborhood": "Bela Suíça",
    "#address-cep": "86050-480",
}


def _wait_cart_mutation(page, click) -> None:
    """Clica e espera a gravação da sacola no servidor (estado, não relógio)."""
    with page.expect_response(
        lambda r: "/api/v1/cart/" in r.url and r.request.method in {"PUT", "POST"},
        timeout=15_000,
    ) as info:
        click()
    assert info.value.ok, f"Sacola recusou a inclusão: {info.value.status}"


def _fill_manual_delivery_address(page) -> None:
    """Passo "Endereço" pelo caminho manual do AddressPicker."""
    step = page.locator("[data-checkout-step='address']")
    expect(step.locator("[data-address-picker]")).to_be_visible(timeout=15_000)
    # Rerun contra o mesmo banco: o endereço do pedido anterior volta salvo. O
    # teste sempre digita um novo, para provar o caminho do cliente de primeira vez.
    new_address = step.locator("[data-address-new]")
    if new_address.count() and new_address.first.is_visible():
        new_address.first.click()
    step.locator("[data-address-manual]").click()
    for selector, value in DAY_ONE_ADDRESS.items():
        field = step.locator(selector)
        expect(field).to_be_visible(timeout=15_000)
        field.fill(value)
    city = step.locator("#address-city")
    if not (city.input_value() or "").strip():
        city.fill("Londrina")
    state = step.locator("#address-state")
    if not (state.inner_text() or "").strip():
        state.click()
        page.get_by_role("option", name="PR", exact=True).click()
        expect(state).to_have_text(re.compile(r"PR"))
    step.locator("[data-address-confirm]").click()


def _select_future_delivery_window(page) -> None:
    """Passo "Quando" da entrega, imune ao relógio de parede.

    As datas rápidas são as datas ABERTAS da loja: ``[hoje, próxima]`` quando
    hoje abre, ou só ``[próxima]`` quando não abre. A ÚLTIMA é sempre um dia
    futuro, com a grade de janelas inteira; hoje, depois do expediente, não tem
    janela nenhuma. O teste escolhe a última e a primeira janela habilitada dela,
    e por isso passa às 8h, às 23h e no domingo.
    """
    when = page.locator("[data-checkout-step='when']")
    dates = when.locator("[role='radio'][id^='checkout-date-']")
    expect(dates.first).to_be_visible(timeout=15_000)
    future = dates.last
    if future.get_attribute("aria-checked") != "true":
        future.click()
    expect(future).to_have_attribute("aria-checked", "true")
    window = when.locator(
        "[data-checkout-delivery-windows] [role='radio'][id^='checkout-window-']"
        ":not([data-disabled]):not([disabled])"
    ).first
    expect(window).to_be_visible(timeout=15_000)
    window.click()
    expect(window).to_have_attribute("aria-checked", "true")


def _day_one_order_facts(django_db_blocker, order_ref: str) -> dict:
    """O que o banco diz do pedido e da cobrança (mesmo banco do servidor vivo)."""
    with django_db_blocker.unblock():
        from shopman.orderman.models import Order
        from shopman.payman import PaymentService

        order = Order.objects.get(ref=order_ref)
        payment = (order.data or {}).get("payment") or {}
        intent = PaymentService.get(payment["intent_ref"]) if payment.get("intent_ref") else None
        return {
            "channel_ref": order.channel_ref,
            "status": order.status,
            "fulfillment_type": (order.data or {}).get("fulfillment_type"),
            "delivery_address": (order.data or {}).get("delivery_address_structured") or {},
            "delivery_time_slot": (order.data or {}).get("delivery_time_slot"),
            "payment_method": payment.get("method"),
            "intent_gateway": getattr(intent, "gateway", None),
            "intent_status": getattr(intent, "status", None),
            "intent_gateway_id": getattr(intent, "gateway_id", "") or "",
        }


class TestDayOneDeliveryCard:
    """O Dia 1 da loja: um cliente novo pede ENTREGA, paga com CARTÃO e acompanha.

    Cadeia inteira, sem atalho: loja Nuxt → BFF → API Django → commit →
    ``payment.initiate`` síncrono (cartão é ``at_commit`` no canal web) →
    ``payment_stripe`` de PRODUÇÃO → Checkout Session → "página do Stripe" →
    webhook ``checkout.session.completed`` assinado → ``PaymentService.authorize``
    → acompanhamento em ``/pedido/<ref>``.

    O Stripe do outro lado da rede é o falso local (``fake_stripe.py``): o CI
    não sai para a rede e não guarda credencial. O que ele NÃO prova está no
    docstring dele e no PR: 3DS, recusa e a página real do Stripe.
    """

    def test_12_delivery_card_order_reaches_tracking(
        self, page, store_base_url, django_db_blocker
    ):
        from .conftest import _in_thread

        fake_stripe_base = os.environ.get("SHOPMAN_E2E_STRIPE_API_BASE", "").strip()
        assert fake_stripe_base, (
            "Defina SHOPMAN_E2E_STRIPE_API_BASE (o run_storefront_e2e.sh sobe o Stripe falso)."
        )
        page.set_viewport_size({"width": 1280, "height": 900})

        # ── Cliente: PDP → sacola ────────────────────────────────────
        sku = _seeded_sku(page, store_base_url)
        assert sku, "Seeded menu should expose at least one product SKU"
        page.goto(
            f"{store_base_url}{storefront_links.path_product(sku)}", wait_until="networkidle"
        )
        add = page.get_by_role("button", name=ADD_TO_CART).first
        _wait_cart_mutation(page, add.click)
        # A entrega tem pedido mínimo (o retirar não). Quatro unidades do primeiro
        # item do cardápio semeado passam dele com folga; cada toque espera a
        # sacola gravar antes do próximo.
        increase = page.locator("[data-quantity-increase]").first
        for _ in range(DAY_ONE_QTY - 1):
            expect(increase).to_be_enabled(timeout=15_000)
            _wait_cart_mutation(page, increase.click)

        # ── Identificação pelo OTP ───────────────────────────────────
        page.goto(f"{store_base_url}{storefront_links.path_checkout()}")
        page.wait_for_url(re.compile(re.escape(storefront_links.path_login())), timeout=15_000)
        _authenticate_via_otp(page, phone=DAY_ONE_PHONE)

        # ── Checkout: entrega → endereço → quando → cartão → revisão ─
        expect(page.locator("[data-checkout-step='fulfillment']")).to_be_visible(
            timeout=15_000
        )
        _ensure_contact_saved(page)
        delivery = page.locator("label[for='checkout-fulfillment-delivery']")
        expect(delivery).to_be_visible(timeout=15_000)
        # Escolher Entrega já avança para o endereço, e confirmar o endereço já
        # avança para "Quando": nenhum dos dois passos pede "Continuar".
        delivery.click()
        _fill_manual_delivery_address(page)

        _select_future_delivery_window(page)
        when_continue = _checkout_action(page, "Continuar")
        expect(when_continue).to_be_enabled(timeout=15_000)
        when_continue.click()

        card = page.locator("label[for='checkout-payment-card']")
        expect(card).to_be_visible(timeout=15_000)
        card.click()
        _checkout_action(page, "Revisar pedido").click()

        sheet = page.get_by_role("dialog").filter(has_text="Revise seu pedido")
        expect(sheet).to_be_visible(timeout=15_000)
        sheet.get_by_role(
            "button", name=re.compile(r"enviar|confirmar", re.IGNORECASE)
        ).last.click()

        # ── Acompanhamento: o pedido nasce e oferece o cartão ────────
        page.wait_for_url(re.compile(r"/pedido/"), timeout=30_000)
        match = re.search(r"/pedido/([^/?#]+)", page.url)
        assert match, f"URL de acompanhamento sem ref de pedido: {page.url}"
        order_ref = match.group(1)

        pay_link = page.get_by_role("link", name="Pagar com cartão")
        expect(pay_link).to_be_visible(timeout=15_000)
        checkout_url = pay_link.get_attribute("href") or ""
        assert checkout_url.startswith(f"{fake_stripe_base}/pay/cs_test_"), (
            f"O link do cartão não é a Checkout Session criada pelo adapter: {checkout_url!r}"
        )

        born = _in_thread(_day_one_order_facts, django_db_blocker, order_ref)
        assert born["channel_ref"] == "web"
        assert born["fulfillment_type"] == "delivery"
        assert born["delivery_address"].get("neighborhood") == DAY_ONE_ADDRESS[
            "#address-neighborhood"
        ]
        assert born["delivery_time_slot"], "Entrega sem janela escolhida"
        assert born["payment_method"] == "card"
        assert born["intent_gateway"] == "stripe"
        assert born["intent_status"] == "pending"
        assert born["intent_gateway_id"].startswith("cs_test_")

        # ── "Página do Stripe": o cliente paga e volta ao acompanhamento ─
        with page.context.expect_page() as stripe_tab_info:
            pay_link.click()
        stripe_tab = stripe_tab_info.value
        expect(stripe_tab.get_by_role("heading", name=re.compile("Checkout de teste"))).to_be_visible(
            timeout=15_000
        )
        stripe_tab.get_by_role("button", name="Pagar").click()
        # O Stripe falso entrega o webhook ANTES do redirect: quando o
        # acompanhamento carrega aqui, a autorização já está gravada.
        stripe_tab.wait_for_url(
            re.compile(re.escape(storefront_links.path_order_tracking(order_ref)) + r"$"),
            timeout=30_000,
        )

        paid = _in_thread(_day_one_order_facts, django_db_blocker, order_ref)
        assert paid["intent_status"] == "authorized", (
            f"Webhook do cartão não autorizou a cobrança: {paid['intent_status']}"
        )
        assert paid["intent_gateway_id"].startswith("pi_test_"), (
            "checkout.session.completed deveria promover o gateway_id ao PaymentIntent"
        )
        # Sem worker de directives neste gate, o pedido segue no estado do commit.
        assert paid["status"] in {"new", "accepted"}, paid["status"]

        # O acompanhamento que o cliente vê depois de pagar não pede o cartão
        # de novo, e a aba original (SSE/poll) chega ao mesmo estado.
        expect(stripe_tab.get_by_text("Pagamento autorizado").first).to_be_visible(
            timeout=15_000
        )
        expect(stripe_tab.get_by_role("link", name="Pagar com cartão")).to_have_count(
            0, timeout=15_000
        )
        expect(page.get_by_role("link", name="Pagar com cartão")).to_have_count(
            0, timeout=30_000
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
