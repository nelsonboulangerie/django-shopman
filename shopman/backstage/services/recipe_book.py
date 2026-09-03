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

import logging
from contextlib import contextmanager
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from shopman.craftsman.exceptions import RecipeBookError
from shopman.craftsman.models import RecipeEntry, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman

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


def _steps(value: Any, *, field: str = "steps") -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        raise _fail("As etapas precisam ser uma lista de textos.", field=field)
    steps = [str(step).strip() for step in value if str(step or "").strip()]
    return steps


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
    return entry, version


def patch_entry(entry: RecipeEntry, data: dict) -> RecipeEntry:
    """``PATCH recipes/<ref>/``: nome, tipo, SKU, observações e arquivamento."""
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
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
    with translating_errors():
        entry.full_clean()
        entry.save()
    return entry


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


def create_version_from_payload(entry: RecipeEntry, data: dict, *, actor: str = "") -> RecipeVersion:
    """``POST recipes/<ref>/versions/``: um rascunho novo, do zero ou copiado de ``from_version``.

    Com ``from_version``, a versão de origem é a base e o corpo sobrescreve o
    que trouxer; sem a fórmula no corpo, a cópia é integral. Sem
    ``from_version``, fórmula, rendimento e unidade são obrigatórios.
    """
    if not isinstance(data, dict):
        raise _fail("A versão precisa ser um objeto.", field="version")
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


def update_draft_from_payload(version: RecipeVersion, data: dict) -> RecipeVersion:
    """``PATCH recipes/<ref>/versions/<n>/``: só os campos presentes no corpo."""
    if not isinstance(data, dict):
        raise _fail("O corpo precisa ser um objeto.")
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
    unknown = sorted(set(data) - set(_VERSION_FIELDS))
    if unknown and not changes:
        raise _fail(f"Nenhum campo do rascunho no corpo (recebido: {', '.join(unknown)}).")
    with translating_errors():
        return craftsman.update_draft(version, **changes)


def publish(version: RecipeVersion, *, actor: str = ""):
    """``POST .../publish/``: escreve a ficha de execução e vira a versão atual."""
    with translating_errors():
        return craftsman.publish_version(version, actor=actor)


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
