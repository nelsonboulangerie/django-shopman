"""Todo rótulo do Admin foi ESCRITO por alguém, não gerado pelo Django (WP-ADM-R9).

Quando um campo de model não declara `verbose_name`, o Django inventa um rótulo a
partir do nome do atributo: `opening_amount_q` vira "Opening amount q", `order_ref`
vira "Order ref". O resultado é inglês na tela de um Admin que é todo em português
— e pior, com o sufixo interno `_q` (centavos) vazando para o dono da padaria.

Não era um punhado de casos: a tela de Cobranças inteira, os turnos de caixa
inteiros, os avisos de reposição. 43 campos. E o mesmo vale para `forms.Field`
declarado sem `label=` — foi assim que "Cancellation presets" apareceu numa tela de
configuração em português.

Este teste não tenta adivinhar idioma. Ele exige o que dá para verificar sem
ambiguidade: que o rótulo tenha sido escrito, e não derivado do nome do atributo.
Rótulo escrito em inglês passaria aqui — mas ninguém escreve em inglês por
acidente; escrever é o momento em que se pensa no idioma. O que acontecia por
acidente era o Django gerar.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory

#: Apps de terceiros: o rótulo é deles, e não se corrige daqui.
_THIRD_PARTY = ("django.contrib.", "django_otp", "taggit")

#: Palavras cujo rótulo automático já é português: escrever "ref" como
#: `verbose_name="ref"` não muda pixel nenhum e só adiciona ruído ao model. A
#: lista é curta de propósito — cada item aqui é uma palavra que o dono da padaria
#: lê igual nos dois idiomas, não uma desculpa para deixar inglês passar.
_JA_E_PORTUGUES = {
    "id", "uuid", "ref", "sku", "status", "email", "gateway",
    "latitude", "longitude",
}


def _auto_generated(verbose_name: str, attname: str) -> bool:
    """O Django deriva o rótulo trocando `_` por espaço quando ninguém declara."""
    return str(verbose_name) == attname.replace("_", " ")


def _visible_fields(model_admin, request):
    """Campos que aparecem no formulário — os que a pessoa realmente lê."""
    try:
        form = model_admin.get_form(request)
    except Exception:
        return
    yield from getattr(form, "base_fields", {}).items()


def _request():
    request = RequestFactory().get("/admin/")
    request.user = User(username="labels", is_staff=True, is_superuser=True)
    return request


_REGISTERED = [
    (model, model_admin)
    for model, model_admin in sorted(
        admin.site._registry.items(), key=lambda kv: kv[0]._meta.label
    )
    if not model.__module__.startswith(_THIRD_PARTY)
]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pair", _REGISTERED, ids=lambda p: p[0]._meta.label_lower
)
def test_model_fields_declare_their_own_label(pair):
    model, _model_admin = pair

    offenders = [
        f"{field.name} → «{field.verbose_name}»"
        for field in model._meta.fields
        if _auto_generated(field.verbose_name, field.name)
        and str(field.verbose_name) not in _JA_E_PORTUGUES
    ]

    assert not offenders, (
        f"{model._meta.label}: campo sem verbose_name — o Django gera o rótulo do "
        f"nome do atributo, em inglês e com sufixo interno à mostra:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pair", _REGISTERED, ids=lambda p: p[0]._meta.label_lower
)
def test_declared_form_fields_declare_their_own_label(pair):
    model, model_admin = pair
    model_field_names = {f.name for f in model._meta.get_fields()}

    offenders = [
        name
        for name, field in _visible_fields(model_admin, _request()) or []
        # Campo que vem do model já herda o verbose_name (coberto pelo teste acima).
        if name not in model_field_names and field.label is None
    ]

    assert not offenders, (
        f"{model._meta.label}: forms.Field declarado sem label= — o Django gera o "
        f"rótulo do nome do campo, em inglês (foi assim que apareceu "
        f"«Cancellation presets»): {offenders}"
    )
