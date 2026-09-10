"""Nelson seed coverage for operator production surfaces."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from shopman.craftsman import STOCK_CONSUMED_KEY, STOCK_REALIZED_KEY, craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderItem
from shopman.craftsman.models.recipe import _item_mass_in_kg
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import IdempotencyKey, Order, OrderItem, Session
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Batch, Move, Position
from shopman.utils import units

from config.management.commands.seed import (
    Command,
    _discard_owned_seed_output_batch,
    _ensure_seed_active_production_supply,
    _ensure_seed_standard_batch,
)
from shopman.backstage.models import (
    KDSInstance,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperatorAlert,
    OvenRun,
    POSTab,
)
from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report
from shopman.backstage.services.production import apply_finish, apply_start, check_finish_materials


@pytest.mark.django_db
def test_nelson_seed_populates_production_history_alerts_and_batches(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item

    assert not Product.objects.filter(sku__startswith="DEMO-").exists()
    assert not Product.objects.filter(ingredients_text__icontains="não contém glúten").exists(), (
        "o seed não pode contradizer a política da casa: sem segregação, nenhum item afirma ausência de glúten"
    )
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

    # Pré-go-live: exemplos úteis para testar etiquetas, sem fingir que são uma
    # decisão sanitária. O readiness de produção só libera depois da revisão
    # assinada no Admin.
    for ref, kind, days in (
        ("massa-tradicao", "mass", 1),
        ("creme-levain", "mass", 1),
        ("creme-baunilha", "cream", 2),
        ("recheio-frango", "other_filling", 3),
    ):
        meta = Recipe.objects.get(ref=ref).meta
        assert meta["shelf_life_days"] == days
        assert meta["preparation_kind"] == kind
        assert meta["shelf_life_source"] == "pre_go_live_example"
        assert meta["shelf_life_review_required"] is True

    # Buyman Material master (WP-B4): insumos viram Material first-class (sku sem
    # prefixo INS-), com unit + shelf-life. Os input_sku das receitas resolvem.
    from shopman.buyman.models import Material

    # 23 da fundação + 33 da Seção 2b (salgados, montados e bebidas — dono,
    # 26/08): queijos, presuntos, salsicha Vienna, frango, milho, bacon, café
    # em grão, blends de chá, tônica, folhas da salada…
    assert Material.objects.count() == 56
    farinha = Material.objects.get(sku="FARINHA-T65")
    assert (farinha.unit, farinha.shelf_life_days) == ("kg", 180)
    assert farinha.metadata["allergens"] == ["glúten"]
    # A água da massa é AGUA-FILTRADA: AGUA é a garrafa que se vende no balcão, e
    # produto e insumo dividem um namespace de SKU só (shop/services/sku_namespace.py).
    assert Material.objects.get(sku="AGUA-FILTRADA").shelf_life_days is None  # não perecível
    assert not Material.objects.filter(sku="AGUA").exists()
    assert Material.objects.get(sku="FERMENTO-NAT").shelf_life_days == 7
    # Insumo PESADO tem base de peso, e a ficha fala na mesma unidade — ADR-024:
    # "0,300 de OVOS" é 300 g de ovo, não 0,3 ovo. A ajuda "(≈ 6 un.)" é
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
    # Líquido também conta em kg desde o WP-BASE-UNIT-LIQUIDS-KG: a casa PESA a
    # água, o leite e o azeite, e é isso que a R1 pergunta. A densidade continua
    # no perfil, mas agora como ponte do RECEBIMENTO (a nota fala em litro), não
    # da produção diária. O invariante da troca vive em
    # test_seed_liquid_base_unit.py.
    for sku in ("AGUA-FILTRADA", "LEITE", "AZEITE"):
        material = Material.objects.get(sku=sku)
        assert material.unit == "kg", sku
        assert Decimal(str(material.metadata["density_g_per_ml"])) > 0, sku
        for item in RecipeItem.objects.filter(input_sku=sku):
            assert item.unit == "kg", f"{sku}: {item.unit}"
            item.full_clean()
    # A equivalência aproximada do que se pesa e se conta: é ela que faz a lista
    # de separação dizer "(≈ 6 un.)" abaixo de "300 g" (ADR-024 §4).
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
    # O saldo de abertura não é mais um 500 chapado: deriva do plano do dia ×
    # cobertura de compra e chega em SACAS fechadas de 25 kg (dono, 26/08).
    # O invariante é o mecanismo, não o número — o número muda com o plano.
    farinha_abertura = stock_service.available("FARINHA-T65", position=warehouse)
    assert farinha_abertura > 0
    assert farinha_abertura % Decimal("25") == 0, "farinha entra em saca fechada de 25 kg"
    assert farinha_abertura <= Decimal("625"), "teto de um pedido: 25 sacas"

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

    # O seed é contrato executável do QC: toda saída tem um único grau por
    # fornada e lote congelado; markdown e perda têm exatamente um motivo;
    # perda nunca ganha grau/lote; produzido + perda conserva a entrada.
    seed_finished = list(
        WorkOrder.objects.filter(
            source_ref__startswith="seed:production:",
            status=WorkOrder.Status.FINISHED,
        )
    )
    outcomes = list(
        WorkOrderItem.objects.filter(
            work_order__in=seed_finished,
            kind__in=(WorkOrderItem.Kind.OUTPUT, WorkOrderItem.Kind.WASTE),
        ).order_by("work_order_id", "pk")
    )
    batches = {
        batch.ref: batch
        for batch in Batch.objects.filter(
            ref__in=[item.batch_ref for item in outcomes if item.batch_ref]
        )
    }
    by_work_order: dict[int, list[WorkOrderItem]] = {}
    for item in outcomes:
        by_work_order.setdefault(item.work_order_id, []).append(item)
        if item.kind == WorkOrderItem.Kind.OUTPUT:
            assert item.quality_grade_ref in {"excellent", "standard", "fair", "minimal"}
            assert item.batch_ref
            assert item.meta.get("quality_contract_version") == 1
            assert item.meta.get("batch_traceability")
            assert batches[item.batch_ref].quality_grade_ref == item.quality_grade_ref
            if item.quality_grade_ref in {"fair", "minimal"}:
                assert item.quality_defect_ref
        else:
            assert item.quality_defect_ref
            assert not item.quality_grade_ref
            assert not item.batch_ref

    mixed = 0
    for work_order in seed_finished:
        lines = by_work_order[work_order.pk]
        output_grades = [
            item.quality_grade_ref
            for item in lines
            if item.kind == WorkOrderItem.Kind.OUTPUT
        ]
        assert len(output_grades) == len(set(output_grades))
        assert sum((item.quantity for item in lines), Decimal("0")) == (
            work_order.started_qty or work_order.quantity
        )
        mixed += len(output_grades) > 1
    assert mixed > 0, "o seed deixou de exercitar vários graus na mesma fornada"

    total_loss = WorkOrder.objects.get(
        source_ref__startswith="seed:production:history-",
        recipe__ref="croissant",
        finished=0,
    )
    assert total_loss.finished == 0
    assert not total_loss.items.filter(kind=WorkOrderItem.Kind.OUTPUT).exists()
    loss = total_loss.items.get(kind=WorkOrderItem.Kind.WASTE)
    assert loss.quantity == (total_loss.started_qty or total_loss.quantity)
    finished_event = total_loss.events.get(kind="finished")
    assert finished_event.payload["context"]["production_outcome"]["kind"] == "total_loss"

    # Medições históricas de forno são fatos sintéticos de BI, nunca timers
    # locais órfãos: todo registro é marcado e aponta para WO deste seed.
    oven_runs = list(OvenRun.objects.all())
    assert oven_runs
    seed_work_order_refs = set(
        WorkOrder.objects.filter(source_ref__startswith="seed:production:")
        .values_list("ref", flat=True)
    )
    assert all(run.metadata.get("seed") == "nelson" for run in oven_runs)
    assert all(run.metadata.get("source") == "synthetic_bi_history" for run in oven_runs)
    assert {run.work_order_ref for run in oven_runs} <= seed_work_order_refs

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
    for prep_sku in ("MASSA-CROISSANT", "MASSA-BRIOCHE", "MASSA-FORMA", "RECHEIO-MACA"):
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
    # Yield baixo já foi explicado no QC: fica como fato auditável/BI, não como
    # causa ativa eterna. Rupturas de estoque/pedido continuam abertas à parte.
    assert OperatorAlert.objects.filter(
        type="production_low_yield",
        resolved_by="system:production-outcome-recorded",
    ).exists()
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
def test_nelson_seed_keeps_the_day_in_order_when_seeded_at_dawn(monkeypatch):
    """A ordem da padaria não pode depender da hora em que o seed roda.

    O dia do seed mistura horas FIXAS (a tabela do plano: campagne 3h40,
    baguete 4h00…) com uma hora FLUTUANTE: a fornada travada nasce atrasada em
    relação ao ``timezone.now()``, senão o alerta ``production_late`` só
    apareceria se o reseed calhasse na hora certa. Enquanto o pré-preparo teve
    hora fixa (1h00–3h10), rodar o seed antes das ~5h25 punha a massa
    terminando DEPOIS de a primeira fornada começar — dia impossível, e um
    teste que passava ou falhava conforme o relógio (22/08).

    Este teste congela o relógio na faixa que quebrava e cobra as DUAS coisas
    ao mesmo tempo, porque é a tensão entre elas que causou o defeito: a massa
    antes do pão E o alerta de atraso aceso.
    """
    tz = timezone.get_current_timezone()
    madrugada = datetime.combine(timezone.localdate(), time(4, 20), tzinfo=tz)
    monkeypatch.setattr(timezone, "now", lambda: madrugada)
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    massas = list(WorkOrder.objects.filter(source_ref__startswith="seed:production:today-prep:"))
    acabados = WorkOrder.objects.filter(
        source_ref__startswith="seed:production:today:", started_at__isnull=False
    )
    assert massas
    ultima_massa = max(wo.finished_at for wo in massas)
    primeiro_pao = min(wo.started_at for wo in acabados)
    assert ultima_massa <= primeiro_pao, (
        f"seed de madrugada inverteu a ordem da casa ({ultima_massa} > {primeiro_pao})"
    )
    assert OperatorAlert.objects.filter(type="production_late", acknowledged=False).exists()


@pytest.mark.django_db
def test_seeded_batches_can_run_the_real_start_and_finish_stock_flow(monkeypatch):
    """Today's seeded cards must cross the same stock gates as real batches."""
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    from shopman.stockman.models import Quant

    today = timezone.localdate()
    production = Position.objects.get(ref="producao")

    # Seed updates are authoritative over their own planned supply. A reduced
    # contract corrects the existing Quant by ledger movement; it does not
    # leave an obsolete surplus or append the full quantity again.
    future = (
        WorkOrder.objects.filter(
            source_ref__startswith="seed:production:future-",
            recipe__ref="croissant",
            status=WorkOrder.Status.PLANNED,
        )
        .order_by("target_date")
        .first()
    )
    future_quant = Quant.objects.get(
        sku=future.output_sku,
        target_date=future.target_date,
        position=production,
        batch="",
    )
    reduced = future.quantity - Decimal("1")
    WorkOrder.objects.filter(pk=future.pk).update(quantity=reduced)
    assert _ensure_seed_active_production_supply() == 1
    future_quant.refresh_from_db()
    assert future_quant.quantity == reduced
    moves_after_reduction = Move.objects.count()
    assert _ensure_seed_active_production_supply() == 0
    assert Move.objects.count() == moves_after_reduction

    # Exact regression: this WO was written directly in STARTED state by the
    # seed. Before reconciliation it had no batch="started" source and finish
    # failed closed with QUANT_NOT_FOUND.
    already_started = WorkOrder.objects.get(
        source_ref=f"seed:production:today:{today.isoformat()}:ciabatta"
    )
    assert already_started.status == WorkOrder.Status.STARTED
    started_quant = Quant.objects.get(
        sku=already_started.output_sku,
        target_date=today,
        position=production,
        batch="started",
    )
    assert started_quant.quantity >= already_started.started_qty
    started_ref, started_finished = apply_finish(
        work_order_id=already_started.pk,
        quantity=already_started.started_qty,
        actor="test:seed-operator",
        partition=[
            {
                "quantity": str(already_started.started_qty),
                "quality_grade_ref": "standard",
            }
        ],
        expected_rev=already_started.rev,
        idempotency_key="seed-ci-finish",
    )
    already_started.refresh_from_db()
    assert started_ref == already_started.ref
    assert started_finished == already_started.started_qty
    assert already_started.status == WorkOrder.Status.FINISHED

    # The user-facing CT path begins as PLANNED, then performs both real
    # transitions. This guards the normal plan → production → stock flow too.
    work_order = WorkOrder.objects.get(
        source_ref=f"seed:production:today:{today.isoformat()}:croissant"
    )
    assert work_order.status == WorkOrder.Status.PLANNED
    planned = Quant.objects.get(
        sku="CT",
        target_date=today,
        position=production,
        batch="",
    )
    assert planned.quantity >= work_order.quantity

    apply_start(
        work_order_id=work_order.pk,
        quantity=work_order.quantity,
        actor="test:seed-operator",
        expected_rev=work_order.rev,
        idempotency_key="seed-ct-start",
    )
    work_order.refresh_from_db()
    started = Quant.objects.get(
        sku="CT",
        target_date=today,
        position=production,
        batch="started",
    )
    assert started.quantity >= work_order.started_qty

    ref, finished = apply_finish(
        work_order_id=work_order.pk,
        quantity=work_order.started_qty,
        actor="test:seed-operator",
        partition=[
            {
                "quantity": str(work_order.started_qty),
                "quality_grade_ref": "standard",
            }
        ],
        expected_rev=work_order.rev,
        idempotency_key="seed-ct-finish",
    )

    work_order.refresh_from_db()
    output = work_order.items.get(kind=WorkOrderItem.Kind.OUTPUT)
    assert ref == work_order.ref
    assert finished == work_order.started_qty
    assert work_order.status == WorkOrder.Status.FINISHED
    assert Quant.objects.filter(
        sku="CT",
        target_date__isnull=True,
        batch=output.batch_ref,
        _quantity=work_order.started_qty,
    ).exists()

    # Reconciliation is stable after terminal transitions: no supply is
    # resurrected and no duplicate movement is appended.
    moves_before = Move.objects.count()
    assert _ensure_seed_active_production_supply() == 0
    assert Move.objects.count() == moves_before


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
def test_seed_batch_helper_never_rewrites_frozen_quality():
    batch = Batch.objects.create(
        ref="CT-20260909-SEED",
        sku="CT",
        production_date=date(2026, 9, 9),
        expiry_date=date(2026, 9, 9),
        quality_grade_ref="fair",
        nonconformity_percent=20,
        nonconformity_reason="Assou demais",
    )

    with pytest.raises(CommandError, match="não reescreve QC congelado"):
        _ensure_seed_standard_batch(
            ref=batch.ref,
            sku=batch.sku,
            production_date=batch.production_date,
            expiry_date=batch.expiry_date,
        )

    batch.refresh_from_db()
    assert batch.quality_grade_ref == "fair"
    assert batch.nonconformity_percent == 20
    assert batch.nonconformity_reason == "Assou demais"


@pytest.mark.django_db
def test_seed_only_replaces_output_batch_that_carries_its_signature():
    owned = Batch.objects.create(
        ref="CT-20260909-OWNED",
        sku="CT",
        notes="Seed Nelson producao WO-SEED",
    )
    _discard_owned_seed_output_batch(
        ref=owned.ref,
        sku="CT",
        work_order_ref="WO-SEED",
    )
    assert not Batch.objects.filter(pk=owned.pk).exists()

    real = Batch.objects.create(
        ref="CT-20260909-REAL",
        sku="CT",
        notes="Produção conferida pela equipe",
        quality_grade_ref="fair",
    )
    with pytest.raises(CommandError, match="fora do domínio do seed"):
        _discard_owned_seed_output_batch(
            ref=real.ref,
            sku="CT",
            work_order_ref="WO-SEED",
        )
    real.refresh_from_db()
    assert real.quality_grade_ref == "fair"


@pytest.mark.django_db
def test_seed_oven_history_never_touches_real_measurement():
    from shopman.backstage.models import OvenRun

    recipe = Recipe.objects.create(
        ref="real-oven-run",
        name="Fornada real",
        output_sku="REAL-OVEN-RUN",
        batch_size=Decimal("1"),
    )
    work_order = craft.plan(recipe, 1, date=date.today())
    WorkOrder.objects.filter(pk=work_order.pk).update(source_ref="real:production:oven")
    craft.finish(work_order, finished=1, actor="test")
    work_order.refresh_from_db()
    real_run = OvenRun.objects.create(
        work_order_ref=work_order.ref,
        planned_seconds=1200,
        armed_at=work_order.finished_at - timedelta(minutes=20),
        concluded_at=work_order.finished_at,
        status="concluded",
        metadata={"source": "operator"},
    )

    Command()._seed_oven_runs(days=1)

    real_run.refresh_from_db()
    assert real_run.metadata == {"source": "operator"}
    assert not OvenRun.objects.filter(
        work_order_ref=work_order.ref,
        metadata__seed="nelson",
    ).exists()


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

    # "planned": sem pronto, mas a fermata do canal oferece exatamente a fornada.
    from shopman.shop.projections import catalog_context
    planned = by_sku[states["planned"]]
    assert planned.availability == Availability.PLANNED_OK
    planned_qty = catalog_context.planned_supply_for_skus(
        [states["planned"]], horizon_days=2
    ).get(states["planned"], 0)
    assert planned_qty == 10
    assert planned.available_qty == planned_qty

    paused = by_sku[states["paused"]]
    assert paused.is_paused is True
    assert paused.can_add_to_cart is False and paused.is_notifiable is False
