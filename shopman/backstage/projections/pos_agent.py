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


def build_agent_install(terminal, *, download_url: str, os_key: str = DEFAULT_OS) -> AgentInstallGuide:
    from shopman.backstage.services.pos_hardware import ADAPTER_AGENT, CashDrawerConfig

    config = CashDrawerConfig.from_terminal(terminal)
    available = AGENT_SOURCE.is_file()
    os_key = normalize_os(os_key)

    blocker = ""
    if not config.declared or config.adapter != ADAPTER_AGENT:
        blocker = "Este terminal está como gaveta de chave. Mude para “Pelo agente local” e salve."
    elif config.misconfigured_reason:
        blocker = config.misconfigured_reason
    elif not available:
        # Falha honesta em vez de um download que devolve 500 no balcão.
        blocker = "O arquivo do agente não veio nesta instalação. Confira o COPY tools do Dockerfile."

    label = next(lbl for key, lbl, _ in OS_CHOICES if key == os_key)
    return AgentInstallGuide(
        terminal_ref=terminal.ref,
        terminal_label=terminal.label or terminal.ref,
        adapter=config.adapter if config.declared else "",
        configured=config.kicks_by_software and not config.misconfigured_reason,
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
        steps=_steps(config, os_key) if not blocker else (),
    )


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
_OS_RUNTIME = {
    "linux": {
        "python": "python3",
        "logs": "journalctl --user -u nelson-pos-counter -f",
        "logs_note": "O agente registra cada abertura e cada impressão no journal do sistema.",
        "carry": "Pendrive, scp, ou copiar e colar num editor, o que for mais fácil.",
    },
    "macos": {
        "python": "python3",
        "logs": "tail -f ~/.local/share/nelson-pos-counter/counter-agent.log",
        "logs_note": "No macOS o launchd não guarda a saída, então o agente escreve num arquivo.",
        "carry": "Pendrive, AirDrop, ou copiar e colar num editor.",
    },
    "windows": {
        "python": "python",
        "logs": "type %LOCALAPPDATA%\\NelsonPosCounter\\counter-agent.log",
        "logs_note": "No Windows o agente roda sem janela de console, então escreve num arquivo.",
        "carry": "Pendrive ou copiar e colar num editor (Bloco de Notas serve).",
    },
}


def _steps(config, os_key: str) -> tuple[AgentStep, ...]:
    runtime = _OS_RUNTIME[os_key]
    origin = _pos_origin()
    install = f"{runtime['python']} {AGENT_FILENAME} --install --token {config.token}"
    if origin:
        install += f" --origin {origin}"

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
                f"ela que o recibo sai hoje. O token já vai no comando, então não há nada "
                f"para copiar de volta para cá. {prereq}"
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
        AgentStep(
            title="Se algo der errado",
            detail=f"{runtime['logs_note']} É a verdade física do balcão.",
            command=runtime["logs"],
        ),
    )


def _source_build() -> str:
    """Mesma impressão digital que o agente calcula de si mesmo.

    Hash do conteúdo, não número escrito à mão: ninguém precisa lembrar de
    bumpar, e o carimbo da tela bate com o que o `/health` do balcão responde.
    """
    import hashlib

    return hashlib.sha256(AGENT_SOURCE.read_bytes()).hexdigest()[:8]


def _pos_origin() -> str:
    """Origem que o agente vai aceitar — a do PDV, não um chute.

    Vazio quando o deployment não declarou `SHOPMAN_POS_BASE_URL`: aí o
    instalador usa o default dele, e é melhor não escrever um endereço errado
    no comando do que fingir que sabemos.
    """
    return str(getattr(settings, "SHOPMAN_POS_BASE_URL", "") or "").rstrip("/")
