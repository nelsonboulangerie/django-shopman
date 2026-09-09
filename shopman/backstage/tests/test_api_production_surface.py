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

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.stockman.models import Position

from shopman.backstage.api.operations import _production_actor
from shopman.backstage.api.production_freshness import (
    signed_action_proof,
    signed_source_revision,
)
from shopman.backstage.models import DayClosing
from shopman.backstage.projections.production import resolve_production_access
from shopman.backstage.services import production as production_service
from shopman.backstage.services.production import (
    MissingMaterial,
    ProductionOrderShortError,
    ProductionStockShortError,
)
from shopman.backstage.tests.support import production_mutation_post


def _operate_production_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_production",
    )


def test_production_actor_is_deterministic_and_fits_event_storage():
    request = SimpleNamespace(user=SimpleNamespace(username="u" * 150))

    first = _production_actor(request)
    second = _production_actor(request)

    assert first == second
    assert first.startswith("production:")
    assert len(first) == 100


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
    oven = Position.objects.create(ref="forno", name="Forno", kind="oven", is_default=True)
    Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)
    return oven


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


def _projected_body(projection: dict, action: dict, **fields) -> dict:
    return {
        **fields,
        "projection_generated_at": projection["generated_at"],
        "source_revision": projection["source_revision"],
        "fresh_until": projection["fresh_until"],
        "contract_version": projection["contract_version"],
        "action_ref": action["ref"],
        "action_proof": action["proof"],
    }


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
        assert production_mutation_post(client, url, {}, content_type="application/json").status_code in (401, 403), url

    bare = User.objects.create_user("bare-mutations", password="pw", is_staff=True)
    client.force_login(bare)
    for url in urls:
        assert production_mutation_post(client, url, {}, content_type="application/json").status_code == 403, url

    reports_only = User.objects.create_user("reports-only", password="pw", is_staff=True)
    reports_only.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(DayClosing),
            codename="view_production_reports",
        )
    )
    client.force_login(reports_only)
    for url in urls:
        assert production_mutation_post(client, url, {}, content_type="application/json").status_code == 403, url


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
    mutation = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        {
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "coarse-start",
        },
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
    operator.user_permissions.add(
        grant,
        _permission("shop", "view_production_planned"),
    )
    first = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    second = craft.plan(recipe, 11, date=date.today(), position_ref="other")
    client.force_login(operator)

    allowed = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[first.pk]),
        {"quantity": "10", "expected_rev": first.rev, "idempotency_key": "start-first"},
        content_type="application/json",
    )
    forbidden_finish = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[first.pk]),
        {"quantity": "10"},
        content_type="application/json",
    )
    operator.user_permissions.remove(grant)
    revoked = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[second.pk]),
        {"quantity": "11"},
        content_type="application/json",
    )

    assert allowed.status_code == 200
    assert forbidden_finish.status_code == 403
    assert revoked.status_code == 403
    assert forbidden_finish.json()["error"] == {
        "code": "forbidden",
        "capability": "can_close_qc",
        "recovery": {
            "action": "request_access",
            "label": "Solicitar acesso a um gestor",
        },
    }
    assert revoked.json()["error"]["capability"] == "can_start"


@pytest.mark.django_db
def test_action_rejects_a_target_hidden_from_the_signed_projection(client, recipe):
    operator = User.objects.create_user("start-without-view", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("shop", "edit_production_started"))
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(operator)

    board = client.get(reverse("api-backstage-production")).json()["board"]
    assert board["access"]["can_start"] is True
    assert board["work_orders"] == []

    response = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "hidden-target-start",
            "projection_generated_at": board["generated_at"],
            "source_revision": board["source_revision"],
            "fresh_until": board["fresh_until"],
            "contract_version": board["contract_version"],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert {issue["field"] for issue in response.json()["error"]["issues"]} == {
        "action_proof",
        "action_ref",
    }
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_unprojected_direct_urls_do_not_reveal_hidden_target_existence_or_date(
    client,
    recipe,
):
    operator = User.objects.create_user("blind-starter", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("shop", "edit_production_started"))
    hidden = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(operator)
    today_board = client.get(reverse("api-backstage-production")).json()["board"]
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_board = client.get(
        reverse("api-backstage-production"),
        {"date": tomorrow.isoformat()},
    ).json()["board"]
    assert not any(action["enabled"] or action["proof"] for action in today_board["actions"])
    assert not any(action["enabled"] or action["proof"] for action in tomorrow_board["actions"])

    cases = (
        (hidden.pk, hidden.rev, today_board),
        (hidden.pk, hidden.rev, tomorrow_board),
        (hidden.pk + 99_999, 0, today_board),
        (hidden.pk + 99_999, 0, tomorrow_board),
    )
    envelopes = []
    for target_id, rev, projection in cases:
        response = client.post(
            reverse("api-backstage-wo-start", args=[target_id]),
            {
                "quantity": "10",
                "expected_rev": rev,
                "idempotency_key": "opaque-direct-target",
                "projection_generated_at": projection["generated_at"],
                "source_revision": projection["source_revision"],
                "fresh_until": projection["fresh_until"],
                "contract_version": projection["contract_version"],
                "action_ref": f"start:{target_id}",
                "action_proof": "not-a-projected-action",
            },
            content_type="application/json",
        )
        assert response.status_code == 400
        envelopes.append(response.json()["error"])

    assert all(envelope == envelopes[0] for envelope in envelopes)
    assert envelopes[0]["issues"][0]["field"] == "action_proof"


@pytest.mark.django_db
def test_kds_proof_cannot_void_a_planned_work_order_absent_from_its_actions(
    client,
    recipe,
    production_operator,
):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 10, date=date.today(), position_ref="other")
    craft.start(started, quantity=10, position_ref="other", expected_rev=started.rev)
    client.force_login(production_operator)
    kds = client.get(reverse("api-backstage-production-kds")).json()["kds"]
    assert all(action["ref"] != f"void:{planned.pk}" for action in kds["actions"])
    other_action = next(action for action in kds["actions"] if action["ref"] == f"void:{started.pk}")

    response = client.post(
        reverse("api-backstage-wo-void", args=[planned.pk]),
        data={
            "reason": "não foi projetada no KDS",
            "expected_rev": planned.rev,
            "idempotency_key": "kds-cannot-void-hidden-planned",
            "projection_generated_at": kds["generated_at"],
            "source_revision": kds["source_revision"],
            "fresh_until": kds["fresh_until"],
            "contract_version": kds["contract_version"],
            "action_ref": f"void:{planned.pk}",
            "action_proof": other_action["proof"],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["issues"][0]["field"] == "action_proof"
    planned.refresh_from_db()
    assert planned.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_board_projected_void_action_is_accepted(
    client,
    recipe,
    production_operator,
):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"void:{planned.pk}")

    response = client.post(
        action["href"],
        data={
            "reason": "correção operacional",
            "expected_rev": action["expected_rev"],
            "idempotency_key": "board-projected-void",
            "projection_generated_at": board["generated_at"],
            "source_revision": board["source_revision"],
            "fresh_until": board["fresh_until"],
            "contract_version": board["contract_version"],
            "action_ref": action["ref"],
            "action_proof": action["proof"],
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    planned.refresh_from_db()
    assert planned.status == WorkOrder.Status.VOID


@pytest.mark.django_db
def test_action_proof_is_bound_to_the_filtered_projection_target(
    client,
    recipe,
    production_operator,
):
    visible = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    hidden = craft.plan(recipe, 10, date=date.today(), position_ref="other")
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production"), {"position": "forno"}).json()["board"]
    visible_action = next(item for item in board["actions"] if item["ref"] == f"start:{visible.pk}")
    assert all(action["ref"] != f"start:{hidden.pk}" for action in board["actions"])

    response = client.post(
        reverse("api-backstage-wo-start", args=[hidden.pk]),
        data={
            "quantity": "10",
            "expected_rev": hidden.rev,
            "idempotency_key": "filtered-target-is-not-projected",
            "projection_generated_at": board["generated_at"],
            "source_revision": board["source_revision"],
            "fresh_until": board["fresh_until"],
            "contract_version": board["contract_version"],
            "action_ref": f"start:{hidden.pk}",
            "action_proof": visible_action["proof"],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["issues"][0]["field"] == "action_proof"
    hidden.refresh_from_db()
    assert hidden.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_qc_capability_cannot_implicitly_start_a_planned_work_order(
    client,
    recipe,
):
    qc_only = User.objects.create_user("qc-only", password="pw", is_staff=True)
    qc_only.user_permissions.add(_permission("shop", "edit_production_finished"))
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(qc_only)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "qc-cannot-start",
        },
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert response.json()["error"]["capability"] == "can_view_planned"
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


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

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        {
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "force": True,
            "reason": "payload forjado",
            "expected_rev": None,
            "idempotency_key": "forged-force",
        },
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_override_capability_still_requires_a_reason(client, recipe, production_operator):
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        {
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "force": True,
            "expected_rev": None,
            "idempotency_key": "force-without-reason",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Justificativa" in response.json()["detail"]
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.django_db
def test_force_requires_the_proof_returned_by_the_exact_shortage_attempt(
    client,
    recipe,
    production_operator,
    monkeypatch,
):
    """A força é continuação do 409, não um booleano livre no payload."""

    def plan_or_shortage(**kwargs):
        if not kwargs["force"]:
            raise ProductionOrderShortError(
                work_order_ref="WO-SHORT",
                required=Decimal("10"),
                requested=kwargs["quantity"],
                order_refs=("ORD-1",),
            )
        return recipe.output_sku, "WO-FORCED", kwargs["quantity"], "created"

    monkeypatch.setattr(
        "shopman.backstage.api.operations.production_service.apply_planned",
        plan_or_shortage,
    )
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(
        item for item in board["actions"] if item["ref"] == f"plan:{recipe.pk}:{board['selected_date']}:forno"
    )
    url = reverse("api-backstage-wo-plan")
    original = _projected_body(
        board,
        action,
        recipe_id=recipe.pk,
        quantity="8",
        target_date=board["selected_date"],
        position_ref="forno",
        source="manual",
        expected_rev=None,
        idempotency_key="shortage-proof-attempt",
    )

    shortage = client.post(url, original, content_type="application/json")
    assert shortage.status_code == 409
    force_possibility = next(item for item in shortage.json()["error"]["possibilities"] if item["kind"] == "force")
    assert force_possibility["proof"]

    direct_force = client.post(
        url,
        {**original, "force": True, "reason": "autorizado"},
        content_type="application/json",
    )
    assert direct_force.status_code == 400
    assert direct_force.json()["error"]["issues"][0]["field"] == "override_proof"

    altered_effect = client.post(
        url,
        {
            **original,
            "quantity": "9",
            "force": True,
            "reason": "autorizado",
            "override_proof": force_possibility["proof"],
        },
        content_type="application/json",
    )
    assert altered_effect.status_code == 400
    assert altered_effect.json()["error"]["issues"][0]["field"] == "override_proof"

    accepted = client.post(
        url,
        {
            **original,
            "force": True,
            "reason": "autorizado",
            "override_proof": force_possibility["proof"],
        },
        content_type="application/json",
    )
    assert accepted.status_code == 200
    assert accepted.json()["quantity"] == "8"


@pytest.mark.django_db
def test_force_rejects_a_changed_shortage_impact_and_returns_a_new_proof(
    client,
    recipe,
    production_operator,
    monkeypatch,
):
    impact = {"required": Decimal("10"), "orders": ("ORD-1",)}

    def current_shortage(**kwargs):
        return ProductionOrderShortError(
            work_order_ref="WO-PENDING",
            required=impact["required"],
            requested=Decimal(str(kwargs["quantity"])),
            order_refs=impact["orders"],
        )

    monkeypatch.setattr(
        production_service,
        "_check_linked_order_coverage",
        current_shortage,
    )
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(
        item for item in board["actions"] if item["ref"] == f"plan:{recipe.pk}:{board['selected_date']}:forno"
    )
    url = reverse("api-backstage-wo-plan")
    body = _projected_body(
        board,
        action,
        recipe_id=recipe.pk,
        quantity="8",
        target_date=board["selected_date"],
        position_ref="forno",
        source="manual",
        expected_rev=None,
        idempotency_key="changed-shortage-impact",
    )

    first = client.post(url, body, content_type="application/json")
    first_force = next(item for item in first.json()["error"]["possibilities"] if item["kind"] == "force")
    impact.update(required=Decimal("100"), orders=("ORD-1", "ORD-2"))
    changed = client.post(
        url,
        {
            **body,
            "force": True,
            "reason": "impacto antigo",
            "override_proof": first_force["proof"],
        },
        content_type="application/json",
    )

    assert changed.status_code == 409
    assert changed.json()["error"]["required"] == "100"
    assert not WorkOrder.objects.filter(recipe=recipe).exists()
    second_force = next(item for item in changed.json()["error"]["possibilities"] if item["kind"] == "force")
    assert second_force["proof"] != first_force["proof"]

    accepted = client.post(
        url,
        {
            **body,
            "force": True,
            "reason": "impacto atualizado",
            "override_proof": second_force["proof"],
        },
        content_type="application/json",
    )
    assert accepted.status_code == 200
    assert WorkOrder.objects.filter(recipe=recipe, quantity=Decimal("8")).exists()


@pytest.mark.django_db
def test_shortage_retry_cannot_change_the_attempt_behind_the_same_key(
    client,
    recipe,
    production_operator,
    monkeypatch,
):
    def shortage(**kwargs):
        return ProductionOrderShortError(
            work_order_ref="WO-PENDING",
            required=Decimal("12"),
            requested=Decimal(str(kwargs["quantity"])),
            order_refs=("ORD-1",),
        )

    monkeypatch.setattr(
        production_service,
        "_check_linked_order_coverage",
        shortage,
    )
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(
        item for item in board["actions"] if item["ref"] == f"plan:{recipe.pk}:{board['selected_date']}:forno"
    )
    body = _projected_body(
        board,
        action,
        recipe_id=recipe.pk,
        quantity="5",
        target_date=board["selected_date"],
        position_ref="forno",
        source="manual",
        expected_rev=None,
        idempotency_key="frozen-shortage-attempt",
    )
    url = reverse("api-backstage-wo-plan")

    first = client.post(url, body, content_type="application/json")
    altered = client.post(
        url,
        {**body, "quantity": "10"},
        content_type="application/json",
    )

    assert first.status_code == 409
    assert first.json()["error"]["code"] == "order_shortage"
    assert altered.status_code == 409
    assert altered.json()["error"]["code"] == "conflict"
    assert "outra tentativa" in altered.json()["detail"]
    assert not WorkOrder.objects.filter(recipe=recipe).exists()


@pytest.mark.django_db
def test_non_shortage_mutations_reject_override_proof_as_an_unknown_field(
    client,
    recipe,
    production_operator,
):
    planned = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    started = craft.plan(recipe, 10, date=date.today(), position_ref="other")
    craft.start(started, quantity=10, position_ref="other", expected_rev=started.rev)
    client.force_login(production_operator)

    requests = (
        (
            reverse("api-backstage-wo-start", args=[planned.pk]),
            {"quantity": "10", "expected_rev": planned.rev},
        ),
        (
            reverse("api-backstage-wo-advance", args=[started.pk]),
            {"expected_rev": started.rev},
        ),
        (
            reverse("api-backstage-wo-void", args=[planned.pk]),
            {"reason": "teste", "expected_rev": planned.rev},
        ),
        (
            reverse("api-backstage-wo-oven-arm", args=[started.pk]),
            {"planned_seconds": 600, "expected_rev": started.rev},
        ),
        (
            reverse("api-backstage-wo-oven-conclude", args=[started.pk]),
            {"expected_rev": started.rev},
        ),
    )
    for index, (url, payload) in enumerate(requests):
        response = production_mutation_post(
            client,
            url,
            {
                **payload,
                "idempotency_key": f"strict-override-{index}",
                "override_proof": "not-valid-here",
            },
            content_type="application/json",
        )
        assert response.status_code == 400
        assert response.json()["error"]["issues"][0]["field"] == "override_proof"


@pytest.mark.django_db
def test_string_false_does_not_enable_shortage_override(client, recipe):
    operator = User.objects.create_user("false-force", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("shop", "manage_production"))
    client.force_login(operator)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        {
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "force": "false",
            "expected_rev": None,
            "idempotency_key": "false-is-false",
        },
        content_type="application/json",
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_suggested_action_binds_the_exact_suggested_quantity(
    client,
    recipe,
    monkeypatch,
):
    suggestion_only = User.objects.create_user(
        "suggestion-only",
        password="pw",
        is_staff=True,
    )
    suggestion_only.user_permissions.add(
        _operate_production_perm(),
        _permission("shop", "edit_production_suggested"),
    )
    monkeypatch.setattr(
        "shopman.backstage.projections.production._production_suggestions",
        lambda selected_date: [
            SimpleNamespace(
                recipe=recipe,
                quantity=Decimal("8"),
                basis={"confidence": "high", "sample_size": 7},
            )
        ],
    )
    client.force_login(suggestion_only)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(
        item
        for item in board["actions"]
        if item["ref"] == f"plan_suggested:{recipe.pk}:{board['selected_date']}:forno:8"
    )
    assert action["enabled"] is True
    original = _projected_body(
        board,
        action,
        recipe_id=recipe.pk,
        quantity="8",
        target_date=board["selected_date"],
        position_ref="forno",
        source="suggested",
        expected_rev=None,
        idempotency_key="apply-exact-suggestion",
    )

    inflated = client.post(
        reverse("api-backstage-wo-plan"),
        {**original, "quantity": "9"},
        content_type="application/json",
    )
    assert inflated.status_code == 400
    assert inflated.json()["error"]["issues"][0]["field"] == "action_ref"
    assert not WorkOrder.objects.filter(recipe=recipe).exists()

    accepted = client.post(
        reverse("api-backstage-wo-plan"),
        original,
        content_type="application/json",
    )
    assert accepted.status_code == 200
    work_order = WorkOrder.objects.get(recipe=recipe)
    assert work_order.quantity == Decimal("8")
    assert work_order.source_ref == "formula:suggestion"


@pytest.mark.django_db
def test_mutation_validation_error_is_structured_and_rejects_unknown_fields(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        {
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "strict-input",
            "surprise": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["issues"] == [
        {
            "field": "surprise",
            "code": "invalid",
            "message": "Campo desconhecido.",
        }
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("extra", "field"),
    [
        ({"partition": []}, "partition"),
        (
            {
                "quality": "standard",
                "partition": [{"quantity": "10", "quality_grade_ref": "standard"}],
            },
            "quality",
        ),
        (
            {"partition": [{"quantity": "9", "quality_grade_ref": "standard"}]},
            "partition",
        ),
        (
            {"partition": [{"quantity": "11", "quality_grade_ref": "standard"}]},
            "partition",
        ),
        (
            {"partition": [{"quantity": "10", "loss": True}]},
            "partition.0.quality_defect_ref",
        ),
    ],
)
def test_finish_rejects_invalid_partition_contract(
    client,
    recipe,
    production_operator,
    extra,
    field,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": f"partition-{field}-{len(str(extra))}",
            **extra,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["issues"][0]["field"] == field


@pytest.mark.django_db
def test_plan_requires_the_canonical_projected_position(
    client,
    recipe,
    production_operator,
):
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(
        item for item in board["actions"] if item["ref"] == f"plan:{recipe.pk}:{board['selected_date']}:forno"
    )
    body = _projected_body(
        board,
        action,
        recipe_id=recipe.pk,
        quantity="8",
        target_date=board["selected_date"],
        expected_rev=None,
        idempotency_key="canonical-position",
    )

    missing = client.post(
        reverse("api-backstage-wo-plan"),
        body,
        content_type="application/json",
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["issues"][0]["field"] == "position_ref"

    phantom = client.post(
        reverse("api-backstage-wo-plan"),
        {**body, "position_ref": "default"},
        content_type="application/json",
    )
    assert phantom.status_code == 400
    assert phantom.json()["error"]["issues"][0]["field"] == "action_ref"


# ── Read ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_board_returns_payload(client, recipe, production_operator):
    work_order = craft.plan(recipe, 20, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    response = client.get(reverse("api-backstage-production"))
    assert response.status_code == 200
    board = response.json()["board"]
    assert board["contract_version"] == 1
    assert board["source_revision"].startswith("sha256:")
    assert board["generated_at"] < board["fresh_until"]
    assert (
        datetime.fromisoformat(board["fresh_until"]) - datetime.fromisoformat(board["generated_at"])
    ).total_seconds() == 90
    action = next(item for item in board["actions"] if item["ref"] == f"start:{work_order.pk}")
    proof = action.pop("proof")
    assert proof
    assert action == {
        "ref": f"start:{work_order.pk}",
        "kind": "start",
        "label": "Iniciar fornada",
        "priority": 20,
        "enabled": True,
        "reason": "",
        "method": "POST",
        "href": f"/api/v1/backstage/production/{work_order.pk}/start/",
        "payload_schema": "ProductionStartMutationRequest",
        "expected_rev": work_order.rev,
        "idempotency": {
            "required": True,
            "key_scope": f"production.start:{work_order.pk}",
        },
        "confirmation": {
            "required": False,
            "reason_required": False,
            "title": "",
            "confirm_label": "Confirmar",
        },
        "approval_requirement": None,
        "source_alert_ref": None,
        "source_alert_effect": None,
    }


@pytest.mark.django_db
def test_mutation_requires_complete_fresh_projection_metadata(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    response = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "missing-freshness",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert {issue["field"] for issue in response.json()["error"]["issues"]} == {
        "action_proof",
        "action_ref",
        "contract_version",
        "fresh_until",
        "projection_generated_at",
        "source_revision",
    }
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_projection_proof_is_bound_to_user_surface_and_date(
    client,
    recipe,
    production_operator,
    superuser,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"start:{work_order.pk}")
    metadata = {
        "action_ref": action["ref"],
        "action_proof": action["proof"],
        "projection_generated_at": board["generated_at"],
        "source_revision": board["source_revision"],
        "fresh_until": board["fresh_until"],
        "contract_version": board["contract_version"],
    }

    client.force_login(superuser)
    wrong_user = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "cross-user-proof",
            **metadata,
        },
        content_type="application/json",
    )
    assert wrong_user.status_code == 400
    assert wrong_user.json()["error"]["issues"][0]["field"] == "source_revision"

    client.force_login(production_operator)
    wrong_surface = client.post(
        reverse("api-backstage-wo-advance", args=[work_order.pk]),
        data={
            "expected_rev": work_order.rev,
            "idempotency_key": "cross-surface-proof",
            **metadata,
        },
        content_type="application/json",
    )
    assert wrong_surface.status_code == 400
    assert wrong_surface.json()["error"]["issues"][0]["field"] == "source_revision"

    wrong_date = client.post(
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "10",
            "target_date": date(2099, 1, 1).isoformat(),
            "position_ref": "forno",
            "expected_rev": None,
            "idempotency_key": "cross-date-proof",
            **metadata,
        },
        content_type="application/json",
    )
    assert wrong_date.status_code == 400
    assert wrong_date.json()["error"]["issues"][0]["field"] == "source_revision"

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_board_rejects_invalid_date_instead_of_silently_using_today(client, recipe, production_operator):
    client.force_login(production_operator)
    response = client.get(reverse("api-backstage-production"), {"date": "tomorrow-ish"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["issues"][0]["field"] == "date"


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


@pytest.mark.django_db
def test_authentic_kds_to_qc_projection_actions_complete_exactly_once(
    client,
    recipe,
    production_operator,
):
    """Exercise only action metadata returned by real read projections."""
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(
        work_order,
        quantity=10,
        position_ref="forno",
        expected_rev=work_order.rev,
    )
    client.force_login(production_operator)

    kds = client.get(reverse("api-backstage-production-kds")).json()["kds"]
    advance = next(action for action in kds["actions"] if action["ref"] == f"advance_step:{work_order.pk}")
    advanced = client.post(
        advance["href"],
        _projected_body(
            kds,
            advance,
            expected_rev=advance["expected_rev"],
            idempotency_key="authentic-advance",
        ),
        content_type="application/json",
    )
    assert advanced.status_code == 200

    qc = client.get(reverse("api-backstage-production-qc")).json()["qc"]
    arm = next(action for action in qc["actions"] if action["ref"] == f"oven_arm:{work_order.pk}")
    armed = client.post(
        arm["href"],
        _projected_body(
            qc,
            arm,
            planned_seconds=900,
            expected_rev=arm["expected_rev"],
            idempotency_key="authentic-oven-arm",
        ),
        content_type="application/json",
    )
    assert armed.status_code == 200

    qc = client.get(reverse("api-backstage-production-qc")).json()["qc"]
    conclude = next(action for action in qc["actions"] if action["ref"] == f"oven_conclude:{work_order.pk}")
    concluded = client.post(
        conclude["href"],
        _projected_body(
            qc,
            conclude,
            expected_rev=conclude["expected_rev"],
            idempotency_key="authentic-oven-conclude",
        ),
        content_type="application/json",
    )
    assert concluded.status_code == 200

    qc = client.get(reverse("api-backstage-production-qc")).json()["qc"]
    finish = next(action for action in qc["actions"] if action["ref"] == f"finish:{work_order.pk}")
    finished = client.post(
        finish["href"],
        _projected_body(
            qc,
            finish,
            quantity="10",
            partition=[{"quantity": "10", "quality_grade_ref": "standard"}],
            expected_rev=finish["expected_rev"],
            idempotency_key="authentic-finish",
        ),
        content_type="application/json",
    )
    assert finished.status_code == 200

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.FINISHED
    for kind in (
        WorkOrderEvent.Kind.STEP_ADVANCED,
        WorkOrderEvent.Kind.OVEN_ARMED,
        WorkOrderEvent.Kind.OVEN_CONCLUDED,
        WorkOrderEvent.Kind.FINISHED,
    ):
        assert (
            WorkOrderEvent.objects.filter(
                work_order=work_order,
                kind=kind,
            ).count()
            == 1
        )


# ── Write actions ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_plan_creates_work_order(client, recipe, production_operator):
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "20",
            "target_date": date.today().isoformat(),
            "position_ref": "forno",
            "expected_rev": None,
            "idempotency_key": "plan-create",
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
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[wo.pk]),
        data={"quantity": "10", "expected_rev": wo.rev, "idempotency_key": "start-wo"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["wo_ref"] == wo.ref
    wo.refresh_from_db()
    assert wo.status == wo.Status.STARTED


@pytest.mark.django_db
def test_start_rejects_stale_revision_with_authoritative_current_state(
    client,
    recipe,
    production_operator,
):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[wo.pk]),
        data={
            "quantity": "10",
            "expected_rev": 99,
            "idempotency_key": "stale-start",
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "stale_projection"
    assert error["age_seconds"] >= 0
    assert error["sent_rev"] == 99
    assert error["current_rev"] == 0
    assert error["current"] == {
        "pk": wo.pk,
        "ref": wo.ref,
        "status": "planned",
        "rev": 0,
    }
    assert error["recovery"]["action"] == "refresh"


@pytest.mark.django_db
def test_expired_projection_is_rejected_before_the_mutation(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    generated_at = datetime.fromisoformat("2020-01-01T00:00:00+00:00")
    fresh_until = datetime.fromisoformat("2020-01-01T00:00:30+00:00")
    source_revision = signed_source_revision(
        digest="expired",
        generated_at=generated_at,
        fresh_until=fresh_until,
        projection_kind="board",
        selected_date=date.today().isoformat(),
        subject_ref=f"user:{production_operator.pk}",
    )
    action_ref = f"start:{work_order.pk}"
    action_proof = signed_action_proof(
        action_ref=action_ref,
        action_kind="start",
        href=reverse("api-backstage-wo-start", args=[work_order.pk]),
        expected_rev=work_order.rev,
        source_revision=source_revision,
        projection_generated_at=generated_at,
        fresh_until=fresh_until,
        contract_version=1,
        projection_kind="board",
        selected_date=date.today().isoformat(),
        subject_ref=f"user:{production_operator.pk}",
    )
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "expired-projection-start",
            "projection_generated_at": generated_at.isoformat(),
            "source_revision": source_revision,
            "fresh_until": fresh_until.isoformat(),
            "contract_version": 1,
            "action_ref": action_ref,
            "action_proof": action_proof,
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "stale_projection"
    assert error["age_seconds"] > 0
    assert error["recovery"]["action"] == "refresh"
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_expired_projection_allows_only_the_exact_committed_retry(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    original_rev = work_order.rev
    client_key = "expired-committed-start"
    actor = f"production:{production_operator.username}"
    production_service.apply_start(
        work_order_id=work_order.pk,
        quantity=Decimal("10"),
        actor=actor,
        expected_rev=original_rev,
        idempotency_key=client_key,
    )
    client.force_login(production_operator)

    generated_at = datetime.fromisoformat("2020-01-01T00:00:00+00:00")
    fresh_until = datetime.fromisoformat("2020-01-01T00:00:30+00:00")
    source_revision = signed_source_revision(
        digest="expired-committed",
        generated_at=generated_at,
        fresh_until=fresh_until,
        projection_kind="board",
        selected_date=date.today().isoformat(),
        subject_ref=f"user:{production_operator.pk}",
    )
    action_ref = f"start:{work_order.pk}"
    action_proof = signed_action_proof(
        action_ref=action_ref,
        action_kind="start",
        href=reverse("api-backstage-wo-start", args=[work_order.pk]),
        expected_rev=original_rev,
        source_revision=source_revision,
        projection_generated_at=generated_at,
        fresh_until=fresh_until,
        contract_version=1,
        projection_kind="board",
        selected_date=date.today().isoformat(),
        subject_ref=f"user:{production_operator.pk}",
    )
    body = {
        "quantity": "10",
        "expected_rev": original_rev,
        "idempotency_key": client_key,
        "projection_generated_at": generated_at.isoformat(),
        "source_revision": source_revision,
        "fresh_until": fresh_until.isoformat(),
        "contract_version": 1,
        "action_ref": action_ref,
        "action_proof": action_proof,
    }

    replay = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        body,
        content_type="application/json",
    )
    assert replay.status_code == 200

    stale_new_attempt = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        {**body, "idempotency_key": "expired-new-start"},
        content_type="application/json",
    )
    assert stale_new_attempt.status_code == 409
    assert stale_new_attempt.json()["error"]["code"] == "stale_projection"


@pytest.mark.django_db
def test_void_retry_survives_terminal_visibility_but_a_new_attempt_does_not(
    client,
    recipe,
):
    voider = User.objects.create_user("minimal-voider", password="pw", is_staff=True)
    voider.user_permissions.add(
        _operate_production_perm(),
        _permission("shop", "view_production_planned"),
        _permission("backstage", "void_production"),
    )
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(voider)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"void:{work_order.pk}")
    body = _projected_body(
        board,
        action,
        reason="erro de planejamento",
        expected_rev=action["expected_rev"],
        idempotency_key="void-response-loss",
    )
    url = reverse("api-backstage-wo-void", args=[work_order.pk])

    first = client.post(url, body, content_type="application/json")
    replay = client.post(url, body, content_type="application/json")
    new_attempt = client.post(
        url,
        {**body, "idempotency_key": "void-after-terminal"},
        content_type="application/json",
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert new_attempt.status_code == 403
    assert new_attempt.json()["error"]["capability"] == "can_manage_all"


@pytest.mark.django_db
def test_one_quick_finish_action_proof_cannot_create_multiple_work_orders(
    client,
    recipe,
    production_operator,
    monkeypatch,
):
    monkeypatch.setattr(production_service, "check_finish_materials", lambda work_order: [])
    client.force_login(production_operator)
    qc = client.get(reverse("api-backstage-production-qc")).json()["qc"]
    action = next(item for item in qc["actions"] if item["ref"] == f"quick_finish:{recipe.pk}")
    url = reverse("api-backstage-wo-quick-finish")
    body = _projected_body(
        qc,
        action,
        recipe_id=recipe.pk,
        quantity="10",
        partition=[{"quantity": "10", "quality_grade_ref": "standard"}],
        idempotency_key="quick-action-first",
    )

    first = client.post(url, body, content_type="application/json")
    second = client.post(
        url,
        {**body, "idempotency_key": "quick-action-second"},
        content_type="application/json",
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_one_empty_cell_plan_proof_cannot_create_multiple_work_orders(
    client,
    recipe,
    production_operator,
):
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    plan_action = next(
        action for action in board["actions"] if action["ref"] == f"plan:{recipe.pk}:{board['selected_date']}:forno"
    )
    plan_body = _projected_body(
        board,
        plan_action,
        recipe_id=recipe.pk,
        quantity="10",
        target_date=board["selected_date"],
        position_ref="forno",
        expected_rev=None,
        idempotency_key="empty-cell-first",
    )
    plan_url = reverse("api-backstage-wo-plan")

    first = client.post(plan_url, plan_body, content_type="application/json")
    assert first.status_code == 200
    work_order = WorkOrder.objects.get(ref=first.json()["wo_ref"])

    updated_board = client.get(reverse("api-backstage-production")).json()["board"]
    start_action = next(action for action in updated_board["actions"] if action["ref"] == f"start:{work_order.pk}")
    started = client.post(
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        _projected_body(
            updated_board,
            start_action,
            quantity="10",
            expected_rev=start_action["expected_rev"],
            idempotency_key="empty-cell-start",
        ),
        content_type="application/json",
    )
    assert started.status_code == 200

    reused = client.post(
        plan_url,
        {**plan_body, "idempotency_key": "empty-cell-second"},
        content_type="application/json",
    )

    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "conflict"
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_one_existing_plan_proof_cannot_emit_multiple_confirmation_events(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"plan:{work_order.pk}")
    body = _projected_body(
        board,
        action,
        recipe_id=recipe.pk,
        work_order_id=work_order.pk,
        quantity="10",
        target_date=board["selected_date"],
        position_ref="forno",
        expected_rev=action["expected_rev"],
        idempotency_key="confirm-plan-first",
    )
    url = reverse("api-backstage-wo-plan")

    first = client.post(url, body, content_type="application/json")
    replay = client.post(url, body, content_type="application/json")
    reused = client.post(
        url,
        {**body, "idempotency_key": "confirm-plan-second"},
        content_type="application/json",
    )

    assert first.status_code == replay.status_code == 200
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "conflict"
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.PLANNING_CONFIRMED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_forged_projection_revision_is_rejected(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    projection = client.get(reverse("api-backstage-production")).json()["board"]

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "forged-projection-start",
            "projection_generated_at": projection["generated_at"],
            "source_revision": "sha256:forged:signature",
            "fresh_until": projection["fresh_until"],
            "contract_version": projection["contract_version"],
            "action_ref": f"start:{work_order.pk}",
            "action_proof": "forged-source-before-action-proof-validation",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["issues"][0]["field"] == "source_revision"
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_future_projection_timestamp_is_rejected_even_with_a_valid_signature(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    generated_at = datetime.fromisoformat("2099-01-01T00:00:00+00:00")
    fresh_until = datetime.fromisoformat("2099-01-01T00:00:30+00:00")

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "future-projection-start",
            "projection_generated_at": generated_at.isoformat(),
            "source_revision": signed_source_revision(
                digest="future",
                generated_at=generated_at,
                fresh_until=fresh_until,
                projection_kind="board",
                selected_date=date.today().isoformat(),
                subject_ref=f"user:{production_operator.pk}",
            ),
            "fresh_until": fresh_until.isoformat(),
            "contract_version": 1,
            "action_ref": f"start:{work_order.pk}",
            "action_proof": "future-before-action-proof-validation",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    issues = response.json()["error"]["issues"]
    assert any(issue["field"] == "projection_generated_at" for issue in issues)
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_domain_validation_error_uses_the_closed_error_envelope(
    client,
    recipe,
    production_operator,
    monkeypatch,
):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)

    def invalid_step(**kwargs):
        from shopman.backstage.services.exceptions import ProductionError

        raise ProductionError("Receita sem passos configurados.")

    monkeypatch.setattr(
        "shopman.backstage.api.operations.production_service.apply_advance_step",
        invalid_step,
    )
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data={
            "expected_rev": wo.rev,
            "idempotency_key": "invalid-step-contract",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "validation_error",
        "issues": [
            {
                "field": "non_field_errors",
                "code": "invalid",
                "message": "Receita sem passos configurados.",
            }
        ],
    }


@pytest.mark.django_db
def test_start_retry_with_same_attempt_is_exactly_once(
    client,
    recipe,
    production_operator,
):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    payload = {
        "quantity": "10",
        "expected_rev": wo.rev,
        "idempotency_key": "start-retry",
    }
    client.force_login(production_operator)

    first = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[wo.pk]),
        data=payload,
        content_type="application/json",
    )
    second = production_mutation_post(
        client,
        reverse("api-backstage-wo-start", args=[wo.pk]),
        data=payload,
        content_type="application/json",
    )

    assert first.status_code == second.status_code == 200
    wo.refresh_from_db()
    assert wo.rev == 1
    assert (
        WorkOrderEvent.objects.filter(
            work_order=wo,
            kind=WorkOrderEvent.Kind.STARTED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_advance_step_increments_pointer(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data={"expected_rev": wo.rev, "idempotency_key": "advance-wo"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["step_index"] == 1


@pytest.mark.django_db
def test_advance_step_retry_is_append_only_and_exactly_once(
    client,
    recipe,
    production_operator,
):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    payload = {"expected_rev": wo.rev, "idempotency_key": "advance-retry"}
    client.force_login(production_operator)

    first = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data=payload,
        content_type="application/json",
    )
    second = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data=payload,
        content_type="application/json",
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["step_index"] == second.json()["step_index"] == 1
    wo.refresh_from_db()
    assert wo.rev == 2
    events = WorkOrderEvent.objects.filter(
        work_order=wo,
        kind=WorkOrderEvent.Kind.STEP_ADVANCED,
    )
    assert events.count() == 1
    assert events.get().payload["step_index"] == 1


@pytest.mark.django_db
def test_advance_step_replay_keeps_original_result_after_later_advance(
    client,
    recipe,
    production_operator,
):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    first_payload = {"expected_rev": wo.rev, "idempotency_key": "advance-a"}
    client.force_login(production_operator)

    first = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data=first_payload,
        content_type="application/json",
    )
    wo.refresh_from_db()
    second = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data={"expected_rev": wo.rev, "idempotency_key": "advance-b"},
        content_type="application/json",
    )
    replay = production_mutation_post(
        client,
        reverse("api-backstage-wo-advance", args=[wo.pk]),
        data=first_payload,
        content_type="application/json",
    )

    assert first.json()["step_index"] == 1
    assert second.json()["step_index"] == 2
    assert replay.status_code == 200
    assert replay.json()["step_index"] == 1
    assert replay.json()["current"]["rev"] == second.json()["current"]["rev"]


@pytest.mark.django_db
def test_finish_started_work_order(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(wo, quantity=10, position_ref="forno", expected_rev=0)
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[wo.pk]),
        data={
            "quantity": "10",
            "partition": [
                {"quantity": "9", "quality_grade_ref": "standard"},
                {"quantity": "1", "quality_defect_ref": "misshapen", "loss": True},
            ],
            "expected_rev": wo.rev,
            "idempotency_key": "finish-wo",
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    wo.refresh_from_db()
    assert wo.status == wo.Status.FINISHED


@pytest.mark.django_db
@pytest.mark.parametrize(
    "partition",
    (
        None,
        [{"quantity": "9", "quality_grade_ref": "standard"}],
    ),
)
def test_finish_rejects_unclassified_yield_deficit(
    client,
    recipe,
    production_operator,
    partition,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=10, position_ref="forno", expected_rev=work_order.rev)
    work_order.refresh_from_db()
    client.force_login(production_operator)
    payload = {
        "quantity": "9",
        "expected_rev": work_order.rev,
        "idempotency_key": f"unclassified-deficit-{partition is not None}",
    }
    if partition is not None:
        payload["partition"] = partition

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[work_order.pk]),
        data=payload,
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["issues"][0]["field"] == "quantity"
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


@pytest.mark.django_db
def test_forged_finish_overshoot_requires_audited_confirmation(
    client,
    recipe,
    production_operator,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    craft.start(work_order, quantity=10, position_ref="forno", expected_rev=0)
    work_order.refresh_from_db()
    client.force_login(production_operator)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[work_order.pk]),
        data={
            "quantity": "12",
            "partition": [{"quantity": "12", "quality_grade_ref": "standard"}],
            "expected_rev": work_order.rev,
            "idempotency_key": "forged-overshoot",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert "Confirme explicitamente" in response.json()["detail"]
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


@pytest.mark.django_db
def test_quick_finish_plans_and_finishes(client, recipe, production_operator, position):
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-quick-finish"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "5",
            "position_id": position.pk,
            "idempotency_key": "quick-finish-wo",
        },
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
        "idempotency_key": "quiosque-gesto-abc123",
    }

    primeira = production_mutation_post(
        client,
        reverse("api-backstage-wo-quick-finish"),
        data=corpo,
        content_type="application/json",
    )
    assert primeira.status_code == 200

    segunda = production_mutation_post(
        client,
        reverse("api-backstage-wo-quick-finish"),
        data=corpo,
        content_type="application/json",
    )
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

    primeira = production_mutation_post(
        client,
        reverse("api-backstage-wo-quick-finish"),
        data={**base, "idempotency_key": "gesto-1"},
        content_type="application/json",
    )
    segunda = production_mutation_post(
        client,
        reverse("api-backstage-wo-quick-finish"),
        data={**base, "idempotency_key": "gesto-2"},
        content_type="application/json",
    )

    assert primeira.status_code == 200 and segunda.status_code == 200, (
        primeira.json(),
        segunda.json(),
    )
    assert primeira.json()["wo_ref"] != segunda.json()["wo_ref"]
    assert WorkOrder.objects.filter(recipe=recipe).count() == 2


@pytest.mark.django_db
def test_quick_finish_invalid_recipe_is_a_client_error(client, production_operator):
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-quick-finish"),
        data={
            "recipe_id": 999_999,
            "quantity": "5",
            "idempotency_key": "quick-invalid-recipe",
        },
        content_type="application/json",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.django_db
def test_missing_work_order_is_typed_not_found_for_every_action(
    client,
    production_operator,
):
    client.force_login(production_operator)
    missing_id = 999_999
    actions = (
        (
            "api-backstage-wo-start",
            {
                "quantity": "5",
                "expected_rev": 0,
                "idempotency_key": "missing-start",
            },
        ),
        (
            "api-backstage-wo-finish",
            {
                "quantity": "5",
                "expected_rev": 0,
                "idempotency_key": "missing-finish",
            },
        ),
        (
            "api-backstage-wo-advance",
            {"expected_rev": 0, "idempotency_key": "missing-advance"},
        ),
        (
            "api-backstage-wo-void",
            {
                "reason": "alvo inexistente",
                "expected_rev": 0,
                "idempotency_key": "missing-void",
            },
        ),
        (
            "api-backstage-wo-oven-arm",
            {
                "planned_seconds": 600,
                "expected_rev": 0,
                "idempotency_key": "missing-oven-arm",
            },
        ),
        (
            "api-backstage-wo-oven-conclude",
            {"expected_rev": 0, "idempotency_key": "missing-oven-conclude"},
        ),
    )

    for route_name, body in actions:
        response = production_mutation_post(
            client,
            reverse(route_name, args=[missing_id]),
            data=body,
            content_type="application/json",
        )
        assert response.status_code == 404, route_name
        assert response.json()["error"] == {
            "code": "not_found",
            "resource": "work_order",
            "identifier": str(missing_id),
        }


@pytest.mark.django_db
def test_void_work_order(client, recipe, production_operator):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="forno")
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-void", args=[wo.pk]),
        data={"reason": "teste", "expected_rev": wo.rev, "idempotency_key": "void-wo"},
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
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[wo.pk]),
        data={
            "quantity": "10",
            "expected_rev": wo.rev,
            "idempotency_key": "finish-shortage",
        },
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
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "8",
            "target_date": date.today().isoformat(),
            "position_ref": "forno",
            "expected_rev": None,
            "idempotency_key": "plan-shortage",
        },
        content_type="application/json",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "order_shortage"
    assert error["required"] == "12"
    assert error["order_refs"] == ["ORD-1", "ORD-2"]


@pytest.mark.django_db
def test_non_overridable_order_shortage_never_offers_force(
    client,
    recipe,
    production_operator,
    monkeypatch,
):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="forno")

    def block_finish(**kwargs):
        raise ProductionOrderShortError(
            work_order_ref=work_order.ref,
            required=Decimal("12"),
            requested=Decimal("8"),
            order_refs=("ORD-1",),
            allow_override=False,
        )

    monkeypatch.setattr(
        "shopman.backstage.api.operations.production_service.apply_finish",
        block_finish,
    )
    client.force_login(production_operator)
    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-finish", args=[work_order.pk]),
        data={
            "quantity": "10",
            "expected_rev": work_order.rev,
            "idempotency_key": "non-overridable-order-shortage",
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    assert [possibility["kind"] for possibility in response.json()["error"]["possibilities"]] == ["retry"]
