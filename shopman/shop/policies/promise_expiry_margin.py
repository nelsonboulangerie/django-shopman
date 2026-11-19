"""A margem de validade da promessa: a sobra de hoje não lastreia encomenda.

Regra do dono (18/11/2026): "'a vitrine de hoje ainda vale amanhã': isso é
controverso! não oferecemos pães de um dia para o outro! eles não ficam
disponíveis para encomenda!"

Validade para VENDER no dia não é lastro para PROMETER para o dia. O pão de
hoje (validade até amanhã) só existe amanhã como "Ontem", com desconto e no
balcão; ele nunca cobre uma encomenda de amanhã. A promessa para uma data
futura se mede contra o que ainda terá validade DEPOIS dela, e a fornada
planejada para a própria data sempre conta (essa parte é do Stockman, em
``shopman.stockman.shelflife``). Mercadoria de validade longa (geleia, queijo,
lata) segue lastreando a encomenda até a véspera do vencimento.

A regra é do ALVO, não do canal: para hoje (ou sem data) vale só a margem que
o canal declara em ``ChannelConfig.stock.expiry_margin_days``, e o balcão segue
vendendo o pão de hoje e o de ontem.

Este é o ponto único. Toda leitura e toda reserva do orquestrador que leva
data passa a margem do canal por :func:`expiry_margin_for_target` antes de
falar com o Stockman: ``services.availability`` (``decide``, ``decide_many``,
``stock_on_dates``), ``adapters.stock`` (``create_hold`` e o livre por saldo de
``create_holds_up_to``) e ``projections.catalog_context``. Se uma delas ficar
de fora, a reserva acha o que a leitura negou, ou o contrário.
"""

from __future__ import annotations

from datetime import date

#: Dias de validade que o saldo precisa ter DEPOIS da data, quando a data é
#: futura. Um: o que está no último dia de validade na data não a lastreia.
FUTURE_TARGET_EXPIRY_MARGIN_DAYS = 1


def expiry_margin_for_target(
    expiry_margin_days: int | None,
    target_date: date | None,
    *,
    today: date | None = None,
) -> int:
    """A margem de validade que vale para a DATA que se lê ou reserva.

    ``expiry_margin_days`` é a margem do canal; ``target_date``, a data da
    leitura ou da reserva (``None`` = hoje). Para data futura a margem ganha
    :data:`FUTURE_TARGET_EXPIRY_MARGIN_DAYS`; para hoje ou data passada, volta
    a margem do canal sem mudança.
    """
    margin = max(0, int(expiry_margin_days or 0))
    if target_date is None:
        return margin
    if today is None:
        from django.utils import timezone

        today = timezone.localdate()
    if target_date > today:
        margin += FUTURE_TARGET_EXPIRY_MARGIN_DAYS
    return margin


__all__ = ["FUTURE_TARGET_EXPIRY_MARGIN_DAYS", "expiry_margin_for_target"]
