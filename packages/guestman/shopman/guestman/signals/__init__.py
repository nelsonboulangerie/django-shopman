"""
Guestman signals — public event API.

Emitted signals:
- customer_created: Emitted by services.customer.create()
- customer_updated: Emitted by services.customer.update()
- contact_reassigned: Emitted by services.identity when a phone/WhatsApp number
  stops being a contact of a customer (it went, or is going, to another owner).
"""

from django.dispatch import Signal

# Customer signals (emitted by services)
customer_created = Signal()  # sender=Customer
customer_updated = Signal()  # sender=Customer, changes=dict

#: O número deixou de ser deste cadastro (D3, "número que muda de dono").
#:
#: sender=ContactPoint; kwargs: ``customer_id`` (o dono ANTERIOR), ``customer_ref``,
#: ``contact_type`` (phone/whatsapp), ``value`` (E.164), ``verification_ref`` (o
#: assinante do provedor que asseverava o número, quando houver) e ``source`` (quem
#: percebeu: ``contact_removed``, ``provider_subscriber_moved``, ``customer_not_me``,
#: ou o nome do provedor que avisou a troca).
#:
#: Quem escuta corta o que ainda trata o número como chave desta pessoa: o
#: identificador do provedor de mensagens (contrib de identificadores) e o vínculo
#: da conversa (orquestrador). Emitido dentro da transação que tirou o número:
#: um receptor que falha desfaz a retirada, e nada fica pela metade. Apagar o
#: telefone e o WhatsApp do mesmo número num ``delete()`` só avisa uma vez por
#: linha: o mesmo número pode chegar duas vezes, e quem escuta é idempotente.
contact_reassigned = Signal()
