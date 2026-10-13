"""Campo de etiquetas (taggit) no Admin: mostra os nomes e sobrevive a um save sem mexer.

Bug medido no alpha em 13/10/2026: o "Palavras-chave" do Produto aparecia como
"[<Tag: pao>, <Tag: hamburger>]" e cada save sem tocar no campo gravava esse repr de
volta como etiquetas novas ("[<Tag: pao>", "<Tag: hamburger>]"). A causa era o
``formfield_overrides`` trocar o ``TagWidget`` do taggit por um campo de texto puro do
Unfold, que não sabe formatar a lista de ``Tag``. As Etiquetas do Cliente tinham o
mesmo override e o mesmo defeito.
"""

from __future__ import annotations

import html
import re

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse
from shopman.guestman.models import Customer
from shopman.offerman.models import Product

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(db):
    Shop.objects.create(name="Loja")  # sem Shop, o onboarding redireciona o Admin
    return User.objects.create_superuser("tags-admin", "tags@example.com", "x")


def _input_value(page: str, name: str) -> str:
    tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', page)
    assert tag, f"campo {name} não renderizado"
    value = re.search(r'value="([^"]*)"', tag.group(0))
    return html.unescape(value.group(1)) if value else ""


def _save_without_touching(model, obj, field: str, user) -> list[str]:
    """Faz o que o navegador faz: devolve o valor que a tela mostrou, intocado."""
    request = RequestFactory().get("/")
    request.user = user
    model_admin = admin.site._registry[model]
    form = model_admin.get_form(request, obj)(instance=obj)
    shown = _input_value(str(form[field]), field)
    form_field = form.fields[field]
    cleaned = form_field.clean(shown)
    assert not form_field.has_changed(form[field].initial, shown)
    model._meta.get_field(field).save_form_data(obj, cleaned)
    return sorted(getattr(obj, field).names())


@pytest.mark.parametrize(
    ("model", "field", "make"),
    [
        (Product, "keywords", lambda: Product.objects.create(sku="TRABB", name="Pão de hambúrguer")),
        (Customer, "tags", lambda: Customer.objects.create(ref="CLI-T", first_name="Ana", phone="+5543999990009")),
    ],
    ids=["produto-palavras-chave", "cliente-etiquetas"],
)
def test_campo_de_etiquetas_mostra_os_nomes_e_salvar_sem_mexer_preserva(client, superuser, model, field, make):
    obj = make()
    getattr(obj, field).set(["pao", "hamburger"])

    client.force_login(superuser)
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[obj.pk])
    response = client.get(url)
    assert response.status_code == 200
    page = response.content.decode()
    assert _input_value(page, field) == "hamburger, pao"
    assert "&lt;Tag" not in page and "<Tag:" not in page

    assert _save_without_touching(model, obj, field, superuser) == ["hamburger", "pao"]
    assert _save_without_touching(model, obj, field, superuser) == ["hamburger", "pao"]


@pytest.mark.parametrize(
    ("model", "field", "make"),
    [
        (Product, "keywords", lambda: Product.objects.create(sku="SEMPC", name="Sem palavra-chave")),
        (Customer, "tags", lambda: Customer.objects.create(ref="CLI-V", first_name="Bia", phone="+5543999990008")),
    ],
    ids=["produto-palavras-chave", "cliente-etiquetas"],
)
def test_campo_de_etiquetas_vazio_nao_vira_etiqueta(client, superuser, model, field, make):
    """Sem etiqueta nenhuma, a tela mostrava "[]" e o save criava a etiqueta "[]"."""
    obj = make()
    client.force_login(superuser)
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[obj.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert _input_value(response.content.decode(), field) == ""
    assert _save_without_touching(model, obj, field, superuser) == []
