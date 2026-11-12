"""Conexões de IA: o cadastro de provedor, endereço, chave e modelo.

A chave entra por um campo de senha e nunca volta à tela: o formulário só a
substitui (vazio mantém a atual) e a lista mostra os quatro últimos caracteres.
"""

from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminPasswordWidget, UnfoldBooleanSwitchWidget

from shopman.shop.models import AIConnection


class AIConnectionForm(forms.ModelForm):
    new_api_key = forms.CharField(
        label="chave",
        required=False,
        strip=True,
        widget=UnfoldAdminPasswordWidget(render_value=False),
        help_text="Cole a chave para gravar ou trocar. Vazio mantém a chave atual.",
    )
    clear_api_key = forms.BooleanField(label="apagar a chave", required=False, widget=UnfoldBooleanSwitchWidget)

    class Meta:
        model = AIConnection
        fields = (
            "ref",
            "name",
            "protocol",
            "base_url",
            "model",
            "price_input_per_m",
            "price_output_per_m",
            "customer_text_approved",
            "is_active",
        )

    def save(self, commit=True):
        connection = super().save(commit=False)
        if self.cleaned_data.get("clear_api_key"):
            connection.set_api_key("")
        elif self.cleaned_data.get("new_api_key"):
            connection.set_api_key(self.cleaned_data["new_api_key"])
        if commit:
            connection.save()
        return connection


@admin.register(AIConnection)
class AIConnectionAdmin(ModelAdmin):
    form = AIConnectionForm
    list_display = ("name", "ref", "protocol", "model", "key_display", "customer_text_approved", "is_active")
    list_filter = ("protocol", "is_active", "customer_text_approved")
    search_fields = ("name", "ref", "model")
    readonly_fields = ("key_display", "created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "ref", "protocol", "base_url", "model", "is_active"),
                "description": (
                    "Cada função de IA usa a conexão da sua rota (Loja → rotas de IA). Sem rota, vale "
                    "a única conexão ativa do formato."
                ),
            },
        ),
        ("Chave", {"fields": ("key_display", "new_api_key", "clear_api_key")}),
        ("Custo", {"fields": ("price_input_per_m", "price_output_per_m")}),
        ("Dados de cliente", {"fields": ("customer_text_approved",)}),
        ("Registro", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="chave")
    def key_display(self, obj):
        return f"…{obj.api_key_last4}" if obj and obj.api_key_last4 else "sem chave"
