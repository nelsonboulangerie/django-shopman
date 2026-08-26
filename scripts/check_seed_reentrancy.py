#!/usr/bin/env python
"""Prova que o `seed --flush` é re-entrante num banco que JÁ tem curadoria.

O bug que este check impede de voltar (staging, 19-22/08/2026): o CI só rodava
`seed --flush` em banco recém-criado — a única condição em que o flush nunca
encontra linha hostil. No staging real havia 98 `ProductAlias` CONFIRMADOS
(FK PROTECT para o catálogo) e config de terminal escrita por gente; o flush
estourava `ProtectedError` no meio, sem transação, e deixava o banco pela metade.

Uso (no job Browser QA do Omotenashi Gate, DEPOIS do primeiro seed):

    python scripts/check_seed_reentrancy.py plant    # insere as linhas hostis
    python manage.py seed --flush                    # a SEGUNDA passada
    python scripts/check_seed_reentrancy.py assert   # a curadoria sobreviveu?

As linhas plantadas espelham os contratos de
shopman/backstage/tests/test_seed_flush_keeps_alias_curation.py e
test_seed_flush_keeps_terminal_config.py — mas aqui contra o Postgres real do
job, com o catálogo do seed anterior já no lugar (a condição do staging).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CURATOR_USERNAME = "curadora-do-staging"
KEPT_EXTERNAL_SKU = "CT-YOOGA"
ORPHAN_EXTERNAL_SKU = "XX-YOOGA"
EXTINCT_SKU = "PRODUTO-QUE-NAO-VOLTA"
TOTEM_REF = "totem-1"
TOTEM_STATION = {"mode": "autonomous", "operator": "totem-da-vitrine"}
SHOP_PRINTER = {"adapter": "driver", "model": "epson-tm-t20", "roll_width_mm": 58}


def _setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def plant() -> None:
    """Insere a curadoria hostil que o staging tinha e o CI nunca tinha."""
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from shopman.cashman.models import Terminal
    from shopman.offerman.models import Product

    from shopman.backstage.models import AliasStatus, ProductAlias

    curator = get_user_model().objects.create_user(CURATOR_USERNAME)

    # Alias CONFIRMADO apontando para um produto que o seed recria (Croissant/CT):
    # é a linha que fazia o `Product.delete()` do flush estourar ProtectedError.
    croissant = Product.objects.get(name="Croissant")
    ProductAlias.objects.create(
        source="yooga",
        external_sku=KEPT_EXTERNAL_SKU,
        external_name="Croissant Tradicional",
        product=croissant,
        status=AliasStatus.CONFIRMED,
        confirmed_by=curator,
        confirmed_at=timezone.now(),
    )

    # Alias CONFIRMADO para um produto que o seed NÃO recria: vira extinto (FK
    # vazia), nunca ProtectedError nem linha apagada.
    extinct = Product.objects.create(
        sku=EXTINCT_SKU, name="Só desta base", base_price_q=100
    )
    ProductAlias.objects.create(
        source="yooga",
        external_sku=ORPHAN_EXTERNAL_SKU,
        external_name="Coisa antiga",
        product=extinct,
        status=AliasStatus.CONFIRMED,
        confirmed_by=curator,
        confirmed_at=timezone.now(),
    )

    # Config de terminal escrita por gente no Admin, por cima do que o seed criou.
    balcao = Terminal.objects.get(ref="pdv-main")
    metadata = dict(balcao.metadata or {})
    metadata.update(
        {
            "default_fulfillment_type": "delivery",
            "favorite_collection_refs": ["paes", "doces"],
            "auto_lock_seconds": 30,
        }
    )
    hardware = dict(metadata.get("hardware") or {})
    # A loja comprou rolo de 58mm; o seed declara 80mm e não pode sobrescrever.
    hardware["printer"] = dict(SHOP_PRINTER)
    metadata["hardware"] = hardware
    balcao.metadata = metadata
    balcao.label = "Balcão da rua"
    balcao.location_ref = "frente"
    balcao.save(update_fields=["metadata", "label", "location_ref"])

    # Um segundo terminal que o seed não conhece: tem de sobreviver inteiro.
    Terminal.objects.create(
        ref=TOTEM_REF,
        label="Totem da vitrine",
        channel_ref="pdv",
        metadata={"station": dict(TOTEM_STATION)},
    )

    print("✅ plant: alias curado (FK PROTECT), alias de produto extinto, "
          "config do pdv-main e totem-1 no banco")


def check() -> list[str]:
    """Valida que a segunda passada do seed preservou a curadoria toda."""
    from shopman.cashman.models import Terminal

    from shopman.backstage.models import AliasStatus, ProductAlias

    failures: list[str] = []

    kept = ProductAlias.objects.filter(external_sku=KEPT_EXTERNAL_SKU).first()
    if kept is None:
        failures.append("alias curado sumiu no reseed (external_sku=CT-YOOGA)")
    else:
        if kept.status != AliasStatus.CONFIRMED:
            failures.append(f"alias curado perdeu o status: {kept.status}")
        if kept.confirmed_by is None or kept.confirmed_at is None:
            failures.append("alias curado perdeu a assinatura (confirmed_by/confirmed_at)")
        if kept.product is None:
            failures.append("alias curado não foi religado ao catálogo novo")
        elif kept.product.name != "Croissant":
            failures.append(
                f"alias curado religado ao produto errado: {kept.product.sku} "
                f"({kept.product.name})"
            )

    orphan = ProductAlias.objects.filter(external_sku=ORPHAN_EXTERNAL_SKU).first()
    if orphan is None:
        failures.append("alias de produto extinto sumiu no reseed (external_sku=XX-YOOGA)")
    else:
        if orphan.product is not None:
            failures.append(
                f"alias extinto religado indevidamente: {orphan.product.sku}"
            )
        if orphan.status != AliasStatus.CONFIRMED:
            failures.append(f"alias extinto perdeu o status: {orphan.status}")

    balcao = Terminal.objects.filter(ref="pdv-main").first()
    if balcao is None:
        failures.append("pdv-main sumiu no reseed")
    else:
        metadata = balcao.metadata or {}
        if metadata.get("default_fulfillment_type") != "delivery":
            failures.append("pdv-main perdeu default_fulfillment_type=delivery")
        if metadata.get("favorite_collection_refs") != ["paes", "doces"]:
            failures.append("pdv-main perdeu favorite_collection_refs")
        if metadata.get("auto_lock_seconds") != 30:
            failures.append("pdv-main perdeu auto_lock_seconds=30")
        if balcao.label != "Balcão da rua":
            failures.append(f"pdv-main perdeu o label da loja: {balcao.label!r}")
        printer = ((metadata.get("hardware") or {}).get("printer")) or {}
        if printer.get("roll_width_mm") != 58:
            failures.append(
                f"o seed sobrescreveu a impressora da loja: {printer or 'ausente'}"
            )

    totem = Terminal.objects.filter(ref=TOTEM_REF).first()
    if totem is None:
        failures.append("totem-1 deixou de existir no reseed")
    else:
        if not totem.is_active:
            failures.append("totem-1 voltou inativo")
        if (totem.metadata or {}).get("station") != TOTEM_STATION:
            failures.append(
                f"totem-1 perdeu a espécie da estação: {(totem.metadata or {}).get('station')!r}"
            )

    return failures


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"plant", "assert"}:
        print(__doc__)
        return 2
    _setup()
    if sys.argv[1] == "plant":
        plant()
        return 0
    failures = check()
    if failures:
        print("❌ seed --flush NÃO é re-entrante — curadoria perdida:")
        for failure in failures:
            print(f"  · {failure}")
        return 1
    print("✅ assert: seed re-entrante — alias curado religado, extinto preservado, "
          "config dos terminais intacta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
