"""Admin for POS terminals, CashShift, and CashMovement."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from shopman.utils import unfold_badge, unfold_badge_numeric
from shopman.utils.monetary import format_money
from unfold.admin import ModelAdmin
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminURLInputWidget,
    UnfoldBooleanSwitchWidget,
)

from shopman.backstage.models import CashMovement, CashShift, POSTerminal
from shopman.backstage.services.pos_hardware import (
    ADAPTER_AGENT,
    ADAPTER_MANUAL,
    DEFAULT_AGENT_URL,
    DEFAULT_PULSE_OFF_MS,
    DEFAULT_PULSE_ON_MS,
    CashDrawerConfig,
)


class CashMovementInline(admin.TabularInline):
    model = CashMovement
    extra = 0
    # `approved_by` fica ao lado de `created_by`: a retirada tem duas assinaturas,
    # e a conferência da retaguarda precisa ver as duas juntas.
    readonly_fields = ("movement_type", "amount_display", "reason", "created_by", "approved_by", "created_at")
    fields = ("movement_type", "amount_display", "reason", "created_by", "approved_by", "created_at")

    def amount_display(self, obj):
        return f"R$ {format_money(obj.amount_q)}"
    amount_display.short_description = "Valor"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CashShift)
class CashShiftAdmin(ModelAdmin):
    list_display = ("operator", "terminal", "opened_at", "status_display", "opening_display", "closing_display", "difference_display")
    list_filter = ("status", "terminal", "opened_at")
    # ``operator`` é FK para User: buscar nele direto vira ``operator__icontains``,
    # que o Django recusa em relação — e o erro derruba a BUSCA GLOBAL inteira, não
    # só esta tela. Atravesse a relação até os campos de texto do usuário.
    search_fields = (
        "operator__username",
        "operator__first_name",
        "operator__last_name",
        "terminal__ref",
        "terminal__label",
    )
    # ``notes`` é editável (gerente anota/corrige um turno fechado); a alteração
    # fica registrada no histórico do admin (LogEntry: quem/quando). Os valores
    # financeiros permanecem read-only (mutados só via PDV/serviço).
    readonly_fields = (
        "terminal", "operator", "opened_at", "closed_at", "status",
        "opening_display", "closing_display", "expected_display", "difference_display",
    )
    inlines = [CashMovementInline]
    ordering = ["-opened_at"]
    list_fullwidth = True
    compressed_fields = True

    def status_display(self, obj):
        if obj.status == CashShift.Status.OPEN:
            return unfold_badge("aberto", "yellow")
        return unfold_badge("fechado", "green")
    status_display.short_description = "Status"

    def opening_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.opening_amount_q)}", "base")
    opening_display.short_description = "Abertura"

    def closing_display(self, obj):
        if obj.blind_closing_amount_q is None:
            return "—"
        return unfold_badge_numeric(f"R$ {format_money(obj.blind_closing_amount_q)}", "base")
    closing_display.short_description = "Fechamento"

    def expected_display(self, obj):
        if obj.expected_amount_q is None:
            return "—"
        return f"R$ {format_money(obj.expected_amount_q)}"
    expected_display.short_description = "Esperado"

    def difference_display(self, obj):
        if obj.difference_q is None:
            return "—"
        sign = "+" if obj.difference_q >= 0 else ""
        color = "green" if obj.difference_q == 0 else "yellow"
        return unfold_badge_numeric(f"{sign}R$ {format_money(obj.difference_q)}", color)
    difference_display.short_description = "Diferença"

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")


@admin.register(CashMovement)
class CashMovementAdmin(ModelAdmin):
    """Trilha readonly de sangria/suprimento/ajuste.

    Movimentos nascem no PDV (POST ``pos/cash/movement/``); o Admin só lista e
    inspeciona a trilha de auditoria.
    """

    list_display = ("shift", "movement_type", "amount_display", "reason", "created_by", "approved_by", "created_at")
    list_filter = ("movement_type", "created_at")
    # ``shift__operator`` também para numa FK (User): atravessa mais um salto.
    # ``created_by``/``approved_by`` aqui são texto, não relação — esses ficam.
    search_fields = (
        "shift__operator__username",
        "shift__operator__first_name",
        "reason",
        "created_by",
        "approved_by",
    )
    readonly_fields = ("created_by", "approved_by", "created_at")
    ordering = ["-created_at"]
    compressed_fields = True

    def amount_display(self, obj):
        return f"R$ {format_money(obj.amount_q)}"
    amount_display.short_description = "Valor"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")

    def has_module_permission(self, request):
        return request.user.has_perm("backstage.operate_pos")


class POSTerminalForm(forms.ModelForm):
    """Config da gaveta em campos de verdade, não num JSON para o dono decorar.

    O schema mora na dataclass (`CashDrawerConfig`); este form é só a tela dela.
    Escreve de volta em `metadata["hardware"]["cash_drawer"]` preservando o
    resto do metadata — que guarda coisas de outros donos (favoritos, auto-lock).
    """

    drawer_adapter = forms.ChoiceField(
        label="Como a gaveta abre",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=(
            (ADAPTER_MANUAL, "Com a chave (o PDV não abre)"),
            (ADAPTER_AGENT, "Pelo agente local (kick na impressora)"),
        ),
        help_text="O agente é um processo na máquina do balcão. Instale com <code>python3 drawer_agent.py --install</code>.",
    )
    drawer_agent_url = forms.URLField(
        label="Endereço do agente",
        required=False,
        widget=UnfoldAdminURLInputWidget,
        assume_scheme="http",
        initial=DEFAULT_AGENT_URL,
        help_text="Sempre loopback do próprio balcão. O servidor nunca alcança este endereço — quem chama é o navegador.",
    )
    drawer_rotate_token = forms.BooleanField(
        label="Gerar um token novo",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text="Só marque se o token vazou ou se você vai reinstalar do zero. O agente do balcão para de abrir até receber o novo.",
    )
    drawer_pulse_pin = forms.ChoiceField(
        label="Pino do conector",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=(("0", "Pino 2 (padrão)"), ("1", "Pino 5")),
        help_text="Só mexa se a gaveta não abrir com o padrão.",
    )
    drawer_pulse_on_ms = forms.IntegerField(
        label="Pulso ligado (ms)",
        required=False,
        widget=UnfoldAdminIntegerFieldWidget,
        min_value=2,
        max_value=510,
        initial=DEFAULT_PULSE_ON_MS,
        help_text="Padrão da TM-T20: 50ms. O teto é 510ms — o solenoide é feito para pulso, não para carga contínua.",
    )
    drawer_pulse_off_ms = forms.IntegerField(
        label="Pulso desligado (ms)",
        required=False,
        widget=UnfoldAdminIntegerFieldWidget,
        min_value=2,
        max_value=510,
        initial=DEFAULT_PULSE_OFF_MS,
        help_text="Padrão da TM-T20: 500ms.",
    )
    drawer_open_on_cash_sale = forms.BooleanField(
        label="Abrir sozinha na venda em dinheiro",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        initial=True,
        help_text="Desligue se o balcão prefere abrir só no botão.",
    )

    class Meta:
        model = POSTerminal
        fields = ("ref", "label", "channel_ref", "location_ref", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance and self.instance.pk):
            return
        config = CashDrawerConfig.from_terminal(self.instance)
        self.fields["drawer_adapter"].initial = config.adapter if config.declared else ""
        self.fields["drawer_agent_url"].initial = config.agent_url
        self.fields["drawer_pulse_pin"].initial = str(config.pulse_pin)
        self.fields["drawer_pulse_on_ms"].initial = config.pulse_on_ms
        self.fields["drawer_pulse_off_ms"].initial = config.pulse_off_ms
        self.fields["drawer_open_on_cash_sale"].initial = config.open_on_cash_sale

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("drawer_adapter") == ADAPTER_AGENT:
            if not (cleaned.get("drawer_agent_url") or "").strip():
                self.add_error("drawer_agent_url", "Informe o endereço do agente.")
        return cleaned

    def _resolved_token(self) -> str:
        """O token do agente, gerado AQUI.

        Antes ele nascia no instalador e alguém transcrevia 43 caracteres de um
        terminal Linux para este formulário — e um erro de digitação só aparecia
        como 401 na hora de dar troco. Agora o Admin é o dono do par, e o comando
        de instalação já sai com o token dentro.
        """
        import secrets

        current = CashDrawerConfig.from_terminal(self.instance).token
        if current and not self.cleaned_data.get("drawer_rotate_token"):
            return current
        return secrets.token_urlsafe(32)

    def save(self, commit=True):
        instance = super().save(commit=False)
        metadata = dict(instance.metadata or {})
        hardware = dict(metadata.get("hardware") or {})
        adapter = self.cleaned_data.get("drawer_adapter") or ""
        if adapter:
            hardware["cash_drawer"] = {
                "enabled": True,
                "adapter": adapter,
                "agent_url": (self.cleaned_data.get("drawer_agent_url") or "").strip(),
                "token": self._resolved_token(),
                "pulse_pin": int(self.cleaned_data.get("drawer_pulse_pin") or 0),
                "pulse_on_ms": self.cleaned_data.get("drawer_pulse_on_ms") or DEFAULT_PULSE_ON_MS,
                "pulse_off_ms": self.cleaned_data.get("drawer_pulse_off_ms") or DEFAULT_PULSE_OFF_MS,
                "open_on_cash_sale": bool(self.cleaned_data.get("drawer_open_on_cash_sale")),
            }
        else:
            # Sem adapter escolhido = a loja não declarou gaveta neste balcão.
            hardware.pop("cash_drawer", None)
        if hardware:
            metadata["hardware"] = hardware
        else:
            metadata.pop("hardware", None)
        instance.metadata = metadata
        if commit:
            instance.save()
        return instance


@admin.register(POSTerminal)
class POSTerminalAdmin(ModelAdmin):
    form = POSTerminalForm
    list_display = ("ref", "label", "channel_ref", "health_display", "is_active")
    list_filter = ("is_active", "channel_ref")
    search_fields = ("ref", "label", "channel_ref")
    ordering = ("ref",)
    readonly_fields = ("health_display", "drawer_install_display")
    fieldsets = (
        (None, {"fields": ("ref", "label", "channel_ref", "location_ref", "is_active", "health_display")}),
        (
            "Gaveta de dinheiro",
            {
                "fields": (
                    "drawer_adapter", "drawer_agent_url", "drawer_pulse_pin",
                    "drawer_pulse_on_ms", "drawer_pulse_off_ms", "drawer_open_on_cash_sale",
                    "drawer_install_display",
                ),
                # Quem testa é a estação: só o navegador do balcão alcança a
                # loopback do agente. Este Admin não tem como chutar a gaveta.
                "description": "O teste da gaveta fica no próprio PDV (antesala do caixa) — só o navegador do balcão alcança o agente.",
            },
        ),
    )
    compressed_fields = True

    def drawer_install_display(self, obj):
        """Ponte para a tela que entrega o agente e o comando pronto.

        Salvar a config e não ter como levá-la ao balcão é meio caminho: o
        arquivo e as instruções ficam a um clique de onde o dono já está.
        """
        if obj is None or not obj.pk:
            return "Salve o terminal primeiro."
        from django.urls import reverse

        url = reverse("admin_console_pos_drawer_agent", args=[obj.ref])
        return format_html(
            '<a href="{}" class="font-medium underline underline-offset-4">Baixar o agente e ver como instalar</a>',
            url,
        )
    drawer_install_display.short_description = "Instalação no balcão"

    _HEALTH = {
        "ready": ("pronto", "green"),
        "warning": ("atenção", "yellow"),
        "error": ("erro", "red"),
        "deferred": ("na estação", "base"),
    }

    def health_display(self, obj):
        if obj is None:
            return "—"
        from shopman.backstage.services.pos_terminal import runtime_profile

        profile = runtime_profile(obj)
        label, color = self._HEALTH.get(profile.status, (profile.status, "base"))
        return unfold_badge(label, color)
    health_display.short_description = "saúde"
