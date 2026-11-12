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
"""

from __future__ import annotations

from dataclasses import dataclass

#: Propósito → o que ele é. A chave é o que vai em ``Shop.ai_routes``.
PURPOSES = {
    "concierge": "Concierge: atendimento no WhatsApp",
    "triage": "Triagem das mensagens de clientes",
    "intents": "Leitura de intenções das mensagens (e seu placar)",
    "copy": "Sugestão de texto no catálogo",
    "marketing": "Sugestão de texto nos anúncios",
    "recipe": "Leitura de receita por foto ou texto",
    "scenarios": "Cenários do B.I.",
    "benchmark": "Placar do de-para do B.I.",
    "decision": "Modelo de decisão (Jev) da triagem e dos placares",
}

#: Propósitos que mandam texto de cliente ao provedor.
CUSTOMER_TEXT_PURPOSES = frozenset({"concierge", "triage", "intents"})


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
    price_input_per_m: float | None
    price_output_per_m: float | None

    @property
    def priced(self) -> bool:
        return self.price_input_per_m is not None and self.price_output_per_m is not None


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
    return Resolved(
        ref=connection.ref,
        protocol=connection.protocol,
        base_url=(connection.base_url or "").strip(),
        api_key=api_key,
        model=model,
        customer_text_approved=connection.customer_text_approved,
        price_input_per_m=_float(connection.price_input_per_m),
        price_output_per_m=_float(connection.price_output_per_m),
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
    return anthropic.Anthropic(**kwargs), resolved.model


def connection_price(model: str) -> tuple[float, float] | None:
    """Preço cadastrado numa conexão ativa cujo modelo padrão é ``model``."""
    from shopman.shop.models import AIConnection

    connection = (
        AIConnection.objects.filter(is_active=True, model=model)
        .exclude(price_input_per_m=None)
        .exclude(price_output_per_m=None)
        .first()
    )
    if connection is None:
        return None
    return float(connection.price_input_per_m), float(connection.price_output_per_m)


def _float(value) -> float | None:
    return None if value is None else float(value)
