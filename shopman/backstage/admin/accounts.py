"""Native Unfold accounts; OTP devices are managed only by the verified enrollment flow."""

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


def unregister_otp_device_admins() -> None:
    """Enrollment is owner-proved; privileged ModelAdmin CRUD must not bypass it."""
    from django_otp.plugins.otp_static.models import StaticDevice
    from django_otp.plugins.otp_totp.models import TOTPDevice

    for model in (TOTPDevice, StaticDevice):
        if admin.site.is_registered(model):
            admin.site.unregister(model)
