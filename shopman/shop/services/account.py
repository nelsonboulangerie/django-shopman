"""Storefront account mutation service.

Views keep HTTP, HTMX rendering, and permission response details here; Guestman
mutations live behind this facade.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.exceptions import ObjectDoesNotExist

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


# A frase que o cliente lê quando o e-mail digitado já é de outro cadastro. Diz
# o que houve sem dizer DE QUEM é o e-mail, e sem culpar quem digitou: pode muito
# bem ser o e-mail dele mesmo, num cadastro antigo com outro telefone.
EMAIL_TAKEN_DETAIL = "Este e-mail já está em uso em outra conta."


class ContactAlreadyTaken(ValueError):
    """O contato digitado é de OUTRO cadastro — e a recusa tem de dizer qual campo.

    Era um ``ValueError`` de frase solta, e a view do storefront o capturava num
    ``except Exception`` que jogava a mensagem fora: o cliente trocava o e-mail,
    lia "não foi possível atualizar seu perfil agora", tentava de novo, e nunca
    descobria que o problema era o e-mail. A informação existia e morria no log.

    ``field`` é o que a tela precisa para apontar o campo certo; a superfície
    acrescenta as saídas por cima (entrar, falar com a padaria). Subclasse de
    ``ValueError`` porque é o que os chamadores já esperavam — quem quer o
    detalhe estruturado captura o tipo.

    ⚠️ Esta recusa NÃO carrega o dono do contato. O PDV carrega, e deve: é
    superfície de operador, e quem está no balcão precisa saber com quem está
    falando. A loja é superfície de CLIENTE — dizer "este e-mail é do Fulano"
    para um desconhecido é vazamento. A loja diz que o contato não está
    disponível e oferece caminho; nunca a identidade de quem o tem.
    """

    def __init__(self, message: str = EMAIL_TAKEN_DETAIL, *, field: str = "email"):
        super().__init__(message)
        self.field = field


# A frase que o cliente lê quando o número digitado já é de outro cadastro.
# Mesma regra do e-mail: diz o que houve, não de quem é.
PHONE_TAKEN_DETAIL = "Este número já está em uso em outra conta."

# Os dois tipos de contato que respondem por "o telefone do cliente".
#
# Não é redundância: o login grava o número verificado como `WHATSAPP`
# (`doorman.verification._link_verified_identifier`) e o cache do `Customer`
# espelha o mesmo número como `PHONE` (`Customer._sync_contact_points`). Os dois
# apontam para `Customer.phone` no caminho de volta (`_sync_to_customer`), e
# `get_by_phone` procura nos DOIS. Trocar só um deixa o outro respondendo pelo
# número velho — que é exatamente o buraco que esta troca existe para fechar.
PHONE_CONTACT_TYPES = ("phone", "whatsapp")


class PhoneChangeRefused(ValueError):
    """A troca de número foi recusada por um motivo que a tela precisa nomear.

    ``field`` diz onde o erro mora (``phone`` ou ``code``) e ``error_code`` é o
    que a superfície usa para escolher a saída sem casar a frase.
    """

    def __init__(self, message: str, *, field: str = "phone", error_code: str = ""):
        super().__init__(message)
        self.field = field
        self.error_code = error_code


def _phone_belongs_to_someone_else(customer, phone: str) -> bool:
    from shopman.guestman.models import ContactPoint

    return (
        ContactPoint.objects.filter(
            type__in=PHONE_CONTACT_TYPES,
            value_normalized=phone,
        )
        .exclude(customer=customer)
        .exists()
    )


def _set_primary_phone(customer, phone: str) -> None:
    """Promove o número a contato principal do cliente — pelo Core, não à mão.

    ⚠️ O caminho intuitivo (``customer.phone = novo; customer.save()``) NÃO
    funciona, e falha de um jeito que parece defeito do Core sem ser. O
    ``save()`` chama ``_sync_contact_points()``, que faz ``get_or_create`` do
    ContactPoint novo já com ``is_primary=True`` e só DEPOIS demove o antigo —
    então o banco vê dois primários do mesmo tipo por um instante e recusa:

        IntegrityError: UNIQUE constraint failed:
        customers_contact_point.customer_id, customers_contact_point.type

    A leitura de que isso pede conserto no guestman é a leitura errada.
    ``Customer.phone`` é CACHE — está escrito no docstring do módulo — e o
    ``_sync_contact_points`` é atalho para o PRIMEIRO contato, não API de troca.
    Quem troca contato é ``ContactPoint.set_as_primary()``, que já faz na ordem
    certa: demove os outros primários do tipo, promove a si, e sincroniza o
    cache do ``Customer`` por ``.update()`` (sem reentrar no ``save()``).

    **O número antigo SAI, não vira secundário.** Aqui a decisão diverge da do
    e-mail, e por um motivo mais forte que "a tela tem um campo só": nesta loja
    o telefone é a IDENTIDADE — é por ele que se entra, por OTP. E
    ``get_by_phone`` acha o cliente por QUALQUER ContactPoint de telefone, sem
    olhar ``is_primary``. Um número velho deixado para trás como secundário
    continuaria abrindo esta conta por OTP — e quem muda de número costuma
    mudar porque perdeu aquele, que a operadora recicla para um estranho em
    poucos meses. Guardar o histórico não vale entregar a chave junto.
    """
    from shopman.guestman.models import ContactPoint

    if _phone_belongs_to_someone_else(customer, phone):
        raise ContactAlreadyTaken(PHONE_TAKEN_DETAIL, field="phone")

    numeros_antigos = set(
        ContactPoint.objects.filter(
            customer=customer,
            type__in=PHONE_CONTACT_TYPES,
        )
        .exclude(value_normalized=phone)
        .values_list("value_normalized", flat=True)
    )

    for tipo in PHONE_CONTACT_TYPES:
        contato, _created = ContactPoint.objects.get_or_create(
            customer=customer,
            type=tipo,
            value_normalized=phone,
            defaults={"value_display": phone},
        )
        if not contato.is_primary:
            contato.set_as_primary()
        if not contato.is_verified:
            contato.mark_verified(ContactPoint.VerificationMethod.OTP_WHATSAPP)

    ContactPoint.objects.filter(
        customer=customer,
        type__in=PHONE_CONTACT_TYPES,
        value_normalized__in=numeros_antigos,
    ).delete()

    customer.refresh_from_db(fields=["phone"])


def request_phone_change(customer, raw_phone: str, *, ip_address: str | None = None):
    """Manda o código para o número NOVO. Nada muda no cadastro ainda.

    O código vai para o número novo porque é ele que precisa ser provado. A
    sessão já prova a conta atual; o que falta provar é que quem pede a troca
    atende no número que quer adotar. Sem isso, trocar o telefone seria
    sequestro de conta com uma requisição: aponte a conta de outra pessoa para
    um número seu e o próximo OTP chega na sua mão.
    """
    from shopman.utils.phone import normalize_phone

    from shopman.shop.services import auth as auth_service

    phone = normalize_phone(raw_phone or "")
    if not phone:
        raise PhoneChangeRefused(
            "Confira o número: faltou algum dígito.",
            field="phone",
            error_code="invalid_phone",
        )

    if phone == (customer.phone or ""):
        raise PhoneChangeRefused(
            "Esse já é o seu número.",
            field="phone",
            error_code="phone_unchanged",
        )

    if _phone_belongs_to_someone_else(customer, phone):
        raise ContactAlreadyTaken(PHONE_TAKEN_DETAIL, field="phone")

    resultado = auth_service.request_contact_verification_code(
        phone=phone,
        delivery_method="whatsapp",
        ip_address=ip_address,
    )
    return phone, resultado


def confirm_phone_change(customer, raw_phone: str, code_input: str) -> str:
    """Confere o código e, só então, troca o número. Devolve o número novo."""
    from django.db import IntegrityError, transaction
    from shopman.utils.phone import normalize_phone

    from shopman.shop.services import auth as auth_service

    phone = normalize_phone(raw_phone or "")
    if not phone:
        raise PhoneChangeRefused(
            "Confira o número: faltou algum dígito.",
            field="phone",
            error_code="invalid_phone",
        )

    codigo = "".join(ch for ch in (code_input or "") if ch.isdigit())
    if len(codigo) != 6:
        raise PhoneChangeRefused(
            "Informe os 6 números do código.",
            field="code",
            error_code="code_incomplete",
        )

    # A conferência fica FORA da transação da troca de propósito: ela grava a
    # tentativa gasta, e uma recusa mais adiante não pode devolver tentativa
    # para quem está chutando código.
    resultado = auth_service.verify_contact_code(
        phone=phone,
        code_input=codigo,
        customer_uuid=customer.uuid,
    )
    if not resultado.success:
        raise PhoneChangeRefused(
            auth_service.contact_verify_error_message(resultado),
            field="code",
            error_code=resultado.error_code or "code_invalid",
        )

    with transaction.atomic():
        try:
            _set_primary_phone(customer, phone)
        except IntegrityError as exc:
            # O dono do número pode aparecer entre a checagem e a escrita. A
            # recusa tem de chegar com nome, não como falha genérica.
            raise ContactAlreadyTaken(PHONE_TAKEN_DETAIL, field="phone") from exc

    return phone


def _set_primary_email(customer, email: str) -> None:
    """Promove o e-mail a contato principal do cliente — pelo Core, não à mão.

    O caminho antigo renomeava o ContactPoint primário no lugar
    (``value_normalized = novo``). Funciona no caso simples e recusa no caso
    real: se o cliente já tiver outro ContactPoint de e-mail com esse valor, o
    UNIQUE global ``(type, value_normalized)`` barra a renomeação — e a barreira
    saía como erro genérico.

    O Core já resolve isto: ``ContactPoint.set_as_primary()`` demove o primário
    antigo antes de promover o novo (em transação, respeitando o UNIQUE parcial
    de um primário por tipo) e sincroniza o cache do Customer.
    ⚠️ ``Customer.email`` é CACHE; o ContactPoint é a fonte da verdade.

    O primário substituído sai: a tela de perfil tem UM campo de e-mail, e
    "trocar" ali sempre significou trocar. Deixá-lo para trás prenderia o
    endereço antigo neste cadastro para sempre, sem tela que o solte.
    """
    from shopman.guestman.models import ContactPoint

    owner_exists = (
        ContactPoint.objects.filter(
            type=ContactPoint.Type.EMAIL,
            value_normalized=email,
        )
        .exclude(customer=customer)
        .exists()
    )
    if owner_exists:
        raise ContactAlreadyTaken()

    previous_primary = ContactPoint.objects.filter(
        customer=customer,
        type=ContactPoint.Type.EMAIL,
        is_primary=True,
    ).first()

    contact, _created = ContactPoint.objects.get_or_create(
        customer=customer,
        type=ContactPoint.Type.EMAIL,
        value_normalized=email,
        defaults={"value_display": email},
    )
    if not contact.is_primary:
        contact.set_as_primary()

    if previous_primary and previous_primary.pk != contact.pk:
        previous_primary.delete()


def update_profile(customer_ref: str, intent):
    from django.db import IntegrityError, transaction
    from shopman.guestman.models import ContactPoint
    from shopman.guestman.services import customer as customer_service

    with transaction.atomic():
        customer = customer_service.get(customer_ref)
        if not customer:
            return None

        # `UNSET` = a requisição não falou deste campo; deixe-o como está.
        # `""` = a requisição pediu para limpar. Os dois eram a mesma coisa até
        # 01/09, e por isso o portão de boas-vindas apagava o e-mail de quem só
        # confirmou o nome.
        from shopman.shop.sentinels import UNSET

        email_provided = intent.email is not UNSET
        email = (intent.email or "").strip().lower() if email_provided else ""
        if email:
            _set_primary_email(customer, email)
        elif email_provided:
            ContactPoint.objects.filter(
                customer=customer,
                type=ContactPoint.Type.EMAIL,
                is_primary=True,
            ).delete()

        campos = {"first_name": intent.first_name}
        if intent.last_name is not UNSET:
            campos["last_name"] = intent.last_name
        if email_provided:
            campos["email"] = email
        if intent.birthday is not UNSET:
            campos["birthday"] = intent.birthday

        try:
            return customer_service.update(customer_ref, **campos)
        except IntegrityError as exc:
            # ``Customer.save()`` espelha o e-mail num ContactPoint cujo UNIQUE
            # ``(type, value_normalized)`` é GLOBAL. Se o dono aparecer entre a
            # checagem e a escrita, a recusa chega por aqui — e tem de chegar
            # com nome, não como frase genérica.
            raise ContactAlreadyTaken() from exc


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


def set_notification_consent(customer_ref: str, channel: str, *, enabled: bool, ip_address: str = "") -> set[str]:
    """Set an explicit desired state under the canonical customer lock."""
    from django.db import transaction
    from shopman.guestman import ConsentService
    from shopman.guestman.models import Customer
    if type(enabled) is not bool or channel not in NOTIFICATION_CONSENT_CHANNELS:
        raise ValueError("Invalid consent state")
    with transaction.atomic():
        Customer.objects.select_for_update().get(ref=customer_ref)
        if not enabled:
            ConsentService.revoke_consent(customer_ref, channel)
        elif not ConsentService.has_consent(customer_ref, channel):
            ConsentService.grant_consent(customer_ref, channel, source="storefront_settings", legal_basis="consent", ip_address=ip_address)
        return _complete_notification_preferences(customer_ref)


def toggle_notification_consent(customer_ref: str, channel: str, *, ip_address: str = "") -> set[str]:
    """Legacy adapter; new callers send the desired state and an intention key."""
    from django.db import transaction
    from shopman.guestman import ConsentService
    from shopman.guestman.models import Customer
    with transaction.atomic():
        Customer.objects.select_for_update().get(ref=customer_ref)
        return set_notification_consent(customer_ref, channel, enabled=not ConsentService.has_consent(customer_ref, channel), ip_address=ip_address)


def _complete_notification_preferences(customer_ref: str) -> set[str]:
    # Preserve the existing rule: preferences displayed off gain explicit opt-out.
    from shopman.guestman import ConsentService
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


def _customer_conversations(customer_ref: str, phone: str):
    """Conversas identificadas pelo mesmo titular, sem depender do cadastro ativo."""
    from django.db.models import Q

    from shopman.shop.models import Conversation

    query = Q()
    if customer_ref:
        query |= Q(customer_ref=customer_ref)
    if phone:
        query |= Q(phone=phone)
    return Conversation.objects.filter(query) if query.children else Conversation.objects.none()


def _order_personal_data(order) -> dict:
    """Prefer current order PII, falling back to the immutable checkout snapshot."""

    current = order.data or {}
    snapshot = ((order.snapshot or {}).get("data") or {})
    result = {}
    for key in _PII_DATA_KEYS:
        value = current.get(key)
        if value in (None, "", {}, []):
            value = snapshot.get(key)
        if value not in (None, "", {}, []):
            result[key] = value
    return result


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
            "customer_type": customer.customer_type,
            "notes": customer.notes,
            "tags": list(customer.tags.names()),
            "created_at": customer.created_at.isoformat(),
            "updated_at": customer.updated_at.isoformat(),
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

    data["contact_points"] = [
        {
            "type": contact.type,
            "value": contact.value_normalized,
            "is_primary": contact.is_primary,
            "is_verified": contact.is_verified,
            "verification_method": contact.verification_method,
            "verified_at": contact.verified_at,
            "created_at": contact.created_at,
        }
        for contact in customer.contact_points.all()
    ]
    data["identifiers"] = [
        {
            "type": identifier.identifier_type,
            "value": identifier.identifier_value,
            "is_primary": identifier.is_primary,
            "verified_at": identifier.verified_at,
            "source": identifier.source_system,
            "created_at": identifier.created_at,
        }
        for identifier in customer.identifiers.all()
    ]
    data["external_identities"] = [
        {
            "provider": identity.provider,
            "provider_uid": identity.provider_uid,
            "provider_data": identity.provider_meta,
            "is_active": identity.is_active,
            "created_at": identity.created_at,
        }
        for identity in customer.external_identities.all()
    ]

    # Direito de acesso não pode depender de um teto silencioso. Em contas com
    # mais de 200 pedidos, o JSON antigo dizia "exportação" mas entregava só uma
    # amostra. A resposta é protegida por step-up e deve ser integral.
    orders = _customer_orders(customer.ref, customer.phone or "").order_by("-created_at")
    data["orders"] = [
        {
            "ref": order.ref,
            "status": order.status,
            "channel": order.channel_ref,
            "currency": order.currency,
            "total_q": (order.snapshot or {}).get("pricing", {}).get("total_q", order.total_q),
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "items": list((order.snapshot or {}).get("items", [])),
            "personal_data": _order_personal_data(order),
        }
        for order in orders
    ]

    data["preferences"] = [
        {
            "category": pref.category,
            "key": pref.key,
            "value": pref.value,
            "preference_type": pref.preference_type,
            "confidence": pref.confidence,
            "source": pref.source,
            "notes": pref.notes,
            "created_at": pref.created_at,
            "updated_at": pref.updated_at,
        }
        for pref in preferences(customer.ref)
    ]

    from shopman.guestman import ConsentService

    data["consents"] = [
        {
            "channel": consent.channel,
            "purpose": consent.purpose,
            "status": consent.status,
            "legal_basis": consent.legal_basis,
            "source": consent.source,
            "policy_version": consent.policy_version,
            "proof_status": consent.proof_status,
            "consented_at": consent.consented_at,
            "revoked_at": consent.revoked_at,
        }
        for consent in ConsentService.get_consents(customer.ref)
    ]

    from shopman.guestman.contrib.consent.models import CommunicationConsentEvent

    data["consent_history"] = [
        {
            "channel": event.channel,
            "purpose": event.purpose,
            "event": event.event_type,
            "resulting_status": event.resulting_status,
            "legal_basis": event.legal_basis,
            "source": event.source,
            "disclosure_text": event.disclosure_text,
            "disclosure_version": event.disclosure_version,
            "proof_status": event.proof_status,
            "occurred_at": event.occurred_at,
        }
        for event in CommunicationConsentEvent.objects.filter(customer=customer).order_by("occurred_at", "pk")
    ]

    data["timeline"] = [
        {
            "type": event.event_type,
            "title": event.title,
            "description": event.description,
            "channel": event.channel,
            "reference": event.reference,
            "metadata": event.metadata,
            "created_at": event.created_at,
        }
        for event in customer.timeline_events.all()
    ]

    try:
        insight = customer.insight
    except ObjectDoesNotExist:
        insight = None
    if insight is not None:
        data["customer_insight"] = {
            "total_orders": insight.total_orders,
            "total_spent_q": insight.total_spent_q,
            "average_ticket_q": insight.average_ticket_q,
            "first_order_at": insight.first_order_at,
            "last_order_at": insight.last_order_at,
            "preferred_weekday": insight.preferred_weekday,
            "preferred_hour": insight.preferred_hour,
            "favorite_products": insight.favorite_products,
            "preferred_channel": insight.preferred_channel,
            "channels_used": insight.channels_used,
            "rfm_segment": insight.rfm_segment,
            "churn_risk": insight.churn_risk,
            "predicted_ltv_q": insight.predicted_ltv_q,
            "calculated_at": insight.calculated_at,
        }

    data["conversations"] = [
        {
            "provider_subscriber_id": conversation.subscriber_id,
            "channel": conversation.channel_ref,
            "state": conversation.state,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            # Só a transcrição visível. Blocos internos podem conter tokens de
            # sacola e chamadas de ferramenta que não são dados do titular.
            "messages": [
                {
                    "direction": "received" if message.role == "user" else "sent",
                    "text": message.text,
                    "created_at": message.created_at,
                }
                for message in conversation.messages.exclude(text="")
            ],
        }
        for conversation in _customer_conversations(customer.ref, customer.phone or "").prefetch_related("messages")
    ]

    data["marketing_audiences"] = [
        {
            "audience": str(member.snapshot.ref),
            "announcement": member.snapshot.announcement_id,
            "reasons": member.reasons,
            "created_at": member.created_at,
        }
        for member in customer.marketing_audience_memberships.select_related("snapshot")
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
            txns = account.transactions.all()
            data["loyalty"]["transactions"] = [
                {
                    "type": txn.transaction_type,
                    "points": txn.points,
                    "balance_after": txn.balance_after,
                    "description": txn.description,
                    "reference": txn.reference,
                    "created_at": txn.created_at.isoformat(),
                }
                for txn in txns
            ]
    except Exception:
        logger.warning("data_export_loyalty_failed", exc_info=True)

    return data


def export_auth_data(customer_uuid) -> dict:
    """Export authentication data through the orchestrator's kernel boundary."""

    from shopman.doorman import SubjectType, TrustedDevice
    from shopman.doorman.models import CustomerUser, Passkey

    try:
        auth_link = CustomerUser.objects.get(customer_id=customer_uuid)
    except CustomerUser.DoesNotExist:
        auth_profile = None
    else:
        auth_profile = {
            "created_at": auth_link.created_at,
            "metadata": auth_link.metadata,
        }

    return {
        "authentication_profile": auth_profile,
        "trusted_devices": [
            {
                "label": device.label,
                "user_agent": device.user_agent,
                "ip_address": device.ip_address,
                "created_at": device.created_at,
                "last_used_at": device.last_used_at,
                "expires_at": device.expires_at,
                "is_active": device.is_active,
            }
            for device in TrustedDevice.objects.filter(
                subject_type=SubjectType.CUSTOMER,
                subject_id=str(customer_uuid),
            ).order_by("-created_at")
        ],
        "passkeys": [
            {
                "credential_id": passkey.credential_id,
                "public_key": passkey.public_key,
                "label": passkey.label,
                "transports": passkey.transports,
                "sign_count": passkey.sign_count,
                "created_at": passkey.created_at,
                "last_used_at": passkey.last_used_at,
            }
            for passkey in Passkey.objects.filter(customer_id=customer_uuid).order_by(
                "-created_at"
            )
        ],
    }


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

    # Perfis, histórico de atendimento e segmentação não têm obrigação fiscal e
    # não podem sobreviver ligados ao cadastro pseudonimizado. Cada etapa é
    # independente para a rotina continuar apagando o máximo possível.
    for label, delete in (
        ("apagar preferências", lambda: customer.preferences.all().delete()),
        ("apagar timeline", lambda: customer.timeline_events.all().delete()),
        ("apagar fidelidade", lambda: customer.loyalty_account.delete()),
        ("apagar etiquetas", lambda: customer.tags.clear()),
        (
            "apagar conversas",
            lambda: _customer_conversations(original_ref, original_phone).delete(),
        ),
        (
            "desvincular públicos de marketing",
            lambda: customer.marketing_audience_memberships.all().delete(),
        ),
    ):
        try:
            delete()
        except Exception as exc:
            if not _nada_a_apagar(exc):
                falhas.append(label)
            logger.warning("anonymize: %s falhou customer=%s", label, original_ref, exc_info=True)

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
