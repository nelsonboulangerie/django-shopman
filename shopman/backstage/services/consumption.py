"""A regra que lê o modo de consumo na cesta (BI-QUESTION-CATALOG §3.1/F3).

Uma implementação, dois consumidores: a mesma função classifica a venda nativa
(``OrderItem``) e a venda histórica (``HistoricalSaleItem``). Duas cópias
divergiriam no primeiro caso de borda, e aí a série de dois anos deixaria de ser
comparável consigo mesma — que é justamente o valor de inferir em vez de
capturar.

**A âncora é a bebida.** O estudo que definiu a regra observou que, nesta casa,
quem pede bebida pra levar é quantidade desprezível — então bebida na cesta
significa alguém que sentou. Prato quente e lanche montado ancoram pelo mesmo
motivo. O que ancora não está escrito aqui: está no catálogo
(``ConsumptionRole.reading``), editável sem deploy.

**Nada é inventado.** Cesta cujos produtos não têm etiqueta sai
``UNCLASSIFIED`` — nunca "levar" por omissão. Quem lê declara a cobertura.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

DINE_IN = "dine_in"
DINE_IN_TAKEAWAY = "dine_in_takeaway"
TAKEAWAY = "takeaway"
DELIVERY = "delivery"
UNCLASSIFIED = "unclassified"

# As três leituras que um produto pode ter (espelham models.Reading).
ANCHOR = "anchor"
TAKEAWAY_ITEM = "takeaway"
HYBRID = "hybrid"

MODE_LABELS: dict[str, str] = {
    DINE_IN: "Consumiu aqui",
    DINE_IN_TAKEAWAY: "Consumiu e levou",
    TAKEAWAY: "Levou",
    DELIVERY: "Entrega",
    UNCLASSIFIED: "(sem etiqueta)",
}

# ── As três leituras da classe ambígua (BI-CONSUMPTION-PROFILES §2.1) ────────
#
# O híbrido (croissant, doce, pão japonês) serve aos dois usos e, sozinho, não
# decide. Isso admite três leituras plausíveis do MESMO dado — e a diferença
# entre elas é uma medida, não um debate. Nenhuma reimplementa a regra: cada
# uma remapeia a leitura dos SKUs e chama a mesma `classify_basket`.
#
#   floor    — híbrido lido como "leva":     piso do consumo local (A no máximo)
#   current  — híbrido transparente:          a regra vigente do F3 (o que o
#              explorador mostra)
#   ceiling  — híbrido lido como "consome":   teto do consumo local (C no máximo)
READING_FLOOR = "floor"
READING_CURRENT = "current"
READING_CEILING = "ceiling"
READING_VARIANTS: tuple[str, ...] = (READING_FLOOR, READING_CURRENT, READING_CEILING)
READING_VARIANT_LABELS: dict[str, str] = {
    READING_FLOOR: "Piso (ambíguo = leva)",
    READING_CURRENT: "Vigente (ambíguo não decide)",
    READING_CEILING: "Teto (ambíguo = consome aqui)",
}


def remap_reading(reading: str | None, variant: str) -> str | None:
    """A leitura de UMA linha sob uma variante. Só o híbrido muda."""
    if reading != HYBRID:
        return reading
    if variant == READING_FLOOR:
        return TAKEAWAY_ITEM
    if variant == READING_CEILING:
        return ANCHOR
    return reading


def remap_readings(readings: dict[str, str], variant: str) -> dict[str, str]:
    """O mapa SKU → leitura inteiro, sob uma variante."""
    if variant == READING_CURRENT:
        return readings
    return {sku: remap_reading(reading, variant) for sku, reading in readings.items()}


# ── Bebida (espelha models.Beverage) ─────────────────────────────────────────
BEVERAGE_NONE = ""
BEVERAGE_PREPARED = "prepared"
BEVERAGE_READY = "ready"

# Palavra na categoria do histórico → tipo de bebida, para as 15 mil linhas
# sem SKU (Coca-Cola, chás gelados, cafés). Mesma ordem de prioridade da
# leitura: específico antes do genérico.
CATEGORY_BEVERAGE: tuple[tuple[str, str], ...] = (
    ("café", BEVERAGE_PREPARED),
    ("cafe", BEVERAGE_PREPARED),
    ("chai", BEVERAGE_PREPARED),
    ("bebida", BEVERAGE_READY),
    ("suco", BEVERAGE_READY),
    ("refri", BEVERAGE_READY),
)

# ── Chave da etiqueta ────────────────────────────────────────────────────────
#
# A etiqueta é chaveada por SKU. Linha do histórico SEM sku (os combos do
# Yooga: 9 mil linhas, 5,5 mil vendas) se etiqueta pelo NOME, com este prefixo
# — a mesma chave que o explorador e o ranking de produtos já usam para essas
# linhas (`sku or f"nome:{name}"`).
NAME_KEY = "nome:"


def line_key(sku: str, name: str) -> str:
    """A chave pela qual uma linha procura sua etiqueta."""
    if sku:
        return sku
    return f"{NAME_KEY}{name}" if name else ""


CATEGORY_READING: tuple[tuple[str, str], ...] = (
    # ⚠️ A ORDEM MANDA: a primeira palavra que casar vence. Por isso o
    # específico vem antes do genérico — "pães finos" antes de "pão", senão
    # 38.369 linhas de viennoiserie cairiam em "leva".
    #
    # As categorias abaixo são as do export real do Yooga, medidas em 18/08
    # (linhas afetadas entre parênteses), e as leituras são decisão do dono.
    ("pães finos", "hybrid"),          # 38.369 — viennoiserie serve aos dois usos
    ("paes finos", "hybrid"),
    ("sanduíche", "anchor"),           # 907 — tartine é prato montado, come aqui
    ("sanduiche", "anchor"),
    ("tartine", "anchor"),
    ("sobremesa", "anchor"),           # 108 — decisão do dono: consumo local
    ("pães rústicos", "takeaway"),     # 15.299
    ("paes rusticos", "takeaway"),
    ("café", "anchor"),                # 5.211
    ("cafe", "anchor"),
    ("bebida", "anchor"),
    ("suco", "anchor"),
    ("refri", "anchor"),
    ("mercearia", "takeaway"),
    ("chai", "anchor"),                # 290 — "Festival Chai" é bebida (dono, 18/08).
                                       # Vem DEPOIS de mercearia: a lata de chai
                                       # da prateleira é compra, não consumo.
    ("doce", "hybrid"),
    ("salgado", "hybrid"),
    ("confeitaria", "hybrid"),
    ("lanche", "anchor"),              # lanche montado come aqui, como a tartine
    # Genéricos por último: só pegam o que os específicos não pegaram.
    ("pão", "takeaway"),
    ("pao", "takeaway"),
    ("padaria", "takeaway"),
)


def reading_for(
    sku: str, category: str, sku_readings: dict[str, str], *, name: str = ""
) -> str | None:
    """A leitura de UMA linha: etiqueta do SKU primeiro, categoria como reserva.

    ⚠️ A reserva não é luxo: **27.177 linhas do histórico não têm SKU** — 11.688
    delas são bebidas (Coca-Cola 350ml, chás gelados) e 3.670 são cafés. Sem a
    reserva, essas linhas ficam invisíveis para a regra, e as vendas em que elas
    aparecem deixam de ser consumo local. Medido sobre os dois anos: 19,2% → 23,5%
    de "consumiu aqui", e o não classificado cai de 7,3% para 6,1%.

    A etiqueta vence sempre que existe: ela é curadoria, a categoria é o rótulo
    do sistema antigo. Linha sem SKU procura a etiqueta pelo nome
    (``nome:<produto>``) antes de cair na categoria — é assim que os combos do
    Yooga, sem SKU e sem categoria, deixam de ser invisíveis.
    """
    etiqueta = sku_readings.get(line_key(sku or "", name or ""))
    if etiqueta is not None:
        return etiqueta
    return _category_match(category, CATEGORY_READING)


def beverage_for(
    sku: str, category: str, sku_beverages: dict[str, str], *, name: str = ""
) -> str:
    """Se a linha é bebida, e de que tipo — etiqueta primeiro, categoria depois.

    Devolve ``""`` (não é bebida) quando nada diz o contrário. Bebida é fato
    da linha, não da cesta: entra na conta do strike rate e das bebidas por
    pedido, e não muda o modo de consumo (esse é da leitura).

    ⚠️ Papel SEM tipo de bebida não veta a categoria. ``""`` é o default de
    todo papel ("consome aqui", "leva", "híbrido"), então significa "o papel
    não fala de bebida", não "não é bebida" — e no staging os cafés do Yooga
    (SS, PS, SL…) estão etiquetados como "consome aqui" por proposta
    automática. Se a etiqueta calasse a categoria, 34 mil linhas de café
    sumiriam do strike rate. O papel que declara bebida (preparada/pronta)
    vence sempre; o que não declara deixa a categoria falar.
    """
    etiqueta = sku_beverages.get(line_key(sku or "", name or ""))
    if etiqueta:
        return etiqueta
    return _category_match(category, CATEGORY_BEVERAGE) or BEVERAGE_NONE


def _category_match(category: str, table: tuple[tuple[str, str], ...]) -> str | None:
    lowered = (category or "").lower()
    for needle, value in table:
        if needle in lowered:
            return value
    return None


class TagFacts(NamedTuple):
    reading: str
    beverage: str


def sku_facts() -> dict[str, TagFacts]:
    """Chave (SKU ou ``nome:``) → (leitura, bebida). Uma consulta por relatório."""
    from shopman.backstage.models import ProductConsumptionTag

    return {
        sku: TagFacts(reading, beverage or BEVERAGE_NONE)
        for sku, reading, beverage in ProductConsumptionTag.objects.filter(
            role__is_active=True
        ).values_list("sku", "role__reading", "role__beverage")
    }


def sku_readings() -> dict[str, str]:
    """SKU → leitura, a partir do catálogo etiquetado. Uma consulta por leitura."""
    return {sku: facts.reading for sku, facts in sku_facts().items()}


def sku_beverages() -> dict[str, str]:
    """SKU → tipo de bebida (``""`` quando não é)."""
    return {sku: facts.beverage for sku, facts in sku_facts().items()}


def classify_basket(lines, readings: dict[str, str], *, is_delivery: bool = False) -> str:
    """Modo de consumo de UMA venda, a partir das suas linhas.

    ``lines`` é um iterável de ``(sku, qty)``. A regra inteira lê **duas coisas**
    na cesta: tem âncora? tem item de levar? Cada degrau abaixo já foi uma
    pergunta:

    1. **Entrega precede tudo.** Quem recebe em casa não sentou, qualquer que
       seja a cesta.
    2. **Sem nenhum produto etiquetado, não há veredito.** A venda sai não
       classificada em vez de cair no balde mais provável.
    3. **Âncora + item de levar = consumiu e levou.** É o único trabalho que a
       leitura "leva" faz — e é o que separa *café + pão* (levou pão) de
       *café + croissant* (comeu junto). Sem ela, o quarto modo não existe.

    ⚠️ **A quantidade não entra.** Houve um corte de "compra de estoque" (4+ do
    mesmo item) que não mudava veredito nenhum: com estes quatro modos, cesta sem
    âncora já é "levou", com uma unidade ou com uma dúzia. Ele volta no dia em
    que existir um modo "compra de estoque" para ele decidir.
    """
    if is_delivery:
        return DELIVERY

    known = False
    anchored = False
    travelling = False

    for sku, _qty in lines:
        reading = readings.get(sku or "")
        if reading is None:
            continue
        known = True
        if reading == ANCHOR:
            anchored = True
        elif reading == TAKEAWAY_ITEM:
            travelling = True

    if not known:
        return UNCLASSIFIED
    if anchored:
        return DINE_IN_TAKEAWAY if travelling else DINE_IN
    # Etiquetado e sem âncora: levou. Vale para pão, para varejo e para o doce
    # sozinho — o estudo descartou a leitura permissiva (doce sozinho = local)
    # por inflar o salão.
    return TAKEAWAY


def mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


# ── A cesta como fato coletado (um dono, vários leitores) ────────────────────
#
# O explorador, o salão e o relatório de perfis precisam da MESMA cesta: as
# linhas de cada venda com leitura e bebida já resolvidas, nas duas fontes,
# com a mesma regra de exclusão (cancelado/devolvido fora) e o mesmo rótulo de
# entrega. Coletar aqui uma vez evita que três varreduras divirjam no primeiro
# caso de borda.

# Prefixo das chaves sintéticas: a leitura já vem resolvida na linha, então a
# "chave de SKU" só precisa carregá-la até `classify_basket`. É o que permite
# que a mesma função decida sobre nativo e histórico — e sob qualquer variante.
RESOLVED_KEY = "leitura:"
_RESOLVED: dict[str, str] = {f"{RESOLVED_KEY}{r}": r for r in (ANCHOR, TAKEAWAY_ITEM, HYBRID)}
_RESOLVED_BY_VARIANT: dict[str, dict[str, str]] = {
    variant: remap_readings(_RESOLVED, variant) for variant in READING_VARIANTS
}


@dataclass(frozen=True, slots=True)
class BasketLine:
    key: str  # sku, ou "nome:<produto>" quando a linha não tem sku
    sku: str
    name: str
    category: str
    reading: str | None  # None = sem etiqueta e sem categoria conhecida
    beverage: str  # BEVERAGE_NONE | BEVERAGE_PREPARED | BEVERAGE_READY
    qty: Decimal
    line_total_q: int


@dataclass(frozen=True, slots=True)
class Basket:
    source: str  # "shopman" | fonte do histórico ("yooga", "seed"…)
    sale_id: int
    local: datetime  # instante LOCAL da venda
    total_q: int
    is_delivery: bool
    channel: str
    lines: tuple[BasketLine, ...]

    def mode(self, variant: str = READING_CURRENT) -> str:
        """O modo de consumo desta cesta sob uma leitura — sempre pela mesma regra."""
        return classify_basket(
            ((f"{RESOLVED_KEY}{line.reading}", line.qty) for line in self.lines if line.reading),
            _RESOLVED_BY_VARIANT[variant],
            is_delivery=self.is_delivery,
        )


def collect_baskets(window) -> tuple[list[Basket], list[Basket]]:
    """(cestas nativas, cestas históricas) da janela — sem fusão.

    Quem lê decide como fundir (``fuse_baskets``: o dia nativo vence). Pedido
    nativo cancelado/devolvido não entra; pedido sem linha entra com cesta
    vazia (e sai "sem etiqueta", que é o que ele é).
    """
    from django.utils import timezone
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem

    facts = sku_facts()
    readings = {key: f.reading for key, f in facts.items()}
    beverages = {key: f.beverage for key, f in facts.items()}

    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)
    native_lines: dict[int, list[BasketLine]] = defaultdict(list)
    native_items = OrderItem.objects.filter(order__created_at__range=window).exclude(
        order__status__in=excluded
    ).values_list("order_id", "sku", "name", "qty", "line_total_q")
    categories = _native_categories({sku for _o, sku, *_r in native_items if sku})
    for order_id, sku, name, qty, line_total_q in native_items:
        category = categories.get(sku, "")
        native_lines[order_id].append(BasketLine(
            key=line_key(sku, name), sku=sku or "", name=name or "", category=category,
            reading=reading_for(sku, category, readings, name=name),
            beverage=beverage_for(sku, category, beverages, name=name),
            qty=qty, line_total_q=line_total_q,
        ))
    native = []
    for order_id, created_at, total_q, channel_ref, data in Order.objects.filter(
        created_at__range=window
    ).exclude(status__in=excluded).values_list("id", "created_at", "total_q", "channel_ref", "data"):
        native.append(Basket(
            source="shopman", sale_id=order_id, local=timezone.localtime(created_at),
            total_q=total_q, channel=channel_ref,
            is_delivery=(data or {}).get("fulfillment_type") == "delivery",
            lines=tuple(native_lines.get(order_id, ())),
        ))

    historical_lines: dict[int, list[BasketLine]] = defaultdict(list)
    for sale_id, sku, name, category, qty, line_total_q in HistoricalSaleItem.objects.filter(
        sale__occurred_at__range=window
    ).values_list("sale_id", "sku", "product_name", "category", "qty", "line_total_q"):
        historical_lines[sale_id].append(BasketLine(
            key=line_key(sku, name), sku=sku or "", name=name or "", category=category or "",
            reading=reading_for(sku, category, readings, name=name),
            beverage=beverage_for(sku, category, beverages, name=name),
            qty=qty, line_total_q=line_total_q,
        ))
    historical = []
    # `is_delivery` é o único rótulo de canal confiável do histórico — mesa e
    # balcão de lá nunca viram verdade (ver docstring de HistoricalSale).
    for sale_id, occurred_at, total_q, is_delivery, source in HistoricalSale.objects.filter(
        occurred_at__range=window
    ).values_list("id", "occurred_at", "total_q", "is_delivery", "source"):
        historical.append(Basket(
            source=source, sale_id=sale_id, local=timezone.localtime(occurred_at),
            total_q=total_q, is_delivery=is_delivery,
            channel=f"{source} · {'delivery' if is_delivery else 'loja'}",
            lines=tuple(historical_lines.get(sale_id, ())),
        ))
    return native, historical


def fuse_baskets(native: Iterable[Basket], historical: Iterable[Basket]) -> list[Basket]:
    """A política de fusão do B.I.: **o dia nativo vence**.

    Um dia com pedido Shopman lê só do Shopman; o histórico preenche os dias em
    que a suite não existia. É a mesma regra do `bi_sales` — e o teste de
    conciliação dos perfis cobra que os dois somem o mesmo faturamento.
    """
    native = list(native)
    native_days = {basket.local.date() for basket in native}
    return native + [b for b in historical if b.local.date() not in native_days]


def _native_categories(skus: set[str]) -> dict[str, str]:
    """SKU nativo → nome da coleção (a "categoria" do catálogo de hoje).

    O histórico traz categoria na linha; o pedido nativo não. A coleção do
    catálogo é o equivalente — e quando um produto vive em várias, a de menor
    ordem responde. Produto fora de coleção fica sem categoria, declarado.
    """
    if not skus:
        return {}
    from shopman.offerman.models import CollectionItem

    rows = CollectionItem.objects.filter(product__sku__in=skus).values_list(
        "product__sku", "collection__name", "collection__sort_order"
    ).order_by("collection__sort_order", "collection__name")
    categories: dict[str, str] = {}
    for sku, name, _order in rows:
        categories.setdefault(sku, name)
    return categories
