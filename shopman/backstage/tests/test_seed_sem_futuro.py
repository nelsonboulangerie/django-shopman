"""O seed rodado de madrugada não deixa nada no futuro, nem fora de ordem.

O beta de 05/11/2026 rodou o seed às 05h51 e o dia inteiro mostrou o relógio
andando para trás: turno "aberto às 08:45" às 07:40, pedido de conta "aberto às
08:20", lote "fechado 11:00" às 07:31, Pix "gerado às 05:51 · expirou às 05:48",
cobrança "criada em 5 nov, capturada em 2 out". Cada um vinha de uma hora fixa ou
de um ``auto_now_add`` que o seed não acertou.

Um seed só, com o relógio parado às 05h50 de um dia de loja aberta, e todas as
coerências cobradas juntas. A data é fixa e passada para o ``default=timezone.now``
dos models (que o monkeypatch não alcança) cair longe da janela que o teste lê.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db.models import DateTimeField, F

# Campos que são futuro por natureza: prazo, agenda, validade.
FUTURO_POR_NATUREZA = {
    "orderman.Directive.available_at",  # tarefa agendada
    "payman.PaymentIntent.expires_at",  # Pix pendente ainda vale
    "shop.Promotion.valid_until",
    "shop.Coupon.valid_until",
}

SEEDED_AT = datetime(2026, 10, 7, 5, 50, tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(UTC)


@pytest.fixture
def seeded_at_dawn(monkeypatch, db):
    monkeypatch.setattr("django.utils.timezone.now", lambda: SEEDED_AT)
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())
    return SEEDED_AT


@pytest.mark.django_db
def test_seed_de_madrugada_nao_deixa_nada_no_futuro_nem_fora_de_ordem(seeded_at_dawn):
    now = seeded_at_dawn
    janela_fim = now + timedelta(days=10)

    no_futuro = []
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if not isinstance(field, DateTimeField):
                continue
            label = f"{model._meta.label}.{field.name}"
            if label in FUTURO_POR_NATUREZA:
                continue
            rows = model._base_manager.filter(
                **{f"{field.name}__gt": now, f"{field.name}__lt": janela_fim}
            )
            count = rows.count()
            if count:
                exemplo = rows.values_list("pk", field.name).first()
                no_futuro.append(f"{label}: {count} (ex.: {exemplo})")
    assert not no_futuro, "o seed gravou fatos depois do agora:\n" + "\n".join(no_futuro)

    from shopman.payman.models import PaymentIntent

    # GES-04 / ENV-01: a cobrança nasce antes de vencer e antes de ser capturada.
    vence_antes_de_nascer = PaymentIntent.objects.filter(expires_at__lt=F("created_at"))
    assert not vence_antes_de_nascer.exists(), list(
        vence_antes_de_nascer.values_list("ref", "created_at", "expires_at")
    )
    capturada_antes_de_nascer = PaymentIntent.objects.filter(captured_at__lt=F("created_at"))
    assert not capturada_antes_de_nascer.exists(), list(
        capturada_antes_de_nascer.values_list("ref", "created_at", "captured_at")[:5]
    )

    from shopman.orderman.models import Order, OrderEvent

    # CEN-10: concluído depois de aberto, e retirada sem "Saiu para entrega".
    assert not Order.objects.filter(completed_at__lt=F("created_at")).exists()
    retirada_que_saiu = [
        event.order.ref
        for event in OrderEvent.objects.select_related("order").filter(type="status_change")
        if (event.payload or {}).get("new_status") in ("dispatched", "delivered")
        and (event.order.data or {}).get("fulfillment_type") != "delivery"
        and event.order.status not in ("dispatched", "delivered")
    ]
    assert not retirada_que_saiu, f"retirada com passo de entrega: {sorted(set(retirada_que_saiu))}"
    for order in Order.objects.filter(ref__startswith="CONTA-"):
        passos = list(order.events.filter(type="status_change").values_list("created_at", flat=True))
        assert passos and all(order.created_at <= at <= order.completed_at for at in passos), order.ref

    from shopman.cashman.models import Entry, Shift

    # PDV-28: o turno abre antes dos próprios lançamentos e fecha depois de abrir.
    assert not Shift.objects.filter(closed_at__lt=F("opened_at")).exists()
    lancado_antes_de_abrir = Entry.objects.filter(at__lt=F("shift__opened_at"))
    assert not lancado_antes_de_abrir.exists(), list(
        lancado_antes_de_abrir.values_list("shift_id", "kind", "at", "shift__opened_at")[:5]
    )

    from shopman.craftsman.models import WorkOrderEvent

    # PROD-20: quem fecha o lote é gente da Cozinha, nunca "seed".
    assert not WorkOrderEvent.objects.filter(
        kind__in=(WorkOrderEvent.Kind.STARTED, WorkOrderEvent.Kind.FINISHED), actor="seed"
    ).exists()


def test_lote_fechado_no_futuro_recua_inteiro_e_aberto_abre_no_teto():
    """O folhado das 8h às 11h, com o seed às 5h50, recua sem virar lote de zero minutos."""
    from config.management.commands.seed import _not_after_now

    teto = datetime(2026, 10, 7, 5, 48, tzinfo=UTC)
    oito, onze = datetime(2026, 10, 7, 8, 0, tzinfo=UTC), datetime(2026, 10, 7, 11, 0, tzinfo=UTC)

    inicio, fim = _not_after_now(oito, onze, ceiling=teto)
    assert fim == teto and fim - inicio == onze - oito

    inicio, fim = _not_after_now(oito, None, ceiling=teto)
    assert (inicio, fim) == (teto, None)

    cedo = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)
    assert _not_after_now(cedo, cedo + timedelta(hours=1), ceiling=teto) == (cedo, cedo + timedelta(hours=1))
