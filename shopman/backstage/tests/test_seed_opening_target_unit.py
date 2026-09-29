"""O saldo de abertura de insumo fala na unidade de CADA insumo.

A base da casa virou o grama em 24/09/2026 (ADR-024, emenda), e o piso de
despensa foi para 5000 g. Num ensaio contra a cópia do alpha, esse piso caiu
também sobre a revenda contada em unidade — 5000 potes de cada geleia da
Mercearia — e sobre um órfão em litro. O piso é da unidade do insumo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.buyman.models import Material

from config.management.commands.seed import material_opening_targets

pytestmark = pytest.mark.django_db


def test_revenda_contada_em_unidade_nao_recebe_piso_em_grama():
    Material.objects.create(sku="GELEIA-TESTE-284", name="Geleia", unit="un", shelf_life_days=365)
    Material.objects.create(sku="FARINHA-TESTE", name="Farinha", unit="g", shelf_life_days=180)

    alvos = material_opening_targets()

    assert alvos["GELEIA-TESTE-284"] == Decimal("5")
    assert alvos["FARINHA-TESTE"] == Decimal("5000")
