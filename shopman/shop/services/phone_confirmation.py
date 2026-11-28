"""Telefone digitado pela equipe: o titular confirma que o número é dele (D4, OC-08).

Decisão do dono (D4, 23/11/2026): quando o balcão grava um telefone, o cliente
recebe no WhatsApp "Confirme que este número é seu" e confirma com um toque. Até
confirmar, o número não resolve para a conta existente: o porto de identidade do
Guestman (``IdentityResolver.resolve``) não entrega contato que ninguém provou.

O que este módulo faz é o PEDIDO, e só ele:

- quem grava o telefone (PDV, cadastro do Gestor, pedido anotado por telefone)
  chama :func:`request_on_commit` com o cliente e o número;
- depois do commit, se o contato continua sem prova, sai o aviso
  ``phone_confirmation_requested`` pelo registro de notificações, pelo WhatsApp;
- fora da janela de 24 horas o WhatsApp só fala por modelo aprovado pela Meta. O
  envio fica atrás desse estado (:func:`template_ready`, o mesmo teste da resposta
  da Concierge): sem o flow ligado nada sai, e o pedido fica registrado como
  ``awaiting_template`` no cadastro.

A CONFIRMAÇÃO não mora aqui. O toque no botão é uma mensagem do próprio número
para a loja; ela chega pelo ManyChat, e o vínculo do assinante
(``ManychatService.sync_subscriber``, chamado pela Concierge ao identificar quem
escreveu) marca o contato como verificado pelo canal. É o caminho de verificação
que já existe; nada novo foi aberto para isso. O código certo do SMS também
confirma (decisão D, 24/11/2026): ele prova a posse do número, e o
``IdentityResolver.create`` do Guestman entrega o cadastro sem prova a quem acabou
de prová-lo, com a prova ``otp_sms`` gravada na transação do aceite.

O registro do pedido fica em ``Customer.metadata["phone_confirmation"]``
(``docs/reference/data-schemas.md``), sem o número: o contato é apontado pelo id.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: O aviso (``notification_copy.CUSTOMER_COPY``) e o modelo da Meta que o leva
#: (``docs/reference/whatsapp-templates-meta.md``, ``confirmar_numero``).
EVENT = "phone_confirmation_requested"
#: Onde o pedido fica registrado no cadastro.
METADATA_KEY = "phone_confirmation"

#: O aviso saiu (o provedor aceitou).
STATE_SENT = "sent"
#: O modelo da Meta ainda não está ligado: nada saiu, de propósito.
STATE_AWAITING_TEMPLATE = "awaiting_template"
#: O modelo está ligado, mas o envio falhou (sem assinante, provedor recusou).
STATE_NOT_SENT = "not_sent"

_PHONE_TYPES = ("phone", "whatsapp")


def template_ready() -> bool:
    """O modelo aprovado pela Meta está ligado (tem flow)? Sem ele, nada sai."""
    try:
        from shopman.shop.adapters import notification_manychat

        return bool(notification_manychat.sends_as_flow(EVENT))
    except Exception:
        logger.warning("phone_confirmation.template_lookup_failed", exc_info=True)
        return False


def _unverified_contact(customer, phone: str):
    """O contato deste número no cadastro, quando ninguém o provou ainda."""
    from shopman.guestman.models import ContactPoint

    contacts = list(
        ContactPoint.objects.filter(
            customer=customer,
            type__in=_PHONE_TYPES,
            value_normalized=phone,
        )
    )
    if not contacts or any(contact.is_verified for contact in contacts):
        return None
    return next((c for c in contacts if c.type == ContactPoint.Type.PHONE), contacts[0])


def request_on_commit(customer_ref: str, phone: str) -> None:
    """Pede a confirmação do número depois que a gravação dele se confirmar.

    Quem chama é quem acabou de gravar o telefone. Antes do commit não se sabe se
    o número fica; depois dele, :func:`request` relê o contato e só pede se ele
    continua sem prova.
    """
    ref = str(customer_ref or "").strip()
    number = str(phone or "").strip()
    if not ref or not number:
        return
    transaction.on_commit(lambda: _request_quietly(ref, number))


def _request_quietly(customer_ref: str, phone: str) -> None:
    # Depois do commit a gravação do cadastro já valeu: uma falha do pedido de
    # confirmação nunca desfaz nem derruba o que o balcão salvou.
    try:
        request(customer_ref, phone)
    except Exception:
        logger.warning("phone_confirmation.request_failed customer=%s", customer_ref, exc_info=True)


def request(customer_ref: str, phone: str) -> str | None:
    """Pede ao titular que confirme o número. Devolve o estado gravado, ou ``None``.

    ``None`` quando não há o que pedir: cadastro inativo ou ausente, número que
    já não é dele, ou contato que alguém já provou.
    """
    from shopman.guestman.models import Customer
    from shopman.guestman.utils import normalize_phone

    number = normalize_phone(phone)
    customer = Customer.objects.filter(ref=customer_ref, is_active=True).first()
    if customer is None or not number:
        return None
    contact = _unverified_contact(customer, number)
    if contact is None:
        return None

    if not template_ready():
        state, error = STATE_AWAITING_TEMPLATE, ""
    else:
        from shopman.shop.notifications import notify

        # Sem nome no contexto, de propósito: o número pode ter sido digitado
        # errado, e quem o recebe não deve ler o nome de outra pessoa.
        result = notify(event=EVENT, recipient=number, context={}, backend="manychat")
        state = STATE_SENT if result.success else STATE_NOT_SENT
        error = "" if result.success else str(result.error or "")[:120]

    _record(customer.pk, contact_id=str(contact.pk), state=state, error=error)
    logger.info("phone_confirmation.requested customer=%s state=%s", customer_ref, state)
    return state


def _record(customer_pk: int, *, contact_id: str, state: str, error: str) -> None:
    from shopman.guestman.models import Customer

    from shopman.shop.services.account import AccountUnavailable, lock_active_customer

    with transaction.atomic():
        try:
            locked = lock_active_customer(customer_pk=customer_pk)
        except AccountUnavailable:
            return
        metadata = dict(locked.metadata or {})
        entry = {
            "contact_id": contact_id,
            "state": state,
            "requested_at": timezone.now().isoformat(),
        }
        if error:
            entry["error"] = error
        metadata[METADATA_KEY] = entry
        # ``update`` e não ``save``: o ``updated_at`` é a revisão que o Gestor
        # confere antes de salvar a ficha, e este registro sai logo depois de a
        # equipe gravar o telefone. Bumpá-lo faria a próxima edição ser recusada
        # com "o cliente mudou desde que você abriu", sem ninguém ter mudado nada.
        Customer.objects.filter(pk=locked.pk).update(metadata=metadata)
