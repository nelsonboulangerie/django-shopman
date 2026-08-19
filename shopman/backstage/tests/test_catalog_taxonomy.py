"""A taxonomia de coleções aplicada sem reseed (BI-QUESTION-CATALOG §9).

O que estes testes guardam:

- **o resultado bate com o que o `seed` produz** — se um divergir do outro, um
  ambiente novo e um ambiente migrado ficam com catálogos diferentes, e isso só
  apareceria muito depois;
- **nenhum produto fica órfão**: coleção com produto dentro não é apagada;
- **renomear preserva os vínculos** — recriar "Mercearia" perderia os 11;
- **é catálogo, não operação**: nada de pedido, sessão ou movimento.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from config.management.commands.apply_catalog_taxonomy import MOVES, RENAME


def _run(*args):
    out = StringIO()
    call_command("apply_catalog_taxonomy", *args, stdout=out, stderr=out)
    return out.getvalue()


@pytest.fixture
def old_taxonomy(db):
    """O catálogo como estava antes de 17/08: com 'Balcão' e 'Despensa'."""
    from shopman.offerman.models import Collection, CollectionItem, Product

    made = {}
    for ref, name, order in [
        ("rusticos", "Rústicos", 4), ("finos", "Finos", 5),
        ("balcao", "Balcão", 8), ("despensa", "Despensa", 9),
    ]:
        made[ref] = Collection.objects.create(ref=ref, name=name, sort_order=order)

    layout = {
        "balcao": ["FE", "TB", "MIB", "PH",
                   "BRIOCHE-BURGER", "PAO-HOTDOG", "COMBO-PETIT-DEJ"],
        "rusticos": ["BF", "CGO"],
        "finos": ["CT"],
        "despensa": ["GL", "GR"],
    }
    for ref, skus in layout.items():
        for i, sku in enumerate(skus):
            product = Product.objects.create(sku=sku, name=sku.title())
            CollectionItem.objects.create(
                collection=made[ref], product=product, sort_order=i, is_primary=True
            )
    return made


def _layout():
    from shopman.offerman.models import CollectionItem

    result: dict[str, set] = {}
    for ref, sku in CollectionItem.objects.values_list("collection__ref", "product__sku"):
        result.setdefault(ref, set()).add(sku)
    return result


# ── O resultado ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_seven_land_where_the_owner_put_them(old_taxonomy):
    _run()
    layout = _layout()
    assert {"FE", "TB", "MIB", "PH"} <= layout["rusticos"]
    assert {"BRIOCHE-BURGER", "PAO-HOTDOG"} <= layout["finos"]
    assert layout["combos"] == {"COMBO-PETIT-DEJ"}


@pytest.mark.django_db
def test_balcao_is_retired_and_despensa_becomes_mercearia(old_taxonomy):
    from shopman.offerman.models import Collection

    _run()
    refs = set(Collection.objects.values_list("ref", flat=True))
    assert "balcao" not in refs
    assert "despensa" not in refs
    assert {"mercearia", "combos"} <= refs
    assert Collection.objects.get(ref="mercearia").name == "Mercearia"


@pytest.mark.django_db
def test_renaming_keeps_the_products_attached(old_taxonomy):
    """Recriar a coleção perderia os vínculos; renomear no lugar preserva."""
    _run()
    assert _layout()["mercearia"] == {"GL", "GR"}


@pytest.mark.django_db
def test_no_product_is_left_without_a_collection(old_taxonomy):
    from shopman.offerman.models import CollectionItem, Product

    before = Product.objects.count()
    _run()
    assert CollectionItem.objects.count() == before
    assert CollectionItem.objects.filter(collection__isnull=True).count() == 0


# ── As guardas ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_running_twice_changes_nothing(old_taxonomy):
    _run()
    first = _layout()
    output = _run()
    assert _layout() == first
    assert "já está aplicada" in output


@pytest.mark.django_db
def test_dry_run_writes_nothing(old_taxonomy):
    before = _layout()
    output = _run("--dry-run")
    assert _layout() == before
    assert "nada gravado" in output


@pytest.mark.django_db
def test_a_collection_that_still_holds_products_is_not_deleted(old_taxonomy):
    """Apagar coleção com produto dentro os deixaria sem casa nenhuma."""
    from shopman.offerman.models import Collection, CollectionItem, Product

    extra = Product.objects.create(sku="INTRUSO", name="Intruso")
    CollectionItem.objects.create(collection=old_taxonomy["balcao"], product=extra)

    output = _run()
    assert Collection.objects.filter(ref="balcao").exists()
    assert "NÃO apaguei" in output
    assert _layout()["balcao"] == {"INTRUSO"}


@pytest.mark.django_db
def test_it_touches_catalog_only(old_taxonomy):
    from shopman.orderman.models import Order, Session
    from shopman.stockman.models import Move

    Order.objects.create(ref="REAL-1", channel_ref="pdv",
                         status=Order.Status.COMPLETED, total_q=1000)
    before = (Order.objects.count(), Session.objects.count(), Move.objects.count())
    _run()
    assert (Order.objects.count(), Session.objects.count(), Move.objects.count()) == before


# ── Anti-divergência com o seed ──────────────────────────────────────────────


def test_the_command_and_the_seed_describe_the_same_taxonomy():
    """Um ambiente migrado e um ambiente novo têm de ficar iguais.

    Lê a lista do `_seed_catalog` como texto — o alvo é a fonte, e se alguém
    mudar um sem o outro, isto acusa antes de dois catálogos divergirem em
    produção.
    """
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "config/management/commands/seed.py"
    block = source.read_text().split("collection_skus = {")[1].split("\n        }")[0]

    def skus_of(ref: str) -> set[str]:
        chunk = block.split(f'"{ref}": [')[1].split("],")[0]
        return set(re.findall(r'"([A-Z][A-Z0-9-]+)"', chunk))

    for target_ref, skus in MOVES.items():
        assert set(skus) <= skus_of(target_ref), (
            f"o comando manda {skus} para '{target_ref}', mas o seed não os põe lá"
        )
    # E a coleção renomeada tem de ser a que o seed cria com o nome novo.
    assert f'"{RENAME[1]}": [' in block
    assert f'"{RENAME[0]}": [' not in block
