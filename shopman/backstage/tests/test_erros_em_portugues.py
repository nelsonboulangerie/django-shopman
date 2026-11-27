"""Erros que falam português (WP-F14; P1-13, P2-19).

Nenhuma recusa da Produção chega ao operador com código do Core, inglês ou jargão:

- cada código do Craftsman que a Produção encontra (``COMMITTED_HOLDS``,
  ``INSUFFICIENT_MATERIALS``, ``DOWNSTREAM_DEFICIT``) tem a frase da casa; o que
  ainda não tem tradução sai com uma frase de saída, e o código vai para o log;
- ``CraftError`` e ``StockError`` nunca viram 500 em ``authorize_formula_deviation``
  e ``register_old_dough``;
- as duas travas de redução do plano (a dos pedidos ligados ao lote e a do Core)
  viram uma mensagem só, e "Salvar com justificativa" some onde o Core recusa de
  qualquer jeito;
- erro de campo sai no dialeto da casa (``{detail, field, errors}``).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman.exceptions import StockError
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services import production as production_service
from shopman.backstage.services.exceptions import ProductionError
from shopman.backstage.services.production import (
    ProductionOrderShortError,
    _operator_error,
)
from shopman.backstage.tests.support import production_mutation_post

pytestmark = pytest.mark.django_db

PLANO_ABAIXO = "Há 12 un. encomendadas para este dia. O plano não pode ficar abaixo disso."
#: Código do Core entre colchetes ou frase do Core em inglês: nunca na tela.
CODIGO_OU_INGLES = re.compile(r"\[[A-Z_]+\]|Insufficient|Quantity|Reducing|work order", re.IGNORECASE)


def _fala_portugues(message: str) -> None:
    assert message
    assert not CODIGO_OU_INGLES.search(message), message
    assert "—" not in message, message


# ── Os códigos do Core ──────────────────────────────────────────────────────


def test_committed_holds_vira_a_frase_do_plano():
    translated = _operator_error(
        CraftError("COMMITTED_HOLDS", committed=12.0, requested=10.0, message="Há 12.000 unidades comprometidas")
    )

    assert isinstance(translated, ProductionError)
    assert str(translated) == PLANO_ABAIXO


def test_insufficient_materials_diz_o_insumo_pelo_nome():
    from shopman.buyman.models import Material

    Material.objects.create(sku="INS-MANTEIGA-F14", name="Manteiga", unit="kg")

    translated = _operator_error(
        CraftError("INSUFFICIENT_MATERIALS", shortages=[{"sku": "INS-MANTEIGA-F14", "needed": 2.0, "available": 1.0}])
    )

    _fala_portugues(str(translated))
    assert "Manteiga" in str(translated)
    assert "INS-MANTEIGA-F14" not in str(translated)


def test_downstream_deficit_diz_quais_lotes_ficam_sem(db):
    position = Position.objects.create(ref="massa-f14", name="Massa", kind=PositionKind.PHYSICAL, is_default=True)
    croissant = Recipe.objects.create(
        ref="croissant-f14", name="Croissant F14", output_sku="CROISSANT-F14", batch_size=Decimal("10")
    )
    downstream = WorkOrder.objects.create(
        recipe=croissant, output_sku="CROISSANT-F14", quantity=Decimal("10"), position_ref=position.ref
    )

    translated = _operator_error(
        CraftError("DOWNSTREAM_DEFICIT", deficit=[{"wo_ref": downstream.ref, "sku": "MASSA-F14", "shortage": 2.0}])
    )

    _fala_portugues(str(translated))
    assert "Croissant F14" in str(translated)


def test_codigo_sem_traducao_sai_com_frase_de_saida_e_vai_para_o_log(monkeypatch):
    logged: list[tuple] = []
    monkeypatch.setattr(production_service.logger, "warning", lambda *args, **kwargs: logged.append(args))

    translated = _operator_error(CraftError("INVALID_PAYLOAD"))

    _fala_portugues(str(translated))
    assert "Atualize o painel" in str(translated)
    assert any("INVALID_PAYLOAD" in args for args in logged)


def test_stock_error_sem_codigo_entre_colchetes():
    translated = _operator_error(StockError("INSUFFICIENT_QUANTITY", available=Decimal("1")))

    _fala_portugues(str(translated))
    assert "quantidade insuficiente no estoque" in str(translated)


# ── Nunca 500 nos dois serviços que não traduziam ───────────────────────────


@pytest.mark.parametrize(
    "failure",
    [CraftError("IDEMPOTENCY_CONFLICT"), StockError("INSUFFICIENT_QUANTITY"), CraftError("INVALID_PAYLOAD")],
    ids=["craft-conflito", "estoque", "craft-sem-traducao"],
)
def test_massa_velha_nunca_vira_500(monkeypatch, failure):
    def boom(*args, **kwargs):
        raise failure

    monkeypatch.setattr(production_service, "_positive_quantity", boom)

    with pytest.raises(ProductionError) as refused:
        production_service.register_old_dough(
            work_order_id=1,
            quantity="100",
            unit="g",
            expiry_date=date.today(),
            actor="production:cozinha",
            idempotency_key="old-dough-f14",
        )
    _fala_portugues(str(refused.value))


@pytest.mark.parametrize(
    "failure",
    [CraftError("TERMINAL_STATUS"), StockError("CONCURRENT_MODIFICATION"), CraftError("BOM_CYCLE")],
    ids=["craft-fechado", "estoque", "craft-receita"],
)
def test_desvio_de_receita_nunca_vira_500(monkeypatch, failure):
    def boom(*args, **kwargs):
        raise failure

    monkeypatch.setattr(production_service, "_positive_quantity", boom)

    with pytest.raises(ProductionError) as refused:
        production_service.authorize_formula_deviation(
            work_order_id=1,
            ingredient_ref="farinha",
            actual_quantity="100",
            reason="Farinha mais seca hoje.",
            actor="production:cozinha",
            expected_rev=1,
            idempotency_key="deviation-f14",
        )
    _fala_portugues(str(refused.value))


# ── As duas travas de redução numa mensagem só (P1-13) ──────────────────────


@pytest.fixture
def plano(db, monkeypatch):
    """Um lote de hoje com 20 planejados e 12 encomendados para o dia (régua do Core)."""
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja F14")
    Position.objects.filter(is_default=True).update(is_default=False)
    Position.objects.create(ref="forno-f14", name="Forno", kind=PositionKind.PHYSICAL, is_default=True)
    Position.objects.get_or_create(ref="vitrine", defaults={"name": "Vitrine", "is_saleable": True})
    recipe = Recipe.objects.create(ref="brioche-f14", name="Brioche", output_sku="BRIOCHE-F14", batch_size=Decimal("10"))
    production_service.apply_planned(
        recipe_id=recipe.pk,
        quantity=Decimal("20"),
        target_date_value=timezone.localdate().isoformat(),
        position_ref="",
        operator_ref="",
        force=False,
        actor="production:cozinha",
        idempotency_key="plan-f14-setup",
    )
    monkeypatch.setattr(
        "shopman.shop.adapters.demand.LedgerAwareDemandBackend.committed",
        # Como o banco devolve: três casas. O envelope e a frase saem "12".
        lambda self, sku, target_date: Decimal("12.000") if sku == "BRIOCHE-F14" else Decimal("0"),
    )
    work_order = WorkOrder.objects.get(recipe=recipe, status=WorkOrder.Status.PLANNED)
    return recipe, work_order


def _reduzir(recipe, work_order, *, quantity="10", force=False, key="plan-f14-reduce", proof=""):
    return production_service.apply_planned(
        recipe_id=recipe.pk,
        quantity=Decimal(quantity),
        target_date_value=timezone.localdate().isoformat(),
        position_ref="",
        operator_ref="",
        force=force,
        reason="Pedido do gestor." if force else "",
        actor="production:cozinha",
        expected_rev=work_order.rev,
        idempotency_key=key,
        projected_action_proof=proof,
    )


def test_reduzir_abaixo_do_encomendado_diz_a_frase_da_casa_e_nao_oferece_forcar(plano):
    recipe, work_order = plano

    with pytest.raises(ProductionOrderShortError) as refused:
        _reduzir(recipe, work_order)

    assert str(refused.value) == PLANO_ABAIXO
    assert refused.value.allow_override is False
    assert refused.value.required == Decimal("12")


def test_forcar_nao_passa_por_cima_da_trava_do_core(plano):
    """Antes, o "Salvar com justificativa" levava ao "[COMMITTED_HOLDS] …" do Core."""
    recipe, work_order = plano

    with pytest.raises(ProductionOrderShortError) as refused:
        _reduzir(recipe, work_order, force=True, key="plan-f14-force")

    assert str(refused.value) == PLANO_ABAIXO
    work_order.refresh_from_db()
    assert work_order.quantity == Decimal("20")


def test_revisar_quantidade_aceita_um_numero_novo(plano):
    recipe, work_order = plano
    with pytest.raises(ProductionOrderShortError):
        _reduzir(recipe, work_order)

    _reduzir(recipe, work_order, quantity="12", key="plan-f14-review")

    work_order.refresh_from_db()
    assert work_order.quantity == Decimal("12")


def test_a_recusa_solta_a_acao_projetada_para_a_tentativa_revisada(plano):
    """A posse da ação projetada é gravada à parte; presa, recusava o número revisado."""
    recipe, work_order = plano
    with pytest.raises(ProductionOrderShortError):
        _reduzir(recipe, work_order, key="plan-f14-first", proof="prova-da-acao")

    _reduzir(recipe, work_order, quantity="12", key="plan-f14-revised", proof="prova-da-acao")

    work_order.refresh_from_db()
    assert work_order.quantity == Decimal("12")


def test_a_posse_da_acao_continua_valendo_depois_de_gravar(plano):
    """Soltar é só na recusa: a ação que gravou não serve a outra tentativa."""
    from shopman.backstage.services.exceptions import ProductionConflict

    recipe, work_order = plano
    _reduzir(recipe, work_order, quantity="14", key="plan-f14-saved", proof="prova-gravada")
    work_order.refresh_from_db()

    with pytest.raises(ProductionConflict):
        _reduzir(recipe, work_order, quantity="15", key="plan-f14-other", proof="prova-gravada")


def test_forcar_depois_da_recusa_retoma_a_posse(plano, monkeypatch):
    """A dona que volta com a mesma chave retoma a ação: depois de gravar, outra
    chave não a usa mais."""
    from shopman.backstage.services.exceptions import ProductionConflict

    recipe, work_order = plano
    monkeypatch.setattr(production_service, "_committed_holds_refusal", lambda **kwargs: None)
    monkeypatch.setattr(
        production_service,
        "_check_linked_order_coverage",
        lambda **kwargs: ProductionOrderShortError(
            work_order_ref=work_order.ref,
            required=Decimal("20"),
            requested=Decimal(str(kwargs["quantity"])),
            order_refs=("ORD-F14",),
        ),
    )
    with pytest.raises(ProductionOrderShortError) as refused:
        _reduzir(recipe, work_order, quantity="14", key="plan-f14-own", proof="prova-forcada")
    production_service.apply_planned(
        recipe_id=recipe.pk,
        quantity=Decimal("14"),
        target_date_value=timezone.localdate().isoformat(),
        position_ref="",
        operator_ref="",
        force=True,
        reason="Pedido do gestor.",
        actor="production:cozinha",
        expected_rev=work_order.rev,
        idempotency_key="plan-f14-own",
        approved_shortage=production_service.production_shortage_snapshot(refused.value),
        projected_action_proof="prova-forcada",
    )
    work_order.refresh_from_db()

    with pytest.raises(ProductionConflict):
        _reduzir(recipe, work_order, quantity="15", key="plan-f14-thief", proof="prova-forcada")


@pytest.fixture
def cozinha(db):
    from django.contrib.auth.models import User

    from shopman.backstage.tests.production_grants import grant_production_operator

    return grant_production_operator(User.objects.create_user("cozinha-f14", password="pw", is_staff=True))


def test_a_recusa_do_plano_pela_api_sai_sem_salvar_com_justificativa(client, plano, cozinha):
    recipe, work_order = plano
    client.force_login(cozinha)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "work_order_id": work_order.pk,
            "quantity": "10",
            "target_date": timezone.localdate().isoformat(),
            "position_ref": "",
            "expected_rev": work_order.rev,
            "idempotency_key": "plan-f14-api",
        },
        content_type="application/json",
    )

    assert response.status_code == 409, response.json()
    body = response.json()
    assert body["detail"] == PLANO_ABAIXO
    assert body["error"]["code"] == "order_shortage"
    assert body["error"]["required"] == "12"
    assert [item["kind"] for item in body["error"]["possibilities"]] == ["retry"]


# ── Erro de campo no dialeto da casa (P2-19) ────────────────────────────────


def test_erro_de_campo_sai_no_dialeto_da_casa(client, cozinha, plano):
    recipe, work_order = plano
    client.force_login(cozinha)

    response = production_mutation_post(
        client,
        reverse("api-backstage-wo-plan"),
        data={
            "recipe_id": recipe.pk,
            "quantity": "dez",
            "target_date": timezone.localdate().isoformat(),
            "expected_rev": work_order.rev,
            "idempotency_key": "plan-f14-field",
        },
        content_type="application/json",
    )

    assert response.status_code == 400, response.json()
    body = response.json()
    assert body["field"] == "quantity"
    assert body["errors"]["quantity"] == [body["detail"]]
    assert body["detail"] != "Corrija os campos indicados e tente novamente."
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["issues"][0]["field"] == "quantity"
