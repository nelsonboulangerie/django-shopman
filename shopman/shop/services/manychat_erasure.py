"""Apagar o que a casa empurrou para o ManyChat, antes de apagar aqui dentro.

A exclusão de conta prometia ao cliente, na página de privacidade, que ele
"pode excluir a conta na hora, sem pedir para ninguém". Não era o que acontecia:
qualquer conta com vínculo ManyChat — e o ManyChat é o caminho do login por
WhatsApp, ou seja, a maioria — levava 409 e a mensagem "peça à equipe para
desvincular essa integração".

O bloqueio tinha uma razão de verdade, escrita no próprio código: apagar só o
vínculo local não impede o próximo webhook do provedor de reapresentar o mesmo
assinante e **recriar** os dados. O que faltava não era coragem para remover o
bloqueio, era fechar aquele caminho. Este módulo fecha, em três movimentos:

1. **limpa lá** os campos personalizados que esta casa empurrou para o perfil do
   assinante (``setCustomFieldByName`` com valor vazio) — é a única forma de
   apagamento que a API pública do ManyChat oferece;
2. **grava a lápide** (`ProviderErasureTombstone`), que faz o sync de entrada
   recusar aquele assinante para sempre, sem guardar o identificador em claro;
3. **abre tarefa datada** ao operador para o que a API não faz: a linha de
   contato do ManyChat, com telefone e nome do WhatsApp, só sai pela mão de um
   humano na interface deles.

⚠️ Medido em 23/09/2026: a API pública do ManyChat **não tem verbo de exclusão
de assinante**. Os endpoints existentes são `getInfo`, `findByName`,
`findByCustomField`, `findBySystemField`, `getInfoByUserRef`, `createSubscriber`,
`updateSubscriber`, `addTag(ByName)`, `removeTag(ByName)`, `setCustomField(s)`,
`setCustomFieldByName`, `verifyBySignedRequest` e os três de envio. Nenhum apaga.
Por isso o passo 3 existe: sem ele, "apagamos tudo" seria mentira.

A ordem obedece a `docs/plans/PRIVACY-CANONICAL-FENCE-MATRIX-2026-09-16.md`:
intenção durável → I/O externo FORA da transação → readquirir `Customer` →
finalizar. E falha fechada: limpeza não confirmada não vira "pronto".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Marcador operacional, sem PII: a casa começou a apagar no provedor.
ERASURE_PENDING_KEY = "manychat_erasure_pending"

#: Prazo legal para concluir o pedido do titular (LGPD).
ERASURE_DEADLINE_DAYS = 15

PROVIDER = "manychat"


@dataclass(frozen=True)
class ErasureOutcome:
    """O que a limpeza no provedor conseguiu provar — nunca o que ela supôs."""

    confirmed: bool
    reason: str = ""
    subscriber_ids: tuple[str, ...] = field(default_factory=tuple)
    scrubbed_fields: int = 0

    @property
    def needs_operator_task(self) -> bool:
        return self.confirmed and bool(self.subscriber_ids)


def subscriber_ids(customer) -> tuple[str, ...]:
    """Os assinantes que esta conta comprovadamente tem no provedor.

    Só vínculo provado entra — nunca coincidência de telefone. É a mesma régua
    que o bloqueio antigo usava para decidir que havia ManyChat em jogo.
    """
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
    from shopman.guestman.models import ExternalIdentity

    found: list[str] = []
    for value in CustomerIdentifier.objects.filter(
        customer=customer,
        identifier_type=IdentifierType.MANYCHAT,
    ).values_list("identifier_value", flat=True):
        value = str(value or "").strip()
        if value and value not in found:
            found.append(value)
    for value in ExternalIdentity.objects.filter(
        customer=customer,
        provider=ExternalIdentity.Provider.MANYCHAT,
    ).values_list("provider_uid", flat=True):
        value = str(value or "").strip()
        if value and value not in found:
            found.append(value)
    return tuple(found)


def resolution_pending(customer) -> bool:
    """Uma criação externa pode ter sido aceita sem resultado conclusivo.

    Enquanto isso não for reconciliado, existe a possibilidade de um assinante
    nosso lá fora que nós não sabemos nomear — e apagar aqui sem resolver isso
    seria prometer uma exclusão que não alcança o que o provedor aceitou.
    """
    from shopman.guestman.contrib.manychat.resolver import _PRIVACY_PENDING_KEY

    return bool((customer.metadata or {}).get(_PRIVACY_PENDING_KEY))


def has_provider_footprint(customer) -> bool:
    """Existe qualquer pegada do provedor nesta conta?"""
    metadata = customer.metadata or {}
    return bool(
        subscriber_ids(customer)
        or resolution_pending(customer)
        or customer.source_system == PROVIDER
        or "manychat_custom_fields" in metadata
    )


def mark_intent(customer_pk: int) -> None:
    """Confirma a intenção durável ANTES de qualquer chamada ao provedor.

    Se o processo morrer no meio do I/O, este marcador é o que conta a história:
    a casa já pode ter mexido no perfil de lá enquanto a conta daqui continua
    de pé. A próxima tentativa refaz a limpeza (é idempotente) e o marcador sai
    junto com a conclusão.
    """
    from shopman.guestman.models import Customer

    with transaction.atomic(durable=True):
        customer = Customer.objects.select_for_update().filter(pk=customer_pk, is_active=True).first()
        if customer is None:
            return
        metadata = dict(customer.metadata or {})
        if metadata.get(ERASURE_PENDING_KEY):
            return
        metadata[ERASURE_PENDING_KEY] = True
        customer.metadata = metadata
        customer.save(update_fields=["metadata", "updated_at"])


def run(*, customer_pk: int, ids: tuple[str, ...], pending: bool) -> ErasureOutcome:
    """I/O do provedor, fora de qualquer transação. Nunca supõe sucesso.

    Silêncio do provedor não é ausência: timeout, erro HTTP ou resposta sem
    identificador continuam INCERTOS, e incerto aqui significa que a exclusão
    não pode se declarar concluída.
    """
    from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

    resolved = list(ids)

    if pending:
        status = ManychatSubscriberResolver.reconcile_pending(customer_pk)
        if status == "uncertain":
            return ErasureOutcome(confirmed=False, reason="manychat_reconciliation_uncertain")
        if status == "linked":
            # A reconciliação materializou o vínculo: agora ele tem nome.
            from shopman.guestman.models import Customer

            customer = Customer.objects.filter(pk=customer_pk).first()
            if customer is not None:
                for value in subscriber_ids(customer):
                    if value not in resolved:
                        resolved.append(value)

    scrubbed = 0
    for subscriber_id in resolved:
        info = ManychatSubscriberResolver.fetch_subscriber_info(subscriber_id)
        if info is None:
            # Pode ser indisponibilidade, token ausente ou assinante que sumiu.
            # Nenhuma dessas hipóteses prova que o perfil ficou limpo.
            return ErasureOutcome(
                confirmed=False,
                reason="manychat_profile_unreachable",
                subscriber_ids=tuple(resolved),
                scrubbed_fields=scrubbed,
            )
        cleared = _scrub_custom_fields(subscriber_id, info)
        if cleared is None:
            return ErasureOutcome(
                confirmed=False,
                reason="manychat_field_not_cleared",
                subscriber_ids=tuple(resolved),
                scrubbed_fields=scrubbed,
            )
        scrubbed += cleared

    return ErasureOutcome(
        confirmed=True,
        subscriber_ids=tuple(resolved),
        scrubbed_fields=scrubbed,
    )


def _scrub_custom_fields(subscriber_id: str, info: dict) -> int | None:
    """Zera todo campo personalizado com conteúdo. ``None`` = não confirmado.

    O que a casa empurrou para o perfil do assinante é dado pessoal dela: nome
    do cliente, produto, histórico de aviso. Zerar campo a campo é o apagamento
    que a API permite, e cada gravação devolve confirmação própria — por isso a
    primeira que não confirmar interrompe tudo.
    """
    from shopman.shop.adapters.notification_manychat import set_custom_field

    cleared = 0
    for entry in info.get("custom_fields") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        value = entry.get("value")
        if not name or value in (None, ""):
            continue
        if not set_custom_field(subscriber_id, name, ""):
            logger.warning("manychat_erasure: campo não apagado name=%s", name)
            return None
        cleared += 1
    return cleared


def remember(ids: tuple[str, ...]) -> int:
    """Grava as lápides. Roda DENTRO da transação final da exclusão.

    A lápide precisa nascer junto com a anonimização: se a exclusão rolar para
    trás, não pode sobrar lápide recusando o sync de uma conta que continua viva.
    """
    from shopman.guestman.models import ProviderErasureTombstone

    written = 0
    for subscriber_id in ids:
        if ProviderErasureTombstone.remember(
            provider=ProviderErasureTombstone.Provider.MANYCHAT,
            handle_type=ProviderErasureTombstone.HandleType.SUBSCRIBER_ID,
            value=subscriber_id,
        ):
            written += 1
    return written


def clear_intent(customer) -> None:
    """Tira o marcador operacional; roda junto com a conclusão."""
    metadata = dict(customer.metadata or {})
    if metadata.pop(ERASURE_PENDING_KEY, None) is None:
        return
    customer.metadata = metadata
    customer.save(update_fields=["metadata", "updated_at"])


def operator_task_message(ids: tuple[str, ...], *, receipt_ref, deadline) -> str:
    """O texto que o operador lê. Ele precisa saber o quê, onde e até quando."""
    assinantes = ", ".join(ids)
    return (
        "Exclusão de conta concluída aqui dentro. Falta apagar o contato no ManyChat: "
        "a API deles não tem como apagar assinante, então essa parte é na mão. "
        f"No ManyChat, abra Contacts, procure o assinante {assinantes} e exclua o contato "
        "(Delete Contact). "
        f"Prazo: até {deadline:%d/%m/%Y} — são 15 dias para concluir o pedido do titular. "
        f"Recibo da exclusão: {receipt_ref}."
    )


def open_operator_task(ids: tuple[str, ...], *, receipt_ref) -> None:
    """Abre a tarefa datada. Chamada DEPOIS do commit da exclusão.

    Sem isto, o resíduo viraria nota de rodapé: alguém teria que lembrar
    sozinho de terminar a exclusão do lado do provedor, e ninguém lembra.
    """
    if not ids:
        return
    from shopman.shop.services.observability import create_operator_alert

    deadline = timezone.now() + timedelta(days=ERASURE_DEADLINE_DAYS)
    create_operator_alert(
        type="manychat_contact_erasure_due",
        severity="critical",
        message=operator_task_message(ids, receipt_ref=receipt_ref, deadline=deadline),
        dedupe_key=f"manychat-erasure:{receipt_ref}",
    )
