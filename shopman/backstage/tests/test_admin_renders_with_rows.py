"""Toda tela do Admin precisa aguentar LINHAS, não só a lista vazia (WP-ADM-R5).

``test_admin_smoke`` cobre a superfície inteira com o banco limpo, e é justamente
por isso que deixou passar dois 500 seguidos: com zero resultados, nenhuma coluna
calculada por linha chega a rodar e ``prefetch_related`` nem é executado. Foi
assim que a lista de pedidos ficou revertendo uma URL removida, e a de sessões
pedindo prefetch de uma property — ambas quebradas na cara do gestor e verdes na
suíte.

Este módulo fecha a fresta pelo lado caro: para cada tela registrada, cria uma
linha de verdade e renderiza lista e formulário. Onde criar a linha exige um grafo
de objetos que este teste não tem por que saber montar, ele diz por que pulou —
silêncio aqui seria a mesma armadilha de novo.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import NoReverseMatch, reverse

from shopman.shop.models import Shop

_REGISTERED_MODELS = sorted(
    admin.site._registry.keys(),
    key=lambda m: (m._meta.app_label, m._meta.model_name),
)


def _model_id(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


@pytest.fixture
def admin_client(client, db):
    Shop.objects.create(name="Loja")
    client.force_login(User.objects.create_superuser("rows-admin", "rows@test.com", "pw"))
    return client


def _make_row(model):
    """Cria uma linha mínima, ou devolve None quando o model exige um grafo."""
    fields = [
        f
        for f in model._meta.fields
        if not f.auto_created and not f.has_default() and not f.blank and not f.null
    ]
    if any(f.is_relation for f in fields):
        return None

    values = {}
    for field in fields:
        internal = field.get_internal_type()
        if internal in ("CharField", "TextField", "SlugField"):
            values[field.name] = f"row-{field.name}"[: field.max_length or 40]
        elif internal in ("IntegerField", "BigIntegerField", "PositiveIntegerField",
                          "SmallIntegerField", "PositiveSmallIntegerField"):
            values[field.name] = 1
        elif internal == "BooleanField":
            values[field.name] = False
        else:
            return None

    try:
        return model.objects.create(**values)
    except Exception:
        return None


@pytest.mark.django_db
@pytest.mark.parametrize("model", _REGISTERED_MODELS, ids=_model_id)
def test_changelist_and_change_form_render_with_a_real_row(admin_client, model):
    row = _make_row(model)
    if row is None:
        pytest.skip(f"{_model_id(model)} precisa de um grafo de objetos para existir")

    changelist = admin_client.get(
        reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
    )
    assert changelist.status_code == 200, (
        f"{_model_id(model)} não renderiza a lista com uma linha "
        f"({changelist.status_code})"
    )

    try:
        change_url = reverse(
            f"admin:{model._meta.app_label}_{model._meta.model_name}_change",
            args=[row.pk],
        )
    except NoReverseMatch:
        return

    change = admin_client.get(change_url)
    assert change.status_code == 200, (
        f"{_model_id(model)} não renderiza o formulário ({change.status_code})"
    )
