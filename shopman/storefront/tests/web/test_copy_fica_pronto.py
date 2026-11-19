"""A casa diz "fica pronto", nunca "sai do forno" (dono, 16/11/2026).

Trava da copy ao cliente da loja: o registro de omotenashi (que é a fonte dos
fallbacks da Presentation, conferidos por ``test_copy_fallback_drift``) e os
modelos de notificação (``shop/notification_copy.py``). Reprova "sai do forno",
"saiu", "sair do forno", "saída do forno" e o "sair" que fala da fornada.

"Saiu para entrega" não é o verbo proibido: ali quem sai é o pedido, com o
entregador. O mesmo vale para "sair da conta".

O que ainda diz o verbo antigo e não foi trocado está em ``PENDING``, cada item
com o motivo. A lista só encolhe: frase nova com "sair do forno" reprova aqui, e
frase da lista que for corrigida também reprova, até sair da lista (#2791).
"""
from __future__ import annotations

import re

from shopman.shop.notification_copy import CUSTOMER_COPY
from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS

#: O pão, o lote ou a fornada como sujeito de "sair".
_OVEN = r"(?:do|de|no)\s+forno"
_SAIR = r"(?:sai|saiu|sair|saem|saíram|saindo|sairá|saída|saído|saídos|saídas)"

FORBIDDEN = (
    # "sai do forno", "saiu do forno", "acabou de sair do forno", "saída do forno".
    re.compile(rf"\b{_SAIR}\b(?:\s+\w+){{0,3}}?\s+{_OVEN}\b", re.IGNORECASE),
    # "saiu", menos quando é o pedido que saiu para entrega.
    re.compile(r"\bsaiu\b(?!\s+para\s+entrega)", re.IGNORECASE),
    # "Sai fresquinho", "sai quentinho".
    re.compile(r"\bsai\s+(?:fresquinh|quentinh)", re.IGNORECASE),
)

#: Na frase que fala de fornada, lote ou fila de espera, "sair" é o do forno.
_BATCH_TALK = re.compile(r"\b(?:fornada|fornadas|lote|fila de espera)\b", re.IGNORECASE)
_SAIR_ALONE = re.compile(r"\b(?:sai|sair|saem|saíram)\b(?!\s+para\s+entrega)", re.IGNORECASE)


def says_out_of_the_oven(text: str) -> bool:
    if any(pattern.search(text) for pattern in FORBIDDEN):
        return True
    return bool(_BATCH_TALK.search(text) and _SAIR_ALONE.search(text))


def _registry_texts() -> dict[str, str]:
    """``chave/momento/público/campo`` → texto, para toda entrada do registro."""
    texts: dict[str, str] = {}
    for key, moments in OMOTENASHI_DEFAULTS.items():
        for moment, audiences in moments.items():
            for audience, entry in audiences.items():
                for field in ("title", "message"):
                    value = getattr(entry, field, "") or ""
                    if value:
                        texts[f"{key}/{moment}/{audience}/{field}"] = value
    return texts


def _notification_texts() -> dict[str, str]:
    return {
        f"{event}/{field}": copy[field]
        for event, copy in CUSTOMER_COPY.items()
        for field in ("subject", "body")
        if copy.get(field)
    }


#: O que ainda diz o verbo antigo, e por quê não foi trocado junto com a fila (#2791).
PENDING = {
    # Aviso do chamado da fila: tem modelo aprovado na Meta com o mesmo texto
    # (`fila_vaga_disponivel`, "A fornada que você esperava saiu."). Texto de
    # modelo aprovado não se edita, reaprova; o texto livre muda junto com ele.
    "notification:waitlist_available/subject",
    "notification:waitlist_available/body",
    # Aviso "saiu do forno" (Marketing): idem, modelo `saiu_do_forno` na Meta.
    "notification:production_ready/subject",
    "notification:production_ready/body",
    # Sacola vazia de manhã e a oferta do próximo lote: fora das telas da fila.
    "registry:CART_EMPTY/manha/anon/message",
    "registry:CART_EMPTY/manha/*/message",
    "registry:KINTSUGI_PLANNED_OFFER/*/*/message",
}


def _offenders() -> set[str]:
    found = {f"registry:{where}" for where, text in _registry_texts().items() if says_out_of_the_oven(text)}
    found |= {
        f"notification:{where}" for where, text in _notification_texts().items() if says_out_of_the_oven(text)
    }
    return found


def test_the_detector_knows_the_forbidden_forms():
    for text in (
        "Sai do forno às 9h.",
        "Sua fornada saiu!",
        "Acabou de sair do forno.",
        "Aviso na saída do forno.",
        "Assim que a fornada sair, a gente te avisa.",
        "Sua reserva está na fila de espera da fornada prevista para hoje. Avisamos quando sair.",
        "Sai fresquinho no próximo lote.",
    ):
        assert says_out_of_the_oven(text), text


def test_the_detector_leaves_delivery_and_account_alone():
    for text in (
        "Seu pedido saiu para entrega.",
        "Saiu para entrega",
        "Avisamos quando sair para entrega.",
        "Entrega combinada para hoje, 15h às 15h30. Avisamos quando sair.",
        "Seu pedido está pronto e aguardando o entregador. Avisamos assim que sair.",
        "Você vai sair desta conta para entrar com outro telefone.",
        "Assim que a fornada ficar pronta, a gente te avisa para confirmar.",
        "Do forno para a sua mesa.",
    ):
        assert not says_out_of_the_oven(text), text


def test_no_customer_copy_says_the_bread_leaves_the_oven_beyond_the_known_list():
    offenders = _offenders()

    new = sorted(offenders - PENDING)
    assert not new, f'a casa diz "fica pronto", nunca "sai do forno": {new}'


def test_the_pending_list_only_shrinks():
    fixed = sorted(PENDING - _offenders())

    assert not fixed, f"estas frases já não dizem o verbo antigo: tire-as de PENDING: {fixed}"


def test_the_queue_phrases_say_ficar_pronta():
    registry = _registry_texts()

    assert registry["TRACKING_WAITLIST_WAITING_MESSAGE/*/*/message"] == (
        "Assim que a fornada ficar pronta, a gente te avisa para confirmar. Nada foi cobrado ainda."
    )
    assert registry["TRACKING_PROMISE_WAITLIST_MESSAGE/*/*/message"] == (
        "Sua reserva está na fila de espera da fornada prevista para {when}. Avisamos quando ficar pronta."
    )
    assert registry["TRACKING_PROMISE_WAITLIST_MESSAGE_PAID/*/*/message"] == (
        "Pagamento recebido. Sua reserva está na fila de espera da fornada prevista para {when}. "
        "Avisamos quando ficar pronta."
    )
