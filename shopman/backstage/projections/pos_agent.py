"""Instalação do agente do balcão — o que a tela do Admin mostra.

O dono já está no Admin configurando o terminal; obrigá-lo a sair dali para
caçar um arquivo no repositório é atrito bobo. Esta projection monta o que a
página precisa: o comando **já preenchido** com o token, a fila e a origem
daquele balcão, e o estado de cada pré-requisito.

O token vive aqui de propósito. Ele não abre nada além da gaveta daquele
terminal, e a alternativa — transcrever 43 caracteres de um terminal Linux para
o formulário — errava calada e só aparecia como 401 na hora de dar troco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

#: Onde o agente mora na árvore do deploy. O Dockerfile copia `tools/` só por
#: causa desta tela — se o download quebrar em produção e funcionar local, é
#: aqui que se olha primeiro.
AGENT_SOURCE = Path(settings.BASE_DIR) / "tools" / "pos-counter-agent" / "counter_agent.py"

AGENT_FILENAME = "counter_agent.py"

#: Linux é o SO **oficial** do balcão — é para onde a máquina do caixa vai. Os
#: outros dois existem por uma razão concreta, não por completude: o caixa ainda
#: roda Windows e a troca não dá para ser feita com a loja aberta, e o dono
#: precisa conseguir testar do Mac dele.
OS_CHOICES = (
    ("linux", "Linux", "o oficial"),
    ("windows", "Windows", "o caixa hoje"),
    ("macos", "macOS", "para testar"),
)
DEFAULT_OS = "linux"


def normalize_os(value: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in {key for key, _, _ in OS_CHOICES} else DEFAULT_OS


@dataclass(frozen=True)
class AgentStep:
    """Um passo da instalação, com o comando pronto quando houver um."""

    title: str
    detail: str
    command: str = ""


@dataclass(frozen=True)
class OSOption:
    key: str
    label: str
    note: str
    active: bool
    url: str


@dataclass(frozen=True)
class AgentInstallGuide:
    terminal_ref: str
    terminal_label: str
    adapter: str
    configured: bool
    #: Por que este terminal ainda não está pronto, em uma frase. Vazio = pronto.
    blocker: str
    #: O arquivo existe nesta instalação? `False` = não veio na imagem.
    source_available: bool
    source_bytes: int
    #: Carimbo do arquivo que ESTA instalação entrega. O balcão só se atualiza
    #: pelo download daqui, e sem carimbo ninguém sabe se a máquina está com o
    #: atual — "reinstalei e continua igual" vira meia hora perdida.
    source_build: str
    download_url: str
    os_key: str = DEFAULT_OS
    os_label: str = "Linux"
    #: Aviso quando o SO escolhido não é o oficial. Vazio no Linux.
    os_caveat: str = ""
    os_options: tuple[OSOption, ...] = field(default_factory=tuple)
    steps: tuple[AgentStep, ...] = field(default_factory=tuple)
    #: Os comandos do dia a dia, prontos para copiar. Separados dos `steps`
    #: porque instalação se faz uma vez e diagnóstico se faz sempre — misturar
    #: obrigaria a reler o roteiro inteiro para achar o comando de conferir.
    commands: tuple[AgentStep, ...] = field(default_factory=tuple)
    #: Estado do relay visto pelo servidor. O segredo nunca volta: uma
    #: credencial emitida só pode ser substituída por outra.
    relay_active: bool = False
    relay_ready: bool = False
    relay_status_label: str = "Não pareado"
    relay_status_detail: str = ""
    relay_credential_ref: str = ""
    relay_credential_version: str = ""
    relay_can_issue: bool = False
    relay_blocker: str = ""
    #: Existe somente na resposta POST que acabou de emitir/rotacionar o
    #: bearer. Não é persistido, não entra em URL e não reaparece no GET.
    relay_install_command: str = ""
    relay_secret_once: str = ""


def build_agent_install(
    terminal,
    *,
    download_url: str,
    os_key: str = DEFAULT_OS,
    relay_bearer: str = "",
) -> AgentInstallGuide:
    from shopman.backstage.services.pos_hardware import DeviceAgentConfig

    config = DeviceAgentConfig.from_terminal(terminal)
    available = AGENT_SOURCE.is_file()
    os_key = normalize_os(os_key)
    relay = _relay_state(terminal)
    relay_server_url = _relay_server_url()

    relay_blocker = ""
    if not config.available:
        relay_blocker = "Configure primeiro o agente local deste terminal."
    else:
        from shopman.backstage.services.print_jobs import PrinterConfig

        printer = PrinterConfig.from_terminal(terminal)
        if not printer.accepts_preparation:
            relay_blocker = printer.problem or "Ative a impressora de preparação neste terminal."
        elif not relay_server_url:
            relay_blocker = "O endereço HTTPS da API de operadores não está configurado."

    blocker = ""
    if not config.declared:
        blocker = "Ative a impressora de preparação ou a gaveta pelo agente local e salve o terminal."
    elif config.misconfigured_reason:
        blocker = config.misconfigured_reason
    elif not available:
        # Falha honesta em vez de um download que devolve 500 no balcão.
        blocker = "O arquivo do agente não veio nesta instalação. Confira o COPY tools do Dockerfile."

    # Nunca deixar um chamador acidentalmente montar um comando incompleto com
    # bearer. A view valida antes de emitir, mas a projection também é uma
    # fronteira de segurança e deve falhar fechada por conta própria.
    effective_relay_bearer = relay_bearer if not relay_blocker and not blocker else ""
    label = next(lbl for key, lbl, _ in OS_CHOICES if key == os_key)
    steps = (
        _steps(
            config,
            os_key,
            relay_server_url=relay_server_url,
            station_ref=terminal.ref,
            relay_bearer=effective_relay_bearer,
        )
        if not blocker
        else ()
    )
    install_command = next((step.command for step in steps if "--install" in step.command), "")
    return AgentInstallGuide(
        terminal_ref=terminal.ref,
        terminal_label=terminal.label or terminal.ref,
        adapter="agent" if config.declared else "",
        configured=config.available,
        blocker=blocker,
        source_available=available,
        source_bytes=AGENT_SOURCE.stat().st_size if available else 0,
        source_build=_source_build() if available else "",
        download_url=download_url,
        os_key=os_key,
        os_label=label,
        os_caveat=_OS_CAVEATS.get(os_key, ""),
        os_options=tuple(
            OSOption(key=key, label=lbl, note=note, active=key == os_key, url=f"?so={key}")
            for key, lbl, note in OS_CHOICES
        ),
        steps=steps,
        # Os comandos do dia a dia saem MESMO com blocker: quando o terminal
        # está mal configurado é justamente quando alguém precisa rodar o
        # `--doctor` para descobrir o que falta.
        commands=_commands(os_key),
        relay_active=relay["active"],
        relay_ready=relay["ready"],
        relay_status_label=relay["label"],
        relay_status_detail=relay["detail"],
        relay_credential_ref=relay["credential_ref"],
        relay_credential_version=relay["credential_version"],
        relay_can_issue=not relay_blocker and not blocker,
        relay_blocker=relay_blocker,
        relay_install_command=install_command if effective_relay_bearer else "",
        relay_secret_once=effective_relay_bearer,
    )


def _relay_server_url() -> str:
    """URL canônica que o agente usa sem depender do host aberto no Admin."""
    from urllib.parse import urlsplit

    configured = str(getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or "").strip()
    if not configured:
        return ""
    candidate = configured if "://" in configured else f"https://{configured}"
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return f"https://{parsed.netloc}"


def _relay_state(terminal) -> dict[str, object]:
    """Resumo não sensível da credencial; nunca tenta reconstruir o bearer."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.backstage.models import PrintAgentCredential
    from shopman.backstage.services.print_jobs import LEASE_SECONDS

    credential = (
        PrintAgentCredential.objects.filter(terminal=terminal, is_active=True).order_by("-last_seen_at", "-pk").first()
    )
    if credential is None:
        return {
            "active": False,
            "ready": False,
            "label": "Não pareado",
            "detail": "Gere um comando completo para a estação buscar impressões enviadas por tablets.",
            "credential_ref": "",
            "credential_version": "",
        }
    ready = bool(
        credential.last_seen_at and credential.last_seen_at >= timezone.now() - timedelta(seconds=LEASE_SECONDS)
    )
    return {
        "active": True,
        "ready": ready,
        "label": "Relay conectado" if ready else "Aguardando o agente",
        "detail": (
            "A estação está buscando trabalhos e pode receber impressões de outros dispositivos."
            if ready
            else "A credencial existe, mas a estação ainda não se apresentou. Repareie somente se o comando anterior não estiver mais disponível."
        ),
        "credential_ref": str(credential.ref),
        "credential_version": f"{credential.ref}:{credential.rotated_at.isoformat()}",
    }


_OS_CAVEATS = {
    "windows": (
        "O balcão vai virar Linux, que é o sistema oficial. O Windows existe porque a "
        "máquina do caixa ainda roda Windows e a troca não pode ser feita com a loja aberta; "
        "aqui o agente entrega os bytes pelo spooler do próprio Windows."
    ),
    "macos": (
        "Caminho de teste, não o do balcão. Funciona igual ao Linux (mesmo comando de "
        "impressão), mas quem vai atender o caixa é a máquina Linux."
    ),
}

#: Só duas coisas mudam de verdade entre os sistemas: o nome do interpretador e
#: onde o agente deixa o registro das aberturas. O comando de instalação e o
#: mecanismo de envio são os mesmos no Linux e no macOS (ambos CUPS); o Windows
#: troca o mecanismo por baixo, mas não a linha que a pessoa digita.
#: Onde o agente FICA depois de instalado. Os comandos do dia a dia apontam
#: para cá, não para a pasta de downloads: o arquivo baixado é descartável — o
#: instalador se copia sozinho — e mandar o dono rodar `--doctor` no Downloads
#: faz ele diagnosticar uma cópia que não é a que está no ar.
_OS_RUNTIME = {
    "linux": {
        "installed": "~/.local/share/nelson-pos-counter/counter_agent.py",
        "python": "python3",
        "logs": "journalctl --user -u nelson-pos-counter -f",
        "logs_note": "O agente registra cada abertura e cada impressão no journal do sistema.",
        "carry": "Pendrive, scp, ou copiar e colar num editor, o que for mais fácil.",
    },
    "macos": {
        "installed": "~/.local/share/nelson-pos-counter/counter_agent.py",
        "python": "python3",
        "logs": "tail -f ~/.local/share/nelson-pos-counter/counter-agent.log",
        "logs_note": "No macOS o launchd não guarda a saída, então o agente escreve num arquivo.",
        "carry": "Pendrive, AirDrop, ou copiar e colar num editor.",
    },
    "windows": {
        "installed": "%LOCALAPPDATA%\\NelsonPosCounter\\counter_agent.py",
        "python": "python",
        "logs": "type %LOCALAPPDATA%\\NelsonPosCounter\\counter-agent.log",
        "logs_note": "No Windows o agente roda sem janela de console, então escreve num arquivo.",
        "carry": "Pendrive ou copiar e colar num editor (Bloco de Notas serve).",
    },
}


def _commands(os_key: str) -> tuple[AgentStep, ...]:
    """Todo comando que o balcão pode precisar, pronto para copiar.

    Existe porque a alternativa é o dono transcrever comando de uma conversa
    para o terminal — e cada transcrição é uma chance de errar um caractere e
    concluir que o defeito é da impressora. Nenhum comando desta casa deveria
    morar fora da tela onde ele é usado.
    """
    runtime = _OS_RUNTIME[os_key]
    agente = f"{runtime['python']} {runtime['installed']}"
    return (
        AgentStep(
            title="Está tudo certo neste balcão?",
            detail=(
                "Um relatório: a versão instalada contra a que está no ar, a config, o "
                "serviço, o serviço antigo e a impressora. Não para no primeiro problema — "
                "varre tudo e diz o que fazer em cada linha."
            ),
            command=f"{agente} --doctor",
        ),
        AgentStep(
            title="A gaveta abre?",
            detail="Manda os cinco bytes direto, sem passar pelo navegador. Se abrir aqui e não abrir no PDV, o problema é de rede ou token, não da impressora.",
            command=f"{agente} --kick",
        ),
        AgentStep(
            title="A impressora está boa?",
            detail="Sai uma página com acento, régua de largura e QR. É o papel que responde, não o palpite.",
            command=f"{agente} --test-print",
        ),
        AgentStep(
            title="Dá para saber se a gaveta ficou aberta?",
            detail=(
                "Ele conduz o teste: pede a gaveta fechada, lê; pede aberta, lê de novo; e "
                "compara. Se der certo, o sistema pode passar a avisar quando alguém deixa a "
                "gaveta aberta. Se não der, ele diz que por este caminho não dá."
            ),
            command=f"{agente} --drawer-status",
        ),
        AgentStep(
            title="O que o agente registrou",
            detail=f"{runtime['logs_note']} É a verdade física do balcão.",
            command=runtime["logs"],
        ),
    )


def _steps(
    config,
    os_key: str,
    *,
    relay_server_url: str = "",
    station_ref: str = "",
    relay_bearer: str = "",
) -> tuple[AgentStep, ...]:
    runtime = _OS_RUNTIME[os_key]
    origins = _operator_origins()
    install = f"{runtime['python']} {AGENT_FILENAME} --install --token {config.token}"
    for origin in origins:
        install += f" --origin {origin}"
    if relay_bearer:
        install += f" --server-url {relay_server_url} --station {station_ref} --relay-token-prompt"

    prereq = (
        "Precisa do Python instalado. O Windows não traz de fábrica: se o comando não for "
        "reconhecido, instale pela Microsoft Store (procure por Python) e tente de novo."
        if os_key == "windows"
        else "O Python já vem instalado neste sistema."
    )

    return (
        AgentStep(
            title="Leve o arquivo até a máquina",
            detail=(
                f"É um arquivo só, sem instalar mais nada junto. {runtime['carry']} Ele não "
                "precisa ficar em lugar nenhum especial: o instalador se copia sozinho para "
                "o lugar certo."
            ),
        ),
        AgentStep(
            title="Rode o instalador",
            detail=(
                "Ele lista as impressoras e pergunta qual é a térmica. Ela já existe, é por "
                "ela que o recibo sai hoje. O token já vai no comando, então não há nada "
                "para copiar de volta para cá. "
                + (
                    "Este comando também liga o relay: depois dele, um tablet pode mandar a etiqueta para esta estação. "
                    if relay_bearer
                    else ""
                )
                + prereq
            ),
            command=install,
        ),
        AgentStep(
            title="Confirme com o olho",
            detail=(
                "No PDV, antesala do caixa, botão “Testar gaveta”. Ele diz se a fila respondeu; "
                "se a gaveta abriu, quem sabe é você. Se a fila responder e a gaveta não abrir, "
                "o cabo dela na impressora é o primeiro lugar para olhar."
            ),
        ),
    )


def _source_build() -> str:
    """Mesma impressão digital que o agente calcula de si mesmo.

    Hash do conteúdo, não número escrito à mão: ninguém precisa lembrar de
    bumpar, e o carimbo da tela bate com o que o `/health` do balcão responde.
    """
    import hashlib

    return hashlib.sha256(AGENT_SOURCE.read_bytes()).hexdigest()[:8]


_OPERATOR_BASE_URL_SETTINGS = (
    "SHOPMAN_POS_BASE_URL",
    "SHOPMAN_ORDERS_BASE_URL",
    "SHOPMAN_KDS_BASE_URL",
    "SHOPMAN_PRODUCTION_BASE_URL",
    "SHOPMAN_MARKETING_BASE_URL",
    "SHOPMAN_BI_BASE_URL",
    "SHOPMAN_PURCHASE_BASE_URL",
)


def _operator_origins() -> tuple[str, ...]:
    """Origem exata de cada app operacional autorizado a falar com o agente.

    O agente continua preso à loopback. Esta lista não o publica: apenas evita
    que o CORS transforme ``/print`` numa exclusividade acidental do PDV quando
    Produção, Gestor ou outro app autorizado roda no mesmo dispositivo.
    """
    from urllib.parse import urlsplit

    origins: list[str] = []
    for setting_name in _OPERATOR_BASE_URL_SETTINGS:
        value = str(getattr(settings, setting_name, "") or "").strip()
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)
