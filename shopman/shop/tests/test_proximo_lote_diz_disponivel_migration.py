"""``shop.0140``: o texto do próximo lote gravado no Admin passa a "Disponível {when}" (dono, 24/11/2026)."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps

from shopman.shop.models import OmotenashiCopy
from shopman.shop.omotenashi.copy import WILDCARD

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0140_proximo_lote_diz_disponivel")


def test_o_texto_gravado_vira_o_novo_mesmo_editado():
    row = OmotenashiCopy.objects.create(
        key="KINTSUGI_PLANNED_OFFER", moment=WILDCARD, audience=WILDCARD,
        title="Já vem quentinho", message="Fica pronto no próximo lote, fresquinho. Quer garantir o seu?",
    )
    edited = OmotenashiCopy.objects.create(
        key="KINTSUGI_PLANNED_OFFER", moment="manha", audience=WILDCARD,
        title="Fornada nova chegando", message="Garanta o seu.",
    )
    other = OmotenashiCopy.objects.create(
        key="KINTSUGI_SHORTAGE_GENERIC", moment=WILDCARD, audience=WILDCARD, title="Ficou indisponível.",
    )

    migration.forwards(apps, None)

    for current in (row, edited):
        current.refresh_from_db()
        assert (current.title, current.message) == ("Disponível {when}", "")
    other.refresh_from_db()
    assert other.title == "Ficou indisponível."
