"""CSV da Base: prévia sem escrita, revisão dos alvos e aplicação atômica em lote."""

from __future__ import annotations

import copy
import csv
import io

from django.apps import apps
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.backstage.services import purchase_catalog as catalog
from shopman.backstage.services.purchase import PurchaseError, parse_qty_input
from shopman.shop.services.remote_mutations import mutation_fingerprint
from shopman.shop.services.sku_namespace import units_agree

SALT = "purchase.csv.v1"
HEADERS = {
    "materials": ("SKU", "Nome", "Unidade", "Validade (dias)", "Categoria", "Mínimo", "Arquivado"),
    "suppliers": (
        "Referência",
        "Razão social",
        "Nome fantasia",
        "Documento",
        "E-mail",
        "Telefone",
        "Prazo (dias)",
        "Condição de pagamento",
        "Arquivado",
    ),
}
FIELDS = {
    "materials": ("sku", "name", "unit", "shelf_life_days", "metadata", "is_active", "updated_at"),
    "suppliers": ("ref", "name", "trade_name", "document", "email", "phone", "metadata", "is_active", "updated_at"),
}


def _model(entity):
    if entity not in HEADERS:
        raise PurchaseError("Cadastro não encontrado.", code="csv_entity_invalid", status_code=404)
    return apps.get_model("buyman", "Material" if entity == "materials" else "Supplier")


def _parse(entity, text):
    if not isinstance(text, str) or not text.strip() or len(text) > 1_000_000:
        raise PurchaseError("Escolha um CSV com até 1 MB.", code="csv_invalid", field="csv")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";", strict=True)
    try:
        headers = reader.fieldnames or []
    except csv.Error as exc:
        raise PurchaseError("As aspas do cabeçalho não foram fechadas.", code="csv_invalid", field="csv") from exc
    if (
        len(set(headers)) != len(headers)
        or not headers
        or headers[0] != HEADERS[entity][0]
        or set(headers) - set(HEADERS[entity])
    ):
        raise PurchaseError(
            "Use o cabeçalho do arquivo exportado. O separador é ponto e vírgula.",
            code="csv_headers_invalid",
            field="csv",
        )
    try:
        rows = [(index, row) for index, row in enumerate(reader, 2) if any(value for value in row.values())]
    except csv.Error as exc:
        raise PurchaseError("As aspas do CSV não foram fechadas.", code="csv_invalid", field="csv") from exc
    if not rows or len(rows) > 1000:
        raise PurchaseError("O CSV precisa ter de 1 a 1.000 registros.", code="csv_size_invalid", field="csv")
    return rows


def _prepare(entity, text, *, lock=False):
    Model = _model(entity)
    rows = _parse(entity, text)
    key = "sku" if entity == "materials" else "ref"

    def identity(row):
        raw = row.get(HEADERS[entity][0]) or ""
        return raw.strip().upper() if entity == "materials" else raw.strip().lower()

    refs = [identity(row) for _, row in rows]
    queryset = Model.objects.filter(**{f"{key}__in": refs}).order_by("pk")
    if lock:
        queryset = queryset.select_for_update()
    existing = {getattr(row, key): row for row in queryset}
    state = [[ref, existing[ref].updated_at.isoformat() if ref in existing else None] for ref in sorted(set(refs))]
    units = {}
    if entity == "materials":
        Product = apps.get_model("offerman", "Product")
        products = Product.objects.filter(sku__in=refs)
        if lock:
            products = products.select_for_update()
        units = dict(products.values_list("sku", "unit"))
    errors, changes, prepared, seen = [], [], [], set()
    for number, raw in rows:
        ref = identity(raw)
        original = existing.get(ref)
        row = copy.deepcopy(original) if original else Model(**{key: ref})
        try:
            if ref in seen:
                raise PurchaseError("Referência repetida no CSV.")
            seen.add(ref)
            if None in raw or any(value is None for value in raw.values()):
                raise PurchaseError("A quantidade de campos difere do cabeçalho.")
            if entity == "materials":
                row.sku = catalog._sku(ref)
                if original is None and "Unidade" not in raw:
                    raise PurchaseError("Informe a unidade do novo insumo.")
                if "Nome" in raw:
                    row.name = raw["Nome"].strip()
                if "Unidade" in raw:
                    row.unit = catalog._unit(raw["Unidade"])
                if "Validade (dias)" in raw:
                    row.shelf_life_days = catalog._shelf_life(raw["Validade (dias)"])
                if "Categoria" in raw:
                    row.metadata = catalog._material_metadata(
                        row.metadata,
                        category=catalog._text(raw["Categoria"], field="category", label="a categoria", max_length=80),
                    )
                if "Mínimo" in raw:
                    minimum = parse_qty_input(raw["Mínimo"] or "0")
                    if minimum is None:
                        raise PurchaseError("Informe um mínimo válido.")
                    meta, purchase = catalog._purchase_meta(row.metadata)
                    if minimum:
                        purchase["min_stock"] = str(minimum)
                    else:
                        purchase.pop("min_stock", None)
                    row.metadata = catalog._write_purchase_meta(meta, purchase)
                # A escrita em lote não dispara pre_save: o mesmo porteiro é
                # avaliado uma vez com o mapa do catálogo inteiro desta importação.
                if (
                    ref in units
                    and (original is None or not units_agree(original.unit, row.unit))
                    and not units_agree(units[ref], row.unit)
                ):
                    raise PurchaseError(f"O SKU {ref} é vendido em {units[ref]}. Use a mesma unidade na compra.")
            else:
                row.ref = catalog._ref(ref, required=True)
                for header, field in (
                    ("Razão social", "name"),
                    ("Nome fantasia", "trade_name"),
                    ("Documento", "document"),
                    ("E-mail", "email"),
                    ("Telefone", "phone"),
                ):
                    if header in raw:
                        setattr(row, field, raw[header].strip())
                row.metadata = catalog._supplier_metadata(
                    row.metadata,
                    lead_time_days=catalog._lead_time(raw["Prazo (dias)"]) if "Prazo (dias)" in raw else None,
                    payment_term=catalog._text(
                        raw["Condição de pagamento"],
                        field="paymentTerm",
                        label="a condição de pagamento",
                        max_length=80,
                    )
                    if "Condição de pagamento" in raw
                    else None,
                )
            if "Arquivado" in raw:
                row.is_active = not catalog._as_flag({"archived": raw["Arquivado"]}, "archived", default=False)
            row.full_clean(validate_unique=False, validate_constraints=False)
            prepared.append(row)
            changes.append({"ref": ref, "name": row.name, "action": "Atualizar" if original else "Criar"})
        except (PurchaseError, ValidationError) as exc:
            errors.append({"row": number, "detail": str(exc)})
    return (
        prepared,
        state,
        {
            "rows": len(rows),
            "totals": {
                "new": sum(row.pk is None for row in prepared),
                "update": sum(row.pk is not None for row in prepared),
            },
            "errors": errors,
            "changes": changes,
        },
    )


def preview_import(entity, data, *, user):
    _, state, preview = _prepare(entity, data.get("csv"))
    preview["base_revision"] = signing.dumps(
        {"entity": entity, "actor": user.pk, "csv": mutation_fingerprint(data.get("csv")), "state": state},
        salt=SALT,
        compress=True,
    )
    return {"preview": preview}


@transaction.atomic
def apply_import(entity, data, *, user):
    try:
        receipt = signing.loads(data.get("base_revision", ""), salt=SALT, max_age=1800)
    except (signing.BadSignature, TypeError):
        raise PurchaseError(
            "Refaça a prévia antes de importar.", code="csv_revision_required", status_code=409
        ) from None
    rows, state, result = _prepare(entity, data.get("csv"), lock=True)
    if receipt != {"entity": entity, "actor": user.pk, "csv": mutation_fingerprint(data.get("csv")), "state": state}:
        raise PurchaseError(
            "Alguém mudou os cadastros. Refaça a prévia antes de importar.", code="csv_changed", status_code=409
        )
    if result["errors"]:
        return {"ok": False, "outcome": "not_applied", **result}
    Model = _model(entity)
    now = timezone.now()
    new, changed = [], []
    for row in rows:
        row.updated_at = now
        (new if row.pk is None else changed).append(row)
    try:
        with transaction.atomic():
            Model.objects.bulk_create(new)
            Model.objects.bulk_update(changed, [field for field in FIELDS[entity] if field not in {"sku", "ref"}])
    except IntegrityError:
        raise PurchaseError(
            "O cadastro mudou durante a importação. Refaça a prévia.", code="csv_changed", status_code=409
        ) from None
    new_ids = {row.pk for row in new}
    content_type = ContentType.objects.get_for_model(Model)
    LogEntry.objects.bulk_create(
        [
            LogEntry(
                user_id=user.pk,
                content_type_id=content_type.pk,
                object_id=str(row.pk),
                object_repr=str(row)[:200],
                action_flag=ADDITION if row.pk in new_ids else CHANGE,
                change_message="Importação CSV da Base",
            )
            for row in rows
        ]
    )
    return {"ok": True, "outcome": "applied", **result}


def export_table(entity):
    Model = _model(entity)
    result = []
    for row in Model.objects.order_by("sku" if entity == "materials" else "ref"):
        meta = (row.metadata or {}).get("purchase") or {}
        if entity == "materials":
            result.append(
                [
                    row.sku,
                    row.name,
                    row.unit,
                    "" if row.shelf_life_days is None else str(row.shelf_life_days),
                    meta.get("category", ""),
                    str(meta.get("min_stock", "0")).replace(".", ","),
                    "Não" if row.is_active else "Sim",
                ]
            )
        else:
            result.append(
                [
                    row.ref,
                    row.name,
                    row.trade_name,
                    row.document,
                    row.email,
                    row.phone,
                    str(meta.get("lead_time_days", 0)),
                    meta.get("payment_term", ""),
                    "Não" if row.is_active else "Sim",
                ]
            )
    return {"table": {"header": list(HEADERS[entity]), "rows": result}}
