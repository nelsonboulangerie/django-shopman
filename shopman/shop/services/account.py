"""Storefront account mutation service.

Views keep HTTP, HTMX rendering, and permission response details here; Guestman
mutations live behind this facade.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from django.db import transaction

logger = logging.getLogger(__name__)

# Domain registry of consent channels this shop tracks. Display copy (labels,
# descriptions) is a storefront concern and lives in storefront.presentation.account.
NOTIFICATION_CONSENT_CHANNELS: tuple[str, ...] = ("whatsapp", "email", "sms", "push")


class AccountUnavailable(ValueError):
    """A conta não existe mais ou perdeu autoridade para receber mutações."""


def lock_active_customer(
    *,
    customer_ref: str = "",
    customer_pk: int | None = None,
    customer_uuid=None,
):
    """Cerca canônica compartilhada com a exclusão de conta.

    Toda mutação pessoal deve adquirir ``Customer`` primeiro. Se a exclusão
    venceu a corrida, a linha continua no banco, mas inativa, e nenhuma escrita
    posterior pode recriar endereço, perfil, preferência ou consentimento.
    """

    from shopman.guestman.models import Customer

    query = Customer.objects.select_for_update().filter(is_active=True)
    if customer_pk is not None:
        query = query.filter(pk=customer_pk)
    elif customer_uuid is not None:
        query = query.filter(uuid=customer_uuid)
    elif customer_ref:
        query = query.filter(ref=customer_ref)
    else:
        raise ValueError("customer_ref, customer_pk or customer_uuid is required")
    customer = query.first()
    if customer is None:
        raise AccountUnavailable("customer_unavailable")
    return customer


def lock_customer_for_privacy(customer_pk: int):
    """Trava inclusive uma conta inativa para decidir replay da exclusão."""

    from shopman.guestman.models import Customer

    return Customer.objects.select_for_update().get(pk=customer_pk)


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

    with transaction.atomic():
        lock_active_customer(customer_ref=customer_ref)
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

    with transaction.atomic():
        lock_active_customer(customer_ref=customer_ref)
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

    with transaction.atomic():
        lock_active_customer(customer_ref=customer_ref)
        address_service.update_address(customer_ref, pk, label=label, label_custom=label_custom)


def delete_address(customer_ref: str, pk: int) -> None:
    from shopman.guestman.services import address as address_service

    with transaction.atomic():
        lock_active_customer(customer_ref=customer_ref)
        address_service.delete_address(customer_ref, pk)


def set_default_address(customer_ref: str, pk: int) -> None:
    from shopman.guestman.services import address as address_service

    with transaction.atomic():
        lock_active_customer(customer_ref=customer_ref)
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

    with transaction.atomic():
        locked_customer = lock_active_customer(customer_pk=customer.pk)
        if phone == (locked_customer.phone or ""):
            raise PhoneChangeRefused(
                "Esse já é o seu número.",
                field="phone",
                error_code="phone_unchanged",
            )

        if _phone_belongs_to_someone_else(locked_customer, phone):
            raise ContactAlreadyTaken(PHONE_TAKEN_DETAIL, field="phone")
        customer_uuid = locked_customer.uuid

    # Provider I/O is deliberately outside the Customer transaction.  The OTP
    # service starts a new durable phase and revalidates the active customer.
    resultado = auth_service.request_contact_verification_code(
        phone=phone,
        delivery_method="whatsapp",
        ip_address=ip_address,
        customer_uuid=customer_uuid,
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

    resultado = None
    conflict = False
    with transaction.atomic():
        locked_customer = lock_active_customer(customer_pk=customer.pk)
        resultado = auth_service.verify_contact_code(
            phone=phone,
            code_input=codigo,
            customer_uuid=locked_customer.uuid,
        )
        if resultado.success:
            try:
                with transaction.atomic():
                    _set_primary_phone(locked_customer, phone)
            except IntegrityError:
                # O savepoint reverte somente os contatos. O OTP confirmado
                # continua consumido quando a transação externa fechar.
                conflict = True

    if not resultado.success:
        raise PhoneChangeRefused(
            auth_service.contact_verify_error_message(resultado),
            field="code",
            error_code=resultado.error_code or "code_invalid",
        )
    if conflict:
        raise ContactAlreadyTaken(PHONE_TAKEN_DETAIL, field="phone")

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
        customer = lock_active_customer(customer_ref=customer_ref)

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

    with transaction.atomic():
        lock_active_customer(customer_ref=customer_ref)
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
        Customer.objects.select_for_update().get(ref=customer_ref, is_active=True)
        if not enabled:
            ConsentService.revoke_consent(customer_ref, channel)
        elif not ConsentService.has_consent(customer_ref, channel):
            ConsentService.grant_consent(
                customer_ref, channel, source="storefront_settings", legal_basis="consent", ip_address=ip_address
            )
        return _complete_notification_preferences(customer_ref)


def toggle_notification_consent(customer_ref: str, channel: str, *, ip_address: str = "") -> set[str]:
    """Legacy adapter; new callers send the desired state and an intention key."""
    from django.db import transaction
    from shopman.guestman import ConsentService
    from shopman.guestman.models import Customer

    with transaction.atomic():
        Customer.objects.select_for_update().get(ref=customer_ref, is_active=True)
        return set_notification_consent(
            customer_ref, channel, enabled=not ConsentService.has_consent(customer_ref, channel), ip_address=ip_address
        )


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
                customer_ref,
                other,
                exc_info=True,
            )

    return enabled_notification_channels(customer_ref)


# ── A declaração de maioridade, feita ao ENTRAR ─────────────────────────
#
# Decisão do dono (16/09): pedir data de nascimento para receber novidades é
# atrito demais e "parece conteúdo adulto". A prova de maioridade para
# marketing direto passa a ser autodeclaração, e ela mora na ENTRADA da loja:
# a nota ao lado do botão diz "Ao continuar, você confirma que é maior de idade
# e aceita os Termos de uso", e toda autenticação bem-sucedida (código,
# aparelho reconhecido, access link, passkey) carimba o cadastro. A data de
# nascimento continua opcional no perfil e só vale para o CONTRÁRIO: se provar
# menor, vence a declaração (`marketing_age.is_proved_adult`).
#
# Precedente da casa: o "Avise-me" (`StockAlertSubscription.adult_declared`)
# já prova maioridade por aceite específico, sem data.
#
# O carimbo é idempotente e guarda a versão dos termos que a pessoa leu. Quem
# já tem conta ganha a declaração no próximo login.
LOGIN_TERMS_VERSION = "login-terms-pt-BR-v1"
# A frase que a pessoa lê ao lado do botão de entrar, em TODOS os caminhos
# (`surfaces/storefront-nuxt/app/presentation/auth.ts`). É o que a versão
# acima representa — o teste de contrato lê o .ts e confere. Mudou a frase?
# Sobe a versão aqui E em `marketing_age.ADULT_DECLARING_TERMS_VERSIONS`.
LOGIN_TERMS_SENTENCE = "Ao continuar, você confirma que é maior de idade e aceita os Termos de uso."
ADULT_DECLARATION_SOURCE = "storefront_login"


def record_adult_declaration(
    customer,
    *,
    terms_version: str = LOGIN_TERMS_VERSION,
    ip_address: str = "",
) -> dict:
    """Carimbar ``Customer.metadata["adult_declaration"]`` na autenticação.

    Idempotente: a PRIMEIRA declaração fica — é ela a evidência de quando a
    pessoa aceitou os termos. Já carimbado, não toca o banco (o ``customer``
    que os views recebem veio de uma leitura recente). Só a primeira vez
    trava a linha e grava.
    """
    from django.utils import timezone

    from shopman.shop.services.marketing_age import ADULT_DECLARATION_KEY

    existing = (getattr(customer, "metadata", None) or {}).get(ADULT_DECLARATION_KEY)
    if isinstance(existing, dict) and existing.get("terms_version"):
        return existing

    with transaction.atomic():
        locked = lock_active_customer(customer_pk=customer.pk)
        metadata = dict(locked.metadata or {})
        current = metadata.get(ADULT_DECLARATION_KEY)
        if isinstance(current, dict) and current.get("terms_version"):
            customer.metadata = metadata
            return current
        declaration = {
            "at": timezone.now().isoformat(),
            "terms_version": terms_version,
            "source": ADULT_DECLARATION_SOURCE,
        }
        if ip_address:
            declaration["ip_address"] = ip_address
        metadata[ADULT_DECLARATION_KEY] = declaration
        locked.metadata = metadata
        locked.save(update_fields=["metadata", "updated_at"])
    # O objeto do chamador passa a refletir o carimbo sem nova leitura.
    customer.metadata = metadata
    return declaration


# ── A pergunta de marketing, feita UMA vez, na entrada ──────────────────
#
# Medido no banco vivo em 16/09: 58 clientes ativos, 1 com aniversário, 5 com
# consentimento de WhatsApp. O resolvedor de audiência (`services/audience.py`)
# exclui quem não prova maioridade e quem não tem `CommunicationConsent`
# whatsapp `opted_in` — campanha direta alcançava ninguém. O consentimento
# passa a ser PERGUNTADO num bottom sheet da loja (na página em que a pessoa
# cai depois de entrar — nunca como passo de login), uma vez por cliente, e
# continua acessível em Conta › Preferências. A maioridade NÃO é perguntada aqui: ela
# é declarada ao entrar (`record_adult_declaration`, acima) — a chave de
# novidades é só consentimento.
#
# "Já respondeu" tem duas provas, qualquer uma basta: existe linha de
# consentimento no canal whatsapp (qualquer status — quem passou por
# Preferências já disse o que quer) OU o carimbo abaixo em `Customer.metadata`.
#
# ⚠️ Fechar o sheet sem ligar a chave grava SÓ o carimbo, nunca
# `opted_out`. Um opt-out gravado é PROIBIÇÃO: `services/notification.py`
# (`_revoked_notification_channels`) cala até o aviso do PRÓPRIO pedido naquele
# canal, e a tela de Preferências avisa isso. "Depois" não é "nunca".
MARKETING_PROMPT_CHANNEL = "whatsapp"
MARKETING_PROMPT_ANSWERED_AT = "marketing_prompt_answered_at"
MARKETING_PROMPT_SOURCE = "storefront_welcome"


def marketing_prompt_pending(customer) -> bool:
    """Se a loja ainda deve PERGUNTAR sobre novidades a este cliente.

    Falha fechado: se a fonte de consentimento não responde, não pergunta — o
    payload de sessão não pode derrubar a sessão inteira por causa disso.
    """
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    if not customer_ref:
        return False
    metadata = getattr(customer, "metadata", None) or {}
    if isinstance(metadata, dict) and metadata.get(MARKETING_PROMPT_ANSWERED_AT):
        return False
    try:
        from shopman.guestman import ConsentService

        consents = ConsentService.get_consents(customer_ref)
    except Exception:
        logger.warning("marketing_prompt.consent_source_unavailable customer=%s", customer_ref, exc_info=True)
        return False
    return not any(consent.channel == MARKETING_PROMPT_CHANNEL for consent in consents)


def answer_marketing_prompt(
    customer_ref: str,
    *,
    whatsapp: bool,
    ip_address: str = "",
    disclosure_text: str,
    disclosure_version: str,
) -> dict:
    """Registrar a resposta da pergunta de novidades. Idempotente.

    ``disclosure_text``/``disclosure_version`` são a frase EXATA que a pessoa
    leu ao lado da chave e a versão dela: viram a evidência imutável do
    consentimento (`CommunicationConsentEvent`). A superfície é quem sabe o que
    mostrou — por isso ela manda, e o serviço não inventa um texto padrão.

    ``whatsapp=True`` concede o consentimento de marketing SÓ nesse canal, via
    ``ConsentService`` — e não por ``set_notification_consent``, porque aquele
    caminho completa os outros canais com ``opted_out`` explícito
    (`_complete_notification_preferences`). Na tela de Preferências isso é
    coerente: as chaves estão à vista, desligadas. No gate o cliente só viu a
    caixa do WhatsApp; gravar "não quero e-mail/SMS" por ele seria inventar
    recusa, e calaria o recado do próprio pedido nesses canais.

    Não pede data de nascimento: a maioridade foi declarada ao entrar
    (`record_adult_declaration`). A data continua opcional no perfil e só vale
    para o contrário — menor conhecido não recebe consentimento (LGPD art. 14):
    a resposta fica carimbada e o canal segue sem linha.
    """
    from django.utils import timezone
    from shopman.guestman import ConsentService

    from shopman.shop.services.marketing_age import is_known_minor

    with transaction.atomic():
        customer = lock_active_customer(customer_ref=customer_ref)
        granted = False
        if whatsapp:
            if not is_known_minor(getattr(customer, "birthday", None)):
                if not ConsentService.has_consent(customer_ref, MARKETING_PROMPT_CHANNEL):
                    ConsentService.grant_consent(
                        customer_ref,
                        MARKETING_PROMPT_CHANNEL,
                        source=MARKETING_PROMPT_SOURCE,
                        legal_basis="consent",
                        ip_address=ip_address or None,
                        disclosure_text=disclosure_text,
                        disclosure_version=disclosure_version,
                    )
                granted = True

        metadata = dict(customer.metadata or {})
        if not metadata.get(MARKETING_PROMPT_ANSWERED_AT):
            metadata[MARKETING_PROMPT_ANSWERED_AT] = timezone.now().isoformat()
            customer.metadata = metadata
            customer.save(update_fields=["metadata", "updated_at"])

    return {
        "answered_at": metadata[MARKETING_PROMPT_ANSWERED_AT],
        "whatsapp_opted_in": granted,
    }


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
    "customer_ref",
    "customer_phone",
    "customer_email",
    "customer_tax_id",
    "name",
    "phone",
    "email",
    "tax_id",
    "document",
    "receipt_email",
    "recipient_name",
    "recipient_phone",
    "delivery_address",
    "delivery_address_structured",
    "recipient",  # presente para terceiro: nome e telefone de quem recebe
    "gift_message",
    "order_notes",  # texto livre escrito pelo cliente
)

_PII_NESTED_KEYS: dict[str, frozenset[str]] = {
    "receipt": frozenset({"email", "customer_name", "customer_phone"}),
    "notification_context": frozenset(
        {"customer_name", "customer_phone", "customer_email", "recipient_name", "recipient_phone"}
    ),
    "context": frozenset({"customer_name", "customer_phone", "customer_email", "recipient_name", "recipient_phone"}),
}

# Handles que SÃO a pessoa. `pos_tab`, `table` e o código de pedido do iFood
# identificam a comanda, a mesa ou o pedido — não o titular — e ficam como estão.
_PERSONAL_HANDLE_TYPES: frozenset[str] = frozenset({"phone", "customer", "whatsapp", "manychat"})

# Tipo de handle de um pedido cujo titular pediu exclusão. Trocar o TIPO junto
# com o valor não é cosmético: `customer_orders.customer_identity_filter` casa
# por (handle_type="phone", handle_ref=<telefone>), então um pedido que ficasse
# com `handle_type="phone"` voltaria a ser alcançável por quem passasse a usar
# aquele número depois — inclusive uma pessoa diferente.
ANONYMIZED_HANDLE_TYPE = "anonymized"


def customer_footprint_query(customer_ref: str, phone: str):
    """A pegada canônica do titular em Order/Session.

    Exportação e exclusão compartilham a mesma consulta, mas telefone atual não
    prova autoria histórica: operadoras reciclam números. Registros sem
    ``customer_ref`` permanecem fora do gesto automático até resolução auditada.
    ``phone`` continua no contrato apenas para compatibilidade dos chamadores.
    """
    from django.db.models import Q

    del phone
    canonical = Q()
    if customer_ref:
        canonical |= Q(data__customer_ref=customer_ref)
        canonical |= Q(data__customer__ref=customer_ref)
    return canonical


def _customer_orders(customer_ref: str, phone: str):
    from shopman.orderman.models import Order

    query = customer_footprint_query(customer_ref, phone)
    if not query.children:
        return Order.objects.none()
    return Order.objects.filter(query)


def privacy_order_deletion_blocker(customer_ref: str, phone: str) -> str:
    """Trava pedidos e trabalho vivo antes de autorizar a exclusão.

    A ordem de locks é Customer (adquirido pelo chamador) → Order → Directive.
    Criadores de trabalho operacional já serializam pela Order; workers mudam a
    Directive para RUNNING antes do I/O. Mantemos ambas as linhas travadas até o
    fim da transação para não existir janela entre conferir e anonimizar.
    """

    from shopman.orderman.models import Directive

    from shopman.shop.directives import PERSONAL_ORDER_DELIVERY_TOPICS

    orders = list(_customer_orders(customer_ref, phone).select_for_update().order_by("pk"))
    if any(order.status not in ("completed", "cancelled", "returned") for order in orders):
        return "active_order"
    refs = [order.ref for order in orders]
    live_directives = list(
        Directive.objects.select_for_update()
        .filter(
            payload__order_ref__in=refs,
            status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
        )
        .order_by("pk")
        .values_list("topic", "status")
    )
    if any(state == Directive.Status.RUNNING for _topic, state in live_directives):
        return "order_automation_in_flight"
    if any(topic not in PERSONAL_ORDER_DELIVERY_TOPICS for topic, _state in live_directives):
        return "order_obligation_pending"
    return ""


def privacy_manychat_deletion_blocker(customer) -> str:
    """Return the fail-closed ManyChat blocker without leaking kernel models.

    Storefront is an adapter layer and must not reach into Guestman directly;
    this domain service owns the provider-link facts used by account deletion.
    """
    from shopman.guestman.contrib.identifiers.models import (
        CustomerIdentifier,
        IdentifierType,
    )
    from shopman.guestman.models import ExternalIdentity

    metadata = customer.metadata or {}
    if bool(metadata.get("manychat_resolution_pending")):
        return "manychat_reconciliation_pending"
    linked = (
        CustomerIdentifier.objects.filter(
            customer=customer,
            identifier_type=IdentifierType.MANYCHAT,
        ).exists()
        or ExternalIdentity.objects.filter(
            customer=customer,
            provider=ExternalIdentity.Provider.MANYCHAT,
        ).exists()
        or customer.source_system == "manychat"
        or "manychat_custom_fields" in metadata
    )
    return "manychat_unlink_required" if linked else ""


def privacy_otp_deletion_blocker(customer) -> str:
    """Keep deletion behind every committed, unfinished OTP delivery intent."""
    from django.db.models import Q
    from django.utils import timezone
    from shopman.doorman.models import VerificationCode

    return (
        "otp_delivery_in_flight"
        if VerificationCode.objects.filter(
            customer_id=customer.uuid,
            status=VerificationCode.Status.PENDING,
        )
        .filter(
            Q(delivery_started_at__isnull=False) | Q(expires_at__gt=timezone.now())
        )
        .exists()
        else ""
    )


def _customer_conversations(customer_ref: str, phone: str):
    """Conversas com vínculo canônico; telefone isolado não prova titularidade."""

    from shopman.shop.models import Conversation

    del phone
    return Conversation.objects.filter(customer_ref=customer_ref) if customer_ref else Conversation.objects.none()


def _delete_customer_conversations(customer_ref: str, phone: str) -> int:
    """Apaga a árvore do concierge na ordem exigida pelos vínculos protegidos."""
    from shopman.shop.models import ConversationBinding, ConversationMessage, OutboundAttempt

    conversations = _customer_conversations(customer_ref, phone)
    conversation_ids = tuple(conversations.values_list("id", flat=True))
    if not conversation_ids:
        return 0
    messages = ConversationMessage.objects.filter(conversation_id__in=conversation_ids)
    if OutboundAttempt.objects.filter(
        message__in=messages,
        state=OutboundAttempt.State.EXECUTING,
    ).exists():
        raise RuntimeError("conversation_delivery_in_progress")
    OutboundAttempt.objects.filter(message__in=messages).delete()
    messages.delete()
    ConversationBinding.objects.filter(conversation_id__in=conversation_ids).delete()
    deleted, _ = conversations.delete()
    return deleted


def _scrub_pii(payload) -> tuple[dict, bool]:
    """Devolve (cópia sem as chaves de PII, houve mudança)."""
    if not isinstance(payload, dict):
        return payload, False
    clean = {k: v for k, v in payload.items() if k not in _PII_DATA_KEYS}
    changed = len(clean) != len(payload)
    for container, personal_keys in _PII_NESTED_KEYS.items():
        nested = clean.get(container)
        if not isinstance(nested, dict):
            continue
        scrubbed = {key: value for key, value in nested.items() if key not in personal_keys}
        if len(scrubbed) != len(nested):
            clean[container] = scrubbed
            changed = True
    return clean, changed


_ITEM_CUSTOMIZATION_PII_KEYS = frozenset({"note", "text", "message"})
_ORDER_EVENT_PII_KEYS = frozenset({"note", "reason"})
_SESSION_EVENT_PII_KEYS = frozenset(
    {
        "customer",
        "customer_name",
        "customer_ref",
        "customer_phone",
        "customer_email",
        "customer_tax_id",
        "document",
        "receipt_email",
        "recipient_name",
        "recipient_phone",
        "delivery_address",
        "delivery_address_structured",
        "recipient",
        "gift_message",
        "order_notes",
        "from_ref",
        "to_ref",
        "note",
        "reason",
        "text",
        "message",
    }
)
_SESSION_EVENT_NESTED_PII_KEYS = {
    "receipt": frozenset({"email", "customer_name", "customer_phone"}),
    "notification_context": frozenset(
        {"customer_name", "customer_phone", "customer_email", "recipient_name", "recipient_phone"}
    ),
    "context": frozenset(
        {"customer_name", "customer_phone", "customer_email", "recipient_name", "recipient_phone"}
    ),
}


def _scrub_item_meta(payload) -> tuple[dict, bool]:
    """Remove apenas os textos pessoais de linha que a exportação revela.

    O restante de ``meta`` documenta a venda (desconto, fiscal, tipo de item,
    escolha e acréscimo da customização) e precisa sobreviver. Por isso esta
    cerca é fechada nos caminhos ``customer_note`` e
    ``customization.{note,text,message}``, em vez de apagar o JSON inteiro.
    """
    if not isinstance(payload, dict):
        return payload, False

    clean = dict(payload)
    changed = "customer_note" in clean
    clean.pop("customer_note", None)

    customization = clean.get("customization")
    if isinstance(customization, dict):
        scrubbed = {key: value for key, value in customization.items() if key not in _ITEM_CUSTOMIZATION_PII_KEYS}
        if len(scrubbed) != len(customization):
            clean["customization"] = scrubbed
            changed = True

    return clean, changed


def _scrub_item_payloads(payload) -> tuple[list, bool]:
    """Copia ``items`` e limpa seu ``meta`` sem alterar dados comerciais."""
    if not isinstance(payload, list):
        return payload, False

    clean = list(payload)
    changed = False
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        meta, meta_changed = _scrub_item_meta(item.get("meta"))
        if meta_changed:
            clean_item = dict(item)
            clean_item["meta"] = meta
            clean[index] = clean_item
            changed = True
    return clean, changed


def _scrub_closed_payload_keys(payload, personal_keys: frozenset[str]) -> tuple[dict, bool]:
    """Remove só as chaves livres conhecidas, preservando a prova operacional."""
    if not isinstance(payload, dict):
        return payload, False
    clean = {key: value for key, value in payload.items() if key not in personal_keys}
    return clean, len(clean) != len(payload)


def _scrub_session_event_payload(payload) -> tuple[dict, bool]:
    clean, changed = _scrub_closed_payload_keys(payload, _SESSION_EVENT_PII_KEYS)
    if not isinstance(clean, dict):
        return clean, changed
    for container, personal_keys in _SESSION_EVENT_NESTED_PII_KEYS.items():
        nested = clean.get(container)
        if not isinstance(nested, dict):
            continue
        scrubbed = {key: value for key, value in nested.items() if key not in personal_keys}
        if len(scrubbed) != len(nested):
            clean = dict(clean)
            clean[container] = scrubbed
            changed = True
    return clean, changed


def _cancellation_alert_operational_message(*, order_ref: str, protocol: str) -> str:
    """Reconstrói o alerta sem depender de parsing do texto pessoal anterior."""
    protocol_copy = f" Protocolo {protocol}." if protocol else ""
    return (
        f"O cliente solicitou análise de cancelamento do pedido {order_ref}."
        f"{protocol_copy} Abra o pedido para decidir o cancelamento e eventual estorno."
    )


_GATEWAY_PERSONAL_KEYS = frozenset(
    {
        "billingdetails",
        "cnpj",
        "cpf",
        "customer",
        "customeremail",
        "customername",
        "customerphone",
        "customerref",
        "document",
        "email",
        "firstname",
        "lastname",
        "name",
        "payer",
        "phone",
        "receiptemail",
        "recipient",
        "recipientname",
        "recipientphone",
        "taxid",
    }
)


def _canonical_json_key(value) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _scrub_gateway_pii(value):
    """Redige PII em qualquer profundidade sem perder evidência financeira."""

    if isinstance(value, dict):
        clean = {}
        changed = False
        for key, item in value.items():
            if _canonical_json_key(key) in _GATEWAY_PERSONAL_KEYS:
                changed = True
                continue
            scrubbed, nested_changed = _scrub_gateway_pii(item)
            clean[key] = scrubbed
            changed = changed or nested_changed
        return clean, changed
    if isinstance(value, list):
        clean = []
        changed = False
        for item in value:
            scrubbed, nested_changed = _scrub_gateway_pii(item)
            clean.append(scrubbed)
            changed = changed or nested_changed
        return clean, changed
    return value, False


def _anonymize_order_trail(*, customer_ref: str, phone: str, pseudonym: str) -> dict[str, int]:
    """Apaga o PII do titular dos pedidos e das sessões dele. Idempotente."""
    from django.apps import apps
    from django.db import IntegrityError
    from shopman.orderman.models import Directive, Order, OrderEvent, Session, SessionEvent
    from shopman.payman.models import PaymentIntent

    from shopman.shop.directives import PERSONAL_ORDER_DELIVERY_TOPICS

    counts = {
        "orders": 0,
        "sessions": 0,
        "order_events": 0,
        "session_events": 0,
        "operator_alerts": 0,
        "payment_intents": 0,
        "directives": 0,
    }

    matching_orders = _customer_orders(customer_ref, phone)
    matching_order_refs = tuple(matching_orders.values_list("ref", flat=True))
    cancellation_protocols = dict(
        OrderEvent.objects.filter(
            order__ref__in=matching_order_refs,
            type="customer_cancellation_requested",
        ).values_list("order__ref", "payload__protocol")
    )

    # Só este tipo de alerta carrega texto escrito pelo titular. O prefixo é
    # evidência operacional (pedido + protocolo) e é reconstruído a partir do
    # evento estruturado, sem tentar recortar uma mensagem livre histórica.
    OperatorAlert = apps.get_model("backstage.OperatorAlert")
    cancellation_alerts = OperatorAlert.objects.filter(
        type="customer_cancellation_requested",
        order_ref__in=matching_order_refs,
    )
    for alert in cancellation_alerts.only("pk", "order_ref", "message").iterator():
        message = _cancellation_alert_operational_message(
            order_ref=alert.order_ref,
            protocol=str(cancellation_protocols.get(alert.order_ref) or ""),
        )
        if alert.message != message:
            OperatorAlert.objects.filter(pk=alert.pk).update(message=message)
            counts["operator_alerts"] += 1

    payment_intents = PaymentIntent.objects.filter(order_ref__in=matching_order_refs)
    for payment_intent in payment_intents.only("pk", "gateway_data").iterator():
        gateway_data, changed = _scrub_gateway_pii(payment_intent.gateway_data)
        if changed:
            PaymentIntent.objects.filter(pk=payment_intent.pk).update(gateway_data=gateway_data)
            counts["payment_intents"] += 1

    directives = list(
        Directive.objects.select_for_update()
        .filter(payload__order_ref__in=matching_order_refs)
        .order_by("pk")
    )
    if any(directive.status == Directive.Status.RUNNING for directive in directives):
        raise RuntimeError("order_directive_in_progress")
    if any(
        directive.status == Directive.Status.QUEUED
        and directive.topic not in PERSONAL_ORDER_DELIVERY_TOPICS
        for directive in directives
    ):
        raise RuntimeError("order_obligation_pending")
    for directive in directives:
        payload, changed = _scrub_pii(directive.payload)
        updates = {}
        if changed:
            updates["payload"] = payload
        # Exclusão revoga somente mensagens pessoais futuras. Obrigações da
        # venda não são alteradas aqui: se alguma ainda estava enfileirada, a
        # precondição acima bloqueou a exclusão antes de tocar no payload.
        if directive.status == Directive.Status.QUEUED and directive.topic in PERSONAL_ORDER_DELIVERY_TOPICS:
            updates.update(
                status=Directive.Status.FAILED,
                error_code="subject_deleted",
                last_error="",
            )
        if updates:
            Directive.objects.filter(pk=directive.pk).update(**updates)
            counts["directives"] += 1

    for order in matching_orders.iterator():
        fields: dict = {}
        item_meta_changed = False

        for event in order.events.only("pk", "payload").iterator():
            payload, changed = _scrub_closed_payload_keys(event.payload, _ORDER_EVENT_PII_KEYS)
            if changed:
                OrderEvent.objects.filter(pk=event.pk).update(payload=payload)
                counts["order_events"] += 1

        # A linha relacional é uma das três cópias duráveis do meta do item.
        # Atualização direta preserva o selo do pedido e evita writers normais.
        for item in order.items.only("pk", "meta").iterator():
            meta, changed = _scrub_item_meta(item.meta)
            if changed:
                type(item).objects.filter(pk=item.pk).update(meta=meta)
                item_meta_changed = True

        data, changed = _scrub_pii(order.data)
        if changed:
            fields["data"] = data

        # `snapshot["data"]` é a cópia integral de `session.data` no commit — o
        # mesmo PII, uma camada abaixo. Sem isto a varredura do banco continuava
        # achando nome e telefone dentro do retrato selado.
        snapshot = order.snapshot or {}
        snap_data, snap_changed = _scrub_pii(snapshot.get("data"))
        snap_items, snap_items_changed = _scrub_item_payloads(snapshot.get("items"))
        if snap_changed or snap_items_changed:
            snapshot = dict(snapshot)
            if snap_changed:
                snapshot["data"] = snap_data
            if snap_items_changed:
                snapshot["items"] = snap_items
            fields["snapshot"] = snapshot

        if order.handle_ref and order.handle_type in _PERSONAL_HANDLE_TYPES:
            fields["handle_type"] = ANONYMIZED_HANDLE_TYPE
            fields["handle_ref"] = pseudonym

        if not fields and not item_meta_changed:
            continue

        # `.update()` e não `save()`: `snapshot` é campo SELADO (`Order.save()`
        # levanta ImmutabilityError). O selo existe para o conteúdo do pedido não
        # derivar depois de vendido, e continua valendo — a exclusão pedida pelo
        # titular é a única exceção legítima, e ela passa por aqui, uma vez, com
        # o motivo escrito. Nunca afrouxe o selo em `save()` para conseguir isto.
        if fields:
            Order.objects.filter(pk=order.pk).update(**fields)
        counts["orders"] += 1

    query = customer_footprint_query(customer_ref, phone)
    sessions = (
        list(Session.objects.select_for_update().filter(query).order_by("pk"))
        if query.children
        else []
    )
    for session in sessions:
        fields = {}
        item_meta_changed = False
        event_payload_changed = False

        for event in SessionEvent.objects.filter(session_key=session.session_key).only(
            "pk", "payload"
        ).iterator():
            payload, changed = _scrub_session_event_payload(event.payload)
            if changed:
                SessionEvent.objects.filter(pk=event.pk).update(payload=payload)
                counts["session_events"] += 1
                event_payload_changed = True

        # ``Session.items`` é a projeção destas linhas relacionais; limpar a
        # fonte garante que qualquer leitura posterior receba o payload limpo.
        for item in session.session_items.only("pk", "meta").iterator():
            meta, changed = _scrub_item_meta(item.meta)
            if changed:
                type(item).objects.filter(pk=item.pk).update(meta=meta)
                item_meta_changed = True

        data, changed = _scrub_pii(session.data)
        if changed:
            fields["data"] = data
        if session.handle_ref and session.handle_type in _PERSONAL_HANDLE_TYPES:
            fields["handle_type"] = ANONYMIZED_HANDLE_TYPE
            fields["handle_ref"] = pseudonym
        if not fields and not item_meta_changed and not event_payload_changed:
            continue
        if fields:
            try:
                # PostgreSQL marca a transação como quebrada depois de um
                # IntegrityError. O savepoint interno permite tratar a colisão e
                # continuar a anonimização atômica.
                with transaction.atomic():
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


@transaction.atomic
def anonymize_customer(customer, *, correlation_ref: str = "") -> tuple[str, str]:
    """Anonymize personal data and return original ref + phone hash.

    Alcança o Customer (campos, ContactPoint, document, metadata, identidades),
    o User do doorman, o perfil de RFM e — desde a correção do LOTE 6 — o rastro
    do titular em `Order` e `Session`, que é onde o telefone realmente morava.
    """
    # O mesmo Customer é a trava canônica de todos os dados pessoais da conta.
    # A releitura evita decidir com uma instância anterior à espera pelo lock.
    customer = type(customer).objects.select_for_update().get(pk=customer.pk)
    correlation_ref = correlation_ref or str(uuid.uuid4())
    falhas: list[str] = []
    original_ref = customer.ref
    original_phone = customer.phone or ""
    original_email = customer.email or ""
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
            logger.warning("consent_revoke_failed channel=%s correlation=%s", channel, correlation_ref)

    try:
        from shopman.guestman.contrib.consent.models import CommunicationConsentEvent

        CommunicationConsentEvent.redact_subject(customer)
        customer.consents.all().delete()
    except Exception:
        falhas.append("desvincular provas de consentimento")
        logger.warning("consent_evidence_redaction_failed correlation=%s", correlation_ref)

    try:
        address_service.delete_all_addresses(original_ref)
    except Exception as exc:
        if not _nada_a_apagar(exc):
            falhas.append("apagar endereços")
        logger.warning("address_cleanup_failed correlation=%s", correlation_ref)

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
        logger.warning("anonymize: purge_pii falhou correlation=%s", correlation_ref)

    try:
        from shopman.doorman.services._user_bridge import forget_customer

        forget_customer(customer.uuid, phone=original_phone, email=original_email)
    except Exception:
        falhas.append("esquecer o login")
        logger.warning("anonymize: forget_customer falhou correlation=%s", correlation_ref)

    # O pedido e a sessão — onde o telefone é coluna, não campo derivado.
    try:
        counts = _anonymize_order_trail(
            customer_ref=original_ref,
            phone=original_phone,
            pseudonym=pseudonym,
        )
        logger.info(
            "anonymize: rastro apagado correlation=%s orders=%s sessions=%s",
            correlation_ref,
            counts["orders"],
            counts["sessions"],
        )
    except Exception:
        falhas.append("apagar o rastro em pedidos e sessões")
        logger.warning("anonymize: rastro de pedidos falhou correlation=%s", correlation_ref)

    # O perfil de RFM é um retrato comportamental montado para MIRAR a pessoa
    # (recência, frequência, ticket, segmento). Não tem valor fiscal e não
    # sobrevive a um pedido de exclusão: sai inteiro. Os números agregados que o
    # B.I. precisa continuam deriváveis dos pedidos já anonimizados.
    try:
        from shopman.guestman import CustomerInsight

        CustomerInsight.objects.filter(customer=customer).delete()
    except Exception:
        falhas.append("apagar o perfil de RFM")
        logger.warning("anonymize: insight delete falhou correlation=%s", correlation_ref)

    try:
        from django.db.models import Q
        from django.utils import timezone
        from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus

        from shopman.shop.models import ContactRelease

        ContactRelease.objects.filter(released_from_ref=original_ref).update(
            value="",
            released_from_ref=pseudonym,
            released_from_name="",
            released_pk="",
        )
        replacement_uuid = uuid.uuid4()
        MergeAudit.objects.filter(Q(source_ref=original_ref) | Q(source_id=customer.uuid)).update(
            source_ref=pseudonym,
            source_id=replacement_uuid,
            actor="",
            evidence={},
            snapshot={},
            status=MergeStatus.REDACTED,
            reverted_at=timezone.now(),
            reverted_by="",
        )
        MergeAudit.objects.filter(Q(target_ref=original_ref) | Q(target_id=customer.uuid)).update(
            target_ref=pseudonym,
            target_id=replacement_uuid,
            actor="",
            evidence={},
            snapshot={},
            status=MergeStatus.REDACTED,
            reverted_at=timezone.now(),
            reverted_by="",
        )
    except Exception:
        falhas.append("redigir auditorias pessoais")
        logger.warning("anonymize: personal audit redaction failed correlation=%s", correlation_ref)

    # Personalização, fidelidade e conversa não têm obrigação fiscal. Como toda
    # a função é atômica, uma falha em qualquer etapa impede que uma exclusão
    # parcial seja persistida ou declarada concluída.
    for label, delete in (
        ("apagar preferências", lambda: customer.preferences.all().delete()),
        ("apagar timeline", lambda: customer.timeline_events.all().delete()),
        ("apagar fidelidade", lambda: customer.loyalty_account.delete()),
        ("apagar etiquetas", lambda: customer.tags.clear()),
        (
            "apagar conversas",
            lambda: _delete_customer_conversations(original_ref, original_phone),
        ),
    ):
        try:
            delete()
        except Exception as exc:
            if not _nada_a_apagar(exc):
                falhas.append(label)
            logger.warning("anonymize: %s falhou correlation=%s", label, correlation_ref)

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
        logger.warning("anonymize: signal customer_anonymized falhou correlation=%s", correlation_ref)

    if falhas:
        # O coordenador externo registra o recibo e alerta DEPOIS do rollback.
        # Persistir o alerta aqui seria ilusório: esta função é atômica, então a
        # mesma exceção que protege contra meia-exclusão também o desfaria.
        raise AnonymizationIncomplete(falhas)

    return original_ref, phone_hash
