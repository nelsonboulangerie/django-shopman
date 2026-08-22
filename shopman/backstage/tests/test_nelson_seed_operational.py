"""Nelson seed coverage for operator production surfaces."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from shopman.craftsman import STOCK_CONSUMED_KEY, STOCK_REALIZED_KEY, craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.craftsman.models.recipe import _item_mass_in_kg
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import IdempotencyKey, Order, OrderItem, Session
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Batch, Move, Position
from shopman.utils import units

from shopman.backstage.models import (
    KDSInstance,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperatorAlert,
    POSTab,
)
from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report
from shopman.backstage.services.production import check_finish_materials


@pytest.mark.django_db
def test_nelson_seed_populates_production_history_alerts_and_batches(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item

    assert not Product.objects.filter(sku__startswith="DEMO-").exists()
    for sku in ("BF", "SS", "COMBO-PETIT-DEJ"):
        metadata = Product.objects.get(sku=sku).metadata
        fiscal = metadata["fiscal"]
        assert fiscal["profile"] == "own_production"
        assert fiscal["ncm"]
        # CFOP/CSOSN são resolvidos do perfil fiscal na emissão (NFC-e intraestadual).
        resolved = resolve_fiscal_item(from_metadata(metadata))
        assert resolved["cfop"] == "5102"
        assert resolved["icms_situacao_tributaria"] == "102"
    croissant_history = [
        item
        for item in OrderItem.objects.filter(sku="CT").select_related("order")
        if (item.meta or {}).get("source") == "production_demand_history"
    ]
    assert len(croissant_history) >= 4
    assert not Order.objects.filter(ref__startswith="NB-").exists()
    assert all(
        ref.split("-")[1] == created_at.strftime("%y%m%d")
        for ref, created_at in Order.objects.values_list("ref", "created_at")
        if len(ref.split("-")) >= 3
    )
    assert set(POSTab.objects.values_list("ref", flat=True)) >= {
        "00001007",
        "00001008",
        "00001009",
        "00001010",
        "00001011",
        "00001012",
    }
    assert Session.objects.filter(
        channel_ref="pdv",
        state="open",
        handle_type="pos_tab",
        handle_ref="00001007",
        data__tab_ref="00001007",
    ).exists()

    recipe = Recipe.objects.get(ref="croissant")
    assert recipe.meta["requires_batch_tracking"] is True
    assert recipe.meta["max_started_minutes"] > 0
    assert recipe.steps

    # Buyman Material master (WP-B4): insumos viram Material first-class (sku sem
    # prefixo INS-), com unit + shelf-life. Os input_sku das receitas resolvem.
    from shopman.buyman.models import Material

    assert Material.objects.count() == 23
    farinha = Material.objects.get(sku="FARINHA-T65")
    assert (farinha.unit, farinha.shelf_life_days) == ("kg", 180)
    assert farinha.metadata["allergens"] == ["glúten"]
    # A água da massa é AGUA-FILTRADA: AGUA é a garrafa que se vende no balcão, e
    # produto e insumo dividem um namespace de SKU só (shop/services/sku_namespace.py).
    assert Material.objects.get(sku="AGUA-FILTRADA").shelf_life_days is None  # não perecível
    assert not Material.objects.filter(sku="AGUA").exists()
    assert Material.objects.get(sku="FERMENTO-NAT").shelf_life_days == 7
    # Insumo PESADO tem base de peso, e a ficha fala na mesma unidade — ADR-024:
    # "0,300 de OVOS" é 300 g de ovo, não 0,3 ovo. A anotação "≈ 6 ovos" é
    # derivada na tela de preparo, nunca gravada como verdade.
    for sku in ("OVOS", "LIMAO", "CANELA", "ALECRIM"):
        assert Material.objects.get(sku=sku).unit == "kg", sku
    weighed = {
        m.sku: m.unit
        for m in Material.objects.filter(unit__in=["kg", "g"])
    }
    for item in RecipeItem.objects.filter(input_sku__in=weighed):
        assert item.unit == weighed[item.input_sku], f"{item.input_sku}: {item.unit}"
        item.full_clean()  # a unidade da ficha bate com a do catálogo
    # Líquido conta em litro, e a ficha fala a mesma língua — a ficha grafa "L",
    # a base grafa "l", e a densidade no perfil é a ponte até a grama da nutrição
    # (ADR-024: a ponte volume→massa é declarada, nunca deduzida).
    for sku in ("AGUA-FILTRADA", "LEITE", "AZEITE"):
        material = Material.objects.get(sku=sku)
        assert material.unit == "l", sku
        assert Decimal(str(material.metadata["density_g_per_ml"])) > 0, sku
        for item in RecipeItem.objects.filter(input_sku=sku):
            assert item.unit == "L", f"{sku}: {item.unit}"
            item.full_clean()
    # A equivalência aproximada do que se pesa e se conta: é ela que faz a lista
    # de separação dizer "≈ 6 ovos" ao lado de "0,3 kg" (ADR-024 §4).
    from shopman.buyman.models import MaterialConversion

    ovo = MaterialConversion.objects.get(material__sku="OVOS", label="ovos")
    assert ovo.is_approximate is True
    assert ovo.supplier_id is None
    assert ovo.to_base_factor == Decimal("0.050000")
    assert MaterialConversion.objects.filter(material__sku="LIMAO").exists()

    # Todo input de receita resolve: insumo cru (Material), intermediário (output
    # de outra receita, ex. MASSA-*) ou produto. Sem inputs órfãos pós-rename.
    recipe_inputs = set(RecipeItem.objects.values_list("input_sku", flat=True))
    material_skus = set(Material.objects.values_list("sku", flat=True))
    intermediate_skus = set(Recipe.objects.values_list("output_sku", flat=True))
    product_skus = set(Product.objects.values_list("sku", flat=True))
    unresolved = recipe_inputs - material_skus - intermediate_skus - product_skus
    assert not unresolved, f"inputs de receita sem resolução: {unresolved}"
    # E os insumos crus de fato vêm do Material (interseção não-vazia).
    assert recipe_inputs & material_skus

    # Estoque de abertura de insumo no depósito (físico, p/ consumir/checar).
    from shopman.stockman import stock as stock_service
    from shopman.stockman.models import Quant

    warehouse = Position.objects.get(ref="deposito")
    assert Quant.objects.filter(sku="FARINHA-T65", position=warehouse).exists()
    assert stock_service.available("FARINHA-T65", position=warehouse) == Decimal("500")

    suggestions = craft.suggest(date.today() + timedelta(days=1), output_skus=["CT"])
    assert suggestions
    assert suggestions[0].quantity > 0

    assert WorkOrder.objects.filter(source_ref__startswith="seed:production:today:").exists()

    # A MASSA ANTES DO PÃO. O seed produz o pré-preparo desde 21/08 (decisão do
    # dono): padaria artesanal faz a própria massa, e encontrá-la pronta era
    # ficção. Duas coisas se guardam aqui, e a segunda é a que já quebrou uma vez:
    massas = list(WorkOrder.objects.filter(source_ref__startswith="seed:production:today-prep:"))
    assert massas, "o seed voltou a encontrar a massa pronta em vez de produzi-la"

    acabados = WorkOrder.objects.filter(
        source_ref__startswith="seed:production:today:", started_at__isnull=False
    )
    ultima_massa = max(wo.finished_at for wo in massas)
    primeiro_pao = min(wo.started_at for wo in acabados)
    assert ultima_massa <= primeiro_pao, (
        "massa terminando depois de a primeira fornada começar: não dá para "
        f"modelar o pão com a massa ainda na masseira ({ultima_massa} > {primeiro_pao})"
    )

    # Toda fornada que o seed grava como FINISHED tem as duas pernas do ledger
    # de estoque CARIMBADAS. Ela não passou por ``CraftExecution.finish``, então
    # não há perna nenhuma a escrever — e sem o carimbo o
    # ``sweep_unrealized_production`` lê a história inteira como "ledger aberto".
    # No staging de 19/08 isso reconsumiu −223,610 kg de insumo em dois minutos,
    # 264 movimentos em dois minutos, sem um único alerta.
    open_ledger = [
        wo.ref
        for wo in WorkOrder.objects.filter(status=WorkOrder.Status.FINISHED)
        if not (wo.meta or {}).get(STOCK_CONSUMED_KEY)
        or not (wo.meta or {}).get(STOCK_REALIZED_KEY)
    ]
    assert not open_ledger, f"fornadas do seed sem marcador de ledger: {open_ledger[:5]}"

    # E a prova pelo comportamento: o ciclo do ``maintenance_worker`` logo após
    # um reseed não pode mover um grama de insumo antigo.
    flour_before = stock_service.available("FARINHA-T65")
    moves_before = Move.objects.count()
    call_command("sweep_unrealized_production", "--minutes", "1", stdout=StringIO())
    assert stock_service.available("FARINHA-T65") == flour_before
    assert Move.objects.count() == moves_before

    # Mise en place: as dez receitas que consomem massa/recheio precisam achar
    # o pré-preparo PRONTO. Sem ele o guardrail de insumo (Buyman WP-B5b)
    # reprovava toda fornada dessas dez, e o operador via "Insumos
    # insuficientes" com o atalho "Concluir mesmo assim" a um toque, todo dia.
    # Alarme sempre errado vira botão que se aprende a apertar.
    for prep_sku in ("MASSA-FOLHADA", "MASSA-BRIOCHE", "MASSA-PAES-MACIOS", "RECHEIO-MACA"):
        assert stock_service.available(prep_sku) > 0, f"{prep_sku} sem estoque"
    crying = sorted(
        {
            wo.recipe.ref
            for wo in WorkOrder.objects.filter(
                source_ref__startswith="seed:production:"
            ).select_related("recipe")
            if check_finish_materials(wo)
        }
    )
    assert not crying, f"fornadas do seed com insumo faltando: {crying}"

    # E as fichas fecham a conta de massa: 10 kg de massa não saem de 8,04 kg
    # de ingredientes. ``Recipe.clean`` recusa daqui em diante; isto confere o
    # dado que o seed grava.
    creating_matter = []
    for sheet in Recipe.objects.all():
        output_unit = sheet._declared_output_unit()
        if units.dimension(output_unit) != units.MASS:
            continue
        total = Decimal("0")
        comparable = True
        for sheet_item in sheet.items.filter(is_optional=False):
            mass = _item_mass_in_kg(sheet_item)
            if mass is None:
                comparable = False
                break
            total += mass
        if comparable and units.convert(sheet.batch_size, output_unit, "kg") > total:
            creating_matter.append(sheet.ref)
    assert not creating_matter, f"fichas que criam matéria do nada: {creating_matter}"

    assert Batch.objects.filter(sku="CT").exists()
    assert set(Position.objects.filter(ref__in=["massa", "molde", "forno"]).values_list("ref", flat=True)) == {
        "massa",
        "molde",
        "forno",
    }
    assert OperatorAlert.objects.filter(type="production_late", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="production_low_yield", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="production_stock_short", acknowledged=False).exists()
    assert set(KDSInstance.objects.values_list("ref", flat=True)) >= {"cafes", "lanches", "encomendas", "expedicao"}
    assert set(OperationChecklistTemplate.objects.values_list("ref", flat=True)) >= {
        "nelson-opening",
        "nelson-routine",
        "nelson-closing",
    }
    assert OperationChecklistRun.objects.filter(template__ref="nelson-opening", status="completed").exists()
    assert OperationChecklistRun.objects.filter(template__ref="nelson-routine", status="open").exists()
    assert OperationChecklistRun.objects.filter(template__ref="nelson-closing", status="completed").exists()

    edge_orders = list(Order.objects.filter(snapshot__seed_namespace="security_reliability_edges"))
    edge_keys = {order.snapshot["seed_key"] for order in edge_orders}
    # O edge "ifood-stale-confirmation" (pedido NEW parado) foi removido de propósito:
    # a coluna Entrada nasce vazia para testar a chegada de pedidos novos ao vivo.
    assert edge_keys >= {
        "security:payment-pending-near-expiry",
        "security:payment-expired-low-attention",
        "security:payment-after-cancel",
    }
    assert "security:ifood-stale-confirmation" not in edge_keys

    edge_order_refs = {order.ref for order in edge_orders}
    assert PaymentIntent.objects.filter(order_ref__in=edge_order_refs, status=PaymentIntent.Status.PENDING).count() >= 2
    assert PaymentIntent.objects.filter(order_ref__in=edge_order_refs, status=PaymentIntent.Status.CAPTURED).exists()
    for intent in PaymentIntent.objects.filter(status=PaymentIntent.Status.CAPTURED):
        order = Order.objects.get(ref=intent.order_ref)
        assert ((order.data or {}).get("payment") or {}).get("intent_ref") == intent.ref
    assert OperatorAlert.objects.filter(type="payment_after_cancel", severity="critical", acknowledged=False).exists()
    # (alerta stale_new_order + webhook:ifood saíram junto com o edge iFood parado — Entrada vazia)
    assert IdempotencyKey.objects.filter(scope="webhook:efi-pix", status="done").exists()

    low_attention = Customer.objects.get(ref="CLI-001")
    assert low_attention.metadata["seed_persona"] == "low_attention"

    qa_report = build_omotenashi_qa_report()
    missing = [check.id for check in qa_report.checks if check.status == "missing"]
    assert qa_report.ready_count == len(qa_report.checks)
    assert not missing


@pytest.mark.django_db
def test_nelson_seed_provisions_operators_with_pins(monkeypatch):
    """Backstage exige operador ativo: staff + PinCredential + permissão da superfície.

    Nenhuma tela destrava sem um operador provisionado — a estação sozinha não
    autoriza nada. O seed provisiona operadores com PIN 1234 para POS/KDS/produção;
    senão o backstage nasce inacessível após um ``--flush``.
    """
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    from django.contrib.auth.models import User

    from shopman.backstage.services.operator import eligible_operators, verify_operator_pin

    for perm in (
        "backstage.operate_pos",
        "backstage.operate_kds",
        "backstage.operate_production",
    ):
        operators = list(eligible_operators(perm=perm))
        assert operators, f"nenhum operador elegível para {perm}"
        assert any(verify_operator_pin(u, "1234", required_perm=perm) for u in operators), (
            f"PIN 1234 não destrava {perm}"
        )

    # O superuser 'admin' também opera — PIN destrava qualquer superfície.
    admin = User.objects.get(username="admin")
    assert verify_operator_pin(admin, "1234", required_perm="backstage.operate_pos")
    assert verify_operator_pin(admin, "1234", required_perm="backstage.operate_kds")

    # PIN errado nunca destrava.
    assert not verify_operator_pin(admin, "0000", required_perm="backstage.operate_pos")


@pytest.mark.django_db
def test_nelson_seed_rejects_default_admin_password_when_not_debug(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with override_settings(DEBUG=False):
        with pytest.raises(CommandError):
            call_command("seed", stdout=StringIO())


@pytest.mark.django_db
def test_nelson_seed_qa_profile_builds_named_scenarios(monkeypatch):
    """Perfil qa (SEED-DATA-QUALITY-PLAN Fase 2): cada cenário nomeado existe com
    ref previsível QA-*, estado estável e datas relativas a localdate().

    Ver docs/reference/qa-seed-scenarios.md — este teste é a âncora de contrato.
    """
    from datetime import timedelta

    from django.utils import timezone
    from shopman.cashman import services as cash
    from shopman.cashman.models import Shift
    from shopman.craftsman.models import WorkOrder
    from shopman.payman.models import PaymentIntent, PaymentTransaction

    from shopman.backstage.models import KDSTicket, POSTab

    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", "--profile", "qa", stdout=StringIO())

    today = timezone.localdate()
    tomorrow = (today + timedelta(days=1)).isoformat()

    # Todas as refs QA-* nomeadas existem.
    named = {
        "QA-PREORDER-01", "QA-PREORDER-02",
        "QA-PAID-READY-01", "QA-PAID-READY-02", "QA-RETURNED-01",
        "QA-PIX-PENDING-01", "QA-IFOOD-01", "QA-NOTES-01", "QA-NAMED-ITEMS-01",
    }
    existing = set(Order.objects.filter(ref__startswith="QA-").values_list("ref", flat=True))
    assert named <= existing, f"faltando cenários qa: {named - existing}"

    # Preorder: novo + confirmado, encomenda para amanhã.
    p1 = Order.objects.get(ref="QA-PREORDER-01")
    assert p1.status == Order.Status.NEW
    assert p1.data["is_preorder"] is True
    assert p1.data["delivery_date"] == tomorrow
    assert Order.objects.get(ref="QA-PREORDER-02").status == Order.Status.ACCEPTED

    # Pago em ready/dispatched com intent capturado.
    ready = Order.objects.get(ref="QA-PAID-READY-01")
    assert ready.status == Order.Status.READY
    assert PaymentIntent.objects.get(order_ref="QA-PAID-READY-01").status == PaymentIntent.Status.CAPTURED
    assert Order.objects.get(ref="QA-PAID-READY-02").status == Order.Status.DISPATCHED

    # Devolvido + estorno (intent refunded com transação de refund).
    ret = Order.objects.get(ref="QA-RETURNED-01")
    assert ret.status == Order.Status.RETURNED
    ret_intent = PaymentIntent.objects.get(order_ref="QA-RETURNED-01")
    assert ret_intent.status == PaymentIntent.Status.REFUNDED
    assert PaymentTransaction.objects.filter(
        intent=ret_intent, type=PaymentTransaction.Type.REFUND
    ).exists()

    # PIX pendente (confirmado, não pago).
    assert Order.objects.get(ref="QA-PIX-PENDING-01").status == Order.Status.ACCEPTED
    assert PaymentIntent.objects.get(order_ref="QA-PIX-PENDING-01").status == PaymentIntent.Status.PENDING

    # iFood (canal marketplace + external_ref).
    ifood = Order.objects.get(ref="QA-IFOOD-01")
    assert ifood.channel_ref == "ifood"
    assert ifood.external_ref == "IFOOD-QA-0001"

    # order_notes do cliente propagado.
    assert Order.objects.get(ref="QA-NOTES-01").data["order_notes"]

    # OrderItem.name preenchido (regressão SKU cru).
    named_items = Order.objects.get(ref="QA-NAMED-ITEMS-01")
    assert all(item.name for item in named_items.items.all())

    # Produção: WO em cada estado hoje + fornada presa de ontem (started).
    today_states = set(
        WorkOrder.objects.filter(
            source_ref__startswith="seed:production:today:", target_date=today
        ).values_list("status", flat=True)
    )
    assert {"planned", "started", "finished"} <= today_states
    stuck = WorkOrder.objects.filter(source_ref__startswith="seed:production:qa-stuck:")
    assert stuck.count() == 1
    stuck_wo = stuck.get()
    assert stuck_wo.status == WorkOrder.Status.STARTED
    assert stuck_wo.target_date == today - timedelta(days=1)

    # Caixa (cashman): 1 aberto + 1 fechado com divergência conhecida, provada pelo livro.
    assert Shift.objects.filter(status=Shift.Status.OPEN).exists()
    closed = Shift.objects.filter(status=Shift.Status.CLOSED)
    assert closed.exists()
    assert cash.difference(closed.first()) == -300

    # Comandas: aberta com itens (00001007) + uma com item disparado à cozinha.
    assert POSTab.objects.filter(ref="00002001").exists()
    assert KDSTicket.objects.filter(session_key="seed-qa-postab-00002001").exists()
    assert Session.objects.filter(
        state="open", handle_type="pos_tab", handle_ref="00001007"
    ).exists()

    # Vitrine da LOJA cobre todos os estados de disponibilidade (QA cliente).
    from config.management.commands.seed import Command
    from shopman.shop.projections.types import Availability
    from shopman.storefront.presentation import build_catalog

    states = Command.QA_STOREFRONT_STATES
    by_sku = {i.sku: i for i in build_catalog(channel_ref="web").items}

    sold = by_sku[states["sold_out"]]
    assert sold.availability == Availability.UNAVAILABLE
    assert sold.is_notifiable is True and sold.can_add_to_cart is False

    low = by_sku[states["low_stock"]]
    assert low.availability == Availability.LOW_STOCK
    assert low.can_add_to_cart is True

    # "planned": sem pronto HOJE (no menu aparece indisponível), MAS tem produção
    # planejada — base da "lista de espera / previsto" no fluxo de encomenda.
    from shopman.shop.projections import catalog_context
    planned = by_sku[states["planned"]]
    assert planned.availability == Availability.UNAVAILABLE
    assert catalog_context.planned_supply_for_skus(
        [states["planned"]], horizon_days=2
    ).get(states["planned"], 0) > 0

    paused = by_sku[states["paused"]]
    assert paused.is_paused is True
    assert paused.can_add_to_cart is False and paused.is_notifiable is False
