"""Preço do item da lista em reais, como o preço base do produto (ADM-09).

O produto passou a pedir reais e o item da lista continuava em centavos: na
mesma tela do produto, "15,00" no preço base e "1500" no preço do canal. E o
preenchimento automático copiava ``base_price_q`` (centavos) para o campo do
item: com o campo em reais, R$ 15,00 viraria R$ 1.500,00.
"""

from __future__ import annotations

import pytest
from shopman.offerman.contrib.admin_unfold.admin import (
    ListingItemAdminForm,
    ListingItemInline,
    ProductAdmin,
    ProductListingItemInline,
)
from shopman.offerman.models import Listing, ListingItem, Product

pytestmark = pytest.mark.django_db


def _data(**overrides) -> dict:
    data = {"min_qty": "1", "is_published": "on", "is_sellable": "on"}
    data.update(overrides)
    return data


def test_preco_do_item_e_digitado_em_reais():
    product = Product.objects.create(sku="LST1", name="Pão", base_price_q=1500)
    listing = Listing.objects.create(ref="web", name="Web")
    form = ListingItemAdminForm(data=_data(listing=listing.pk, product=product.pk, price_q="12,50"))
    assert form.is_valid(), form.errors
    assert form.save().price_q == 1250


def test_preco_gravado_aparece_em_reais():
    product = Product.objects.create(sku="LST2", name="Pão", base_price_q=1500)
    listing = Listing.objects.create(ref="web2", name="Web")
    item = ListingItem.objects.create(listing=listing, product=product, price_q=1500)
    form = ListingItemAdminForm(instance=item)
    assert 'value="15,00"' in str(form["price_q"])


def test_na_tela_do_produto_o_preco_do_canal_e_obrigatorio():
    assert ProductListingItemInline.form.base_fields["price_q"].required
    # Classes separadas: o AutofillInlineMixin desliga o ``required`` do campo da
    # lista, e o objeto de campo não pode ser o mesmo da tela do produto.
    assert (
        ProductListingItemInline.form.base_fields["price_q"]
        is not ListingItemInline.form.base_fields["price_q"]
    )


def test_preenchimento_automatico_copia_reais_e_nao_centavos():
    """O destino é em reais: a origem tem de ser ``base_price`` (reais)."""
    assert ListingItemInline.autofill_fields == {"product": {"price_q": "base_price"}}
    assert "base_price" in ProductAdmin.autocomplete_extra_fields
    product = Product(sku="LST3", name="Pão", base_price_q=1500)
    form = ListingItemAdminForm()
    assert form.fields["price_q"].to_python(str(product.base_price)) == 1500
