"""Instalação do agente da gaveta — o que a tela do Admin mostra.

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
AGENT_SOURCE = Path(settings.BASE_DIR) / "tools" / "pos-drawer-agent" / "drawer_agent.py"

AGENT_FILENAME = "drawer_agent.py"


@dataclass(frozen=True)
class AgentStep:
    """Um passo da instalação, com o comando pronto quando houver um."""

    title: str
    detail: str
    command: str = ""


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
    download_url: str
    steps: tuple[AgentStep, ...] = field(default_factory=tuple)


def build_agent_install(terminal, *, download_url: str) -> AgentInstallGuide:
    from shopman.backstage.services.pos_hardware import ADAPTER_AGENT, CashDrawerConfig

    config = CashDrawerConfig.from_terminal(terminal)
    available = AGENT_SOURCE.is_file()

    blocker = ""
    if not config.declared or config.adapter != ADAPTER_AGENT:
        blocker = "Este terminal está como gaveta de chave. Mude para “Pelo agente local” e salve."
    elif config.misconfigured_reason:
        blocker = config.misconfigured_reason
    elif not available:
        # Falha honesta em vez de um download que devolve 500 no balcão.
        blocker = "O arquivo do agente não veio nesta instalação. Confira o COPY tools do Dockerfile."

    return AgentInstallGuide(
        terminal_ref=terminal.ref,
        terminal_label=terminal.label or terminal.ref,
        adapter=config.adapter if config.declared else "",
        configured=config.kicks_by_software and not config.misconfigured_reason,
        blocker=blocker,
        source_available=available,
        source_bytes=AGENT_SOURCE.stat().st_size if available else 0,
        download_url=download_url,
        steps=_steps(config) if not blocker else (),
    )


def _steps(config) -> tuple[AgentStep, ...]:
    origin = _pos_origin()
    install = f"python3 {AGENT_FILENAME} --install --token {config.token}"
    if origin:
        install += f" --origin {origin}"
    return (
        AgentStep(
            title="Leve o arquivo até o balcão",
            detail=(
                "É um arquivo só, sem dependência nenhuma. Pendrive, scp, ou copiar e colar "
                "num editor, o que for mais fácil. Ele não precisa ficar em lugar nenhum "
                "especial: o instalador se copia sozinho para o lugar certo."
            ),
        ),
        AgentStep(
            title="Rode o instalador, no terminal do balcão",
            detail=(
                "Ele lista as filas de impressão e pergunta qual é a da térmica. A fila já "
                "existe, é por ela que o recibo sai hoje. O token já vai no comando, então "
                "não há nada para copiar de volta para cá."
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
            detail="O agente registra cada abertura. É a verdade física do balcão.",
            command="journalctl --user -u nelson-pos-drawer -f",
        ),
    )


def _pos_origin() -> str:
    """Origem que o agente vai aceitar — a do PDV, não um chute.

    Vazio quando o deployment não declarou `SHOPMAN_POS_BASE_URL`: aí o
    instalador usa o default dele, e é melhor não escrever um endereço errado
    no comando do que fingir que sabemos.
    """
    return str(getattr(settings, "SHOPMAN_POS_BASE_URL", "") or "").rstrip("/")
