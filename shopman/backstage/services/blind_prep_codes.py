"""Comando idempotente de alocação dos códigos cegos da pesagem.

A projection apenas lê ``BlindPrepCode``. A criação fica neste command-side
service e só é acionada por POST, para que GET, polling e pré-render SSR sejam
observacionais.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date, timedelta

from django.db import IntegrityError, transaction

from shopman.backstage.models import BlindPrepCode

logger = logging.getLogger(__name__)

# Alfabeto ultra legível: 1 letra + 1 número, sem 0/1/O/I.
BLIND_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
BLIND_DIGITS = "23456789"

# Famílias sonoras (pt-BR): quando um número reaparece, a letra deve vir de
# outra família sempre que houver espaço ("Z7" veta "D7", mas libera "M7").
BLIND_LETTER_FAMILIES = {
    **dict.fromkeys("BCDGPTVZ", "ê"),
    "M": "êm",
    "N": "êm",
    "F": "és",
    "S": "és",
    "K": "cá",
    "Q": "cá",
    "L": "él",
    "R": "él",
}


def allocate_blind_prep_codes(*, recipe_refs: tuple[str, ...], selected_date: date) -> dict[str, str]:
    """Aloca uma vez e devolve o mapa completo pedido pelo chamador."""
    normalized = tuple(dict.fromkeys(ref for ref in recipe_refs if ref))
    for recipe_ref in normalized:
        _allocate_one(recipe_ref=recipe_ref, selected_date=selected_date)
    return dict(
        BlindPrepCode.objects.filter(date=selected_date, recipe_ref__in=normalized).values_list("recipe_ref", "code")
    )


def blind_prep_code(recipe_ref: str, selected_date: date) -> str:
    """Compatibilidade interna do command-side para alocar um único preparo."""
    return _allocate_one(recipe_ref=recipe_ref, selected_date=selected_date)


def _allocate_one(*, recipe_ref: str, selected_date: date) -> str:
    """Aloca o identificador estável de um preparo sem revelar a receita.

    Letras não repetem nos primeiros 24 preparos; dígitos não repetem nos oito
    primeiros e depois evitam a mesma família sonora. O código completo não
    repete na janela de dias úteis adjacentes.
    """
    existing = BlindPrepCode.objects.filter(date=selected_date, recipe_ref=recipe_ref).first()
    if existing:
        return existing.code

    window = _blind_window(selected_date)
    space = [letter + digit for letter in BLIND_LETTERS for digit in BLIND_DIGITS]
    for _attempt in range(len(space)):
        window_taken = set(BlindPrepCode.objects.filter(date__in=window).values_list("code", flat=True))
        day_codes = set(BlindPrepCode.objects.filter(date=selected_date).values_list("code", flat=True))
        day_letters = {code[0] for code in day_codes}
        day_digits = {code[1] for code in day_codes}
        by_letter = [code for code in space if code not in window_taken and code[0] not in day_letters]
        strict = [code for code in by_letter if code[1] not in day_digits]
        if strict:
            free = strict
        elif by_letter:
            digit_families = {
                digit: {BLIND_LETTER_FAMILIES.get(code[0], code[0]) for code in day_codes if code[1] == digit}
                for digit in day_digits
            }
            quality = [
                code
                for code in by_letter
                if BLIND_LETTER_FAMILIES.get(code[0], code[0]) not in digit_families.get(code[1], set())
            ]
            free = quality or by_letter
        else:
            free = [code for code in space if code not in window_taken and code not in day_codes]
        if not free:
            raise RuntimeError(
                "Sem código cego disponível: espaço esgotado no dia e na janela "
                "de expediente. Verifique refs duplicadas."
            )
        candidate = secrets.choice(free)
        try:
            with transaction.atomic():
                row = BlindPrepCode.objects.create(
                    date=selected_date,
                    recipe_ref=recipe_ref,
                    code=candidate,
                )
        except IntegrityError:
            existing = BlindPrepCode.objects.filter(date=selected_date, recipe_ref=recipe_ref).first()
            if existing:
                return existing.code
            continue
        window_clash = (
            BlindPrepCode.objects.filter(date__in=window, code=candidate)
            .exclude(pk=row.pk)
            .filter(pk__lt=row.pk)
            .exists()
        )
        if window_clash:
            row.delete()
            continue
        return candidate
    raise RuntimeError("Alocação de código cego não convergiu: investigar concorrência.")


def _blind_window(selected_date: date) -> tuple[date, date, date]:
    """Dia útil anterior, dia escolhido e próximo dia útil."""
    from shopman.shop.services.business_calendar import is_open_on

    def step(start: date, delta: int) -> date:
        candidate = start
        for _ in range(14):
            candidate += timedelta(days=delta)
            try:
                if is_open_on(candidate):
                    return candidate
            except Exception:
                logger.debug("blind_window.calendar_failed", exc_info=True)
                return start + timedelta(days=delta)
        return start + timedelta(days=delta)

    return (step(selected_date, -1), selected_date, step(selected_date, 1))
