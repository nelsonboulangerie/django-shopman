# ruff: noqa: F401, F811
"""Cartões de pedido de produto escritos como o cliente escreve (dono, 24/11/2026).

"A frase que enviei à Concierge foi de uma cliente real... eles escrevem errado com alguma
frequência." A leitura de produto aguenta o erro comum de escrita (letra trocada, acento
faltando, nome dito como se ouve, plural) e várias coisas numa frase só.

Fonte dos cartões:

- ``real``: falas reais de clientes, do conjunto conferido ``concierge/golden_set.json``
  (alpha, 04/09 a 03/10/2026, já redigidas e conferidas à mão), mais a da cliente que o
  dono repassou em 24/11;
- ``erro-comum``: os erros que o dono citou (campanha, croassant, acento faltando, plural)
  sobre o cardápio do seed;
- ``palavra-chave``: o produto que o cliente chama por outro nome, achado pelas palavras-chave
  do produto ("folhado de maçã" é o Chausson aux Pommes).

Cada cartão diz o que a resposta tem que mostrar e, quando o item não existe, que a casa
diz que não encontrou. Nenhuma resposta pode trazer o cardápio inteiro no lugar do item.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.storefront.concierge import intents, service
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _binding,
    _listed,
    _receive,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db

MENU = (
    ("CPG", "Pain de Campagne"), ("CPR", "Campagne Redondo"), ("CPX", "Campagne Passas & Castanhas"),
    ("FFGO", "Folhado de Frango"), ("FENDU", "Fendu"), ("TABAT", "Tabatière"), ("MELON", "Melonpan"),
    ("MELSA", "Melon Iced Sando"), ("PERDU", "Pain Perdu"), ("CO", "Cornet"), ("CI", "Ciabatta"),
    ("MIB", "Mini Baguete"), ("TRADI", "Baguette de Tradition"), ("CRO", "Croissant"), ("MDLN", "Madeleine"),
    ("PCHOC", "Pain au Chocolat"), ("COE", "Coelhinho de Chocolate"), ("CAP", "Cappuccino"),
    ("SP", "Espresso"), ("CQMA", "Croque Madame"), ("CQMO", "Croque Monsieur"), ("CN", "Chausson aux Pommes"),
)

#: As palavras-chave do seed (``keywords_map``), genéricas como as do ar: "pao", "frances",
#: "levain" em quase todo pão. Elas ajudam a achar ("folhado de maçã" é o Chausson aux Pommes)
#: e não podem estragar o que o nome já resolve.
KEYWORDS = {
    "CPG": ["pao", "campagne", "levain", "integral", "centeio"],
    "CPX": ["pao", "campagne", "levain", "passas", "castanhas", "especial"],
    "CI": ["pao", "italiano", "levain", "azeite", "aerado"],
    "CRO": ["croissant", "folhado", "manteiga", "frances"],
    "CN": ["chausson", "folhado", "maca", "frances"],
    "PCHOC": ["croissant", "folhado", "chocolate", "frances"],
    "MELON": ["pao-doce", "japones", "crocante", "amanteigado"],
    "CO": ["pao-doce", "creme", "recheado", "amanteigado"],
    "MDLN": ["bolinho", "frances", "classico", "doce"],
    "CQMO": ["lanche", "sanduiche", "frances", "presunto", "queijo", "gratinado"],
    "CQMA": ["lanche", "sanduiche", "frances", "ovo", "queijo", "gratinado"],
    "SP": ["cafe", "espresso", "bebida", "quente"],
    "CAP": ["cafe", "cappuccino", "leite", "bebida", "quente"],
    "FENDU": ["pao", "frances", "levain", "individual", "artesanal"],
    "TABAT": ["pao", "frances", "levain", "individual", "artesanal"],
    "MIB": ["pao", "frances", "levain", "mini", "individual"],
    "TRADI": ["pao", "frances", "levain", "artesanal", "crocante"],
    "COE": ["pao-doce", "bichinho", "criancas", "do-dia"],
    "PERDU": ["doce", "rabanada", "chapa", "frances"],
    "MELSA": ["doce", "frutas", "chantilly", "japones", "gelado"],
}

ASK, ORDER, HOUSE = "product_question", "order", "house"

#: (fonte, fala, a leitura da IA como no ar [(ato, trecho, o produto como o cliente escreveu, qtd)],
#:  o que a resposta mostra, o que a casa diz que não encontrou).
#: Várias coisas numa fala vêm num ato só, que é a leitura que falhou no ar em 24/11.
CARDS = (
    ("real", "Ainda tem pão champagne e folhado de maçã?", [(ASK, None, "pão champagne e folhado de maçã", 0)],
     ("Pain de Campagne", "Campagne Redondo", "Campagne Passas & Castanhas", "Chausson aux Pommes"), ()),
    ("real", "tem melonpan?", [(ASK, None, "melonpan", 0)], ("Melonpan",), ()),
    ("real", "Queria um Pain perdu, vocês entregam?", [(ORDER, None, "Pain perdu", 1)], ("Pain Perdu",), ()),
    ("real", "Corneto de chocolate 1", [(ORDER, None, "Corneto de chocolate", 1)], ("Cornet",), ()),
    ("real", "Bom dia. Poderia reservar uma baguete e um ciabata? Obrigado", [(ORDER, None, "uma baguete e um ciabata", 0)],
     ("Ciabatta", "Baguet"), ()),
    ("real", "Mais 4 croissant", [(ORDER, None, "croissant", 4)], ("Croissant",), ()),
    ("real", "Pode ser 2 pacotes e mais 3 madeleines", [(ORDER, None, "madeleines", 3)], ("Madeleine",), ()),
    ("real", "Boa tarde! Pode reservar 2 pain chocolat", [(ORDER, None, "pain chocolat", 2)], ("Pain au Chocolat",), ()),
    ("real", "Pode separar pra mim dois croassant", [(ORDER, None, "croassant", 2)], ("Croissant",), ()),
    ("real", "E coelinho ou o ursinho (o que tiver)", [(ASK, "E coelinho ou o ursinho (o que tiver)", "coelinho ou o ursinho", 0)],
     ("Coelhinho de Chocolate",), ("ursinho",)),
    ("real", "1 pão italiano grande e 2 croissant", [(ORDER, None, "1 pão italiano grande e 2 croissant", 0)],
     ("Croissant",), ("pão italiano grande",)),
    ("real", "Tem croissant hoje? e vocês aceitam vale refeição?", [(ASK, "Tem croissant hoje?", "croissant", 0), (HOUSE, "vocês aceitam vale refeição?", "", 0)],
     ("Croissant",), ()),
    ("real", "quero sim. mas a baguete de tradição, não tem?", [(ASK, "mas a baguete de tradição, não tem?", "baguete de tradição", 0)],
     ("Baguette de Tradition",), ()),
    ("erro-comum", "tem pão campanha?", [(ASK, None, "pão campanha", 0)], ("Pain de Campagne",), ()),
    ("erro-comum", "tem croassants hoje?", [(ASK, None, "croassants", 0)], ("Croissant",), ()),
    ("erro-comum", "queria 2 baguetes de tradiçao", [(ORDER, None, "baguetes de tradiçao", 2)], ("Baguette de Tradition",), ()),
    ("erro-comum", "tem capuccino?", [(ASK, None, "capuccino", 0)], ("Cappuccino",), ()),
    ("erro-comum", "um expresso e um croque madame", [(ORDER, None, "um expresso e um croque madame", 0)],
     ("Espresso", "Croque Madame"), ()),
    ("erro-comum", "tem tabatiere?", [(ASK, None, "tabatiere", 0)], ("Tabatière",), ()),
    # Pela palavra-chave (dono, 24/11/2026): "Folhado de maçã se refere claramente ao Chausson".
    ("palavra-chave", "tem folhado de maçã?", [(ASK, None, "folhado de maçã", 0)], ("Chausson aux Pommes",), ()),
    ("palavra-chave", "quero 2 folhados de maca", [(ORDER, None, "folhados de maca", 2)], ("Chausson aux Pommes",), ()),
    ("palavra-chave", "tem rabanada?", [(ASK, None, "rabanada", 0)], ("Pain Perdu",), ()),
    ("palavra-chave", "tem um sanduiche de presunto?", [(ASK, None, "sanduiche de presunto", 0)], ("Croque Monsieur",), ()),
)


@pytest.fixture
def menu(surface):
    for sku, name in MENU:
        product = _listed(sku, name, stock="10")
        if KEYWORDS.get(sku):
            product.keywords.add(*KEYWORDS[sku])


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
@pytest.mark.parametrize(("source", "said", "reading", "shows", "not_found"), CARDS,
                         ids=[card[1][:40] for card in CARDS])
def test_the_product_written_as_the_customer_writes_is_found(conversation, outbox, menu, monkeypatch, source, said,
                                                             reading, shows, not_found):
    from shopman.shop.tests.ai_support import configure_ai

    configure_ai("isolated-fixture", model="claude-sonnet-5")
    acts = [intents.Act(act, span=span or said, product=product, qty=qty) for act, span, product, qty in reading]
    monkeypatch.setattr(intents, "read_with_model", lambda text, **kwargs: (acts, 0.0, ""))
    monkeypatch.setattr(intents, "gate", lambda text, **kwargs: intents.GateDecision(False, "jev_unsure"))
    _receive(conversation, said, f"cartao-{[card[1] for card in CARDS].index(said)}")
    service.run_turn(conversation.pk, _binding(conversation).pk)
    reply = "\n\n".join(outbox.sent)
    for name in shows:
        assert name in reply, reply
    for asked in not_found:
        # Não tem: a casa diz, citando o que foi pedido (ou verifica com a equipe), nunca finge que achou.
        assert asked in reply and ("Não encontrei" in reply or "não tenho essa informação" in reply), reply
    if not not_found:
        assert "Não encontrei" not in reply, reply
    listed = [name for _sku, name in MENU if name in reply]
    assert len(listed) <= len(shows) + 3, reply  # nunca o cardápio inteiro no lugar do item
    if source == "palavra-chave":
        # O outro nome aponta UM produto: nem "qual deles?" com quem leva só uma das palavras.
        assert set(listed) == set(shows), reply
