"""Máscara não é nome.

Medido no alpha em 19/09/2026: o iFood entrega ``customer_name`` como
``"********************************"`` — 32 asteriscos, não um campo vazio. O card
imprimia isso na linha do cliente, onde parece defeito de renderização e ocupa o
lugar do dado que decide. O operador precisa saber que não há nome para chamar, e
de quem é a decisão de ocultar.
"""
import pytest

from shopman.backstage.projections.order_queue import _format_customer_display


@pytest.mark.parametrize("mascara", [
    "*" * 32,
    "****",
    "••••••",
    "· · · ·",
    "…",
])
def test_mascara_nao_vira_nome_na_tela(mascara):
    assert _format_customer_display(mascara) == "Nome oculto pelo iFood"


@pytest.mark.parametrize("nome", [
    "Marina Alencar",
    "Marina A.",          # o iFood às vezes abrevia — continua sendo nome
    "Jean-Luc",
    "Ana",
    "D'Ávila",
])
def test_nome_de_verdade_continua_passando(nome):
    assert _format_customer_display(nome) == nome


def test_campo_vazio_continua_vazio():
    """Vazio e mascarado são coisas diferentes: um é ausência, o outro é recusa."""
    assert _format_customer_display("") == ""
    assert _format_customer_display("   ") == ""


def test_nome_com_asterisco_no_meio_nao_e_mascara():
    """Só é máscara o que é feito SÓ de máscara — um nome com adorno segue nome."""
    assert _format_customer_display("Ana*") == "Ana*"


def test_telefone_nao_e_confundido_com_mascara():
    """O formatador também recebe telefone quando não há nome; não pode regredir."""
    assert _format_customer_display("+5543999990000") != "Nome oculto pelo iFood"
