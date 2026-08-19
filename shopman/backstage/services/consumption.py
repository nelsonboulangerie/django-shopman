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

# ── Peso de consumo local (BI-CONSUMPTION-PROFILES §8, passo 1) ──────────────
#
# A vocação é 0 ou 1 e a classe ambígua explode a faixa piso–teto. O peso é a
# mesma vocação em graus: P(consumido aqui | o produto está na cesta), de 0 a
# 100. Mora no PAPEL (default por leitura, editável) e pode ser sobrescrito por
# SKU. Estes são só a reserva para linha que não tem etiqueta nem papel — a
# categoria do histórico dá a leitura, e a leitura dá um peso de partida.
DEFAULT_WEIGHT_BY_READING: dict[str, int] = {
    ANCHOR: 95,
    TAKEAWAY_ITEM: 5,
    HYBRID: 50,
}


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


def category_readings() -> tuple[tuple[str, str], ...]:
    """(trecho, leitura) confirmados, na ordem em que casam. Uma consulta por leitura.

    Vive em ``CategoryAlias``, editável no Admin com quem confirmou — mapeamento
    é dado, não código. Só linhas **confirmadas** com leitura entram: uma
    sugestão que ninguém viu não muda número nenhum. As regras padrão desta
    loja moram no seed / ``setup_bi_reference``. Quem classifica em laço carrega
    uma vez e passa adiante (``category_rules=``); sem passar, carrega aqui.
    """
    from shopman.backstage.models import CategoryAlias

    return tuple(
        CategoryAlias.objects.confirmed()
        .exclude(reading="")
        .order_by("position", "id")
        .values_list("pattern", "reading")
    )


def reading_for(
    sku: str,
    category: str,
    sku_readings: dict[str, str],
    *,
    name: str = "",
    category_rules: tuple[tuple[str, str], ...] | None = None,
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
    rules = category_rules if category_rules is not None else category_readings()
    return _category_match(category, rules)


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


def weight_for(
    sku: str,
    category: str,
    sku_weights: dict[str, int],
    *,
    name: str = "",
    category_rules: tuple[tuple[str, str], ...] | None = None,
) -> int | None:
    """O peso (0–100) de UMA linha: etiqueta/papel primeiro, categoria como reserva.

    ``None`` = linha sem etiqueta e sem categoria conhecida — não entra na
    estimativa, e a cobertura declara quantas ficaram de fora.
    """
    weight = sku_weights.get(line_key(sku or "", name or ""))
    if weight is not None:
        return weight
    rules = category_rules if category_rules is not None else category_readings()
    reading = _category_match(category, rules)
    return DEFAULT_WEIGHT_BY_READING.get(reading) if reading else None


class TagFacts(NamedTuple):
    reading: str
    beverage: str
    weight: int  # peso de consumo local já resolvido: o do SKU, senão o do papel


def sku_facts() -> dict[str, TagFacts]:
    """Chave (SKU ou ``nome:``) → (leitura, bebida, peso). Uma consulta por relatório."""
    from shopman.backstage.models import ProductConsumptionTag

    return {
        sku: TagFacts(
            reading, beverage or BEVERAGE_NONE,
            sku_weight if sku_weight is not None else role_weight,
        )
        for sku, reading, beverage, sku_weight, role_weight in ProductConsumptionTag.objects.filter(
            role__is_active=True
        ).values_list(
            "sku", "role__reading", "role__beverage", "eat_in_weight", "role__eat_in_weight"
        )
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
    weight: int | None = None  # peso de consumo local (0–100); None = sem dado


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

    def eat_in_probability(self) -> float | None:
        """P(alguém sentou) desta cesta, pelos pesos — a leitura em graus.

        **O item mais "de comer aqui" decide**: a probabilidade é o MAIOR peso da
        cesta, não o produto dos pesos. Multiplicar suporia independência entre
        os itens de uma mesma pessoa — e "café + croissant" viraria quase certeza
        por contagem, não por evidência. Com o máximo, café (95) + croissant (50)
        dá 95: o café já disse que alguém sentou; o croissant não muda isso.

        Entrega é 0 por definição. Cesta sem nenhuma linha com peso devolve
        ``None`` — fica fora da estimativa, e a cobertura declara.
        """
        if self.is_delivery:
            return 0.0
        weights = [line.weight for line in self.lines if line.weight is not None]
        if not weights:
            return None
        return max(weights) / 100


def baskets_for(sales_window) -> list[Basket]:
    """As cestas de uma janela canônica já conciliada (``bi/canonical.read_sales``).

    Uma leitura das linhas canônicas, a MESMA resolução de etiqueta para todas:
    o de-para confirmado traduz o SKU da fonte para o do catálogo, e a etiqueta
    é procurada primeiro por ele, depois pelo SKU como a fonte escreveu (o
    ``propose_consumption_tags --include-historical`` grava assim), depois pelo
    nome (``nome:``) e só então pela categoria — crua no histórico, coleção do
    catálogo no nativo. Pedido sem linha entra com cesta vazia (e sai "sem
    etiqueta", que é o que ele é).
    """
    facts = sku_facts()
    readings = {key: f.reading for key, f in facts.items()}
    beverages = {key: f.beverage for key, f in facts.items()}
    weights = {key: f.weight for key, f in facts.items()}
    rules = category_readings()  # uma consulta, milhares de linhas

    lines = sales_window.lines()
    native_skus = {line.product_ref for line in lines if line.source == "shopman" and line.product_ref}
    native_categories = _native_categories(native_skus)

    def pick(table: dict, line) -> str | int | None:
        # Catálogo (via de-para) antes do SKU da fonte; o nome só quando não há SKU.
        for key in (line.product_ref, line.external_sku):
            if key and key in table:
                return table[key]
        if not line.product_ref and not line.external_sku:
            return table.get(line_key("", line.name))
        return None

    by_sale: dict[tuple[str, int], list[BasketLine]] = defaultdict(list)
    for line in lines:
        category = line.category or (native_categories.get(line.product_ref, "") if line.source == "shopman" else "")
        reading = pick(readings, line)
        if reading is None:
            reading = _category_match(category, rules)
        beverage = pick(beverages, line) or _category_match(category, CATEGORY_BEVERAGE) or BEVERAGE_NONE
        weight = pick(weights, line)
        if weight is None:
            weight = DEFAULT_WEIGHT_BY_READING.get(reading) if reading else None
        by_sale[(line.source, line.sale_key)].append(BasketLine(
            key=line.product_key, sku=line.product_ref or line.external_sku, name=line.name,
            category=category, reading=reading, beverage=beverage,
            qty=line.qty, line_total_q=line.line_total_q, weight=weight,
        ))
    return [
        Basket(
            source=sale.source, sale_id=sale.key, local=sale.occurred_at, total_q=sale.total_q,
            is_delivery=sale.is_delivery, channel=sale.channel_key,
            lines=tuple(by_sale.get((sale.source, sale.key), ())),
        )
        for sale in sales_window.sales
    ]


def collect_baskets(window) -> tuple[list[Basket], list[Basket]]:
    """(cestas nativas, cestas históricas) da janela [início, fim) em hora local.

    Lê a camada canônica, que já aplicou "o dia nativo vence": o histórico
    devolvido aqui é só o dos dias sem pedido Shopman. Quem chama pode juntar
    as duas listas com ``fuse_baskets`` sem medo de somar a mesma venda duas
    vezes.
    """
    from datetime import timedelta

    from django.utils import timezone

    from shopman.backstage.bi.canonical import read_sales

    start, end = window
    date_from = timezone.localtime(start).date()
    date_to = (timezone.localtime(end) - timedelta(seconds=1)).date()
    baskets = baskets_for(read_sales(date_from, date_to))
    native = [basket for basket in baskets if basket.source == "shopman"]
    historical = [basket for basket in baskets if basket.source != "shopman"]
    return native, historical


def fuse_baskets(native: Iterable[Basket], historical: Iterable[Basket]) -> list[Basket]:
    """Junta as duas listas de ``collect_baskets``.

    A política de fusão do B.I. — **o dia nativo vence** — tem um dono só, a
    camada canônica (``bi/canonical.py``), e já foi aplicada quando as cestas
    chegaram aqui; por isso juntar é seguro. A função fica porque é a frase que
    os leitores dizem ("funde"), e o teste de conciliação dos perfis cobra que
    esta leitura e o ``bi_sales`` somem o mesmo faturamento.
    """
    return list(native) + list(historical)


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


# ── A dica para quem etiqueta: o que o histórico sabe sobre um SKU ───────────


class SkuSignal(NamedTuple):
    sales: int  # vendas de balcão com o SKU
    with_beverage_pct: int  # % delas com alguma bebida na cesta
    alone_pct: int  # % em que o SKU era o único produto
    bulk_pct: int  # % com 4+ unidades do SKU (compra de lote)


def sku_signal(key: str) -> SkuSignal | None:
    """O sinal que o histórico dá sobre um SKU (ou ``nome:<produto>``).

    Não classifica ninguém — é a dica ao lado do campo de peso, para o gestor
    não decidir no escuro: um produto que em 97% das vendas sai em 4+ unidades
    e em 17% com bebida é pão de abastecimento, diga o nome o que disser.
    Só balcão (entrega não tem cesta de salão); só histórico (o nativo ainda é
    pequeno demais para dizer algo).
    """
    from django.db.models import Q

    from shopman.backstage.models import HistoricalSaleItem

    if key.startswith(NAME_KEY):
        match = Q(sku="", product_name=key[len(NAME_KEY):])
    else:
        match = Q(sku=key)
    sales_with_sku = HistoricalSaleItem.objects.filter(match, sale__is_delivery=False).values("sale_id")
    rows = HistoricalSaleItem.objects.filter(sale_id__in=sales_with_sku).values_list(
        "sale_id", "sku", "product_name", "category", "qty"
    )
    beverages = {k: f.beverage for k, f in sku_facts().items()}
    sales: set[int] = set()
    with_beverage: set[int] = set()
    units: dict[int, Decimal] = defaultdict(Decimal)
    distinct: dict[int, set[str]] = defaultdict(set)
    for sale_id, sku, name, category, qty in rows:
        sales.add(sale_id)
        line = line_key(sku, name)
        distinct[sale_id].add(line)
        if line == key:
            units[sale_id] += qty
        if beverage_for(sku, category, beverages, name=name):
            with_beverage.add(sale_id)
    if not sales:
        return None
    n = len(sales)
    return SkuSignal(
        sales=n,
        with_beverage_pct=round(100 * len(with_beverage) / n),
        alone_pct=round(100 * sum(1 for s in sales if len(distinct[s]) == 1) / n),
        bulk_pct=round(100 * sum(1 for s in sales if units[s] >= 4) / n),
    )


def beverage_rate() -> int:
    """% das vendas de balcão do histórico com alguma bebida — a média da casa.

    É a base contra a qual um SKU "inclina": co-ocorrência igual à média não
    diz nada sobre o produto, diz sobre a casa.
    """
    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem

    beverages = {k: f.beverage for k, f in sku_facts().items()}
    total = HistoricalSale.objects.filter(is_delivery=False).count()
    if not total:
        return 0
    with_beverage: set[int] = set()
    for sale_id, sku, name, category in HistoricalSaleItem.objects.filter(
        sale__is_delivery=False
    ).values_list("sale_id", "sku", "product_name", "category"):
        if beverage_for(sku, category, beverages, name=name):
            with_beverage.add(sale_id)
    return round(100 * len(with_beverage) / total)
