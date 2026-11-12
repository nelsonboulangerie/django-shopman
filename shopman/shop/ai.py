"""A porta única de IA: toda função que fala com um modelo passa por aqui.

Cada função tem um **propósito** (``PURPOSES``). A loja diz, em
``Shop.ai_routes``, qual ``AIConnection`` e qual modelo cada propósito usa. Sem
rota para o propósito vale a rota ``default``; sem ela, a única conexão ativa
do formato. Cadastrar uma conexão só basta para tudo funcionar.

Texto de cliente (Concierge, triagem, leitura de intenções) só vai para conexão
marcada como ``customer_text_approved``: credencial presente não liga provedor
(LGPD; a mesma regra do Marketing).

Quem chama recebe um cliente pronto (``anthropic_client``) ou a conexão
resolvida (``resolve``), nunca lê chave nem cria cliente do SDK.

Toda chamada paga passa pelo freio e pelo medidor (``shopman.shop.ai_governor``):
a loja desliga a IA ou põe teto de gasto por dia em ``Shop.ai_limits``, e cada
chamada vira uma linha em ``AiInvocation``. Desligada ou no teto, a função se
comporta como não configurada.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from urllib.parse import urlparse

#: Propósito → o que ele é. A chave é o que vai em ``Shop.ai_routes``.
PURPOSES = {
    "concierge": "Concierge: atendimento no WhatsApp",
    "triage": "Triagem das mensagens de clientes",
    "intents": "Leitura de intenções das mensagens (e seu placar)",
    "labeling": "Pré-rótulo do gabarito do piloto de intenções",
    "copy": "Sugestão de texto no catálogo",
    "marketing": "Sugestão de texto nos anúncios",
    "recipe": "Leitura de receita por foto ou texto",
    "scenarios": "Cenários do B.I.",
    "benchmark": "Placar do de-para do B.I.",
    "decision": "Modelo de decisão (Jev) da triagem e dos placares",
}

#: Propósitos que mandam texto de cliente ao provedor.
CUSTOMER_TEXT_PURPOSES = frozenset({"concierge", "triage", "intents", "labeling"})


class AINotConfigured(Exception):
    """O propósito não tem conexão utilizável. A mensagem diz por quê, para o Admin."""


@dataclass(frozen=True)
class Resolved:
    ref: str
    protocol: str
    base_url: str
    api_key: str
    model: str
    customer_text_approved: bool

    @property
    def extras(self) -> frozenset[str]:
        return extras_for(self.base_url)


def _protocol_for(purpose: str) -> str:
    from shopman.shop.models import AIProtocol

    return AIProtocol.JEV if purpose == "decision" else AIProtocol.ANTHROPIC


def _routes() -> dict:
    from shopman.shop.models import Shop

    shop = Shop.load()
    routes = getattr(shop, "ai_routes", None) if shop else None
    return routes if isinstance(routes, dict) else {}


def _route(purpose: str) -> dict:
    routes = _routes()
    for key in (purpose, "default"):
        route = routes.get(key)
        if isinstance(route, dict) and route.get("connection"):
            # A rota default não serve ao Jev: formato diferente.
            if key == "default" and purpose == "decision":
                continue
            return route
    return {}


def explain(purpose: str) -> str:
    """Por que o propósito não está configurado, ou vazio se está."""
    try:
        resolve(purpose)
    except AINotConfigured as exc:
        return str(exc)
    return ""


def resolve(purpose: str) -> Resolved:
    """A conexão e o modelo do propósito. Levanta ``AINotConfigured`` com o motivo."""
    from shopman.shop.models import AIConnection

    if purpose not in PURPOSES:
        raise ValueError(f"propósito de IA desconhecido: {purpose}")
    protocol = _protocol_for(purpose)
    route = _route(purpose)
    active = AIConnection.objects.filter(is_active=True, protocol=protocol)
    if route:
        connection = active.filter(ref=route["connection"]).first()
        if connection is None:
            raise AINotConfigured(
                f"a rota de IA '{purpose}' aponta para a conexão '{route['connection']}', "
                "que não existe, está inativa ou é de outro formato"
            )
    else:
        candidates = list(active[:2])
        if not candidates:
            raise AINotConfigured(f"nenhuma conexão de IA ativa no formato {protocol} (Admin → Conexões de IA)")
        if len(candidates) > 1:
            raise AINotConfigured(
                f"há mais de uma conexão de IA no formato {protocol}; diga qual usar em Loja → rotas de IA"
            )
        connection = candidates[0]
    api_key = connection.api_key
    if not api_key:
        raise AINotConfigured(f"a conexão de IA '{connection.ref}' está sem chave")
    if purpose in CUSTOMER_TEXT_PURPOSES and not connection.customer_text_approved:
        raise AINotConfigured(
            f"a conexão de IA '{connection.ref}' não está liberada para receber mensagem de cliente"
        )
    model = str(route.get("model") or connection.model or "").strip()
    if not model:
        raise AINotConfigured(f"a conexão de IA '{connection.ref}' está sem modelo")
    from shopman.shop import ai_governor

    ai_governor.check(purpose)
    return Resolved(
        ref=connection.ref,
        protocol=connection.protocol,
        base_url=(connection.base_url or "").strip(),
        api_key=api_key,
        model=model,
        customer_text_approved=connection.customer_text_approved,
    )


def is_configured(purpose: str) -> bool:
    try:
        resolve(purpose)
    except AINotConfigured:
        return False
    return True


def anthropic_client(purpose: str, *, timeout: float | None = None, max_retries: int | None = None):
    """``(cliente, modelo)`` no formato Anthropic para o propósito.

    O endereço da conexão vai para ``base_url``: é o que deixa DeepSeek, Kimi ou
    GLM responderem no lugar da Anthropic sem mudar o código de quem chama.
    """
    resolved = resolve(purpose)
    import anthropic

    kwargs: dict = {"api_key": resolved.api_key}
    if resolved.base_url:
        kwargs["base_url"] = resolved.base_url
    if timeout is not None:
        kwargs["timeout"] = timeout
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    client = FittedClient(
        anthropic.Anthropic(**kwargs),
        resolved.extras,
        purpose=purpose,
        connection_ref=resolved.ref,
        default_model=resolved.model,
    )
    return client, resolved.model


# ── O pedido que cada provedor entende ──────────────────────────────────────
#
# Quem chama escreve o pedido completo, no formato Anthropic, com os extras que
# melhoram a resposta: ``effort``, raciocínio (``thinking``), saída estruturada
# (``output_config.format``) e cache de prompt (``cache_control``). Cada provedor
# compatível aceita só parte disso, e o que ele não aceita vira erro 400. A porta
# ajusta o pedido ao provedor, e quem chama não precisa saber qual é.

#: Os extras do formato Anthropic.
EXTRAS = frozenset({"effort", "thinking", "structured_output", "prompt_cache"})

#: O que cada provedor aceita, pelo host do endereço da conexão. Endereço vazio é
#: a Anthropic. Host fora da tabela recebe só o básico: pedir de menos nunca
#: quebra, pedir de mais dá 400. DeepSeek conforme a tabela de compatibilidade
#: dela (api-docs.deepseek.com/guides/anthropic_api, lida em 12/11/2026): aceita
#: ``effort`` e ``thinking``, ignora ``cache_control``, e o ``output_config``
#: dela é só ``effort``.
EXTRAS_BY_HOST = {
    "api.anthropic.com": EXTRAS,
    "api.deepseek.com": frozenset({"effort", "thinking", "prompt_cache"}),
}


def extras_for(base_url: str) -> frozenset[str]:
    if not base_url:
        return EXTRAS
    host = (urlparse(base_url).hostname or "").lower()
    return EXTRAS_BY_HOST.get(host, frozenset())


def fit_request(request: dict, extras: frozenset[str]) -> dict:
    """O pedido sem o que o provedor não aceita.

    Saída estruturada não some: vira instrução no sistema com o mesmo esquema, e a
    validação de quem chama continua conferindo a resposta.
    """
    if extras >= EXTRAS:
        return request
    fitted = dict(request)
    if "thinking" not in extras:
        fitted.pop("thinking", None)
    output = dict(fitted.pop("output_config", None) or {})
    schema_format = output.pop("format", None)
    if "effort" not in extras:
        output.pop("effort", None)
    if schema_format and "structured_output" in extras:
        output["format"] = schema_format
    if output:
        fitted["output_config"] = output
    if "prompt_cache" not in extras:
        fitted = _without_cache_control(fitted)
    if schema_format and "structured_output" not in extras:
        schema = schema_format.get("schema") if isinstance(schema_format, dict) else None
        if schema:
            fitted["system"] = _with_text(
                fitted.get("system"),
                "Responda somente com um objeto JSON válido, sem texto antes ou depois, neste "
                f"esquema JSON:\n{json.dumps(schema, ensure_ascii=False)}",
            )
    return fitted


def _without_cache_control(request: dict) -> dict:
    request = copy.deepcopy(request)
    for key in ("system", "tools"):
        if isinstance(request.get(key), list):
            for block in request[key]:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    for message in request.get("messages") or []:
        if isinstance(message, dict) and isinstance(message.get("content"), list):
            for block in message["content"]:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    return request


def _with_text(system, text: str):
    if not system:
        return text
    if isinstance(system, str):
        return f"{system}\n\n{text}"
    return [*system, {"type": "text", "text": text}]


class _FittedMessages:
    def __init__(self, messages, extras: frozenset[str], *, purpose: str, connection_ref: str, default_model: str):
        self._messages = messages
        self._extras = extras
        self._purpose = purpose
        self._connection_ref = connection_ref
        self._default_model = default_model

    def create(self, **request):
        """O pedido ajustado ao provedor, freado e medido (``ai_governor``)."""
        from shopman.shop import ai_governor

        fitted = fit_request(request, self._extras)
        model = str(fitted.get("model") or self._default_model)
        estimate = ai_governor.estimate_usd(
            model,
            tokens_in=ai_governor.estimate_input_tokens(fitted),
            tokens_out=int(fitted.get("max_tokens") or ai_governor.DEFAULT_MAX_OUTPUT_TOKENS),
        )
        with ai_governor.metered(
            self._purpose,
            connection_ref=self._connection_ref,
            model=model,
            estimate_usd_value=estimate,
        ) as box:
            response = self._messages.create(**fitted)
            box["usage"] = getattr(response, "usage", None)
        return response

    def __getattr__(self, name):
        return getattr(self._messages, name)


class FittedClient:
    """O cliente do SDK com ``messages.create`` ajustado ao provedor; o resto passa direto."""

    def __init__(self, client, extras: frozenset[str], *, purpose: str, connection_ref: str, default_model: str):
        self._client = client
        self.messages = _FittedMessages(
            client.messages,
            extras,
            purpose=purpose,
            connection_ref=connection_ref,
            default_model=default_model,
        )

    def __getattr__(self, name):
        return getattr(self._client, name)


#: Endereço oficial do Jev quando a conexão não diz outro.
JEV_DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"


def jev_endpoint(*, customer_text: bool) -> tuple[str, str, str]:
    """``(url, chave, modelo)`` do Jev (propósito ``decision``).

    ``customer_text`` diz se o pedido leva mensagem de cliente: aí a conexão
    precisa estar liberada para isso, como qualquer outra.
    """
    resolved = resolve("decision")
    if customer_text and not resolved.customer_text_approved:
        raise AINotConfigured(
            f"a conexão de IA '{resolved.ref}' não está liberada para receber mensagem de cliente"
        )
    return resolved.base_url or JEV_DEFAULT_URL, resolved.api_key, resolved.model


def jev_post(session, url: str, api_key: str, body: dict, *, timeout: float, model: str):
    """``POST`` ao Jev, freado e medido como qualquer chamada paga. Devolve a resposta HTTP.

    O custo vem do ``usage.input_tokens`` da resposta (saída grátis); sem ele, a
    estimativa pelo tamanho do corpo.
    """
    from shopman.shop import ai_governor

    tokens_in = ai_governor.estimate_input_tokens({"messages": body})
    estimate = ai_governor.estimate_usd(model, tokens_in=tokens_in, tokens_out=0, protocol="jev")
    with ai_governor.metered(
        "decision", connection_ref="jev", model=model, estimate_usd_value=estimate, protocol="jev"
    ) as box:
        response = session.post(url, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
        box["usage"] = {"input_tokens": tokens_in}
        try:
            usage = response.json().get("usage") if response.status_code < 400 else None
        except Exception:
            usage = None
        if isinstance(usage, dict) and usage.get("input_tokens") is not None:
            box["usage"] = {"input_tokens": usage.get("input_tokens")}
    return response
