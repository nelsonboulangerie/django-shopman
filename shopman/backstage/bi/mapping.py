"""Sugestão de de-para — a máquina propõe, a pessoa confirma (P1 da fundação).

Três sugestores, um por tabela de alias, todos com a mesma disciplina:

- **Nunca confirmam.** Tudo o que sai daqui nasce ``proposed``; a leitura só
  usa ``confirmed``, então uma sugestão errada que ninguém viu não muda número.
- **Nunca sobrescrevem.** Chave que já tem alias (em qualquer estado) é pulada:
  o que a pessoa já decidiu, ou já viu, não volta para a fila.
- **Declaram o que não acharam.** Produto sem correspondência acima do corte
  vira linha sem produto, com o melhor palpite e a nota na cara — a fila do
  Admin mostra o que falta mapear, em vez de esconder num log de console.

Produto casa por SKU exato primeiro (o Yooga guarda o código real da casa;
quando o catálogo usar o mesmo, é 100 sem fuzzy) e por nome depois
(``rapidfuzz.token_set_ratio`` sobre nome normalizado — sem acento, minúsculo,
espaços colapsados). Categoria e forma de pagamento não têm fuzzy: são
vocabulários por trecho, e a sugestão é só "esta categoria/forma crua não casa
com regra nenhuma" — quem lê decide o trecho e o significado.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from django.db.models import Count

DEFAULT_MIN_SCORE = 80


def normalize_name(value: str) -> str:
    """Minúsculo, sem acento, um espaço só — o que dois sistemas escrevem igual."""
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


@dataclass
class Suggestions:
    """O que um sugestor produziu, para o relatório do comando."""

    kind: str
    created: int = 0
    skipped_existing: int = 0
    matched: int = 0
    unmatched: int = 0
    rows: list = field(default_factory=list)  # (chave, alvo ou '—', score ou '', nota)


# ── Produto ─────────────────────────────────────────────────────────────────


def suggest_products(source: str, *, min_score: int = DEFAULT_MIN_SCORE, dry_run: bool = False) -> Suggestions:
    from rapidfuzz import fuzz, process
    from shopman.offerman.models import Product

    from shopman.backstage.models import HistoricalSaleItem, ProductAlias

    result = Suggestions(kind="product")

    known_skus = set(
        ProductAlias.objects.filter(source=source).exclude(external_sku="").values_list("external_sku", flat=True)
    )
    known_names = set(
        ProductAlias.objects.filter(source=source, external_sku="").values_list("external_name", flat=True)
    )

    # ⚠️ `.order_by()` antes do agrupamento: o `Meta.ordering` do item entraria
    # no GROUP BY e o agrupamento deixaria de agrupar (o mesmo defeito que o
    # `propose_consumption_tags` já pagou).
    seen = (
        HistoricalSaleItem.objects.filter(sale__source=source)
        .order_by()
        .values("sku", "product_name")
        .annotate(lines=Count("id"))
        .order_by("-lines")
    )
    # Uma chave por SKU (o nome mais frequente representa) e uma por nome sem SKU.
    by_sku: dict[str, str] = {}
    by_name: dict[str, int] = {}
    for row in seen:
        sku, name = row["sku"] or "", (row["product_name"] or "").strip()
        if sku:
            by_sku.setdefault(sku, name)
        elif name:
            by_name.setdefault(name, row["lines"])

    catalog = {
        sku: (name, normalize_name(name), pk)
        for pk, sku, name in Product.objects.values_list("id", "sku", "name")
    }
    catalog_by_sku_ci = {sku.lower(): sku for sku in catalog}
    sku_by_pk = {pk: sku for sku, (_name, _normalized, pk) in catalog.items()}
    choices = {sku: normalized for sku, (_name, normalized, _pk) in catalog.items()}

    def match(external_sku: str, external_name: str) -> tuple[int | None, int | None, str]:
        """(product_pk, score, nota) — SKU exato antes de nome parecido."""
        exact = catalog_by_sku_ci.get(external_sku.lower()) if external_sku else None
        if exact is not None:
            return catalog[exact][2], 100, "SKU igual ao do catálogo"
        if not external_name or not choices:
            return None, None, "sem nome para comparar" if not external_name else "catálogo vazio"
        best = process.extractOne(normalize_name(external_name), choices, scorer=fuzz.token_set_ratio)
        if best is None:
            return None, None, "sem correspondência"
        _normalized, score, sku = best
        score = int(round(score))
        if score >= min_score:
            return catalog[sku][2], score, f"nome parecido com {sku} ({catalog[sku][0]})"
        return None, score, f"melhor palpite abaixo do corte ({min_score}): {sku} ({catalog[sku][0]})"

    pending: list[ProductAlias] = []
    for external_sku, external_name in by_sku.items():
        if external_sku in known_skus:
            result.skipped_existing += 1
            continue
        pk, score, note = match(external_sku, external_name)
        pending.append(ProductAlias(
            source=source, external_sku=external_sku, external_name=external_name[:200],
            product_id=pk, score=score, note=note[:200],
        ))
    for external_name in by_name:
        if external_name in known_names:
            result.skipped_existing += 1
            continue
        pk, score, note = match("", external_name)
        pending.append(ProductAlias(
            source=source, external_sku="", external_name=external_name[:200],
            product_id=pk, score=score, note=note[:200],
        ))

    for alias in pending:
        if alias.product_id:
            result.matched += 1
        else:
            result.unmatched += 1
        result.rows.append((
            alias.external_sku or f"nome: {alias.external_name}",
            sku_by_pk.get(alias.product_id, "—"),
            alias.score if alias.score is not None else "",
            alias.note,
        ))
    if not dry_run and pending:
        ProductAlias.objects.bulk_create(pending, batch_size=500)
    result.created = len(pending)
    return result


# ── Categoria e forma de pagamento: o que nenhuma regra cobre ───────────────


def suggest_categories(*, dry_run: bool = False) -> Suggestions:
    from shopman.backstage.models import CategoryAlias, HistoricalSaleItem

    patterns = list(CategoryAlias.objects.order_by("position", "id").values_list("pattern", flat=True))
    raw_categories = (
        HistoricalSaleItem.objects.exclude(category="")
        .order_by()
        .values("category")
        .annotate(lines=Count("id"))
        .order_by("-lines")
    )
    return _suggest_vocabulary(
        CategoryAlias, "category", patterns,
        ((row["category"], row["lines"]) for row in raw_categories),
        note="categoria do histórico que nenhuma regra cobre",
        dry_run=dry_run,
    )


def suggest_payments(*, dry_run: bool = False) -> Suggestions:
    from shopman.backstage.models import HistoricalSale, PaymentMethodAlias

    patterns = list(PaymentMethodAlias.objects.order_by("position", "id").values_list("pattern", flat=True))
    raw_payments = (
        HistoricalSale.objects.exclude(payment="")
        .order_by()
        .values("payment")
        .annotate(lines=Count("id"))
        .order_by("-lines")
    )
    return _suggest_vocabulary(
        PaymentMethodAlias, "payment", patterns,
        ((row["payment"], row["lines"]) for row in raw_payments),
        note="forma de pagamento do histórico que nenhuma regra cobre",
        dry_run=dry_run,
    )


def _suggest_vocabulary(model, kind: str, patterns: list[str], raw_values, *, note: str, dry_run: bool) -> Suggestions:
    """Um alias por valor cru que nenhum trecho existente casa — em qualquer estado.

    Trecho proposto = o valor cru inteiro, minúsculo. Quem confirma pode
    encurtá-lo para o pedaço que importa e dizer o que ele significa; até lá a
    linha só marca "isto existe e não tem regra".
    """
    result = Suggestions(kind=kind)
    last_position = max(
        list(model.objects.values_list("position", flat=True)) or [0]
    )
    existing = set(patterns)
    pending = []
    for raw, lines in raw_values:
        lowered = (raw or "").strip().lower()
        if not lowered:
            continue
        if any(pattern in lowered for pattern in patterns) or lowered in existing:
            result.skipped_existing += 1
            continue
        existing.add(lowered)
        last_position += 10
        pending.append(model(pattern=lowered[:100], position=last_position, note=f"{note} ({lines} linhas)"[:200]))
        result.rows.append((lowered, "—", "", f"{lines} linhas"))
    result.unmatched = len(pending)
    if not dry_run and pending:
        model.objects.bulk_create(pending)
    result.created = len(pending)
    return result
