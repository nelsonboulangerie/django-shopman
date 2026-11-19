"""O acompanhamento diz até quando a loja responde, e separa do dia do pedido (#2749).

Antes a frase do cartão juntava a resposta da loja (que tem prazo de minutos) com
o dia do pedido ("...só é cobrado quando a loja aceitar seu pedido para amanhã, a
partir das 15h."), e lia como se a loja fosse responder amanhã às 15h. Agora são
duas frases: a resposta da loja com o prazo que o servidor publicou, e para quando
é o pedido. O verbo é "confirmar" em toda a família, como na revisão do checkout.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from shopman.storefront.presentation.order_tracking import _acceptance_until, _promise_copy
from shopman.storefront.tests.web.test_tracking_promise_cascade import (
    _authorized_wait_data,
    _preorder_wait_data,
)

SP = ZoneInfo("America/Sao_Paulo")
#: Quinta, 19/11/2026, 7h40 em São Paulo: o "agora" das frases deste arquivo.
NOW = datetime(2026, 11, 19, 7, 40, tzinfo=SP)
WHEN = "amanhã, a partir das 15h"


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


def _copy():
    from shopman.shop.projections.copy import build_copy

    return build_copy("TRACKING")


def _iso(moment: datetime) -> str:
    return moment.isoformat()


# ── A hora do prazo, na forma que cabe na frase ──────────────────────────────


def test_prazo_de_hoje_diz_so_a_hora():
    assert _acceptance_until(_iso(NOW + timedelta(minutes=60))) == "até 8h40"


def test_hora_cheia_sai_sem_minutos():
    assert _acceptance_until(_iso(NOW.replace(hour=10, minute=0))) == "até 10h"


def test_prazo_de_amanha_diz_o_dia():
    tomorrow_10 = (NOW + timedelta(days=1)).replace(hour=10, minute=0)
    assert _acceptance_until(_iso(tomorrow_10)) == "até amanhã, sexta, às 10h"


def test_prazo_depois_de_amanha_diz_o_dia_e_a_data():
    monday_10 = datetime(2026, 11, 23, 10, 0, tzinfo=SP)
    assert _acceptance_until(_iso(monday_10)) == "até segunda, 23/11, às 10h"


def test_uma_hora_leva_o_artigo_no_singular():
    tomorrow_1 = (NOW + timedelta(days=1)).replace(hour=1, minute=0)
    assert _acceptance_until(_iso(tomorrow_1)) == "até amanhã, sexta, à 1h"


def test_prazo_em_utc_vira_a_hora_da_loja():
    utc = (NOW + timedelta(minutes=60)).astimezone(ZoneInfo("UTC"))
    assert _acceptance_until(_iso(utc)) == "até 8h40"


@pytest.mark.parametrize("value", [None, "", "não é data", _iso(NOW), _iso(NOW - timedelta(minutes=5))])
def test_sem_prazo_ou_com_ele_vencido_a_frase_nao_promete_hora(value):
    assert _acceptance_until(value) == ""


# ── Cartão autorizado esperando a loja ───────────────────────────────────────


def _card(deadline: datetime | None):
    return replace(_authorized_wait_data(), acceptance_deadline_at=_iso(deadline) if deadline else None)


def test_cartao_autorizado_separa_o_prazo_do_aceite_e_o_dia_do_pedido():
    title, message = _promise_copy(
        _card(NOW + timedelta(minutes=60)),
        status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN,
    )

    assert title == "Pagamento autorizado"
    assert message == (
        "O valor está reservado no seu cartão e só é cobrado quando a loja confirmar, até 8h40. "
        "Seu pedido é para amanhã, a partir das 15h."
    )


def test_cartao_autorizado_com_a_casa_fechada_diz_o_dia_do_prazo():
    tomorrow_10 = (NOW + timedelta(days=1)).replace(hour=10, minute=0)
    _title, message = _promise_copy(
        _card(tomorrow_10), status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN,
    )

    assert message == (
        "O valor está reservado no seu cartão e só é cobrado quando a loja confirmar, "
        "até amanhã, sexta, às 10h. Seu pedido é para amanhã, a partir das 15h."
    )


def test_cartao_autorizado_sem_prazo_publicado_fica_sem_o_trecho_do_prazo():
    _title, message = _promise_copy(
        _card(None), status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN,
    )

    assert message == (
        "O valor está reservado no seu cartão e só é cobrado quando a loja confirmar. "
        "Seu pedido é para amanhã, a partir das 15h."
    )
    assert "até" not in message
    assert ", ." not in message and "  " not in message


def test_cartao_autorizado_sem_dia_combinado_fica_so_com_a_frase_do_aceite():
    data = replace(_card(NOW + timedelta(minutes=60)), fulfillment_wait_until=None)
    _title, message = _promise_copy(data, status="new", is_delivery=False, copy=_copy())

    assert message == "O valor está reservado no seu cartão e só é cobrado quando a loja confirmar, até 8h40."


def test_cartao_de_pedido_ja_aceito_nao_fala_em_prazo_de_aceite():
    _title, message = _promise_copy(
        _card(NOW + timedelta(minutes=60)),
        status="accepted", is_delivery=False, copy=_copy(), when_phrase=WHEN,
    )

    assert message == "Pedido aceito para amanhã, a partir das 15h. Estamos cobrando o valor reservado no seu cartão."


# ── Pix pago (e encomenda sem pagamento) esperando a loja ────────────────────


def _preorder(state: str, deadline: datetime | None):
    return replace(_preorder_wait_data(state), acceptance_deadline_at=_iso(deadline) if deadline else None)


def test_pix_pago_esperando_a_loja_diz_ate_quando_ela_confirma():
    title, message = _promise_copy(
        _preorder("payment_confirmed", NOW + timedelta(minutes=60)),
        status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN, payment_confirmed=True,
    )

    assert title == "Pagamento recebido"
    assert message == (
        "A loja confirma até 8h40 e avisa por aqui. Se não puder, devolvemos o valor. "
        "Sua encomenda é para amanhã, a partir das 15h."
    )


def test_pix_pago_sem_prazo_publicado_mantem_a_frase_inteira():
    _title, message = _promise_copy(
        _preorder("payment_confirmed", None),
        status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN, payment_confirmed=True,
    )

    assert message == (
        "A loja confirma e avisa por aqui. Se não puder, devolvemos o valor. "
        "Sua encomenda é para amanhã, a partir das 15h."
    )


def test_pago_e_conferindo_leva_o_prazo_na_mesma_familia():
    _title, message = _promise_copy(
        _preorder("store_checking", NOW + timedelta(minutes=60)),
        status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN, payment_confirmed=True,
    )

    assert message == (
        "Pagamento recebido. A loja confirma até 8h40 e avisa por aqui. Se não puder, devolvemos o valor. "
        "Sua encomenda é para amanhã, a partir das 15h."
    )


@pytest.mark.parametrize("state", ["store_checking", "received"])
def test_encomenda_sem_pagamento_esperando_a_loja_nao_promete_devolucao(state):
    _title, message = _promise_copy(
        _preorder(state, NOW + timedelta(minutes=60)),
        status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN,
    )

    assert message == "A loja confirma até 8h40 e avisa por aqui. Sua encomenda é para amanhã, a partir das 15h."
    assert "devolvemos" not in message


# ── As quatro combinações de cada frase da família ────────────────────────────
#
# Com e sem prazo publicado × com e sem dia combinado. Sem prazo e com dia, a
# frase do aceite não nomeia o pedido (a frase do dia vem logo depois e o nomeia);
# sem dia, ela nomeia. Em nenhuma combinação o substantivo aparece duas vezes.

CARD_RESERVED = "O valor está reservado no seu cartão e só é cobrado quando a loja confirmar"
REFUND = "Se não puder, devolvemos o valor."
ORDER_IS_FOR = "Seu pedido é para amanhã, a partir das 15h."
PREORDER_IS_FOR = "Sua encomenda é para amanhã, a partir das 15h."

#: família → (estado, pago, método) e as quatro frases: (prazo, dia) → frase literal.
FAMILY = {
    "cartao_autorizado": {
        "build": ("payment_authorized", False, "card"),
        (True, True): f"{CARD_RESERVED}, até 8h40. {ORDER_IS_FOR}",
        (True, False): f"{CARD_RESERVED}, até 8h40.",
        (False, True): f"{CARD_RESERVED}. {ORDER_IS_FOR}",
        (False, False): f"{CARD_RESERVED} seu pedido.",
    },
    "pix_pago": {
        "build": ("payment_confirmed", True, "pix"),
        (True, True): f"A loja confirma até 8h40 e avisa por aqui. {REFUND} {PREORDER_IS_FOR}",
        (True, False): f"A loja confirma até 8h40 e avisa por aqui. {REFUND}",
        (False, True): f"A loja confirma e avisa por aqui. {REFUND} {PREORDER_IS_FOR}",
        (False, False): f"A loja confirma sua encomenda e avisa por aqui. {REFUND}",
    },
    "encomenda_esperando_a_loja": {
        "build": ("received", False, "pix"),
        (True, True): f"A loja confirma até 8h40 e avisa por aqui. {PREORDER_IS_FOR}",
        (True, False): "A loja confirma até 8h40 e avisa por aqui.",
        (False, True): f"A loja confirma e avisa por aqui. {PREORDER_IS_FOR}",
        (False, False): "A loja confirma sua encomenda e avisa por aqui.",
    },
    "pago_e_conferindo": {
        "build": ("store_checking", True, "pix"),
        (True, True): f"Pagamento recebido. A loja confirma até 8h40 e avisa por aqui. {REFUND} {PREORDER_IS_FOR}",
        (True, False): f"Pagamento recebido. A loja confirma até 8h40 e avisa por aqui. {REFUND}",
        (False, True): f"Pagamento recebido. A loja confirma e avisa por aqui. {REFUND} {PREORDER_IS_FOR}",
        (False, False): f"Pagamento recebido. A loja confirma sua encomenda e avisa por aqui. {REFUND}",
    },
}


def _family_message(family: str, *, with_deadline: bool, with_date: bool) -> str:
    state, paid, method = FAMILY[family]["build"]
    deadline = NOW + timedelta(minutes=60) if with_deadline else None
    data = _card(deadline) if method == "card" else _preorder(state, deadline)
    _title, message = _promise_copy(
        data,
        status="new",
        is_delivery=False,
        copy=_copy(),
        when_phrase=WHEN if with_date else None,
        payment_confirmed=paid,
    )
    return message


@pytest.mark.parametrize("family", sorted(FAMILY))
@pytest.mark.parametrize("with_deadline", [True, False])
@pytest.mark.parametrize("with_date", [True, False])
def test_as_quatro_combinacoes_de_cada_frase(family, with_deadline, with_date):
    message = _family_message(family, with_deadline=with_deadline, with_date=with_date)

    assert message == FAMILY[family][(with_deadline, with_date)]


@pytest.mark.parametrize("family", sorted(FAMILY))
@pytest.mark.parametrize("with_deadline", [True, False])
@pytest.mark.parametrize("with_date", [True, False])
def test_o_mesmo_substantivo_nao_aparece_duas_vezes(family, with_deadline, with_date):
    message = _family_message(family, with_deadline=with_deadline, with_date=with_date).lower()

    for noun in ("encomenda", "pedido"):
        assert message.count(noun) <= 1, f"{noun!r} repetido: {message}"
    assert "{" not in message


def test_o_estado_de_espera_sem_pagamento_tambem_fecha_as_quatro():
    # ``store_checking`` sem pagamento usa a mesma frase de ``received``.
    for with_deadline in (True, False):
        for with_date in (True, False):
            deadline = NOW + timedelta(minutes=60) if with_deadline else None
            _title, message = _promise_copy(
                _preorder("store_checking", deadline),
                status="new", is_delivery=False, copy=_copy(),
                when_phrase=WHEN if with_date else None,
            )
            assert message == FAMILY["encomenda_esperando_a_loja"][(with_deadline, with_date)]


def test_nenhuma_frase_da_familia_junta_o_aceite_com_o_dia_do_pedido():
    # A leitura errada era "a loja confirma/aceita ... para amanhã, a partir das 15h".
    deadline = NOW + timedelta(minutes=60)
    messages = [
        _promise_copy(_card(deadline), status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN)[1],
        _promise_copy(_card(None), status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN)[1],
    ]
    for state, paid in [("payment_confirmed", True), ("store_checking", True), ("store_checking", False), ("received", False)]:
        for value in (deadline, None):
            messages.append(_promise_copy(
                _preorder(state, value),
                status="new", is_delivery=False, copy=_copy(), when_phrase=WHEN, payment_confirmed=paid,
            )[1])

    for message in messages:
        assert "{" not in message
        assert "·" not in message, "dentro de frase vai a forma de frase (#2752)"
        assert "—" not in message
        for sentence in message.split(". "):
            mixes = "confirma" in sentence and "para amanhã" in sentence
            assert not mixes, sentence


@pytest.mark.parametrize("family", sorted(FAMILY))
@pytest.mark.parametrize("with_deadline", [True, False])
@pytest.mark.parametrize("with_date", [True, False])
def test_o_ato_da_loja_tem_um_verbo_so(family, with_deadline, with_date):
    # A revisão do checkout e o Pix dizem "confirmar"; o cartão dizia "aceitar".
    # Dois verbos para o mesmo ato fazem a cliente procurar a diferença (dono, 19/11).
    message = _family_message(family, with_deadline=with_deadline, with_date=with_date).lower()

    assert "aceit" not in message, message
    assert "confirm" in message
