"""O laço com o modelo: prompt, janela de memória, ferramentas, resposta.

Um turno é: montar o sistema (estável cacheado + dinâmico), enviar a janela de
mensagens, e enquanto o modelo pedir ferramenta, executar e devolver o
resultado, até ele responder em texto. O laço tem teto de iterações; no teto,
a última ida ao modelo é sem ferramentas, para sair com uma frase e não com
silêncio.

O que este módulo NÃO faz: falar com o ManyChat (``service``/``transport``),
gravar no banco (``service``), decidir preço (``tools``). Ele recebe a
história já persistida e devolve o que aconteceu, para quem chamou gravar.

Sobre os blocos de raciocínio (``thinking``): dentro do turno eles voltam ao
modelo intactos, como a API pede. Na transcrição persistida eles são
descartados: a janela de memória corta turnos antigos inteiros, e um histórico
sem blocos de raciocínio é o formato que qualquer modelo da família aceita.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

from shopman.shop.models import Conversation, ConversationMessage

from . import tools as tools_module
from .tools import ToolContext

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 6000

#: Sintaxe interna de chamada de ferramenta que o modelo pode vazar como texto ou
#: dentro de argumentos (tags de parâmetro, `name="tool">`). Medido em 04/09/2026:
#: seis chamadas com `category` contendo a tag e a resposta final com o lixo.
#: Montado por partes para o próprio arquivo não carregar a sequência literal.
_TAG_OPEN = "<" + "/?" + "\\w*" + "antml" + "[^>]*>"
_LEAK_RE = re.compile(_TAG_OPEN + "|<" + "/?parameter[^>]*>|<" + "/?invoke[^>]*>|" + 'name="[a-z_]+">', re.I)
#: Quantas vezes a mesma chamada (ferramenta + argumentos) pode se repetir num turno.
MAX_REPEATED_CALLS = 2


def clean_text(value: str) -> str:
    """Remove sintaxe vazada e linhas que sobraram só com ela."""
    text = _LEAK_RE.sub("", str(value or ""))
    lines = [ln for ln in text.splitlines() if ln.strip() not in ("", "?", '"', "{}")]
    return "\n".join(lines).strip()


def clean_arguments(arguments: dict) -> dict:
    """Argumentos com sintaxe vazada viram vazio: melhor a ferramenta responder
    "sem filtro" do que buscar a categoria "<tag>"."""
    cleaned = {}
    for key, value in (arguments or {}).items():
        if isinstance(value, str):
            cleaned[key] = "" if _LEAK_RE.search(value) else value
        else:
            cleaned[key] = value
    return cleaned


class AgentRefused(Exception):
    """O modelo recusou o turno (``stop_reason = refusal``)."""


@dataclass
class AgentOutcome:
    reply_text: str
    messages: list[dict] = field(default_factory=list)  # formato da API, na ordem
    usage: dict = field(default_factory=dict)
    handoff: bool = False
    handoff_reason: str = ""
    extra_replies: list[str] = field(default_factory=list)
    tool_events: list[dict] = field(default_factory=list)
    order_ref: str = ""


def _config() -> dict:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


def build_client():
    import anthropic

    api_key = (getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip()
    return anthropic.Anthropic(api_key=api_key, timeout=45.0, max_retries=2)


# ── Memória ───────────────────────────────────────────────────────────


def history_for(conversation: Conversation) -> list[dict]:
    """A janela de mensagens no formato da API, começando numa mensagem do cliente.

    Pares ferramenta/resultado nunca ficam pela metade: a janela avança até a
    primeira mensagem inbound, e tudo que vier antes dela fica de fora.
    """
    window = int(_config().get("window_messages") or 40)
    rows = list(
        conversation.messages.exclude(kind=ConversationMessage.Kind.NOTE).order_by("-id")[:window]
    )
    rows.reverse()
    while rows and rows[0].kind != ConversationMessage.Kind.INBOUND:
        rows.pop(0)

    messages: list[dict] = []
    for row in rows:
        content = row.content or ([{"type": "text", "text": row.text}] if row.text else [])
        if not content:
            continue
        messages.append({"role": row.role, "content": _clean_history_content(content)})
    return messages


def _clean_history_content(content: list) -> list:
    """Transcrição antiga pode carregar sintaxe vazada; ela não volta ao modelo."""
    cleaned = []
    for block in content:
        if not isinstance(block, dict):
            cleaned.append(block)
            continue
        kind = block.get("type")
        if kind == "tool_use" and isinstance(block.get("input"), dict):
            cleaned.append({**block, "input": clean_arguments(block["input"])})
        elif kind == "text":
            text = clean_text(block.get("text", ""))
            cleaned.append({**block, "text": text or "…"})
        else:
            cleaned.append(block)
    return cleaned


# ── Serialização ──────────────────────────────────────────────────────


def _block_to_dict(block) -> dict | None:
    kind = getattr(block, "type", "")
    if kind == "text":
        return {"type": "text", "text": clean_text(block.text)}
    if kind == "tool_use":
        # Persistido LIMPO: a transcrição volta ao modelo como exemplo do formato, e
        # exemplo com lixo ensina lixo (foi assim que um turno ruim virou três).
        arguments = block.input if isinstance(block.input, dict) else {}
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": clean_arguments(arguments)}
    # thinking / redacted_thinking e afins: fora da transcrição (ver docstring).
    return None


def _content_for_replay(response) -> list:
    """O conteúdo que volta ao modelo dentro do MESMO turno: intacto."""
    return list(response.content)


def _persistable_content(response) -> list[dict]:
    return [d for d in (_block_to_dict(b) for b in response.content) if d is not None]


def _text_of(response) -> str:
    return "\n".join(
        (block.text or "") for block in response.content if getattr(block, "type", "") == "text"
    ).strip()


def _tool_result_text(result: dict) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "…"
    return text


def _accumulate(usage: dict, response) -> None:
    u = getattr(response, "usage", None)
    if u is None:
        return
    for name in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = getattr(u, name, None)
        if value:
            usage[name] = int(usage.get(name, 0)) + int(value)


def _cart_summary(conversation: Conversation, channel_ref: str) -> str:
    try:
        from shopman.shop.projections.cart import build_cart
        from shopman.shop.services import cart as cart_service

        if not conversation.session_key:
            return ""
        session = cart_service.get_open_session(session_key=conversation.session_key, channel_ref=channel_ref)
        if session is None or not session.items:
            return ""
        cart = build_cart(session.session_key, channel_ref)
        items = ", ".join(f"{line.qty}x {line.name}" for line in cart.lines[:6])
        return f"{items}; total {tools_module._money(cart.grand_total_q)}"
    except Exception:
        logger.debug("concierge.cart_summary degraded", exc_info=True)
        return ""


# ── O turno ───────────────────────────────────────────────────────────


def run_agent(*, conversation: Conversation, history: list[dict], client=None) -> AgentOutcome:
    """Roda um turno completo. ``history`` já contém a(s) mensagem(ns) do cliente."""
    from .prompt import build_system

    cfg = _config()
    model = str(cfg.get("model") or "claude-sonnet-5")
    max_tokens = int(cfg.get("max_tokens") or 1024)
    max_iterations = max(1, int(cfg.get("max_iterations") or 6))
    effort = str(cfg.get("effort") or "").strip()
    channel_ref = str(conversation.channel_ref or cfg.get("channel_ref") or "whatsapp")

    client = client or build_client()
    ctx = ToolContext(conversation=conversation, channel_ref=channel_ref)

    is_first_turn = not conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).exists()
    system = build_system(
        conversation,
        is_first_turn=is_first_turn,
        cart_summary=_cart_summary(conversation, channel_ref),
    )

    messages: list[dict] = list(history)
    outcome = AgentOutcome(reply_text="")
    usage: dict = {}
    seen_calls: dict[str, int] = {}

    for iteration in range(max_iterations + 1):
        request: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "tools": tools_module.TOOL_SPECS,
            "messages": messages,
        }
        if effort:
            request["output_config"] = {"effort": effort}
        if cfg.get("adaptive_thinking", True):
            # Com o raciocínio desligado o modelo às vezes escreve a chamada de
            # ferramenta como TEXTO, ou vaza tags nos argumentos. Ligado, a chamada
            # sai como bloco `tool_use`. Haiku 4.5 não aceita: desligue na config.
            request["thinking"] = {"type": "adaptive"}
        if iteration == max_iterations:
            # Teto de iterações: a última ida sai em texto, sem ferramenta.
            request["tool_choice"] = {"type": "none"}

        response = client.messages.create(**request)
        _accumulate(usage, response)

        stop = getattr(response, "stop_reason", "") or ""
        if stop == "refusal":
            raise AgentRefused(str(getattr(response, "stop_details", "") or "refusal"))

        tool_uses = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
        if stop != "tool_use" or not tool_uses:
            text = clean_text(_text_of(response))
            if stop == "max_tokens":
                logger.warning("concierge.agent max_tokens conversation=%s", conversation.pk)
            outcome.reply_text = text
            outcome.messages.append({"role": "assistant", "content": _persistable_content(response)})
            break

        messages.append({"role": "assistant", "content": _content_for_replay(response)})
        outcome.messages.append({"role": "assistant", "content": _persistable_content(response)})

        results = []
        for use in tool_uses:
            arguments = clean_arguments(use.input if isinstance(use.input, dict) else {})
            signature = f"{use.name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
            seen_calls[signature] = seen_calls.get(signature, 0) + 1
            if seen_calls[signature] > MAX_REPEATED_CALLS:
                # Repetir a mesma pergunta não muda a resposta: devolve ao modelo a
                # ordem de responder ao cliente com o que já tem.
                result = {
                    "ok": False,
                    "error": "repeated_call",
                    "message": "Esta chamada já foi feita com os mesmos argumentos. Responda ao cliente com o que já tem.",
                }
            else:
                result = tools_module.execute(use.name, arguments, ctx)
            outcome.tool_events.append({"name": use.name, "input": arguments, "ok": result.get("ok", True)})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": use.id,
                    "content": _tool_result_text(result),
                    **({"is_error": True} if result.get("ok") is False and result.get("error") == "tool_failed" else {}),
                }
            )
        messages.append({"role": "user", "content": results})
        outcome.messages.append({"role": "user", "content": results})

        if ctx.handoff:
            # A equipe assume: fecha o turno com o texto que o modelo já tinha (se
            # houver) e deixa a casa mandar a confirmação de handoff.
            outcome.reply_text = clean_text(_text_of(response))
            break

    outcome.usage = usage
    outcome.handoff = ctx.handoff
    outcome.handoff_reason = ctx.handoff_reason
    outcome.extra_replies = list(ctx.extra_replies)
    outcome.order_ref = ctx.order_ref
    return outcome
