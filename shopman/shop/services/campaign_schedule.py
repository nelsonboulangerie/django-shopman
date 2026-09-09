"""Janela de publicação — a hora certa de falar com o cliente.

Uma fornada que sai às 5h30 não vira announcement às 5h30: ninguém está olhando, e o
conteúdo chega frio justamente quando a pessoa acorda. A
``Campaign.schedule`` declara as janelas em que a padaria quer aparecer;
um evento fora delas não perde o announcement, só espera a próxima abertura.

O vocabulário distingue **adiar** de **disparar**, sem overload — dois verbos diferentes
não podem morar na mesma chave:

    ADIAM (um evento aconteceu; a janela decide quando ele sai)
    {"type": "immediate"}                        # padrão — sai na hora
    {"type": "preferred_hours",
     "windows": [["07:00", "11:00"], ["15:00", "18:00"]],
     "weekdays": [0, 1, 2, 3, 4, 5]}             # 0 = segunda; ausente = todos

    DISPARAM (não há evento; o relógio É o evento)
    {"type": "once", "at": "2026-08-15T07:00:00-03:00"}
    {"type": "recurring",
     "windows": [["17:30", "18:30"]], "weekdays": [4, 5],
     "starts_on": "2026-08-10", "ends_on": "2026-09-30"}

``starts_on``/``ends_on`` cobrem "só neste período" sem inventar um terceiro tipo.

Puro e testável: só relógio e config, sem banco. Config quebrada nunca segura
um announcement — na dúvida publica agora, porque marketing não pode virar gargalo da
operação. A recíproca vale para os que DISPARAM, e com sinal oposto: config quebrada
não dispara nada, porque disparo surpresa alcança cliente de verdade.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone

from shopman.shop.services import marketing_time

PREFERRED_HOURS = "preferred_hours"
IMMEDIATE = "immediate"
#: Tipos que DISPARAM sozinhos: o relógio é o evento, não há fornada por trás.
ONCE = "once"
RECURRING = "recurring"
FIRING_TYPES = frozenset({ONCE, RECURRING})

#: Hoje + uma semana cheia: cobre qualquer combinação de ``weekdays``.
MAX_LOOKAHEAD_DAYS = 8

#: Para recorrente, olhar mais longe: `weekdays` pode ser um único dia e `starts_on`
#: pode estar semanas à frente. Um ano e pouco é teto generoso e ainda finito.
MAX_RECURRING_LOOKAHEAD_DAYS = 400

ALL_WEEKDAYS = frozenset(range(7))


def next_publish_at(schedule: dict | None, *, now: datetime | None = None):
    """Quando este announcement deve sair, ou ``None`` para "agora".

    Args:
        schedule: ``Campaign.schedule``.
        now: relógio injetável (default: agora).

    Returns:
        ``None`` quando o momento atual já serve (tipo ``immediate``, config
        ausente ou inválida, ou estamos dentro de uma janela). Caso contrário,
        o início da próxima janela, timezone-aware.
    """
    if not isinstance(schedule, dict) or schedule.get("type") != PREFERRED_HOURS:
        return None

    windows = _windows(schedule.get("windows"))
    weekdays = _weekdays(schedule.get("weekdays"))
    if not windows or not weekdays:
        return None

    try:
        timezone_name = marketing_time.schedule_timezone(schedule)
        now = marketing_time.local(now or timezone.now(), timezone_name=timezone_name)
    except ValueError:
        return None
    if _is_open(now, windows, weekdays):
        return None
    return _next_opening(now, windows, weekdays, timezone_name=timezone_name)


def describe(schedule: dict | None) -> str:
    """Resumo legível da janela, para o Admin e o card do gestor."""
    if not isinstance(schedule, dict) or schedule.get("type") != PREFERRED_HOURS:
        return "Publica na hora"
    windows = _windows(schedule.get("windows"))
    if not windows:
        return "Publica na hora"
    faixas = ", ".join(
        f"{start.strftime('%H:%M')} às {end.strftime('%H:%M')}" for start, end in windows
    )
    weekdays = _weekdays(schedule.get("weekdays"))
    timezone_suffix = (
        f" · {schedule['timezone']}" if schedule.get("timezone") else ""
    )
    if weekdays == ALL_WEEKDAYS:
        return f"Publica entre {faixas}{timezone_suffix}"
    dias = ", ".join(_WEEKDAY_NAMES[day] for day in sorted(weekdays))
    return f"Publica entre {faixas} ({dias}){timezone_suffix}"


_WEEKDAY_NAMES = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


# ── Cálculo ──────────────────────────────────────────────────────────


def _is_open(now: datetime, windows, weekdays) -> bool:
    if now.weekday() not in weekdays:
        return False
    return any(start <= now.time() < end for start, end in windows)


def _next_opening(now: datetime, windows, weekdays, *, timezone_name: str):
    """A primeira abertura de janela estritamente depois de ``now``."""
    for offset in range(MAX_LOOKAHEAD_DAYS):
        day = (now + timedelta(days=offset)).date()
        if day.weekday() not in weekdays:
            continue
        for start, _end in windows:
            try:
                candidate = marketing_time.resolve_wall_time(
                    datetime.combine(day, start),
                    timezone_name=timezone_name,
                    fold="earlier",
                )
            except ValueError:
                # A DST gap never shifts to an hour the operator did not choose.
                continue
            if candidate > now:
                return candidate
    return None


def _aware(value: datetime, *, timezone_name: str) -> datetime:
    if timezone.is_naive(value):
        return marketing_time.resolve_wall_time(
            value,
            timezone_name=timezone_name,
            fold="earlier",
        )
    return value


# ── Parsing tolerante ────────────────────────────────────────────────


def _windows(raw) -> list[tuple[time, time]]:
    """Pares ``[início, fim]`` válidos, ordenados. Entrada torta é ignorada.

    Janela que vira o dia (fim <= início) não existe aqui: padaria não publica
    de madrugada, e aceitar isso só criaria agendamento surpresa.
    """
    out: list[tuple[time, time]] = []
    for entry in raw or ():
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        start, end = _parse_time(entry[0]), _parse_time(entry[1])
        if start is None or end is None or end <= start:
            continue
        out.append((start, end))
    return sorted(out)


def _weekdays(raw) -> frozenset:
    """Dias permitidos (0 = segunda). Ausente ou inválido = a semana toda."""
    if raw is None:
        return ALL_WEEKDAYS
    days = set()
    for value in raw if isinstance(raw, (list, tuple, set)) else ():
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            days.add(day)
    return frozenset(days) if days else ALL_WEEKDAYS


def _parse_time(value) -> time | None:
    if isinstance(value, time):
        return value
    try:
        hour, _, minute = str(value).partition(":")
        return time(int(hour), int(minute or 0))
    except (TypeError, ValueError):
        return None


# ── Agendamento que DISPARA ──────────────────────────────────────────
#
# Os tipos acima adiam um announcement que já existe. Os de baixo criam a ocasião: sem
# fornada, sem estoque, só relógio. Por isso são válidos apenas com `Trigger.SCHEDULE` —
# um gatilho de evento com `type: once` seria duas causas para o mesmo anúncio.


def fires_on_its_own(schedule: dict | None) -> bool:
    """Este agendamento cria a ocasião, em vez de só adiar uma que já existe?"""
    return isinstance(schedule, dict) and schedule.get("type") in FIRING_TYPES


def next_occurrence(schedule: dict | None, *, now: datetime | None = None, after=None):
    """O próximo instante em que este agendamento deve disparar, ou ``None``.

    ``after`` permite pedir "a próxima depois desta", que é como a vassoura evita rearmar
    a mesma ocasião. ``None`` significa "nunca mais" — config inválida, período encerrado,
    ou ``once`` que já passou.

    Config torta devolve ``None`` de propósito: no caminho que ADIA, a dúvida publica
    agora; aqui a dúvida **não dispara**, porque disparo surpresa alcança cliente de
    verdade e não tem desfazer.
    """
    if not isinstance(schedule, dict):
        return None

    kind = schedule.get("type")
    try:
        timezone_name = marketing_time.schedule_timezone(schedule)
        now = marketing_time.local(now or timezone.now(), timezone_name=timezone_name)
        floor = (
            marketing_time.local(
                _aware(after, timezone_name=timezone_name),
                timezone_name=timezone_name,
            )
            if after
            else now
        )
    except ValueError:
        return None

    if kind == ONCE:
        moment = _parse_datetime(
            schedule.get("at"),
            timezone_name=timezone_name,
            strict_timezone=bool(schedule.get("timezone")),
        )
        if moment is None or moment <= floor:
            return None
        return moment

    if kind != RECURRING:
        return None

    windows = _windows(schedule.get("windows"))
    weekdays = _weekdays(schedule.get("weekdays"))
    if not windows:
        return None

    starts_on = _parse_date(schedule.get("starts_on"))
    ends_on = _parse_date(schedule.get("ends_on"))

    for offset in range(MAX_RECURRING_LOOKAHEAD_DAYS):
        day = (floor + timedelta(days=offset)).date()
        if day.weekday() not in weekdays:
            continue
        if starts_on and day < starts_on:
            continue
        if ends_on and day > ends_on:
            return None
        for start, _end in windows:
            try:
                candidate = marketing_time.resolve_wall_time(
                    datetime.combine(day, start),
                    timezone_name=timezone_name,
                    # Repeated recurring hours fire once, at the earlier occurrence.
                    fold="earlier",
                )
            except ValueError:
                # A nonexistent wall time is skipped, never silently shifted.
                continue
            if candidate > floor:
                return candidate
    return None


def describe_occurrence(schedule: dict | None) -> str:
    """Resumo legível de um agendamento que dispara, para o card do gestor."""
    if not isinstance(schedule, dict):
        return ""
    kind = schedule.get("type")
    if kind == ONCE:
        try:
            timezone_name = marketing_time.schedule_timezone(schedule)
        except ValueError:
            return "Timezone inválido"
        moment = _parse_datetime(
            schedule.get("at"),
            timezone_name=timezone_name,
            strict_timezone=bool(schedule.get("timezone")),
        )
        if moment is None:
            return "Data inválida"
        localized = marketing_time.local(moment, timezone_name=timezone_name)
        suffix = f" ({timezone_name})" if schedule.get("timezone") else ""
        return f"Uma vez, em {localized.strftime('%d/%m às %H:%M')}{suffix}"
    if kind != RECURRING:
        return ""

    windows = _windows(schedule.get("windows"))
    if not windows:
        return "Horário inválido"
    faixas = ", ".join(start.strftime("%H:%M") for start, _end in windows)
    weekdays = _weekdays(schedule.get("weekdays"))
    dias = (
        "todo dia" if weekdays == ALL_WEEKDAYS
        else ", ".join(_WEEKDAY_NAMES[day] for day in sorted(weekdays))
    )
    texto = f"{dias}, às {faixas}"
    ends_on = _parse_date(schedule.get("ends_on"))
    if ends_on:
        texto += f" (até {ends_on.strftime('%d/%m')})"
    if schedule.get("timezone"):
        texto += f" · {schedule['timezone']}"
    # O resumo abre a linha do card sozinho: sentence case, seja "Todo dia" ou "Seg, qua".
    return texto[:1].upper() + texto[1:]


def _parse_datetime(value, *, timezone_name: str, strict_timezone: bool = False):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            from django.utils.dateparse import parse_datetime

            parsed = parse_datetime(str(value))
        except (TypeError, ValueError):
            return None
    if parsed is None:
        return None
    try:
        if timezone.is_naive(parsed):
            return marketing_time.resolve_wall_time(
                parsed,
                timezone_name=timezone_name,
            )
        if strict_timezone:
            return marketing_time.validate_named_instant(
                parsed,
                timezone_name=timezone_name,
            )
        return parsed
    except ValueError:
        return None


def _parse_date(value):
    if value is None:
        return None
    try:
        from django.utils.dateparse import parse_date

        return parse_date(str(value))
    except (TypeError, ValueError):
        return None
