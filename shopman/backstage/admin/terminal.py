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
from django.utils.html import format_html
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
from shopman.backstage.station_trust import (
    ATTENDED,
    AUTONOMOUS,
    autonomous_operator_for,
    eligible_station_operators,
    terminal_mode,
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
    station_mode = forms.ChoiceField(
        label="Como esta estação se identifica",
        required=False,
        widget=UnfoldAdminSelectWidget,
        # Sem opção vazia, e de propósito: "atendida" É o default do servidor
        # (`terminal_mode` devolve ATTENDED para qualquer coisa que não seja
        # exatamente `autonomous`), então a primeira opção que o navegador marca
        # sozinho é a mesma que o servidor já aplica. A armadilha que a gaveta
        # tem — primeira opção marcada gravando um estado que ninguém escolheu —
        # aqui não existe, porque o estado marcado é o estado real.
        choices=(
            (ATTENDED, "Atendida — pede PIN ou crachá (balcão, cozinha)"),
            (AUTONOMOUS, "Autônoma — age sozinha, só na Produção (painel de parede)"),
        ),
        initial=ATTENDED,
        help_text=(
            "Autônoma é para o painel que fica na parede sem ninguém para digitar PIN. "
            "Ela age em nome da conta escolhida abaixo, e <strong>somente na superfície "
            "de Produção</strong>: o cookie deste dispositivo vale em todo o domínio, e o "
            "servidor recusa a conta em qualquer outra tela."
        ),
    )
    station_operator = forms.ChoiceField(
        label="Conta em nome de quem a estação autônoma age",
        required=False,
        widget=UnfoldAdminSelectWidget,
        # ⚠️ Lista, nunca texto livre — e a lista é a MESMA pergunta que o
        # servidor faz (`eligible_station_operators`). Um campo de texto aqui
        # aceitaria a conta que `autonomous_operator_for` recusa (superusuária,
        # inativa, fora da casa) e o gestor salvaria feliz uma estação que não
        # age — sem nada escrito em tela dizendo por quê.
        choices=(("", "— nenhuma —"),),
        help_text=(
            "Superusuário não aparece aqui e o servidor o recusa: "
            "<code>is_superuser</code> curto-circuita toda checagem de permissão, "
            "e um painel de parede com chave-mestra é o incidente de 20/08 com outro "
            "nome. Conceda a esta conta só o que a Produção precisa "
            "(<code>backstage.operate_production</code>), e desative a conta para "
            "desligar o painel sem ir até ele."
        ),
    )
    print_target_ref = forms.ChoiceField(
        label="Para onde vão as etiquetas desta estação",
        required=False,
        widget=UnfoldAdminSelectWidget,
        # ⚠️ Lista, nunca texto livre. O servidor recusa um destino que não
        # aceite preparação (`resolve_destination`), então um campo que aceita
        # ref inventada só troca o beco visível por um silencioso. As opções
        # saem da MESMA pergunta que o servidor faz na hora de imprimir.
        choices=(("", "— a impressora desta estação, ou a única da loja —"),),
        help_text=(
            "Deixe no automático quando a estação imprime na própria impressora "
            "ou quando a loja só tem uma de preparação. Com duas ou mais, sem "
            "escolher aqui o servidor recusa o pedido — e não havia por onde escolher."
        ),
    )

    class Meta:
        model = Terminal
        fields = ("ref", "label", "channel_ref", "location_ref", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stale_print_target = ""
        self._stale_station_operator = ""
        self._load_print_target_choices()
        self._load_station_identity()
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

    def _station_config(self) -> dict:
        """O bloco ``station`` do terminal — de outro dono, e preservado inteiro.

        ``mode`` e ``operator`` (totem autônomo) moram no mesmo dict e não têm
        campo aqui. Escrever o destino sem reler isto apagaria em silêncio a
        identidade de uma estação autônoma.
        """
        metadata = getattr(self.instance, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        station = metadata.get("station")
        return dict(station) if isinstance(station, dict) else {}

    def _load_station_identity(self) -> None:
        """Modo e conta da estação — a lista saindo da MESMA fonte do gate.

        O ``initial`` do modo vem de ``terminal_mode``, não do JSON cru: um
        ``mode`` escrito errado (``"autonoma"``, um typo de outro tempo) o
        servidor já lê como atendida, e a tela tem de dizer a mesma coisa. Mostrar
        o texto cru faria o gestor ler "autônoma" numa estação que pede PIN.
        """
        station = self._station_config()
        current = str(station.get("operator") or "").strip()
        elegiveis = eligible_station_operators()
        choices = [("", "— nenhuma —")]
        choices += [
            (conta.username, f"{conta.get_full_name() or conta.username} ({conta.username})")
            for conta in elegiveis
        ]
        if current and current not in {conta.username for conta in elegiveis}:
            # ⚠️ O que está GRAVADO entra na lista mesmo recusado — mesma regra do
            # destino da etiqueta. Sumir com ele faria a tela mostrar "nenhuma"
            # enquanto o banco aponta para uma conta desativada, promovida a
            # superusuária ou apagada, e o gestor procuraria o defeito na conta
            # certa. O `clean` barra o salvamento até ele repontar.
            self._stale_station_operator = current
            choices.append((current, f"{current} — conta indisponível"))
        self.fields["station_operator"].choices = choices
        self.fields["station_operator"].initial = current
        self.fields["station_mode"].initial = terminal_mode(
            self.instance.ref if getattr(self.instance, "pk", None) else ""
        )

    def _load_print_target_choices(self) -> None:
        from shopman.backstage.services.print_jobs import preparation_destinations

        current = str(self._station_config().get("print_target_ref") or "").strip()
        own_ref = self.instance.ref if getattr(self.instance, "pk", None) else ""
        # A própria estação fica FORA da lista: quando ela tem impressora, o
        # automático já resolve nela. Duas opções para a mesma coisa é uma a mais.
        available = preparation_destinations(exclude_ref=own_ref)
        choices = [("", "— a impressora desta estação, ou a única da loja —")]
        choices += [
            (ref, label if label == ref else f"{label} ({ref})") for ref, label in available
        ]
        if current and current not in {ref for ref, _ in available}:
            # ⚠️ O que está GRAVADO entra na lista mesmo quebrado. Sumir com ele
            # faria a tela mostrar "automático" enquanto o banco aponta para uma
            # impressora que saiu do ar — estado exibido divergindo do real, que
            # é o mesmo buraco da opção vazia do adapter da gaveta.
            self._stale_print_target = current
            choices.append((current, f"{current} — destino indisponível"))
        self.fields["print_target_ref"].choices = choices
        self.fields["print_target_ref"].initial = current

    def clean(self):
        cleaned = super().clean()
        modo = (cleaned.get("station_mode") or ATTENDED).strip()
        conta = (cleaned.get("station_operator") or "").strip()
        # A conta só é cobrada quando ela IMPORTA. Cobrar numa estação atendida
        # travaria o salvamento de um balcão por causa de um nome largado no JSON
        # que ninguém usa — e o próprio `save` apaga esse nome logo abaixo.
        if modo == AUTONOMOUS:
            if not conta:
                self.add_error(
                    "station_operator",
                    "Uma estação autônoma age em nome de uma conta. Sem ela o painel "
                    "volta a pedir PIN — e não há ninguém na parede para digitar.",
                )
            elif conta == self._stale_station_operator:
                self.add_error(
                    "station_operator",
                    "Esta conta não serve mais a uma estação autônoma (desativada, fora "
                    "da equipe ou promovida a superusuário). Escolha outra.",
                )
        target = (cleaned.get("print_target_ref") or "").strip()
        if target and target == self._stale_print_target:
            self.add_error(
                "print_target_ref",
                "Este destino não aceita mais etiquetas de preparação (inativo ou sem "
                "impressora). Escolha outro ou volte para o automático.",
            )
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
            # A fila e o modelo são fatos já aferidos na estação. Editar o
            # tamanho da etiqueta não pode apagá-los — foi exatamente assim que
            # uma impressora funcional do PDV voltava a parecer um relay ainda
            # não pareado. Por isso o `update` sobre o dict existente, que
            # preserva toda chave que este form não conhece.
            #
            # ⚠️ `adapter` NÃO é escrito aqui. Ele era um rótulo que ninguém
            # consultava — o Admin cunhava "relay", o seed cunhava "driver" — e
            # quem responde se este terminal imprime é `hardware.device_agent`,
            # escrito logo acima. Ver `pos_terminal._printer_health`.
            printer = dict(hardware.get("printer") or {})
            printer.update({
                "enabled": True,
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
        # ⚠️ RELEITURA, não dict novo. O bloco `station` tem três chaves de dois
        # donos — `mode`/`operator` (identidade) e `print_target_ref` (destino da
        # etiqueta) — e escrever por cima apagaria a do outro em silêncio.
        station = self._station_config()
        target = (self.cleaned_data.get("print_target_ref") or "").strip()
        if target:
            station["print_target_ref"] = target
        else:
            station.pop("print_target_ref", None)
        modo = (self.cleaned_data.get("station_mode") or ATTENDED).strip()
        station["mode"] = modo
        if modo == AUTONOMOUS:
            station["operator"] = (self.cleaned_data.get("station_operator") or "").strip()
        else:
            # Voltar para atendida DESFAZ o vínculo, não o guarda para depois. Uma
            # conta com poder permanente esquecida num aparelho físico é a arma
            # carregada da gaveta: basta alguém reativar o modo — ou um typo — para
            # ela voltar a agir sem que ninguém tenha escolhido essa conta hoje.
            station.pop("operator", None)
        if station:
            metadata["station"] = station
        else:
            metadata.pop("station", None)
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
    readonly_fields = (
        "health_display",
        "drawer_install_display",
        "print_destination_display",
        "station_identity_display",
    )
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
        (
            "Identificação desta estação",
            {
                "fields": ("station_mode", "station_operator", "station_identity_display"),
                "description": (
                    "O painel de parede da Produção não tem ninguém para digitar PIN, "
                    "então ele age em nome de uma conta. Vale SÓ para a Produção: o "
                    "cookie deste dispositivo alcança o domínio inteiro, e é o servidor "
                    "que recusa a conta nas demais telas — não a configuração daqui."
                ),
            },
        ),
        (
            "Destino das etiquetas desta estação",
            {
                "fields": ("print_target_ref", "print_destination_display"),
                "description": "Quem PEDE a etiqueta e quem IMPRIME podem ser dispositivos diferentes: o tablet da bancada pede, a impressora do balcão imprime. Quem escolhe é o gestor, aqui — o dispositivo nunca manda um endereço de impressora ao servidor.",
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

    def station_identity_display(self, obj):
        """Quem o SERVIDOR resolve para esta estação, agora.

        Mesmo papel do destino da etiqueta logo abaixo: salvar e só descobrir na
        parede que o painel continua pedindo PIN é o buraco de sempre. Aqui o
        gestor lê a resposta do gate — a de ``autonomous_operator_for``, a mesma
        que roda na requisição — ao lado dos campos que a decidem.
        """
        if obj is None or not obj.pk:
            return "Salve o terminal primeiro."
        if terminal_mode(obj.ref) != AUTONOMOUS:
            return unfold_badge("atendida — pede identificação", "base")
        conta = autonomous_operator_for(obj.ref)
        if conta is None:
            return format_html(
                "{} {}",
                unfold_badge("autônoma sem conta válida", "red"),
                "O painel vai pedir PIN e não há quem digite. Escolha uma conta acima.",
            )
        return format_html(
            "{} {}",
            unfold_badge("autônoma", "green"),
            f"age como {conta.get_full_name() or conta.username} ({conta.username}), só na Produção",
        )
    station_identity_display.short_description = "Identidade resolvida agora"

    def print_destination_display(self, obj):
        """A MESMA resposta que a estação vai receber na hora de imprimir.

        Salvar o destino e só descobrir no meio da produção se ele vale é o
        buraco de sempre. Aqui o gestor lê a recusa do servidor — palavra por
        palavra — ao lado do campo que a resolve.
        """
        if obj is None or not obj.pk:
            return "Salve o terminal primeiro."
        from shopman.backstage.services.print_jobs import (
            preparation_destinations,
            resolve_destination,
        )

        if not preparation_destinations():
            # Loja sem nenhuma impressora de preparação não é defeito DESTA
            # estação, e pintar vermelho aqui seria alarme aceso para sempre.
            return unfold_badge("sem impressora de preparação na loja", "base")
        destination = resolve_destination(station_ref=obj.ref)
        detail = destination.problem or destination.label
        return format_html(
            "{} {}",
            unfold_badge(destination.status_label, "green" if destination.available else "red"),
            detail,
        )
    print_destination_display.short_description = "Destino resolvido agora"

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
