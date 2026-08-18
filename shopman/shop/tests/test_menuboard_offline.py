"""A TV desenha sem JS? O teste que a tela em branco exigiu."""
import pytest
from django.test import Client


@pytest.mark.django_db
def test_menuboard_paints_without_javascript(settings, monkeypatch):
    """Sem Alpine, o cardápio precisa estar no HTML — e visível.

    O defeito real: tudo vivia dentro de `x-cloak`, então um CDN fora do ar
    deixava a TV da loja em branco com o servidor saudável e o cardápio já
    embutido na página. Este teste falha se alguém devolver o quadro para
    dentro do cloak.
    """
    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    from shopman.offerman.models import Collection, CollectionItem, Product

    from shopman.shop.models import Channel

    col = Collection.objects.create(ref="rusticos", name="Rústicos")
    product = Product.objects.create(sku="BAGUETE", name="Baguette de Tradition",
                                     base_price_q=1600, is_published=True, is_sellable=True)
    CollectionItem.objects.create(collection=col, product=product)
    Channel.objects.create(
        ref="tv-salao", name="TV do Salão",
        commerce_policy=Channel.CommercePolicy.DISPLAY, is_active=True,
        config={"display": {"format": "", "collections": ["rusticos"],
                            "prices_from": "pdv", "paused_skus": []}},
    )

    html = Client().get("/menuboard/tv-salao/").content.decode()

    # O nome e o preço saem do SERVIDOR, não de um x-for.
    assert "Baguette de Tradition" in html
    assert "R$ 16,00" in html

    # E o bloco que os carrega não pode ter NENHUMA diretiva do Alpine.
    server_block = html.split('id="menuboard-server"')[1].split('id="menuboard-root"')[0]
    assert "Baguette de Tradition" in server_block, "a pintura do servidor sumiu"
    for diretiva in ("x-cloak", "x-show", "x-text", "x-for", "x-data"):
        assert diretiva not in server_block, (
            f"o bloco do servidor voltou a depender do Alpine ({diretiva}). "
            "Expressão do Alpine que falha é tratada como FALSA, então isso "
            "esconde o cardápio justamente quando o Alpine está quebrado."
        )


@pytest.mark.django_db
def test_menuboard_has_no_inline_script(settings):
    """O CSP de produção bloqueia script inline — e bloqueava o nosso.

    `'unsafe-inline'` só entra no script-src em DEBUG. Em produção, o `<script>`
    que definia `menuboard()` era barrado: o Alpine carregava, não achava a
    função, e cada expressão dele falhava — apagando o texto que o servidor
    havia renderizado. Sobrava um ponto na tela.

    Bloco `type="application/json"` é DADO, não código, e passa.
    """
    import re

    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    from shopman.shop.models import Channel

    Channel.objects.create(
        ref="tv-salao", name="TV do Salão",
        commerce_policy=Channel.CommercePolicy.DISPLAY, is_active=True,
        config={"display": {"format": "", "collections": [], "prices_from": "pdv",
                            "paused_skus": []}},
    )
    html = Client().get("/menuboard/tv-salao/").content.decode()

    executaveis = [
        tag for tag in re.findall(r"<script[^>]*>", html)
        if "src=" not in tag and 'type="application/json"' not in tag
    ]
    assert not executaveis, f"script inline executável (o CSP barra): {executaveis}"


def test_no_django_template_loads_javascript_from_a_cdn():
    """Kiosk não pode depender de rede externa para desenhar.

    A TV da loja e a prévia do DANFE carregavam o Alpine do unpkg.com. Vale para
    qualquer template daqui pra frente, não só para esses dois.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "shopman"
    offenders = [
        f"{path.relative_to(root)}:{i}"
        for path in root.rglob("*.html")
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "<script" in line and ("unpkg.com" in line or "cdn.jsdelivr" in line or "cdnjs." in line)
    ]
    assert not offenders, "script de CDN em template Django: " + ", ".join(offenders)
