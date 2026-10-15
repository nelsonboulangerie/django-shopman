"""Orquestração fina do inventário de receitas sobre o Craftsman.

O que mora aqui é o que a porta HTTP precisa e o Craftsman não tem por que
saber: ler o corpo da requisição, gerar o ``ref`` a partir do nome, copiar uma
versão de origem ao criar outra, e traduzir ``RecipeBookError`` para
``RecipeBookServiceError`` (mensagem, campo e código, já no dialeto da porta).
Nenhuma regra do inventário é repetida: validar fórmula, numerar versão,
publicar na ficha e comparar versões continuam em
``shopman.craftsman.services.recipe_book``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from shopman.craftsman.exceptions import RecipeBookError
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeVersion
from shopman.craftsman.recipe_steps import normalize_steps
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.services import recipe_external_references as external_references
from shopman.backstage.services.exceptions import (
    RecipeBookServiceError,
    RecipeEntryNotFound,
    RecipeVersionNotFound,
)
from shopman.backstage.services.recipe_capture import CapturedRecipe, read_recipe

logger = logging.getLogger(__name__)

#: ``source.kind`` que uma versão pode declarar (§2).
SOURCE_KINDS = ("manual", "note", "photo", "ficha", "import")
#: O que o corpo de ``POST versions/`` e ``PATCH versions/<n>/`` pode trazer.
_VERSION_FIELDS = ("formula", "yield_quantity", "yield_unit", "steps", "notes", "label")
_MAX_REF_LENGTH = RecipeEntry._meta.get_field("ref").max_length or 50
#: Recusas do Craftsman que não nomeiam campo mas têm um dono na tela.
_FIELD_BY_CODE = {"ENTRY_WITHOUT_SKU": "output_sku", "ANCHOR_EMPTY": "anchor"}


# ── Tradução de erro ─────────────────────────────────────────────────────────


@contextmanager
def translating_errors():
    """``RecipeBookError`` do Craftsman e ``ValidationError`` do modelo viram ``RecipeBookServiceError``."""
    try:
        yield
    except RecipeBookError as exc:
        field = str(exc.data.get("field") or "") or _FIELD_BY_CODE.get(exc.code, "")
        raise RecipeBookServiceError(exc.message, field=field, code=exc.code) from exc
    except ValidationError as exc:
        field, detail = _first_validation_message(exc)
        raise RecipeBookServiceError(detail, field=field, code="FORMULA_INVALID") from exc


def _first_validation_message(exc: ValidationError) -> tuple[str, str]:
    if hasattr(exc, "message_dict"):
        for field, messages in exc.message_dict.items():
            for message in messages:
                return ("" if field == "__all__" else field), str(message)
    messages = list(getattr(exc, "messages", []) or [])
    return "", str(messages[0]) if messages else "Dados inválidos."


def _fail(detail: str, *, field: str = "", code: str = "INVALID_PAYLOAD") -> RecipeBookServiceError:
    return RecipeBookServiceError(detail, field=field, code=code)


# ── Leitura do corpo ─────────────────────────────────────────────────────────


def _text(data: dict, key: str, *, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise _fail(f"O campo {key} precisa ser texto.", field=key)
    return value.strip()


def _steps(value: Any, *, field: str = "steps") -> list[dict]:
    """Etapas na forma única (``shopman.craftsman.recipe_steps``).

    Aceita objeto ``{name, instructions?, target_seconds?, temperature_celsius?, note?}`` ou texto puro
    (vira ``{"name": ...}``); um texto só é lido uma etapa por linha. Linha
    vazia é sobra de textarea e sai; objeto inválido é recusado apontando a etapa.
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        raise _fail("As etapas precisam ser uma lista.", field=field)
    value = [step for step in value if not (isinstance(step, str) and not step.strip())]
    try:
        return normalize_steps(value)
    except ValidationError as exc:
        _, detail = _first_validation_message(exc)
        raise _fail(detail, field=field) from exc


def _kind(value: Any, *, allow_empty: bool) -> str:
    """Tipo da receita. Vazio vira ``other`` ao criar; ao editar, vazio é pergunta sem resposta."""
    kind = str(value or "").strip()
    if not kind:
        if allow_empty:
            return RecipeEntry.Kind.OTHER
        raise _fail("Informe o tipo da receita.", field="kind")
    if kind not in RecipeEntry.Kind.values:
        raise _fail(
            f"Tipo de receita desconhecido; use um de: {', '.join(RecipeEntry.Kind.values)}.", field="kind",
        )
    return kind


def _source(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _fail("A origem precisa ser um objeto com kind.", field="source")
    kind = str(value.get("kind") or "manual").strip()
    if kind not in SOURCE_KINDS:
        raise _fail(f"Origem desconhecida; use uma de: {', '.join(SOURCE_KINDS)}.", field="source.kind")
    return {**value, "kind": kind}


def _origin(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _fail("A receita como foi informada precisa ser um objeto.", field="origin")
    return dict(value)


def _formula(value: Any, *, required: bool) -> dict | None:
    if value is None:
        if required:
            raise _fail("Informe a fórmula da versão.", field="formula")
        return None
    if not isinstance(value, dict):
        raise _fail("A fórmula precisa ser um objeto.", field="formula")
    return value


# ── Ref ──────────────────────────────────────────────────────────────────────


def unique_ref(name: str, *, wanted: str = "") -> str:
    """``slugify`` do nome (ou do ref pedido) com sufixo numérico quando já existe."""
    base = slugify(wanted or name)[:_MAX_REF_LENGTH].strip("-")
    if not base:
        raise _fail("Não foi possível gerar um identificador a partir do nome.", field="ref" if wanted else "name")
    candidate = base
    suffix = 2
    while RecipeEntry.objects.filter(ref=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: _MAX_REF_LENGTH - len(tail)]}{tail}"
        suffix += 1
    return candidate


# ── Entry ────────────────────────────────────────────────────────────────────


def create_entry_from_payload(data: dict, *, actor: str = "") -> tuple[RecipeEntry, RecipeVersion | None]:
    """``POST recipes/``: a entry e, quando ``version`` veio junto, o primeiro rascunho.

    Tudo ou nada: um rascunho inválido não deixa uma entry órfã para trás.
    """
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
    name = _text(data, "name")
    if not name:
        raise _fail("Informe o nome da receita.", field="name")
    kind = _kind(data.get("kind"), allow_empty=True)
    output_sku = _text(data, "output_sku")
    notes = _text(data, "notes")
    version_data = data.get("version")
    if version_data is not None and not isinstance(version_data, dict):
        raise _fail("A versão precisa ser um objeto.", field="version")

    try:
        with transaction.atomic(), translating_errors():
            entry = craftsman.create_entry(
                ref=unique_ref(name, wanted=_text(data, "ref")),
                name=name,
                kind=kind,
                output_sku=output_sku,
                notes=notes,
            )
            version = None
            if version_data is not None:
                version = create_version_from_payload(entry, version_data, actor=actor)
    except IntegrityError as exc:
        raise _fail("Já existe uma receita com essa referência. Tente novamente.", field="ref") from exc
    return entry, version


def patch_entry(entry: RecipeEntry, data: dict) -> RecipeEntry:
    """``PATCH recipes/<ref>/``: nome, tipo, SKU, observações, arquivamento e referências externas.

    ``external_references`` substitui a lista INTEIRA (a tela manda a lista
    com o item a mais ou a menos); a forma é de ``recipe_external_references``.
    """
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
    with transaction.atomic():
        entry = (
            RecipeEntry.objects.select_for_update(of=("self",))
            .select_related("current_version")
            .get(pk=entry.pk)
        )
        _assert_revision(entry, data)
        return _patch_entry_locked(entry, data)


def _patch_entry_locked(entry: RecipeEntry, data: dict) -> RecipeEntry:
    if "name" in data:
        name = _text(data, "name")
        if not name:
            raise _fail("Informe o nome da receita.", field="name")
        entry.name = name
    if "kind" in data:
        entry.kind = _kind(data.get("kind"), allow_empty=False)
    if "output_sku" in data:
        entry.output_sku = _text(data, "output_sku")
    if "notes" in data:
        entry.notes = _text(data, "notes")
    if "is_archived" in data:
        value = data.get("is_archived")
        if not isinstance(value, bool):
            raise _fail("Arquivar aceita apenas sim ou não.", field="is_archived")
        entry.is_archived = value
    if external_references.FIELD in data:
        references = external_references.validate(data.get(external_references.FIELD))
        meta = dict(entry.meta or {})
        if references:
            meta[external_references.META_KEY] = references
        else:
            meta.pop(external_references.META_KEY, None)
        entry.meta = meta
    with translating_errors():
        entry.full_clean()
        entry.save()
    return entry


def _assert_revision(row, data: dict, *, field: str = "expectedRevision") -> None:
    expected = str(data.get(field) or "").strip()
    if expected and expected != row.updated_at.isoformat():
        raise _fail(
            "A receita mudou desde que você abriu. Atualize e confira antes de salvar.",
            field=field,
            code="RECIPE_CHANGED",
        )


def version_revision(version: RecipeVersion) -> str:
    """Revisão estável do rascunho sem exigir uma coluna nova no Core."""
    payload = {
        "status": version.status,
        "label": version.label or "",
        "yield_quantity": str(version.yield_quantity),
        "yield_unit": version.yield_unit,
        "formula": version.formula or {},
        "steps": version.steps or [],
        "notes": version.notes or "",
        "published_at": version.published_at.isoformat() if version.published_at else "",
        "meta": version.meta or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _assert_version_revision(version: RecipeVersion, data: dict, *, field: str = "expectedRevision") -> None:
    expected = str(data.get(field) or "").strip()
    if expected and expected != version_revision(version):
        raise _fail(
            "O rascunho mudou desde que você abriu. Atualize e confira antes de salvar.",
            field=field,
            code="RECIPE_CHANGED",
        )


def _integer_setting(value: Any, *, field: str, minimum: int, maximum: int) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise _fail(f"{field} precisa ser um número inteiro.", field=field)
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise _fail(f"{field} precisa ser um número inteiro.", field=field) from None
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or not minimum <= parsed <= maximum:
        raise _fail(f"{field} precisa estar entre {minimum} e {maximum}.", field=field)
    return int(parsed)


def _decimal_setting(value: Any, *, field: str) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise _fail(f"{field} precisa ser um número maior que zero.", field=field)
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise _fail(f"{field} precisa ser um número maior que zero.", field=field) from None
    if not parsed.is_finite() or parsed <= 0 or parsed > Decimal("999999999"):
        raise _fail(f"{field} precisa ser um número maior que zero.", field=field)
    return format(parsed.normalize(), "f")


def _boolean_setting(data: dict, field: str, *, default: bool) -> bool:
    value = data.get(field, default)
    if not isinstance(value, bool):
        raise _fail(f"{field} aceita apenas sim ou não.", field=field)
    return value


@transaction.atomic
def update_execution(entry: RecipeEntry, data: dict, *, actor: str) -> Recipe:
    """Edita apenas a operação da ficha; fórmula e BOM continuam vindo da versão."""
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
    recipe = Recipe.objects.select_for_update().filter(ref=entry.ref, is_active=True).first()
    if recipe is None:
        raise RecipeEntryNotFound("Publique uma versão antes de configurar a ficha de execução.")
    _assert_revision(recipe, data)
    meta = dict(recipe.meta or {})

    if "maxStartedMinutes" in data:
        value = _integer_setting(data.get("maxStartedMinutes"), field="maxStartedMinutes", minimum=1, maximum=10080)
        if value is None:
            meta.pop("max_started_minutes", None)
        else:
            meta["max_started_minutes"] = value
    if "capacityPerDay" in data:
        value = _decimal_setting(data.get("capacityPerDay"), field="capacityPerDay")
        if value is None:
            meta.pop("capacity_per_day", None)
        else:
            meta["capacity_per_day"] = value
    if "requiresBatchTracking" in data:
        enabled = _boolean_setting(data, "requiresBatchTracking", default=False)
        if enabled:
            meta["requires_batch_tracking"] = True
        else:
            meta.pop("requires_batch_tracking", None)
    if "shelfLifeDays" in data:
        days = _integer_setting(data.get("shelfLifeDays"), field="shelfLifeDays", minimum=0, maximum=3650)
        if days is None:
            meta.pop("shelf_life_days", None)
        else:
            meta["shelf_life_days"] = days
    else:
        days = _integer_setting(meta.get("shelf_life_days"), field="shelfLifeDays", minimum=0, maximum=3650)

    if "shelfLifeReviewed" in data:
        reviewed = _boolean_setting(data, "shelfLifeReviewed", default=False)
        if reviewed:
            if days is None:
                raise _fail("Informe a validade antes de confirmar a revisão.", field="shelfLifeDays")
            already_reviewed = bool(
                _integer_setting(
                    meta.get("shelf_life_reviewed_days"),
                    field="shelfLifeDays",
                    minimum=0,
                    maximum=3650,
                ) == days
                and meta.get("shelf_life_reviewed_by")
                and meta.get("shelf_life_reviewed_at")
            )
            if not already_reviewed:
                meta.update({
                    "shelf_life_reviewed_days": days,
                    "shelf_life_reviewed_by": actor,
                    "shelf_life_reviewed_at": timezone.now().isoformat(),
                    "shelf_life_source": "manager_review",
                })
            meta.pop("shelf_life_review_required", None)
        else:
            for key in ("shelf_life_reviewed_days", "shelf_life_reviewed_by", "shelf_life_reviewed_at"):
                meta.pop(key, None)
    elif _integer_setting(
        meta.get("shelf_life_reviewed_days"),
        field="shelfLifeDays",
        minimum=0,
        maximum=3650,
    ) != days:
        for key in ("shelf_life_reviewed_days", "shelf_life_reviewed_by", "shelf_life_reviewed_at"):
            meta.pop(key, None)

    if "productionLifecycle" in data:
        from shopman.shop.production_lifecycle import production_lifecycle_choices

        lifecycle = str(data.get("productionLifecycle") or "").strip()
        choices = production_lifecycle_choices()
        allowed = {str(value) for value, _label in choices}
        if lifecycle and lifecycle not in allowed:
            raise _fail("Escolha um ciclo de produção disponível.", field="productionLifecycle")
        default = str(choices[0][0]) if choices else ""
        if lifecycle and lifecycle != default:
            meta["production_lifecycle"] = lifecycle
        else:
            meta.pop("production_lifecycle", None)

    recipe.meta = meta
    with translating_errors():
        recipe.full_clean()
        recipe.save()
    return recipe


@transaction.atomic
def duplicate_entry(entry: RecipeEntry, data: dict, *, actor: str) -> tuple[RecipeEntry, RecipeVersion]:
    """Cria outra receita com um rascunho copiado; nunca clona uma ficha ativa."""
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
    entry = (
        RecipeEntry.objects.select_for_update(of=("self",))
        .select_related("current_version")
        .get(pk=entry.pk)
    )
    _assert_revision(entry, data)
    raw_number = data.get("fromVersion")
    if raw_number in (None, ""):
        source = entry.current_version or entry.versions.order_by("-number").first()
    else:
        number = _integer_setting(raw_number, field="fromVersion", minimum=1, maximum=999999)
        source = entry.versions.filter(number=number).first()
    if source is None:
        raise RecipeVersionNotFound(f"A receita '{entry.ref}' não tem versão para duplicar.")

    name = _text(data, "name")
    if not name:
        raise _fail("Informe o nome da cópia.", field="name")
    output_sku = _text(data, "outputSku").upper()
    if output_sku and output_sku.casefold() == entry.output_sku.casefold():
        raise _fail("A cópia precisa produzir outro SKU ou ficar sem SKU por enquanto.", field="outputSku")
    try:
        with transaction.atomic(), translating_errors():
            copied = craftsman.create_entry(
                ref=unique_ref(name, wanted=_text(data, "ref")),
                name=name,
                kind=entry.kind,
                output_sku=output_sku,
                notes=entry.notes or "",
            )
    except IntegrityError as exc:
        raise _fail("Já existe uma receita com essa referência. Tente novamente.", field="ref") from exc
    with translating_errors():
        version = craftsman.create_version(
            copied,
            formula=dict(source.formula or {}),
            yield_quantity=source.yield_quantity,
            yield_unit=source.yield_unit,
            origin=dict(source.origin or {}),
            source={"kind": "manual", "copied_from": source.version_ref},
            steps=list(source.steps or []),
            notes=source.notes or "",
            label=f"Cópia de {entry.name}",
            created_by=actor,
        )
    return copied, version


# ── Versão ───────────────────────────────────────────────────────────────────


def _version_fields_from(version: RecipeVersion) -> dict:
    return {
        "formula": dict(version.formula or {}),
        "yield_quantity": version.yield_quantity,
        "yield_unit": version.yield_unit,
        "steps": list(version.steps or []),
        "notes": version.notes or "",
        "label": "",
    }


@transaction.atomic
def create_version_from_payload(entry: RecipeEntry, data: dict, *, actor: str = "") -> RecipeVersion:
    """``POST recipes/<ref>/versions/``: um rascunho novo, do zero ou copiado de ``from_version``.

    Com ``from_version``, a versão de origem é a base e o corpo sobrescreve o
    que trouxer; sem a fórmula no corpo, a cópia é integral. Sem
    ``from_version``, fórmula, rendimento e unidade são obrigatórios.
    """
    if not isinstance(data, dict):
        raise _fail("A versão precisa ser um objeto.", field="version")
    entry = RecipeEntry.objects.select_for_update().get(pk=entry.pk)
    _assert_revision(entry, data)
    base: dict = {}
    source = _source(data.get("source"))
    from_version = data.get("from_version")
    if from_version not in (None, ""):
        if isinstance(from_version, bool) or not str(from_version).strip().isdigit():
            raise _fail("from_version precisa ser o número de uma versão.", field="from_version")
        origin_version = entry.versions.filter(number=int(from_version)).first()
        if origin_version is None:
            raise RecipeVersionNotFound(f"A receita '{entry.ref}' não tem a versão {from_version}.")
        base = _version_fields_from(origin_version)
        if source is None:
            source = {"kind": "manual", "copied_from": origin_version.version_ref}

    formula = _formula(data.get("formula"), required=not base)
    if formula is None:
        formula = base["formula"]
    yield_quantity = data.get("yield_quantity", base.get("yield_quantity"))
    if yield_quantity in (None, ""):
        raise _fail("Informe o rendimento da fórmula.", field="yield_quantity")
    yield_unit = str(data.get("yield_unit") or base.get("yield_unit") or "").strip()
    if not yield_unit:
        raise _fail("Informe a unidade do rendimento.", field="yield_unit")
    steps = _steps(data["steps"]) if "steps" in data and data["steps"] is not None else list(base.get("steps") or [])
    notes = _text(data, "notes") if "notes" in data else str(base.get("notes") or "")
    label = _text(data, "label") if "label" in data else ""

    with translating_errors():
        return craftsman.create_version(
            entry,
            formula=formula,
            yield_quantity=yield_quantity,
            yield_unit=yield_unit,
            origin=_origin(data.get("origin")),
            source=source,
            steps=steps,
            notes=notes,
            label=label,
            created_by=actor,
        )


@transaction.atomic
def update_draft_from_payload(version: RecipeVersion, data: dict) -> RecipeVersion:
    """``PATCH recipes/<ref>/versions/<n>/``: só os campos presentes no corpo."""
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
    version = RecipeVersion.objects.select_for_update().select_related("entry").get(pk=version.pk)
    _assert_version_revision(version, data)
    changes: dict[str, Any] = {}
    if "formula" in data:
        changes["formula"] = _formula(data.get("formula"), required=True)
    if "yield_quantity" in data:
        if data.get("yield_quantity") in (None, ""):
            raise _fail("Informe o rendimento da fórmula.", field="yield_quantity")
        changes["yield_quantity"] = data.get("yield_quantity")
    if "yield_unit" in data:
        unit = str(data.get("yield_unit") or "").strip()
        if not unit:
            raise _fail("Informe a unidade do rendimento.", field="yield_unit")
        changes["yield_unit"] = unit
    if "steps" in data:
        changes["steps"] = _steps(data.get("steps"))
    if "notes" in data:
        changes["notes"] = _text(data, "notes")
    if "label" in data:
        changes["label"] = _text(data, "label")
    unknown = sorted(set(data) - set(_VERSION_FIELDS) - {"expectedRevision"})
    if unknown and not changes:
        raise _fail(f"Nenhum campo do rascunho no corpo (recebido: {', '.join(unknown)}).")
    with translating_errors():
        return craftsman.update_draft(version, **changes)


@transaction.atomic
def publish(version: RecipeVersion, data: dict | None = None, *, actor: str = ""):
    """``POST .../publish/``: escreve a ficha de execução e vira a versão atual.

    Leva junto o perfil de cada insumo (``Material.metadata``: alérgenos, dieta,
    nutrição, densidade) para o ``RecipeItem.meta`` de linha nova. Sem isso uma
    receita nova publicada não teria de onde tirar o rótulo do PDP (ADR-008)
    nem a ponte volume/massa do leite ao publicar.
    """
    data = data if isinstance(data, dict) else {}
    entry = RecipeEntry.objects.select_for_update().get(pk=version.entry_id)
    version = RecipeVersion.objects.select_for_update().get(pk=version.pk)
    _assert_version_revision(version, data)
    _assert_revision(entry, data, field="expectedEntryRevision")
    with translating_errors():
        return craftsman.publish_version(
            version, actor=actor, default_item_meta=material_profiles_for(version.formula or {}),
        )


#: O que do cadastro do insumo viaja para a linha da ficha ao publicar.
_MATERIAL_PROFILE_KEYS = ("allergens", "diet", "nutrition", "density_g_per_ml")


def material_profiles_for(formula: dict) -> dict[str, dict]:
    """``sku`` → perfil do insumo (só as chaves que a ficha lê), para os SKUs da fórmula."""
    from shopman.buyman.models import Material

    skus = {
        str(line.get("sku") or "").strip()
        for line in [*list(formula.get("items") or []), *list(formula.get("parts") or [])]
        if str(line.get("sku") or "").strip()
    }
    if not skus:
        return {}
    profiles: dict[str, dict] = {}
    for material in Material.objects.filter(sku__in=skus):
        metadata = material.metadata or {}
        profile = {key: metadata[key] for key in _MATERIAL_PROFILE_KEYS if key in metadata}
        if profile:
            profiles[material.sku] = profile
    return profiles


# ── Lente e padronização ─────────────────────────────────────────────────────


def standardize_formula(formula: Any, basis_g: Any = 1000) -> dict:
    """A fórmula reescrita para a âncora somar ``basis_g`` (padrão da casa: 1000 g)."""
    formula = _formula(formula, required=True)
    with translating_errors():
        craftsman.validate_formula(formula)
        return craftsman.standardize(formula, basis_g if basis_g not in (None, "") else 1000)


# ── Captura ──────────────────────────────────────────────────────────────────


def capture(text: str = "", image: dict | None = None, language_hint: str = "") -> CapturedRecipe:
    """Lê uma anotação (``text``) ou uma foto (``image = {data_base64, media_type}``)."""
    image = image if isinstance(image, dict) else {}
    return read_recipe(
        text=text or "",
        image_base64=str(image.get("data_base64") or ""),
        image_media_type=str(image.get("media_type") or ""),
        language_hint=language_hint or "",
    )


# ── Localização (404 por tipo) ───────────────────────────────────────────────


def get_entry(ref: str) -> RecipeEntry:
    """A entry pelo ``ref``. ``RecipeEntryNotFound`` quando não existe (404 na porta)."""
    entry = RecipeEntry.objects.filter(ref=ref).select_related("current_version").first()
    if entry is None:
        raise RecipeEntryNotFound(f"Receita '{ref}' não existe no inventário.")
    return entry


def get_version(entry: RecipeEntry, number: int) -> RecipeVersion:
    """A versão ``number`` da entry. ``RecipeVersionNotFound`` quando não existe (404 na porta)."""
    version = entry.versions.filter(number=number).first()
    if version is None:
        raise RecipeVersionNotFound(f"A receita '{entry.ref}' não tem a versão {number}.")
    return version
