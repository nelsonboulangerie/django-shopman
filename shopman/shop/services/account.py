"""Storefront account mutation service.

Views keep HTTP, HTMX rendering, and permission response details here; Guestman
mutations live behind this facade.
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

# Domain registry of consent channels this shop tracks. Display copy (labels,
# descriptions) is a storefront concern and lives in storefront.presentation.account.
NOTIFICATION_CONSENT_CHANNELS: tuple[str, ...] = ("whatsapp", "email", "sms", "push")


def get_authenticated_customer(request):
    """Return the authenticated Customer model instance, or None."""
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None

    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_uuid(customer_info.uuid)


def addresses(customer_ref: str):
    from shopman.guestman.services import address as address_service

    return address_service.addresses(customer_ref)


def get_address(customer_ref: str, pk: int):
    from shopman.guestman.services import address as address_service

    return address_service.get_address(customer_ref, pk)


def add_address(customer_ref: str, intent):
    from shopman.guestman.services import address as address_service

    return address_service.add_address(
        customer_ref=customer_ref,
        label=intent.label,
        label_custom=intent.label_custom,
        formatted_address=intent.formatted_address,
        place_id=intent.place_id or "",
        coordinates=intent.coordinates,
        complement=intent.complement,
        delivery_instructions=intent.delivery_instructions,
        is_default=intent.is_default,
        components={
            "route": intent.route,
            "street_number": intent.street_number,
            "neighborhood": intent.neighborhood,
            "city": intent.city,
            "state_code": intent.state_code,
            "postal_code": intent.postal_code,
        },
    )


def update_address(customer_ref: str, pk: int, intent) -> None:
    from shopman.guestman.services import address as address_service

    fields: dict = {
        "label": intent.label,
        "label_custom": intent.label_custom,
        "formatted_address": intent.formatted_address,
        "route": intent.route,
        "street_number": intent.street_number,
        "neighborhood": intent.neighborhood,
        "city": intent.city,
        "state_code": intent.state_code,
        "postal_code": intent.postal_code,
        "complement": intent.complement,
        "delivery_instructions": intent.delivery_instructions,
        "place_id": intent.place_id or "",
        "is_default": intent.is_default,
    }
    if intent.coordinates is not None:
        fields["latitude"] = intent.coordinates[0]
        fields["longitude"] = intent.coordinates[1]
        fields["is_verified"] = True
    elif not intent.place_id:
        fields["latitude"] = None
        fields["longitude"] = None
        fields["is_verified"] = False

    address_service.update_address(customer_ref, pk, **fields)


def update_address_label(customer_ref: str, pk: int, *, label: str, label_custom: str) -> None:
    from shopman.guestman.services import address as address_service

    address_service.update_address(customer_ref, pk, label=label, label_custom=label_custom)


def delete_address(customer_ref: str, pk: int) -> None:
    from shopman.guestman.services import address as address_service

    address_service.delete_address(customer_ref, pk)


def set_default_address(customer_ref: str, pk: int) -> None:
    from shopman.guestman.services import address as address_service

    address_service.set_default_address(customer_ref, pk)


def update_profile(customer_ref: str, intent):
    from django.db import transaction
    from shopman.guestman.models import ContactPoint
    from shopman.guestman.services import customer as customer_service

    with transaction.atomic():
        customer = customer_service.get(customer_ref)
        if not customer:
            return None

        email = (intent.email or "").strip().lower()
        if email:
            conflict = (
                ContactPoint.objects.filter(
                    type=ContactPoint.Type.EMAIL,
                    value_normalized=email,
                )
                .exclude(customer=customer)
                .exists()
            )
            if conflict:
                raise ValueError("E-mail já está em uso.")

            primary_email = ContactPoint.objects.filter(
                customer=customer,
                type=ContactPoint.Type.EMAIL,
                is_primary=True,
            ).first()
            if primary_email:
                primary_email.value_normalized = email
                primary_email.value_display = email
                primary_email.save(update_fields=["value_normalized", "value_display", "updated_at"])
        else:
            ContactPoint.objects.filter(
                customer=customer,
                type=ContactPoint.Type.EMAIL,
                is_primary=True,
            ).delete()

        return customer_service.update(
            customer_ref,
            first_name=intent.first_name,
            last_name=intent.last_name,
            email=email,
            birthday=intent.birthday,
        )


def preferences(customer_ref: str, category: str | None = None):
    from shopman.guestman import PreferenceService

    return PreferenceService.get_preferences(customer_ref, category)


def active_food_keys(customer_ref: str) -> set[str]:
    return {pref.key for pref in preferences(customer_ref, "alimentar")}


def toggle_food_preference(customer_ref: str, key: str) -> set[str]:
    """Toggle one dietary preference; return the active preference keys."""
    from shopman.guestman import PreferenceService

    existing = PreferenceService.get_preference(customer_ref, "alimentar", key)
    if existing is not None:
        PreferenceService.delete_preference(customer_ref, "alimentar", key)
    else:
        PreferenceService.set_preference(
            customer_ref,
            "alimentar",
            key,
            value=True,
            preference_type="restriction",
            source="storefront_settings",
        )

    return active_food_keys(customer_ref)


def enabled_notification_channels(customer_ref: str) -> set[str]:
    """Return the consent channels the customer has currently granted."""
    from shopman.guestman import ConsentService

    return {channel for channel in NOTIFICATION_CONSENT_CHANNELS if ConsentService.has_consent(customer_ref, channel)}


def toggle_notification_consent(
    customer_ref: str,
    channel: str,
    *,
    ip_address: str = "",
) -> set[str]:
    """Toggle one channel's consent; return the enabled consent channels.

    Ao gravar, a tela inteira vira registro: os canais que aparecem desligados
    passam a ter um opt-out explícito, e não a ausência de registro que tinham
    antes.

    Isso não é zelo burocrático — é o que faz a tela dizer a verdade. O aviso do
    próprio pedido tem base legal de execução de contrato e sai por canal sem
    registro (ver `shop/services/notification.py::_filter_backend_chain`), então
    um canal "desligado na tela, ausente no banco" seria um botão que mostra
    "não" e responde "sim". Quem mexeu numa chave viu as quatro; gravar as
    quatro é registrar o que ela viu e decidiu.
    """
    from shopman.guestman import ConsentService

    if ConsentService.has_consent(customer_ref, channel):
        ConsentService.revoke_consent(customer_ref, channel)
    else:
        ConsentService.grant_consent(
            customer_ref,
            channel,
            source="storefront_settings",
            legal_basis="consent",
            ip_address=ip_address,
        )

    known = {consent.channel for consent in ConsentService.get_consents(customer_ref)}
    for other in NOTIFICATION_CONSENT_CHANNELS:
        if other in known:
            continue
        try:
            ConsentService.revoke_consent(customer_ref, other)
        except Exception:
            logger.warning(
                "consent: opt-out explícito falhou customer=%s channel=%s",
                customer_ref, other, exc_info=True,
            )

    return enabled_notification_channels(customer_ref)


# ── O rastro que a exclusão tem de alcançar ───────────────────────────
#
# O telefone É a identidade desta loja: é o único login. E ele não vive só no
# Customer — vive em `Order.handle_ref` como coluna de primeira classe e dentro
# de `Order.data["customer"]`, que o CommitService copia de `session.data` em
# TODO commit. A anonimização anterior não tinha uma única referência a `Order`
# ou `Session`: medido no banco do seed em 20/08, os 29 pedidos de um titular
# continuavam com o telefone em texto puro depois da exclusão feita pela tela.
# Quem tivesse acesso ao Admin, ao banco ou a um relatório re-identificava o
# titular e reconstruía tudo que ele comprou — enquanto a tela afirmava, no gesto
# do art. 18 da LGPD, que os dados pessoais tinham sido anonimizados.
#
# Estas são as chaves de `Order.data` / `Session.data` que identificam a PESSOA.
# O que descreve a COMPRA (itens, preços, pagamento, datas, canal) fica: é dele
# que vivem a obrigação fiscal e o B.I., e ele não diz quem comprou.
_PII_DATA_KEYS: tuple[str, ...] = (
    "customer",  # {name, phone, email, cpf, uuid, address}
    "customer_name",
    "customer_phone",
    "delivery_address",
    "delivery_address_structured",
    "recipient",  # presente para terceiro: nome e telefone de quem recebe
    "gift_message",
    "order_notes",  # texto livre escrito pelo cliente
)

# Handles que SÃO a pessoa. `pos_tab`, `table` e o código de pedido do iFood
# identificam a comanda, a mesa ou o pedido — não o titular — e ficam como estão.
_PERSONAL_HANDLE_TYPES: frozenset[str] = frozenset(
    {"phone", "customer", "whatsapp", "manychat"}
)

# Tipo de handle de um pedido cujo titular pediu exclusão. Trocar o TIPO junto
# com o valor não é cosmético: `customer_orders.customer_identity_filter` casa
# por (handle_type="phone", handle_ref=<telefone>), então um pedido que ficasse
# com `handle_type="phone"` voltaria a ser alcançável por quem passasse a usar
# aquele número depois — inclusive uma pessoa diferente.
ANONYMIZED_HANDLE_TYPE = "anonymized"


def customer_footprint_query(customer_ref: str, phone: str):
    """A pegada do titular em Order/Session — a MESMA para exportar e para apagar.

    Exportação e exclusão são as duas metades do mesmo direito (art. 18 da LGPD),
    e discordar de escopo é como a exportação passava a mostrar menos do que a
    exclusão precisava alcançar: a exportação lia só `data.customer_ref` e perdia
    o pedido identificado apenas pelo handle de telefone. Uma função só, usada
    pelos dois lados, torna a divergência impossível.
    """
    from django.db.models import Q

    query = Q()
    if customer_ref:
        query |= Q(data__customer_ref=customer_ref)
        query |= Q(data__customer__ref=customer_ref)
    if phone:
        query |= Q(handle_type__in=tuple(_PERSONAL_HANDLE_TYPES), handle_ref=phone)
        query |= Q(data__customer__phone=phone)
    return query


def _customer_orders(customer_ref: str, phone: str):
    from shopman.orderman.models import Order

    query = customer_footprint_query(customer_ref, phone)
    if not query.children:
        return Order.objects.none()
    return Order.objects.filter(query)


def _scrub_pii(payload) -> tuple[dict, bool]:
    """Devolve (cópia sem as chaves de PII, houve mudança)."""
    if not isinstance(payload, dict):
        return payload, False
    clean = {k: v for k, v in payload.items() if k not in _PII_DATA_KEYS}
    return clean, len(clean) != len(payload)


def _anonymize_order_trail(*, customer_ref: str, phone: str, pseudonym: str) -> dict[str, int]:
    """Apaga o PII do titular dos pedidos e das sessões dele. Idempotente."""
    from django.db import IntegrityError
    from shopman.orderman.models import Order, Session

    counts = {"orders": 0, "sessions": 0}

    for order in _customer_orders(customer_ref, phone).iterator():
        fields: dict = {}

        data, changed = _scrub_pii(order.data)
        if changed:
            fields["data"] = data

        # `snapshot["data"]` é a cópia integral de `session.data` no commit — o
        # mesmo PII, uma camada abaixo. Sem isto a varredura do banco continuava
        # achando nome e telefone dentro do retrato selado.
        snapshot = order.snapshot or {}
        snap_data, snap_changed = _scrub_pii(snapshot.get("data"))
        if snap_changed:
            snapshot = dict(snapshot)
            snapshot["data"] = snap_data
            fields["snapshot"] = snapshot

        if order.handle_ref and order.handle_type in _PERSONAL_HANDLE_TYPES:
            fields["handle_type"] = ANONYMIZED_HANDLE_TYPE
            fields["handle_ref"] = pseudonym

        if not fields:
            continue

        # `.update()` e não `save()`: `snapshot` é campo SELADO (`Order.save()`
        # levanta ImmutabilityError). O selo existe para o conteúdo do pedido não
        # derivar depois de vendido, e continua valendo — a exclusão pedida pelo
        # titular é a única exceção legítima, e ela passa por aqui, uma vez, com
        # o motivo escrito. Nunca afrouxe o selo em `save()` para conseguir isto.
        Order.objects.filter(pk=order.pk).update(**fields)
        counts["orders"] += 1

    query = customer_footprint_query(customer_ref, phone)
    sessions = Session.objects.filter(query) if query.children else Session.objects.none()
    for session in sessions.iterator():
        fields = {}
        data, changed = _scrub_pii(session.data)
        if changed:
            fields["data"] = data
        if session.handle_ref and session.handle_type in _PERSONAL_HANDLE_TYPES:
            fields["handle_type"] = ANONYMIZED_HANDLE_TYPE
            fields["handle_ref"] = pseudonym
        if not fields:
            continue
        try:
            Session.objects.filter(pk=session.pk).update(**fields)
        except IntegrityError:
            # Índice único parcial (channel_ref, handle_type, handle_ref) para
            # sessões abertas: duas sessões abertas do mesmo titular no mesmo
            # canal colidiriam no pseudônimo comum. O sufixo mantém a exclusão
            # completa; o agrupamento por titular já vive em `data.customer_ref`.
            fields["handle_ref"] = f"{pseudonym}-{session.pk}"
            Session.objects.filter(pk=session.pk).update(**fields)
        counts["sessions"] += 1

    return counts


def export_customer_data(customer) -> dict:
    data = {
        "customer": {
            "ref": customer.ref,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "phone": customer.phone,
            "email": customer.email,
            # `document` e `metadata` são apagados por `purge_pii` na exclusão e
            # faltavam aqui: o titular só pode conferir o que a loja guarda dele
            # se a exportação mostrar tudo que a exclusão alcança.
            "document": customer.document,
            "metadata": customer.metadata,
            "birthday": str(customer.birthday) if customer.birthday else None,
            "created_at": customer.created_at.isoformat(),
        },
        "addresses": [
            {
                "label": addr.label,
                "formatted_address": addr.formatted_address,
                "route": addr.route,
                "street_number": addr.street_number,
                "neighborhood": addr.neighborhood,
                "city": addr.city,
                "complement": addr.complement,
                "delivery_instructions": addr.delivery_instructions,
                "is_default": addr.is_default,
            }
            for addr in addresses(customer.ref)
        ],
    }

    orders = _customer_orders(customer.ref, customer.phone or "").order_by("-created_at")[:200]
    data["orders"] = [
        {
            "ref": order.ref,
            "status": order.status,
            "total_q": (order.snapshot or {}).get("pricing", {}).get("total_q", order.total_q),
            "created_at": order.created_at.isoformat(),
            "items": list((order.snapshot or {}).get("items", [])),
        }
        for order in orders
    ]

    data["preferences"] = [
        {
            "category": pref.category,
            "key": pref.key,
            "value": pref.value,
            "preference_type": pref.preference_type,
        }
        for pref in preferences(customer.ref)
    ]

    from shopman.guestman import ConsentService

    data["consents"] = [
        {
            "channel": consent.channel,
            "status": consent.status,
            "consented_at": consent.consented_at,
            "revoked_at": consent.revoked_at,
        }
        for consent in ConsentService.get_consents(customer.ref)
    ]

    try:
        from shopman.guestman import LoyaltyService

        account = LoyaltyService.get_account(customer.ref)
        if account:
            data["loyalty"] = {
                "tier": account.tier,
                "points_balance": account.points_balance,
                "lifetime_points": account.lifetime_points,
                "stamps_current": account.stamps_current,
            }
            txns = LoyaltyService.get_transactions(customer.ref, limit=100)
            data["loyalty"]["transactions"] = [
                {
                    "type": txn.transaction_type,
                    "points": txn.points,
                    "description": txn.description,
                    "created_at": txn.created_at.isoformat(),
                }
                for txn in txns
            ]
    except Exception:
        logger.warning("data_export_loyalty_failed", exc_info=True)

    return data


def _nada_a_apagar(exc: BaseException) -> bool:
    """A etapa falhou porque não havia nada lá? Então ela não falhou.

    Anonimizar é idempotente de propósito: o operador reexecuta depois de uma
    falha parcial, e a segunda passada encontra metade das coisas já apagadas.
    "Não achei o titular" nessa segunda passada é o estado DESEJADO chegando
    pelo caminho da exceção — contá-lo como falha faria a reexecução nunca
    convergir, e o alerta crítico gritar para sempre sobre um trabalho que
    terminou.

    Duas formas da mesma ausência, porque duas camadas a expressam diferente:
    o `guestman` levanta `CustomerError(CUSTOMER_NOT_FOUND)`, e o ORM levanta
    `Customer.DoesNotExist` — este último inclusive quando o titular existe mas
    está inativo, que é exatamente como a anonimização o deixa
    (`revoke_consent` filtra por `is_active=True`).
    """
    from django.core.exceptions import ObjectDoesNotExist

    if isinstance(exc, ObjectDoesNotExist):
        return True
    return getattr(exc, "code", None) == "CUSTOMER_NOT_FOUND"


class AnonymizationIncomplete(Exception):
    """A exclusão rodou inteira, mas alguma etapa falhou — e isso NÃO é sucesso.

    A estrutura defensiva de ``anonymize_customer`` está certa: cada etapa é
    independente, e uma falha não pode impedir as outras de apagarem o que
    conseguem. O erro era o silêncio depois — a função voltava sem dizer nada e
    a API respondia ``{"ok": true}``. O titular ouvia que seus dados foram
    apagados enquanto parte deles continuava no banco.

    ``steps`` nomeia as etapas que falharam, para o operador saber onde olhar.
    """

    def __init__(self, steps):
        self.steps = tuple(steps)
        super().__init__("Exclusão incompleta: " + ", ".join(self.steps))


def anonymize_customer(customer) -> tuple[str, str]:
    """Anonymize personal data and return original ref + phone hash.

    Alcança o Customer (campos, ContactPoint, document, metadata, identidades),
    o User do doorman, o perfil de RFM e — desde a correção do LOTE 6 — o rastro
    do titular em `Order` e `Session`, que é onde o telefone realmente morava.
    """
    falhas: list[str] = []
    original_ref = customer.ref
    original_phone = customer.phone or ""
    phone_hash = hashlib.sha256(original_phone.encode()).hexdigest()[:12]

    # O pseudônimo do pedido vem do uuid do Customer, e NÃO do `phone_hash`
    # acima: sha256 de telefone é reversível por força bruta (o espaço de
    # números brasileiros cabe num laptop), então gravar esse hash no lugar do
    # número seria gravar o número com outra roupa. O uuid é aleatório, já
    # existe, e mantém os pedidos do mesmo titular agrupados para auditoria sem
    # dizer quem ele é. O `phone_hash` continua sendo só o recibo devolvido à
    # tela — nunca entra no banco.
    pseudonym = f"ANON-{customer.uuid.hex[:12]}"

    from shopman.guestman import ConsentService
    from shopman.guestman.services import address as address_service

    for channel in NOTIFICATION_CONSENT_CHANNELS:
        try:
            ConsentService.revoke_consent(original_ref, channel)
        except Exception as exc:
            if not _nada_a_apagar(exc):
                falhas.append(f"revogar consentimento ({channel})")
            logger.warning("consent_revoke_failed channel=%s", channel, exc_info=True)

    try:
        address_service.delete_all_addresses(original_ref)
    except Exception as exc:
        if not _nada_a_apagar(exc):
            falhas.append("apagar endereços")
        logger.warning("address_cleanup_failed customer=%s", original_ref, exc_info=True)

    customer.first_name = "Anonimizado"
    customer.last_name = ""
    customer.email = ""
    customer.phone = ""
    customer.birthday = None
    customer.notes = ""
    customer.is_active = False
    customer.save()

    # Alcançar a FONTE DE VERDADE do PII (ContactPoint/document/metadata/identidades),
    # que a limpeza dos campos denormalizados acima não toca, e o User do doorman.
    try:
        from shopman.guestman.services import customer as customer_service

        customer_service.purge_pii(customer)
    except Exception:
        falhas.append("purgar PII do cadastro")
        logger.warning("anonymize: purge_pii falhou customer=%s", original_ref, exc_info=True)

    try:
        from shopman.doorman.services._user_bridge import forget_customer

        forget_customer(customer.uuid, phone=original_phone)
    except Exception:
        falhas.append("esquecer o login")
        logger.warning("anonymize: forget_customer falhou customer=%s", original_ref, exc_info=True)

    # O pedido e a sessão — onde o telefone é coluna, não campo derivado.
    try:
        counts = _anonymize_order_trail(
            customer_ref=original_ref,
            phone=original_phone,
            pseudonym=pseudonym,
        )
        logger.info(
            "anonymize: rastro apagado customer=%s orders=%s sessions=%s",
            original_ref, counts["orders"], counts["sessions"],
        )
    except Exception:
        falhas.append("apagar o rastro em pedidos e sessões")
        logger.warning("anonymize: rastro de pedidos falhou customer=%s", original_ref, exc_info=True)

    # O perfil de RFM é um retrato comportamental montado para MIRAR a pessoa
    # (recência, frequência, ticket, segmento). Não tem valor fiscal e não
    # sobrevive a um pedido de exclusão: sai inteiro. Os números agregados que o
    # B.I. precisa continuam deriváveis dos pedidos já anonimizados.
    try:
        from shopman.guestman import CustomerInsight

        CustomerInsight.objects.filter(customer=customer).delete()
    except Exception:
        falhas.append("apagar o perfil de RFM")
        logger.warning("anonymize: insight delete falhou customer=%s", original_ref, exc_info=True)

    # As superfícies guardam dado do cliente que o shop não pode importar
    # (`storefront` importa `shop`, nunca o contrário — ADR-001). O anúncio é um
    # signal porque não precisamos de retorno: quem guarda, apaga.
    try:
        from shopman.shop.signals import customer_anonymized

        customer_anonymized.send(
            sender=None,
            customer_ref=original_ref,
            phone=original_phone,
            pseudonym=pseudonym,
        )
    except Exception:
        falhas.append("avisar as superfícies")
        logger.warning("anonymize: signal customer_anonymized falhou customer=%s", original_ref, exc_info=True)

    if falhas:
        # Alerta ANTES de levantar: a exceção sobe para a API e vira resposta de
        # erro, mas quem tem de agir é a operação — dado de titular que não saiu
        # do banco é obrigação legal em aberto, não um 500 qualquer.
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="account_deletion_incomplete",
            severity="critical",
            message=(
                f"Exclusão de conta incompleta ({original_ref}): "
                + ", ".join(falhas)
                + ". Dado pessoal permanece no banco."
            ),
            dedupe_key=f"anonymize:{original_ref}",
        )
        raise AnonymizationIncomplete(falhas)

    return original_ref, phone_hash
