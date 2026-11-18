"""Courier sync handler — polling do status da corrida (Directive ``courier.sync``).

Fallback do webhook da Machine (e única via enquanto o webhook não estiver
homologado): heartbeat auto-reagendável por pedido, no padrão do
``production.late_check``. Cada batida lê a corrida inteira
(``adapter.read_ride``: status, entregador, previsão de chegada à loja,
coleta, viagem, valor) e aplica pelo funil ``courier.apply_snapshot``. Para
sozinho quando a corrida chega a um status terminal (F/N/C), quando a corrida
some do pedido, quando passa de ``courier.MAX_POLL_HOURS`` ou quando o polling
é desligado (``Shop.defaults.delivery.courier_poll_seconds = 0``). Leitura que
falha aparece na tela (``courier.sync``) e vira aviso ao operador.

Webhook e polling convergem no mesmo funil (``courier.apply_status``), que é
idempotente — receber o mesmo status pelas duas vias é inofensivo.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive, Order

from shopman.shop.directives import COURIER_SYNC

logger = logging.getLogger(__name__)


class CourierSyncHandler:
    """Consulta o status da corrida no adapter e aplica ao pedido."""

    topic = COURIER_SYNC

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.adapters import get_adapter
        from shopman.shop.adapters.courier_machine import TERMINAL_STATUSES, CourierError, CourierRateLimited
        from shopman.shop.services import courier

        payload = message.payload or {}
        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return

        block = courier.get_block(order)
        if not block.get("id_mch"):
            # O primeiro pedido já encerrou a corrida (N/C arquiva e tira o
            # ``id_mch``), mas a batida é uma só para a corrida inteira: quem
            # ainda a carrega recebe o mesmo fim, senão fica "com corrida" para
            # sempre, com a letra, o troco e a maquininha presos.
            self._release_stranded(order)
            return
        # F may already be durable while the local delivery/custody step failed.
        # Recover before deciding the terminal heartbeat has nothing left to do.
        # Os outros pedidos da corrida, lidos ANTES da leitura: o N/C arquiva a
        # corrida no primeiro pedido, e depois dele ninguém mais saberia quem
        # estava nela (os outros ficariam presos "com corrida", com a custódia fora).
        companions = courier.ride_companions(order)
        courier.recover_local_status(order, ride_id=block["id_mch"])
        for other in companions:
            courier.recover_local_status(other, ride_id=block["id_mch"])
        if block.get("status") in TERMINAL_STATUSES:
            return

        adapter = get_adapter("courier")
        if adapter is None:
            return

        seconds = courier.poll_seconds()
        ride_id = block["id_mch"]
        if courier.poll_expired(block):
            logger.warning("courier.sync_expired order=%s id_mch=%s", order.ref, ride_id)
            return

        try:
            read_ride = getattr(adapter, "read_ride", None)
            snapshot = read_ride(ride_id) if read_ride else {"status": adapter.get_status(ride_id)}
        except CourierRateLimited as exc:
            # A TaOn limitou as chamadas: não é a corrida que parou de informar,
            # é a casa que tem de esperar. Não conta como falha de leitura (sem
            # "sem notícias" na tela, sem aviso) e a próxima batida respeita o
            # prazo que a TaOn pediu.
            logger.warning("courier.sync_rate_limited order=%s id_mch=%s retry_after=%s",
                           order.ref, ride_id, exc.retry_after)
            if seconds > 0:
                courier.schedule_sync(order, delay_seconds=max(seconds, exc.retry_after))
            return
        except CourierError as exc:
            # A batida não "falha" (o heartbeat segue), mas não fica calada: a
            # tela do Gestor diz desde quando a TaOn não informa a corrida, e
            # depois de algumas batidas vira aviso ao operador. Em 13/10/2026 a
            # primeira corrida real ficou parada em D por 30 min só com WARNING
            # no log (``solicitacaoStatus`` → 400 [67] a cada minuto).
            logger.warning(
                "courier.sync_failed order=%s id_mch=%s: %s",
                order.ref, ride_id, exc,
            )
            courier.record_sync_failure(order, exc, ride_id=ride_id)
            if seconds > 0:
                courier.schedule_sync(order, delay_seconds=seconds)
            return

        if snapshot:
            courier.apply_snapshot(order, snapshot, source="poll")
            # Corrida com várias paradas: a mesma leitura vale para os outros pedidos dela.
            for other in companions:
                other.refresh_from_db()
                courier.apply_snapshot(other, snapshot, source="poll")

        block = courier.get_block(order)
        still_active = bool(block.get("id_mch")) and block.get("status") not in TERMINAL_STATUSES
        if still_active and seconds > 0:
            courier.schedule_sync(order, delay_seconds=seconds)
        elif not block.get("id_mch"):
            # A leitura encerrou a corrida neste pedido; se algum companheiro não
            # recebeu o fim (falha local no meio), ele recebe agora.
            self._release_stranded(order)

    @staticmethod
    def _release_stranded(order) -> None:
        from shopman.shop.services import courier

        status, stuck = courier.stranded_companions(order)
        if not stuck:
            return
        logger.warning("courier.sync_stranded lead=%s status=%s orders=%s", order.ref, status,
                       ",".join(other.ref for other in stuck))
        if status in ("N", "C"):
            for other in stuck:
                courier.apply_status(other, status, source="poll:reconcile")
            return
        # O fim do primeiro não diz o da corrida (letra inesperada no histórico):
        # a batida passa a ser de quem ainda a carrega, e a central responde.
        courier.schedule_sync(stuck[0], delay_seconds=0)

__all__ = ["CourierSyncHandler"]
