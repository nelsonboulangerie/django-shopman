"""Admin de credenciais de operador (PIN) — reset e desbloqueio pelo gerente.

Gestão de operador é canônica no Admin/Unfold. A credencial (PIN) é genérica
(doorman); a POLÍTICA de operador (PIN temporário + trocar-no-1º-uso) vive no
backstage, que pode importar doorman. "Resetar PIN" gera um temporário mostrado
UMA vez ao gerente e marca ``must_change`` — o operador é forçado a trocá-lo no
próximo uso. O PIN nunca é revelado (só o digest é guardado); o temporário
aparece uma vez na mensagem para o gerente repassar.

Gateado por ``cashman.manage_operators``. Provisionar o PRIMEIRO PIN de um
operador novo continua pela CLI (``set_operator_pin``) ou pelo próprio reset.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.shortcuts import redirect
from shopman.doorman.models import PinCredential, PinCredentialError
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin

from shopman.backstage.admin_console.operator_badge import BADGE_SESSION_KEY
from shopman.backstage.services.operator import reset_operator_pin

MANAGE_OPERATORS = "cashman.manage_operators"


@admin.register(PinCredential)
class PinCredentialAdmin(ModelAdmin):
    list_display = (
        "operator_display", "state_display", "badge_display", "must_change_display",
        "last_verified_at", "updated_at",
    )
    list_filter = ("must_change",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = (
        "user", "pin_hash", "badge_hash", "attempts", "max_attempts",
        "locked_until", "must_change", "last_verified_at", "created_at", "updated_at",
    )
    ordering = ["user__first_name", "user__username"]
    actions = ["issue_badge", "revoke_badge", "reset_pin", "unlock_pin"]
    compressed_fields = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.display(description="Operador")
    def operator_display(self, obj):
        return obj.user.get_full_name().strip() or obj.user.get_username()

    @admin.display(description="Situação")
    def state_display(self, obj):
        if obj.is_locked:
            return unfold_badge("bloqueado", "red")
        return unfold_badge("ativo", "green")

    @admin.display(description="Crachá")
    def badge_display(self, obj):
        # Só o FATO de ter crachá. O código nunca é revelado (só o digest é guardado),
        # e mostrar o digest não ajudaria ninguém e ainda sugeriria que é reutilizável.
        return unfold_badge("emitido", "green") if obj.badge_hash else unfold_badge("sem crachá", "base")

    @admin.display(description="Trocar no 1º uso")
    def must_change_display(self, obj):
        return unfold_badge("sim", "yellow") if obj.must_change else unfold_badge("não", "base")

    @admin.action(description="Resetar PIN (gera temporário)")
    def reset_pin(self, request, queryset):
        temps: list[str] = []
        for cred in queryset.select_related("user"):
            try:
                temp = reset_operator_pin(cred.user)
            except PinCredentialError as exc:
                self.message_user(request, f"{cred.user.get_username()}: {exc}", level=messages.ERROR)
                continue
            temps.append(f"{cred.user.get_username()}: {temp}")
        if temps:
            self.message_user(
                request,
                "PIN temporário (anote e informe ao operador — não será mostrado de novo): "
                + " · ".join(temps),
                level=messages.WARNING,
            )

    @admin.action(description="Emitir crachá (mostra o código uma vez)")
    def issue_badge(self, request, queryset):
        """Sorteia um crachá novo e manda para a página de impressão.

        Um operador por vez, de propósito: a página mostra UM crachá, e o token só existe
        naquela ida. Emitir para vários de uma vez esconderia os outros para sempre.
        """
        creds = list(queryset.select_related("user")[:2])
        if len(creds) != 1:
            self.message_user(
                request,
                "Selecione um operador por vez — o código do crachá aparece uma vez só.",
                level=messages.ERROR,
            )
            return None
        cred = creds[0]
        token = PinCredential.issue_badge(cred.user)
        # O token viaja pela SESSÃO, não pela URL: credencial em querystring vaza para
        # histórico, log de proxy e ombro alheio. A página o retira ao mostrar.
        request.session[BADGE_SESSION_KEY] = {
            "token": token,
            "name": cred.user.get_full_name().strip(),
            "username": cred.user.get_username(),
        }
        return redirect("admin_console_operator_badge")

    @admin.action(description="Revogar crachá (crachá perdido)")
    def revoke_badge(self, request, queryset):
        revoked = 0
        for cred in queryset:
            if cred.badge_hash:
                cred.clear_badge()
                revoked += 1
        if revoked:
            self.message_user(
                request,
                f"{revoked} crachá(s) revogado(s). Quem estava com o crachá antigo não entra mais.",
            )
        else:
            self.message_user(
                request, "Nenhum dos selecionados tinha crachá.", level=messages.WARNING
            )

    @admin.action(description="Desbloquear PIN")
    def unlock_pin(self, request, queryset):
        count = 0
        for cred in queryset:
            cred.unlock()
            count += 1
        self.message_user(request, f"{count} credencial(is) desbloqueada(s).")

    def has_add_permission(self, request):
        # Sem hash à mão: o primeiro PIN vem do reset (temporário) ou da CLI.
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_OPERATORS)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_OPERATORS)

    def has_module_permission(self, request):
        return request.user.has_perm(MANAGE_OPERATORS)

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_OPERATORS)
