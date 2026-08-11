"""Fonte única de URL da loja Nuxt — caminhos canônicos + cutover por 1 knob.

PAYMENT-TRACKING-MERGE: não há mais rota /pagamento — o pagamento é um degrau do
próprio acompanhamento, então ``path_order_payment``/``order_payment_url`` sumiram.
"""
from shopman.shop.services import storefront_links as sl


def test_paths_are_nuxt_canonical():
    """⚠️ Os caminhos REAIS das páginas, não os que só funcionam via 301.

    Eram os em inglês, e todo link do Django (acompanhamento, pagamento, magic link) dava
    um salto extra até a página de verdade. Se algum voltar a divergir de
    `surfaces/storefront-nuxt/app/pages/`, este teste quebra antes do cliente descobrir.
    """
    assert sl.path_home() == "/"
    assert sl.path_menu() == "/menu"
    assert sl.path_product("BAGUETE") == "/produto/BAGUETE"
    assert sl.path_cart() == "/sacola"
    assert sl.path_checkout() == "/finalizar"
    assert sl.path_order_tracking("ORD-001") == "/pedido/ORD-001"
    assert sl.path_account() == "/conta"
    assert sl.path_login() == "/entrar"
    assert sl.path_order_history() == "/conta/pedidos"


def test_absolute_urls_use_base(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com"
    assert sl.order_tracking_url("ORD-1") == "https://nelson.com/pedido/ORD-1"
    assert sl.product_url("BAGUETE") == "https://nelson.com/produto/BAGUETE"
    assert sl.home_url() == "https://nelson.com/"


def test_base_trailing_slash_is_normalized(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com/"
    assert sl.storefront_base_url() == "https://nelson.com"
    assert sl.order_tracking_url("X") == "https://nelson.com/pedido/X"


def test_empty_base_returns_relative_path(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = ""
    assert sl.order_tracking_url("X") == "/pedido/X"
    assert sl.home_url() == "/"


def test_domain_cutover_is_a_single_knob(settings):
    # Trocar a base reaponta TODOS os links de cliente de uma vez (staging → prod).
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://staging.example/thing"
    assert sl.order_tracking_url("R") == "https://staging.example/thing/pedido/R"
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com"
    assert sl.order_tracking_url("R") == "https://nelson.com/pedido/R"
