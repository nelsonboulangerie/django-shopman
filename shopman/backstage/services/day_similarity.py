"""Dias parecidos — a definição de "período compatível".

Quando alguém pergunta "o que esperar para a próxima quarta?", a resposta honesta
não vem de um modelo: vem de **olhar as quartas parecidas**. Todo o resto do
"o que esperar" é aritmética em cima desta lista.

Os ingredientes já existiam espalhados — contexto do dia (feriado, clima),
expediente congelado, dias em que a casa não abriu, dias atrapalhados por
episódio. O que faltava era **compor**: uma função só que diga quais dias do
passado se parecem com um dia-alvo, e que declare o que precisou abrir mão para
chegar a uma amostra utilizável.

Duas distinções governam o módulo, e confundi-las seria mentir de formas
diferentes:

- **Afrouxado** ≠ **indisponível.** Afrouxado é critério que existia e foi
  abandonado porque a amostra estrita ficou pequena demais. Indisponível é
  critério que nunca pôde ser aplicado (sem calendário carregado, sem estações
  declaradas, alvo sem temperatura conhecida). O primeiro é uma escolha do
  cálculo; o segundo é uma ausência do mundo.
- **Menos parecido** ≠ **inválido.** Dia fechado e dia atrapalhado saem em
  qualquer nível de afrouxamento: eles não são dias pouco parecidos, são dias
  que não ensinam nada. Vender pouco sem energia não é procura baixa.

E a regra que fecha: **amostra pequena não vira número pequeno, vira ausência.**
Abaixo do mínimo, mesmo depois de afrouxar tudo, ``enough`` sai falso e quem
chama deve dizer "não temos dias parecidos o bastante" em vez de responder com
três dias. É o mesmo comportamento que a fórmula de produção já tem quando a
confiança não se sustenta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Do mais forte ao mais fraco. Sábado não é terça (dia da semana); uma sexta que
# é véspera de feriado não é uma sexta (tipo de dia); julho não é janeiro
# (estação); um sábado de 32 °C não é um sábado de 16 °C (temperatura).
CRITERIA: tuple[str, ...] = ("weekday", "day_kind", "season", "temperature")

# A escada de afrouxamento: o critério mais fraco cai primeiro. O dia da semana
# não está aqui de propósito — abrir mão dele descaracterizaria a pergunta.
RELAX_ORDER: tuple[str, ...] = ("temperature", "season", "day_kind")

MINIMUM_SAMPLE = 5
DEFAULT_WINDOW_DAYS = 730  # dois anos: o alcance do histórico que a casa tem


@dataclass(frozen=True)
class DayProfile:
    """O que caracteriza um dia. String vazia = não sabemos, nunca um default."""

    date: date
    weekday: int
    day_kind: str = ""
    season: str = ""
    temperature: str = ""

    def value(self, criterion: str) -> str:
        if criterion == "weekday":
            return str(self.weekday)
        return getattr(self, criterion, "")


@dataclass(frozen=True)
class DayPool:
    """O que se sabe sobre uma janela de dias, lido de uma vez só.

    Perguntar "o que esperar deste mês" são trinta perguntas de dia, e cada uma
    precisa do mesmo contexto e da mesma lista de dias atrapalhados. Sem isto
    seriam sessenta consultas idênticas ao banco.
    """

    since: date
    until: date
    contexts: dict
    disrupted: frozenset


def build_pool(since: date, until: date) -> DayPool:
    return DayPool(
        since=since,
        until=until,
        contexts=_contexts_between(since, until),
        disrupted=_disrupted_days(since, until),
    )


@dataclass(frozen=True)
class SimilarDays:
    """Os dias parecidos, e a prestação de contas de como se chegou a eles."""

    target: date
    days: tuple[date, ...]
    applied: tuple[str, ...]
    relaxed: tuple[str, ...]
    unavailable: tuple[str, ...]
    window_from: date
    window_to: date
    candidates: int
    excluded_closed: int
    excluded_disrupted: int

    @property
    def enough(self) -> bool:
        return len(self.days) >= MINIMUM_SAMPLE

    @property
    def sample_size(self) -> int:
        return len(self.days)


def similar_days(
    target: date,
    *,
    since: date | None = None,
    until: date | None = None,
    criteria: tuple[str, ...] = CRITERIA,
    minimum: int = MINIMUM_SAMPLE,
    pool: DayPool | None = None,
) -> SimilarDays:
    """Dias de ``[since, until]`` parecidos com ``target``.

    ``until`` nunca passa de ontem: o dia de hoje ainda não terminou e entraria
    na amostra pela metade.
    """
    from django.utils import timezone

    today = timezone.localdate()
    if pool is not None:
        since, until = pool.since, pool.until
    until = min(until or today - timedelta(days=1), today - timedelta(days=1))
    since = since or until - timedelta(days=DEFAULT_WINDOW_DAYS)
    if since > until:
        return SimilarDays(
            target=target, days=(), applied=(), relaxed=(), unavailable=criteria,
            window_from=since, window_to=until,
            candidates=0, excluded_closed=0, excluded_disrupted=0,
        )

    contexts = pool.contexts if pool is not None else _contexts_between(since, until)
    target_profile = profile_for(target)

    # Critério indisponível é o que o ALVO não sabe responder: sem calendário
    # carregado não há tipo de dia para casar, sem estação declarada não há
    # estação, e um dia futuro não tem temperatura medida. Perguntar por eles
    # devolveria zero dias parecidos e pareceria uma amostra ruim, quando na
    # verdade é uma pergunta que não pôde ser feita.
    unavailable = tuple(c for c in criteria if not target_profile.value(c))
    usable = tuple(c for c in criteria if c not in unavailable)

    candidates: list[DayProfile] = []
    closed: list[DayProfile] = []
    interrupted: list[DayProfile] = []
    disrupted = pool.disrupted if pool is not None else _disrupted_days(since, until)

    day = since
    while day <= until:
        if day == target:
            day += timedelta(days=1)
            continue
        profile = profile_for(day, context=contexts.get(day))
        if not _was_open(day, contexts.get(day)):
            closed.append(profile)
        elif day in disrupted:
            interrupted.append(profile)
        else:
            candidates.append(profile)
        day += timedelta(days=1)

    applied = usable
    relaxed: list[str] = []
    matched = _matching(candidates, target_profile, applied)
    # Afrouxa um degrau por vez, sempre o critério mais fraco ainda de pé, e só
    # enquanto a amostra não se sustenta. Parar no primeiro nível suficiente
    # preserva o máximo de semelhança que a amostra permite.
    for criterion in RELAX_ORDER:
        if len(matched) >= minimum:
            break
        if criterion not in applied:
            continue
        applied = tuple(c for c in applied if c != criterion)
        relaxed.append(criterion)
        matched = _matching(candidates, target_profile, applied)

    # Os excluídos são contados DEPOIS, e só entre os que teriam se parecido:
    # perguntando por uma quarta, os domingos fechados do calendário não são
    # dias perdidos — nunca foram candidatos. Contá-los diria "cem dias ficaram
    # de fora" para uma amostra que jamais os teria, o que assusta sem informar.
    return SimilarDays(
        target=target,
        days=tuple(p.date for p in matched),
        applied=applied,
        relaxed=tuple(relaxed),
        unavailable=unavailable,
        window_from=since,
        window_to=until,
        candidates=len(candidates),
        excluded_closed=len(_matching(closed, target_profile, applied)),
        excluded_disrupted=len(_matching(interrupted, target_profile, applied)),
    )


def profile_for(day: date, *, context=None) -> DayProfile:
    """O perfil de um dia. Serve para o alvo (futuro) e para os candidatos."""
    if context is None:
        from shopman.backstage.models import DayContext

        context = DayContext.objects.filter(date=day).first()
    return DayProfile(
        date=day,
        weekday=day.weekday(),
        day_kind=context.day_kind if context else "",
        season=season_of(day),
        temperature=temperature_band(context.temp_max_c) if context else "",
    )


def temperature_band(temp_max_c) -> str:
    """Faixa de 5 °C. Vazio quando não há medição — nunca uma faixa qualquer.

    É a mesma régua do explorador: o recorte de temperatura precisa significar a
    mesma coisa nas duas telas, senão "dias de 25 a 29 °C" quer dizer uma coisa
    numa e outra na outra.
    """
    if temp_max_c is None:
        return ""
    return f"{int(temp_max_c // 5 * 5):03d}"


def season_of(day: date) -> str:
    """A estação declarada pela casa para o mês do dia.

    Quem define estação é a configuração de produção, que a casa já preenche —
    o B.I. não inventa estações meteorológicas próprias para discordar dela.
    Sem estações declaradas, o critério simplesmente não existe.
    """
    try:
        from shopman.shop.production_config import ProductionConfig

        seasons = ProductionConfig.load().suggestion.seasons or {}
    except Exception:
        logger.debug("configuração de estações indisponível", exc_info=True)
        return ""
    for name, months in seasons.items():
        if isinstance(months, list) and day.month in months:
            return str(name)
    return ""


def untrustworthy_days(*, since: date, until: date) -> frozenset[date]:
    """Dias que não ensinam demanda: a casa não abriu, ou o dia foi atrapalhado.

    É o caso degenerado da semelhança — os critérios de exclusão sem os de
    parecença. Mora aqui, e não em dois lugares, porque a tela de plano e o B.I.
    não podem discordar sobre o que foi a última quarta.
    """
    contexts = _contexts_between(since, until)
    disrupted = _disrupted_days(since, until)
    days = set(disrupted)
    day = since
    while day <= until:
        if not _was_open(day, contexts.get(day)):
            days.add(day)
        day += timedelta(days=1)
    return frozenset(days)


def _matching(
    candidates: list[DayProfile], target: DayProfile, criteria: tuple[str, ...]
) -> list[DayProfile]:
    return [
        profile
        for profile in candidates
        if all(profile.value(c) == target.value(c) for c in criteria)
    ]


def _contexts_between(since: date, until: date) -> dict:
    from shopman.backstage.models import DayContext

    return {
        row.date: row for row in DayContext.objects.filter(date__range=(since, until))
    }


def _was_open(day: date, context) -> bool:
    """A casa abriu neste dia?

    Prioridade para o **carimbo** do dia (§12 do mapa de insights): ele guarda o
    expediente realmente praticado, e é imune a mudanças posteriores no cadastro.
    Dia sem carimbo — anterior à medição — cai no calendário de hoje, que é
    aproximado mas melhor que supor que a casa abriu.
    """
    if context is not None and context.open_minutes is not None:
        return context.open_minutes > 0
    try:
        from shopman.shop.services.business_calendar import is_open_on

        return is_open_on(day)
    except Exception:
        logger.debug("calendário indisponível para %s", day, exc_info=True)
        return True


def _disrupted_days(since: date, until: date) -> frozenset[date]:
    try:
        from shopman.backstage.services.episodes import disrupted_days

        return disrupted_days(since=since, until=until)
    except Exception:
        logger.debug("episódios indisponíveis", exc_info=True)
        return frozenset()
