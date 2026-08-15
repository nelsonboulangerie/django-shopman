"""Detecta sozinho que o dia teve algo estranho — e só então pergunta.

O sistema não sabe que faltou luz. Mas sabe que, num dia de expediente normal,
a loja parou de vender por duas horas seguidas e depois voltou; e sabe que uma
fornada planejada não saiu. Isso basta para levantar a mão e perguntar **uma
coisa só** no fechamento: *o que houve?*

Por que detectar em vez de pedir para anotar: ninguém lembra de registrar às
17h que faltou energia às 14h, e um formulário em branco todo dia vira campo
morto — pior que não ter, porque a ausência de registro passaria a ser lida
como "não houve nada".

Cada detector é honesto sobre o que mediu (``detected_signal``) e **nunca**
chuta o motivo: o motivo fica vazio até alguém dizer.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Régua padrão quando a loja não configurou: duas horas sem uma única venda
# dentro do expediente. É só um ponto de partida — o número certo depende do
# movimento da casa (num dia de jogo grande a rua some por mais tempo e isso é
# normal), por isso ele é editável em Configuração › Produção.
DEFAULT_SALES_SILENCE_MINUTES = 120


def sales_silence_minutes() -> int:
    """A régua da casa. ``0`` desliga o detector de silêncio."""
    try:
        from shopman.shop.production_config import ProductionConfig

        return int(ProductionConfig.load().episodes.sales_silence_minutes)
    except Exception:
        logger.debug("config de episódios indisponível; usando o padrão", exc_info=True)
        return DEFAULT_SALES_SILENCE_MINUTES


def detect_for_day(day: date) -> list:
    """Roda os detectores do dia e devolve os episódios levantados (idempotente)."""
    found = []
    for detector in (_detect_sales_silence, _detect_closed_when_expected, _detect_missed_batch):
        try:
            found.extend(detector(day))
        except Exception:
            logger.debug("detector %s falhou em %s", detector.__name__, day, exc_info=True)
    return found


def _open_window(day: date):
    """A janela em que a casa esteve aberta, do carimbo do dia."""
    from shopman.backstage.models import DayContext

    context = DayContext.objects.filter(date=day).first()
    if context is None or not context.open_minutes or not context.opens_at:
        return None
    tz = timezone.get_current_timezone()
    return (
        datetime.combine(day, context.opens_at, tzinfo=tz),
        datetime.combine(day, context.closes_at, tzinfo=tz),
    )


def _sales_times(day: date) -> list:
    from shopman.orderman.models import Order

    tz = timezone.get_current_timezone()
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return sorted(
        timezone.localtime(created_at)
        for created_at in Order.objects.filter(created_at__range=(start, end))
        .exclude(status__in=(Order.Status.CANCELLED, Order.Status.RETURNED))
        .values_list("created_at", flat=True)
    )


def _detect_sales_silence(day: date) -> list:
    """Vendeu, parou por horas, voltou a vender — algo aconteceu no meio.

    Exige venda ANTES e DEPOIS do silêncio: assim o começo devagar da manhã e a
    ponta morta do fim da tarde não viram episódio.
    """
    limite = sales_silence_minutes()
    if limite <= 0:
        return []  # a casa desligou este detector
    window = _open_window(day)
    if window is None:
        return []
    opens_at, closes_at = window
    sales = [stamp for stamp in _sales_times(day) if opens_at <= stamp <= closes_at]
    if len(sales) < 2:
        return []

    episodes = []
    for previous, following in zip(sales, sales[1:], strict=False):
        gap = (following - previous).total_seconds() / 60
        if gap >= limite:
            episodes.append(
                _raise(
                    detector="sales_silence",
                    started_at=previous,
                    ended_at=following,
                    signal=(
                        f"nenhuma venda entre {previous:%H:%M} e {following:%H:%M}"
                    ),
                )
            )
    return [episode for episode in episodes if episode is not None]


def _detect_closed_when_expected(day: date) -> list:
    """A casa deveria abrir e não vendeu nada o dia inteiro."""
    window = _open_window(day)
    if window is None:
        return []
    if _sales_times(day):
        return []
    opens_at, closes_at = window
    episode = _raise(
        detector="no_sales_at_all",
        started_at=opens_at,
        ended_at=closes_at,
        signal="dia de expediente sem nenhuma venda",
    )
    return [episode] if episode else []


def _detect_missed_batch(day: date) -> list:
    """Fornada planejada que não saiu — o forno não rodou como o plano dizia."""
    from shopman.craftsman.models import WorkOrder

    pending = list(
        WorkOrder.objects.filter(target_date=day, status=WorkOrder.Status.PLANNED)
        .select_related("recipe")[:5]
    )
    if not pending:
        return []
    window = _open_window(day)
    if window is None:
        return []
    nomes = ", ".join(wo.recipe.name for wo in pending)
    episode = _raise(
        detector="missed_batch",
        started_at=window[0],
        ended_at=window[1],
        signal=f"fornada planejada não saiu: {nomes}",
    )
    return [episode] if episode else []


def _raise(*, detector: str, started_at, ended_at, signal: str):
    """Levanta a mão sem chutar o motivo. Idempotente por (detector, início)."""
    from shopman.backstage.models import OperationEpisode

    episode, created = OperationEpisode.objects.get_or_create(
        detector=detector,
        started_at=started_at,
        defaults={"ended_at": ended_at, "detected_signal": signal},
    )
    return episode if created else None


def pending_for_day(day: date) -> list:
    """Episódios do dia esperando explicação — é o que o fechamento pergunta."""
    from shopman.backstage.models import EpisodeStatus, OperationEpisode

    tz = timezone.get_current_timezone()
    start = datetime.combine(day, time.min, tzinfo=tz)
    return list(
        OperationEpisode.objects.filter(
            status=EpisodeStatus.SUSPECTED,
            started_at__range=(start, start + timedelta(days=1)),
        ).order_by("started_at")
    )


def answer(episode_id: int, *, kind_ref: str, actor: str, note: str = ""):
    """Registra o que houve — ou que não houve nada (``kind_ref`` vazio)."""
    from shopman.backstage.models import (
        EpisodeStatus,
        OperationEpisode,
        OperationEpisodeKind,
    )

    episode = OperationEpisode.objects.get(pk=episode_id)
    if kind_ref:
        episode.kind = OperationEpisodeKind.objects.get(ref=kind_ref, is_active=True)
        episode.status = EpisodeStatus.CONFIRMED
    else:
        episode.kind = None
        episode.status = EpisodeStatus.DISMISSED
    episode.note = note[:200]
    episode.resolved_by = actor
    episode.resolved_at = timezone.now()
    episode.save()
    return episode


def disrupted_days(*, since: date, until: date) -> frozenset:
    """Dias que não devem ensinar demanda.

    Entram os confirmados cujo tipo diz que atrapalhou a venda **e** os que
    ninguém explicou: o sinal existiu, e é mais seguro não aprender com um dia
    estranho do que aprender errado. Sai apenas o que foi descartado como falso
    alarme — porque aí alguém olhou e disse que não houve nada.
    """
    from shopman.backstage.models import EpisodeStatus, OperationEpisode

    tz = timezone.get_current_timezone()
    start = datetime.combine(since, time.min, tzinfo=tz)
    end = datetime.combine(until + timedelta(days=1), time.min, tzinfo=tz)
    episodes = OperationEpisode.objects.filter(
        started_at__range=(start, end)
    ).exclude(status=EpisodeStatus.DISMISSED).select_related("kind")
    return frozenset(
        episode.day for episode in episodes if episode.affects_demand
    )
