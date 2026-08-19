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
from django.utils import timezone
from django.utils.html import format_html
from shopman.doorman.models import PinCredential, PinCredentialError
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin

from shopman.backstage.admin_console.operator_badge import BADGE_SESSION_KEY
from shopman.backstage.services.operator import reset_operator_pin

MANAGE_OPERATORS = "cashman.manage_operators"


def registrar_no_historico(request, operador, mensagem: str) -> None:
    """Deixa no histórico do Admin quem mexeu no crachá de quem, e quando.

    Antes, emitir crachá não deixava rastro NENHUM: um gerente emitia para
    qualquer pessoa, a qualquer hora, e o único vestígio era o digest mudando
    em silêncio no banco.

    ⚠️ Isto não IMPEDE a cópia não declarada — quem emite vê o código na tela e
    uma câmera de celular vence qualquer prazo. O que a trilha faz é DETECTAR:
    se o crachá de alguém destrava o PDV num dia de folga, existe onde olhar e
    com o que comparar. Foi o buraco que sobrou depois de cercar o resto.

    Vai para o `LogEntry` do Django, que é o histórico que o próprio Admin já
    mostra — sem model novo, sem migração, e visível onde alguém procuraria.
    """
    from django.contrib.admin.models import CHANGE, LogEntry
    from django.contrib.contenttypes.models import ContentType

    # `create` direto, não o helper: `log_action` saiu do Django e o substituto
    # (`log_actions`) mudou de assinatura entre versões. A linha é simples, e
    # depender dela é mais estável do que perseguir o helper da vez.
    LogEntry.objects.create(
        user_id=request.user.pk,
        content_type=ContentType.objects.get_for_model(operador),
        object_id=str(operador.pk),
        object_repr=operador.get_username(),
        action_flag=CHANGE,
        change_message=mensagem,
    )


@admin.register(PinCredential)
class PinCredentialAdmin(ModelAdmin):
    list_display = (
        "operator_display", "groups_display", "state_display", "badge_display",
        "must_change_display", "last_verified_at", "updated_at",
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

    list_select_related = ("user",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user").prefetch_related("user__groups")

    @admin.display(description="Operador")
    def operator_display(self, obj):
        return obj.user.get_full_name().strip() or obj.user.get_username()

    @admin.display(description="Papel")
    def groups_display(self, obj):
        """O papel da pessoa, na MESMA linha do PIN e do crachá.

        Antes, montar alguém exigia duas telas: esta para PIN/crachá e a de
        Usuários para o grupo. Duas telas para uma pessoa é como se esquece
        metade — e a metade esquecida costuma ser a permissão, que só aparece
        quando alguém não consegue trabalhar.

        Sem grupo aparece em vermelho de propósito: conta que opera sem grupo é
        acesso por permissão avulsa, que não se explica pela tela de Grupos.
        """
        nomes = [g.name for g in obj.user.groups.all()]
        if not nomes:
            return unfold_badge("sem grupo", "red")
        return format_html(" ".join(["{}"] * len(nomes)), *(unfold_badge(n, "base") for n in nomes))

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
        # histórico, log de proxy e ombro alheio.
        request.session[BADGE_SESSION_KEY] = {
            "token": token,
            "name": cred.user.get_full_name().strip(),
            "username": cred.user.get_username(),
            # Carimbo para a página saber até quando pode REEXIBIR (ver
            # `operator_badge.py`): impressora que emperra não pode custar um
            # crachá novo, e reexibir o mesmo token não cria credencial alguma.
            "issued_at": timezone.now().isoformat(),
        }
        registrar_no_historico(
            request, cred.user, "Crachá emitido (o anterior deixou de valer)."
        )
        return redirect("admin_console_operator_badge")

    @admin.action(description="Revogar crachá (crachá perdido)")
    def revoke_badge(self, request, queryset):
        revoked = 0
        for cred in queryset.select_related("user"):
            if cred.badge_hash:
                cred.clear_badge()
                registrar_no_historico(request, cred.user, "Crachá revogado.")
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
