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
import re
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


def _authenticate_via_debug_otp(page) -> None:
    """Entra pela UI de /entrar usando o código OTP de teste.

    Em DEBUG o backend devolve ``debug_otp_code`` no request-code e a tela
    renderiza o alerta "Ambiente de teste" com o botão "Usar código de teste"
    (que preenche os 6 dígitos; o watcher confirma sozinho). É o MESMO caminho
    que um cliente real percorre — só a leitura do SMS é substituída pelo
    código exposto na própria tela.
    """
    expect(page.get_by_role("button", name="Usar outro número")).to_be_visible()
    page.get_by_role("button", name="Usar outro número").click()
    page.locator("#login-phone").fill(LIVE_ORDER_PHONE)
    page.locator("form:has(#login-phone) button[type='submit']").click()

    debug_alert = page.locator("[data-testid='debug-otp-alert']")
    expect(debug_alert, (
        "O alerta do OTP de teste não apareceu — o gate exige DJANGO_DEBUG=true "
        "(o request-code só devolve debug_otp_code com o debug OTP exposto)."
    )).to_be_visible(timeout=15_000)
    page.get_by_role("button", name="Usar código de teste").click()

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


def _ensure_contact_saved(page) -> None:
    """Se o cartão de contato abriu em edição (cliente sem nome), completa-o."""
    name_input = page.locator("#checkout-name")
    if name_input.count() and name_input.first.is_visible():
        if not (name_input.first.input_value() or "").strip():
            name_input.first.fill(LIVE_ORDER_NAME)
        page.get_by_role("button", name="Salvar contato").click()


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
        # Viewport alto o bastante para o checkout inteiro caber sem rolagem.
        # Não é cosmético: a status bar do ShopHeader colapsa com `scrollY > 8`
        # animando `max-height` — quando um clique deixa a rolagem exatamente no
        # limiar, colapsar muda a altura da página, o scroll volta, a barra
        # reexpande… um laço de reflow que balança a página ~1px para sempre e
        # reprova o teste de estabilidade do Playwright. Com tudo em vista,
        # `scrollY` fica em 0 e o laço nunca arma.
        page.set_viewport_size({"width": 1280, "height": 3200})

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
        _authenticate_via_debug_otp(page)

        # ── Checkout: retirada → quando → pagamento → revisão ────────
        expect(page.locator("[data-checkout-step='fulfillment']")).to_be_visible(
            timeout=15_000
        )
        _ensure_contact_saved(page)
        pickup = page.locator("label[for='checkout-fulfillment-pickup']")
        assert pickup.count(), "Canal web semeado deve oferecer retirada"
        pickup.click()
        page.locator("[data-checkout-step='fulfillment']").get_by_role(
            "button", name="Continuar"
        ).click()

        _ensure_pickup_slot_selected(page)
        when_continue = page.locator("[data-checkout-step='when']").get_by_role(
            "button", name="Continuar"
        )
        expect(when_continue).to_be_enabled(timeout=15_000)
        when_continue.click()

        pix = page.locator("label[for='checkout-payment-pix']")
        if pix.count():
            pix.click()
        page.locator("[data-checkout-step='payment']").get_by_role(
            "button", name="Revisar pedido"
        ).click()

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
