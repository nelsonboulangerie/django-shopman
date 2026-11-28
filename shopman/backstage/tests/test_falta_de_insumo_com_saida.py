"""Falta de insumo com saída (WP-F11; P1-14, P1-23, P1-24; #2389 a).

O que se mede aqui, pelos caminhos reais (estoque no Stockman, guarda pelo
``INVENTORY_BACKEND`` da casa, baixa pelo receiver do Craftsman):

- a guarda e a baixa usam a MESMA quantidade, a bruta: com aproveitamento menor
  que 1, a guarda que conferia a líquida passava e a baixa recusava com "o
  estoque falhou", sem nome (P1-23);
- na abertura a falta é aviso, não trava: a recusa diz o que falta e oferece
  "Pedir no Compras" e "Abrir assim mesmo"; a confirmação do mesmo impacto abre;
- no fechamento, a saída é a assinatura de quem pode autorizar (Gerente ou Dono,
  da lista, com o próprio PIN; decisão 3 do dono, D-042), nunca texto livre.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderEvent
from shopman.doorman.models import PinCredential
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, PositionKind

from shopman.backstage.services import production
from shopman.backstage.services.production import ProductionStockShortError

pytestmark = pytest.mark.django_db

BUTTER = "INS-MANTEIGA-F11"
ACTOR = "production:cozinha"


def _permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@pytest.fixture
def producao(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja F11")
    Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True}
    )
    position, _ = Position.objects.get_or_create(
        ref="producao",
        defaults={"name": "Produção", "kind": PositionKind.PHYSICAL, "is_saleable": False, "is_default": True},
    )
    return position


@pytest.fixture
def ficha(producao):
    """Croissant: 0,9 kg de manteiga líquida por 10, aproveitamento 0,9 (bruta 1 kg)."""
    recipe = Recipe.objects.create(
        ref="croissant-f11", name="Croissant F11", output_sku="CROISSANT-F11", batch_size=Decimal("10")
    )
    RecipeItem.objects.create(
        recipe=recipe,
        input_sku=BUTTER,
        quantity=Decimal("0.9"),
        usable_factor=Decimal("0.9"),
        unit="kg",
    )
    return recipe


def _manteiga(quantity: str, producao) -> None:
    stock.receive(Decimal(quantity), BUTTER, position=producao, reason="entrada do Compras", kind=Move.Kind.BUY)


def _planejar(ficha, qty: int = 10) -> WorkOrder:
    return craft.plan(ficha, qty, date=date.today(), position_ref="producao")


def _abrir(work_order, *, qty="10", key="start-f11", **kwargs):
    work_order.refresh_from_db()
    return production.apply_start(
        work_order_id=work_order.pk,
        quantity=qty,
        actor=ACTOR,
        expected_rev=work_order.rev,
        idempotency_key=key,
        **kwargs,
    )


def _fechar(work_order, *, qty="10", key="finish-f11", **kwargs):
    work_order.refresh_from_db()
    return production.apply_finish(
        work_order_id=work_order.pk,
        quantity=qty,
        actor=ACTOR,
        expected_rev=work_order.rev,
        idempotency_key=key,
        **kwargs,
    )


def _consumido(work_order) -> Decimal:
    return -sum(
        (move.delta for move in Move.objects.filter(quant__sku=BUTTER, kind=Move.Kind.MAKE)),
        Decimal("0"),
    )


# ── A régua: guarda e baixa pela bruta (P1-23) ───────────────────────────────


def test_a_guarda_confere_a_bruta_que_a_baixa_consome(ficha, producao):
    """0,95 kg cabe na líquida (0,9) e falta na bruta (1,0): a guarda tem de ver."""
    _manteiga("0.95", producao)
    work_order = _planejar(ficha)

    with pytest.raises(ProductionStockShortError) as aviso:
        _abrir(work_order)

    [item] = aviso.value.missing
    assert item.sku == BUTTER
    assert item.needed == Decimal("1.000")
    assert item.available == Decimal("0.95")
    assert item.shortage == Decimal("0.050")


def test_com_a_bruta_no_estoque_a_guarda_passa_e_a_baixa_tira_a_mesma_quantidade(ficha, producao):
    _manteiga("1", producao)
    work_order = _planejar(ficha)

    _abrir(work_order)
    assert production.check_finish_materials(WorkOrder.objects.get(pk=work_order.pk)) == []
    _fechar(work_order)

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.FINISHED
    assert _consumido(work_order) == Decimal("1.000")


def test_a_sugestao_confere_pela_bruta(ficha, producao):
    """A checagem da sugestão no planejamento usa a mesma régua da baixa."""
    from types import SimpleNamespace

    from shopman.backstage.projections.production import _suggestion_material_checks

    _manteiga("0.95", producao)
    suggestion = SimpleNamespace(recipe=ficha, quantity=Decimal("10"))
    checks = _suggestion_material_checks([suggestion], (ficha,), skip_skus=set())

    shortages, fits = checks[ficha.output_sku]
    assert [item.sku for item in shortages] == [BUTTER]
    assert fits == "9"


# ── Abertura: aviso, não trava (P1-14) ───────────────────────────────────────


def test_a_abertura_avisa_a_falta_e_abre_com_a_confirmacao_do_mesmo_impacto(ficha, producao):
    _manteiga("0.7", producao)
    work_order = _planejar(ficha)

    with pytest.raises(ProductionStockShortError) as aviso:
        _abrir(work_order)
    assert aviso.value.stage == "start"
    assert aviso.value.missing[0].shortage == Decimal("0.300")
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED

    _abrir(work_order, approved_material_shortage=production.production_shortage_snapshot(aviso.value))

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED
    registro = WorkOrderEvent.objects.get(work_order=work_order, kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN)
    assert registro.payload["action"] == "start"
    assert registro.payload["impact"]["missing"][0]["shortage"] == "0.3"


def test_abrir_assim_mesmo_nao_autoriza_a_baixa_do_fechamento(ficha, producao):
    """O aviso aceito na abertura não é a assinatura do fechamento."""
    _manteiga("0.7", producao)
    work_order = _planejar(ficha)
    with pytest.raises(ProductionStockShortError) as aviso:
        _abrir(work_order)
    _abrir(work_order, approved_material_shortage=production.production_shortage_snapshot(aviso.value))

    with pytest.raises(ProductionStockShortError) as trava:
        _fechar(work_order)
    assert trava.value.stage == "finish"
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


def test_a_confirmacao_de_outra_falta_nao_abre(ficha, producao):
    _manteiga("0.7", producao)
    work_order = _planejar(ficha)
    with pytest.raises(ProductionStockShortError) as aviso:
        _abrir(work_order)
    lida = production.production_shortage_snapshot(aviso.value)

    # O estoque mudou entre a leitura e a confirmação: a falta agora é outra.
    _manteiga("0.1", producao)
    with pytest.raises(ProductionStockShortError) as nova:
        _abrir(work_order, approved_material_shortage=lida)
    assert nova.value.missing[0].shortage == Decimal("0.200")


# ── Fechamento: assinatura da lista com o próprio PIN (P1-24, D-042) ─────────


@pytest.fixture
def cozinha(db):
    """Quem fecha o lote: opera a produção, NÃO pode autorizar falta."""
    from shopman.backstage.tests.production_grants import grant_production_operator

    user = User.objects.create_user("diofer-f11", password="pw", is_staff=True)
    return grant_production_operator(user)


@pytest.fixture
def gerente(db):
    user = User.objects.create_user("joyce-f11", password="pw", is_staff=True, first_name="Joyce")
    user.user_permissions.add(_permission("backstage", "override_production_shortage"))
    PinCredential.set_for(user, "2468")
    return User.objects.get(pk=user.pk)


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


def _lote_aberto_com_falta(ficha, producao) -> WorkOrder:
    _manteiga("0.7", producao)
    work_order = _planejar(ficha)
    with pytest.raises(ProductionStockShortError) as aviso:
        _abrir(work_order)
    _abrir(work_order, approved_material_shortage=production.production_shortage_snapshot(aviso.value))
    work_order.refresh_from_db()
    return work_order


def _finish_body(client, work_order, key: str) -> tuple[str, dict]:
    qc = client.get(reverse("api-backstage-production-qc")).json()["qc"]
    action = next(item for item in qc["actions"] if item["ref"] == f"finish:{work_order.pk}")
    body = _projected_body(qc, action, quantity="10", expected_rev=action["expected_rev"], idempotency_key=key)
    return reverse("api-backstage-wo-finish", args=[work_order.pk]), body


def test_o_envelope_do_fechamento_traz_a_lista_de_quem_autoriza(client, ficha, producao, cozinha, gerente):
    work_order = _lote_aberto_com_falta(ficha, producao)
    client.force_login(cozinha)
    url, body = _finish_body(client, work_order, "finish-envelope-f11")

    refused = client.post(url, body, content_type="application/json")

    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "material_shortage"
    assert error["stage"] == "finish"
    assert error["missing"][0]["shortage"] == "0.3"
    assert error["missing"][0]["shortage_display"] == "300 g"
    assert [person["username"] for person in error["authorizers"]] == ["joyce-f11"]
    assert error["authorizers"][0]["name"] == "Joyce"
    force = next(item for item in error["possibilities"] if item["kind"] == "force")
    assert force["label"] == "Fechar com autorização"
    assert force["enabled"] is True
    assert force["proof"]


def test_a_gerente_assina_com_o_proprio_pin_e_o_lote_fecha(client, ficha, producao, cozinha, gerente):
    work_order = _lote_aberto_com_falta(ficha, producao)
    client.force_login(cozinha)
    url, body = _finish_body(client, work_order, "finish-signed-f11")
    refused = client.post(url, body, content_type="application/json")
    proof = next(item for item in refused.json()["error"]["possibilities"] if item["kind"] == "force")["proof"]
    sign_url = reverse("api-backstage-production-shortage-authorization")

    wrong = client.post(
        sign_url, {"override_proof": proof, "username": "joyce-f11", "pin": "1111"}, content_type="application/json"
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["issues"][0]["field"] == "pin"
    # A frase do problema chega à tela de quem autoriza, não "corrija os campos".
    assert wrong.json()["detail"].startswith("PIN incorreto.")

    signed = client.post(
        sign_url, {"override_proof": proof, "username": "joyce-f11", "pin": "2468"}, content_type="application/json"
    )
    assert signed.status_code == 200
    assert signed.json()["authorizer_name"] == "Joyce"

    closed = client.post(
        url,
        {**body, "force": True, "reason": "texto livre ignorado", "override_proof": signed.json()["override_proof"]},
        content_type="application/json",
    )

    assert closed.status_code == 200, closed.json()
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.FINISHED
    registro = WorkOrderEvent.objects.get(
        work_order=work_order, kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN, payload__action="finish"
    )
    assert registro.payload["authorized_by"] == "joyce-f11"
    assert registro.payload["reason"] == "Autorizado por Joyce, com PIN."
    # A baixa levou o que havia (0,7) e a falta assinada (0,3) cobriu o resto.
    assert _consumido(work_order) == Decimal("0.7")


def test_quem_nao_pode_autorizar_nao_assina(client, ficha, producao, cozinha):
    work_order = _lote_aberto_com_falta(ficha, producao)
    PinCredential.set_for(cozinha, "1357")
    client.force_login(cozinha)
    url, body = _finish_body(client, work_order, "finish-unsigned-f11")
    refused = client.post(url, body, content_type="application/json")
    error = refused.json()["error"]
    assert error["authorizers"] == []
    assert not any(item["kind"] == "force" and item["enabled"] for item in error["possibilities"])

    sign = client.post(
        reverse("api-backstage-production-shortage-authorization"),
        {"override_proof": "forjada", "username": cozinha.username, "pin": "1357"},
        content_type="application/json",
    )
    assert sign.status_code == 400


def test_a_abertura_pela_api_oferece_o_compras_e_abrir_assim_mesmo(client, ficha, producao, cozinha, monkeypatch):
    monkeypatch.setattr("shopman.backstage.api.operations.purchase_surface_url", lambda user: "https://compras.example")
    _manteiga("0.7", producao)
    work_order = _planejar(ficha)
    client.force_login(cozinha)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"start:{work_order.pk}")
    body = _projected_body(
        board, action, quantity="10", expected_rev=action["expected_rev"], idempotency_key="start-api-f11"
    )
    url = reverse("api-backstage-wo-start", args=[work_order.pk])

    aviso = client.post(url, body, content_type="application/json")

    assert aviso.status_code == 409
    error = aviso.json()["error"]
    assert error["stage"] == "start"
    assert error["authorizers"] == []
    kinds = {item["kind"]: item for item in error["possibilities"]}
    assert kinds["purchase"]["label"] == "Pedir no Compras"
    assert kinds["purchase"]["href"] == "https://compras.example"
    assert kinds["confirm"]["label"] == "Abrir assim mesmo"
    assert "force" not in kinds

    aberto = client.post(
        url, {**body, "material_shortage_proof": kinds["confirm"]["proof"]}, content_type="application/json"
    )
    assert aberto.status_code == 200, aberto.json()
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


def test_o_que_a_casa_produz_nao_se_pede_ao_compras(client, producao, cozinha, monkeypatch):
    """A massa que falta é produzida aqui: o envelope não oferece o Compras."""
    monkeypatch.setattr("shopman.backstage.api.operations.purchase_surface_url", lambda user: "https://compras.example")
    Recipe.objects.create(ref="massa-f11", name="Massa F11", output_sku="MASSA-F11", batch_size=Decimal("1"))
    pao = Recipe.objects.create(ref="pao-f11", name="Pão F11", output_sku="PAO-F11", batch_size=Decimal("1"))
    RecipeItem.objects.create(recipe=pao, input_sku="MASSA-F11", quantity=Decimal("100"), unit="g")
    work_order = craft.plan(pao, 10, date=date.today(), position_ref="producao")
    client.force_login(cozinha)
    board = client.get(reverse("api-backstage-production")).json()["board"]
    action = next(item for item in board["actions"] if item["ref"] == f"start:{work_order.pk}")
    body = _projected_body(
        board, action, quantity="10", expected_rev=action["expected_rev"], idempotency_key="start-massa-f11"
    )

    aviso = client.post(reverse("api-backstage-wo-start", args=[work_order.pk]), body, content_type="application/json")

    error = aviso.json()["error"]
    assert error["missing"][0]["produced_here"] is True
    assert error["missing"][0]["shortage_display"] == "1000 g"
    assert "purchase" not in {item["kind"] for item in error["possibilities"]}
    assert "confirm" in {item["kind"] for item in error["possibilities"]}
