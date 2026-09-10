"""
Management command: reconcile_payments

Reconcilia pedidos com status pending_payment cujo webhook de pagamento
pode ter sido perdido (timeout, reinicialização de servidor, falha de rede).

Lógica:
  0. Pergunta ao GATEWAY sobre todo pedido de cartão em aberto (sem recorte de
     `--since`): é a rede que não depende de o cliente voltar à tela.
  1. Busca Orders NEW/CONFIRMED criadas antes de `--since` atrás.
  2. Para cada uma, lê intent_ref em order.data["payment"].
  3. Consulta Payman: PaymentService.get(intent_ref). Intent sem gateway
     (cash/external, capturado na venda) é ignorado: não há webhook a perder.
  4. Se intent capturada → dispatch("on_paid") (pulado se a fase já completou).
  5. Se intent PENDING vencida (expires_at no passado — Payman não tem status
     "expired") → re-arma a directive payment.timeout, que é quem sabe cancelar
     com segurança (verifica o gateway antes, contra webhook perdido).
  6. Loga cada reconciliação com order.ref, intent_ref, action.

Idempotente: rodar duas vezes não gera estado inconsistente.

Usage:
    python manage.py reconcile_payments
    python manage.py reconcile_payments --since=4h
    python manage.py reconcile_payments --since=30m --dry-run
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

_SINCE_PATTERN = re.compile(r"^(\d+)(m|h|d)$")


def _parse_since(value: str) -> timedelta:
    """Parse '2h', '30m', '1d' → timedelta."""
    m = _SINCE_PATTERN.match(value.strip().lower())
    if not m:
        raise ValueError(f"Formato inválido para --since: '{value}'. Use ex: 2h, 30m, 1d.")
    amount, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


class Command(BaseCommand):
    help = "Reconcilia pedidos pending_payment cujo webhook pode ter sido perdido."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            default="2h",
            help="Reconcilia pedidos criados antes de N tempo atrás (ex: 2h, 30m, 1d). Default: 2h.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas lista o que seria feito, sem executar.",
        )

    def handle(self, *args, **options):
        from shopman.orderman.models import Order

        from shopman.shop.services import payment as payment_service

        since_str = options["since"]
        dry_run = options["dry_run"]

        try:
            since_delta = _parse_since(since_str)
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        cutoff = timezone.now() - since_delta

        gateway_updated = self._ask_the_gateway_about_open_hosted_checkouts(dry_run=dry_run)

        pending = Order.objects.filter(
            status__in=(Order.Status.NEW, Order.Status.ACCEPTED),
            created_at__lt=cutoff,
        )

        if not pending.exists():
            self.stdout.write(
                "Nenhum pedido pending_payment encontrado para reconciliar."
                + (f" (cartões atualizados pelo gateway: {gateway_updated})" if gateway_updated else "")
            )
            return

        reconciled = 0
        skipped = 0
        failures = 0

        for order in pending:
            payment_data = (order.data or {}).get("payment", {})
            intent_ref = payment_data.get("intent_ref")

            if not intent_ref:
                skipped += 1
                logger.debug("reconcile_payments: order %s sem intent_ref, ignorando.", order.ref)
                continue

            try:
                from shopman.payman import PaymentService
                intent = PaymentService.get(intent_ref)
            except Exception as exc:
                logger.warning(
                    "reconcile_payments: falha ao consultar intent %s (order %s): %s",
                    intent_ref, order.ref, exc,
                )
                skipped += 1
                continue

            if payment_service.settles_without_gateway(intent.method):
                # Dinheiro/cobrança externa: capturado na venda, sem webhook a
                # perder (ADR-022). Não há on_paid a recuperar; despachar aqui
                # mandaria "pagamento confirmado" para toda venda de balcão.
                skipped += 1
                logger.debug("reconcile_payments: order %s intent %s sem gateway, ignorando.", order.ref, intent_ref)
                continue

            if intent.status == "captured":
                from shopman.shop.lifecycle import phase_complete

                if phase_complete(order, "on_paid"):
                    # A fase já rodou até o fim (marcador durável) — re-despachar
                    # aqui só duplicaria alertas/eventos a cada ciclo.
                    skipped += 1
                    self.stdout.write(
                        f"order={order.ref} intent={intent_ref} → sem ação (on_paid já completo)"
                    )
                    continue
                action = "on_paid → flow dispatch"
                if not dry_run:
                    try:
                        from shopman.shop.lifecycle import dispatch
                        dispatch(order, "on_paid")
                        logger.info(
                            "reconcile_payments: order %s intent %s → on_paid dispatched",
                            order.ref, intent_ref,
                        )
                    except Exception as exc:
                        logger.debug("reconcile_payments.handle degraded; using fallback", exc_info=True)
                        failures += 1
                        from shopman.shop.services import observability

                        observability.record_payment_reconciliation_failure(
                            gateway=getattr(intent, "gateway", "") or "payman",
                            intent_ref=intent_ref,
                            order_ref=order.ref,
                            code="on_paid_dispatch_failed",
                            context={"action": "on_paid"},
                            exc=exc,
                        )
                        logger.error(
                            "reconcile_payments: falha ao despachar on_paid para order %s: %s",
                            order.ref, exc,
                        )
                        skipped += 1
                        continue
                reconciled += 1

            elif (
                intent.status == "pending"
                and intent.expires_at
                and intent.expires_at <= timezone.now()
            ):
                # Payman não tem status "expired": PIX vencido é intent PENDING
                # com expires_at no passado. Cancelar direto aqui seria pular a
                # checagem de gateway (webhook perdido + dinheiro capturado =
                # perda real do cliente) — re-armar a directive payment.timeout
                # entrega o cancel ao caminho canônico e seguro.
                action = "payment.timeout re-armada (intent vencida)"
                if not dry_run:
                    if self._rearm_payment_timeout(order, intent):
                        reconciled += 1
                    else:
                        action = "sem ação (payment.timeout já na fila)"
                        skipped += 1
                else:
                    reconciled += 1

            else:
                action = f"sem ação (intent.status={intent.status})"
                skipped += 1

            prefix = "[dry-run] " if dry_run else ""
            self.stdout.write(
                f"{prefix}order={order.ref} intent={intent_ref} → {action}"
            )

        from shopman.shop.services import observability

        observability.operational_event(
            "payment_reconciliation.completed",
            reconciled=reconciled,
            skipped=skipped,
            failures=failures,
            dry_run=dry_run,
            since=since_str,
        )

        summary = (
            f"Reconciliados: {reconciled} | Ignorados: {skipped} | Falhas: {failures} "
            f"| Cartões atualizados pelo gateway: {gateway_updated}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[dry-run] {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _ask_the_gateway_about_open_hosted_checkouts(self, *, dry_run: bool) -> int:
        """Pergunta ao gateway sobre todo pedido de CARTÃO ainda em aberto.

        ⚠️ **Esta é a rede que não depende de ninguém estar olhando.**

        A reconciliação contra webhook perdido existia em um lugar só: a
        leitura do acompanhamento, quando o cliente volta do Stripe. Enquanto
        for só ali, a verdade do sistema fica pendurada no navegador do
        cliente — quem paga e fecha a aba, ou paga num aparelho e some, deixa
        o pedido ACCEPTED com o avanço barrado por "Aguardando pagamento…", e
        do lado da loja não existe gesto nenhum capaz de destravar. O dinheiro
        está autorizado no gateway, o pão não sai, e ninguém sabe por quê.

        O passo roda a cada ciclo do ``maintenance_worker`` (5 min) e fica
        FORA do recorte de ``--since`` de propósito: esperar duas horas para
        perguntar sobre um pedido que o cliente pagou há dois minutos é a
        mesma pane, só mais lenta. Quem segura a mão é o throttle por pedido
        (``GATEWAY_RECHECK_SECONDS``), dentro de
        ``reconcile_with_gateway_if_due``.

        Só sessão hospedada (cartão da loja e link do balcão), pela mesma
        razão que a leitura da loja: o PIX já tem webhook, SSE e a checagem do
        vencimento. A sessão hospedada é o que leva o cliente para fora do site
        e volta sem sinal nenhum — e o link nem tem "volta": o cliente paga do
        celular, num aparelho que nunca abriu o acompanhamento.
        """
        from shopman.orderman.models import Order

        from shopman.shop.services import payment as payment_service

        open_hosted = Order.objects.filter(
            status__in=(Order.Status.NEW, Order.Status.ACCEPTED),
            data__payment__method__in=sorted(payment_service.HOSTED_CHECKOUT_METHODS),
        ).exclude(data__payment__intent_ref__isnull=True)

        # "Atualizada", não "liquidada": a resposta do gateway pode ser CAPTURA
        # (o dinheiro entrou) ou AUTORIZAÇÃO (o cliente pagou, a loja ainda não
        # cobrou). As duas mudam o que as telas mostram, e chamar as duas de
        # "liquidada" no relatório do worker seria dizer que entrou dinheiro que
        # não entrou.
        updated = 0
        for order in open_hosted:
            if payment_service.has_sufficient_captured_payment(order) is True:
                continue
            if dry_run:
                self.stdout.write(f"[dry-run] order={order.ref} → perguntaria ao gateway")
                continue
            try:
                if payment_service.reconcile_with_gateway_if_due(order):
                    updated += 1
                    logger.info("reconcile_payments: order %s atualizada pelo gateway", order.ref)
                    self.stdout.write(f"order={order.ref} → atualizada pelo gateway")
            except Exception:
                logger.warning(
                    "reconcile_payments: falha ao consultar gateway para order %s",
                    order.ref,
                    exc_info=True,
                )
        return updated

    def _rearm_payment_timeout(self, order, intent) -> bool:
        """Re-arma a directive payment.timeout para uma intent PENDING vencida.

        Cobre directive perdida (crash antes do create) ou concluída sem efeito
        (ex.: status incerto na rodada). O PaymentTimeoutHandler re-checa tudo,
        inclusive o gateway, antes de cancelar. Retorna True se enfileirou.
        """
        from shopman.orderman.models import Directive

        from shopman.shop.directives import PAYMENT_TIMEOUT, create_deduped

        dedupe_key = f"{PAYMENT_TIMEOUT}:{order.ref}:{intent.ref}"
        live = Directive.objects.filter(
            topic=PAYMENT_TIMEOUT,
            dedupe_key=dedupe_key,
            status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
        ).exists()
        if live:
            return False

        created = create_deduped(
            PAYMENT_TIMEOUT,
            payload={
                "order_ref": order.ref,
                "intent_ref": intent.ref,
                "expires_at": intent.expires_at.isoformat(),
            },
            dedupe_key=dedupe_key,
            available_at=timezone.now(),
        )
        if created is not None:
            logger.info(
                "reconcile_payments: order %s intent %s → payment.timeout re-armada",
                order.ref,
                intent.ref,
            )
        return created is not None
