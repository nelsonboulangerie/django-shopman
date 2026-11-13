"""O item do pedido do iFood vira o SKU da casa pelo vínculo confirmado (#2326).

Caso medido: no primeiro pedido real (IFOOD-261112-3417) os itens chegaram com
``89c36650c82b11eeb4433516a`` (``externalCode``) e
``c570b678-9a2b-4cab-a52d-26ae21d3f8d6`` (id do item, sem ``externalCode``).
Nenhum dos dois é SKU nosso: deu ``stock_unknown_sku``, sem baixa, e o ticket
caiu na estação genérica "Encomendas".
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.orderman.models import OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.models import CatalogBinding, CatalogSnapshot, Channel
from shopman.shop.services import ifood_ingest, kds
from shopman.shop.services.ifood_item_sku import resolve_items

pytestmark = pytest.mark.django_db

MERCHANT = "merchant-nelson"
ITEM_ID = "c570b678-9a2b-4cab-a52d-26ae21d3f8d6"
EXTERNAL_CODE = "89c36650c82b11eeb4433516a"


@pytest.fixture
def channel():
    return Channel.objects.create(ref="ifood", name="iFood", config={
        "confirmation": {"mode": "manual"},
        "payment": {"method": "external", "timing": "external"},
        "stock": {"check_on_commit": False, "allow_untracked": False},
    })


def _product(sku: str, name: str = "") -> Product:
    return Product.objects.create(sku=sku, name=name or sku, unit="un", base_price_q=4800)


def _bind(channel, product, *, resource_id=ITEM_ID, product_ref="remote-product", account_ref=MERCHANT):
    actor, _ = get_user_model().objects.get_or_create(username="revisor")
    snapshot = CatalogSnapshot.objects.create(
        channel=channel, provider="ifood", account_ref=account_ref, catalog_ref="cat",
        context="DEFAULT", captured_at=timezone.now(), imported_by=actor,
        sha256="0" * 64, raw_json="{}", source="test", item_count=1,
    )
    return CatalogBinding.objects.create(
        channel=channel, product=product, provider="ifood", account_ref=account_ref,
        catalog_ref=f"cat-{resource_id}-{product.sku}", context="DEFAULT", resource_id=resource_id,
        external_product_ref=product_ref, category_ref="remote-category",
        snapshot=snapshot, confirmed_by=actor,
    )


def _item(sku=EXTERNAL_CODE, line_id=ITEM_ID, name="Queijo Camembert"):
    return {"line_id": line_id, "sku": sku, "name": name, "qty": "1",
            "unit_price_q": 4800, "line_total_q": 4800, "meta": {"notes": "Embalado para presente"}}


def _payload(*items):
    return {"order_code": "ord-3417", "merchant_id": MERCHANT, "display_id": "3417",
            "items": list(items) or [_item()]}


# ── Resolução ──────────────────────────────────────────────────────────────


def test_vinculo_confirmado_pelo_id_do_item_da_o_sku_da_casa(channel):
    _bind(channel, _product("CAMEMBERT"))

    [item] = resolve_items([_item()], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == "CAMEMBERT"
    assert item["meta"]["catalog_link"] == {
        "source": "binding", "remote_sku": EXTERNAL_CODE, "remote_item_id": ITEM_ID,
    }
    # o resto da linha (observação da cozinha) segue intacto
    assert item["meta"]["notes"] == "Embalado para presente"


def test_item_sem_external_code_resolve_pelo_id(channel):
    """O segundo item do 3417: sem ``externalCode``, o sku de entrada é o id."""
    _bind(channel, _product("CAMEMBERT"))

    [item] = resolve_items([_item(sku=ITEM_ID)], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == "CAMEMBERT"


def test_vinculo_pelo_id_do_produto_remoto(channel):
    _bind(channel, _product("CAMEMBERT"), resource_id="outro-item", product_ref=ITEM_ID)

    [item] = resolve_items([_item()], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == "CAMEMBERT"


def test_external_code_que_ja_e_sku_da_casa_vale_sem_vinculo(channel):
    _product("CAMEMBERT")

    [item] = resolve_items([_item(sku="CAMEMBERT")], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == "CAMEMBERT"
    assert item["meta"]["catalog_link"]["source"] == "external_code"


def test_vinculo_vence_o_external_code(channel):
    """A decisão humana registrada vale mais que um código digitado no Portal."""
    _product("OUTRO")
    _bind(channel, _product("CAMEMBERT"))

    [item] = resolve_items([_item(sku="OUTRO")], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == "CAMEMBERT"


def test_sem_vinculo_o_item_entra_como_veio(channel):
    [item] = resolve_items([_item()], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == EXTERNAL_CODE
    assert item["meta"]["catalog_link"]["source"] == "unbound"


def test_vinculo_de_outra_conta_nao_serve(channel):
    _bind(channel, _product("CAMEMBERT"), account_ref="outra-loja")

    [item] = resolve_items([_item()], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == EXTERNAL_CODE


def test_dois_produtos_para_o_mesmo_item_nao_se_desempatam(channel):
    _bind(channel, _product("CAMEMBERT"))
    _bind(channel, _product("BRIE"), resource_id=EXTERNAL_CODE)

    [item] = resolve_items([_item()], channel_ref="ifood", merchant_id=MERCHANT)

    assert item["sku"] == EXTERNAL_CODE
    assert item["meta"]["catalog_link"]["source"] == "ambiguous"


# ── Ingestão, estoque e cozinha ────────────────────────────────────────────


def test_ingestao_grava_o_sku_da_casa_no_pedido(channel):
    _bind(channel, _product("CAMEMBERT"))

    order = ifood_ingest.ingest(_payload())

    line = OrderItem.objects.get(order=order)
    assert line.sku == "CAMEMBERT"
    assert line.meta["catalog_link"]["remote_sku"] == EXTERNAL_CODE
    assert order.snapshot["items"][0]["sku"] == "CAMEMBERT"


def test_item_sem_vinculo_nao_quebra_o_pedido(channel):
    order = ifood_ingest.ingest(_payload())

    assert OrderItem.objects.get(order=order).sku == EXTERNAL_CODE


def test_ticket_cai_na_estacao_da_colecao_do_produto(channel):
    """O ticket do 3417 caiu na estação genérica porque o SKU não era nosso."""
    queijos = Collection.objects.create(ref="queijos", name="Queijos")
    camembert = _product("CAMEMBERT", "Queijo Camembert")
    CollectionItem.objects.create(collection=queijos, product=camembert, is_primary=True)
    KDSInstance.objects.create(ref="encomendas", name="Encomendas", type="picking")
    frios = KDSInstance.objects.create(ref="frios", name="Frios", type="picking")
    frios.collections.add(queijos)
    _bind(channel, camembert)

    order = ifood_ingest.ingest(_payload())
    kds.fire_lines(session_key=order.session_key, lines=kds.order_lines(order))

    ticket = KDSTicket.objects.get(session_key=order.session_key)
    assert ticket.kds_instance.ref == "frios"
    assert [line["sku"] for line in ticket.items] == ["CAMEMBERT"]


def test_aviso_do_item_sem_vinculo_diz_qual_item(channel):
    from shopman.shop.services.stock import _alert_unknown_sku

    from shopman.backstage.models import OperatorAlert

    order = ifood_ingest.ingest(_payload())
    item = order.snapshot["items"][0]
    _alert_unknown_sku(order, item["sku"], item)

    alert = OperatorAlert.objects.get(type="stock_unknown_sku", order_ref=order.ref)
    assert '"Queijo Camembert"' in alert.message
    assert "não tem produto da casa ligado" in alert.message


def test_aviso_do_item_ambiguo_diz_que_ha_dois_produtos(channel):
    from shopman.shop.services.stock import _alert_unknown_sku

    from shopman.backstage.models import OperatorAlert

    _bind(channel, _product("CAMEMBERT"))
    _bind(channel, _product("BRIE"), resource_id=EXTERNAL_CODE)
    order = ifood_ingest.ingest(_payload())
    item = order.snapshot["items"][0]
    _alert_unknown_sku(order, item["sku"], item)

    alert = OperatorAlert.objects.get(type="stock_unknown_sku", order_ref=order.ref)
    assert "ligado a mais de um produto da casa" in alert.message
