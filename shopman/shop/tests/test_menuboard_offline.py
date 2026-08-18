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

    # E o bloco que os carrega não pode estar cloakeado.
    server_block = html.split('x-show="!hydrated"')[1].split('x-show="hydrated"')[0]
    assert "Baguette de Tradition" in server_block, "a pintura do servidor sumiu"
    assert "x-cloak" not in server_block, "o bloco do servidor voltou para dentro do cloak"


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
