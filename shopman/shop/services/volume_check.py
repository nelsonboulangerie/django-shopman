"""Conferência de volumes no despacho: cada sacola diz de que pedido é.

Medido em 13/10/2026 (cenários de pedido, P1-13): o pedido sai em N sacolas,
cada uma com a sua Via Pedido ("Volume k de N"), e nada conferia, na hora de
entregar ao entregador ou ao cliente, se as N estavam ali, nem se uma sacola de
OUTRO pedido tinha entrado no meio. O QR da via era o link do cliente.

Agora a Via Pedido leva também um QR de CONFERÊNCIA com o pedido e o volume
(:func:`volume_code`). O leitor do posto Saída (modo teclado, como o da Via
Cozinha no PDV) bipa a sacola e o Gestor diz "2 de 3 sacolas conferidas".
Sacola de outro pedido bipada enquanto se confere um pedido é aviso FORTE e não
conta. Nada aqui segura a saída: despachar com sacola sem conferir só avisa
(decisão do dono, a mesma da expedição sem NFC-e).

O código é assinado (HMAC com a SECRET_KEY), como o da Via Cozinha: um papel
não se forja digitando o número de outro pedido. O alfabeto é o que um leitor em
modo teclado entrega igual em qualquer leiaute: letras, dígitos e o hífen.

Estado em ``Order.data["volume_check"]`` (``docs/reference/data-schemas.md``).
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

VOLUME_CODE_PREFIX = "VP-"
_SIG_LEN = 8
_SALT = "shopman.backstage.volume_check_code"
_PATTERN = re.compile(r"VP-(.+)-(\d{1,2})-(\d{1,2})-([A-Z2-7]{" + str(_SIG_LEN) + r"})")

#: Chave em ``Order.data``.
DATA_KEY = "volume_check"
#: Quantas sacolas erradas o pedido guarda na trilha (as mais recentes).
_MAX_WRONG = 20

UNCHECKED_ALERT_TYPE = "dispatch_unchecked_volumes"

OUTCOME_CHECKED = "checked"
OUTCOME_REPEATED = "repeated"
OUTCOME_OTHER_ORDER = "other_order"
OUTCOME_STALE = "stale"
OUTCOME_UNKNOWN = "unknown"


def _signature(order_ref: str, k: int, n: int) -> str:
    digest = salted_hmac(_SALT, f"volume:{order_ref}:{k}:{n}", algorithm="sha256").digest()
    return base64.b32encode(digest).decode("ascii")[:_SIG_LEN]


def volume_code(order_ref: str, k: int, n: int) -> str:
    """O código do QR de conferência da sacola ``k`` de ``n`` do pedido."""
    ref = str(order_ref).upper()
    return f"{VOLUME_CODE_PREFIX}{ref}-{int(k)}-{int(n)}-{_signature(ref, int(k), int(n))}"


@dataclass(frozen=True)
class VolumeCode:
    order_ref: str
    k: int
    n: int


def parse_volume_code(code: str) -> VolumeCode | None:
    """O pedido e o volume de um código lido; ``None`` para código que não é desta casa.

    Aceita minúsculas (leitor com Caps Lock trocado) e espaço nas pontas. A
    assinatura é comparada em tempo constante.
    """
    match = _PATTERN.fullmatch(str(code or "").strip().upper())
    if match is None:
        return None
    ref, k, n, sig = match.group(1), int(match.group(2)), int(match.group(3)), match.group(4)
    if not (1 <= k <= n) or not constant_time_compare(sig, _signature(ref, k, n)):
        return None
    return VolumeCode(order_ref=ref, k=k, n=n)


def declared_total(order: Order) -> int:
    """Quantas sacolas o pedido tem: as declaradas, ou uma quando ninguém declarou."""
    value = (order.data or {}).get("volumes")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 1


def checked_volumes(order: Order) -> tuple[int, ...]:
    """Os volumes já conferidos, valendo para o total ATUAL do pedido."""
    state = (order.data or {}).get(DATA_KEY)
    if not isinstance(state, dict) or state.get("total") != declared_total(order):
        return ()
    checked = state.get("checked") if isinstance(state.get("checked"), dict) else {}
    return tuple(sorted(int(k) for k in checked if str(k).isdigit()))


def conference_started(order: Order) -> bool:
    return bool(checked_volumes(order))


def missing_volumes(order: Order) -> tuple[int, ...]:
    done = set(checked_volumes(order))
    return tuple(k for k in range(1, declared_total(order) + 1) if k not in done)


def progress_label(order: Order) -> str:
    """ "2 de 3 sacolas conferidas", ou ``""`` quando a conferência não começou."""
    done = len(checked_volumes(order))
    if not done:
        return ""
    total = declared_total(order)
    if total == 1:
        return "Sacola conferida"
    return f"{done} de {total} sacolas conferidas"


@dataclass(frozen=True)
class VolumeCheckResult:
    """O que a bipada deu, na voz da Saída."""

    outcome: str
    message: str
    #: O pedido da SACOLA lida ("" quando o código não é desta casa).
    order_ref: str = ""
    #: O pedido em conferência, quando quem bipou disse qual era.
    expected_ref: str = ""
    k: int = 0
    n: int = 0
    checked: int = 0
    total: int = 0

    @property
    def complete(self) -> bool:
        return bool(self.total) and self.checked >= self.total


def _order_label(ref: str) -> str:
    return f"pedido {ref}"


@transaction.atomic
def check_volume(code: str, *, actor: str, expected_ref: str = "") -> VolumeCheckResult:
    """Confere uma sacola bipada. Nunca levanta por causa do papel: devolve o resultado.

    ``expected_ref``: o pedido que está sendo conferido (o detalhe aberto, ou o
    primeiro bipado no quadro). Sacola de outro pedido não conta e volta como
    ``other_order``, com a frase forte, e fica na trilha do pedido conferido.
    """
    parsed = parse_volume_code(code)
    expected = str(expected_ref or "").strip().upper()
    if parsed is None:
        return VolumeCheckResult(
            outcome=OUTCOME_UNKNOWN, expected_ref=expected,
            message="Este código não é de uma Via Pedido desta loja.",
        )
    order = Order.objects.select_for_update().filter(ref__iexact=parsed.order_ref).first()
    if order is None:
        return VolumeCheckResult(
            outcome=OUTCOME_UNKNOWN, expected_ref=expected,
            message=f"Não achei o pedido {parsed.order_ref}.",
        )

    if expected and expected != order.ref.upper():
        _record_wrong_bag(expected, scanned=order, parsed=parsed, actor=actor)
        return VolumeCheckResult(
            outcome=OUTCOME_OTHER_ORDER, order_ref=order.ref, expected_ref=expected,
            k=parsed.k, n=parsed.n,
            message=(
                f"Esta sacola é do {_order_label(order.ref)}, não do {_order_label(expected)}. "
                "Separe-a antes de entregar."
            ),
        )

    total = declared_total(order)
    if parsed.n != total:
        return VolumeCheckResult(
            outcome=OUTCOME_STALE, order_ref=order.ref, expected_ref=expected,
            k=parsed.k, n=parsed.n, checked=len(checked_volumes(order)), total=total,
            message=(
                f"Esta via diz {parsed.n} {'sacola' if parsed.n == 1 else 'sacolas'}, e o "
                f"{_order_label(order.ref)} tem {total}. Reimprima as vias do pedido."
            ),
        )

    data = dict(order.data or {})
    state = data.get(DATA_KEY) if isinstance(data.get(DATA_KEY), dict) else {}
    if state.get("total") != total:
        state = {"total": total, "checked": {}}
    checked = dict(state.get("checked") or {})
    repeated = str(parsed.k) in checked
    if not repeated:
        checked[str(parsed.k)] = {"at": timezone.now().isoformat(), "by": actor}
        state = {**state, "total": total, "checked": checked}
        data[DATA_KEY] = state
        order.data = data
        order.save(update_fields=["data", "updated_at"])
        # A trilha do pedido, e o sinal para os outros quadros relerem (SSE).
        order.emit_event(
            event_type="volume_checked", actor=actor,
            payload={"k": parsed.k, "n": total, "checked": len(checked)},
        )
    done = len(checked)
    if repeated:
        message = f"A sacola {parsed.k} de {total} do {_order_label(order.ref)} já foi conferida."
    elif done >= total:
        message = (
            f"Pedido {order.ref}: todas as {total} sacolas conferidas."
            if total > 1 else f"Pedido {order.ref}: sacola conferida."
        )
    else:
        message = f"Pedido {order.ref}: {done} de {total} sacolas conferidas."
    return VolumeCheckResult(
        outcome=OUTCOME_REPEATED if repeated else OUTCOME_CHECKED,
        order_ref=order.ref, expected_ref=expected, k=parsed.k, n=parsed.n,
        checked=done, total=total, message=message,
    )


def _record_wrong_bag(expected_ref: str, *, scanned: Order, parsed: VolumeCode, actor: str) -> None:
    """A trilha do pedido conferido guarda a sacola errada que apareceu nele."""
    target = Order.objects.select_for_update().filter(ref__iexact=expected_ref).first()
    if target is None:
        return
    data = dict(target.data or {})
    state = dict(data.get(DATA_KEY) or {}) if isinstance(data.get(DATA_KEY), dict) else {}
    wrong = list(state.get("wrong") or [])[-(_MAX_WRONG - 1):]
    wrong.append({"order_ref": scanned.ref, "k": parsed.k, "n": parsed.n, "at": timezone.now().isoformat(), "by": actor})
    state["wrong"] = wrong
    data[DATA_KEY] = state
    target.data = data
    target.save(update_fields=["data", "updated_at"])
    target.emit_event(
        event_type="volume_check_wrong_bag",
        actor=actor,
        payload={"scanned_order_ref": scanned.ref, "k": parsed.k, "n": parsed.n},
    )
    logger.warning(
        "volume_check.wrong_bag expected=%s scanned=%s k=%s n=%s actor=%s",
        target.ref, scanned.ref, parsed.k, parsed.n, actor,
    )


def alert_if_unchecked(order: Order, *, target_status: str) -> None:
    """O pedido sai com sacola sem conferir: AVISA, nunca barra.

    Só quando a conferência começou (alguém bipou ao menos uma sacola): a casa
    que não confere não recebe um alerta por saída, e o que vale é o pedido em
    que a conferência ficou pela metade. Nunca levanta.
    """
    if str(target_status or "").lower() not in {"dispatched", "completed"}:
        return
    try:
        if not conference_started(order):
            return
        missing = missing_volumes(order)
        if not missing:
            return
        from shopman.shop.services.observability import create_operator_alert

        total = declared_total(order)
        faltam = ", ".join(str(k) for k in missing)
        create_operator_alert(
            type=UNCHECKED_ALERT_TYPE,
            severity="warning",
            message=(
                f"O pedido {order.ref} saiu com {len(missing)} de {total} sacolas sem conferir "
                f"(volume {faltam}). Confirme com quem levou se todas foram juntas."
            ),
            order_ref=order.ref,
            dedupe_key=f"{UNCHECKED_ALERT_TYPE}:{order.ref}",
        )
    except Exception:
        logger.warning("volume_check.alert_failed order=%s", getattr(order, "ref", "?"), exc_info=True)
