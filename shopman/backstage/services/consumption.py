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
