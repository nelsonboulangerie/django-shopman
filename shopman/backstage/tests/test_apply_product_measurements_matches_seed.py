"""A tabela do `apply_product_measurements` não pode divergir do seed.

O comando carrega uma cópia de peso, medida e rendimento para poder aplicá-los
num banco que já roda, onde o `seed` seria destrutivo. Cópia diverge sozinha: um
ajusta o peso no seed, ninguém lembra do comando, e o comando passa a reescrever
o catálogo com o valor velho — pior que não existir, porque parece que funcionou.

Este teste é a corda entre os dois. Roda o seed do zero e confere valor a valor.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.offerman.models import Product

from shopman.shop.management.commands.apply_product_measurements import MEASUREMENTS

pytestmark = pytest.mark.django_db


def test_a_tabela_do_comando_bate_com_o_catalogo_semeado(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Measurements-2026!")
    call_command("seed", verbosity=0)

    produtos = {p.sku: p for p in Product.objects.filter(sku__in=MEASUREMENTS)}
    faltando = sorted(set(MEASUREMENTS) - set(produtos))
    assert not faltando, f"SKU na tabela do comando que o seed não cria: {faltando}"

    divergencias = []
    for sku, desejado in sorted(MEASUREMENTS.items()):
        produto = produtos[sku]
        metadata = produto.metadata if isinstance(produto.metadata, dict) else {}
        atual = {
            "unit_weight_g": produto.unit_weight_g,
            "serves": metadata.get("serves"),
            "approx_dimensions": metadata.get("approx_dimensions"),
        }
        for campo, esperado in desejado.items():
            if atual[campo] != esperado:
                divergencias.append(f"{sku}.{campo}: seed={atual[campo]!r} comando={esperado!r}")

    assert not divergencias, (
        "A tabela de `apply_product_measurements` divergiu do seed. Mexeu num, "
        "mexa no outro:\n  " + "\n  ".join(divergencias)
    )


def test_o_comando_nao_muda_nada_num_banco_recem_semeado(monkeypatch, capsys):
    """Depois do seed, aplicar a tabela é no-op — é a mesma verdade nos dois lugares."""
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Measurements-2026!")
    call_command("seed", verbosity=0)

    call_command("apply_product_measurements", "--apply")
    saida = capsys.readouterr().out

    assert "Nada a fazer" in saida
