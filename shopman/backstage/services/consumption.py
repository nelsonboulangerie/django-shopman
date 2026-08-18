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


def reading_for(sku: str, category: str, sku_readings: dict[str, str]) -> str | None:
    """A leitura de UMA linha: etiqueta do SKU primeiro, categoria como reserva.

    ⚠️ A reserva não é luxo: **27.177 linhas do histórico não têm SKU** — 11.688
    delas são bebidas (Coca-Cola 350ml, chás gelados) e 3.670 são cafés. Sem a
    reserva, essas linhas ficam invisíveis para a regra, e as vendas em que elas
    aparecem deixam de ser consumo local. Medido sobre os dois anos: 19,2% → 23,5%
    de "consumiu aqui", e o não classificado cai de 7,3% para 6,1%.

    A etiqueta do SKU vence sempre que existe: ela é curadoria, a categoria é o
    rótulo do sistema antigo.
    """
    etiqueta = sku_readings.get(sku or "")
    if etiqueta is not None:
        return etiqueta
    lowered = (category or "").lower()
    for needle, reading in CATEGORY_READING:
        if needle in lowered:
            return reading
    return None


def sku_readings() -> dict[str, str]:
    """SKU → leitura, a partir do catálogo etiquetado. Uma consulta por leitura."""
    from shopman.backstage.models import ProductConsumptionTag

    return dict(
        ProductConsumptionTag.objects.filter(role__is_active=True).values_list(
            "sku", "role__reading"
        )
    )


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
