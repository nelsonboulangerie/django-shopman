"""O salão desenhado: ler a planta de hoje e gravar o que o operador mudou.

PDV › Ajustes › Salão (decisão do dono, 04/10/2026): quem opera o PDV pode
redesenhar o salão, e toda mudança fica registrada (quem, quando, o quê, antes e
depois) no ``LogEntry`` do Admin, o histórico que a casa já usa para gesto de
configuração (``channel_switch``, ``catalog_bindings``).

**A regra de tempo.** O B.I. mede a lotação com o cadastro do salão
(``services/room.py``): em cada dia conta as mesas que existiam naquele dia e
que entram na capacidade oficial. Por isso há duas espécies de campo:

* **desenho** (rótulo, sigla, área, forma, posição, giro): o B.I. não lê, então
  muda no lugar;
* **medida** (lugares e "conta na capacidade oficial"): muda por VERSÃO. A mesa
  de antes encerra ontem (``active_until``) e a mesa de hoje nasce hoje
  (``active_from``), apontando para a anterior (``replaces``). Os dias de antes
  continuam contados com o que existia neles.

Mesa nascida hoje ainda não tem passado, e muda no lugar mesmo na medida. Tirar
do salão nunca apaga: encerra ontem, e a mesa some da planta a partir de hoje.

Um salvar só (prévia ``salao-mesas4.html``): a planta inteira vai numa transação,
com a revisão que o operador leu. Se outro dispositivo salvou no meio, a gravação
recusa com conflito em vez de sobrescrever.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from shopman.backstage.models import SeatingSpot, SpotKind, SpotShape

#: O que o B.I. lê: mudar estes campos versiona a mesa.
MEASURED_FIELDS = ("seats", "counts_in_capacity")
#: Desenho: muda no lugar.
DRAWING_FIELDS = ("label", "short_label", "area", "shape", "plan_x", "plan_y", "rotation")
EDITABLE_FIELDS = DRAWING_FIELDS + MEASURED_FIELDS

MAX_SEATS = 40
MAX_COORD = 4000
ROTATIONS = (0, 90, 180, 270)
AUDIT_ACTION = "seating.spot"


class SeatingError(Exception):
    """Pedido de gravação que não pode ser aceito, com o campo culpado."""

    def __init__(self, message: str, *, field: str = "", code: str = "invalid"):
        super().__init__(message)
        self.field = field
        self.code = code


class SeatingConflict(SeatingError):
    def __init__(self):
        super().__init__(
            "Outro dispositivo salvou o salão enquanto você editava. Recarregue para ver a planta nova.",
            code="seating_conflict",
        )


def today() -> date:
    return timezone.localdate()


def active_spots(day: date | None = None) -> list[SeatingSpot]:
    """As mesas que existem no dia (hoje, por padrão), na ordem do cadastro."""
    day = day or today()
    return [spot for spot in SeatingSpot.objects.order_by("kind", "ref") if spot.existed_on(day)]


def snapshot(spot: SeatingSpot) -> dict:
    """O retrato de uma mesa que vai para o registro (antes/depois)."""
    return {
        "ref": spot.ref,
        "label": spot.label,
        "short_label": spot.short_label,
        "area": spot.area,
        "shape": spot.shape,
        "seats": spot.seats,
        "counts_in_capacity": spot.counts_in_capacity,
        "plan_x": spot.plan_x,
        "plan_y": spot.plan_y,
        "rotation": spot.rotation,
        "active_from": spot.active_from.isoformat() if spot.active_from else None,
        "active_until": spot.active_until.isoformat() if spot.active_until else None,
    }


def revision(spots: list[SeatingSpot] | None = None) -> str:
    """A impressão digital da planta de hoje: muda quando qualquer mesa muda."""
    spots = active_spots() if spots is None else spots
    payload = json.dumps([snapshot(spot) for spot in spots], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def first_day(spot: SeatingSpot) -> date | None:
    """Desde quando a mesa existe, atravessando as versões (o "existe desde" da tela)."""
    seen = set()
    current = spot
    while current.replaces_id and current.replaces_id not in seen:
        seen.add(current.replaces_id)
        current = current.replaces
    return current.active_from


# ── validação ───────────────────────────────────────────────────────────────


def _text(value, *, field: str, max_length: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise SeatingError("Escreva um texto.", field=field)
    value = value.strip()
    if required and not value:
        raise SeatingError("Dê um nome à mesa.", field=field)
    if len(value) > max_length:
        raise SeatingError(f"Use no máximo {max_length} letras.", field=field)
    return value


def _int(value, *, field: str, low: int, high: int, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise SeatingError(message, field=field)
    return value


def clean_spot(raw, *, index: int) -> dict:
    """Os campos de uma mesa vindos da tela, validados. Ausente = não mexe."""
    prefix = f"spots[{index}]"
    if not isinstance(raw, dict):
        raise SeatingError("Mesa em formato inválido.", field=prefix)
    cleaned: dict = {}
    if "label" in raw:
        cleaned["label"] = _text(raw["label"], field=f"{prefix}.label", max_length=80, required=True)
    if "short_label" in raw:
        cleaned["short_label"] = _text(raw["short_label"], field=f"{prefix}.short_label", max_length=8)
    if "area" in raw:
        cleaned["area"] = _text(raw["area"], field=f"{prefix}.area", max_length=40)
    if "shape" in raw:
        if raw["shape"] not in SpotShape.values:
            raise SeatingError("Escolha redonda, quadrada, comprida ou banqueta.", field=f"{prefix}.shape")
        cleaned["shape"] = raw["shape"]
    if "seats" in raw:
        cleaned["seats"] = _int(raw["seats"], field=f"{prefix}.seats", low=1, high=MAX_SEATS,
                                message=f"Lugares vão de 1 a {MAX_SEATS}.")
    if "counts_in_capacity" in raw:
        if not isinstance(raw["counts_in_capacity"], bool):
            raise SeatingError("Diga se a mesa conta na capacidade oficial.", field=f"{prefix}.counts_in_capacity")
        cleaned["counts_in_capacity"] = raw["counts_in_capacity"]
    for axis in ("plan_x", "plan_y"):
        if axis in raw:
            cleaned[axis] = _int(raw[axis], field=f"{prefix}.{axis}", low=0, high=MAX_COORD,
                                 message="A mesa ficou fora da planta.")
    if "rotation" in raw:
        if raw["rotation"] not in ROTATIONS or isinstance(raw["rotation"], bool):
            raise SeatingError("O giro é de 90 em 90 graus.", field=f"{prefix}.rotation")
        cleaned["rotation"] = raw["rotation"]
    if cleaned.get("shape") == SpotShape.STOOL and cleaned.get("seats", 1) != 1:
        raise SeatingError("Banqueta tem um lugar só.", field=f"{prefix}.seats")
    return cleaned


# ── gravação ────────────────────────────────────────────────────────────────


@dataclass
class SaveResult:
    changed: int
    created: int
    versioned: int
    removed: int


def _new_ref(label: str, taken: set[str]) -> str:
    base = (slugify(label) or "mesa")[:24].strip("-") or "mesa"
    candidate = base
    counter = 2
    while candidate in taken:
        suffix = f"-{counter}"
        candidate = f"{base[: 32 - len(suffix)]}{suffix}"
        counter += 1
    taken.add(candidate)
    return candidate


def _kind_for(shape: str) -> str:
    return SpotKind.COUNTER if shape == SpotShape.STOOL else SpotKind.TABLE


def _audit(actor, spot: SeatingSpot, *, flag: int, change: str, before: dict | None, after: dict | None,
           replaces: str = "") -> None:
    from django.contrib.admin.models import LogEntry

    payload = {"action": f"{AUDIT_ACTION}.{change}", "ref": spot.ref, "before": before, "after": after}
    if replaces:
        payload["replaces"] = replaces
    LogEntry.objects.log_actions(
        user_id=actor.pk, queryset=[spot], action_flag=flag,
        change_message=json.dumps(payload, ensure_ascii=False),
    )


def _diff(before: dict, after: dict) -> tuple[dict, dict]:
    keys = [key for key in after if before.get(key) != after.get(key) and key not in ("ref",)]
    return {key: before.get(key) for key in keys}, {key: after.get(key) for key in keys}


@transaction.atomic
def save_layout(*, actor, spots, removed, expected_revision, fixtures=None) -> SaveResult:
    """Grava a planta: mesas mudadas ou novas (``spots``) e as que saem (``removed``).

    Cada item de ``spots`` com ``ref`` muda uma mesa de hoje; sem ``ref`` é mesa
    nova. Só os campos presentes mudam. Tudo ou nada.
    """
    from django.contrib.admin.models import ADDITION, CHANGE

    if not isinstance(spots, list):
        raise SeatingError("Envie a lista de mesas.", field="spots")
    if not isinstance(removed, list) or not all(isinstance(ref, str) for ref in removed):
        raise SeatingError("Envie a lista de mesas que saem.", field="removed")

    day = today()
    yesterday = day - timedelta(days=1)
    current = {spot.ref: spot for spot in SeatingSpot.objects.select_for_update().order_by("kind", "ref")}
    on_floor = {ref: spot for ref, spot in current.items() if spot.existed_on(day)}
    if expected_revision != revision(sorted(on_floor.values(), key=lambda s: (s.kind, s.ref))):
        raise SeatingConflict()

    taken = set(current)
    result = SaveResult(changed=0, created=0, versioned=0, removed=0)
    seen: set[str] = set()

    for index, raw in enumerate(spots):
        fields = clean_spot(raw, index=index)
        ref = raw.get("ref") if isinstance(raw, dict) else None
        if ref:
            spot = on_floor.get(ref)
            if spot is None:
                raise SeatingError("Esta mesa não está mais no salão de hoje.", field=f"spots[{index}].ref",
                                   code="spot_unknown")
            if ref in seen or ref in removed:
                raise SeatingError("A mesma mesa veio duas vezes.", field=f"spots[{index}].ref")
            seen.add(ref)
            shape = fields.get("shape", spot.shape)
            if shape == SpotShape.STOOL and fields.get("seats", spot.seats) != 1:
                if "seats" in fields:
                    raise SeatingError("Banqueta tem um lugar só.", field=f"spots[{index}].seats")
                fields["seats"] = 1
            before = snapshot(spot)
            measured = any(key in fields and fields[key] != getattr(spot, key) for key in MEASURED_FIELDS)
            has_past = spot.active_from is None or spot.active_from < day
            if measured and has_past:
                spot.active_until = yesterday
                spot.save(update_fields=["active_until"])
                successor = SeatingSpot(
                    ref=_new_ref(spot.ref, taken),
                    kind=_kind_for(shape),
                    active_from=day,
                    active_until=None,
                    replaces=spot,
                    **{key: fields.get(key, getattr(spot, key)) for key in EDITABLE_FIELDS},
                )
                successor.save()
                old, new = _diff(before, snapshot(successor))
                _audit(actor, successor, flag=ADDITION, change="version", before=old, after=new,
                       replaces=spot.ref)
                result.versioned += 1
                continue
            for key, value in fields.items():
                setattr(spot, key, value)
            spot.kind = _kind_for(spot.shape)
            old, new = _diff(before, snapshot(spot))
            if not new:
                continue
            spot.save()
            _audit(actor, spot, flag=CHANGE, change="change", before=old, after=new)
            result.changed += 1
        else:
            if "label" not in fields:
                raise SeatingError("Dê um nome à mesa.", field=f"spots[{index}].label")
            shape = fields.get("shape", SpotShape.SQUARE)
            if shape == SpotShape.STOOL:
                fields["seats"] = 1
            spot = SeatingSpot(
                ref=_new_ref(fields["label"], taken),
                kind=_kind_for(shape),
                shape=shape,
                active_from=day,
                **{key: value for key, value in fields.items() if key != "shape"},
            )
            spot.save()
            _audit(actor, spot, flag=ADDITION, change="add", before=None, after=snapshot(spot))
            result.created += 1

    for ref in removed:
        spot = on_floor.get(ref)
        if spot is None:
            raise SeatingError("Esta mesa não está mais no salão de hoje.", field="removed", code="spot_unknown")
        before = snapshot(spot)
        spot.active_until = yesterday
        spot.save(update_fields=["active_until"])
        _audit(actor, spot, flag=CHANGE, change="remove", before={"active_until": before["active_until"]},
               after={"active_until": yesterday.isoformat()})
        result.removed += 1

    if fixtures is not None:
        save_fixtures(fixtures)
    return result


FIXTURE_MAX = 2000


def save_fixtures(fixtures) -> None:
    """A vitrine e caixa e a entrada da planta: troca a lista inteira de uma vez.

    Desenho, não medida (o B.I. não lê): edita-se no lugar, sem versão, junto do
    Salvar do salão. Cada item ``{kind, label?, plan_x, plan_y, width?, height?}``.
    """
    from shopman.backstage.models import FixtureKind, SeatingFixture

    if not isinstance(fixtures, list):
        raise SeatingError("Envie a lista de elementos fixos.", field="fixtures")
    kinds = dict(FixtureKind.choices)
    rows = []
    for index, raw in enumerate(fixtures):
        if not isinstance(raw, dict) or raw.get("kind") not in kinds:
            raise SeatingError("Elemento fixo desconhecido.", field=f"fixtures[{index}].kind")

        def number(key, default, low=0, high=FIXTURE_MAX, raw=raw, index=index):
            try:
                value = int(raw.get(key, default))
            except (TypeError, ValueError):
                raise SeatingError("Posição inválida.", field=f"fixtures[{index}].{key}") from None
            return max(low, min(high, value))

        rows.append(SeatingFixture(
            kind=raw["kind"],
            label=str(raw.get("label") or kinds[raw["kind"]])[:60],
            plan_x=number("plan_x", 0),
            plan_y=number("plan_y", 0),
            width=number("width", 40, 16),
            height=number("height", 320, 16),
        ))
    SeatingFixture.objects.all().delete()
    SeatingFixture.objects.bulk_create(rows)
