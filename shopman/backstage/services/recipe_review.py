"""Procedência e conferência das receitas (WP-RECEITAS-DA-CASA F1/F2).

Em 22/09/2026 o dono achou seis fichas com a massa errada, todas vindas de
inferência de agente. Elas passaram porque uma receita digitada pelo padeiro e
uma inventada por máquina tinham a mesma cara na tela. Aqui a ficha passa a
dizer duas coisas:

- **de onde veio** (procedência), lida do ``RecipeVersion.source`` que já
  existe: ``manual``/``import`` são da casa, ``note``/``photo`` são o caderno
  lido pelo sistema, ``ficha`` (bootstrap da ficha antiga) é o cadastro inicial,
  escrito por agente. Nada novo é gravado para isso;
- **se alguém da casa conferiu**, por quem e quando:
  ``RecipeVersion.meta["review"] = {by, by_name, at, formula_digest}``. A
  conferência é da VERSÃO; se a fórmula mudar depois (versão publicada se edita,
  D11), o carimbo deixa de valer e a tela diz que mudou.

A fila do padeiro (F2) é a lista das receitas cuja versão atual não está
conferida, na ordem do que mais sai: o que vendeu nos últimos 12 meses (a mesma
leitura canônica do B.I.), contando para a massa o que vendeu cada peça feita
dela. A massa da peça vem em destaque porque foi ali que as seis erraram.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeVersion

from shopman.backstage.services.exceptions import RecipeBookServiceError

logger = logging.getLogger(__name__)

#: Quanto da história de vendas ordena a fila.
SALES_WINDOW_DAYS = 365

PROVENANCE_HOUSE = "house"
PROVENANCE_NOTEBOOK = "notebook"
PROVENANCE_AGENT = "agent"

PROVENANCE_LABELS = {
    PROVENANCE_HOUSE: "Da casa",
    PROVENANCE_NOTEBOOK: "Do caderno",
    PROVENANCE_AGENT: "Do cadastro inicial",
}

_PROVENANCE_DETAILS = {
    "manual": "Escrita à mão no inventário.",
    "import": "Veio de uma planilha da casa.",
    "note": "Uma anotação do padeiro, lida pelo sistema.",
    "photo": "Uma foto do caderno, lida pelo sistema.",
    "ficha": "Ficha do cadastro inicial, escrita por agente. Ninguém da casa a declarou.",
}

REVIEW_PENDING = "pending"
REVIEW_CONFIRMED = "confirmed"
REVIEW_CHANGED = "changed"

REVIEW_LABELS = {
    REVIEW_PENDING: "Não conferida",
    REVIEW_CONFIRMED: "Conferida",
    REVIEW_CHANGED: "Mudou depois da conferência",
}


@dataclass(frozen=True)
class Provenance:
    kind: str
    label: str
    detail: str


@dataclass(frozen=True)
class ReviewState:
    status: str
    label: str
    by: str
    by_name: str
    at: str


def provenance_of(version: RecipeVersion | None) -> Provenance:
    """De onde veio a versão. Sem origem registrada conta como cadastro inicial."""
    source = version.source if version is not None and isinstance(version.source, dict) else {}
    source_kind = str(source.get("kind") or "")
    if source_kind in ("manual", "import"):
        kind = PROVENANCE_HOUSE
    elif source_kind in ("note", "photo"):
        kind = PROVENANCE_NOTEBOOK
    else:
        kind = PROVENANCE_AGENT
    detail = _PROVENANCE_DETAILS.get(source_kind, "A origem desta versão não foi registrada.")
    return Provenance(kind=kind, label=PROVENANCE_LABELS[kind], detail=detail)


def formula_digest(version: RecipeVersion) -> str:
    """O que a conferência assina: fórmula, rendimento e etapas da versão."""
    payload = {
        "formula": version.formula or {},
        "yield_quantity": str(version.yield_quantity),
        "yield_unit": version.yield_unit,
        "steps": version.steps or [],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def review_of(version: RecipeVersion | None) -> ReviewState:
    """O estado de conferência da versão, lido do carimbo em ``meta["review"]``."""
    review = (version.meta or {}).get("review") if version is not None else None
    if not isinstance(review, dict) or not review.get("by"):
        return ReviewState(REVIEW_PENDING, REVIEW_LABELS[REVIEW_PENDING], "", "", "")
    status = REVIEW_CONFIRMED if review.get("formula_digest") == formula_digest(version) else REVIEW_CHANGED
    return ReviewState(
        status=status,
        label=REVIEW_LABELS[status],
        by=str(review.get("by") or ""),
        by_name=str(review.get("by_name") or review.get("by") or ""),
        at=str(review.get("at") or ""),
    )


def confirm(version: RecipeVersion, *, actor: str, actor_name: str = "") -> RecipeVersion:
    """Assina a conferência da versão ATUAL publicada. Repetir só renova o carimbo.

    Conferência anônima é indistinguível de nenhuma conferência: sem autor, recusa.
    """
    if not str(actor or "").strip():
        raise RecipeBookServiceError("Conferência precisa de quem conferiu.", code="REVIEW_WITHOUT_ACTOR")
    entry = version.entry
    if version.status != RecipeVersion.Status.PUBLISHED or entry.current_version_id != version.pk:
        raise RecipeBookServiceError(
            "Só a versão em uso pode ser conferida. Abra a receita de novo.",
            code="REVIEW_NOT_CURRENT",
        )
    version.meta = {
        **(version.meta or {}),
        "review": {
            "by": actor,
            "by_name": (actor_name or actor).strip(),
            "at": timezone.now().isoformat(),
            "formula_digest": formula_digest(version),
        },
    }
    version.save(update_fields=["meta"])
    return version


# ── A fila do padeiro ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QueueItem:
    entry: RecipeEntry
    version: RecipeVersion
    provenance: Provenance
    review: ReviewState
    sold_qty: Decimal
    sold_via: int
    dough_sku: str
    dough_name: str


def sold_by_sku(days: int = SALES_WINDOW_DAYS) -> dict[str, Decimal]:
    """Quantidade vendida por SKU do catálogo na janela, pela leitura canônica do B.I."""
    from shopman.backstage.bi.canonical import read_sales

    today = timezone.localdate()
    try:
        window = read_sales(today - timedelta(days=days), today)
    except Exception:
        # Sem a ordem por venda a fila continua útil (ordem por nome); quebrar a
        # conferência por causa do B.I. seria trocar o certo pelo bonito.
        logger.warning("recipe_review.sales_unavailable", exc_info=True)
        return {}
    sold: dict[str, Decimal] = defaultdict(Decimal)
    for line in window.lines():
        if line.product_ref:
            sold[line.product_ref] += Decimal(str(line.qty))
    return dict(sold)


def _consumers_by_input() -> dict[str, set[str]]:
    """SKU do insumo → SKUs que a ficha ATIVA de cada produto consome (um nível)."""
    consumers: dict[str, set[str]] = defaultdict(set)
    for output_sku, input_sku in Recipe.objects.filter(is_active=True, items__is_optional=False).values_list(
        "output_sku", "items__input_sku"
    ):
        if output_sku and input_sku:
            consumers[input_sku].add(output_sku)
    return consumers


def _dough_of(version: RecipeVersion, dough_names: dict[str, str]) -> tuple[str, str]:
    """A massa da peça: o item da fórmula que é ele mesmo uma receita do inventário.

    Só peça (rende unidade) tem massa a destacar. Na massa, a prep (levain,
    autolisada) é fração da fórmula, não "a massa" dela.
    """
    if version.yield_unit != RecipeVersion.YieldUnit.UNIT:
        return "", ""
    formula = version.formula or {}
    for line in [*(formula.get("preps") or []), *(formula.get("items") or [])]:
        sku = str(line.get("sku") or "")
        if sku and sku in dough_names and sku != version.entry.output_sku:
            return sku, dough_names[sku]
    return "", ""


def review_queue(*, sold: dict[str, Decimal] | None = None) -> list[QueueItem]:
    """As receitas com versão em uso ainda não conferida, do que mais sai para o que menos sai."""
    entries = list(
        RecipeEntry.objects.filter(is_active=True, current_version__isnull=False)
        .select_related("current_version")
        .order_by("name", "ref")
    )
    sold = sold_by_sku() if sold is None else sold
    consumers = _consumers_by_input()
    dough_names = {entry.output_sku: entry.name for entry in RecipeEntry.objects.exclude(output_sku="")}
    items: list[QueueItem] = []
    for entry in entries:
        version = entry.current_version
        review = review_of(version)
        if review.status == REVIEW_CONFIRMED:
            continue
        qty = sold.get(entry.output_sku, Decimal("0")) if entry.output_sku else Decimal("0")
        via = consumers.get(entry.output_sku, set()) if entry.output_sku else set()
        qty += sum((sold.get(sku, Decimal("0")) for sku in via), Decimal("0"))
        dough_sku, dough_name = _dough_of(version, dough_names)
        items.append(
            QueueItem(
                entry=entry,
                version=version,
                provenance=provenance_of(version),
                review=review,
                sold_qty=qty,
                sold_via=len(via),
                dough_sku=dough_sku,
                dough_name=dough_name,
            )
        )
    items.sort(key=lambda item: (-item.sold_qty, item.entry.name.lower(), item.entry.ref))
    return items
