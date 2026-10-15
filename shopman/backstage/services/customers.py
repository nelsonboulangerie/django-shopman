"""Unificar e desfazer cadastros a partir do Gestor.

O trabalho inteiro é do ``MergeService`` do Guestman — prévia, ida e volta.
Aqui só se traduz o pedido do Gestor (dois ``ref``) e a recusa do Core, que é
de engenharia e em inglês, para a frase que o gestor lê.

A evidência do gate G6 é ``staff_override``: quem unifica é um gestor
autenticado, com ``shop.manage_customers``, que viu a prévia lado a lado e
confirmou. A evidência viaja assinada com quem disse e de onde.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from shopman.backstage.services.exceptions import CustomerMergeError, CustomerMutationError, CustomerNotFound

logger = logging.getLogger(__name__)

_EVIDENCE = {
    "staff_override": True,
    "operator_confirmed": True,
    "source_surface": "gestor",
}

_MUTABLE_FIELDS = {
    "firstName",
    "lastName",
    "customerType",
    "document",
    "birthday",
    "email",
    "phone",
    "priceTierRef",
    "tags",
    "notes",
    "houseAccount",
    "houseAccountLimit",
    "fiscalCpfNaNota",
    "fiscalEmailReceipt",
}


def _mutation_error(detail: str, *, field: str = "", code: str = "invalid_payload") -> CustomerMutationError:
    return CustomerMutationError(detail, field=field, code=code)


def _text(data: dict, key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise _mutation_error("Use texto neste campo.", field=key)
    return str(value).strip()


def _birthday(value) -> date | None:
    if value in (None, ""):
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        raise _mutation_error("Informe a data no formato dia, mês e ano.", field="birthday") from None
    if parsed > date.today():
        raise _mutation_error("A data de nascimento não pode estar no futuro.", field="birthday")
    return parsed


def _limit(value) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise _mutation_error("Informe um limite maior que zero ou deixe em branco.", field="houseAccountLimit")
    try:
        amount = Decimal(str(value).replace(".", "").replace(",", ".")) if "," in str(value) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _mutation_error("Informe um limite em reais.", field="houseAccountLimit") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("99999999.99"):
        raise _mutation_error("Informe um limite maior que zero ou deixe em branco.", field="houseAccountLimit")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise _mutation_error("Use no máximo duas casas decimais.", field="houseAccountLimit")
    return int(cents)


def _boolean(data: dict, key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise _mutation_error("Escolha sim ou não.", field=key)
    return value


def _revision(customer) -> str:
    return customer.updated_at.isoformat()


def _assert_revision(customer, data: dict) -> None:
    expected = _text(data, "expectedRevision")
    if not expected:
        raise _mutation_error(
            "Atualize a ficha antes de salvar.", field="expectedRevision", code="revision_required",
        )
    if expected != _revision(customer):
        raise _mutation_error(
            "O cliente mudou desde que você abriu. Atualize e confira antes de salvar.",
            field="expectedRevision",
            code="customer_changed",
        )


def _price_tier(ref: str):
    if not ref:
        return None
    from shopman.guestman.models import PriceTier

    tier = PriceTier.objects.filter(ref=ref).first()
    if tier is None:
        raise _mutation_error("Escolha uma faixa de preço disponível.", field="priceTierRef")
    return tier


def _tags(value) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise _mutation_error("Envie as etiquetas como uma lista.", field="tags")
    normalized: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            raise _mutation_error("Cada etiqueta precisa ser texto.", field="tags")
        tag = re.sub(r"\s+", " ", raw).strip()
        if tag and tag.casefold() not in {item.casefold() for item in normalized}:
            normalized.append(tag[:100])
    if len(normalized) > 30:
        raise _mutation_error("Use no máximo 30 etiquetas.", field="tags")
    return normalized


def _apply_payload(customer, data: dict, *, creating: bool) -> list[str]:
    from shopman.guestman.models import CustomerType
    from shopman.utils.documents import is_valid_tax_id

    unknown = sorted(set(data) - _MUTABLE_FIELDS - {"expectedRevision"})
    if unknown:
        raise _mutation_error(f"Campo desconhecido: {unknown[0]}.", field=unknown[0])

    if creating or "firstName" in data:
        first_name = _text(data, "firstName")
        if not first_name:
            raise _mutation_error("Informe o nome do cliente.", field="firstName")
        customer.first_name = first_name
    if creating or "lastName" in data:
        customer.last_name = _text(data, "lastName")
    if creating or "customerType" in data:
        customer_type = _text(data, "customerType") or CustomerType.INDIVIDUAL
        if customer_type not in CustomerType.values:
            raise _mutation_error("Escolha pessoa física ou jurídica.", field="customerType")
        customer.customer_type = customer_type
    if creating or "document" in data:
        document = re.sub(r"\D", "", _text(data, "document"))
        if document and not is_valid_tax_id(document):
            raise _mutation_error("O CPF ou CNPJ não confere.", field="document")
        customer.document = document
    if creating or "birthday" in data:
        customer.birthday = _birthday(data.get("birthday"))
    if creating or "email" in data:
        customer.email = _text(data, "email").lower()
    if creating or "phone" in data:
        customer.phone = _text(data, "phone")
    if creating or "priceTierRef" in data:
        customer.price_tier = _price_tier(_text(data, "priceTierRef"))
    if creating or "notes" in data:
        customer.notes = _text(data, "notes")

    metadata = dict(customer.metadata or {})
    if creating or "houseAccount" in data:
        if _boolean(data, "houseAccount"):
            metadata["house_account"] = True
        else:
            metadata.pop("house_account", None)
            metadata.pop("house_account_limit_q", None)
    if creating or "houseAccountLimit" in data:
        limit_q = _limit(data.get("houseAccountLimit"))
        if limit_q is None:
            metadata.pop("house_account_limit_q", None)
        elif not metadata.get("house_account"):
            raise _mutation_error(
                "Ative a conta na casa antes de definir um limite.", field="houseAccountLimit",
            )
        else:
            metadata["house_account_limit_q"] = limit_q
    prefs = dict(metadata.get("fiscal_prefs") or {})
    if creating or "fiscalCpfNaNota" in data:
        prefs["cpf_na_nota"] = _boolean(data, "fiscalCpfNaNota")
    if creating or "fiscalEmailReceipt" in data:
        prefs["email_receipt"] = _boolean(data, "fiscalEmailReceipt")
    if any(prefs.values()):
        metadata["fiscal_prefs"] = prefs
    else:
        metadata.pop("fiscal_prefs", None)
    if prefs.get("cpf_na_nota") and not customer.document:
        raise _mutation_error("Informe o CPF ou CNPJ usado na nota.", field="document")
    if prefs.get("email_receipt") and not customer.email:
        raise _mutation_error("Informe o e-mail que receberá a nota.", field="email")
    customer.metadata = metadata
    return _tags(data.get("tags")) if creating or "tags" in data else list(customer.tags.names())


def _save_customer(customer, *, tags: list[str], cleared: set[str]) -> None:
    from shopman.guestman.models import ContactPoint

    try:
        for field, contact_type in (("phone", ContactPoint.Type.PHONE), ("email", ContactPoint.Type.EMAIL)):
            raw = getattr(customer, field)
            if not raw:
                continue
            normalized = ContactPoint.normalize_value(raw, contact_type=contact_type)
            owned = ContactPoint.objects.filter(type=contact_type, value_normalized=normalized)
            if customer.pk:
                owned = owned.exclude(customer=customer)
            if owned.exists():
                raise _mutation_error(
                    f"Este {'telefone' if field == 'phone' else 'e-mail'} já pertence a outro cadastro. Abra o cadastro existente para unificar.",
                    field=field,
                    code="contact_conflict",
                )
        customer.full_clean()
        customer.save()
        customer.tags.set(tags)
        if "phone" in cleared:
            ContactPoint.objects.filter(customer=customer, type__in=(ContactPoint.Type.PHONE, ContactPoint.Type.WHATSAPP)).update(is_primary=False)
        if "email" in cleared:
            ContactPoint.objects.filter(customer=customer, type=ContactPoint.Type.EMAIL).update(is_primary=False)
    except ValidationError as exc:
        messages = getattr(exc, "message_dict", {})
        field = next(iter(messages), "")
        detail = str((messages.get(field) or ["Confira os dados do cliente."])[0])
        raise _mutation_error(detail, field={"first_name": "firstName", "last_name": "lastName"}.get(field, field)) from exc
    except IntegrityError as exc:
        raise _mutation_error(
            "Este telefone ou e-mail já pertence a outro cadastro. Abra o cadastro existente para unificar.",
            code="contact_conflict",
        ) from exc


@transaction.atomic
def create_customer(data: dict, *, actor: str):
    from shopman.guestman.models import Customer

    if not isinstance(data, dict):
        raise _mutation_error("O cadastro precisa ser um objeto.")
    customer = Customer(ref=Customer.generate_ref(), source_system="manual", created_by=actor or "gestor")
    tags = _apply_payload(customer, data, creating=True)
    cleared = {field for field in ("phone", "email") if not getattr(customer, field)}
    _save_customer(customer, tags=tags, cleared=cleared)
    return customer


@transaction.atomic
def update_customer(ref: str, data: dict):
    from shopman.guestman.models import Customer

    if not isinstance(data, dict):
        raise _mutation_error("O cadastro precisa ser um objeto.")
    customer = Customer.objects.select_for_update().filter(ref=ref).first()
    if customer is None:
        raise CustomerNotFound("Cliente não encontrado.")
    if not customer.is_active:
        raise _mutation_error("Este cadastro foi unificado ou desativado e não pode mais ser editado.", code="inactive")
    _assert_revision(customer, data)
    tags = _apply_payload(customer, data, creating=False)
    cleared = {field for field in ("phone", "email") if field in data and not getattr(customer, field)}
    _save_customer(customer, tags=tags, cleared=cleared)
    return customer


_ADDRESS_FIELDS = {
    "label",
    "labelCustom",
    "formattedAddress",
    "route",
    "streetNumber",
    "complement",
    "neighborhood",
    "city",
    "stateCode",
    "postalCode",
    "deliveryInstructions",
    "isDefault",
}


def _active_customer(ref: str, *, lock: bool = False):
    from shopman.guestman.models import Customer

    qs = Customer.objects.filter(ref=ref)
    if lock:
        qs = qs.select_for_update()
    customer = qs.first()
    if customer is None:
        raise CustomerNotFound("Cliente não encontrado.")
    if not customer.is_active:
        raise _mutation_error("Este cadastro foi unificado ou desativado e não pode mais ser editado.", code="inactive")
    return customer


def _apply_address(address, data: dict, *, creating: bool) -> None:
    from shopman.guestman.models.address import AddressLabel

    unknown = sorted(set(data) - _ADDRESS_FIELDS - {"expectedRevision"})
    if unknown:
        raise _mutation_error(f"Campo desconhecido: {unknown[0]}.", field=unknown[0])
    if creating or "label" in data:
        label = _text(data, "label") or AddressLabel.HOME
        if label not in AddressLabel.values:
            raise _mutation_error("Escolha Casa, Trabalho ou Outro.", field="label")
        address.label = label
    mapping = {
        "labelCustom": "label_custom",
        "formattedAddress": "formatted_address",
        "route": "route",
        "streetNumber": "street_number",
        "complement": "complement",
        "neighborhood": "neighborhood",
        "city": "city",
        "stateCode": "state_code",
        "postalCode": "postal_code",
        "deliveryInstructions": "delivery_instructions",
    }
    location_fields = {
        "formattedAddress",
        "route",
        "streetNumber",
        "neighborhood",
        "city",
        "stateCode",
        "postalCode",
    }
    location_changed = creating
    for source, target in mapping.items():
        if creating or source in data:
            value = _text(data, source)
            if source in location_fields and value != getattr(address, target):
                location_changed = True
            setattr(address, target, value)
    address.state_code = address.state_code.upper()
    if address.label == AddressLabel.OTHER:
        if not address.label_custom:
            raise _mutation_error("Dê um nome ao endereço.", field="labelCustom")
    else:
        address.label_custom = ""
    if not address.formatted_address:
        raise _mutation_error("Informe o endereço completo.", field="formattedAddress")
    if creating or "isDefault" in data:
        address.is_default = _boolean(data, "isDefault", default=creating)
    if location_changed:
        address.place_id = ""
        address.latitude = None
        address.longitude = None
        address.is_verified = False


def _save_address(address) -> None:
    try:
        address.full_clean()
        address.save()
    except ValidationError as exc:
        messages = getattr(exc, "message_dict", {})
        field = next(iter(messages), "")
        detail = str((messages.get(field) or ["Confira os dados do endereço."])[0])
        aliases = {"formatted_address": "formattedAddress", "street_number": "streetNumber"}
        raise _mutation_error(detail, field=aliases.get(field, field)) from exc


@transaction.atomic
def create_address(customer_ref: str, data: dict):
    from shopman.guestman.models import CustomerAddress

    if not isinstance(data, dict):
        raise _mutation_error("O endereço precisa ser um objeto.")
    customer = _active_customer(customer_ref, lock=True)
    address = CustomerAddress(customer=customer)
    has_address = CustomerAddress.objects.filter(customer=customer).exists()
    if not has_address:
        # Um cadastro com endereço sempre tem exatamente um padrão. O formulário
        # envia ``false`` por padrão; o primeiro endereço ainda assim é o padrão.
        data = {**data, "isDefault": True}
    elif "isDefault" not in data:
        data = {**data, "isDefault": False}
    _apply_address(address, data, creating=True)
    _save_address(address)
    return address


@transaction.atomic
def update_address(customer_ref: str, address_id: int, data: dict):
    from shopman.guestman.models import CustomerAddress

    if not isinstance(data, dict):
        raise _mutation_error("O endereço precisa ser um objeto.")
    customer = _active_customer(customer_ref, lock=True)
    address = CustomerAddress.objects.select_for_update().filter(pk=address_id, customer=customer).first()
    if address is None:
        raise CustomerNotFound("Endereço não encontrado.")
    expected = _text(data, "expectedRevision")
    if not expected:
        raise _mutation_error("Atualize a ficha antes de salvar.", field="expectedRevision", code="revision_required")
    if expected != address.updated_at.isoformat():
        raise _mutation_error(
            "O endereço mudou desde que você abriu. Atualize e confira antes de salvar.",
            field="expectedRevision",
            code="customer_changed",
        )
    if address.is_default and data.get("isDefault") is False:
        raise _mutation_error(
            "Escolha outro endereço como padrão antes de retirar este.",
            field="isDefault",
            code="default_address_required",
        )
    _apply_address(address, data, creating=False)
    _save_address(address)
    return address


@transaction.atomic
def delete_address(customer_ref: str, address_id: int, data: dict) -> None:
    from shopman.guestman.models import CustomerAddress

    customer = _active_customer(customer_ref, lock=True)
    address = CustomerAddress.objects.select_for_update().filter(pk=address_id, customer=customer).first()
    if address is None:
        raise CustomerNotFound("Endereço não encontrado.")
    expected = _text(data, "expectedRevision") if isinstance(data, dict) else ""
    if not expected:
        raise _mutation_error("Atualize a ficha antes de remover.", field="expectedRevision", code="revision_required")
    if expected != address.updated_at.isoformat():
        raise _mutation_error(
            "O endereço mudou desde que você abriu. Atualize e confira antes de remover.",
            field="expectedRevision",
            code="customer_changed",
        )
    was_default = address.is_default
    address.delete()
    if was_default:
        replacement = CustomerAddress.objects.filter(customer=customer).order_by("pk").first()
        if replacement is not None:
            replacement.is_default = True
            replacement.save(update_fields=["is_default", "updated_at"])


def _pair(source_ref: str, target_ref: str, *, lock: bool = False):
    from shopman.guestman.models import Customer

    source_ref = (source_ref or "").strip()
    target_ref = (target_ref or "").strip()
    if not source_ref or not target_ref:
        raise CustomerMergeError("Escolha os dois cadastros: o que sai e o que fica.")
    if source_ref == target_ref:
        raise CustomerMergeError("Os dois lados são o mesmo cadastro.")

    qs = Customer.objects.filter(ref__in=(source_ref, target_ref))
    if lock:
        # Linhas de Customer antes de qualquer filho que o merge mova, em ordem
        # estável — duas unificações invertidas não se travam.
        qs = qs.select_for_update().order_by("pk")
    by_ref = {customer.ref: customer for customer in qs}
    source, target = by_ref.get(source_ref), by_ref.get(target_ref)
    if source is None or target is None:
        missing = source_ref if source is None else target_ref
        raise CustomerNotFound(f"O cadastro {missing} não existe mais. Recarregue a lista.")
    if not source.is_active:
        raise CustomerMergeError(
            f"{source.ref} já foi unificado a outro cadastro. Abra a ficha dele para ver para onde foi."
        )
    if not target.is_active:
        raise CustomerMergeError(
            f"{target.ref} já foi unificado a outro cadastro e não pode receber este. "
            "Escolha o cadastro que ficou."
        )
    return source, target


def _translate(exc: Exception) -> CustomerMergeError:
    logger.warning("gestor_customer_merge_denied error=%s", exc, exc_info=True)
    return CustomerMergeError("Não foi possível unificar os cadastros. Recarregue e tente de novo.")


def preview_merge(*, source_ref: str, target_ref: str):
    """``(source, target, MergePreview)`` — nada é gravado."""
    from shopman.guestman.contrib.merge.service import MergeService
    from shopman.guestman.exceptions import CustomerError
    from shopman.guestman.gates import GateError

    source, target = _pair(source_ref, target_ref)
    try:
        preview = MergeService.preview(source, target, evidence=_EVIDENCE)
    except (GateError, CustomerError) as exc:
        raise _translate(exc) from exc
    return source, target, preview


def merge_customers(*, source_ref: str, target_ref: str, actor: str):
    """Unifica: ``source`` sai (fica desativado), ``target`` fica com tudo."""
    from shopman.guestman.contrib.merge.service import MergeService
    from shopman.guestman.exceptions import CustomerError
    from shopman.guestman.gates import GateError

    try:
        with transaction.atomic():
            source, target = _pair(source_ref, target_ref, lock=True)
            result = MergeService.merge(source, target, evidence=_EVIDENCE, actor=actor or "gestor")
    except (GateError, CustomerError) as exc:
        raise _translate(exc) from exc

    logger.info(
        "gestor_customer_merged source=%s target=%s actor=%s audit=%s",
        result.source_ref,
        result.target_ref,
        actor,
        result.audit_id,
    )
    return result


def undo_merge(*, audit_id: str, actor: str) -> None:
    """Desfaz dentro da janela. A recusa diz qual dos três casos aconteceu."""
    from django.core.exceptions import ValidationError
    from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
    from shopman.guestman.contrib.merge.service import MergeService
    from shopman.guestman.exceptions import CustomerError

    try:
        audit = MergeAudit.objects.filter(pk=audit_id).first()
    except (ValueError, ValidationError):
        audit = None
    if audit is None:
        raise CustomerNotFound("Esta unificação não está mais no sistema. Recarregue a lista.")
    if audit.status != MergeStatus.COMPLETED:
        who = f" por {audit.reverted_by}" if audit.reverted_by else ""
        raise CustomerMergeError(f"Esta unificação já foi desfeita{who}.")
    if not audit.can_undo:
        raise CustomerMergeError(
            f"O prazo de {MergeAudit.UNDO_WINDOW_HOURS} horas para desfazer terminou. "
            f"Daqui em diante a separação é manual: cadastre {audit.source_ref} de novo e mova o que for dele."
        )
    try:
        MergeService.undo(str(audit.pk), actor=actor or "gestor")
    except CustomerError as exc:
        logger.warning("gestor_customer_undo_denied audit=%s error=%s", audit.pk, exc, exc_info=True)
        raise CustomerMergeError(
            "Não foi possível desfazer: um dos dois cadastros mudou desde a unificação. "
            "Confira as fichas antes de tentar de novo."
        ) from exc
    logger.info("gestor_customer_merge_undone audit=%s actor=%s", audit.pk, actor)
