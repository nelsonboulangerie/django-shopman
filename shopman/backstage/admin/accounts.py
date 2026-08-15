"""Usuários, grupos e 2FA no Unfold — as três telas que ficaram no Admin antigo.

Ninguém as registrou: elas vêm prontas do `django.contrib.auth` e do
`django_otp`, com o `ModelAdmin` vanilla. O Unfold estiliza o que passa pelo
`ModelAdmin` dele, então essas três abriam com a cara do Django de sempre —
input de borda quadrada, rádio sem estilo, botão cinza — no meio de um Admin
Unfold. Era o ponto mais visível do "Frankenstein": não é que estivessem feias,
é que eram de OUTRO sistema.

O Unfold publica exatamente para isto os seus formulários de conta
(`unfold.forms`), que preservam o comportamento do Django (hash de senha, o link
para trocá-la, validação) e trocam só os widgets.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """UserAdmin do Django com o chrome e os widgets do Unfold."""

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    compressed_fields = True


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin, ModelAdmin):
    """Grupos com o seletor de permissões do Unfold.

    A lista de permissões é longa por natureza; o widget do Unfold é o mesmo
    filtro horizontal, mas legível dentro do tema.
    """

    compressed_fields = True


def register_totp_admin() -> None:
    """Re-registra o dispositivo TOTP no Unfold, se o django_otp estiver instalado.

    Fica atrás de uma função porque o app é opcional: sem ele, não há o que
    re-registrar, e um import no topo quebraria o boot de um deployment sem 2FA.
    """
    try:
        from django_otp.plugins.otp_totp.admin import TOTPDeviceAdmin
        from django_otp.plugins.otp_totp.models import TOTPDevice
    except ImportError:
        return

    try:
        admin.site.unregister(TOTPDevice)
    except admin.sites.NotRegistered:
        return

    @admin.register(TOTPDevice)
    class UnfoldTOTPDeviceAdmin(TOTPDeviceAdmin, ModelAdmin):
        """O django_otp vem inteiro em inglês, e nada disso é nosso vocabulário.

        Os fieldsets herdados diziam "Timestamps", "Configuration", "State"; os
        campos, "Step", "Drift", "Tolerance". Redeclarar os fieldsets é o que dá
        para fazer sem tocar no pacote de terceiros: os rótulos dos campos técnicos
        (`step`, `drift`) seguem do django_otp, mas quem mexe nesta tela é
        superusuário configurando 2FA, não o dono da padaria.
        """

        compressed_fields = True
        fieldsets = (
            ("Identificação", {"fields": ("user", "name", "confirmed")}),
            ("Chave", {"fields": ("key", "step", "t0", "digits", "tolerance", "drift")}),
            (
                "Bloqueio por tentativa",
                {"fields": ("throttling_failure_timestamp", "throttling_failure_count")},
            ),
        )
