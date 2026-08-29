"""Quiosque de QC do fournil (ADR-017 §9 / QC-FORNADA §5).

Cobre a projection ``build_qc_kiosk`` (painel de fornadas do dia + catálogos
de grau/defeito) e o endpoint ``GET /api/v1/backstage/production/qc/``, atrás
do gate grosso do chão (``backstage.operate_production``).
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman import Position

from shopman.backstage.projections.production import build_qc_kiosk
from shopman.backstage.services import production


@pytest.fixture
def floor_operator(db):
    """Superfície MAIS colunas — ver `production_grants`."""
    from shopman.backstage.tests.production_grants import grant_production_operator

    user = User.objects.create_user("qc-floor", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def recipe(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja QC")
    Position.objects.create(ref="forno", name="Forno", is_default=True)
    return Recipe.objects.create(
        ref="qc-baguete",
        name="Baguete",
        output_sku="BAG-TRAD",
        batch_size=40,
    )


@pytest.mark.django_db
def test_kiosk_carries_catalogs_with_semantics(recipe):
    kiosk = build_qc_kiosk(selected_date=date.today())

    # Escala do seed, do melhor para o pior — rank é a única hierarquia.
    assert [g.ref for g in kiosk.grades] == ["excellent", "standard", "fair", "minimal"]
    assert [g.rank for g in kiosk.grades] == sorted(
        (g.rank for g in kiosk.grades), reverse=True
    )
    default = next(g for g in kiosk.grades if g.is_default)
    assert default.ref == "standard"
    assert default.markdown_percent == 0

    # Defeitos ativos com hint (a segunda linha do botão) e o veto raro.
    defect_refs = {d.ref for d in kiosk.defects}
    assert "contaminated" in defect_refs
    vetoed = [d.ref for d in kiosk.defects if d.forces_discard]
    assert vetoed == ["contaminated"]


@pytest.mark.django_db
def test_kiosk_orders_open_first_closed_carry_partition(recipe, monkeypatch):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    today = date.today()

    craft.plan(recipe, 24, date=today, position_ref="forno", operator_ref="ana")
    closed = craft.plan(recipe, 40, date=today, position_ref="forno", operator_ref="bia")
    craft.start(closed, quantity=40, position_ref="forno", operator_ref="bia", expected_rev=0)
    production.apply_finish(
        work_order_id=closed.pk, quantity="40", actor="production:bia",
        partition=[
            {"quantity": "32", "quality_grade_ref": "standard"},
            {"quantity": "5", "quality_grade_ref": "minimal", "quality_defect_ref": "overbaked"},
            {"quantity": "3", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )

    kiosk = build_qc_kiosk(selected_date=today)

    assert kiosk.total_count == 2
    assert kiosk.closed_count == 1
    opened, finished = kiosk.orders
    assert opened.can_close and not opened.closed
    assert opened.planned_qty == "24"
    assert opened.started_qty == ""  # planejada: nada entrou no forno ainda
    assert finished.closed and not finished.can_close
    assert (finished.full_price_qty, finished.discounted_qty, finished.loss_qty) == ("32", "5", "3")


@pytest.mark.django_db
def test_kiosk_carries_the_real_oven_quantity(recipe):
    """Planejou 10, enfornou 11: o card carrega o started — é ele que ancora
    o fechamento (QC-FORNADA §1); ancorar no previsto gravaria 1 de perda
    que nunca existiu."""
    today = date.today()

    wo = craft.plan(recipe, 10, date=today, position_ref="forno", operator_ref="ana")
    craft.start(wo, quantity=11, position_ref="forno", operator_ref="ana", expected_rev=0)

    kiosk = build_qc_kiosk(selected_date=today)

    (card,) = kiosk.orders
    assert card.planned_qty == "10"
    assert card.started_qty == "11"


@pytest.mark.django_db
def test_kiosk_warns_about_open_batches_from_previous_days(recipe):
    """A fornada esquecida não depende de memória: o painel de hoje avisa."""
    from datetime import timedelta

    today = date.today()
    craft.plan(recipe, 10, date=today - timedelta(days=2), position_ref="forno")
    craft.plan(recipe, 12, date=today, position_ref="forno")

    kiosk = build_qc_kiosk(selected_date=today)

    assert kiosk.previous_open_count == 1
    assert kiosk.previous_open_date == (today - timedelta(days=2)).isoformat()


@pytest.mark.django_db
def test_closed_card_partition_uses_the_frozen_lot_percent(recipe, monkeypatch):
    """Editar o markdown de um grau no Admin não reescreve a leitura de
    fornada já fechada — o card classifica pelo percentual CONGELADO no lote."""
    from shopman.shop.models import QualityGrade

    recipe.meta = {"requires_batch_tracking": True, "shelf_life_days": 1}
    recipe.save(update_fields=["meta"])
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    today = date.today()

    wo = craft.plan(recipe, 10, date=today, position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    production.apply_finish(
        work_order_id=wo.pk, quantity="10", actor="production:op",
        partition=[
            {"quantity": "7", "quality_grade_ref": "standard"},
            {"quantity": "3", "quality_grade_ref": "fair", "quality_defect_ref": "misshapen"},
        ],
    )

    # O gestor zera o desconto de "fair" DEPOIS do fechamento.
    QualityGrade.objects.filter(ref="fair").update(markdown_percent=0)

    kiosk = build_qc_kiosk(selected_date=today)
    closed = next(o for o in kiosk.orders if o.closed and o.pk == wo.pk)
    assert closed.full_price_qty == "7"
    assert closed.discounted_qty == "3"  # o lote congelou 20%; a tabela nova não manda aqui


@pytest.mark.django_db
def test_qc_endpoint_behind_floor_gate(client, floor_operator, recipe):
    url = reverse("api-backstage-production-qc")

    response = client.get(url)
    assert response.status_code in (401, 403)

    client.force_login(floor_operator)
    response = client.get(url)
    assert response.status_code == 200
    payload = response.json()["qc"]
    assert [g["ref"] for g in payload["grades"]][0] == "excellent"
    assert payload["recipes"], "fornada avulsa precisa da lista de receitas"


@pytest.mark.django_db
def test_repeating_the_same_finish_is_idempotent(client, floor_operator, recipe, monkeypatch):
    """O MESMO fechamento, repetido, é replay — não conflito.

    O `idempotency_key` do finish sai do resultado resolvido (WO + linhas), e o
    core devolve a fornada existente. É o que tira o operador do beco: um
    receiver posterior estoura DEPOIS do commit, ele vê erro numa fornada que
    já está fechada, aperta de novo e agora funciona.
    """
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    client.force_login(floor_operator)
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    url = reverse("api-backstage-wo-finish", args=[wo.pk])
    body = {"quantity": "10", "partition": [{"quantity": "10", "quality_grade_ref": "standard"}]}

    first = client.post(url, body, content_type="application/json")
    assert first.status_code == 200

    second = client.post(url, body, content_type="application/json")
    assert second.status_code == 200
    assert second.json()["wo_ref"] == first.json()["wo_ref"]


@pytest.mark.django_db
def test_finishing_the_same_batch_with_other_numbers_is_a_clean_conflict(
    client, floor_operator, recipe, monkeypatch
):
    """Dois quiosques discordando do rendimento: o segundo leva 409 {detail}
    em pt-BR, nunca 500 cru (o CraftError do kernel não era capturado).

    Números diferentes é o caso perigoso — não é retry, é um segundo
    fechamento de uma fornada já fechada, com outra verdade.
    """
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    client.force_login(floor_operator)
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    url = reverse("api-backstage-wo-finish", args=[wo.pk])

    first = client.post(
        url,
        {"quantity": "10", "partition": [{"quantity": "10", "quality_grade_ref": "standard"}]},
        content_type="application/json",
    )
    assert first.status_code == 200

    second = client.post(
        url,
        {"quantity": "8", "partition": [{"quantity": "8", "quality_grade_ref": "standard"}]},
        content_type="application/json",
    )
    assert second.status_code == 409
    payload = second.json()
    assert "fechada em outra tela" in payload["detail"]
    assert payload["error"]["code"] == "state_conflict"


@pytest.mark.django_db
def test_finish_after_void_and_void_after_finish_conflict(client, floor_operator, recipe, monkeypatch):
    """Gestor estorna enquanto o forneiro fecha (e vice-versa): 409, com a
    mensagem dizendo O QUE aconteceu com a fornada."""
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    client.force_login(floor_operator)
    body = {"quantity": "10", "partition": [{"quantity": "10", "quality_grade_ref": "standard"}]}

    voided = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.void(voided, reason="teste")
    response = client.post(
        reverse("api-backstage-wo-finish", args=[voided.pk]), body,
        content_type="application/json",
    )
    assert response.status_code == 409
    assert "estornada" in response.json()["detail"]

    finished = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.post(
        reverse("api-backstage-wo-finish", args=[finished.pk]), body,
        content_type="application/json",
    )
    response = client.post(
        reverse("api-backstage-wo-void", args=[finished.pk]), {},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert "não pode ser estornada" in response.json()["detail"]


@pytest.mark.django_db
def test_quick_finish_accepts_partition(client, floor_operator, recipe, monkeypatch):
    """Fornada avulsa fechada pelo quiosque: N lotes, veto e perda."""
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    client.force_login(floor_operator)

    response = client.post(
        reverse("api-backstage-wo-quick-finish"),
        {
            "recipe_id": recipe.pk,
            "quantity": "10",
            "position_id": Position.objects.get(ref="forno").pk,
            "partition": [
                {"quantity": "8", "quality_grade_ref": "excellent"},
                {"quantity": "2", "quality_defect_ref": "misshapen", "loss": True},
            ],
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ok"] is True
    assert body["quantity"] == "8"

    from shopman.craftsman.models import WorkOrder, WorkOrderItem

    wo = WorkOrder.objects.get(ref=body["wo_ref"])
    assert wo.finished == 8
    waste = WorkOrderItem.objects.get(work_order=wo, kind=WorkOrderItem.Kind.WASTE)
    assert waste.quality_defect_ref == "misshapen"
