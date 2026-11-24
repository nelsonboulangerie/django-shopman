"""Marcar no cadastro do cliente "É da equipe: <operador>" (decisão do dono, 24/11/2026).

O operador e o cliente são contas diferentes: o operador é um ``User`` com grupos e
PIN, e a pessoa, quando compra na loja, entra pelo telefone e vira outra conta. A
ponte entre as duas é declarada uma vez, aqui, e mora em
``Customer.metadata["team_operator_id"]`` (sem migração; schema em
``docs/reference/data-schemas.md``). Quem lê é
``shopman.shop.services.experience.operator_customer_refs``: a coorte interna dos
experimentos de versão da loja passa a ser "clientes marcados cujo operador está
ativo", e desligar o operador tira a pessoa da coorte sem editar o cliente.

A base é o Admin de Cliente que o Guestman REGISTROU, lido do site no ``ready()`` do
backstage e não importado: o orquestrador compõe por cima do que o Core pôs no
Admin, sem tocar o ``guestman`` (mesmo caminho de ``product_enrichment``).
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from unfold.widgets import UnfoldAdminSelectWidget

from shopman.shop.services.experience import TEAM_OPERATOR_KEY, team_operators

FIELD = "team_operator"
FIELDSET_TITLE = "Equipe"


def _operator_label(user, active_ids: set[int]) -> str:
    name = (user.get_full_name() or "").strip()
    label = f"{name} ({user.get_username()})" if name else user.get_username()
    if user.pk not in active_ids:
        return f"{label}, desligado"
    return label


def _linked_id(metadata) -> int | None:
    value = (metadata or {}).get(TEAM_OPERATOR_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def build_team_form(base_form: type[forms.ModelForm]) -> type[forms.ModelForm]:
    """O form do cliente com o campo "É da equipe" por cima do form do Guestman."""
    from django.contrib.auth import get_user_model

    class CustomerTeamForm(base_form):
        team_operator = forms.ModelChoiceField(
            label="É da equipe",
            queryset=get_user_model().objects.none(),
            required=False,
            empty_label="Não é da equipe",
            widget=UnfoldAdminSelectWidget,
            help_text=(
                "Escolha o operador quando este cliente for alguém da equipe. Enquanto o "
                "operador estiver ativo, esta conta vê a versão em teste da loja. "
                "Desligado o operador, ela volta sozinha à versão de todos."
            ),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            linked = _linked_id(getattr(self.instance, "metadata", None))
            operators = team_operators()
            active_ids = set(operators.values_list("pk", flat=True))
            User = get_user_model()
            queryset = User.objects.filter(pk__in=operators.values("pk"))
            if linked is not None:
                # O operador desligado continua na lista enquanto estiver marcado:
                # sem isso, salvar qualquer outro campo apagaria a marca calado.
                queryset = queryset | User.objects.filter(pk=linked)
            field = self.fields[FIELD]
            field.queryset = queryset.distinct().order_by("first_name", "username")
            field.label_from_instance = lambda user: _operator_label(user, active_ids)
            field.initial = linked

        def save(self, commit=True):
            customer = super().save(commit=False)
            metadata = dict(customer.metadata or {})
            operator = self.cleaned_data.get(FIELD)
            if operator is not None:
                metadata[TEAM_OPERATOR_KEY] = operator.pk
            else:
                metadata.pop(TEAM_OPERATOR_KEY, None)
            customer.metadata = metadata
            if commit:
                customer.save()
                self.save_m2m()
            return customer

    CustomerTeamForm.__name__ = base_form.__name__
    CustomerTeamForm.__qualname__ = base_form.__qualname__
    return CustomerTeamForm


def _with_team_fieldset(fieldsets) -> list:
    fieldsets = list(fieldsets or [])
    team = (FIELDSET_TITLE, {"fields": [FIELD]})
    titles = [title for title, _options in fieldsets]
    # Logo depois da Segmentação, antes do bloco Sistema (recolhido).
    index = titles.index("Segmentação") + 1 if "Segmentação" in titles else len(fieldsets)
    fieldsets.insert(index, team)
    return fieldsets


def install_customer_team_link() -> None:
    """Compõe o campo "É da equipe" sobre o Admin de Cliente registrado. Idempotente."""
    from shopman.guestman.models import Customer

    current = admin.site._registry.get(Customer)
    if current is None or getattr(current, "_team_link", False):
        return
    base = type(current)

    class CustomerTeamAdmin(base):
        form = build_team_form(base.form)
        fieldsets = _with_team_fieldset(base.fieldsets)
        _team_link = True

    CustomerTeamAdmin.__name__ = base.__name__
    CustomerTeamAdmin.__qualname__ = base.__qualname__
    admin.site.unregister(Customer)
    admin.site.register(Customer, CustomerTeamAdmin)
