"""Ligar e desligar IA em teste, pelo mesmo caminho do Admin (``AIConnection``).

Substitui o ``settings.AI_ASSIST_API_KEY = ...`` de antes: a chave agora mora
no banco, então ligar a IA num teste é cadastrar a conexão.
"""

from __future__ import annotations

from shopman.shop.models import AIConnection, AIProtocol, Shop


def configure_ai(
    api_key: str = "test-key",
    *,
    model: str = "claude-opus-5",
    protocol: str = AIProtocol.ANTHROPIC,
    customer_text: bool = True,
    base_url: str = "",
    ref: str = "",
) -> AIConnection | None:
    """A única conexão ativa do formato, com esta chave. ``api_key`` vazio desliga.

    Limpa as rotas da loja: sem rota, vale a única conexão ativa do formato, que é
    esta. As outras conexões do mesmo formato ficam inativas.
    """
    ref = ref or ("jev" if protocol == AIProtocol.JEV else "anthropic")
    AIConnection.objects.filter(protocol=protocol).exclude(ref=ref).update(is_active=False)
    for shop in Shop.objects.exclude(ai_routes={}):
        shop.ai_routes = {}
        shop.save(update_fields=["ai_routes"])
    connection, _created = AIConnection.objects.get_or_create(
        ref=ref, defaults={"name": ref, "protocol": protocol, "model": model}
    )
    connection.protocol = protocol
    connection.model = model
    connection.base_url = base_url
    connection.customer_text_approved = customer_text
    connection.is_active = bool(api_key)
    connection.set_api_key(api_key)
    connection.save()
    return connection if api_key else None


def configure_jev(api_key: str = "jev-test-key", *, customer_text: bool = True, model: str = "jev-latest"):
    return configure_ai(api_key, protocol=AIProtocol.JEV, model=model, customer_text=customer_text)
