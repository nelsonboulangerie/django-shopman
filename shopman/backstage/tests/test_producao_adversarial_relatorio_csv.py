"""O CSV do relatório de produção não pode carregar fórmula viva.

O gestor baixa o relatório e abre no Excel/Sheets. Um nome de receita como
``=HYPERLINK("http://evil","clique")`` — ou um usuário de operador começando com
``+``/``-``/``@`` — vira fórmula ATIVA na planilha (injeção de fórmula em CSV): o
clique do gestor dispara o que o dado disser. O nome da receita e o ref do
operador são texto controlado por quem cadastra; a exportação tem de neutralizar
a célula (prefixo ``'``), nunca despejá-la crua.
"""

from __future__ import annotations

import csv
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services.production import export_reports_csv

pytestmark = pytest.mark.django_db

GATILHOS = ("=", "+", "-", "@")
NOME_HOSTIL = '=HYPERLINK("http://evil.example","clique")'


@pytest.fixture
def vitrine(db):
    return Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )[0]


def _finish_uma_fornada(nome_receita, *, output_sku="PAO-CSV", operator="op"):
    receita = Recipe.objects.create(
        ref="rc-csv", name=nome_receita, output_sku=output_sku, batch_size=Decimal("1")
    )
    wo = craft.plan(receita, Decimal("10"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("10"), actor=operator, operator_ref=operator)
    craft.finish(wo, finished=Decimal("10"), actor=operator)
    return receita, wo


def _cells(raw: bytes) -> list[list[str]]:
    text = raw.decode("utf-8-sig")
    return list(csv.reader(text.splitlines()))


def test_history_csv_neutraliza_nome_de_receita_com_formula(vitrine):
    _finish_uma_fornada(NOME_HOSTIL)

    rows = _cells(export_reports_csv("history"))

    # A célula com o nome hostil existe e NÃO começa com gatilho de fórmula.
    hit = [c for row in rows for c in row if "HYPERLINK" in c]
    assert hit, "o nome da receita não apareceu no CSV — cenário inválido"
    for cell in hit:
        assert cell[0] not in GATILHOS, f"célula ainda executa como fórmula: {cell!r}"
        assert cell.startswith("'"), f"célula não foi neutralizada: {cell!r}"


@pytest.mark.parametrize("nome", ['=1+1', '+cmd', '-2+3', '@SUM(A1:A9)'])
def test_history_csv_neutraliza_todos_os_gatilhos(vitrine, nome):
    _finish_uma_fornada(nome, output_sku=f"SKU-{abs(hash(nome)) % 1000}")

    rows = _cells(export_reports_csv("history"))
    perigosas = [
        c for row in rows for c in row
        if c and c[0] in GATILHOS and c not in ("",)
    ]
    # Nenhuma célula pode sair começando com um gatilho de fórmula.
    assert not perigosas, f"células ainda perigosas: {perigosas!r}"


def test_operator_csv_neutraliza_ref_de_operador_hostil(vitrine):
    _finish_uma_fornada("Pão", operator="=cmd|calc")

    rows = _cells(export_reports_csv("operator_productivity"))
    perigosas = [c for row in rows for c in row if c and c[0] in GATILHOS]
    assert not perigosas, f"ref de operador vazou como fórmula: {perigosas!r}"


def test_csv_valido_nao_e_alterado(vitrine):
    """Contraponto: um nome inofensivo continua saindo igual, sem prefixo."""
    _finish_uma_fornada("Pão francês")

    rows = _cells(export_reports_csv("history"))
    nomes = [c for row in rows for c in row if c == "Pão francês"]
    assert nomes, "o nome são foi alterado ou sumiu"


def test_numero_negativo_puro_nao_e_escapado(vitrine):
    """`-10` é o NÚMERO -10 na planilha, não fórmula: escapar sujaria coluna.

    Sem esta distinção, ``_csv_safe`` prefixaria todo inteiro negativo com ``'``
    e o transformaria em texto. Só o que NÃO é número puro (``-2+3``, ``+cmd``)
    é neutralizado.
    """
    from shopman.backstage.services.production import _csv_safe

    # Número puro: intacto.
    assert _csv_safe("-10") == "-10"
    assert _csv_safe("+3") == "+3"
    assert _csv_safe("-1.5") == "-1.5"
    # Não é número: neutralizado.
    assert _csv_safe("-2+3") == "'-2+3"
    assert _csv_safe("+cmd") == "'+cmd"
    assert _csv_safe("=1+1") == "'=1+1"
    assert _csv_safe("@SUM(A1)") == "'@SUM(A1)"
