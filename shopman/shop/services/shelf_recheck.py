"""A reserva que vence devolve o saldo à vitrine no próprio prazo (#2785).

O Stockman já tira a reserva vencida da conta no instante do ``expires_at``, sem
escrever nada: ``HoldQuerySet.active()`` filtra ``expires_at >= now``, e é o que a
disponibilidade lê. O ``release_expired`` que o ``maintenance_worker`` roda a cada
cinco minutos é só higiene de status. O saldo volta no prazo, mas ninguém avisa: quem
olha a vitrine ou a sacola só via o item voltar no próximo gesto.

Quem sabe a hora certa é o shop, que dá o prazo às reservas: a sacola renova o prazo
de todas as suas reservas a cada gesto (``availability.bump_session_hold_expiry``,
que também cobre a reserva que acabou de nascer), e o adapter estende reservas
avulsas (``adapters.stock.extend_hold``). Ao gravar o prazo, ele agenda (Directive
``stock.shelf_recheck``) a releitura dos SKUs para o próprio prazo. Na hora, o
handler confere, SKU a SKU, se uma reserva de fato venceu naquele intervalo e só
então publica o mesmo ``stock-update`` da reserva salva. A renovação seguinte move o
prazo para frente: a releitura antiga encontra a reserva viva e não publica nada.

Os prazos caem em janelas de :data:`BUCKET_SECONDS`: uma releitura por sacola (ou
reserva avulsa) por janela, no fim dela.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from django.db.models import F, Q
from django.utils import timezone

#: Largura da janela dos prazos. O aviso chega no máximo isso depois do vencimento, e
#: os gestos de uma sacola dentro dela viram uma releitura só.
BUCKET_SECONDS = 15


def bucket_end(expires_at: datetime) -> datetime:
    """O fim da janela em que ``expires_at`` cai (o próprio, se já estiver na borda)."""
    epoch = int(expires_at.timestamp())
    if epoch % BUCKET_SECONDS == 0 and expires_at.microsecond == 0:
        return expires_at
    return datetime.fromtimestamp(epoch - epoch % BUCKET_SECONDS + BUCKET_SECONDS, tz=expires_at.tzinfo)


def schedule(skus: Iterable[str], expires_at: datetime | None, *, scope: str) -> None:
    """Agenda a releitura dos ``skus`` para o fim da janela do prazo.

    ``scope`` identifica quem gravou o prazo (a sacola, a reserva avulsa): o mesmo
    escopo na mesma janela é uma releitura só. Prazo nulo ou passado, ou nenhum SKU:
    nada.
    """
    wanted = sorted({sku for sku in skus if sku})
    if not wanted or expires_at is None or expires_at <= timezone.now():
        return
    from shopman.shop.directives import STOCK_SHELF_RECHECK, create_deduped

    at = bucket_end(expires_at)
    create_deduped(
        STOCK_SHELF_RECHECK,
        payload={"skus": wanted, "at": at.isoformat()},
        dedupe_key=f"{scope}:{int(at.timestamp())}",
        available_at=at,
    )


def lapsed_within(sku: str, start: datetime, end: datetime) -> bool:
    """Alguma reserva do ``sku`` venceu em ``(start, end]`` sem ter sido entregue ou solta antes?

    Conta a viva com o prazo no intervalo e a que a varredura já soltou depois do prazo.
    A que a cliente tirou da sacola antes do prazo não conta: ela avisou ao sair.
    """
    from shopman.stockman.models import Hold, HoldStatus

    return (
        Hold.objects.filter(sku=sku, expires_at__gt=start, expires_at__lte=end)
        .filter(
            Q(status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED])
            | Q(status=HoldStatus.RELEASED, resolved_at__gte=F("expires_at"))
        )
        .exists()
    )
