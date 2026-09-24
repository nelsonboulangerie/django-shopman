"""Abrir a embalagem: a unidade que se vende vira gramas que só a produção usa.

Decisão do dono (24/09/2026): "na produção é consumido em gramas. De alguma
forma, o estoque deve saber que aquela unidade não está mais disponível para
revenda, mas aquela quantidade, dentro da validade, em tese, sim."

O modelo é o gesto físico de abrir o tablete:

- a **embalagem** é o SKU comprado e vendido por unidade
  (``MANTEIGA-SAL-PRESIDENT-200``, ``un``) e declara, no cadastro de compra,
  em que ela se abre::

      Material.metadata["opens_into"] = {
          "sku": "MANTEIGA-COM-SAL",   # o insumo aberto, com unidade própria
          "quantity": "0.200",         # conteúdo de UMA embalagem, nessa unidade
          "shelf_life_days": 7,        # opcional: validade depois de aberta
      }

- o **aberto** é outro SKU — o insumo que a ficha usa (``MANTEIGA-COM-SAL``,
  ``kg``). Ele não tem cadastro de venda, então a revenda nunca o vende; e a
  ficha fala a unidade dele, então o porteiro de unidade da ficha
  (``RecipeItem.clean``) segue valendo sem exceção nenhuma no Core.

Quando a produção vai consumir o aberto e ele não basta, abre-se UMA embalagem
por vez: sai 1 un da embalagem (``MAKE``, a perna de saída da transformação —
e é isso que conta como consumo para a reposição do Compras) e entra o conteúdo
no aberto (``MAKE``), no mesmo lugar e com lote próprio quando há validade
depois de aberto. O consumo da ficha já tira do mais antigo primeiro
(``consumable_quants``), então o aberto que sobrou é usado antes do novo.

Nunca se abre embalagem da vitrine (``Position.is_saleable``): o que está
exposto para o cliente fica para o cliente — a mesma régua do consumo da
Produção.

Cores não se importam (ADR-001): o Craftsman não sabe de embalagem nem o Buyman
de receita. Abrir é composição, e mora no orquestrador — chamado antes do
fechamento da fornada (``shop/services/production.finish_work_order``) e
contado pelo guardrail de disponibilidade (``shop/adapters/inventory``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Package:
    """Uma embalagem que se abre em ``content`` de ``opened_sku``."""

    sku: str
    opened_sku: str
    content: Decimal
    shelf_life_days: int | None


def _package_from(material) -> Package | None:
    spec = (material.metadata or {}).get("opens_into") if isinstance(material.metadata, dict) else None
    if not isinstance(spec, dict):
        return None
    opened_sku = str(spec.get("sku") or "").strip()
    try:
        content = Decimal(str(spec.get("quantity")))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not opened_sku or content <= 0 or opened_sku == material.sku:
        return None
    shelf = spec.get("shelf_life_days")
    shelf_days = shelf if isinstance(shelf, int) and not isinstance(shelf, bool) and shelf >= 0 else None
    return Package(sku=material.sku, opened_sku=opened_sku, content=content, shelf_life_days=shelf_days)


def packages_opening_into(opened_sku: str) -> list[Package]:
    """As embalagens ativas que se abrem em ``opened_sku``."""
    from shopman.buyman.models import Material

    packages = []
    for material in Material.objects.filter(is_active=True, metadata__opens_into__sku=opened_sku).order_by("sku"):
        package = _package_from(material)
        if package is not None:
            packages.append(package)
    return packages


def _sealed_quants(package_sku: str):
    """Embalagens fechadas que a produção pode abrir: fora da vitrine, mais antiga primeiro."""
    from django.db.models import F
    from shopman.stockman.services.queries import StockQueries

    return (
        StockQueries.list_quants(package_sku, include_empty=False)
        .exclude(position__is_saleable=True)
        .order_by(F("target_date").asc(nulls_first=True), "pk")
    )


def _open_quants(opened_sku: str):
    """O aberto que a ficha pode consumir — a régua de ``consumable_quants`` do consumo.

    Fora da vitrine, salvo ``CRAFTSMAN_CONSUME_FROM_SALEABLE_POSITIONS``.
    """
    from shopman.craftsman.conf import get_setting
    from shopman.stockman.services.queries import StockQueries

    quants = StockQueries.list_quants(opened_sku, include_empty=False)
    if not get_setting("CONSUME_FROM_SALEABLE_POSITIONS"):
        quants = quants.exclude(position__is_saleable=True)
    return quants


def _available(quants) -> Decimal:
    return sum((quant.available for quant in quants), Decimal("0"))


def openable_content(opened_sku: str) -> Decimal:
    """Quanto de ``opened_sku`` as embalagens fechadas ainda podem virar."""
    total = Decimal("0")
    for package in packages_opening_into(opened_sku):
        sealed = _available(_sealed_quants(package.sku))
        total += sealed.to_integral_value(rounding="ROUND_FLOOR") * package.content
    return total


def _opened_batch(package: Package, sealed_quant) -> str:
    """Lote do aberto: validade depois de aberta, sem passar da validade da embalagem."""
    from shopman.stockman import Batch

    today = timezone.localdate()
    candidates = []
    if package.shelf_life_days is not None:
        candidates.append(today + timedelta(days=package.shelf_life_days))
    if sealed_quant.batch:
        sealed_batch = Batch.objects.filter(ref=sealed_quant.batch).only("expiry_date").first()
        if sealed_batch and sealed_batch.expiry_date:
            candidates.append(sealed_batch.expiry_date)
    if not candidates:
        return ""
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    ref = f"{package.opened_sku}-ABERTO-{stamp}"[:50]
    Batch.objects.create(
        ref=ref,
        sku=package.opened_sku,
        production_date=today,
        expiry_date=min(candidates),
        notes=f"Aberto de {package.sku}",
    )
    return ref


def open_package(package: Package, *, reason: str, user=None) -> bool:
    """Abre UMA embalagem fechada. ``False`` quando não há embalagem para abrir."""
    from shopman.stockman import Move
    from shopman.stockman.services.movements import StockMovements

    for sealed in _sealed_quants(package.sku):
        if sealed.available < 1:
            continue
        with transaction.atomic():
            StockMovements.issue(
                quantity=Decimal("1"), quant=sealed, user=user, kind=Move.Kind.MAKE,
                reason=f"Embalagem aberta: {reason}",
            )
            StockMovements.receive(
                quantity=package.content,
                sku=package.opened_sku,
                position=sealed.position,
                batch=_opened_batch(package, sealed),
                user=user,
                reason=f"Aberto de {package.sku}: {reason}",
                kind=Move.Kind.MAKE,
                opened_from_sku=package.sku,
                opened_from_batch=sealed.batch or "",
            )
        return True
    return False


def ensure_open_stock(opened_sku: str, needed: Decimal, *, reason: str, user=None) -> int:
    """Abre embalagens até o aberto cobrir ``needed``. Devolve quantas abriu.

    Abre uma por vez e só o necessário: o aberto que já existe é usado primeiro.
    Faltando embalagem, para — a falta segue para o guardrail/override de
    sempre, que decide se a fornada fecha assim mesmo.
    """
    packages = packages_opening_into(opened_sku)
    if not packages or needed <= 0:
        return 0
    opened = 0
    while _available(_open_quants(opened_sku)) < needed:
        if not any(open_package(package, reason=reason, user=user) for package in packages):
            break
        opened += 1
    if opened:
        logger.info(
            "package_opening.opened",
            extra={"opened_sku": opened_sku, "packages": opened, "reason": reason},
        )
    return opened


def open_for_work_order(work_order, *, user=None) -> int:
    """Abre o que a fornada vai consumir, antes do fechamento. Devolve quantas abriu.

    Usa a mesma conta do consumo (``CraftExecution.finish``): a quantidade BRUTA
    da ficha congelada × (quantidade iniciada ÷ rendimento da ficha).
    """
    snapshot = (work_order.meta or {}).get("_recipe_snapshot") or {}
    items = snapshot.get("items")
    if items:
        batch_size = Decimal(str(snapshot["batch_size"]))
    else:
        recipe = work_order.recipe
        batch_size = recipe.batch_size
        items = [
            {"input_sku": item.input_sku, "gross_quantity": str(item.gross_quantity)}
            for item in recipe.items.filter(is_optional=False)
        ]
    started = work_order.started_qty or work_order.quantity
    if not batch_size:
        return 0
    coefficient = Decimal(str(started)) / Decimal(str(batch_size))
    needs: dict[str, Decimal] = {}
    for item in items:
        quantity = item.get("gross_quantity", item.get("quantity"))
        needs[item["input_sku"]] = needs.get(item["input_sku"], Decimal("0")) + Decimal(str(quantity)) * coefficient
    return sum(
        ensure_open_stock(sku, needed, reason=f"Fornada {work_order.ref}", user=user)
        for sku, needed in needs.items()
    )


# ── Declarar: "Quando aberto, vira" ─────────────────────────────────────────

#: Unidades em que o aberto pode ser medido — o que se pesa ou se mede.
OPENED_UNITS = ("kg", "g", "l", "ml")

_SIZE_SUFFIX = r"\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\s*$"


def opened_name_for(package_name: str) -> str:
    """"Manteiga Extra com Sal Président 200g" → "Manteiga Extra com Sal Président (aberta)"."""
    import re

    base = re.sub(_SIZE_SUFFIX, "", package_name, flags=re.IGNORECASE).strip() or package_name
    return f"{base} (aberta)"


def suggested_content(package_sku: str, opened_unit: str = "kg") -> Decimal | None:
    """Conteúdo de uma embalagem na unidade do aberto, pelo peso líquido declarado.

    Vem de ``Product.unit_weight_g`` do cadastro de venda do mesmo SKU (a
    Mercearia o grava a partir da embalagem). Sem ele, não se sugere nada.
    """
    from shopman.offerman.models import Product
    from shopman.utils.units import UnitError, convert

    grams = Product.objects.filter(sku=package_sku).values_list("unit_weight_g", flat=True).first()
    if not grams:
        return None
    try:
        return convert(Decimal(grams), "g", opened_unit).normalize()
    except UnitError:
        return None


def declare_opening(package, *, opened_sku: str = "", create_opened: bool = False, opened_unit: str = "kg",
                    quantity=None, shelf_life_days=None):
    """Grava em que a embalagem se abre. Devolve o cadastro do aberto.

    ``create_opened`` cria o insumo aberto a partir da embalagem
    (``<SKU>-ABERTO``, nome sem o tamanho + "(aberta)"), ou reaproveita o que
    já existe com esse SKU. A embalagem é contada por unidade; o aberto, pesado
    ou medido.
    """
    from django.core.exceptions import ValidationError
    from shopman.buyman.models import Material

    from shopman.shop.services.sku_records import is_produced_here

    if package.unit != "un":
        raise ValidationError({"unit": f"{package.name} é contado em {package.unit}: só embalagem por unidade se abre."})
    if is_produced_here(package.sku):
        raise ValidationError({"sku": f"{package.name} é produzido aqui: não é embalagem comprada."})
    try:
        content = Decimal(str(quantity).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        content = Decimal("0")
    if not content.is_finite() or content <= 0:
        raise ValidationError({"quantity": "Informe quanto vem em uma embalagem."})
    days = None
    if shelf_life_days not in (None, ""):
        try:
            days = int(shelf_life_days)
        except (TypeError, ValueError):
            days = -1
        if days < 0:
            raise ValidationError({"shelf_life_days": "Validade depois de aberto: um número de dias, 0 ou mais."})

    if create_opened:
        if opened_unit not in OPENED_UNITS:
            raise ValidationError({"opened_unit": f"O aberto se mede em {', '.join(OPENED_UNITS)}."})
        opened = Material.objects.filter(sku=f"{package.sku}-ABERTO").first()
        if opened is None:
            opened = Material(sku=f"{package.sku}-ABERTO", name=opened_name_for(package.name), unit=opened_unit)
            opened.full_clean()
            opened.save()
    else:
        opened = Material.objects.filter(sku=str(opened_sku or "").strip(), is_active=True).first()
        if opened is None:
            raise ValidationError({"opened_sku": "Escolha o insumo em que a embalagem vira, ou crie a partir dela."})
    if opened.sku == package.sku:
        raise ValidationError({"opened_sku": "A embalagem não se abre nela mesma."})
    if opened.unit not in OPENED_UNITS:
        raise ValidationError({"opened_sku": f"{opened.name} é contado em {opened.unit}: o aberto se pesa ou se mede."})

    spec = {"sku": opened.sku, "quantity": str(content)}
    if days is not None:
        spec["shelf_life_days"] = days
    metadata = dict(package.metadata or {})
    metadata["opens_into"] = spec
    package.metadata = metadata
    package.save(update_fields=["metadata", "updated_at"])
    return opened


def clear_opening(package) -> None:
    """A embalagem deixa de se abrir: some a declaração; o aberto e o estoque ficam."""
    metadata = dict(package.metadata or {})
    if metadata.pop("opens_into", None) is not None:
        package.metadata = metadata
        package.save(update_fields=["metadata", "updated_at"])
