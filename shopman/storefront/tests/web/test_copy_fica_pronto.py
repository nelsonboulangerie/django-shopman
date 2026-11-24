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


def _dynamic_collection_texts() -> dict[str, str]:
    """Rótulo e descrição das seções vivas do cardápio (``shop/dynamic_collections.py``)."""
    from shopman.shop import dynamic_collections

    out: dict[str, str] = {}
    for ref in sorted(dynamic_collections._registry):
        meta = dynamic_collections._registry[ref].meta
        out[f"{ref}/label"] = meta.label
        out[f"{ref}/description"] = meta.description or ""
    return out


def _badge_texts() -> dict[str, str]:
    """O selo de fornada do produto, nos dois tempos (agora e há N minutos)."""
    from datetime import UTC, datetime, timedelta

    from shopman.storefront.presentation.fomo import badges_for_product

    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    out: dict[str, str] = {}
    for name, finished in (("agora", now), ("ha_12_min", now - timedelta(minutes=12))):
        for badge in badges_for_product("SKU", production={"finished_at": finished}, now=now):
            out[f"{badge.type}/{name}"] = badge.label
    return out


def _alert_type_texts() -> dict[str, str]:
    """O nome de cada tipo de aviso, como a cliente lê na conta."""
    from shopman.storefront.models import StockAlertSubscription

    return {value: str(label) for value, label in StockAlertSubscription.AlertType.choices}


def _screen_texts() -> dict[str, list[str]]:
    """O que as telas da loja dizem: os trechos de texto do ``<template>`` de cada
    página e componente, sem comentário. Um trecho por nó, para a frase de um lugar
    não se misturar com a de outro."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[4] / "surfaces" / "storefront-nuxt" / "app"
    out: dict[str, list[str]] = {}
    for path in sorted(app.rglob("*.vue")):
        source = path.read_text(encoding="utf-8")
        start, end = source.find("<template"), source.rfind("</template>")
        if start < 0 or end < 0:
            continue
        template = re.sub(r"<!--.*?-->", " ", source[start:end], flags=re.DOTALL)
        # Só o texto entre as marcas: expressões, atributos e classes ficam de fora.
        nodes = [" ".join(node.split()) for node in re.findall(r">([^<>{}]+)<", template)]
        nodes = [node for node in nodes if node]
        if nodes:
            out[str(path.relative_to(app))] = nodes
    return out


def says_out_of_the_oven_on_screen(text: str) -> bool:
    """Nas telas, só o que fala do forno ou da fornada. O "saiu" sozinho fica de fora:
    a loja também diz "a mensagem que saiu do seu WhatsApp"."""
    if FORBIDDEN[0].search(text) or FORBIDDEN[2].search(text):
        return True
    return bool(_BATCH_TALK.search(text) and _SAIR_ALONE.search(text))


#: O que ainda diz o verbo antigo, e por quê. Vazia desde 19/11/2026: o aviso do
#: chamado da fila e o de fornada pronta nunca tiveram modelo submetido à Meta
#: (``docs/reference/whatsapp-templates-meta.md``), então os textos mudaram junto
#: com a sacola vazia, a oferta do próximo lote e a seção viva do cardápio.
PENDING: set[str] = set()


def _offenders() -> set[str]:
    found = {f"registry:{where}" for where, text in _registry_texts().items() if says_out_of_the_oven(text)}
    found |= {
        f"notification:{where}" for where, text in _notification_texts().items() if says_out_of_the_oven(text)
    }
    found |= {
        f"collection:{where}" for where, text in _dynamic_collection_texts().items() if says_out_of_the_oven(text)
    }
    found |= {f"badge:{where}" for where, text in _badge_texts().items() if says_out_of_the_oven(text)}
    found |= {f"alert-type:{where}" for where, text in _alert_type_texts().items() if says_out_of_the_oven(text)}
    found |= {
        f"screen:{where}"
        for where, nodes in _screen_texts().items()
        if any(says_out_of_the_oven_on_screen(node) for node in nodes)
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
        "Quando a fornada ficar pronta, avisamos para você confirmar. Nada foi cobrado ainda."
    )
    assert registry["TRACKING_PROMISE_WAITLIST_MESSAGE_QUEUED/*/*/message"] == (
        "Sua reserva está na fila de espera da fornada prevista para {when}."
    )
    assert registry["TRACKING_PROMISE_WAITLIST_MESSAGE/*/*/message"] == (
        "Sua reserva está na fila de espera da fornada prevista para {when}. Avisamos quando ficar pronta."
    )
    assert registry["TRACKING_PROMISE_WAITLIST_MESSAGE_PAID/*/*/message"] == (
        "Pagamento recebido. Sua reserva está na fila de espera da fornada prevista para {when}. "
        "Avisamos quando ficar pronta."
    )


def test_the_rest_of_the_house_copy_says_ficar_pronto():
    from shopman.shop.notification_copy import CUSTOMER_COPY

    registry = _registry_texts()
    assert registry["CART_EMPTY/manha/anon/message"] == "Pão fresquinho acabou de ficar pronto."
    assert registry["CART_EMPTY/manha/*/message"] == "Pão fresquinho acabou de ficar pronto."
    # O próximo lote fala de disponibilidade, como o produto (dono, 24/11/2026).
    assert registry["KINTSUGI_PLANNED_OFFER/*/*/title"] == "Disponível {when}"
    assert "KINTSUGI_PLANNED_OFFER/*/*/message" not in registry
    # O chamado da fila: a mesma voz do acompanhamento ("Chegou a sua vez!", "vaga").
    assert CUSTOMER_COPY["waitlist_available"]["subject"] == "Chegou a sua vez: confirme o pedido {order_ref_short}"
    assert CUSTOMER_COPY["waitlist_available"]["body"] == (
        "Oi{customer_name_greeting}! A fornada que você esperava ficou pronta. "
        "Confirme seu pedido *{order_ref_short}* para garantir a sua vaga: {tracking_url}"
    )
    # "Fornada pronta", para a concordância não depender do gênero do produto.
    assert CUSTOMER_COPY["production_ready"]["subject"] == "Fornada pronta: {product_name}"
    assert "a fornada que acabou de ficar pronta: *{product_name}*" in CUSTOMER_COPY["production_ready"]["body"]


def test_the_live_menu_section_has_the_new_name():
    texts = _dynamic_collection_texts()

    assert texts["fresh_from_oven/label"] == "Acabaram de ficar prontos"
    assert texts["fresh_from_oven/description"] == "Ficaram prontos nos últimos 60 minutos."


def test_the_badge_the_alert_name_and_the_screens_say_ficar_pronto():
    badges = _badge_texts()
    assert badges["fresh/agora"] == "Fornada pronta agora"
    assert badges["fresh/ha_12_min"] == "Fornada pronta há 12 min"
    assert _alert_type_texts()["production_ready"] == "fornada pronta"
    # A varredura das telas enxerga a loja: sem isso, ela passaria por não ler nada.
    screens = _screen_texts()
    assert len(screens) > 50
    assert any("o pão ficou pronto" in node for node in screens["pages/conta/seguranca.vue"])
    # E acusaria a frase antiga, sem confundir com o que não é do forno.
    assert says_out_of_the_oven_on_screen("recebe o aviso de que o pão saiu do forno.")
    assert not says_out_of_the_oven_on_screen("a mensagem que saiu do seu WhatsApp.")


def _house_rules_texts() -> dict[str, str]:
    """Toda frase escrita nas regras da casa da Concierge (``storefront/concierge/house_rules.py``).

    São os exemplos que ensinam a Concierge a falar com a cliente: o que eles dizem, ela
    repete. Lidos como literais do código, sem importar o módulo (#2797).
    """
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "concierge" / "house_rules.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
            out[f"house_rules.py:{node.lineno}"] = node.value
    return out


def test_as_regras_da_casa_da_concierge_dizem_ficar_pronto():
    """A Concierge aprende a falar pelos exemplos das regras da casa (#2797, item 1):
    "A fornada acabou de sair do forno" virava a frase dela para a cliente."""
    texts = _house_rules_texts()
    assert texts, "as regras da casa sumiram do lugar: a trava não está varrendo nada"
    offenders = {where: text for where, text in texts.items() if says_out_of_the_oven(text)}
    assert offenders == {}
