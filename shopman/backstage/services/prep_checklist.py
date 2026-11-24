"""O "Separado" da Preparação, no servidor (WP-F09a; D-042, item 5).

A marca é presa ao **item e à data** (``models.prep_checklist``) e à **quantidade do
momento**. Este service é o único que lê e grava a marca, e é ele quem decide se ela
ainda vale: lê a Preparação do dia (a lista de separação nas duas lentes e os
preparos) pelas mesmas projeções que a tela usa, sem entrar nelas.

* Uma marca vale enquanto a quantidade que ela guarda for uma das quantidades que
  aquele item mostra agora. Mudou a quantidade daquele item, a marca cai; nada mais a
  derruba (ligar "Mostrar ingredientes dos pré-preparos", uma entrada de estoque, um
  lote de outro produto).
* Marcar exige a quantidade do momento: quem marcou olhando uma lista velha recebe
  ``PrepChecklistQuantityChanged`` com a quantidade de agora.
* Desmarcar grava ``checked=False`` e a história guarda o gesto.
* Dois tablets marcando o mesmo item ao mesmo tempo dão uma marca só: a linha é única
  por (dia, item), a escrita trava a linha, e repetir o estado atual não é gesto novo.
* Cada gesto avisa a grade pelo canal ``production`` do SSE (ADR-016), o mesmo evento
  que os lotes já emitem; a tela refaz a leitura.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.backstage.models import PrepChecklistMark

logger = logging.getLogger(__name__)

#: Separador entre o preparo e o ingrediente na chave do item ("MASSA-BRIOCHE/FARINHA").
PREP_SEPARATOR = "/"
MAX_ITEM_REF_LENGTH = PrepChecklistMark._meta.get_field("item_ref").max_length
MAX_QUANTITY_LENGTH = PrepChecklistMark._meta.get_field("quantity").max_length


class PrepChecklistError(Exception):
    """Pedido de marca que não faz sentido (item mal formado)."""


class PrepChecklistQuantityChanged(Exception):
    """A quantidade que a pessoa viu não é mais a do item: a lista mudou."""

    def __init__(self, item_ref: str, current: tuple[str, ...]):
        self.item_ref = item_ref
        self.current = current
        if current:
            detail = f"A quantidade mudou: agora são {' ou '.join(current)}. Confira e separe de novo."
        else:
            detail = "Este item saiu da preparação do dia."
        super().__init__(detail)


@dataclass(frozen=True)
class PrepChecklistMarkView:
    item_ref: str
    quantity: str
    marked_by: str
    marked_at: str

    def as_dict(self) -> dict:
        return {
            "item_ref": self.item_ref,
            "quantity": self.quantity,
            "marked_by": self.marked_by,
            "marked_at": self.marked_at,
        }


def item_ref_for_line(sku: str) -> str:
    """A chave de uma linha da lista de separação ("Por insumo")."""
    return sku


def item_ref_for_prep_ingredient(recipe_ref: str, sku: str) -> str:
    """A chave do ingrediente de um preparo ("Por preparo")."""
    return f"{recipe_ref}{PREP_SEPARATOR}{sku}"


def normalize_item_ref(item_ref: str) -> str:
    value = str(item_ref or "").strip()
    if not value or len(value) > MAX_ITEM_REF_LENGTH or any(char.isspace() for char in value):
        raise PrepChecklistError("Item da preparação inválido.")
    parts = value.split(PREP_SEPARATOR)
    if len(parts) > 2 or not all(parts):
        raise PrepChecklistError("Item da preparação inválido.")
    return value


def current_quantities(*, selected_date: date, access=None) -> dict[str, frozenset[str]]:
    """Cada item da Preparação do dia e as quantidades que ele mostra agora.

    Uma linha da lista pode mostrar duas quantidades: a da lista e a da lista com os
    ingredientes dos pré-preparos (a farinha da massa soma na farinha). A marca vale
    na lente em que a quantidade dela aparece, e a tela a mostra onde bate.
    """
    from shopman.backstage.projections.production import (
        build_production_mise_en_place,
        build_production_weighing,
    )

    quantities: dict[str, set[str]] = {}
    for expand in (False, True):
        mise_en_place = build_production_mise_en_place(selected_date=selected_date, expand=expand, access=access)
        for line in mise_en_place.lines:
            quantities.setdefault(item_ref_for_line(line.sku), set()).add(line.quantity_display)
    weighing = build_production_weighing(selected_date=selected_date, access=access)
    for ticket in weighing.tickets:
        for ingredient in ticket.ingredients:
            ref = item_ref_for_prep_ingredient(ticket.recipe_ref, ingredient.sku)
            quantities.setdefault(ref, set()).add(ingredient.quantity_display)
    return {ref: frozenset(values) for ref, values in quantities.items()}


def marks_for(*, selected_date: date, access=None) -> list[PrepChecklistMarkView]:
    """As marcas de "Separado" que valem agora, para todos os tablets do dia."""
    marks = list(PrepChecklistMark.objects.filter(prep_date=selected_date, checked=True).order_by("item_ref"))
    if not marks:
        return []
    current = current_quantities(selected_date=selected_date, access=access)
    return [_view(mark) for mark in marks if mark.quantity in current.get(mark.item_ref, frozenset())]


def set_mark(
    *,
    selected_date: date,
    item_ref: str,
    quantity: str,
    checked: bool,
    user,
    access=None,
) -> PrepChecklistMarkView | None:
    """Marca ou desmarca um item do dia. Devolve a marca que vale, ou ``None``."""
    item_ref = normalize_item_ref(item_ref)
    quantity = str(quantity or "").strip()
    if checked:
        if not quantity or len(quantity) > MAX_QUANTITY_LENGTH:
            raise PrepChecklistError("Quantidade da preparação inválida.")
        shown = current_quantities(selected_date=selected_date, access=access).get(item_ref, frozenset())
        if quantity not in shown:
            raise PrepChecklistQuantityChanged(item_ref, tuple(sorted(shown)))

    with transaction.atomic():
        mark = _locked_mark(selected_date, item_ref)
        if mark is None:
            if not checked:
                return None
            mark = _create_locked_mark(selected_date, item_ref, quantity)
            if mark is None:  # outro tablet criou no mesmo instante: a linha dele vale
                mark = _locked_mark(selected_date, item_ref)
            else:
                _record(mark, checked=True, quantity=quantity, user=user, fresh=True)
                _announce(mark)
                return _view(mark)

        if mark.checked == checked and (not checked or mark.quantity == quantity):
            return _view(mark) if checked else None

        _record(mark, checked=checked, quantity=quantity if checked else mark.quantity, user=user)
        _announce(mark)
        return _view(mark) if checked else None


def _locked_mark(selected_date: date, item_ref: str) -> PrepChecklistMark | None:
    return PrepChecklistMark.objects.select_for_update().filter(prep_date=selected_date, item_ref=item_ref).first()


def _create_locked_mark(selected_date: date, item_ref: str, quantity: str) -> PrepChecklistMark | None:
    try:
        with transaction.atomic():
            return PrepChecklistMark.objects.create(
                prep_date=selected_date,
                item_ref=item_ref,
                quantity=quantity,
                checked=True,
                marked_at=timezone.now(),
            )
    except IntegrityError:
        return None


def _record(mark: PrepChecklistMark, *, checked: bool, quantity: str, user, fresh: bool = False) -> None:
    now = timezone.now()
    name = _operator_name(user)
    mark.checked = checked
    mark.quantity = quantity
    mark.marked_by = user if getattr(user, "pk", None) else None
    mark.marked_by_name = name
    mark.marked_at = now
    mark.history = [
        *(mark.history or []),
        {"checked": checked, "quantity": quantity, "by": name, "at": now.isoformat()},
    ]
    mark.save(
        update_fields=None if fresh else ["checked", "quantity", "marked_by", "marked_by_name", "marked_at", "history"]
    )


def _operator_name(user) -> str:
    first_name = (getattr(user, "first_name", "") or "").strip()
    return (first_name or getattr(user, "username", "") or "")[:150]


def _view(mark: PrepChecklistMark) -> PrepChecklistMarkView:
    return PrepChecklistMarkView(
        item_ref=mark.item_ref,
        quantity=mark.quantity,
        marked_by=mark.marked_by_name,
        marked_at=timezone.localtime(mark.marked_at).isoformat(),
    )


def _announce(mark: PrepChecklistMark) -> None:
    """Avisa a grade pelo canal ``production`` (o evento que ela já ouve)."""
    payload = {
        "kind": "prep_checklist",
        "date": mark.prep_date.isoformat(),
        "item_ref": mark.item_ref,
        "checked": mark.checked,
    }
    try:
        from shopman.shop.handlers._sse_emitters import _default_backstage_scope, _emit_backstage

        _emit_backstage(
            "production",
            "backstage-production-update",
            payload,
            scope=_default_backstage_scope(),
        )
    except Exception:
        logger.warning("prep_checklist.announce_failed item=%s", mark.item_ref, exc_info=True)
