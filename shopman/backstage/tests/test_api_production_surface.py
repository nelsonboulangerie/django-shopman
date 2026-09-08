"""Headless production API contract (api/v1/backstage/production/*).

Covers the REST surface that the dedicated production-nuxt app
(``prod.``) consumes: the floor + planning board reads, every write action
(plan/start/finish/advance-step/quick-finish/void), effective capabilities,
and the structured shortage envelopes that drive the material/order shortage
modals.

Reuses the orchestrator services (``shopman.backstage.services.production`` →
Craftsman); no domain rule is duplicated here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman.models import Position

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.production import resolve_production_access
from shopman.backstage.services.production import (
    MissingMaterial,
    ProductionOrderShortError,
    ProductionStockShortError,
)


def _operate_production_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


def _permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(
        content_type__app_label=app_label,
        codename=codename,
    )


@pytest.fixture
def production_operator(db):
    """Um operador de produção como a casa o define: superfície MAIS colunas.

    ⚠️ A fixture concedia só `operate_production`, e a suíte inteira media um usuário
    que não existe em nenhum dos dois grupos seedados. Ver `production_grants`.
    """
    from shopman.backstage.tests.production_grants import grant_production_operator

    user = User.objects.create_user("prod-api", password="pw", is_staff=True)
    user = grant_production_operator(user)
    user.user_permissions.add(
        _permission("shop", "manage_production"),
        _permission("backstage", "quick_finish_production"),
        _permission("backstage", "override_production_shortage"),
        _permission("backstage", "void_production"),
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("prod-admin", "prod@test.com", "pw")


@pytest.fixture
def position(db):
    return Position.objects.create(ref="forno", name="Forno", kind="oven", is_default=True)


@pytest.fixture
def recipe(db, position):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Produção")
    return Recipe.objects.create(
        ref="api-prod-v1",
        name="Pão de Produção",
        output_sku="API-PROD",
        batch_size=Decimal("10"),
        steps=["Mistura", "Forno"],
        meta={"max_started_minutes": 30, "capacity_per_day": 100},
    )


# ── Gate ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_board_requires_operate_production(client, recipe):
    bare = User.objects.create_user("bare-prod", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-production")).status_code == 403


@pytest.mark.django_db
def test_every_mutation_endpoint_enforces_the_floor_gate(client, recipe):
    """Contrato independe da superfície: cada endpoint de ESCRITA da produção
    recusa anônimo e staff sem ``operate_production`` — inclusive quem só tem
    a perm fina de relatórios (gestor leitor não fecha fornada)."""
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    urls = [
        reverse("api-backstage-wo-plan"),
        reverse("api-backstage-wo-start", args=[wo.pk]),
        reverse("api-backstage-wo-finish", args=[wo.pk]),
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        reverse("api-backstage-wo-quick-finish"),
        reverse("api-backstage-wo-void", args=[wo.pk]),
    ]

    for url in urls:
        assert client.post(url, {}, content_type="application/json").status_code in (401, 403), url

    bare = User.objects.create_user("bare-mutations", password="pw", is_staff=True)
    client.force_login(bare)
    for url in urls:
        assert client.post(url, {}, content_type="application/json").status_code == 403, url

    reports_only = User.objects.create_user("reports-only", password="pw", is_staff=True)
    reports_only.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(DayClosing),
            codename="view_production_reports",
        )
    )
    client.force_login(reports_only)
    for url in urls:
        assert client.post(url, {}, content_type="application/json").status_code == 403, url


@pytest.mark.django_db
def test_operator_and_superuser_pass_gate(client, recipe, production_operator, superuser):
    client.force_login(production_operator)
    assert client.get(reverse("api-backstage-production")).status_code == 200
    client.force_login(superuser)
    assert client.get(reverse("api-backstage-production")).status_code == 200


@pytest.mark.django_db
def test_surface_entry_permission_is_read_only_without_effective_edit_capability(
    client,
    recipe,
):
    operator = User.objects.create_user("coarse-only", password="pw", is_staff=True)
    operator.user_permissions.add(_operate_production_perm())
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(operator)

    board = client.get(reverse("api-backstage-production"))
    mutation = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        {"quantity": "10"},
        content_type="application/json",
    )

    assert board.status_code == 200
    assert board.json()["board"]["access"]["can_start"] is False
    assert mutation.status_code == 403


@pytest.mark.django_db
def test_board_filters_rows_and_counts_by_effective_view_capability(client, recipe):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 11, date=date.today(), position_ref="other")
    craft.start(started, quantity=11, position_ref="other", expected_rev=0)
    finished = craft.plan(recipe, 12, date=date.today(), position_ref="third")
    craft.finish(finished, finished=12, expected_rev=0)
    viewer = User.objects.create_user("planned-viewer", password="pw", is_staff=True)
    viewer.user_permissions.add(_permission("shop", "view_production_planned"))
    client.force_login(viewer)

    response = client.get(reverse("api-backstage-production"))

    assert response.status_code == 200
    board = response.json()["board"]
    assert [row["ref"] for row in board["work_orders"]] == [planned.ref]
    assert board["counts"] == {
        "total": 1,
        "planned": 1,
        "started": 0,
        "finished": 0,
        "void": 0,
        "planned_qty": "10",
        "started_qty": "0",
        "finished_qty": "0",
        "loss_qty": "0",
    }
    assert board["access"]["can_view_plan"] is True
    assert board["access"]["can_edit_plan"] is False


@pytest.mark.django_db
def test_action_endpoint_checks_matching_capability_and_observes_revocation(
    client,
    recipe,
):
    operator = User.objects.create_user("starter", password="pw", is_staff=True)
    grant = _permission("shop", "edit_production_started")
    operator.user_permissions.add(grant)
    first = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    second = craft.plan(recipe, 11, date=date.today(), position_ref="other")
    client.force_login(operator)

    allowed = client.post(
        reverse("api-backstage-wo-start", args=[first.pk]),
        {"quantity": "10"},
        content_type="application/json",
    )
    forbidden_finish = client.post(
        reverse("api-backstage-wo-finish", args=[first.pk]),
        {"quantity": "10"},
        content_type="application/json",
    )
    operator.user_permissions.remove(grant)
    revoked = client.post(
        reverse("api-backstage-wo-start", args=[second.pk]),
        {"quantity": "11"},
        content_type="application/json",
    )

    assert allowed.status_code == 200
    assert forbidden_finish.status_code == 403
    assert revoked.status_code == 403


@pytest.mark.django_db
@override_settings(PRODUCTION_TRUSTED_STATION_CAPABILITIES=("can_start",))
def test_station_policy_can_fail_closed_without_changing_the_role_matrix(recipe):
    operator = User.objects.create_user("station-bound", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("shop", "edit_production_started"))

    off_station = resolve_production_access(operator)
    on_station = resolve_production_access(operator, trusted_station_ref="forno")

    assert off_station.can_start is False
    assert on_station.can_start is True


@pytest.mark.django_db
def test_forged_force_payload_requires_separate_override_capability(client, recipe):
    operator = User.objects.create_user("ordinary-manager", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("shop", "manage_production"))
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-wo-plan"),
        {
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "force": True,
            "reason": "payload forjado",
        },
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_override_capability_still_requires_a_reason(client, recipe, production_operator):
    client.force_login(production_operator)

    response = client.post(
        reverse("api-backstage-wo-plan"),
        {
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "force": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Justificativa" in response.json()["detail"]


# ── Read ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_board_returns_payload(client, recipe, production_operator):
    craft.plan(recipe, 20, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    response = client.get(reverse("api-backstage-production"))
    assert response.status_code == 200
    assert "board" in response.json()


@pytest.mark.django_db
def test_board_rejects_invalid_date_instead_of_silently_using_today(client, recipe, production_operator):
    client.force_login(production_operator)
    response = client.get(reverse("api-backstage-production"), {"date": "tomorrow-ish"})
    assert response.status_code == 400
    assert response.json()["field"] == "date"


@pytest.mark.django_db
def test_mise_en_place_parses_false_as_false(client, recipe, production_operator):
    client.force_login(production_operator)
    response = client.get(
        reverse("api-backstage-production-mise-en-place"),
        {"expand": "false"},
    )
    assert response.status_code == 200
    assert response.json()["mise_en_place"]["expanded"] is False


@pytest.mark.django_db
def test_kds_returns_started_cards_only(client, recipe, production_operator):
    started = craft.plan(recipe, 12, date=date.today(), position_ref="forno")
    craft.start(started, quantity=12, position_ref="forno", expected_rev=0)
    client.force_login(production_operator)
    response = client.get(reverse("api-backstage-production-kds"))
    assert response.status_code == 200
    kds = response.json()["kds"]
    refs = {card["ref"] for card in kds["cards"]}
    assert started.ref in refs


# ── Write actions ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_plan_creates_work_order(client, recipe, production_operator):
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "20",
            "target_date": date.today().isoformat(),
            "position_ref": "forno",
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["result"] == "created"
    assert body["output_sku"] == "API-PROD"


@pytest.mark.django_db
def test_start_planned_work_order(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-start", args=[wo.pk]),
        data={"quantity": "10"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["wo_ref"] == wo.ref
    wo.refresh_from_db()
    assert wo.status == wo.Status.STARTED


@pytest.mark.django_db
def test_advance_step_increments_pointer(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    client.force_login(production_operator)
    response = client.post(reverse("api-backstage-wo-advance", args=[wo.pk]))
    assert response.status_code == 200
    assert response.json()["step_index"] == 1


@pytest.mark.django_db
def test_finish_started_work_order(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-finish", args=[wo.pk]),
        data={"quantity": "9"},
        content_type="application/json",
    )
    assert response.status_code == 200
    wo.refresh_from_db()
    assert wo.status == wo.Status.FINISHED


@pytest.mark.django_db
def test_quick_finish_plans_and_finishes(client, recipe, production_operator, position):
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-quick-finish"),
        data={"recipe_id": recipe.pk, "quantity": "5", "position_id": position.pk},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.django_db
def test_quick_finish_com_a_mesma_chave_nao_assa_duas_vezes(client, recipe, production_operator, position):
    """O duplo toque no quiosque não pode virar duas fornadas.

    ⚠️ Esta é a única operação COMPOSTA da produção: cria a WO e a fecha na
    mesma requisição. A trava do core (`WorkOrderEvent.idempotency_key`, com
    `unique` no banco) é correta e defensiva — ela até levanta
    `IDEMPOTENCY_CONFLICT` se a mesma chave aparecer em outra WO. Só que
    `_finish_idempotency_key` inclui o `work_order.pk`, e aqui o pk é **novo a
    cada tentativa**: chave nova, trava do core nunca alcançada.

    Sem a trava de REQUISIÇÃO, o segundo toque produzia uma segunda WorkOrder,
    um segundo `production_changed(action="finished")` e portanto um segundo
    `kind=MAKE` no ledger — mais um segundo consumo de insumo. O livro é
    imutável de propósito, então o conserto seria um ajuste no fechamento, com
    o dono perguntando por que faltou farinha.
    """
    from shopman.craftsman.models import WorkOrder

    client.force_login(production_operator)
    corpo = {
        "recipe_id": recipe.pk,
        "quantity": "5",
        "position_id": position.pk,
        "client_request_id": "quiosque-gesto-abc123",
    }

    primeira = client.post(reverse("api-backstage-wo-quick-finish"), data=corpo, content_type="application/json")
    assert primeira.status_code == 200

    segunda = client.post(reverse("api-backstage-wo-quick-finish"), data=corpo, content_type="application/json")
    assert segunda.status_code == 200

    # O replay devolve a MESMA fornada, não uma nova.
    assert segunda.json()["wo_ref"] == primeira.json()["wo_ref"]
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1, (
        "o segundo toque criou uma segunda fornada — dois MAKE no ledger imutável"
    )


@pytest.mark.django_db
def test_quick_finish_com_chave_nova_assa_de_novo(client, recipe, production_operator, position):
    """Duas fornadas avulsas iguais no mesmo dia são DUAS assadeiras de verdade.

    É por isso que a chave é do GESTO e não derivada do conteúdo: consolidar por
    (receita, posição, dia, quantidade) engoliria em silêncio a segunda fornada
    legítima. O `chaveDoGesto` do PDV descarta a chave no sucesso exatamente por
    isso — o próximo lançamento nasce com chave nova.

    E é por isso também que `CraftPlanning.plan` do core NÃO deve consolidar: o
    core é primitiva de criação, e quem decide "criar ou reaproveitar" é o
    orquestrador (ver `set_planned_quantity`, que procura antes de criar).
    """
    from shopman.craftsman.models import WorkOrder

    client.force_login(production_operator)
    base = {"recipe_id": recipe.pk, "quantity": "5", "position_id": position.pk}

    primeira = client.post(
        reverse("api-backstage-wo-quick-finish"),
        data={**base, "client_request_id": "gesto-1"},
        content_type="application/json",
    )
    segunda = client.post(
        reverse("api-backstage-wo-quick-finish"),
        data={**base, "client_request_id": "gesto-2"},
        content_type="application/json",
    )

    assert primeira.status_code == 200 and segunda.status_code == 200
    assert primeira.json()["wo_ref"] != segunda.json()["wo_ref"]
    assert WorkOrder.objects.filter(recipe=recipe).count() == 2


@pytest.mark.django_db
def test_void_work_order(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-void", args=[wo.pk]),
        data={"reason": "teste"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["wo_ref"] == wo.ref


# ── Structured shortage envelopes ────────────────────────────────────────────


@pytest.mark.django_db
def test_finish_material_shortage_returns_structured_envelope(client, recipe, production_operator, monkeypatch):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)

    def block_finish(**kwargs):
        raise ProductionStockShortError(
            work_order_ref=wo.ref,
            missing=[MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))],
        )

    monkeypatch.setattr(
        "shopman.backstage.api.operations.production_service.apply_finish",
        block_finish,
    )
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-finish", args=[wo.pk]),
        data={"quantity": "10"},
        content_type="application/json",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "material_shortage"
    assert error["missing"][0]["sku"] == "FARINHA"
    assert error["missing"][0]["shortage"] == "3"


@pytest.mark.django_db
def test_plan_order_shortage_returns_structured_envelope(client, recipe, production_operator, monkeypatch):
    def block_plan(**kwargs):
        raise ProductionOrderShortError(
            work_order_ref="WO-API-1",
            required=Decimal("12"),
            requested=Decimal("8"),
            order_refs=("ORD-1", "ORD-2"),
        )

    monkeypatch.setattr(
        "shopman.backstage.api.operations.production_service.apply_planned",
        block_plan,
    )
    client.force_login(production_operator)
    response = client.post(
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "position_ref": "forno",
        },
        content_type="application/json",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "order_shortage"
    assert error["required"] == "12"
    assert error["order_refs"] == ["ORD-1", "ORD-2"]
