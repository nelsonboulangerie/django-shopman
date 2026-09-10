"""Admin do terminal do PDV: o do ``cashman`` mais a gaveta e a saúde do balcão.

O pacote registra ``Terminal`` como config genérica (ref, canal, local). O que é
da SUPERFÍCIE de operador — como a gaveta abre, o agente do balcão, o pulso do
solenoide, a saúde dos periféricos — não é do pacote e não pode morar nele
(``cashman`` não sabe o que é um agente de impressora). Por isso o backstage
registra por cima: tira o Admin do contrib e põe uma subclasse com o form de
hardware. Um Admin só para o terminal, e o hardware onde a superfície manda.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from shopman.cashman.models import Terminal
from shopman.utils import unfold_badge, unfold_link
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminURLInputWidget,
    UnfoldBooleanSwitchWidget,
)

from shopman.backstage.projections.operator_badge import mask_badge
from shopman.backstage.services.pos_hardware import (
    ADAPTER_AGENT,
    ADAPTER_MANUAL,
    DEFAULT_AGENT_URL,
    DEFAULT_PULSE_OFF_MS,
    DEFAULT_PULSE_ON_MS,
    CashDrawerConfig,
    DeviceAgentConfig,
)


class TerminalForm(forms.ModelForm):
    """Config da gaveta em campos de verdade, não num JSON para o dono decorar.

    O schema mora na dataclass (`CashDrawerConfig`); este form é só a tela dela.
    Escreve de volta em `metadata["hardware"]["cash_drawer"]` preservando o
    resto do metadata — que guarda coisas de outros donos (favoritos, auto-lock).
    """

    drawer_adapter = forms.ChoiceField(
        label="Como a gaveta abre",
        required=False,
        widget=UnfoldAdminSelectWidget,
        # ⚠️ A opção vazia é obrigatória, não decoração. Sem ela, um terminal
        # sem gaveta configurada abria o formulário mostrando "Com a chave"
        # visualmente marcado (o navegador seleciona a primeira opção quando
        # nenhuma tem `selected`) — e salvar sem tocar no campo GRAVAVA
        # `manual`. Estado real e estado exibido divergiam, e ninguém via.
        choices=(
            ("", "— não configurada —"),
            (ADAPTER_MANUAL, "Com a chave (o PDV não abre)"),
            (ADAPTER_AGENT, "Pelo agente local (kick na impressora)"),
        ),
        help_text="O agente é um processo na máquina do balcão. Instale com <code>python3 counter_agent.py --install</code>.",
    )
    counter_agent_url = forms.URLField(
        label="Endereço do agente do dispositivo",
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
    printer_enabled = forms.BooleanField(
        label="Impressora de preparação ativa",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text="Habilita a fila auditável de etiquetas neste terminal.",
    )
    printer_role = forms.ChoiceField(
        label="Papel operacional",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=(("preparation", "Preparação e pesagem"),),
        initial="preparation",
    )
    printer_roll_width_mm = forms.ChoiceField(
        label="Largura da bobina de recibos",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=(("80", "80 mm"), ("58", "58 mm")),
        initial="80",
    )
    printer_label_width_mm = forms.IntegerField(
        label="Largura da etiqueta (mm)",
        required=False,
        min_value=40,
        max_value=120,
        widget=UnfoldAdminIntegerFieldWidget,
        initial=60,
        help_text="Padrão atual da preparação: etiqueta adesiva de 60 mm.",
    )
    printer_label_height_mm = forms.IntegerField(
        label="Altura da etiqueta (mm)",
        required=False,
        min_value=20,
        max_value=200,
        widget=UnfoldAdminIntegerFieldWidget,
        initial=40,
        help_text="Padrão atual da preparação: etiqueta adesiva de 40 mm.",
    )
    printer_cut_mode = forms.ChoiceField(
        label="Separação das etiquetas",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=(("none", "Sem corte (adesiva)"), ("partial", "Corte parcial")),
        initial="none",
    )
    class Meta:
        model = Terminal
        fields = ("ref", "label", "channel_ref", "location_ref", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance and self.instance.pk):
            return
        config = CashDrawerConfig.from_terminal(self.instance)
        device_agent = DeviceAgentConfig.from_terminal(self.instance)
        self.fields["drawer_adapter"].initial = config.adapter if config.declared else ""
        # ⚠️ As PONTAS do token, ao lado do botão de rotacionar. É o único lugar
        # do Admin onde dá para comparar com o `--doctor` do balcão — e "token
        # inválido" no PDV é exatamente um par desencontrado, que sem isto não
        # tinha como ser diagnosticado de nenhum dos dois lados.
        if config.token:
            self.fields["drawer_rotate_token"].help_text += (
                f" Token atual: {mask_badge(config.token)} "
                "— confira com `counter-agent --doctor` no balcão."
            )
        self.fields["counter_agent_url"].initial = device_agent.agent_url
        self.fields["drawer_pulse_pin"].initial = str(config.pulse_pin)
        self.fields["drawer_pulse_on_ms"].initial = config.pulse_on_ms
        self.fields["drawer_pulse_off_ms"].initial = config.pulse_off_ms
        self.fields["drawer_open_on_cash_sale"].initial = config.open_on_cash_sale
        metadata = self.instance.metadata if isinstance(self.instance.metadata, dict) else {}
        hardware = metadata.get("hardware") if isinstance(metadata.get("hardware"), dict) else {}
        printer = hardware.get("printer") if isinstance(hardware.get("printer"), dict) else {}
        self.fields["printer_enabled"].initial = bool(printer and printer.get("enabled") is not False)
        self.fields["printer_role"].initial = str(printer.get("role") or "preparation")
        self.fields["printer_roll_width_mm"].initial = str(printer.get("roll_width_mm") or "80")
        self.fields["printer_label_width_mm"].initial = int(printer.get("label_width_mm") or 60)
        self.fields["printer_label_height_mm"].initial = int(printer.get("label_height_mm") or 40)
        self.fields["printer_cut_mode"].initial = str(printer.get("label_cut_mode") or "none")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("drawer_adapter") == ADAPTER_AGENT or cleaned.get("printer_enabled"):
            if not (cleaned.get("counter_agent_url") or "").strip():
                self.add_error("counter_agent_url", "Informe o endereço do agente.")
        if cleaned.get("printer_enabled"):
            if cleaned.get("printer_role") != "preparation":
                self.add_error("printer_role", "Neste incremento, use Preparação e pesagem.")
            if not cleaned.get("printer_label_width_mm") or not cleaned.get("printer_label_height_mm"):
                self.add_error("printer_label_width_mm", "Informe as duas dimensões da etiqueta.")
        return cleaned

    def _resolved_token(self) -> str:
        """O token do agente, gerado AQUI.

        Antes ele nascia no instalador e alguém transcrevia 43 caracteres de um
        terminal Linux para este formulário — e um erro de digitação só aparecia
        como 401 na hora de dar troco. Agora o Admin é o dono do par, e o comando
        de instalação já sai com o token dentro.
        """
        import secrets

        current = DeviceAgentConfig.from_terminal(self.instance).token
        if current and not self.cleaned_data.get("drawer_rotate_token"):
            return current
        return secrets.token_urlsafe(32)

    def save(self, commit=True):
        instance = super().save(commit=False)
        metadata = dict(instance.metadata or {})
        hardware = dict(metadata.get("hardware") or {})
        adapter = self.cleaned_data.get("drawer_adapter") or ""
        needs_device_agent = bool(
            adapter == ADAPTER_AGENT or self.cleaned_data.get("printer_enabled")
        )
        agent_url = (self.cleaned_data.get("counter_agent_url") or "").strip()
        token = self._resolved_token() if needs_device_agent else ""
        if needs_device_agent:
            hardware["device_agent"] = {
                "enabled": True,
                "agent_url": agent_url,
                "token": token,
            }
        else:
            hardware.pop("device_agent", None)
        if adapter:
            hardware["cash_drawer"] = {
                "enabled": True,
                "adapter": adapter,
                "pulse_pin": int(self.cleaned_data.get("drawer_pulse_pin") or 0),
                "pulse_on_ms": self.cleaned_data.get("drawer_pulse_on_ms") or DEFAULT_PULSE_ON_MS,
                "pulse_off_ms": self.cleaned_data.get("drawer_pulse_off_ms") or DEFAULT_PULSE_OFF_MS,
                "open_on_cash_sale": bool(self.cleaned_data.get("drawer_open_on_cash_sale")),
            }
        else:
            # Sem adapter escolhido = a loja não declarou gaveta neste balcão.
            hardware.pop("cash_drawer", None)
        if self.cleaned_data.get("printer_enabled"):
            label_width = int(self.cleaned_data.get("printer_label_width_mm") or 60)
            label_height = int(self.cleaned_data.get("printer_label_height_mm") or 40)
            # A fila/modelo/adaptador são fatos já aferidos na estação. Editar
            # o tamanho da etiqueta não pode apagá-los — foi exatamente assim
            # que uma impressora funcional do PDV voltava a parecer um relay
            # ainda não pareado.
            printer = dict(hardware.get("printer") or {})
            printer.update({
                "enabled": True,
                "adapter": str(printer.get("adapter") or "relay"),
                "role": "preparation",
                "roll_width_mm": int(self.cleaned_data.get("printer_roll_width_mm") or 80),
                "columns": 48,
                "cut_mode": "partial",
                "label_width_mm": label_width,
                "label_height_mm": label_height,
                "label_print_width_mm": label_width - 8,
                "label_cut_mode": self.cleaned_data.get("printer_cut_mode") or "none",
            })
            hardware["printer"] = printer
        else:
            hardware.pop("printer", None)
        if hardware:
            metadata["hardware"] = hardware
        else:
            metadata.pop("hardware", None)
        instance.metadata = metadata
        if commit:
            instance.save()
        return instance


# A base é o que o pacote REGISTROU (``shopman.cashman.contrib.admin_unfold``),
# lida do site em vez de importada: a superfície não entra no contrib do Core
# (fronteira de imports), ela herda do que o Core pôs no Admin.
_CashmanTerminalAdmin = type(admin.site._registry[Terminal])


class TerminalAdmin(_CashmanTerminalAdmin):
    """O Admin do pacote, mais a gaveta (form) e a saúde do balcão (coluna)."""

    form = TerminalForm
    list_display = ("ref", "label", "channel_ref", "health_display", "active_badge")
    readonly_fields = ("health_display", "drawer_install_display")
    fieldsets = (
        (None, {"fields": ("ref", "label", "channel_ref", "location_ref", "is_active", "health_display")}),
        (
            "Agente local do dispositivo",
            {
                "fields": (
                    "counter_agent_url",
                    "drawer_rotate_token",
                    "drawer_install_display",
                ),
                "description": "Ponte privada deste computador com impressora e gaveta. Produção, PDV e os demais apps autorizados reutilizam o mesmo agente.",
            },
        ),
        (
            "Gaveta de dinheiro",
            {
                "fields": (
                    "drawer_adapter", "drawer_pulse_pin",
                    "drawer_pulse_on_ms", "drawer_pulse_off_ms", "drawer_open_on_cash_sale",
                ),
                # Quem testa é a estação: só o navegador do balcão alcança a
                # loopback do agente. Este Admin não tem como chutar a gaveta.
                "description": "O teste da gaveta fica no próprio PDV (antesala do caixa) — só o navegador do balcão alcança o agente local.",
            },
        ),
        (
            "Impressora de preparação",
            {
                "fields": (
                    "printer_enabled",
                    "printer_role",
                    "printer_roll_width_mm",
                    ("printer_label_width_mm", "printer_label_height_mm"),
                    "printer_cut_mode",
                ),
                "description": "A bobina do PDV e a etiqueta de preparação são perfis distintos. O servidor deriva automaticamente margens e colunas; o agente apenas entrega os bytes.",
            },
        ),
    )

    def drawer_install_display(self, obj):
        """Ponte para a tela que entrega o agente e o comando pronto.

        Salvar a config e não ter como levá-la ao balcão é meio caminho: o
        arquivo e as instruções ficam a um clique de onde o dono já está.
        """
        if obj is None or not obj.pk:
            return "Salve o terminal primeiro."
        from django.urls import reverse

        url = reverse("admin_console_pos_counter_agent", args=[obj.ref])
        return unfold_link(url, "Baixar o agente e ver como instalar", icon="download")
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


# Registrar por cima do contrib: o backstage vem depois do cashman no
# INSTALLED_APPS, então o Admin do pacote já está no site quando este módulo
# importa. Tirar e pôr é o jeito honesto de dizer "aqui a superfície manda".
admin.site.unregister(Terminal)
admin.site.register(Terminal, TerminalAdmin)
