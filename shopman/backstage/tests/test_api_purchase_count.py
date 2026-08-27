"""Contagem de insumos (GET/POST api/v1/backstage/purchase/count/*).

A tela pré-carrega a posição CRUA do ledger por insumo; o dono informa o
contado, e a divergência (com motivo obrigatório) vira ``Move kind=adjust``
com usuário — auditoria pelo próprio ledger do Stockman.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.urls import reverse
from shopman.buyman.models import Material
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import DayClosing


def _dayclosing_perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename=codename,
    )


@pytest.fixture
def purchase_operator(db):
    user = User.objects.create_user("count-operator", password="pw", is_staff=True)
    user.user_permissions.add(_dayclosing_perm("operate_purchase"))
    return user


@pytest.fixture
def stock_auditor(db):
    user = User.objects.create_user("count-auditor", password="pw", is_staff=True)
    user.user_permissions.add(_dayclosing_perm("operate_purchase"), _dayclosing_perm("audit_stock"))
    return user


@pytest.fixture
def position(db):
    return Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_default=True)


@pytest.fixture
def material(db):
    return Material.objects.create(
        sku="FARINHA-T65",
        name="Farinha T65",
        unit="kg",
        shelf_life_days=180,
        metadata={"purchase": {"category": "Farinhas"}},
    )


def _sku_total(sku: str) -> Decimal:
    return Quant.objects.filter(sku=sku).aggregate(total=Sum("_quantity"))["total"] or Decimal("0")


# ── Permissão: operar Compras NÃO basta; contagem exige audit_stock ─────────


@pytest.mark.django_db
def test_count_board_requires_audit_stock(client, purchase_operator, material):
    client.force_login(purchase_operator)
    assert client.get(reverse("api-backstage-purchase-count")).status_code == 403


@pytest.mark.django_db
def test_count_confirm_requires_audit_stock(client, purchase_operator, material):
    client.force_login(purchase_operator)
    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "1"}]},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not Move.objects.filter(quant__sku=material.sku).exists()


# ── GET: posição crua do ledger por insumo ──────────────────────────────────


@pytest.mark.django_db
def test_count_board_returns_raw_ledger_position(client, stock_auditor, material, position):
    stock.receive(Decimal("12"), material.sku, position=position, batch="LOTE-A", reason="seed", kind=Move.Kind.BUY)
    stock.receive(Decimal("3.5"), material.sku, position=position, batch="LOTE-B", reason="seed", kind=Move.Kind.BUY)
    client.force_login(stock_auditor)

    response = client.get(reverse("api-backstage-purchase-count"))
    assert response.status_code == 200
    items = response.json()["count"]["items"]
    assert [item["sku"] for item in items] == [material.sku]
    (item,) = items
    assert item["name"] == "Farinha T65"
    assert item["unit"] == "kg"
    assert item["category"] == "Farinhas"
    assert item["systemQty"] == 15.5


@pytest.mark.django_db
def test_count_board_hides_inactive_material_without_stock(client, stock_auditor, material):
    Material.objects.create(sku="INSUMO-MORTO", name="Insumo desativado", unit="un", is_active=False)
    client.force_login(stock_auditor)

    items = client.get(reverse("api-backstage-purchase-count")).json()["count"]["items"]
    assert [item["sku"] for item in items] == [material.sku]


# ── POST: divergência exige motivo e sai como ADJUST com usuário ────────────


@pytest.mark.django_db
def test_confirm_shortage_writes_adjust_with_reason_and_user(client, stock_auditor, material, position):
    stock.receive(Decimal("12"), material.sku, position=position, batch="LOTE-A", reason="seed", kind=Move.Kind.BUY)
    client.force_login(stock_auditor)

    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "10,5", "reason": "Quebra na produção"}]},
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "1 ajuste" in body["message"]
    assert _sku_total(material.sku) == Decimal("10.5")

    move = Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.ADJUST).get()
    assert move.delta == Decimal("-1.5")
    assert "Quebra na produção" in move.reason
    assert move.user == stock_auditor

    (item,) = body["count"]["items"]
    assert item["systemQty"] == 10.5


@pytest.mark.django_db
def test_confirm_divergence_without_reason_is_rejected(client, stock_auditor, material, position):
    stock.receive(Decimal("12"), material.sku, position=position, batch="LOTE-A", reason="seed", kind=Move.Kind.BUY)
    client.force_login(stock_auditor)

    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "10"}]},
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "count_reason_required"
    assert body["field"] == "reason"
    assert "reason" in body["errors"]
    assert _sku_total(material.sku) == Decimal("12")
    assert not Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.ADJUST).exists()


@pytest.mark.django_db
def test_confirm_matching_count_writes_no_move(client, stock_auditor, material, position):
    stock.receive(Decimal("12"), material.sku, position=position, batch="LOTE-A", reason="seed", kind=Move.Kind.BUY)
    client.force_login(stock_auditor)

    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "12"}]},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert "sem divergência" in response.json()["message"]
    assert not Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.ADJUST).exists()


@pytest.mark.django_db
def test_confirm_negative_count_is_rejected(client, stock_auditor, material):
    client.force_login(stock_auditor)
    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "-1", "reason": "erro"}]},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "count_qty_invalid"


@pytest.mark.django_db
def test_confirm_unknown_sku_is_rejected(client, stock_auditor, material):
    client.force_login(stock_auditor)
    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": "BAGUETE", "countedQty": "3", "reason": "achado"}]},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "count_material_not_found"


@pytest.mark.django_db
def test_confirm_surplus_without_stock_creates_adjust_entry(client, stock_auditor, material, position):
    client.force_login(stock_auditor)
    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "5", "reason": "Sobra encontrada no depósito"}]},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert _sku_total(material.sku) == Decimal("5")
    move = Move.objects.filter(quant__sku=material.sku).get()
    assert move.kind == Move.Kind.ADJUST
    assert move.delta == Decimal("5")
    assert "Sobra encontrada no depósito" in move.reason
    assert move.user == stock_auditor


@pytest.mark.django_db
def test_confirm_shortage_reduces_oldest_quant_first(client, stock_auditor, material, position):
    stock.receive(Decimal("10"), material.sku, position=position, batch="LOTE-VELHO", reason="seed", kind=Move.Kind.BUY)
    stock.receive(Decimal("8"), material.sku, position=position, batch="LOTE-NOVO", reason="seed", kind=Move.Kind.BUY)
    client.force_login(stock_auditor)

    response = client.post(
        reverse("api-backstage-purchase-count-confirm"),
        data={"counts": [{"materialSku": material.sku, "countedQty": "6", "reason": "Perda de armazenagem"}]},
        content_type="application/json",
    )
    assert response.status_code == 200
    old = Quant.objects.get(sku=material.sku, batch="LOTE-VELHO")
    new = Quant.objects.get(sku=material.sku, batch="LOTE-NOVO")
    assert old.quantity == Decimal("0")
    assert new.quantity == Decimal("6")
    adjust_moves = Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.ADJUST)
    assert sorted(move.delta for move in adjust_moves) == [Decimal("-10"), Decimal("-2")]
