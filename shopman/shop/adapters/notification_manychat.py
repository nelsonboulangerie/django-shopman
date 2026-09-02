"""
ManyChat notification adapter — WhatsApp via ManyChat API.

WhatsApp is ALWAYS via ManyChat, never Meta Cloud API directly.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

MESSAGE_TEMPLATES: dict[str, str] = {
    "order_received": (
        "Olá{customer_name_greeting}! Recebemos seu pedido {order_ref}. "
        "O estabelecimento vai conferir a disponibilidade. Acompanhe: {tracking_url}"
    ),
    "order_accepted": (
        "Olá{customer_name_greeting}! Seu pedido {order_ref} foi confirmado."
        " Total: {total}. Obrigado pela preferência! \U0001f950{tracking_suffix}"
    ),
    "order_preparing": (
        "Olá{customer_name_greeting}! Seu pedido {order_ref} está em preparo."
        "{tracking_suffix}"
    ),
    "order_ready_pickup": (
        "Olá{customer_name_greeting}! Seu pedido {order_ref} está pronto"
        " para retirada! \U0001f389\n\nVenha buscar. Obrigado!{tracking_suffix}"
    ),
    "order_ready_delivery": (
        "Olá{customer_name_greeting}! Seu pedido {order_ref} está pronto"
        " e será enviado em breve! \U0001f4e6{tracking_suffix}"
    ),
    "order_dispatched": (
        "Olá{customer_name_greeting}! Seu pedido {order_ref} saiu para"
        " entrega! \U0001f697{courier_tracking_suffix}"
        "\nQuando receber, é só confirmar por aqui: {tracking_url}"
    ),
    "order_delivered": (
        "Pedido {order_ref} entregue. Obrigado pela preferência! \u2b50{reorder_suffix}"
    ),
    "order_cancelled": (
        "Seu pedido {order_ref} foi cancelado.{reason_note}"
        "\n\nVeja os detalhes do pedido por aqui: {tracking_url}"
    ),
    "order_rejected": (
        "Seu pedido {order_ref} não pôde ser confirmado pelo estabelecimento.{reason_note}"
        "\n\nVeja os detalhes do pedido por aqui: {tracking_url}"
    ),
    # Fila de espera (WP-P2E): o chamado tem prazo, e é ele que faz a fila
    # funcionar. Sem prazo dito, a vaga fica presa a quem não respondeu.
    # Entrada na loja pelo WhatsApp: a pessoa mandou a palavra e recebe o acesso.
    # Uso único e vida curta — dizer isso evita o link guardado que não abre depois.
    "access_link": (
        "Olá{customer_name_greeting}! Aqui está seu acesso à loja:"
        "\n{access_url}{cart_note}"
        "\n\nO link é só seu e vale por poucos minutos."
    ),
    "waitlist_available": (
        "Olá{customer_name_greeting}! Sua fornada saiu \U0001f950 "
        "Confirme o pedido {order_ref} para garantir o seu: {tracking_url}"
    ),
    "waitlist_released": (
        "O prazo de confirmação do pedido {order_ref} passou e liberamos a sua vaga. "
        "Nada foi cobrado, e é só entrar na fila da próxima fornada. {tracking_url}"
    ),
    # Pagar não é o mesmo que ser aceito: enquanto o pedido está `new`, a tela diz
    # "estamos conferindo a disponibilidade". Prometer preparo aqui era prometer o
    # que a tela não cumpre.
    "payment_confirmed": (
        "Olá{customer_name_greeting}! Pagamento do pedido {order_ref} recebido."
        "\nAvisamos a cada passo. Acompanhe por aqui: {tracking_url}"
    ),
    "payment_requested": (
        "Olá{customer_name_greeting}! Conferimos a disponibilidade do pedido {order_ref}. "
        "Agora falta o pagamento. Acesse: {payment_url}{pix_suffix}"
    ),
    # Pedido remoto anotado no PDV: a venda já fechou, falta o cliente pagar pelo
    # link. "Anotamos", não "conferimos a disponibilidade" — o pão já está separado.
    "payment_link_sent": (
        "Olá{customer_name_greeting}! Anotamos seu pedido {order_ref} — total {total}."
        "\nPara confirmar, é só pagar por aqui: {checkout_url}{payment_deadline_note}"
        "\nQualquer coisa, é só responder esta mensagem. \U0001f956"
    ),
    "payment_reminder": (
        "Olá{customer_name_greeting}! Seu pedido {order_ref} aguarda"
        " pagamento PIX. Use o código: {copy_paste}"
    ),
    "payment_expired": (
        "Seu pedido {order_ref} foi cancelado pois o pagamento PIX"
        " não foi confirmado a tempo."
    ),
    "payment_failed": (
        "Não conseguimos preparar o pagamento do pedido {order_ref}. "
        "Abra o link do pedido para tentar novamente: {payment_url}"
    ),
    "preorder_reminder": (
        "Lembrete: seu pedido {order_ref} está agendado para amanhã. "
        "Já estamos preparando tudo!"
    ),
    # Chegada de estoque (AVAILABILITY-PLAN §8.3 + "Me avise"): os pedaços
    # reserve_note/deadline_note/cta/action_url vem prontos do emissor —
    # reserva de sacola materializada traz prazo + link do carrinho; o
    # "Me avise" (sem reserva) traz o link do produto.
    "stock_arrived": (
        "Boa notícia! {product_name} chegou.{reserve_note}{deadline_note} "
        "{cta} {action_url}"
    ),
    # Fornada pronta ("Me avise quando sair do forno", F9 do FOMO-MARKETING):
    # o valor da mensagem e o frescor, entao ela nasce e envelhece rapido.
    "production_ready": (
        "Saiu do forno agora: {product_name}! {cta} {action_url}"
    ),
    "purchase_request": (
        "Olá! Pedido de compra {purchase_ref} da {shop_name}: "
        "{material_name} {purchase_qty_display}. "
        "Confirme disponibilidade, prazo e valor final."
    ),
    "purchase_receipt_rejected": (
        "Devolução {receipt_ref} registrada para {supplier_name}. "
        "Motivo: {reason}"
    ),
    # Campanha: o corpo ja vem pronto do AnnouncementTemplate (com as variaveis
    # resolvidas), entao o template daqui e so o envelope.
    "announcement_published": "{body}\n\n{cta} {action_url}",
}


def _get_config() -> dict:
    """Read ManyChat configuration from settings."""
    return getattr(settings, "SHOPMAN_MANYCHAT", {})


def _resolve_subscriber(recipient: str, config: dict) -> int | None:
    """Resolve recipient to ManyChat subscriber ID."""
    if recipient.isdigit():
        return int(recipient)

    resolver_path = config.get("resolver")
    if resolver_path:
        from ._dotted import import_dotted_attr

        resolver = import_dotted_attr(resolver_path)
        return resolver(recipient)

    return None


def _api_call(endpoint: str, payload: dict, config: dict) -> dict:
    """Make authenticated request to ManyChat API."""
    base_url = config.get("base_url", "https://api.manychat.com/fb")
    api_token = config["api_token"]
    timeout = config.get("timeout", 15)

    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            if resp_data.get("status") == "success":
                return {
                    "success": True,
                    "message_id": f"mc_{payload.get('subscriber_id')}",
                }
            return {"success": False, "error": resp_data.get("message", "Manychat error")}
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"success": False, "error": f"HTTP {e.code}: {error_body[:200]}"}
    except URLError as e:
        return {"success": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        logger.warning("manychat._send_whatsapp: unexpected error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def _build_message(template: str, context: dict) -> str:
    """Build message from template + context.

    Resolution order:
    1. NotificationTemplate DB record (event=template, is_active=True) → body field
    2. MESSAGE_TEMPLATES hardcoded fallback
    3. Generic fallback with order_ref

    As chaves auxiliares (``customer_name_greeting``, ``tracking_suffix``, …) são
    derivadas por ``_notification_templates.derive_context``, dentro do
    ``render_message`` — ponto único para WhatsApp, SMS e e-mail.
    """
    from shopman.shop.adapters._notification_templates import render_message

    return render_message(template, context, MESSAGE_TEMPLATES)


def _load_db_flow_ns(event: str) -> str | None:
    """Return the ManyChat flow namespace configured in the Admin (NotificationTemplate), or None."""
    try:
        from shopman.shop.models import NotificationTemplate

        obj = NotificationTemplate.objects.filter(event=event, is_active=True).first()
        if obj and (obj.whatsapp_flow_ns or "").strip():
            return obj.whatsapp_flow_ns.strip()
    except Exception:
        logger.debug("manychat._load_db_flow_ns: lookup failed for event=%s", event, exc_info=True)
    return None


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send a notification via ManyChat (WhatsApp).

    Args:
        recipient: Phone number or ManyChat subscriber ID.
        template: Event template name (e.g. "order_accepted").
        context: Template variables (order_ref, customer_name, total, etc.).

    Returns:
        True if sent successfully, False otherwise.
    """
    mc_config = _get_config()
    if not mc_config.get("api_token"):
        logger.warning("ManyChat API token not configured")
        return False

    from ._external import inert

    if inert("SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG"):
        logger.info(
            "ManyChat externo inerte (trava dev/seed): %s -> %s",
            template, recipient,
        )
        return True

    from shopman.shop.adapters._notification_templates import derive_context

    # Também no caminho de FLOW: as variáveis do template aprovado saem dos campos
    # personalizados, e `customer_name_greeting` é uma delas nos textos semeados.
    ctx = derive_context(context)
    subscriber_id = _resolve_subscriber(recipient, mc_config)
    if subscriber_id is None:
        logger.warning("Could not resolve subscriber for: %s", recipient)
        return False

    # Flow configurado no Admin (NotificationTemplate.whatsapp_flow_ns) tem precedência;
    # cai no settings flow_map como fallback de bootstrap.
    flow_ns = _load_db_flow_ns(template) or mc_config.get("flow_map", {}).get(template)

    if flow_ns:
        # ⚠️ O flow do ManyChat NÃO lê o `flow_token`: o texto vive lá dentro, e as
        # variáveis dele saem dos CAMPOS PERSONALIZADOS do assinante. Sem este passo, um
        # template aprovado que diga "O {{product_name}} que você pediu chegou" sai com o
        # nome do produto em branco — e é exatamente o que acontecia, em silêncio, nos
        # dois caminhos que usam flow (alerta de estoque e anúncio de campanha).
        _push_custom_fields(subscriber_id, ctx, mc_config)
        payload = {
            "subscriber_id": subscriber_id,
            "flow_ns": flow_ns,
            # Mantido por rastreabilidade do lado do ManyChat; NÃO é a fonte das
            # variáveis do flow (ver acima). Vai o mesmo recorte dos campos: mandar o
            # contexto CRU punha aqui exatamente o que a denylist barrava logo acima.
            "flow_token": _shareable_context(ctx),
        }
        result = _api_call("/sending/sendFlow", payload, mc_config)
    else:
        message = _build_message(template, ctx)
        payload = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    # ⚠️ DECLARAR O CANAL. Sem esta linha o ManyChat trata o envio
                    # como Messenger e avalia a janela de 24h DE LÁ — que para um
                    # assinante de WhatsApp nunca abriu. O sintoma foi um 400 com
                    # o código 3011 dizendo "última interação há 19521h" (mais de
                    # dois anos) para alguém que tinha ACABADO de mandar mensagem.
                    # A pista estava na própria recusa: ela fala em "message tag",
                    # que é conceito do Messenger — o WhatsApp tem template e
                    # janela, não tag.
                    "type": "whatsapp",
                    "messages": [{"type": "text", "text": message}],
                },
            },
        }
        result = _api_call("/sending/sendContent", payload, mc_config)

    if not result["success"]:
        logger.warning("ManyChat send failed: %s", result.get("error"))
    return result["success"]


#: Chaves que NÃO viram campo personalizado: identificadores internos e coisas que a
#: mensagem nunca deve exibir. Lista explícita porque empurrar contexto inteiro para o
#: perfil do cliente no ManyChat seria vazar estado interno para uma ferramenta de
#: marketing.
_FIELD_DENYLIST = frozenset({
    "session_key", "sku", "subscriber_id", "recipient", "phone",
    "customer_ref", "customer_uuid", "hold_ids",
    # Chave auxiliar: existe só para o `action_url` que SAI daqui poder ser o link
    # COMUM (ver `_safe_field_value`). Ela mesma nunca viaja.
    "action_url_public",
})


#: Token de acesso na query (`/a?t=<token>`) — a forma do link pessoal cunhado em
#: `campaign_identity.personal_link`.
_ACCESS_TOKEN_IN_QUERY = re.compile(r"[?&]t=")


def _safe_field_value(name: str, value, ctx: dict):
    """O valor que pode SAIR daqui, ou ``None`` para "não mande este campo".

    ⚠️ `action_url` carrega um LINK DE ACESSO PESSOAL: o despacho o cunha por
    destinatário, ele vale 24h e cria sessão de cliente identificado por número.
    Como campo personalizado, esse token passava a viver em texto claro no perfil do
    cliente dentro de uma ferramenta SaaS de marketing — legível por qualquer pessoa
    com acesso à conta, e utilizável enquanto o cliente não clicasse.

    ⚠️ E simplesmente NÃO mandar não serve: o flow do ManyChat não lê o `flow_token`,
    as variáveis dele saem dos campos personalizados. Um `action_url` ausente sai como
    botão EM BRANCO, e trocar um vazamento por uma CTA quebrada não é conserto.

    Então o que sai é o link COMUM, informado por quem chama em `action_url_public`.
    O cliente chega anônimo por esse caminho e o checkout pede login — é o preço, e é
    o lado seguro dele. Os canais que interpolam o texto na hora (SMS, e-mail) seguem
    recebendo o pessoal: eles não gravam nada em lugar nenhum.

    A recusa é ESTRUTURAL, não uma lista de chaves: valor com token de acesso na query
    nunca sai, mesmo que um chamador futuro esqueça de informar o link comum.
    """
    if name != "action_url":
        return value
    public = str(ctx.get("action_url_public") or "").strip()
    if public:
        return public
    return None if _ACCESS_TOKEN_IN_QUERY.search(str(value)) else value


def _shareable_context(ctx: dict) -> dict:
    """O recorte do contexto que pode SAIR daqui para o ManyChat.

    Um só filtro para os dois caminhos que mandam contexto — os campos personalizados
    e o `flow_token`. Eram dois antes, e o `flow_token` mandava o contexto CRU: o que a
    denylist barrava no perfil saía inteiro no corpo do envio. Filtro que vale em
    metade das saídas não é filtro.
    """
    shareable: dict[str, str] = {}
    for name, value in (ctx or {}).items():
        if name in _FIELD_DENYLIST or not isinstance(value, (str, int, float)):
            continue
        safe = _safe_field_value(name, value, ctx or {})
        if safe is None:
            continue
        text = str(safe).strip()
        if text:
            shareable[name] = text
    return shareable


def _push_custom_fields(subscriber_id: str, ctx: dict, config: dict) -> int:
    """Gravar os valores do contexto como campos personalizados do assinante.

    É o que faz a variável do template aprovado resolver. Falha de um campo **não**
    interrompe o envio: um alerta de fornada é tempo-sensível, e mensagem com um pedaço
    faltando ainda avisa o cliente — mensagem nenhuma não avisa. Mas cada falha vai para
    o log, porque campo que não existe no ManyChat é configuração pendente, não ruído.

    O campo tem de existir no ManyChat com o MESMO nome. Nomes em inglês, como o resto
    do vocabulário de integração.
    """
    pushed = 0
    for name, text in _shareable_context(ctx).items():
        result = _api_call(
            "/subscriber/setCustomFieldByName",
            {"subscriber_id": subscriber_id, "field_name": name, "field_value": text},
            config,
        )
        if result.get("success"):
            pushed += 1
        else:
            logger.warning(
                "ManyChat custom field não gravado: %s (%s). O template vai renderizar "
                "sem ele — crie o campo com este nome no ManyChat.",
                name, result.get("error"),
            )
    return pushed


def is_available(recipient: str | None = None, **config) -> bool:
    """Check if ManyChat adapter is configured and available."""
    mc_config = _get_config()
    return bool(mc_config.get("api_token"))
