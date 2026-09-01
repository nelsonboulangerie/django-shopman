"""Cofre de dados curados — o que o backup promete, provado de ponta a ponta.

A promessa central é o CICLO FECHADO: exportar, perder/alterar dado, importar, e
o banco volta ao que era — por chave natural, com FKs e M2M atravessando a
planilha por ``ref``/``sku``, nunca por id de banco. E as fronteiras falham
fechado: coluna renomeada grita, aba desconhecida grita, dry-run não escreve,
erro no meio desfaz o arquivo inteiro, produção exige ``--force``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from shopman.buyman.models import Material, Supplier, SupplierMaterialCost
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.backup import registry, workbook
from shopman.shop.models import (
    Channel,
    Coupon,
    OmotenashiCopy,
    Promotion,
    RuleConfig,
    Shop,
)


@pytest.fixture
def curated(db):
    """Um recorte pequeno mas atravessado de FKs, M2M, JSON e chave composta."""
    shop = Shop.objects.create(name="Padaria do Teste", defaults={"pickup": True})
    channel = Channel.objects.create(ref="pos", name="Balcão", shop=shop)
    product = Product.objects.create(
        sku="PAO-01",
        name="Pão de teste",
        base_price_q=1500,
        unit="un",
        metadata={"fiscal": {"ncm": "1905.90.90"}},
    )
    product.keywords.set(["pao", "integral"])
    listing = Listing.objects.create(ref="balcao", name="Balcão")
    ListingItem.objects.create(listing=listing, product=product, price_q=1600)
    rule = RuleConfig.objects.create(
        ref="happy-hour", rule_path="shopman.shop.rules.pricing.HappyHourRule",
        label="Happy hour", params={"percent": 10},
    )
    rule.channels.add(channel)
    promotion = Promotion.objects.create(
        ref="promo-teste", name="Promo", type="percent", value=10,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2027, 1, 1, tzinfo=UTC),
    )
    Coupon.objects.create(code="BEMVINDO", promotion=promotion)
    OmotenashiCopy.objects.create(
        key="welcome", moment="checkout", audience="customer", message="Bem-vindo",
    )
    recipe = Recipe.objects.create(
        ref="pao-01", name="Pão", output_sku="PAO-01", batch_size=Decimal("10"),
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="FARINHA", quantity=Decimal("5"), unit="kg",
    )
    supplier = Supplier.objects.create(ref="moinho", name="Moinho")
    material = Material.objects.create(sku="FARINHA", name="Farinha", unit="kg")
    SupplierMaterialCost.objects.create(supplier=supplier, material=material, cost_q=18000)
    return {"product": product, "rule": rule, "channel": channel}


def _export_xlsx(tmp_path: Path) -> Path:
    call_command("export_backup", "--out", str(tmp_path), stdout=StringIO())
    files = list(tmp_path.glob("backup-*.xlsx"))
    assert len(files) == 1
    return files[0]


def test_registry_has_entities_in_import_order(db):
    names = [e.name for e in registry.entries()]
    assert "products" in names and "coupons" in names
    tiers = [e.tier for e in registry.entries()]
    assert tiers == sorted(tiers)
    # O acoplamento fino que importa: filho vem depois do pai.
    assert names.index("listing_items") > names.index("listings")
    assert names.index("coupons") > names.index("promotions")


def test_every_resource_exports_on_seedless_db(db):
    for entry in registry.entries():
        dataset = entry.resource_class().export()
        assert dataset.headers, entry.name


def test_roundtrip_restores_deleted_and_mutated_rows(curated, tmp_path):
    path = _export_xlsx(tmp_path)

    Coupon.objects.all().delete()
    Promotion.objects.all().delete()
    RuleConfig.objects.all().delete()
    ListingItem.objects.all().delete()
    product = curated["product"]
    product.base_price_q = 999
    product.metadata = {}
    product.keywords.clear()
    product.save()

    call_command("import_backup", str(path), "--apply", stdout=StringIO())

    product.refresh_from_db()
    assert product.base_price_q == 1500
    assert product.metadata == {"fiscal": {"ncm": "1905.90.90"}}
    assert sorted(t.name for t in product.keywords.all()) == ["integral", "pao"]
    rule = RuleConfig.objects.get(ref="happy-hour")
    assert rule.params == {"percent": 10}
    assert list(rule.channels.values_list("ref", flat=True)) == ["pos"]
    assert Coupon.objects.get(code="BEMVINDO").promotion.ref == "promo-teste"
    item = ListingItem.objects.get(listing__ref="balcao", product__sku="PAO-01")
    assert item.price_q == 1600
    assert OmotenashiCopy.objects.filter(key="welcome", moment="checkout").count() == 1
    cost = SupplierMaterialCost.objects.get(supplier__ref="moinho", material__sku="FARINHA")
    assert cost.cost_q == 18000


def test_dry_run_is_default_and_writes_nothing(curated, tmp_path):
    path = _export_xlsx(tmp_path)
    Coupon.objects.all().delete()
    out = StringIO()
    call_command("import_backup", str(path), stdout=out)
    assert Coupon.objects.count() == 0
    assert "Dry-run limpo" in out.getvalue()


def test_renamed_column_fails_loud(curated, tmp_path):
    path = _export_xlsx(tmp_path)
    datasets = workbook.read_xlsx(path)
    headers = datasets["products"].headers
    headers[headers.index("base_price_q")] = "preco"
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(workbook.write_xlsx(datasets))
    with pytest.raises(CommandError, match="products"):
        call_command("import_backup", str(broken), stdout=StringIO())


def test_unknown_sheet_fails_loud(curated, tmp_path):
    path = _export_xlsx(tmp_path)
    datasets = workbook.read_xlsx(path)
    datasets["surpresa"] = datasets["products"]
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(workbook.write_xlsx(datasets))
    with pytest.raises(CommandError, match="surpresa"):
        call_command("import_backup", str(broken), stdout=StringIO())


def test_apply_rolls_back_the_whole_file_on_row_error(curated, tmp_path):
    path = _export_xlsx(tmp_path)
    datasets = workbook.read_xlsx(path)
    # Cupom apontando para promoção inexistente: a aba de cupons falha...
    row = list(datasets["coupons"][0])
    row[datasets["coupons"].headers.index("promotion__ref")] = "nao-existe"
    datasets["coupons"] = _replace_rows(datasets["coupons"], [row])
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(workbook.write_xlsx(datasets))

    Product.objects.all().update(base_price_q=999)
    with pytest.raises(CommandError):
        call_command("import_backup", str(broken), "--apply", stdout=StringIO(), stderr=StringIO())
    # ...e nem a aba de produtos (que viria antes e passaria) pode ter escrito.
    assert Product.objects.get(sku="PAO-01").base_price_q == 999


def test_apply_in_production_requires_force(curated, tmp_path, settings):
    path = _export_xlsx(tmp_path)
    settings.SHOPMAN_ENVIRONMENT = "production"
    with pytest.raises(CommandError, match="--force"):
        call_command("import_backup", str(path), "--apply", stdout=StringIO())


def test_csv_roundtrip(curated, tmp_path):
    call_command("export_backup", "--out", str(tmp_path), "--format", "csv", stdout=StringIO())
    csv_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
    Coupon.objects.all().delete()
    call_command("import_backup", str(csv_dir), "--apply", stdout=StringIO())
    assert Coupon.objects.filter(code="BEMVINDO").exists()


def test_shop_integrations_never_leave_the_db(curated, tmp_path):
    Shop.objects.all().update(integrations={"efi": {"client_secret": "segredo"}})
    path = _export_xlsx(tmp_path)
    datasets = workbook.read_xlsx(path)
    assert "integrations" not in (datasets["shop_settings"].headers or [])
    assert "segredo" not in path.read_bytes().decode("utf-8", errors="ignore")


def _replace_rows(dataset, rows):
    import tablib

    fresh = tablib.Dataset()
    fresh.headers = dataset.headers
    for row in rows:
        fresh.append(row)
    return fresh
