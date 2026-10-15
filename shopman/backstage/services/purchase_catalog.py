"""Cadastro da Base do Compras: criar, editar e duplicar insumo e fornecedor.

O Compras já operava (receber, custo, mínimo, conversão, revenda); cadastrar o
insumo e o fornecedor ainda mandava o gestor ao Admin. Este módulo é a escrita
que faltava, no lugar que a casa já escolheu: um service de framework
(Backstage), que compõe os modelos do Buyman sem tocar no Core.

Três coisas que ele deliberadamente NÃO faz:

- não cria campo nem migração (Material, Supplier, SupplierContact e
  MaterialConversion já têm tudo);
- não valida por conta própria o que o modelo já valida: chama full_clean
  quando as constraints são do modelo, e deixa o diálogo de erro do Core
  virar a mensagem do operador;
- não copia na duplicação o que identifica a coisa (EAN do insumo, CNPJ do
  fornecedor, de-para de nota) nem o que é decisão operacional do original
  (mínimo declarado, pedido em aberto, custo e conversão).

Quem chama é a API shopman.backstage.api.purchase; ela traduz as respostas
no dialeto da casa e devolve a projeção inteira, como todas as ações do
Compras.
"""

from __future__ import annotations

import copy
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services.purchase import PurchaseError, _supplier_ref_from_name

logger = logging.getLogger(__name__)

MATERIAL_UNITS = ("un", "kg", "g", "l", "ml")
CONTACT_ROLES = ("sales", "finance", "quality", "general")
CONVERSION_KINDS = ("conventional", "approximate")

_MATERIAL_LABEL_MAX = 200
_SUPPLIER_NAME_MAX = 200
_SUPPLIER_TRADE_MAX = 120
_CONTACT_NAME_MAX = 200
_CONVERSION_LABEL_MAX = 60
_CATEGORY_MAX = 80

#: O que a cópia de um insumo NÃO herda. EAN identifica a embalagem (dois SKUs
#: com o mesmo código viram recusa na nota), o de-para de nota é daquele SKU, e
#: mínimo/pedido são decisão operacional do original.
_MATERIAL_COPY_BLOCKED_META = frozenset(
    {
        "eans",
        "min_stock",
        "minStock",
        "request_status",
        "requestStatus",
        "invoice_codes",
        "invoiceCodes",
        "opens_into",
    }
)
#: O que a cópia de um fornecedor NÃO herda: CNPJ fica no cadastro dela e o
#: de-para de nota/contagem de volumes é história daquele fornecedor.
_SUPPLIER_COPY_BLOCKED_META = frozenset(
    {
        "invoice_product_map",
        "receipt_volume_counts",
        "document_learned_from",
        "created_from",
        "last_delivery_at",
        "lastDeliveryAt",
    }
)


_TRUE_TOKENS = frozenset({"1", "true", "sim", "on", "yes"})
_FALSE_TOKENS = frozenset({"0", "false", "nao", "não", "off", "no"})


def _as_flag(data: Any, field: str, *, default: bool) -> bool:
    """Booleano estrito do campo, no dialeto do service (PurchaseError).

    Mesmo contrato do _as_flag de services/purchase.py: o booleano JSON passa, os
    tokens inequívocos passam, e qualquer outra coisa é recusa com o campo, nunca
    False calado. O nome não é _as_bool de propósito: esse é o parser canônico de
    shopman/backstage/parsing.py, e a camada de serviço tem o seu (ver
    test_input_parsing_gate.py).
    """
    if not isinstance(data, dict) or field not in data or data[field] is None:
        return default
    value = data[field]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    token = str(value).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise PurchaseError("Este campo aceita apenas sim ou não.", code=f"{field}_invalid", field=field)


def _text(raw: Any, *, field: str, label: str, required: bool = False, max_length: int = 0) -> str:
    value = "" if raw is None else str(raw).strip()
    if required and not value:
        raise PurchaseError(f"Informe {label}.", code=f"{field}_required", field=field)
    if max_length and len(value) > max_length:
        raise PurchaseError(
            f"{label.capitalize()} cabe em {max_length} caracteres.",
            code=f"{field}_too_long",
            field=field,
        )
    return value


def _ref(raw: Any, *, required: bool = False) -> str:
    value = _text(raw, field="ref", label="a referência", required=required, max_length=64)
    if value:
        value = value.lower()
    if value and not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise PurchaseError(
            "A referência usa letras sem acento, números, ponto, hífen ou sublinhado.",
            code="ref_invalid",
            field="ref",
        )
    return value


def _sku(raw: Any) -> str:
    value = _text(raw, field="sku", label="o SKU", required=True, max_length=64)
    if "/" in value:
        raise PurchaseError("O SKU não pode ter barra (/).", code="sku_invalid", field="sku")
    return value


def _unit(raw: Any) -> str:
    value = str(raw or "").strip()
    if value not in MATERIAL_UNITS:
        raise PurchaseError(
            "Escolha a unidade: un, kg, g, l ou ml.",
            code="unit_invalid",
            field="unit",
        )
    return value


def _shelf_life(raw: Any) -> int | None:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise PurchaseError(
            "A validade é um número de dias (vazio = não perecível).",
            code="shelf_life_invalid",
            field="shelfLifeDays",
        ) from None
    if not value.is_finite() or value != value.to_integral_value() or value < 0 or value > 36500:
        raise PurchaseError(
            "A validade precisa ser um número inteiro entre 0 e 36.500 dias.",
            code="shelf_life_invalid",
            field="shelfLifeDays",
        )
    return int(value)


def _factor(raw: Any) -> Decimal:
    text = "" if raw is None else str(raw).strip().replace(",", ".")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise PurchaseError(
            "O fator precisa ser um número maior que zero.",
            code="conversion_factor_invalid",
            field="factor",
        ) from None
    if not value.is_finite() or value <= 0:
        raise PurchaseError(
            "O fator precisa ser maior que zero: quanto vale UM item de compra na unidade-base.",
            code="conversion_factor_invalid",
            field="factor",
        )
    return value


def _conversion_kind(raw: Any) -> str:
    value = str(raw or "").strip() or "conventional"
    if value not in CONVERSION_KINDS:
        raise PurchaseError("Tipo de conversão inválido.", code="conversion_kind_invalid", field="kind")
    return value


def _purchase_meta(metadata: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = copy.deepcopy(dict(metadata or {}))
    nested = meta.get("purchase")
    purchase = dict(nested) if isinstance(nested, dict) else {}
    return meta, purchase


def _write_purchase_meta(meta: dict[str, Any], purchase: dict[str, Any]) -> dict[str, Any]:
    if purchase:
        meta["purchase"] = purchase
    else:
        meta.pop("purchase", None)
    return meta


def _material_metadata(metadata: Any, *, category: str | None) -> dict[str, Any]:
    meta, purchase = _purchase_meta(metadata)
    if category is not None:
        if category:
            purchase["category"] = category
        else:
            purchase.pop("category", None)
    return _write_purchase_meta(meta, purchase)


def _supplier_metadata(metadata: Any, *, lead_time_days: int | None, payment_term: str | None) -> dict[str, Any]:
    meta, purchase = _purchase_meta(metadata)
    if lead_time_days is not None:
        if lead_time_days > 0:
            purchase["lead_time_days"] = lead_time_days
        else:
            purchase.pop("lead_time_days", None)
    if payment_term is not None:
        if payment_term:
            purchase["payment_term"] = payment_term
        else:
            purchase.pop("payment_term", None)
    return _write_purchase_meta(meta, purchase)


def _first_validation_message(exc: ValidationError) -> str:
    messages = getattr(exc, "message_dict", None) or {}
    if messages:
        return "; ".join(message for texts in messages.values() for message in texts)
    return "; ".join(exc.messages)


def _material_field(exc: ValidationError) -> str:
    messages = getattr(exc, "message_dict", None) or {}
    if "sku" in messages:
        return "sku"
    if "unit" in messages:
        return "unit"
    return "name"


def _supplier_field(exc: ValidationError) -> str:
    messages = getattr(exc, "message_dict", None) or {}
    if "ref" in messages:
        return "ref"
    return "name"


def _assert_revision(row, data: dict[str, Any], *, noun: str) -> None:
    expected = str(data.get("expectedRevision") or "").strip()
    current = row.updated_at.isoformat() if row.updated_at else ""
    if expected and expected != current:
        raise PurchaseError(
            f"{noun.capitalize()} mudou desde que você abriu o cadastro. Atualize e confira antes de salvar.",
            code="catalog_changed",
            field="expectedRevision",
            status_code=409,
        )


# ── Insumo ───────────────────────────────────────────────────────────────────


@transaction.atomic
def create_material(data: dict[str, Any], *, user=None) -> tuple[dict[str, Any], str]:
    """Cria o insumo do zero. SKU e nome são o mínimo; o resto tem default."""
    Material = apps.get_model("buyman", "Material")
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos do insumo.", code="material_invalid")

    sku = _sku(data.get("sku"))
    name = _text(data.get("name"), field="name", label="o nome", required=True, max_length=_MATERIAL_LABEL_MAX)
    unit = _unit(data.get("unit"))
    if Material.objects.filter(sku__iexact=sku).exists():
        raise PurchaseError(
            f"Já existe um insumo com o SKU {sku}. Edite o existente em vez de criar outro.",
            code="material_sku_exists",
            field="sku",
        )
    category = _text(data.get("category"), field="category", label="a categoria", max_length=_CATEGORY_MAX)
    material = Material(
        sku=sku,
        name=name,
        unit=unit,
        shelf_life_days=_shelf_life(data.get("shelfLifeDays")),
        is_active=_as_flag(data, "isActive", default=True),
        metadata=_material_metadata({}, category=category),
    )
    try:
        material.full_clean()
        material.save()
    except ValidationError as exc:
        raise PurchaseError(_first_validation_message(exc), code="material_refused", field=_material_field(exc)) from exc
    except IntegrityError as exc:
        raise PurchaseError(
            f"Já existe um insumo com o SKU {sku}. Edite o existente em vez de criar outro.",
            code="material_sku_exists",
            field="sku",
        ) from exc

    logger.info("purchase.material_created sku=%s user=%s", material.sku, getattr(user, "username", "") or "anon")
    return build_purchase(), material.sku


@transaction.atomic
def update_material(material_sku: str, data: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Edita o cadastro do insumo. O SKU não muda por aqui (renome é do Admin)."""
    Material = apps.get_model("buyman", "Material")
    material = Material.objects.select_for_update().filter(sku=material_sku).first()
    if material is None:
        raise PurchaseError("Insumo não encontrado.", code="material_not_found", field="sku", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos do insumo.", code="material_invalid")
    _assert_revision(material, data, noun="o insumo")

    if "name" in data:
        material.name = _text(data.get("name"), field="name", label="o nome", required=True, max_length=_MATERIAL_LABEL_MAX)
    if "unit" in data:
        material.unit = _unit(data.get("unit"))
    if "shelfLifeDays" in data:
        material.shelf_life_days = _shelf_life(data.get("shelfLifeDays"))
    if "isActive" in data:
        material.is_active = _as_flag(data, "isActive", default=material.is_active)
    if "category" in data:
        category = _text(data.get("category"), field="category", label="a categoria", max_length=_CATEGORY_MAX)
        material.metadata = _material_metadata(material.metadata, category=category)

    try:
        material.full_clean()
        material.save()
    except ValidationError as exc:
        raise PurchaseError(_first_validation_message(exc), code="material_refused", field=_material_field(exc)) from exc

    logger.info("purchase.material_updated sku=%s user=%s", material.sku, getattr(user, "username", "") or "anon")
    return build_purchase()


@transaction.atomic
def duplicate_material(material_sku: str, data: dict[str, Any], *, user=None) -> tuple[dict[str, Any], str]:
    """Duplica o conteúdo copiável do insumo num SKU novo.

    A cópia traz nome, unidade, validade e categoria. Não traz EAN, mínimo
    declarado, pedido em aberto, custo nem conversão: esses são história ou
    decisão do original, e o novo SKU começa limpo.
    """
    Material = apps.get_model("buyman", "Material")
    source = Material.objects.select_for_update().filter(sku=material_sku).first()
    if source is None:
        raise PurchaseError("Insumo não encontrado.", code="material_not_found", field="sku", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos da cópia.", code="material_invalid")
    _assert_revision(source, data, noun="o insumo original")

    new_sku = _sku(data.get("sku"))
    if new_sku.casefold() == source.sku.casefold():
        raise PurchaseError(
            "O SKU da cópia precisa ser diferente do original.",
            code="material_sku_same",
            field="sku",
        )
    if Material.objects.filter(sku__iexact=new_sku).exists():
        raise PurchaseError(
            f"Já existe um insumo com o SKU {new_sku}.",
            code="material_sku_exists",
            field="sku",
        )
    suffix = " (cópia)"
    fallback = f"{source.name[: _MATERIAL_LABEL_MAX - len(suffix)]}{suffix}"
    name = _text(data.get("name"), field="name", label="o nome", max_length=_MATERIAL_LABEL_MAX) or fallback

    meta, purchase = _purchase_meta(source.metadata)
    for key in _MATERIAL_COPY_BLOCKED_META:
        meta.pop(key, None)
        purchase.pop(key, None)
    meta = _write_purchase_meta(meta, purchase)

    copy_row = Material(
        sku=new_sku,
        name=name,
        unit=source.unit,
        shelf_life_days=source.shelf_life_days,
        is_active=True,
        metadata=meta,
    )
    try:
        copy_row.full_clean()
        copy_row.save()
    except ValidationError as exc:
        raise PurchaseError(_first_validation_message(exc), code="material_refused", field=_material_field(exc)) from exc
    except IntegrityError as exc:
        raise PurchaseError(
            f"Já existe um insumo com o SKU {new_sku}.",
            code="material_sku_exists",
            field="sku",
        ) from exc

    logger.info(
        "purchase.material_duplicated source=%s sku=%s user=%s",
        source.sku,
        copy_row.sku,
        getattr(user, "username", "") or "anon",
    )
    return build_purchase(), copy_row.sku


# ── Fornecedor ───────────────────────────────────────────────────────────────


def _unique_supplier_ref(base: str) -> str:
    Supplier = apps.get_model("buyman", "Supplier")
    ref = base
    suffix = 2
    while Supplier.objects.filter(ref=ref).exists():
        ref = f"{base}-{suffix}"
        suffix += 1
    return ref


def _lead_time(raw: Any) -> int:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return 0
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise PurchaseError(
            "O prazo de entrega é um número de dias.",
            code="lead_time_invalid",
            field="leadTimeDays",
        ) from None
    if not value.is_finite() or value != value.to_integral_value() or value < 0 or value > 3650:
        raise PurchaseError(
            "O prazo de entrega precisa ser um número inteiro entre 0 e 3.650 dias.",
            code="lead_time_invalid",
            field="leadTimeDays",
        )
    return int(value)


@transaction.atomic
def create_supplier(data: dict[str, Any], *, user=None) -> tuple[dict[str, Any], str]:
    """Cria o fornecedor. Sem ref informada, ela nasce do nome (o padrão da casa)."""
    Supplier = apps.get_model("buyman", "Supplier")
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos do fornecedor.", code="supplier_invalid")

    name = _text(data.get("name"), field="name", label="a razão social", required=True, max_length=_SUPPLIER_NAME_MAX)
    ref = _ref(data.get("ref"))
    if not ref:
        ref = _unique_supplier_ref(_supplier_ref_from_name(name))
        if not ref:
            raise PurchaseError(
                "Informe a referência do fornecedor: o nome não gera uma sozinho.",
                code="ref_required",
                field="ref",
            )
    elif Supplier.objects.filter(ref=ref).exists():
        raise PurchaseError(
            f"Já existe um fornecedor com a referência {ref}.",
            code="supplier_ref_exists",
            field="ref",
        )

    supplier = Supplier(
        ref=ref,
        name=name,
        trade_name=_text(data.get("tradeName"), field="tradeName", label="o nome fantasia", max_length=_SUPPLIER_TRADE_MAX),
        document=_text(data.get("document"), field="document", label="o documento", max_length=32),
        email=_text(data.get("email"), field="email", label="o e-mail", max_length=254),
        phone=_text(data.get("phone"), field="phone", label="o telefone", max_length=32),
        is_active=_as_flag(data, "isActive", default=True),
        metadata=_supplier_metadata(
            {},
            lead_time_days=_lead_time(data.get("leadTimeDays")),
            payment_term=_text(data.get("paymentTerm"), field="paymentTerm", label="a condição de pagamento", max_length=80),
        ),
    )
    try:
        supplier.full_clean()
        supplier.save()
    except ValidationError as exc:
        raise PurchaseError(_first_validation_message(exc), code="supplier_refused", field=_supplier_field(exc)) from exc
    except IntegrityError as exc:
        raise PurchaseError(
            f"Já existe um fornecedor com a referência {ref}.",
            code="supplier_ref_exists",
            field="ref",
        ) from exc

    logger.info("purchase.supplier_created ref=%s user=%s", supplier.ref, getattr(user, "username", "") or "anon")
    return build_purchase(), supplier.ref


@transaction.atomic
def update_supplier(ref: str, data: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Edita o fornecedor. A referência não muda por aqui (renome é do Admin)."""
    Supplier = apps.get_model("buyman", "Supplier")
    supplier = Supplier.objects.select_for_update().filter(ref=ref).first()
    if supplier is None:
        raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="ref", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos do fornecedor.", code="supplier_invalid")
    _assert_revision(supplier, data, noun="o fornecedor")

    if "name" in data:
        supplier.name = _text(data.get("name"), field="name", label="a razão social", required=True, max_length=_SUPPLIER_NAME_MAX)
    if "tradeName" in data:
        supplier.trade_name = _text(data.get("tradeName"), field="tradeName", label="o nome fantasia", max_length=_SUPPLIER_TRADE_MAX)
    if "document" in data:
        supplier.document = _text(data.get("document"), field="document", label="o documento", max_length=32)
    if "email" in data:
        supplier.email = _text(data.get("email"), field="email", label="o e-mail", max_length=254)
    if "phone" in data:
        supplier.phone = _text(data.get("phone"), field="phone", label="o telefone", max_length=32)
    if "isActive" in data:
        supplier.is_active = _as_flag(data, "isActive", default=supplier.is_active)
    if "leadTimeDays" in data or "paymentTerm" in data:
        lead_time_days = _lead_time(data.get("leadTimeDays")) if "leadTimeDays" in data else None
        payment_term = (
            _text(data.get("paymentTerm"), field="paymentTerm", label="a condição de pagamento", max_length=80)
            if "paymentTerm" in data
            else None
        )
        supplier.metadata = _supplier_metadata(
            supplier.metadata, lead_time_days=lead_time_days, payment_term=payment_term,
        )

    try:
        supplier.full_clean()
        supplier.save()
    except ValidationError as exc:
        raise PurchaseError(_first_validation_message(exc), code="supplier_refused", field=_supplier_field(exc)) from exc

    logger.info("purchase.supplier_updated ref=%s user=%s", supplier.ref, getattr(user, "username", "") or "anon")
    return build_purchase()


@transaction.atomic
def duplicate_supplier(ref: str, data: dict[str, Any], *, user=None) -> tuple[dict[str, Any], str]:
    """Duplica o fornecedor, com os contatos e os termos comerciais.

    A cópia NÃO herda CNPJ nem o de-para de nota: são identidade e história do
    original. Nome, referência e documento vêm do formulário.
    """
    Supplier = apps.get_model("buyman", "Supplier")
    SupplierContact = apps.get_model("buyman", "SupplierContact")
    source = Supplier.objects.select_for_update().filter(ref=ref).first()
    if source is None:
        raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="ref", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos da cópia.", code="supplier_invalid")
    _assert_revision(source, data, noun="o fornecedor original")

    new_ref = _ref(data.get("ref"), required=True)
    if new_ref == source.ref:
        raise PurchaseError(
            "A referência da cópia precisa ser diferente da original.",
            code="supplier_ref_same",
            field="ref",
        )
    if Supplier.objects.filter(ref=new_ref).exists():
        raise PurchaseError(
            f"Já existe um fornecedor com a referência {new_ref}.",
            code="supplier_ref_exists",
            field="ref",
        )
    fallback = f"{source.name[: _SUPPLIER_NAME_MAX - 9]} (cópia)"
    name = _text(data.get("name"), field="name", label="a razão social", max_length=_SUPPLIER_NAME_MAX) or fallback

    meta, purchase = _purchase_meta(source.metadata)
    for key in _SUPPLIER_COPY_BLOCKED_META:
        meta.pop(key, None)
        purchase.pop(key, None)
    meta = _write_purchase_meta(meta, purchase)

    copy_row = Supplier(ref=new_ref, name=name, is_active=True, metadata=meta)
    try:
        copy_row.full_clean()
        copy_row.save()
    except ValidationError as exc:
        raise PurchaseError(_first_validation_message(exc), code="supplier_refused", field=_supplier_field(exc)) from exc
    except IntegrityError as exc:
        raise PurchaseError(
            f"Já existe um fornecedor com a referência {new_ref}.",
            code="supplier_ref_exists",
            field="ref",
        ) from exc

    for contact in source.contacts.all().order_by("pk"):
        SupplierContact.objects.create(
            supplier=copy_row,
            name=contact.name,
            role=contact.role,
            email=contact.email,
            phone=contact.phone,
            is_primary=False,
            is_active=contact.is_active,
            notes=contact.notes,
        )

    logger.info(
        "purchase.supplier_duplicated source=%s ref=%s user=%s",
        source.ref,
        copy_row.ref,
        getattr(user, "username", "") or "anon",
    )
    return build_purchase(), copy_row.ref


# ── Contato do fornecedor ────────────────────────────────────────────────────


def _contact_payload(contact, data: dict[str, Any]) -> None:
    if "name" in data:
        contact.name = str(data.get("name") or "").strip()
    if "role" in data:
        role = str(data.get("role") or "").strip() or "general"
        if role not in CONTACT_ROLES:
            raise PurchaseError("Papel do contato inválido.", code="contact_role_invalid", field="role")
        contact.role = role
    if "email" in data:
        contact.email = str(data.get("email") or "").strip()
    if "phone" in data:
        contact.phone = str(data.get("phone") or "").strip()
    if "notes" in data:
        contact.notes = str(data.get("notes") or "").strip()
    if "isPrimary" in data:
        contact.is_primary = _as_flag(data, "isPrimary", default=contact.is_primary)
    if "isActive" in data:
        contact.is_active = _as_flag(data, "isActive", default=contact.is_active)


def _contact_error(exc: Exception) -> PurchaseError:
    message = _first_validation_message(exc) if isinstance(exc, ValidationError) else str(exc)
    messages = getattr(exc, "message_dict", None) or {}
    field_map = {"is_primary": "isPrimary", "is_active": "isActive"}
    raw_field = next(iter(messages), "name")
    field = field_map.get(raw_field, raw_field)
    return PurchaseError(message, code="contact_refused", field=field)


def create_supplier_contact(ref: str, data: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Cria a pessoa do fornecedor. Sem e-mail nem telefone, ela não é rota."""
    Supplier = apps.get_model("buyman", "Supplier")
    SupplierContact = apps.get_model("buyman", "SupplierContact")
    supplier = Supplier.objects.filter(ref=ref).first()
    if supplier is None:
        raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="ref", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos do contato.", code="contact_invalid")

    contact = SupplierContact(supplier=supplier)
    _contact_payload(contact, data)
    if not contact.name:
        raise PurchaseError("Informe o nome do contato.", code="contact_name_required", field="name")
    if not contact.email and not contact.phone:
        raise PurchaseError(
            "Informe e-mail ou telefone do contato: sem isso ele é um nome que o sistema não alcança.",
            code="contact_reach_required",
            field="email",
        )
    try:
        # O save do modelo promove o contato e demove o principal anterior na
        # mesma transação. Validar a constraint única antes disso recusaria o
        # gesto que o próprio modelo foi desenhado para resolver.
        contact.full_clean(validate_constraints=False)
        contact.save()
    except (ValidationError, IntegrityError) as exc:
        raise _contact_error(exc) from exc

    logger.info(
        "purchase.contact_created supplier=%s contact=%s user=%s",
        supplier.ref,
        contact.pk,
        getattr(user, "username", "") or "anon",
    )
    return build_purchase()


def update_supplier_contact(contact_id: int, data: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Edita a pessoa do fornecedor (inclusive aposentá-la com isActive)."""
    SupplierContact = apps.get_model("buyman", "SupplierContact")
    contact = SupplierContact.objects.select_related("supplier").filter(pk=contact_id).first()
    if contact is None:
        raise PurchaseError("Contato não encontrado.", code="contact_not_found", field="id", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos do contato.", code="contact_invalid")

    _contact_payload(contact, data)
    if not contact.name:
        raise PurchaseError("Informe o nome do contato.", code="contact_name_required", field="name")
    if not contact.email and not contact.phone:
        raise PurchaseError(
            "Informe e-mail ou telefone do contato: sem isso ele é um nome que o sistema não alcança.",
            code="contact_reach_required",
            field="email",
        )
    try:
        contact.full_clean(validate_constraints=False)
        contact.save()
    except (ValidationError, IntegrityError) as exc:
        raise _contact_error(exc) from exc

    logger.info("purchase.contact_updated contact=%s user=%s", contact.pk, getattr(user, "username", "") or "anon")
    return build_purchase()


# ── Conversão ────────────────────────────────────────────────────────────────


def update_conversion(conversion_id: int, data: dict[str, Any], *, user=None) -> dict[str, Any]:
    """Edita a conversão declarada. Corrigir o fator reprecifica tudo sozinho."""
    MaterialConversion = apps.get_model("buyman", "MaterialConversion")
    Supplier = apps.get_model("buyman", "Supplier")
    conversion = MaterialConversion.objects.select_related("material", "supplier").filter(pk=conversion_id).first()
    if conversion is None:
        raise PurchaseError("Conversão não encontrada.", code="conversion_not_found", field="id", status_code=404)
    if not isinstance(data, dict):
        raise PurchaseError("Informe os campos da conversão.", code="conversion_invalid")

    if "label" in data:
        conversion.label = _text(data.get("label"), field="label", label="o rótulo", required=True, max_length=_CONVERSION_LABEL_MAX)
    if "factor" in data:
        conversion.to_base_factor = _factor(data.get("factor"))
    if "kind" in data:
        conversion.kind = _conversion_kind(data.get("kind"))
    if "supplierRef" in data:
        supplier_ref = str(data.get("supplierRef") or "").strip()
        if supplier_ref:
            supplier = Supplier.objects.filter(ref=supplier_ref).first()
            if supplier is None:
                raise PurchaseError("Fornecedor não encontrado.", code="supplier_not_found", field="supplierRef")
            conversion.supplier = supplier
        else:
            conversion.supplier = None
    if "isActive" in data:
        conversion.is_active = _as_flag(data, "isActive", default=conversion.is_active)

    try:
        conversion.full_clean()
        conversion.save()
    except (ValidationError, IntegrityError) as exc:
        messages = getattr(exc, "message_dict", None) or {}
        field = "factor" if "to_base_factor" in messages else "label"
        raise PurchaseError(
            _first_validation_message(exc), code="conversion_validation_failed", field=field,
        ) from exc

    logger.info("purchase.conversion_updated pk=%s user=%s", conversion.pk, getattr(user, "username", "") or "anon")
    unit = getattr(conversion.material, "unit", "")
    approximate = " (aproximada)" if conversion.is_approximate else ""
    factor = format(Decimal(conversion.to_base_factor).normalize(), "f")
    message = f"Conversão salva: 1 {conversion.label} = {factor} {unit}{approximate}."
    return build_purchase(), message


__all__ = [
    "create_material",
    "update_material",
    "duplicate_material",
    "create_supplier",
    "update_supplier",
    "duplicate_supplier",
    "create_supplier_contact",
    "update_supplier_contact",
    "update_conversion",
]
