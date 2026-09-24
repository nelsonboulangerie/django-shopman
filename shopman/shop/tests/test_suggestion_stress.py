"""Estresse do adicional: centenas de sacolas, uma NOTA de atendente para cada.

O dono (23/09): "Vamos estabelecer um sistema bastante útil e inteligente, não
algo desumano ou engessado!". Teste de caso isolado prova o caso isolado; este
aqui mede o motor contra o cardápio inteiro de uma vez.

**O cardápio** é um recorte fiel do seed (SKU, nome, preço, coleção e
palavras-chave do `seed.py`), e os atributos saem do MESMO comando que os
propõe no alpha (`propose_product_attributes`) — inclusive a lacuna real do
croissant, cujo sabor nenhuma coleção responde. Os pães doces de Macios estão
também em Doces desde 24/09 (dono: "Brioche Chocolat é Doce sim").

**A nota** vem de uma rubrica que NÃO lê os atributos do motor. Cada SKU tem um
papel "de verdade" (``TRUTH``), o que um atendente vê no balcão, e a rubrica
julga com ele:

- **3 · óbvio/ideal** — o que o atendente ofereceria primeiro;
- **2 · aceitável** — faz sentido, não é o primeiro reflexo;
- **1 · estranho** — defensável, mas ninguém do balcão diria isso;
- **0 · absurdo** — substituto (mesmo papel do que já está na sacola), bebida
  com bebida, ou item que não dá para adicionar.

O histórico de afinidade é ADVERSÁRIO de propósito: croque com croque, café
com café, pão com pão, croissant com pain au chocolat, madeleine com água.
É o histórico real de mesa, e é o que levou o Croque Monsieur ao Croque Madame.

Para ver a tabela: ``pytest shopman/shop/tests/test_suggestion_stress.py -s``;
com ``SUGGESTION_STRESS_REPORT=<arquivo>`` ela também é gravada.
"""

from __future__ import annotations

import itertools
import os
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product

from shopman.shop.models import ProductAffinity
from shopman.shop.projections.suggestions import COMPLEMENT, suggest

pytestmark = pytest.mark.django_db

CHANNEL = "loja"

# (sku, nome, preço, coleção primária, coleções secundárias, palavras-chave)
# Palavras-chave como no seed — inclusive a falta delas (Mocha, Brioche Chocolat).
CATALOG = [
    ("SP", "Espresso", 800, "bebidas-quentes", [], ["cafe", "espresso", "bebida", "quente"]),
    ("COAD", "Café Coado", 1200, "bebidas-quentes", [], ["cafe", "coado", "bebida", "quente"]),
    ("CAP", "Cappuccino", 1200, "bebidas-quentes", [], ["cafe", "cappuccino", "leite", "bebida"]),
    ("MOCHA", "Mocha", 2200, "bebidas-quentes", [], []),
    ("CHCAM", "Chá Camille", 1400, "bebidas-quentes", [], ["cha", "blend", "bebida", "quente"]),
    ("CHOQ", "Chocolate Quente", 1800, "bebidas-quentes", [], []),
    ("CE", "Coffee Float", 1800, "bebidas-geladas", [], ["cafe", "sorvete", "gelado", "bebida"]),
    ("FRAP", "Frappé", 1800, "bebidas-geladas", [], ["cafe", "frappe", "gelado", "bebida"]),
    ("AGUA", "Água", 600, "bebidas-geladas", [], ["agua", "mineral", "bebida", "frio"]),
    ("SDLA", "Soda de Laranja", 1400, "bebidas-geladas", [], ["soda", "laranja", "bebida"]),
    ("CHHIB", "Chá Hibisco", 1800, "bebidas-geladas", [], ["cha", "hibisco", "gelado", "bebida"]),
    ("TRADI", "Baguette de Tradition", 1600, "rusticos", [], ["pao", "baguete"]),
    ("CPG", "Pain de Campagne", 2200, "rusticos", [], ["pao", "levain"]),
    ("MIB", "Mini Baguete", 900, "rusticos", [], ["pao", "baguete"]),
    ("FORMA", "Shokupan", 2800, "macios", [], ["pao", "forma"]),
    ("BRCH", "Brioche Chocolat", 1000, "macios", ["doces"], []),
    ("COC", "Cornet de Chocolate", 900, "macios", ["doces"], []),
    ("CRO", "Croissant", 1300, "folhados", [], ["croissant", "folhado", "manteiga"]),
    ("PCHOC", "Pain au Chocolat", 1500, "folhados", ["doces"], ["croissant", "folhado", "chocolate"]),
    ("FFGO", "Folhado de Frango", 2000, "folhados", ["salgados"], []),
    ("CRPQ", "Croissant Presunto e Queijo", 1600, "folhados", ["salgados"], []),
    ("CQMO", "Croque Monsieur", 2400, "salgados", [], ["lanche", "sanduiche", "queijo"]),
    ("CQMA", "Croque Madame", 2800, "salgados", [], ["lanche", "sanduiche", "ovo"]),
    ("CQCOM", "Croque Complet", 3000, "salgados", [], ["lanche", "sanduiche", "ovo"]),
    ("QJQT", "Queijo-Quente", 2600, "salgados", [], ["lanche", "queijo"]),
    ("JB", "Jambon-Beurre", 1800, "salgados", [], ["sanduiche", "presunto"]),
    ("PERDU", "Pain Perdu", 1800, "doces", [], ["doce", "rabanada", "chapa"]),
    ("MDLN", "Madeleine", 600, "doces", [], ["bolinho", "frances", "doce"]),
    ("TJ", "Tea Jelly", 1800, "doces", [], ["doce", "gelatina", "cha", "sobremesa"]),
    ("MA", "Maçã", 1300, "doces", [], []),
    ("GL", "Geleia St. Dalfour (mini)", 1600, "mercearia", [], ["mercearia", "geleia", "fruta"]),
    ("MT", "Mostarda da Casa", 1800, "mercearia", [], ["mercearia", "mostarda"]),
    ("QP", "Queijo Pomerode", 3200, "mercearia", [], ["mercearia", "queijo"]),
    ("GR", "Café em Grão (250g)", 4200, "mercearia", [], ["mercearia", "cafe", "grao"]),
]

#: O papel de verdade, como o balcão vê — independente dos atributos derivados.
TRUTH = {
    "SP": "bebida_quente", "COAD": "bebida_quente", "CAP": "bebida_quente",
    "MOCHA": "bebida_quente", "CHCAM": "bebida_quente", "CHOQ": "bebida_quente",
    "CE": "bebida_gelada", "FRAP": "bebida_gelada", "AGUA": "bebida_gelada",
    "SDLA": "bebida_gelada", "CHHIB": "bebida_gelada",
    "TRADI": "pao", "CPG": "pao", "MIB": "pao", "FORMA": "pao",
    "BRCH": "doce", "COC": "doce", "PCHOC": "doce",
    "CRO": "folhado",
    "FFGO": "salgado", "CRPQ": "salgado",
    "CQMO": "salgado", "CQMA": "salgado", "CQCOM": "salgado", "QJQT": "salgado", "JB": "salgado",
    "PERDU": "doce", "MDLN": "doce", "TJ": "doce", "MA": "doce",
    "GL": "acompanhamento", "MT": "acompanhamento", "QP": "acompanhamento",
    "GR": "varejo",
}
DRINKS = {"bebida_quente", "bebida_gelada"}
#: O salgado LEVE que o dono pediu para doce + bebida (24/09): croissant de
#: presunto e queijo, folhado de frango, queijo-quente.
LIGHT_SAVORY = {"CRPQ", "FFGO", "QJQT"}
FOODS = {"pao", "doce", "folhado", "salgado"}

#: O histórico de mesa, adversário de propósito.
AFFINITY = [
    ("CQMA", "CQMO", 9.0), ("CQMA", "CQCOM", 6.0), ("CQMO", "QJQT", 5.0),
    ("SP", "CAP", 7.0), ("COAD", "SP", 5.0), ("CAP", "CHOQ", 4.0),
    ("CRO", "PCHOC", 8.0), ("TRADI", "CPG", 6.0), ("TRADI", "MIB", 5.0),
    ("TRADI", "AGUA", 1.02), ("MDLN", "AGUA", 4.0), ("CQMA", "SP", 3.0),
    ("CRO", "GR", 5.0), ("CAP", "GR", 4.0), ("SP", "MDLN", 1.5),
    ("JB", "SDLA", 1.3), ("MDLN", "PERDU", 6.0), ("FRAP", "CE", 5.0),
    ("QJQT", "AGUA", 2.5), ("PCHOC", "CAP", 2.0),
]

ESGOTADO = {"availability_policy": "planned_ok", "total_promisable": Decimal("0"), "is_planned": False}


@pytest.fixture(autouse=True)
def _fresh_caches():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def menu():
    listing = Listing.objects.create(ref=CHANNEL, name="Loja", is_active=True)
    collections = {}
    for sku, name, price, primary, secondary, keywords in CATALOG:
        product = Product.objects.create(
            sku=sku, name=name, base_price_q=price, is_published=True,
            is_sellable=True, availability_policy="demand_ok",
        )
        ListingItem.objects.create(
            listing=listing, product=product, price_q=price, is_published=True, is_sellable=True,
        )
        product.keywords.add(*keywords)
        for ref, is_primary in [(primary, True)] + [(r, False) for r in secondary]:
            if ref not in collections:
                collections[ref] = Collection.objects.create(ref=ref, name=ref)
            CollectionItem.objects.create(
                collection=collections[ref], product=product, is_primary=is_primary,
            )
    # Os atributos saem do mesmo comando que os propõe no alpha.
    call_command("propose_product_attributes", verbosity=0)
    now = timezone.now()
    for a, b, lift in AFFINITY:
        for x, y in ((a, b), (b, a)):
            ProductAffinity.objects.create(
                sku_a=x, sku_b=y, together_count=20, score=20.0,
                lift=lift, window_days=365, computed_at=now,
            )
    return listing


@contextmanager
def _unavailable(skus: set[str]):
    """Esgota ``skus`` no portão de disponibilidade, e só eles."""
    from shopman.shop.projections import cart as cart_projection

    real = cart_projection._availability

    def fake(asked, session_key, channel_ref):
        avail, own = real(asked, session_key, channel_ref)
        avail = dict(avail)
        for sku in skus:
            if sku in asked:
                avail[sku] = ESGOTADO
        return avail, own

    with patch("shopman.shop.projections.cart._availability", side_effect=fake):
        yield


# --- a rubrica --------------------------------------------------------------

IDEAL_DRINK = {"salgado": "bebida_gelada", "doce": "bebida_quente",
               "pao": "bebida_quente", "folhado": "bebida_quente"}
IDEAL_FOOD = {"bebida_quente": {"doce", "folhado"}, "bebida_gelada": {"salgado"}}


def grade(cart: tuple[str, ...], suggested: str | None, available: set[str]) -> tuple[int, str]:
    """A nota de atendente para ``suggested`` diante de ``cart``, e o porquê."""
    kinds = {TRUTH[s] for s in cart}
    foods = kinds & FOODS
    drinks = kinds & DRINKS
    offerable = available - set(cart)
    drink_available = any(TRUTH[s] in DRINKS for s in offerable)
    food_available = any(TRUTH[s] in FOODS for s in offerable)

    if suggested is None:
        if foods and not drinks:
            return (1, "calou com bebida disponível") if drink_available else (3, "calou: não há bebida")
        if drinks and not foods:
            return (1, "calou com comida disponível") if food_available else (3, "calou: não há comida")
        if "salgado" in foods and drinks and "doce" not in foods:
            doce_available = any(TRUTH[s] == "doce" for s in offerable)
            return (1, "calou com doce disponível") if doce_available else (3, "calou: não há doce")
        if "doce" in foods and drinks and "salgado" not in foods:
            savory_available = any(TRUTH[s] == "salgado" for s in offerable)
            return (1, "calou com salgado disponível") if savory_available else (3, "calou: não há salgado")
        return 3, "mesa completa: calar é certo"

    k = TRUTH[suggested]
    if suggested not in available:
        return 0, "indisponível"
    if k in kinds:
        return 0, "substituto (mesmo papel da sacola)"
    if k in DRINKS and drinks:
        return 0, "bebida com bebida"
    if k == "varejo":
        return 1, "varejo oferecido numa refeição"

    if foods and not drinks:
        if k in DRINKS:
            if any(IDEAL_DRINK.get(f) == k for f in foods):
                return 3, "comida → a bebida que ela pede"
            return 2, "comida → bebida cruzada"
        if not drink_available:
            if "salgado" in foods and k == "doce":
                return 3, "sem bebida: salgado → doce"
            return 2, "sem bebida: outra comida"
        if k == "acompanhamento" and "pao" in foods:
            return 2, "pão → acompanhamento (antes da bebida)"
        return 1, "comida → comida com bebida disponível"

    if drinks and not foods:
        if k in FOODS:
            if any(k in IDEAL_FOOD.get(d, set()) for d in drinks):
                return 3, "bebida → a comida que ela pede"
            return 2, "bebida → comida cruzada"
        return 1, "bebida → acompanhamento"

    if foods and drinks:
        if "salgado" in foods and "doce" not in foods:
            if k == "doce":
                return 3, "salgado + bebida → doce"
            return 2, "salgado + bebida → outra comida"
        if "doce" in foods:
            # Dono, 24/09: 1º um salgado LEVE (completa a mesa), 2º o pão.
            if k == "salgado":
                if suggested in LIGHT_SAVORY:
                    return 3, "doce + bebida → salgado leve"
                return 2, "doce + bebida → salgado de prato"
            if k == "acompanhamento":
                return 1, "doce + bebida → acompanhamento"
            return 2, "doce + bebida → um convite a mais"
        if k == "doce":
            return 3, "comida + bebida → doce"
        if k == "acompanhamento" and "pao" in foods:
            return 3, "pão + bebida → o que se passa no pão"
        return 2, "comida + bebida → outra comida"

    # Sacola só de acompanhamento/varejo.
    return (2, "mercearia → comida/bebida") if k in FOODS | DRINKS else (1, "mercearia → mercearia")


# --- as sacolas -------------------------------------------------------------


def baskets() -> list[tuple[str, tuple[str, ...], frozenset[str]]]:
    """``(classe, sacola, esgotados)`` — o gerador determinístico das sacolas."""
    by_kind: dict[str, list[str]] = {}
    for sku, *_ in CATALOG:
        by_kind.setdefault(TRUTH[sku], []).append(sku)
    foods = [s for s, *_ in CATALOG if TRUTH[s] in FOODS]
    drinks = [s for s, *_ in CATALOG if TRUTH[s] in DRINKS]
    none: frozenset[str] = frozenset()

    out: list[tuple[str, tuple[str, ...], frozenset[str]]] = []
    for sku, *_ in CATALOG:
        out.append((f"só {TRUTH[sku]}", (sku,), none))
    for kind in ("salgado", "doce", "pao", "bebida_quente", "bebida_gelada"):
        for a, b in itertools.combinations(by_kind[kind], 2):
            out.append((f"2× {kind}", (a, b), none))
    for f, d in itertools.product(foods, drinks):
        out.append((f"{TRUTH[f]} + {TRUTH[d]}", (f, d), none))
    for s, d in itertools.product(by_kind["salgado"], by_kind["doce"]):
        out.append(("salgado + doce", (s, d), none))
    for s, d, b in itertools.product(by_kind["salgado"][:3], by_kind["doce"][:3], drinks[::3]):
        out.append(("salgado + doce + bebida", (s, d, b), none))
    for p, d, b, x in itertools.product(by_kind["pao"][:2], by_kind["doce"][:2], drinks[::5], ["GL"]):
        out.append(("pão + doce + bebida + geleia", (p, d, b, x), none))
    out.append(("só mercearia", ("GL",), none))
    out.append(("só mercearia", ("GR",), none))

    everything = frozenset(s for s, *_ in CATALOG)
    geladas = frozenset(by_kind["bebida_gelada"])
    quentes = frozenset(by_kind["bebida_quente"])
    all_drinks = geladas | quentes
    for s in by_kind["salgado"]:
        out.append(("limite: sem bebida gelada", (s,), geladas))
        out.append(("limite: sem bebida alguma", (s,), all_drinks))
        out.append(("limite: tudo esgotado", (s,), everything - {s}))
    for d in by_kind["doce"]:
        out.append(("limite: sem bebida quente", (d,), quentes))
    for d in by_kind["bebida_gelada"]:
        out.append(("limite: sem salgado", (d,), frozenset(by_kind["salgado"])))
    out.append(("limite: sacola com tudo", ("CQMA", "MDLN", "SP", "TRADI", "GL"), none))
    return out


def run_all():
    rows = []
    all_skus = {s for s, *_ in CATALOG}
    for label, cart, esgotados in baskets():
        with _unavailable(set(esgotados)):
            found = suggest(COMPLEMENT, cart_skus=set(cart), channel_ref=CHANNEL, limit=1)
        top = found[0] if found else None
        available = all_skus - set(esgotados)
        note, why = grade(cart, top.sku if top else None, available)
        rows.append((label, cart, top, note, why))
    return rows


def report(rows) -> str:
    total = Counter(r[3] for r in rows)
    by_class: dict[str, Counter] = {}
    for label, _cart, _top, note, _why in rows:
        by_class.setdefault(label, Counter())[note] += 1
    lines = [
        f"{len(rows)} sacolas · nota média {sum(r[3] for r in rows) / len(rows):.2f}",
        "| nota | sacolas |", "|---|---|",
        *[f"| {n} | {total.get(n, 0)} |" for n in (3, 2, 1, 0)],
        "", "| classe | n | 3 | 2 | 1 | 0 |", "|---|---|---|---|---|---|",
    ]
    for label, c in by_class.items():
        lines.append(
            f"| {label} | {sum(c.values())} | {c.get(3, 0)} | {c.get(2, 0)} | {c.get(1, 0)} | {c.get(0, 0)} |"
        )
    lines += ["", "Piores casos:"]
    for label, cart, top, note, why in sorted(rows, key=lambda r: r[3])[:25]:
        if note >= 2:
            break
        got = f"{top.sku} {top.reasons}" if top else "—"
        lines.append(f"- [{note}] {label} {'+'.join(cart)} → {got} ({why})")
    return "\n".join(lines)


#: Lacunas de DADO do seed que o motor não tem como adivinhar. Vazia desde
#: 24/09: o Brioche Chocolat (e os outros pães doces de Macios) entraram também
#: em Doces, e o `propose_product_attributes` deixou de chamá-los de neutros.
KNOWN_DATA_GAPS: set[str] = set()


def _write_report(name: str, text: str) -> None:
    print(f"\n## {name}\n" + text)
    target = os.environ.get("SUGGESTION_STRESS_REPORT")
    if target:
        with open(target, "a") as fh:
            fh.write(f"## {name}\n{text}\n\n")


def _touches_a_gap(row) -> bool:
    _label, cart, top, _note, _why = row
    return bool(KNOWN_DATA_GAPS & (set(cart) | ({top.sku} if top else set())))


def test_the_menu_is_graded_like_a_human_would(menu):
    rows = run_all()
    _write_report("cardápio do seed, como está", report(rows))

    bad = [r for r in rows if r[3] == 0 or (r[3] == 1 and not _touches_a_gap(r))]
    assert not bad, "sugestão absurda ou estranha:\n" + "\n".join(
        f"[{n}] {'+'.join(c)} → {t.sku if t else '—'} ({w})" for _, c, t, n, w in bad
    )


# --- os casos canônicos, um por linha --------------------------------------


@pytest.mark.parametrize(
    ("cart", "esgotados", "wanted"),
    [
        # O caso do dono.
        (("CQMA",), (), {"bebida_gelada"}),
        (("CQMA", "CQMO"), (), {"bebida_gelada"}),
        # Doce pede bebida quente; o histórico de madeleine com água não vence.
        (("MDLN",), (), {"bebida_quente"}),
        # Pão pede café, e a Água (a mais vendida) nunca.
        (("TRADI",), (), {"bebida_quente"}),
        (("TRADI", "FORMA"), (), {"bebida_quente"}),
        # Folhado sem sabor derivado ainda pede o café.
        (("CRO",), (), {"bebida_quente"}),
        # Bebida sozinha pede comida: quente → doce/folhado, gelada → salgado.
        (("SP",), (), {"doce", "folhado"}),
        (("CAP",), (), {"doce", "folhado"}),
        (("SDLA",), (), {"salgado"}),
        # Salgado + bebida → doce, "claro!".
        (("CQMA", "SDLA"), (), {"doce"}),
        (("JB", "COAD"), (), {"doce"}),
        # Doce + bebida → o salgado LEVE que completa a mesa (dono, 24/09),
        # e com mais força se a bebida é gelada.
        (("MDLN", "SP"), (), {"salgado"}),
        (("MDLN", "SDLA"), (), {"salgado"}),
        (("BRCH", "CAP"), (), {"salgado"}),
        # O folhado salgado completa o folhado doce: Folhados agrupa pela massa.
        (("PCHOC", "COAD"), (), {"salgado"}),
        # Pão + café → o que se passa no pão, ou o doce.
        (("TRADI", "COAD"), (), {"acompanhamento", "doce"}),
        # Preferência é peso, não filtro: sem gelada, o salgado leva a quente.
        (("CQMA",), ("CE", "FRAP", "AGUA", "SDLA", "CHHIB"), {"bebida_quente"}),
        # Sem bebida alguma, o salgado ainda tem o doce.
        (("CQMA",), ("SP", "COAD", "CAP", "MOCHA", "CHCAM", "CHOQ",
                     "CE", "FRAP", "AGUA", "SDLA", "CHHIB"), {"doce"}),
    ],
)
def test_canonical_baskets(menu, cart, esgotados, wanted):
    with _unavailable(set(esgotados)):
        found = suggest(COMPLEMENT, cart_skus=set(cart), channel_ref=CHANNEL, limit=1)
    assert found, f"{cart}: nada sugerido"
    assert TRUTH[found[0].sku] in wanted, (cart, found[0].sku, found[0].reasons)


def test_drink_never_follows_a_drink(menu):
    for sku, *_ in CATALOG:
        if TRUTH[sku] not in DRINKS:
            continue
        found = suggest(COMPLEMENT, cart_skus={sku}, channel_ref=CHANNEL, limit=5)
        assert not [s.sku for s in found if TRUTH[s.sku] in DRINKS], sku


def test_everything_sold_out_suggests_nothing(menu):
    everything = {s for s, *_ in CATALOG}
    with _unavailable(everything - {"CQMA"}):
        assert suggest(COMPLEMENT, cart_skus={"CQMA"}, channel_ref=CHANNEL, limit=3) == ()

