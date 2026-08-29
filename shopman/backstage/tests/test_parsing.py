"""O parser canônico de entrada: o que passa, o que vira 400, e por quê.

A régua é a da casa — falhar fechado, ou falhar gritando; nunca falhar aberto e
calado. O caso que motivou o módulo é ``bool("false")``, que em Python é ``True``.
"""

from __future__ import annotations

import pytest
from rest_framework.exceptions import ValidationError

from shopman.backstage.parsing import as_bool, as_int

# ── as_bool ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (True, True), (False, False),          # o booleano JSON que as superfícies mandam
        ("true", True), ("false", False),      # ⬅ o bug: `bool("false")` era True
        ("TRUE", True), (" False ", False),    # caixa e espaço não importam
        ("1", True), ("0", False),
        ("yes", True), ("no", False),
        ("on", True), ("off", False),
        (1, True), (0, False),
    ],
)
def test_as_bool_aceita_o_que_e_inequivoco(valor, esperado) -> None:
    assert as_bool({"x": valor}, "x") is esperado


def test_o_caso_que_motivou_o_modulo() -> None:
    """`bool("false")` é True em Python — e o item da cozinha desmarcava marcando."""
    assert bool("false") is True          # o comportamento antigo, para o teste doer
    assert as_bool({"x": "false"}, "x") is False


@pytest.mark.parametrize("valor", ["talvez", "sim!", "2", 2, -1, 1.5, [], {}, "verdadeiro"])
def test_as_bool_recusa_o_ambiguo_em_vez_de_adivinhar(valor) -> None:
    with pytest.raises(ValidationError) as recusa:
        as_bool({"x": valor}, "x")
    # `field` nomeado é o que deixa a tela focar o campo certo.
    assert "x" in recusa.value.detail


@pytest.mark.parametrize("data", [{}, {"x": None}])
def test_ausencia_e_null_sao_400_quando_nao_ha_default(data) -> None:
    """Campo obrigatório que chega vazio é pergunta sem resposta, não resposta negativa."""
    with pytest.raises(ValidationError):
        as_bool(data, "x")


@pytest.mark.parametrize("data", [{}, {"x": None}])
def test_o_default_do_call_site_vale_para_ausencia_e_para_null(data) -> None:
    assert as_bool(data, "x", default=False) is False
    assert as_bool(data, "x", default=True) is True


def test_mensagem_da_casa_vence_a_generica() -> None:
    with pytest.raises(ValidationError) as recusa:
        as_bool({"x": "talvez"}, "x", message="Marque sim ou não para continuar.")
    assert recusa.value.detail["x"][0] == "Marque sim ou não para continuar."


# ── as_int ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("valor", "esperado"), [(42, 42), ("42", 42), (" 7 ", 7), (0, 0), (-3, -3)])
def test_as_int_aceita_inteiro_e_string_de_inteiro(valor, esperado) -> None:
    assert as_int({"x": valor}, "x") == esperado


@pytest.mark.parametrize("valor", ["abc", "4.5", 1.5, [], {}, "12a"])
def test_as_int_recusa_lixo_em_vez_de_devolver_none(valor) -> None:
    """O `_as_int` antigo devolvia None, e o None seguia viagem sem 400."""
    with pytest.raises(ValidationError):
        as_int({"x": valor}, "x")


@pytest.mark.parametrize("valor", [True, False])
def test_booleano_nao_vale_como_inteiro(valor) -> None:
    """`int(True)` é 1 em Python — aceitar deixaria um booleano trocado passar."""
    with pytest.raises(ValidationError):
        as_int({"x": valor}, "x")


@pytest.mark.parametrize("data", [{}, {"x": None}, {"x": ""}, {"x": "   "}])
def test_as_int_trata_vazio_como_ausencia(data) -> None:
    with pytest.raises(ValidationError):
        as_int(data, "x")
    assert as_int(data, "x", default=None) is None


def test_a_faixa_e_conferida_no_mesmo_lugar_da_conversao() -> None:
    """Para o call site não repetir a checagem — e não esquecer dela."""
    assert as_int({"x": 5}, "x", min_value=0, max_value=10) == 5
    with pytest.raises(ValidationError):
        as_int({"x": -1}, "x", min_value=0)
    with pytest.raises(ValidationError):
        as_int({"x": 11}, "x", max_value=10)


def test_default_fora_da_faixa_reprova_no_teste_e_nao_na_producao() -> None:
    """Default fora da faixa é bug de quem chamou; passa pela mesma conferência."""
    with pytest.raises(ValidationError):
        as_int({}, "x", default=-5, min_value=0)
