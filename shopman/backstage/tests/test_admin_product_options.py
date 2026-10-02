"""A aba "Escolhas" compõe por cima do Admin de Produto (fiscal e social ficam).

O cadastro salva em ``metadata["option_groups"]`` validado, relê no form, e a
tela mostra o insumo pelo nome e unidade. O rótulo do Cartão de escolha vai em
``metadata["choice_group_label"]``.
"""

from __future__ import annotations

import json

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db

GROUPS = [{
    "ref": "adicionais", "label": "Adicionais", "min": 0, "max": 1,
    "options": [{"ref": "ovo-frito", "label": "Ovo frito", "price_q": 400,
                 "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]}],
}]


def _request():
    request = RequestFactory().get("/admin/offerman/product/1/change/")
    request.user = User(is_superuser=True, is_staff=True)
    return request


def _form_data(product, **extra):
    return {
        "sku": product.sku, "name": product.name, "unit": product.unit,
        "base_price_q": product.base_price_q, "availability_policy": product.availability_policy,
        "is_published": "on", "is_sellable": "on", "social_condition": "new",
        **extra,
    }


def test_the_tab_stacks_on_top_of_fiscal_and_social():
    model_admin = admin.site._registry[Product]
    labels = [str(label) for label, _ in model_admin.get_fieldsets(_request())]
    assert "Escolhas" in labels
    assert "Redes sociais" in labels
    assert "Fiscal (NFC-e)" in labels
    options = next(opts for label, opts in model_admin.get_fieldsets(_request()) if str(label) == "Escolhas")
    assert "tab" in options["classes"]
    assert "option_groups_display" in model_admin.get_readonly_fields(_request())


def test_the_tab_saves_validated_and_reads_back_with_the_ingredient_name():
    from shopman.buyman.models import Material

    Material.objects.create(sku="OVOS", name="Ovos", unit="g")
    product = Product.objects.create(sku="CQMO", name="Croque Monsieur", base_price_q=2400)
    model_admin = admin.site._registry[Product]
    Form = model_admin.get_form(_request(), product)

    form = Form(
        data=_form_data(product, option_groups_json=json.dumps(GROUPS), choice_group_label="  Sabor "),
        instance=product,
    )
    assert form.is_valid(), form.errors
    saved = form.save()

    assert saved.metadata["option_groups"][0]["options"][0]["consumes"] == [{"sku": "OVOS", "qty": "50", "unit": "g"}]
    assert saved.metadata["option_groups"][0]["options"][0]["available"] is True
    assert saved.metadata["choice_group_label"] == "Sabor"

    reread = Form(instance=saved)
    assert json.loads(reread.fields["option_groups_json"].initial) == saved.metadata["option_groups"]
    assert reread.fields["choice_group_label"].initial == "Sabor"
    shown = model_admin.option_groups_display(saved)
    assert "Ovo frito: + R$ 4,00; gasta Ovos (OVOS) 50 g" in shown

    # Vazio apaga as duas chaves.
    form = Form(data=_form_data(saved, option_groups_json="", choice_group_label=""), instance=saved)
    assert form.is_valid(), form.errors
    cleared = form.save()
    assert "option_groups" not in cleared.metadata
    assert "choice_group_label" not in cleared.metadata


def test_the_tab_refuses_an_ingredient_that_does_not_exist_and_bad_json():
    product = Product.objects.create(sku="CQMO", name="Croque Monsieur", base_price_q=2400)
    Form = admin.site._registry[Product].get_form(_request(), product)

    form = Form(data=_form_data(product, option_groups_json=json.dumps(GROUPS)), instance=product)
    assert not form.is_valid()
    assert any("OVOS não existe" in error for error in form.errors["option_groups_json"])

    form = Form(data=_form_data(product, option_groups_json="[{"), instance=product)
    assert not form.is_valid()
    assert "JSON inválido" in form.errors["option_groups_json"][0]
