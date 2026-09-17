"""O separador de nome nesta casa é o ponto médio, e o CI lembra no lugar de alguém.

O `__str__` de um modelo é o NOME do objeto no Admin: a coluna da lista, o dropdown de
chave estrangeira, o autocomplete, o breadcrumb "Alterar <str>", a tela de confirmação
de exclusão, o histórico. O `verbose_name` de um app é o rótulo da seção na sidebar do
Unfold. Os dois são texto de tela, e nos dois a casa separa com "·".

Dezoito `__str__` já cumpriam a regra e quinze não — o Produto, o objeto mais visto do
Admin inteiro, dizia "PAO-001 - Pão francês"; o Insumo, com a MESMA forma "SKU + nome",
usava travessão; a conta de fidelidade misturava ":" e "|" na mesma linha. Não era
descuido de uma pessoa: era uma convenção sem trava.

Varredura, não amostra: um modelo novo com hífen espaçado reprova aqui.

⚠️ Hífen COLADO em palavra ("pão-de-queijo", "e-mail", "WO-001", "PAO-001") não é
separador e passa. O que a regra pega é o separador CERCADO DE ESPAÇO.
"""

from __future__ import annotations

import re

import pytest
from django.apps import apps

# " - ", " – ", " — ", " | " dentro de uma string que vira texto de tela.
SEPARATOR = re.compile(r"\s[-–—|]\s")

# Endereço brasileiro é formatação dos Correios, não nome de tela: "Cidade - UF" e
# "Rua, nº - Bairro" ficam como o carteiro lê.
ADDRESS_MODELS = {"shop.Shop"}


def _app_configs():
    """Apps do Shopman com `verbose_name` próprio (os de terceiros não são nossos)."""
    return [
        config
        for config in apps.get_app_configs()
        if (config.module and config.module.__name__.startswith("shopman"))
    ]


@pytest.mark.parametrize("config", _app_configs(), ids=lambda c: c.label)
def test_app_verbose_name_uses_the_middle_dot(config) -> None:
    """A sidebar do Unfold mostra este rótulo; "Fiscal — produtos" virou "Fiscal · produtos"."""
    assert not SEPARATOR.search(str(config.verbose_name)), (
        f"{config.label}: o verbose_name do app separa com hífen, travessão ou barra — "
        f'o separador desta casa é o ponto médio: {config.verbose_name!r}'
    )


def _models_with_own_str():
    """Modelos do Shopman que definem o próprio `__str__` (o do Django não tem separador)."""
    return [
        model
        for model in apps.get_models()
        if model.__module__.startswith("shopman")
        and "__str__" in model.__dict__
        and f"{model._meta.app_label}.{model.__name__}" not in ADDRESS_MODELS
    ]


@pytest.mark.parametrize(
    "model", _models_with_own_str(), ids=lambda m: f"{m._meta.app_label}.{m.__name__}"
)
def test_model_str_source_uses_the_middle_dot(model) -> None:
    """Lê a FONTE do `__str__`: montar uma instância de cada modelo pediria o banco inteiro."""
    import inspect

    source = inspect.getsource(model.__dict__["__str__"])
    # Comentário e docstring são prosa; travessão neles é pontuação, não separador.
    code = re.sub(r"#[^\n]*", "", re.sub(r'"""[\s\S]*?"""', "", source))
    offenders = [line.strip() for line in code.splitlines() if SEPARATOR.search(line)]
    assert offenders == [], (
        f"{model._meta.app_label}.{model.__name__}.__str__ separa com hífen, travessão "
        f"ou barra; o separador desta casa é o ponto médio: {offenders}"
    )
