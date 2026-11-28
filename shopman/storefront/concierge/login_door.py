"""A mensagem de entrada no site não é conversa (dono, 25/11/2026).

"A concierge não entendeu a mensagem de 'login'... Isso precisa ser endereçado
corretamente!" O botão "Abrir o WhatsApp" da página Entrar manda a mensagem pronta
("Olá! Quero entrar no site da … (ref. NB-XXXXXX)", ``whatsapp_verify``). Ela é o pedido de
entrada, e a casa a atende aqui, antes de qualquer leitura: cria o link de acesso com o
mesmo contexto que o ``AccessLinkCreateView`` do doorman dobra na metadata (destino,
sacola, a aba do computador a liberar) e a mensagem de entrada sai pela casa
(``shop.handlers.access_link``), com o botão "Voltar à loja" ou o que libera o computador.
A Nice não responde por cima: uma mensagem só, a da entrada.

Até 25/11 isto era do fluxo do ManyChat, disparado pela palavra-chave. Quando a mensagem
chegava à Concierge, ela lia como conversa e chamava a equipe (conversa 2, 12:11). Se o
fluxo do ManyChat também atender a mesma mensagem, quem consumir a referência primeiro cria
o link, que leva a marca dela (``doorman.services.site_context.already_answered``); quem
chega depois encontra a marca e fica calado, sem segunda mensagem (#3621).

Sem código válido (venceu, já foi usado), a resposta diz como gerar outro. Nunca equipe.
"""

from __future__ import annotations

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

#: As palavras da mensagem pronta do site e a palavra-chave de quem digita.
LOGIN_MARKERS = ("quero entrar no site", "#menu")
#: Sem referência (``#menu`` digitado), o link que o fluxo do ManyChat criou há menos que
#: isto atendeu esta mesma mensagem: não há marca para conferir.
JUST_SENT = timedelta(minutes=3)

EXPIRED = (
    "Esse pedido de entrada venceu ou já foi usado. "
    "Na página Entrar do site, toque de novo em “Abrir o WhatsApp”."
)
NOT_CONFIRMED = (
    "Não consegui confirmar este número para a entrada. "
    "Na página Entrar do site, toque de novo em “Abrir o WhatsApp”."
)
UNAVAILABLE = (
    "Não consegui preparar sua entrada agora. "
    "Na página Entrar do site, toque de novo em “Abrir o WhatsApp”."
)


def is_login(text: str) -> bool:
    """A mensagem é o pedido de entrada no site (a pronta do botão, ou ``#menu``)."""
    from .house_rules import fold

    folded = fold(text or "")
    return any(marker in folded for marker in LOGIN_MARKERS)


def _customer(conversation, binding):
    from shopman.shop.models import ConversationBinding
    from shopman.shop.services.auth import identity_by_customer_ref

    if binding.identity_assurance != ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER:
        return None
    return identity_by_customer_ref(conversation.customer_ref or "")


def _just_sent(customer) -> bool:
    from django.utils import timezone
    from shopman.doorman.models import AccessLink

    recent = AccessLink.objects.filter(
        customer_id=customer.subject_id,
        source=AccessLink.Source.MANYCHAT,
        created_at__gte=timezone.now() - JUST_SENT,
    ).values_list("metadata", flat=True)
    # A liberação da aba do computador nasce junto e não é a mensagem. Em Python, e não no
    # ``exclude``: chave ausente no JSON vira NULL no SQL e o ``exclude`` jogaria fora o link
    # sem ``login_source`` (o do fluxo do ManyChat).
    return any((metadata or {}).get("login_source") != "site_release" for metadata in recent)


def answer(conversation, binding, text: str) -> str | None:
    """Atende o pedido de entrada; ``None`` quando a mensagem não é um.

    Devolve ``""`` quando a entrada saiu (a mensagem é da casa, pelo link) ou o fluxo do
    ManyChat acabou de atender; senão, a frase curta que diz como tentar de novo.
    """
    if not is_login(text):
        return None
    from shopman.doorman.services.link_state import contains_code, pop_state

    customer = _customer(conversation, binding)
    if customer is None:
        # O código fica guardado: a pessoa pode tentar de novo pelo mesmo botão.
        logger.info("concierge.login_door.not_confirmed conversation=%s", conversation.pk)
        return NOT_CONFIRMED
    state = None
    if contains_code(text):
        state = pop_state(text)
        if not isinstance(state, dict):
            from shopman.doorman.services.site_context import already_answered

            if already_answered(text, customer):
                logger.info("concierge.login_door.already_sent conversation=%s", conversation.pk)
                return ""
            logger.info("concierge.login_door.expired conversation=%s", conversation.pk)
            return EXPIRED
    elif _just_sent(customer):
        return ""
    try:
        sent = _create_link(customer, binding, dict(state or {}), code=text if state else "")
    except Exception:
        logger.exception("concierge.login_door.failed conversation=%s", conversation.pk)
        return UNAVAILABLE
    return "" if sent else UNAVAILABLE


def _create_link(customer, binding, state: dict, code: str = "") -> bool:
    """O link de acesso com o contexto do site, pelo mesmo serviço do ``AccessLinkCreateView``."""
    from shopman.doorman.models import AccessLink
    from shopman.doorman.services.access_link import AccessLinkService
    from shopman.doorman.services.site_context import fold_state, release_origin

    metadata: dict = {"login_source": "concierge", "deliver": "manychat"}
    if binding.subject:
        # Entregar para quem falou, pelo assinante (ver ``AccessLinkCreateView``).
        metadata["deliver_to"] = str(binding.subject)
    origin, origin_label = fold_state(state, metadata, code=code)
    release_origin(customer=customer, metadata=metadata, origin=origin, origin_label=origin_label)
    result = AccessLinkService.create_token(
        customer, audience=AccessLink.Audience.WEB_GENERAL, source=AccessLink.Source.MANYCHAT, metadata=metadata
    )
    if not result.success:
        logger.error("concierge.login_door.token_refused error=%s", result.error)
    return bool(result.success)
