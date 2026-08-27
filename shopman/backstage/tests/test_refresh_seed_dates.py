"""O rejuvenescimento re-ancora um banco semeado em hoje — e recusa produção.

O comando existe porque ambiente de QA envelhece (26/08: alpha com insumo
zerado e nenhuma fornada do dia). Ele repõe ATÉ o alvo — nunca além — e não
toca na história: dado envelhecido que revela defeito é feature do ambiente.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from config.management.commands.seed import material_opening_targets


@pytest.mark.django_db
def test_recusa_producao_sem_flag_de_override():
    with override_settings(SHOPMAN_ENVIRONMENT="production"):
        with pytest.raises(CommandError, match="produção"):
            call_command("refresh_seed_dates", "--apply")


@pytest.mark.django_db
def test_rejuvenesce_um_banco_envelhecido_e_e_idempotente(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    from shopman.craftsman.models import WorkOrder
    from shopman.stockman import stock
    from shopman.stockman.models import Position

    deposito = Position.objects.get(ref="deposito")
    hoje = timezone.localdate()

    # ── Envelhecimento simulado: a produção consumiu a farinha até perto de
    # zero, e as fornadas planejadas de amanhã em diante "apodreceram" no
    # passado (como no alpha entre 19 e 26/08).
    from shopman.stockman.models import Quant

    farinha_antes = stock.available("FARINHA-T65", position=deposito)
    quant_farinha = Quant.objects.get(sku="FARINHA-T65", position=deposito)
    stock.issue(
        quantity=farinha_antes - Decimal("1"),
        quant=quant_farinha,
        reason="teste: consumo até quase zero",
    )
    WorkOrder.objects.filter(target_date__gt=hoje).update(
        target_date=hoje - timedelta(days=6)
    )
    apodrecidas = WorkOrder.objects.filter(
        status=WorkOrder.Status.PLANNED,
        target_date__lt=hoje,
        source_ref__regex=r"^(seed|refresh):",
    ).count()
    assert apodrecidas > 0

    # ── Dry-run relata e NÃO muda nada ──────────────────────────────────────
    out = StringIO()
    call_command("refresh_seed_dates", stdout=out)
    assert "DRY-RUN" in out.getvalue()
    assert stock.available("FARINHA-T65", position=deposito) == Decimal("1")
    assert WorkOrder.objects.filter(
        status=WorkOrder.Status.PLANNED, target_date__lt=hoje
    ).count() == apodrecidas

    # ── Apply: farinha volta ao alvo (saca fechada), passado vira void,
    # horizonte de hoje a +7 replantado ─────────────────────────────────────
    out = StringIO()
    call_command("refresh_seed_dates", "--apply", stdout=out)
    alvo_farinha = material_opening_targets()["FARINHA-T65"]
    assert stock.available("FARINHA-T65", position=deposito) == alvo_farinha
    assert alvo_farinha % Decimal("25") == 0
    assert not WorkOrder.objects.filter(
        status=WorkOrder.Status.PLANNED,
        target_date__lt=hoje,
        source_ref__regex=r"^(seed|refresh):",
    ).exists()
    for offset in (1, 3, 7):
        target = hoje + timedelta(days=offset)
        assert WorkOrder.objects.filter(
            status=WorkOrder.Status.PLANNED, target_date=target
        ).exists(), f"sem fornada planejada em {target}"

    # ── Segunda passada é no-op: o banco já está ancorado em hoje ───────────
    out = StringIO()
    call_command("refresh_seed_dates", "--apply", stdout=out)
    assert "Nada a fazer" in out.getvalue()

    # ── E o que envelheceu de verdade continua lá (história não se apaga) ───
    assert WorkOrder.objects.filter(status=WorkOrder.Status.VOID).count() >= apodrecidas
