"""Contrato da curadoria do Admin (WP-ADM-R1).

A curadoria é uma lista escrita à mão, e lista escrita à mão apodrece: o model
muda de app, o nome muda no plural, alguém corrige um typo no lugar errado. Aí a
entrada para de bater com qualquer model, o `unregister` vira no-op e a tela que
deveria ter sumido volta a aparecer — sem que nada reclame. Estes testes fecham
essa porta pelos dois lados: cada entrada precisa apontar para um model real, e
cada model apontado precisa estar mesmo fora do Admin.
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.contrib import admin

from shopman.backstage.admin.curation import HIDDEN_SCREENS


def _ids(entry):
    return f"{entry[0]}.{entry[1]}"


@pytest.mark.parametrize("entry", HIDDEN_SCREENS, ids=_ids)
def test_curated_entry_points_at_a_real_model(entry):
    app_label, model_name, reason = entry

    try:
        apps.get_model(app_label, model_name)
    except LookupError:
        pytest.fail(
            f"curadoria aponta para {app_label}.{model_name}, que não existe — "
            "corrija ou remova a entrada"
        )

    assert reason.strip(), f"{app_label}.{model_name} foi escondido sem motivo escrito"


@pytest.mark.parametrize("entry", HIDDEN_SCREENS, ids=_ids)
def test_curated_screen_is_absent_from_the_admin(entry):
    app_label, model_name, _reason = entry
    model = apps.get_model(app_label, model_name)

    assert model not in admin.site._registry, (
        f"{app_label}.{model_name} está na curadoria mas continua registrado — "
        "algum app registrou depois do backstage"
    )


def test_curation_has_no_duplicate_entries():
    seen = [(app, model) for app, model, _ in HIDDEN_SCREENS]

    assert len(seen) == len(set(seen)), "há entradas repetidas na curadoria"
