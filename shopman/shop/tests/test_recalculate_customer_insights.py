"""A varredura diária percebe quem PAROU de comprar.

O ``CustomerInsight`` é recalculado no ``customer.ensure`` de cada pedido, então
quem compra está sempre em dia. Quem sumiu não dispara nada e ficava congelado no
dia da última visita — o segmento nunca virava "Em risco", e o Gestor, a campanha
e o B.I. liam um retrato velho como se fosse de agora.

Os testes fixam as três decisões que fazem a varredura ser barata e verdadeira:
a janela da madrugada, o teto por ciclo (o worker é serial), e o cliente sem
pedido nenhum que fica de fora — porque recalculá-lo carimbaria "Perdido" em
quem nunca comprou.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db

COMMAND = "recalculate_customer_insights"
MODULE = "shopman.shop.management.commands.recalculate_customer_insights"


def _insight(ref: str, *, calculado_ha_horas: float, com_pedido: bool = True) -> CustomerInsight:
    customer = Customer.objects.create(ref=ref, first_name=f"Cliente {ref}")
    insight = CustomerInsight.objects.create(
        customer=customer,
        total_orders=3 if com_pedido else 0,
        last_order_at=timezone.now() - timedelta(days=40) if com_pedido else None,
    )
    # ``calculated_at`` é auto_now: só um update direto move o relógio.
    CustomerInsight.objects.filter(pk=insight.pk).update(
        calculated_at=timezone.now() - timedelta(hours=calculado_ha_horas)
    )
    insight.refresh_from_db()
    return insight


def _rodar(**kwargs) -> str:
    saida = StringIO()
    call_command(COMMAND, stdout=saida, **kwargs)
    return saida.getvalue()


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))  # a janela cobre o dia todo
def test_insight_vencido_e_recalculado() -> None:
    _insight("CLI-VELHO", calculado_ha_horas=30)

    with patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc:
        _rodar()

    recalc.assert_called_once_with("CLI-VELHO")


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))
def test_insight_recente_nao_e_recalculado_de_novo_na_mesma_noite() -> None:
    """``STALE_HOURS`` é o que faz "1x por dia" ser 1x, e não 24 vezes: o ciclo do
    worker passa a cada 5 minutos, e sem o corte de idade a mesma base seria
    varrida a cada passagem dentro da janela."""
    _insight("CLI-NOVO", calculado_ha_horas=2)

    with patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc:
        _rodar()

    recalc.assert_not_called()


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))
def test_cliente_sem_pedido_nenhum_fica_de_fora() -> None:
    """Quem nunca comprou não tem recência para envelhecer — e recalculá-lo daria
    ``r=1, f=1, m=1``, que cai em ``lost``. "Perdido" é sobre quem foi embora, não
    sobre quem nunca chegou."""
    _insight("CLI-SEM-PEDIDO", calculado_ha_horas=200, com_pedido=False)

    with patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc:
        _rodar()

    recalc.assert_not_called()


@patch(f"{MODULE}.QUIET_HOURS", (3, 5))
def test_fora_da_janela_o_comando_volta_na_hora() -> None:
    """Está na lista do ciclo de 5 min, mas só trabalha de madrugada: sem o portão,
    entrar no worker significaria varrer a base 288 vezes por dia."""
    _insight("CLI-VELHO", calculado_ha_horas=30)

    agora = timezone.localtime().replace(hour=14, minute=30)
    with (
        patch(f"{MODULE}.timezone.localtime", return_value=agora),
        patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc,
    ):
        _rodar()

    recalc.assert_not_called()


@patch(f"{MODULE}.QUIET_HOURS", (3, 5))
def test_force_ignora_a_janela() -> None:
    _insight("CLI-VELHO", calculado_ha_horas=30)

    agora = timezone.localtime().replace(hour=14, minute=30)
    with (
        patch(f"{MODULE}.timezone.localtime", return_value=agora),
        patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc,
    ):
        _rodar(force=True)

    recalc.assert_called_once_with("CLI-VELHO")


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))
def test_o_lote_tem_teto_e_drena_do_mais_velho_para_o_mais_novo() -> None:
    """O worker roda os comandos em SÉRIE: um ciclo que varresse a base inteira
    atrasaria ``reconcile_payments`` e tudo atrás dela. Com teto, a ordem por
    ``calculated_at`` garante que a cauda mais velha saia primeiro — base maior que
    uma noite drena em ordem, sem ninguém ficar para trás para sempre."""
    _insight("CLI-30H", calculado_ha_horas=30)
    _insight("CLI-99H", calculado_ha_horas=99)
    _insight("CLI-50H", calculado_ha_horas=50)

    with patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc:
        _rodar(limit=2)

    assert [c.args[0] for c in recalc.call_args_list] == ["CLI-99H", "CLI-50H"]


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))
def test_cliente_problematico_nao_derruba_o_lote() -> None:
    """Cliente desativado entre a query e o recálculo levanta ``DoesNotExist`` no
    ``InsightService``. Um sozinho não pode custar a noite dos outros."""
    _insight("CLI-A", calculado_ha_horas=30)
    _insight("CLI-B", calculado_ha_horas=40)

    with patch(
        "shopman.guestman.contrib.insights.InsightService.recalculate",
        side_effect=[Customer.DoesNotExist("sumiu"), None],
    ) as recalc:
        saida = _rodar()

    assert recalc.call_count == 2
    assert "1 insight(s) recalculado(s), 1 pulado(s)." in saida


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))
def test_dry_run_conta_sem_recalcular() -> None:
    _insight("CLI-VELHO", calculado_ha_horas=30)

    with patch("shopman.guestman.contrib.insights.InsightService.recalculate") as recalc:
        saida = _rodar(dry_run=True)

    recalc.assert_not_called()
    assert "1 insight(s) vencido(s)" in saida


def test_all_faz_a_base_inteira_ignorando_janela_e_teto() -> None:
    """Escotilha manual do backfill — cliente importado que nunca teve insight só
    ganha um por aqui (ou pela ação do CustomerAdmin)."""
    agora = timezone.localtime().replace(hour=14, minute=30)
    with (
        patch(f"{MODULE}.timezone.localtime", return_value=agora),
        patch(
            "shopman.guestman.contrib.insights.InsightService.recalculate_all",
            return_value=7,
        ) as recalc_all,
    ):
        saida = _rodar(all=True)

    recalc_all.assert_called_once_with()
    assert "7 cliente(s) recalculado(s)" in saida


# ── O efeito de verdade, sem mock ───────────────────────────────────────────
#
# Os testes acima provam o AGENDAMENTO (janela, teto, ordem, quem entra) com o
# service mockado. Nenhum deles prova a razão do WP existir. Este roda o
# InsightService de verdade, contra pedidos de verdade, e mostra o segmento
# mudando sozinho — que é a coisa que ninguém fazia.


@patch(f"{MODULE}.QUIET_HOURS", (0, 24))
def test_quem_sumiu_vira_em_risco_sem_ninguem_mexer() -> None:
    from shopman.orderman.models import Order

    customer = Customer.objects.create(ref="CLI-SUMIU", first_name="Cristiane")
    ha_muito = timezone.now() - timedelta(days=120)
    for i in range(6):
        pedido = Order.objects.create(
            ref=f"W-SUM-{i}",
            channel_ref="web",
            session_key=f"session-sum-{i}",
            status="delivered",
            total_q=4200,
            data={"customer_ref": "CLI-SUMIU"},
            snapshot={"pricing": {"total_q": 4200}, "items": []},
        )
        Order.objects.filter(pk=pedido.pk).update(created_at=ha_muito - timedelta(days=i * 7))

    # O retrato congelado do dia em que ela ainda era cliente frequente: o
    # insight diz "há 1 dia" porque foi calculado naquele dia e nunca mais.
    insight = CustomerInsight.objects.create(
        customer=customer,
        total_orders=6,
        last_order_at=ha_muito,
        days_since_last_order=1,
        rfm_recency=5,
        rfm_frequency=3,
        rfm_monetary=1,
        rfm_segment="loyal_customer",
    )
    CustomerInsight.objects.filter(pk=insight.pk).update(
        calculated_at=timezone.now() - timedelta(hours=30)
    )

    _rodar()

    insight.refresh_from_db()
    # 120 dias sem comprar: a recência despenca e o segmento conta a verdade.
    assert insight.days_since_last_order >= 119
    assert insight.rfm_recency <= 2
    assert insight.rfm_segment == "at_risk"
    # E o Gestor passa a mostrar o selo âmbar sem que ninguém tenha tocado nela.
