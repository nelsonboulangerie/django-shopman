"""A busca global do Admin (⌘K) precisa responder (WP-ADM-R6).

Ela é a única forma de chegar a uma tela sem saber onde ela mora no menu — e
estava morta: dois `search_fields` apontavam para ForeignKey crua
(`operator`, `closed_by`), o Django recusa `icontains` em relação, e o
FieldError derrubava a requisição inteira. Não era a busca daquelas duas telas
que quebrava: era QUALQUER busca, porque o endpoint varre todos os admins numa
requisição só. Na tela isso aparecia como "nenhum resultado" para tudo.

Dois testes, um para cada metade do problema: nenhum `search_fields` pode
apontar para relação (a causa), e a busca precisa devolver 200 achando telas
pelo nome (o efeito).
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import FieldDoesNotExist

from shopman.shop.models import Shop

_REGISTERED = sorted(admin.site._registry.items(), key=lambda kv: kv[0]._meta.label)


def _model_id(pair) -> str:
    return pair[0]._meta.label_lower


@pytest.fixture
def admin_client(client, db):
    Shop.objects.create(name="Loja")
    client.force_login(User.objects.create_superuser("busca", "busca@test.com", "pw"))
    return client


@pytest.mark.parametrize("pair", _REGISTERED, ids=_model_id)
def test_search_fields_never_point_at_a_bare_relation(pair):
    model, model_admin = pair

    offenders = []
    for entry in model_admin.search_fields or ():
        name = entry.lstrip("^=@")
        if "__" in name:
            continue
        try:
            field = model._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if field.is_relation:
            offenders.append(f"{entry} → {field.related_model._meta.label}")

    assert not offenders, (
        f"{model._meta.label}: search_fields aponta para relação, o que levanta "
        f"FieldError e derruba a busca global inteira — atravesse até um campo de "
        f"texto (ex.: 'operator__username'): {offenders}"
    )


@pytest.mark.django_db
def test_global_search_finds_screens_by_name(admin_client):
    response = admin_client.get("/admin/search/", {"s": "entrega", "extended": "1"})

    assert response.status_code == 200
    body = response.content.decode()
    assert "Zonas de entrega" in body, (
        "a busca global não encontrou uma tela cujo nome contém o termo"
    )


@pytest.mark.django_db
def test_global_search_survives_a_term_that_matches_nothing(admin_client):
    response = admin_client.get("/admin/search/", {"s": "zzzznadaaqui", "extended": "1"})

    assert response.status_code == 200
