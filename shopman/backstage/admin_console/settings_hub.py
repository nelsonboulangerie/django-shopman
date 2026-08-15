"""Configuração — destino próprio da retaguarda (Unfold, página canônica).

A configuração saiu do menu de operação. O menu agora responde "o que está
acontecendo na loja"; esta tela responde "o que dá para ajustar" — e responde
mostrando, não exigindo que se lembre. Os dados vêm de
``shopman.backstage.projections.settings_hub``.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminTextInputWidget

from shopman.backstage.projections.settings_hub import build_settings_hub


class SettingsHubFilterForm(forms.Form):
    q = forms.CharField(
        label="Buscar",
        required=False,
        widget=UnfoldAdminTextInputWidget(
            attrs={"placeholder": "O que você quer ajustar? Ex.: entrega, preço, horário"}
        ),
    )


class SettingsHubView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Configuração"
    permission_required = "shop.view_shop"
    template_name = "admin_console/settings_hub/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "")
        hub = build_settings_hub(q=q, slug=kwargs.get("slug", ""))
        context.update(
            {
                "settings_hub": hub,
                "settings_hub_form": SettingsHubFilterForm(self.request.GET or None),
            }
        )
        return context


def _shop_model_admin():
    from shopman.shop.models import Shop

    return admin.site._registry[Shop]


def settings_hub_as_view():
    return SettingsHubView.as_view(model_admin=_shop_model_admin())


def settings_hub_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve o ModelAdmin de Shop tardiamente (ordem de import do URLConf)."""
    return settings_hub_as_view()(request, *args, **kwargs)
