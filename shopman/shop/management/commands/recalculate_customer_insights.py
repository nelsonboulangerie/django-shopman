"""Management command: recalculate_customer_insights

O ``CustomerInsight`` é recalculado no ``customer.ensure`` de cada pedido — então
quem COMPRA está sempre em dia. O que ninguém percebia é quem **parou** de
comprar: não comprar não dispara nada, e o insight de um cliente que sumiu ficava
congelado no dia da última visita. Era a única razão para existir uma varredura, e
é exatamente ela que este comando faz.

O que de fato envelhece sozinho é só a parte derivada de RECÊNCIA
(``days_since_last_order``, ``churn_risk``, ``rfm_segment``). Contagem, ticket
médio, favorito e canal preferido só mudam com um pedido novo, e esse caminho já
está coberto.

**Cadência: uma vez por dia, de madrugada.** A escada de recência do RFM é
7/30/90/180 dias (``contrib/insights/conf.py``) e o degrau mais fino do
``churn_risk`` fica na casa dos dias — nada se move em menos de um dia-calendário,
então rodar mais vezes mede a mesma coisa repetidas vezes, e caro.

Três decisões que o formato carrega:

1. **Cliente sem NENHUM pedido fica de fora.** Sem pedido, ``r=1, f=1, m=1`` cai em
   ``r<=2 and f<=2`` e o segmento sai ``lost`` — chamar de "Perdido" quem nunca
   comprou é mentira, não classificação. Quem não tem ``last_order_at`` não tem
   recência para envelhecer, e a varredura não o toca.
2. **Lote com teto por ciclo.** O ``maintenance_worker`` roda os comandos em SÉRIE:
   uma varredura de base inteira dentro de um ciclo atrasaria
   ``reconcile_payments`` e todo o resto atrás dela. Com teto, cada ciclo devolve o
   turno rápido e a janela da madrugada drena o resto.
3. **A marca d'água é o próprio dado.** ``calculated_at`` é ``auto_now``, então
   "quem está vencido" é uma query, não um estado novo para guardar (e desincronizar).
   Noite perdida por worker fora do ar se resolve sozinha na noite seguinte.

Uso::

    python manage.py recalculate_customer_insights            # varredura do ciclo
    python manage.py recalculate_customer_insights --force    # ignora a janela
    python manage.py recalculate_customer_insights --dry-run  # só conta
    python manage.py recalculate_customer_insights --all      # base inteira (backfill manual)
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Janela silenciosa (hora local, ``[início, fim)``). Madrugada porque a varredura
#: lê o snapshot de todo pedido de cada cliente — trabalho pesado não disputa
#: banco com o balcão aberto.
QUIET_HOURS = (3, 5)

#: Idade a partir da qual o insight é considerado vencido. Menor que 24h de
#: propósito: com exatamente 24h a varredura escorregaria alguns minutos por noite
#: e um dia sairia da janela. Maior que a janela (2h) para ninguém ser recalculado
#: duas vezes na mesma madrugada.
STALE_HOURS = 20

#: Teto de clientes por execução. Ver decisão (2) no topo: o worker é serial.
BATCH_LIMIT = 200


class Command(BaseCommand):
    help = "Recalcula os insights vencidos por recência (varredura diária de madrugada)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Recalcula a base inteira, ignorando janela e teto (backfill manual).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Roda fora da janela da madrugada.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Conta os vencidos sem recalcular nada.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=BATCH_LIMIT,
            help=f"Teto de clientes nesta execução (default {BATCH_LIMIT}).",
        )

    def handle(self, *args, **options):
        try:
            from shopman.guestman.contrib.insights import InsightService
            from shopman.guestman.contrib.insights.models import CustomerInsight
        except (ImportError, RuntimeError):
            # ``contrib.insights`` é opcional: sem ele não há o que varrer, e isso
            # não é falha do ciclo de manutenção.
            self.stdout.write("contrib.insights não instalado — nada a fazer.")
            return

        if options["all"]:
            total = InsightService.recalculate_all()
            logger.info("insights.sweep: recalculate_all processou %s clientes", total)
            self.stdout.write(self.style.SUCCESS(f"Base inteira: {total} cliente(s) recalculado(s)."))
            return

        if not (options["force"] or self._within_quiet_hours()):
            return

        vencidos = self._stale_queryset(CustomerInsight)
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(f"[dry-run] {vencidos.count()} insight(s) vencido(s).")
            )
            return

        refs = list(vencidos.values_list("customer__ref", flat=True)[: max(1, options["limit"])])
        feitos, pulados = self._recalculate(InsightService, refs)

        logger.info("insights.sweep: %s recalculado(s), %s pulado(s)", feitos, pulados)
        self.stdout.write(
            self.style.SUCCESS(f"{feitos} insight(s) recalculado(s), {pulados} pulado(s).")
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _within_quiet_hours(self) -> bool:
        """Hora LOCAL, não UTC: a madrugada que importa é a da padaria."""
        inicio, fim = QUIET_HOURS
        return inicio <= timezone.localtime().hour < fim

    def _stale_queryset(self, model):
        """Insights que podem ter mudado de recência desde o último cálculo.

        ``last_order_at__isnull=False`` é a decisão (1) do topo: sem pedido não há
        recência para envelhecer, e recalcular carimbaria "Perdido" em quem nunca
        comprou. Ordem por ``calculated_at`` crescente para que uma base maior que
        a capacidade de uma noite drene em ordem, sem deixar uma cauda faminta.
        """
        return (
            model.objects.filter(
                calculated_at__lt=timezone.now() - timedelta(hours=STALE_HOURS),
                last_order_at__isnull=False,
            )
            .order_by("calculated_at")
        )

    def _recalculate(self, service, refs: list[str]) -> tuple[int, int]:
        """Recalcula um a um: cliente desativado no meio não derruba o lote."""
        feitos = 0
        pulados = 0
        for ref in refs:
            try:
                service.recalculate(ref)
                feitos += 1
            except Exception:
                pulados += 1
                logger.warning("insights.sweep: pulou o cliente %s", ref, exc_info=True)
        return feitos, pulados
