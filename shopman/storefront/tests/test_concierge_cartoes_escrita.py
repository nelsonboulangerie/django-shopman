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
- ``observação``: falas reais do ar, da observação dos últimos 7 dias (18 a 24/11/2026, #3591),
  já redigidas, sem nome e sem telefone;
- ``palavra-chave``: o produto que o cliente chama por outro nome, achado pelas palavras-chave
  do produto ("folhado de maçã" é o Chausson aux Pommes).

Cada cartão diz o que a resposta tem que mostrar e, quando o item não existe, que a casa
diz que não encontrou. Nenhuma resposta pode trazer o cardápio inteiro no lugar do item.
"""

from __future__ import annotations

import json

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
    ("ITA", "Italiano Rústico"), ("BAT", "Bâtard"), ("CPBG", "Baguette Campagne"), ("BGG", "Baguete Gergelim"),
    ("BRBB", "Brioche Burger Bun"), ("TRABB", "Pão de Hambúrguer"), ("BRCH", "Brioche Chocolat"),
    ("FORMA", "Shokupan"), ("FOA", "Focaccia Alecrim"), ("FOC", "Focaccia Cebola Roxa"), ("CHLH", "Challah"),
    ("HOL", "Pão para Hot Dog"), ("BRRSN", "Pain aux Raisins"),
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
    "BGG": ["pao", "frances", "levain", "gergelim", "azeite"],
    "BRBB": ["brioche", "hamburger", "manteiga", "ovos"],
    "TRABB": ["pao", "hamburger", "levain", "individual"],
    "FORMA": ["pao", "forma", "japones", "macio", "fatiado", "shokupan", "artesanal"],
    "FOA": ["focaccia", "alecrim", "italiano", "azeite"],
    "HOL": ["pao", "hotdog", "manteiga", "salgado"],
    "BRRSN": ["pain", "raisins", "passas", "folhado"],
}

ASK, ORDER, HOUSE = "product_question", "order", "house"

#: (fonte, fala, a leitura da IA como no ar [(ato, trecho, o produto como o cliente escreveu, qtd)],
#:  o que a resposta mostra, o que a casa diz que não encontrou).
#: Várias coisas numa fala vêm num ato só, que é a leitura que falhou no ar em 24/11.
CARDS = (
    # Quatro Campagne no cardápio e a lista mostra três: o Pain de Campagne vem primeiro.
    ("real", "Ainda tem pão champagne e folhado de maçã?", [(ASK, None, "pão champagne e folhado de maçã", 0)],
     ("Pain de Campagne", "Chausson aux Pommes"), ()),
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
     ("Italiano Rústico", "Croissant"), ()),
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
    # "oval" distingue: o Pain de Campagne é o oval (dono, 24/11/2026). O Redondo o contradiz e
    # o de passas é variante: vai direto, sem pergunta.
    ("palavra-chave", "1 campagne oval", [(ORDER, None, "campagne oval", 1)], ("Pain de Campagne",), ()),
    # Falas reais da observação do ar, 18 a 24/11/2026 (#3591), redigidas: o pedido de produto
    # como o cliente escreveu, fora as do número do dono (testes) e as com nome que a redação
    # deixou passar. A leitura da IA vem como no ar: várias coisas num ato só.
    ("observação", "Por favor, separa pra mim, 3 baguetes francesas e 2 ciabattas…pego as 11:30, pode ser?",
     [(ORDER, None, "baguetes francesas e 2 ciabattas", 0)], ("Baguet", "Ciabatta"), ()),
    ("observação", "Ainda há disponível pão de forma artesanal, 1 pacote?", [(ASK, None, "pão de forma artesanal", 0)],
     ("Shokupan",), ()),
    ("observação", "Vce consegue reservar pra mim , 1 baguete tradicional e um rústico grande?",
     [(ORDER, None, "1 baguete tradicional e um rústico grande", 0)], ("Baguette de Tradition", "Rústico"), ()),
    ("observação", "Oii tudo bem? Queria encomendar 3 pães brioche de hambúrguer pra amanhã por favor",
     [(ORDER, None, "pães brioche de hambúrguer", 3)], ("Brioche Burger Bun",), ()),
    ("observação", "Estou entrando em contato para encomendar 6 unidades de baguettes para hoje umas 15h - 15h30, teria como?",
     [(ORDER, None, "baguettes", 6)], ("Baguet",), ()),
    ("observação", "Tem pão au chocolat?", [(ASK, None, "pão au chocolat", 0)], ("Pain au Chocolat",), ()),
    ("observação", "Gostaria de encomendar uma focaccia para hoje", [(ORDER, None, "focaccia", 1)], ("Focaccia",), ()),
    ("observação", "Vcs tem baguette, ciabatta e batard?", [(ASK, None, "baguette, ciabatta e batard", 0)],
     ("Baguet", "Ciabatta", "Bâtard"), ()),
    ("observação", "e do pão de champanhe e passas", [(ASK, None, "pão de champanhe e passas", 0)],
     ("Campagne Passas & Castanhas",), ()),
    ("observação", "1 pão italiano grande", [(ORDER, None, "pão italiano grande", 1)], ("Italiano Rústico",), ()),
    ("observação", "Queria 1 pão italiano rústico grande , 4 baguetes campagne e 2 ciabatas p/ entrega hoje à tarde .",
     [(ORDER, None, "1 pão italiano rústico grande , 4 baguetes campagne e 2 ciabatas", 0)],
     ("Italiano Rústico", "Baguette Campagne", "Ciabatta"), ()),
    ("observação", "Quero 8 Madalena", [(ORDER, None, "Madalena", 8)], ("Madeleine",), ()),
    ("observação", "Meninas,vocês podem reservar 4 bisnaguinhas pra mim?", [(ORDER, None, "bisnaguinhas", 4)],
     (), ("bisnaguinhas",)),
    ("observação", "Boa tarde , aí vcs tem panetone?", [(ASK, None, "panetone", 0)], (), ("panetone",)),
    ("observação", "1 brioche e 1 campagne oval", [(ORDER, None, "1 brioche e 1 campagne oval", 0)],
     ("Brioche", "Campagne"), ()),
    ("observação", "Gostaria de reservar um pão rústico por favor!", [(ORDER, None, "pão rústico", 1)], ("Rústico",), ()),
    ("observação", "Queria fazer encomenda de 4 pães ( chalá / gergelim e 2 pct de hot-dog )",
     [(ORDER, None, "4 pães ( chalá / gergelim e 2 pct de hot-dog )", 0)], ("Challah", "Gergelim", "Hot Dog"), ()),
    ("observação", "Meninas, ainda consigo um bâtard e um campagne oval para hoje?",
     [(ORDER, None, "um bâtard e um campagne oval", 0)], ("Bâtard", "Campagne"), ()),
)


#: Os cartões que só passam com as palavras-chave da proposta (``keywords_proposal.json``, #3595):
#: o nome que o cliente fala está longe demais do cardápio para a correção de escrita.
NEEDS_PROPOSAL = {
    "Quero 8 Madalena",  # Madeleine: "madalena"
    "Queria fazer encomenda de 4 pães ( chalá / gergelim e 2 pct de hot-dog )",  # Challah: "chalá"
}


#: O que ainda falha, com a issue que carrega (vazio: nada).
KNOWN_GAPS: dict[str, str] = {}


def _proposal() -> dict:
    from shopman.storefront.management.commands.concierge_keywords import PROPOSAL

    return json.loads(PROPOSAL.read_text(encoding="utf-8"))["products"]


@pytest.fixture
def menu(surface, request):
    proposal = _proposal() if request.node.callspec.params["keywords"] == "proposta" else {}
    for sku, name in MENU:
        product = _listed(sku, name, stock="10")
        if KEYWORDS.get(sku):
            product.keywords.add(*KEYWORDS[sku])
        entry = proposal.get(sku) or {}
        if entry.get("add"):
            product.keywords.add(*entry["add"])
        if entry.get("remove"):
            product.keywords.remove(*entry["remove"])


def _cases():
    for card in CARDS:
        for keywords in ("seed", "proposta"):
            marks = (
                [pytest.mark.xfail(strict=True, reason=KNOWN_GAPS[card[1]])] if card[1] in KNOWN_GAPS
                else [pytest.mark.xfail(strict=True, reason="só com as palavras-chave da proposta")]
                if keywords == "seed" and card[1] in NEEDS_PROPOSAL else []
            )
            yield pytest.param(*card, keywords, marks=marks, id=f"{keywords}-{card[1][:40]}")


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
@pytest.mark.parametrize(("source", "said", "reading", "shows", "not_found", "keywords"), list(_cases()))
def test_the_product_written_as_the_customer_writes_is_found(conversation, outbox, menu, monkeypatch, source, said,
                                                             reading, shows, not_found, keywords):
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
