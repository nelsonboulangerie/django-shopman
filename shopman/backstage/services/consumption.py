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
(``ConsumptionRole.anchors_dine_in``), editável sem deploy.

**Nada é inventado.** Cesta cujos produtos não têm etiqueta sai
``UNCLASSIFIED`` — nunca "levar" por omissão. Quem lê declara a cobertura.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

DINE_IN = "dine_in"
DINE_IN_TAKEAWAY = "dine_in_takeaway"
TAKEAWAY = "takeaway"
DELIVERY = "delivery"
UNCLASSIFIED = "unclassified"

MODE_LABELS: dict[str, str] = {
    DINE_IN: "Consumiu aqui",
    DINE_IN_TAKEAWAY: "Consumiu e levou",
    TAKEAWAY: "Levou",
    DELIVERY: "Entrega",
    UNCLASSIFIED: "(sem etiqueta)",
}

STOCK_QUANTITY_CUT = Decimal("4")
"""A partir de quantas unidades do MESMO item de levar a compra é de estoque.

Uma dúzia de pães é despensa, não café da manhã na casa. O corte veio do estudo
original e vale só para itens de levar — quatro cafés são uma mesa de quatro, e
tratá-los como estoque leria o movimento de sábado ao contrário.
"""


@dataclass(frozen=True)
class RoleFlags:
    anchors_dine_in: bool
    travels: bool


def role_flags() -> dict[str, RoleFlags]:
    """SKU → papel, a partir do catálogo etiquetado. Uma consulta por leitura."""
    from shopman.backstage.models import ProductConsumptionTag

    rows = ProductConsumptionTag.objects.filter(role__is_active=True).values_list(
        "sku", "role__anchors_dine_in", "role__travels"
    )
    return {sku: RoleFlags(anchors, travels) for sku, anchors, travels in rows}


def classify_basket(lines, flags: dict[str, RoleFlags], *, is_delivery: bool = False) -> str:
    """Modo de consumo de UMA venda, a partir das suas linhas.

    ``lines`` é um iterável de ``(sku, qty)``. A ordem de decisão importa e está
    aqui, explícita, porque cada degrau já foi uma pergunta:

    1. **Entrega precede tudo.** Quem recebe em casa não sentou, qualquer que
       seja a cesta.
    2. **Sem nenhum produto etiquetado, não há veredito.** A venda sai não
       classificada em vez de cair no balde mais provável.
    3. **A âncora vence o corte de estoque.** Quatro cafés são uma mesa cheia,
       não uma despensa — por isso o corte só olha item de levar.
    4. **Âncora + item de levar = consumiu e levou.** É o terceiro estado que o
       dono pediu, e ele não precisa de botão: está na composição da cesta.
    """
    if is_delivery:
        return DELIVERY

    known = False
    anchored = False
    travelling = False
    stock_purchase = False

    for sku, qty in lines:
        role = flags.get(sku or "")
        if role is None:
            continue
        known = True
        if role.anchors_dine_in:
            anchored = True
        if role.travels:
            travelling = True
            if Decimal(str(qty or 0)) >= STOCK_QUANTITY_CUT:
                stock_purchase = True

    if not known:
        return UNCLASSIFIED
    if anchored:
        return DINE_IN_TAKEAWAY if travelling else DINE_IN
    if stock_purchase or travelling:
        return TAKEAWAY
    # Etiquetado, sem âncora e sem item de levar: doce ou fino sozinho. O estudo
    # descartou a leitura permissiva (doce sozinho = local) por inflar o salão.
    return TAKEAWAY


def mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)
