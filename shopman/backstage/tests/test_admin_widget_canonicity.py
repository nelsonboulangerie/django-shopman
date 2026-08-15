"""Todo campo de todo formulário do Admin desenha com widget do Unfold (WP-ADM-R7).

O gate canônico varre TEMPLATES. Formulário não é template: um
`forms.ChoiceField()` declarado sem `widget=` cai no `<select>` cru do Django e
passa por todos os checks — foi assim que "Como a gaveta abre", no terminal do
PDV, ficou com a cara do Admin de 2010 dentro de uma tela Unfold. Eram 94 campos
assim, espalhados por seis telas, e a única forma de achá-los foi enumerar.

Achar na sorte não escala: quem revisa vê a tela que abriu, não as outras trinta.
Este teste percorre cada ModelAdmin e cada inline registrado, instancia o
formulário e confere o widget de cada campo, um a um.

Duas sutilezas que a auditoria aprendeu, e que o teste precisa manter:

1. **Instanciar o form.** Vários widgets só são trocados no `__init__` (os campos
   de senha do Unfold, por exemplo). Ler `base_fields` acusa falso positivo.
2. **Olhar o template, não só a classe.** O Unfold não substitui o
   `RelatedFieldWidgetWrapper` do Django: ele re-aponta o `template_name` para o
   dele. Classe do Django, desenho do Unfold — canônico.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.forms import widgets as django_widgets
from django.test import RequestFactory

# Widgets que não desenham controle visual: não há o que canonizar neles.
_INVISIBLE = {django_widgets.HiddenInput, django_widgets.MultipleHiddenInput}


def _is_canonical(widget) -> bool:
    if type(widget) in _INVISIBLE:
        return True
    if type(widget).__module__.startswith("unfold"):
        return True
    # O Unfold re-templata alguns widgets do Django em vez de trocar a classe;
    # quem manda no desenho é o template.
    return (getattr(widget, "template_name", "") or "").startswith("unfold/")


def _request():
    request = RequestFactory().get("/admin/")
    request.user = User(username="widget-audit", is_staff=True, is_superuser=True)
    return request


def _forms_of(model, model_admin):
    """O form do ModelAdmin e o de cada inline dele."""
    yield "", model_admin.get_form(_request())
    for inline_cls in model_admin.inlines or []:
        inline = inline_cls(model, admin.site)
        yield f" [inline {inline_cls.__name__}]", inline.get_formset(_request()).form


def _fields_of(form):
    """Campos do form JÁ INSTANCIADO — o `__init__` troca widgets."""
    try:
        return form().fields
    except Exception:
        return form.base_fields


_REGISTERED = sorted(admin.site._registry.items(), key=lambda kv: kv[0]._meta.label)


@pytest.mark.django_db
@pytest.mark.parametrize("pair", _REGISTERED, ids=lambda p: p[0]._meta.label_lower)
def test_every_admin_form_field_uses_an_unfold_widget(pair):
    model, model_admin = pair

    offenders = []
    for origem, form in _forms_of(model, model_admin):
        for name, field in _fields_of(form).items():
            if not _is_canonical(field.widget):
                widget = type(field.widget)
                offenders.append(
                    f"{name}{origem}: {widget.__module__}.{widget.__name__}"
                )

    assert not offenders, (
        f"{model._meta.label} tem campo com widget não canônico — declare "
        f"`widget=UnfoldAdmin...` no campo, ou registre a tela com "
        f"`unfold.admin.ModelAdmin`/`TabularInline`:\n  " + "\n  ".join(offenders)
    )
