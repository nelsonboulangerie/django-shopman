"""Traz a Mercearia real para o catálogo: cria a revenda que a casa vende e troca os placeholders.

Usage::

    python manage.py apply_grocery_catalog            # ensaio: executa e desfaz
    python manage.py apply_grocery_catalog --apply    # grava

**Fonte.** A aba ``Produtos`` da planilha consolidada do dono (22–23/09/2026):
SKU no padrão de revenda ``TIPO-VARIANTE-MARCA-EMBALAGEM``, nome e preço do
Yooga, marca, GTIN, NCM e CEST das NF-e de compra. A tabela mora aqui, no
código, para que o banco novo (o ``seed`` chama :func:`apply_grocery`) e o banco
que já roda (este comando) terminem iguais.

**Entra quem tem dado para vender sem mentir**: nome, marca, embalagem, preço
maior que zero, NCM e GTIN que passa no dígito verificador GS1 (o validador
oficial do catálogo, ``gtin_is_valid``). Quem falta alguma dessas fica em
:data:`LEFT_OUT`, com o motivo — ausência declarada, não esquecimento.

**Como cada item nasce**

- Unidade ``un`` e perfil fiscal **por item**, com o CEST do Anexo XVII do
  Conv. ICMS 142/2018 (ver :data:`FISCAL_NOTES`):
    * ``resale_common`` (102/5102 + CEST) — revenda fora da ST do PR: queijo,
      manteiga, azeite, geleia, picles, presunto, chá em folhas. O CEST vai no
      documento porque o Conv. 142/2018 (cl. 20ª, I; cl. 3ª para o Simples) o
      exige para item listado "ainda que a operação não esteja sujeita ao
      regime de ST";
    * ``resale`` (500/5405 + CEST) — revenda NA ST do PR (RICMS/PR, Anexo IX,
      art. 118): mostarda preparada (17.038.00) e os cremes de queijo como
      "requeijão e similares" (17.023.00). ⚠️ Interpretação: confirmar com o
      contador — se a compra NÃO veio com ST retida, é 102.
  Produto que ainda está no perfil antigo (``own_production`` sem CEST) é
  reclassificado; qualquer outra classificação já curada fica, e sai no
  relatório como divergência.
- Marca e GTIN em ``metadata['social']`` (o que o feed e a página declaram) e
  o **cadastro de compra** do mesmo SKU (``buyman.Material``): é ele que torna
  o item comprável, e é por ele que o Compras recebe a NF-e (ver
  ``shopman/shop/services/sku_records.py``).
- Coleção ``mercearia``.
- **Despublicado** (``is_published=False``) e vendável, como os chás Kãnfa:
  alérgenos, tabela nutricional e ingredientes são dado da embalagem, que
  ninguém digitou ainda. Publicar é passo do gestor, depois da ficha.

**Onde se vende — a regra das listagens**

- **PDV sempre.** O balcão já vende estes itens hoje (é o histórico do Yooga);
  o PDV lê a listagem ``pdv``, não ``Product.is_published``.
- **Loja online, WhatsApp e iFood só com foto.** Sem foto nenhum item entra
  em canal onde o cliente compra de longe: ele decide pela imagem, e produto
  sem retrato na vitrine é produto que parece faltar. Nenhum item desta tabela
  tem foto hoje, então todos nascem só no PDV; quando a foto chegar
  (``image_url``), rodar o comando de novo os lista nos canais remotos. E o
  contrário também vale: item desta tabela sem foto que estiver num canal
  remoto sai dele.

**Vendido a quilo** (``unit="kg"``): o Queijo Vale do Testo chega em peças de
peso diferente. Unidade ``kg``, sem GTIN (a etiqueta da balança é EAN interno
prefixo 2) e preço por quilo **quando alguma fonte o tiver** — hoje nenhuma
tem, e o relatório repete a pergunta a cada execução. A falta de preço não
trava o CADASTRO, mas trava a VENDA: item com preço zero não vende (regra do
dono, 24/09), então ele fica ``is_sellable=False`` — no produto e na listagem —
até o preço por quilo chegar. E item a quilo **nunca** entra em canal remoto,
com ou sem foto: o carrinho online só aceita unidade inteira.

**GTIN da web** (``gtin_source``): quando o código veio de pesquisa (duas
fontes ou mais concordando) e não da NF-e nem da embalagem, o produto guarda
``metadata['gtin_source'] = "web, a confirmar na embalagem"``.

**Caixas presente** (:data:`GIFT_BOXES`): produto da casa, SKU da casa, sem
GTIN nem marca de revenda; entram no lugar da ``LN``. Os placeholders que
saíram (MT, QP, CX, BK, GR, LN, THL) saem pelo ``apply_catalog_decisions``.

**Placeholders da despensa que viram produto real** (:data:`REAL_PLACEHOLDERS`):
Ratatouille, Tapenade e Camembert tinham nome e preço provisórios do Cardápio
2027. O comando só troca quando o valor atual ainda é o placeholder — nome ou
preço que o gestor já mexeu fica, e sai no relatório como divergência.

Idempotente: item que já está como a tabela diz não é tocado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.shop.services.sku_records import ensure_purchase_record, sync_sale_listings

COLLECTION_REF = "mercearia"


@dataclass(frozen=True)
class GroceryItem:
    sku: str
    name: str
    price_q: int
    brand: str
    gtin: str
    ncm: str
    #: CEST da NF-e do fornecedor. NÃO é gravado (ver docstring do módulo).
    cest: str = ""
    #: Peso líquido da embalagem, em gramas. ``None`` quando ela é em volume
    #: ou quando o item é vendido a quilo.
    weight_g: int | None = None
    keywords: tuple[str, ...] = ()
    #: ``un`` = embalagem fechada, com GTIN. ``kg`` = vendido POR PESO: preço
    #: por quilo, sem GTIN de embalagem (a etiqueta da balança é EAN interno
    #: prefixo 2, que não é o GTIN do produto).
    unit: str = "un"
    #: De onde veio o GTIN, quando NÃO foi da NF-e. Vai para
    #: ``metadata['gtin_source']``: quem lê sabe se é conferido ou palpite.
    gtin_source: str = ""
    #: Perfil fiscal: ``resale_common`` (sem ST) ou ``resale`` (na ST do PR).
    profile: str = "resale_common"


#: O GTIN que veio da web: duas fontes ou mais concordando, e ninguém leu a
#: embalagem ainda (lição de 23/09: fontes podem errar juntas).
WEB_UNCONFIRMED = "web, a confirmar na embalagem"
#: O GTIN que o dono leu na embalagem — a fonte que decide.
OWNER_PACKAGE = "embalagem, dono, 24/09"


#: Revenda real da Mercearia. Nome e preço: Yooga (preço mais praticado);
#: GTIN, NCM e CEST: NF-e de compra. Planilha consolidada, 22–23/09/2026.
GROCERY: tuple[GroceryItem, ...] = (
    # ── Azeite ──
    GroceryItem("AZEITE-DEFUMADO-MIRANTE-250", "Azeite Defumado Mirante 250ml", 14300, "Mirante",
                "602883466104", "15092000", "1706700", None, ("azeite", "defumado")),
    GroceryItem("AZEITE-DEFUMADO-PICANTE-MIRANTE-250", "Azeite Defumado Picante Mirante 250ml", 7700,
                "Mirante", "602883466128", "15092000", "1706700", None, ("azeite", "defumado", "picante")),
    # ── Conservas Duga ──
    # NCM corrigido: a nota trazia 2103.90.99 (molhos e condimentos), que não
    # tem CEST; berinjela preparada em óleo é 2005.99.00 → 17.092.00.
    # ⚠️ Anotar para o contador.
    GroceryItem("BERINJELA-DUGA-320", "Berinjela Insalata Duga 320g", 3100, "Duga",
                "7898655520010", "20059900", "1709200", 320, ("berinjela", "conserva", "antepasto")),
    GroceryItem("RELISH-ABOBRINHA-DUGA-320", "Relish de Abobrinha Duga 320g", 3100, "Duga",
                "7898655520065", "20019000", "1709000", 320, ("relish", "abobrinha", "conserva")),
    GroceryItem("RELISH-CEBOLA-DUGA-320", "Relish de Cebola Duga 320g", 3100, "Duga",
                "7898655520034", "20019000", "1709000", 320, ("relish", "cebola", "conserva")),
    GroceryItem("RELISH-PEPINO-DUGA-320", "Relish de Pepino Duga 320g", 3100, "Duga",
                "7898655520041", "20019000", "1709000", 320, ("relish", "pepino", "conserva")),
    # ── Cremes de queijo Pomerode ──
    GroceryItem("CREME-GORGONZOLA-POMERODE-90", "Creme de Gorgonzola Pomerode 90g", 2600, "Pomerode",
                "7898361661236", "04063000", "1702300", 90, ("queijo", "creme", "gorgonzola"), profile="resale"),
    GroceryItem("CREME-PARMESAO-POMERODE-90", "Creme de Parmesão Kraeuterkaese Pomerode 90g", 2600,
                "Pomerode", "7898361661014", "04063000", "1702300", 90, ("queijo", "creme", "parmesao"), profile="resale"),
    # GTIN da web: Empório Varanda, Cosmos (lista do NCM 0406.30.00) e Santa
    # Helena; mesmo prefixo dos irmãos.
    GroceryItem("CREME-BRIE-POMERODE-90", "Creme de Brie Pomerode 90g", 2600, "Pomerode",
                "7898361662103", "04063000", "1702300", 90, ("queijo", "creme", "brie"),
                gtin_source=WEB_UNCONFIRMED, profile="resale"),
    # Vendido POR PESO: a peça chega da Pomerode com peso diferente a cada
    # vez. O preço do quilo é a conta de :data:`VALE_DO_TESTO_PRICE`: custo de
    # 2025 corrigido pelo IPCA do queijo, mais o markup da mercearia.
    GroceryItem("QUEIJO-VALEDOTESTO-POMERODE", "Queijo Vale do Testo Pomerode 3m", 21900, "Pomerode",
                "", "04069020", "1702400", None, ("queijo", "colonial", "pomerode"), unit="kg"),
    # ── Geleias St. Dalfour ──
    # - o 810019371295 do Limão é mesmo St. Dalfour, mas do sabor **Limão &
    #   Lima** ("Citrons & Citrons Verts"; Empório Itiê e Open Food Facts) —
    #   pergunta para quem tem o pote na mão;
    # - as Frutas Vermelhas SÃO a "4 Frutas" ("4 fruits", Four Fruits): o
    #   francês diz quatro frutas, o brasileiro diz frutas vermelhas (dono,
    #   24/09). Um produto só; "4 frutas" entra como palavra de busca.
    GroceryItem("GELEIA-DAMASCO-STDALFOUR-284", "Geleia Damasco St. Dalfour 284g", 4200, "St. Dalfour",
                "084380957543", "20079910", "1709400", 284, ("geleia", "damasco", "fruta")),
    GroceryItem("GELEIA-FIGO-STDALFOUR-284", "Geleia Figo St. Dalfour 284g", 4200, "St. Dalfour",
                "084380959042", "20079910", "1709400", 284, ("geleia", "figo", "fruta")),
    GroceryItem("GELEIA-FRUTASVERM-STDALFOUR-284", "Geleia Frutas Vermelhas St. Dalfour 284g", 4200,
                "St. Dalfour", "084380957840", "20079910", "1709400", 284, ("geleia", "frutas vermelhas", "4 frutas", "fruta")),
    GroceryItem("GELEIA-LARANJA-STDALFOUR-284", "Geleia Laranja St. Dalfour 284g", 4200, "St. Dalfour",
                "084380957949", "20079100", "1709400", 284, ("geleia", "laranja", "fruta")),
    GroceryItem("GELEIA-LIMAO-STDALFOUR-284", "Geleia Limão St. Dalfour 284g", 4200, "St. Dalfour",
                "810019371295", "20079100", "1709400", 284, ("geleia", "limao", "fruta")),
    GroceryItem("GELEIA-MORANGO-STDALFOUR-284", "Geleia Morango St. Dalfour 284g", 4200, "St. Dalfour",
                "084380957444", "20079910", "1709400", 284, ("geleia", "morango", "fruta")),
    # Os dois minis nascem no lugar do `GL` (placeholder de sabor indefinido,
    # que o dono mandou sair em 22/09 — ver `apply_catalog_decisions`). O NCM do
    # de damasco veio da nota como 2007.99.90 e sem CEST; o de frutas
    # vermelhas, como os potes grandes.
    GroceryItem("GELEIA-DAMASCO-STDALFOUR-28", "Mini Geleia Damasco St. Dalfour 28g", 900, "St. Dalfour",
                "084380980428", "20079990", "1709400", 28, ("geleia", "damasco", "fruta", "mini")),
    GroceryItem("GELEIA-FRUTASVERM-STDALFOUR-28", "Mini Geleia Frutas Vermelhas St. Dalfour 28g", 900,
                "St. Dalfour", "084380980626", "20079910", "1709400", 28,
                ("geleia", "frutas vermelhas", "4 frutas", "fruta", "mini")),
    # ── Laticínios ──
    GroceryItem("MANTEIGA-SAL-PRESIDENT-200", "Manteiga Extra com Sal Président 200g", 1500, "Président",
                "3228020355741", "04051000", "1702500", 200, ("manteiga", "com sal")),
    GroceryItem("QUEIJO-BRIE-ILEDEFRANCE-25", "Queijo Mini Brie Ile de France 25g", 1000, "Ile de France",
                "3161712002113", "04069030", "1702400", 25, ("queijo", "brie", "mini")),
    # ── Mostardas Maille ──
    GroceryItem("MOSTARDA-MEL-MAILLE-215", "Mostarda com Mel Maille 215g", 4200, "Maille",
                "3036810204014", "21033021", "1703800", 215, ("mostarda", "mel"), profile="resale"),
    GroceryItem("MOSTARDA-DIJON-MAILLE-215", "Mostarda Dijon Maille 215g", 3500, "Maille",
                "3036810201280", "21033021", "1703800", 215, ("mostarda", "dijon"), profile="resale"),
    # A embalagem (lida pelo dono em 24/09) confirma o 3036810207589 que
    # Auchan PT, Covabra e Open Food Facts davam; o Cosmos (…7558) errava.
    GroceryItem("MOSTARDA-ANCIENNE-MAILLE-210", "Mostarda à l'Ancienne Maille 210g", 4200, "Maille",
                "3036810207589", "21033021", "1703800", 210, ("mostarda", "ancienne", "graos"),
                gtin_source=OWNER_PACKAGE, profile="resale"),
    # ── Mirante ──
    # 120 g e R$ 26 (dono, 24/09). GTIN-12 602883466111 (a embalagem traz
    # 0602883466111), guardado como os outros Mirante.
    GroceryItem("CHURRASQUINHO-PIMENTA-MIRANTE-120", "Churrasquinho de Pimenta Mirante 120g", 2600,
                "Mirante", "602883466111", "21039099", "", 120,
                ("churrasquinho", "pimenta", "conserva"), gtin_source=OWNER_PACKAGE),
    # ── Chá Kãnfa em lata ──
    # A lata de Chalosofia (dono, embalagem, 24/09). ⚠️ Na loja da Kãnfa o
    # 7898708850477 aparece no kit "Lata + Pouch"; a embalagem é quem decide.
    # O peso é o da planilha (50 g) — o dono não o leu na lata. NCM da NF-e da
    # Kãnfa (0902.10.00); as irmãs no catálogo ainda estão em 0902.20.00.
    GroceryItem("CHA-CHALOSOFIA-KANFA-L50", "Chalosofia Kãnfa — Lata 50g", 7300, "Kãnfa",
                "7898708850477", "09021000", "1709700", 50, ("cha", "chalosofia", "lata", "kanfa"),
                gtin_source=OWNER_PACKAGE),
    # A lata de Vital Chai (dono confirmou 7898708850743 e os 70 g, 24/09 — a
    # loja da Kãnfa já a chamava de "Lata 70g"; a planilha dizia 60 g).
    GroceryItem("CHA-VITAL-KANFA-L70", "Vital Chai Kãnfa — Lata 70g", 7300, "Kãnfa",
                "7898708850743", "09021000", "1709700", 70, ("cha", "vital", "chai", "lata", "kanfa"),
                gtin_source=OWNER_PACKAGE),
    # ── Frios ──
    GroceryItem("PRESUNTO-CRU-VITOBAUDUCCI-100", "Presunto Cru Fatiado Vito Bauducci 100g", 3800,
                "Vito Bauducci", "7890203650002", "02101900", "1708701", 100, ("presunto", "cru", "fatiado")),
)

@dataclass(frozen=True)
class SupplierCost:
    """Custo de compra conhecido, com a origem — vira o custo do fornecedor."""

    sku: str
    supplier_ref: str
    supplier_name: str
    cost_q: int  # por unidade-base do cadastro de compra (aqui, o quilo)
    date: str
    source: str


#: O que a casa pagou (dono, 24/09: "em 2025 pagamos ao fornecedor R$ 140,07/kg").
#: A NF Pomerode 145675 é de 05/09/2025 — o mês do custo é set/2025.
SUPPLIER_COSTS: tuple[SupplierCost, ...] = (
    SupplierCost("QUEIJO-VALEDOTESTO-POMERODE", "pomerode", "Pomerode", 14007, "2025-09-05",
                 "dono, 2025 (NF Pomerode 145675)"),
)


@dataclass(frozen=True)
class PriceFromCost:
    """Preço de venda derivado do custo: correção pela inflação + markup."""

    cost_q: int
    #: Variação mensal (%) do índice usado, do mês seguinte ao do custo até o
    #: último publicado. Dado oficial, não estimativa.
    monthly_pct: tuple[tuple[str, str], ...]
    index: str
    markup_pct: int

    @property
    def factor(self):
        from decimal import Decimal

        acc = Decimal(1)
        for _month, pct in self.monthly_pct:
            acc *= Decimal(1) + Decimal(pct) / Decimal(100)
        return acc

    @property
    def corrected_cost_q(self) -> int:
        from decimal import ROUND_HALF_UP, Decimal

        return int((Decimal(self.cost_q) * self.factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def price_q(self) -> int:
        from shopman.shop.resale_markup import suggested_price_q

        return suggested_price_q(self.corrected_cost_q, self.markup_pct)


#: O preço do quilo do Vale do Testo (dono, 24/09: "corrija inflação + alguma
#: correção apropriada + markup"). Custo de set/2025 corrigido pelo **IPCA do
#: subitem Queijo** (IBGE, SIDRA tabela 7060, variável 63, subitem 1111011),
#: de out/2025 a ago/2026 — o último mês publicado em 24/09/2026. O custo é de
#: 05/09/2025: a variação de setembro já estava no preço pago, então a
#: correção começa em outubro. Acumulado: +3,86% (o IPCA geral, série SGS 433
#: do BCB, dá +3,73% no mesmo período → R$ 218/kg; o do queijo é o índice do
#: próprio produto). R$ 140,07 × 1,038584 = R$ 145,47; × 1,5 (markup padrão
#: da mercearia, ``resale_markup``) = R$ 218,21 → R$ 219,00 (para cima, real
#: inteiro, a regra do ``suggested_price_q``).
VALE_DO_TESTO_PRICE = PriceFromCost(
    cost_q=14007,
    monthly_pct=(
        ("2025-10", "-0.50"), ("2025-11", "-0.55"), ("2025-12", "1.00"), ("2026-01", "-0.63"),
        ("2026-02", "0.68"), ("2026-03", "-0.28"), ("2026-04", "1.13"), ("2026-05", "1.56"),
        ("2026-06", "0.53"), ("2026-07", "0.40"), ("2026-08", "0.48"),
    ),
    index="IPCA subitem 1111011.Queijo (IBGE SIDRA 7060)",
    markup_pct=50,
)


#: O porquê de cada classificação fiscal, com fonte — para a revisão do dono
#: e do contador. Pesquisa de 24/09/2026.
FISCAL_NOTES: dict[str, str] = {
    "obrigacao": (
        "Conv. ICMS 142/2018, cl. 20ª, I (e cl. 3ª, Simples): informar o CEST do item "
        "listado nos Anexos II a XXVI mesmo sem ST — confaz.fazenda.gov.br/legislacao/"
        "convenios/2018/CV142_18; RICMS/PR, Anexo X, art. 1º, §§ 1º e 5º. A SEFAZ não "
        "rejeita CSOSN 102 sem CEST (a rejeição 806 é só para ST), mas a obrigação existe."
    ),
    "st_no_pr": (
        "RICMS/PR, Anexo IX, art. 118: na ST seguem mostarda preparada 2103.30.21 "
        "(17.038.00), condimentos 2103.90.21/.91 (17.035.00) e requeijão e similares "
        "(17.023.00); saíram em 1º/11/2019 (Decreto 2.673/2019) azeite, geleias/doces "
        "(2007) e picles (2001). Queijos 0406 (17.024.00), manteiga e presunto cru "
        "estão fora."
    ),
    "csosn_500": (
        "Item na ST comprado com ST retida sai com CSOSN 500/CFOP 5405; com 102, o ICMS "
        "entraria de novo no DAS. Interpretação — confirmar com o contador."
    ),
    "creme_de_queijo": (
        "0406.30 (queijo fundido) → 17.023.00 (requeijão e similares, na ST do PR). "
        "Alternativa defensável: 17.024.00 (queijos, fora da ST). Contador decide."
    ),
    "churrasquinho": (
        "2103.90.99 (outros molhos) não está no Anexo XVII: sem CEST. Se o contador "
        "enxergar condimento (2103.90.21/.91), vira 17.035.00 e ST."
    ),
}


@dataclass(frozen=True)
class SeedResaleFiscal:
    """Revenda que o seed já semeia (chás Kãnfa, Camembert): só a classificação."""

    sku: str
    ncm: str
    cest: str
    profile: str = "resale_common"
    #: Peso líquido confirmado pelo dono (latas, 24/09). ``None`` = não mexe.
    weight_g: int | None = None


#: Os chás Kãnfa voltam ao NCM da NF-e (0902.10.00, chá verde em embalagem
#: até 3 kg — a planilha anotou "antes 09022000"); CEST 17.097.00, chá em
#: folhas fora da ST do PR. O Camembert, queijo 17.024.00.
SEED_RESALE_FISCAL: tuple[SeedResaleFiscal, ...] = (
    # Latas: pesos confirmados pelo dono em 24/09 — Namastê, Intuição, Mama
    # Chai e Vital Chai têm 70 g; Aconchego, Chalosofia e Intimidade, 50 g.
    *(SeedResaleFiscal(sku, "09021000", "1709700", weight_g=weight) for sku, weight in (
        ("CHA-ACONCHEGO-KANFA-L50", 50), ("CHA-INTIMIDADE-KANFA-L50", 50),
        ("CHA-INTUICAO-KANFA-L70", 70), ("CHA-MAMA-KANFA-L70", 70), ("CHA-NAMASTE-KANFA-L70", 70),
    )),
    *(SeedResaleFiscal(sku, "09021000", "1709700") for sku in (
        "CHA-ACONCHEGO-KANFA-P50", "CHA-CHALOSOFIA-KANFA-P50", "CHA-INTIMIDADE-KANFA-P50",
        "CHA-INTUICAO-KANFA-P50", "CHA-MAMA-KANFA-P50", "CHA-NAMASTE-KANFA-P50", "CHA-VITAL-KANFA-P50",
    )),
    SeedResaleFiscal("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", "04069020", "1702400"),
)


#: Mercearia da planilha que NÃO entra, e por quê. Entra quando o dado faltante
#: chegar — basta mover a linha para :data:`GROCERY`.
LEFT_OUT: dict[str, str] = {
    "CHA-INTUICAO-KANFA-F250": "é INSUMO (lata de serviço do chá do bule), não produto de prateleira",
}


@dataclass(frozen=True)
class RealPlaceholder:
    """Placeholder do Cardápio 2027 que já tem o produto real do Yooga."""

    sku: str
    placeholder_name: str
    placeholder_price_q: int
    name: str
    price_q: int
    weight_g: int


@dataclass(frozen=True)
class GiftBox:
    """Caixa presente montada na casa: SKU da casa, sem GTIN, marca da loja."""

    sku: str
    name: str
    price_q: int
    ncm: str


#: As quatro caixas presente (planilha consolidada; entram no lugar do `LN`,
#: decisão do dono em 24/09). Composição ainda indefinida: vendável no PDV,
#: sem ficha, despublicada na loja. A marca da casa vem do
#: `apply_product_brands`.
GIFT_BOXES: tuple[GiftBox, ...] = (
    GiftBox("DIJON", "Caixa Presente Dijon", 27000, "19059090"),
    GiftBox("LILLE", "Caixa Presente Lille", 16000, "19059090"),
    GiftBox("MIMO", "Caixa Presente Mimo", 4000, "19059090"),
    GiftBox("NICE", "Caixa Presente Nice", 22000, "19059090"),
)


#: Nome no Yooga (``ProductAlias.external_name``, exato — espaço duplo e
#: grafia de lá inclusos) → SKU. É o que devolve ao produto novo os dois anos
#: de venda que o B.I. já importou: esses de-paras estavam confirmados e sem
#: produto, esperando o catálogo ter para onde apontar.
YOOGA_NAMES: dict[str, str] = {
    "Azeite Defumado Mirante 250ml": "AZEITE-DEFUMADO-MIRANTE-250",
    "Azeite Defumado Picante Mirante 250ml": "AZEITE-DEFUMADO-PICANTE-MIRANTE-250",
    "Berinjela Insalata Duga 320g": "BERINJELA-DUGA-320",
    "Relish de Abobrinha Duga 320g": "RELISH-ABOBRINHA-DUGA-320",
    "Relish de Cebola Duga 320g": "RELISH-CEBOLA-DUGA-320",
    "Relish de Pepino Duga 320g": "RELISH-PEPINO-DUGA-320",
    "Creme de Brie Pomerode 90g": "CREME-BRIE-POMERODE-90",
    "Creme de Gorgonzola Pomerode 90g": "CREME-GORGONZOLA-POMERODE-90",
    "Creme de Parmesão Kraeuterkaese Pomerode 90g": "CREME-PARMESAO-POMERODE-90",
    "Geléia Damasco St.Dalfour 284g": "GELEIA-DAMASCO-STDALFOUR-284",
    "Geléia Figo St.Dalfour 284g": "GELEIA-FIGO-STDALFOUR-284",
    "Geléia Frutas Vermelhas St.Dalfour 284g": "GELEIA-FRUTASVERM-STDALFOUR-284",
    "Geléia Laranja St.Dalfour 284g": "GELEIA-LARANJA-STDALFOUR-284",
    "Geléia Limão St.Dalfour 284g": "GELEIA-LIMAO-STDALFOUR-284",
    "Geléia Morango St.Dalfour 284g": "GELEIA-MORANGO-STDALFOUR-284",
    "Mini Geléia Damasco St.Dalfour 28g": "GELEIA-DAMASCO-STDALFOUR-28",
    "Mini Geléia Frutas Vermelhas St.Dalfour 28g": "GELEIA-FRUTASVERM-STDALFOUR-28",
    "Queijo Mini Brie Ile de France 25g": "QUEIJO-BRIE-ILEDEFRANCE-25",
    "Mostarda Àl' Ancienne Maille 210g -": "MOSTARDA-ANCIENNE-MAILLE-210",
    "Churrasquinho de Pimenta Mirante 120g": "CHURRASQUINHO-PIMENTA-MIRANTE-120",
    "Mostarda Com Mel Maille 215g": "MOSTARDA-MEL-MAILLE-215",
    "Mostarda Dijon Maille 215g": "MOSTARDA-DIJON-MAILLE-215",
    "Mostarda Maille Dijon Originale 215g": "MOSTARDA-DIJON-MAILLE-215",  # nome do iFood
    "Presunto Cru Fatiado Vito Bauducci 100g": "PRESUNTO-CRU-VITOBAUDUCCI-100",
    # Este apontava para o placeholder `QP` (curadoria de 19/08, "nome
    # parecido"); o placeholder sai e a venda volta para o queijo que ela é.
    "Queijo Vale do Testo Pomerode  3m": "QUEIJO-VALEDOTESTO-POMERODE",
    "Caixa Presente Lille": "LILLE",
    "Caixa Presente Nice": "NICE",
}

#: Placeholders que saem pelo `apply_catalog_decisions`: um de-para que aponta
#: para eles pode ser reapontado ao produto real. Qualquer outro alvo é
#: curadoria de alguém, e fica.
LEAVING_PLACEHOLDERS: frozenset[str] = frozenset({"MT", "QP", "CX", "BK", "GR", "LN", "THL"})


REAL_PLACEHOLDERS: tuple[RealPlaceholder, ...] = (
    RealPlaceholder("RTAT", "Patê de Ratatouille", 2400, "Ratatouille 90g", 1800, 90),
    RealPlaceholder("TPND", "Tapenade", 2400, "Tapenade Azeitonas Pretas 100g", 2900, 100),
    RealPlaceholder("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", "Camembert", 3800,
                    "Queijo Camembert Ile de France 125g", 4000, 125),
)


def _metadata(product) -> dict:
    return dict(product.metadata) if isinstance(product.metadata, dict) else {}


def _sync_listings(product, price_q: int, report: dict) -> None:
    """PDV sempre; canal remoto só com foto e nunca a quilo (``sku_records.sync_sale_listings``)."""
    from django.core.exceptions import ValidationError

    try:
        listed, unlisted = sync_sale_listings(product, price_q)
    except ValidationError as exc:
        raise CommandError(exc.messages[0]) from exc
    report["listed"].extend((product.sku, ref) for ref in listed)
    report["unlisted"].extend((product.sku, ref) for ref in unlisted)


def _ensure_collection(product, collection) -> None:
    from shopman.offerman.models import CollectionItem

    if CollectionItem.objects.filter(collection=collection, product=product).exists():
        return
    has_primary = CollectionItem.objects.filter(product=product, is_primary=True).exists()
    last = CollectionItem.objects.filter(collection=collection).order_by("-sort_order").first()
    CollectionItem.objects.create(
        collection=collection, product=product, is_primary=not has_primary,
        sort_order=(last.sort_order + 1) if last else 0,
    )


def _wanted_fiscal(profile: str, ncm: str, cest: str, unit: str) -> dict:
    return {"profile": profile, "ncm": ncm, "unit": unit.upper(), **({"cest": cest} if cest else {})}


def _sync_fiscal(product, wanted: dict, report: dict) -> list[str]:
    """Garante a classificação da tabela. Devolve as linhas do que mudou.

    Vazio ou no perfil antigo (``own_production`` sem CEST, que é como a
    Mercearia nasceu antes do CEST) → a tabela manda. Qualquer outra coisa é
    curadoria de alguém: fica, e a divergência sai no relatório.
    """
    metadata = _metadata(product)
    current = dict(metadata.get("fiscal") or {})
    if all((current.get(k) or "") == (wanted.get(k) or "") for k in ("profile", "ncm", "cest", "unit")):
        return []
    legacy = not current or (current.get("profile", "own_production") == "own_production"
                             and not current.get("cest"))
    if not legacy:
        for field in ("profile", "ncm", "cest"):
            if (current.get(field) or "") != (wanted.get(field) or ""):
                report["conflicts"].append((product.sku, field, current.get(field) or "", wanted.get(field) or ""))
        return []
    metadata["fiscal"] = {**{k: v for k, v in current.items() if k != "cest"}, **wanted}
    product.metadata = metadata
    parts = [f"perfil {wanted['profile']}", f"ncm {wanted['ncm']}"]
    if wanted.get("cest"):
        parts.append(f"cest {wanted['cest']}")
    return ["fiscal: " + ", ".join(parts)]


def _get_or_build(sku: str, name: str, price_q: int, *, unit: str, weight_g: int | None,
                  ncm: str, report: dict):
    """O produto existente (e as divergências dele com a tabela) ou um novo, não salvo."""
    from shopman.offerman.models import AvailabilityPolicy, Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        product = Product(
            sku=sku, name=name, base_price_q=price_q, unit=unit, unit_weight_g=weight_g,
            is_published=False, is_sellable=True,
            availability_policy=AvailabilityPolicy.PLANNED_OK,
        )
        product.metadata = {"fiscal": {"profile": "own_production", "ncm": ncm, "unit": unit.upper()}}
        return product
    for field, value in (("name", name), ("base_price_q", price_q), ("unit", unit)):
        have = getattr(product, field)
        if field == "base_price_q" and have <= 0 < value:
            continue  # preço zero é vazio: quem preenche é o _apply_item
        if have != value:
            report["conflicts"].append((sku, field, have, value))
    return product


def _refusal(item: GroceryItem) -> str:
    from shopman.offerman.contrib.social.schema import gtin_is_valid

    if item.unit == "kg":
        # A etiqueta da balança não é GTIN do produto: declará-lo seria mentira.
        return "item a quilo não leva GTIN de embalagem" if item.gtin else ""
    if item.price_q <= 0:
        return "sem preço"
    if not gtin_is_valid(item.gtin):
        return "GTIN inválido"
    return ""


def _apply_item(item: GroceryItem, collection, report: dict) -> None:
    from shopman.offerman import get_social_attributes
    from shopman.offerman.contrib.social.schema import set_social_attributes
    from shopman.offerman.models import ListingItem

    refusal = _refusal(item)
    if refusal:
        report["refused"].append((item.sku, refusal))
        return

    product = _get_or_build(
        item.sku, item.name, item.price_q, unit=item.unit, weight_g=item.weight_g, ncm=item.ncm,
        report=report,
    )
    is_new = product.pk is None
    lines: list[str] = []
    metadata = _metadata(product)
    product.metadata = metadata
    fiscal_lines = _sync_fiscal(product, _wanted_fiscal(item.profile, item.ncm, item.cest, item.unit), report)
    if not is_new:
        lines.extend(fiscal_lines)
    metadata = _metadata(product)

    if item.gtin_source and metadata.get("gtin_source") != item.gtin_source:
        metadata["gtin_source"] = item.gtin_source
        lines.append(f"origem do GTIN: {item.gtin_source}")
    product.metadata = metadata
    if not is_new and product.base_price_q <= 0 < item.price_q:
        # O preço que faltava chegou: preenche e devolve a venda (produto e
        # listagem) — foi a falta de preço, e só ela, que a tirou.
        product.base_price_q = item.price_q
        product.is_sellable = True
        lines.append(f"preço: → R$ {item.price_q / 100:.2f}{'/kg' if item.unit == 'kg' else ''}; venda ligada")
        ListingItem.objects.filter(product=product).update(price_q=item.price_q, is_sellable=True)
    if product.base_price_q <= 0 and product.is_sellable:
        # Preço zero não vende (dono, 24/09): cadastrado, sim; vendável, não.
        product.is_sellable = False
        if not is_new:
            lines.append("venda: desligada até ter preço")

    social = get_social_attributes(product)
    updates = {}
    for field, value in (("brand", item.brand), ("gtin", item.gtin)):
        have = getattr(social, field)
        if have == value or not value:
            continue
        if have:
            report["conflicts"].append((item.sku, field, have, value))
            continue
        updates[field] = value
        lines.append(f"{field}: → {value}")
    if updates:
        product.metadata = set_social_attributes(product.metadata, replace(social, **updates))

    if is_new:
        product.save()
        report["created"].append(item)
    elif lines:
        product.save()
        report["updated"].append((item.sku, lines))
    _material, purchasable = ensure_purchase_record(product)
    if purchasable and not is_new:
        report["updated"].append((item.sku, ["compra: cadastro de compra do mesmo SKU"]))
    if product.base_price_q <= 0:
        report["no_price"].append((item.sku, "sem preço em fonte nenhuma: cadastrado e fora da venda até o dono dizer"))
    product.keywords.add(COLLECTION_REF, *item.keywords)
    _ensure_collection(product, collection)
    _sync_listings(product, product.base_price_q, report)
    if not product.is_sellable:
        # A grade do PDV lê a LISTAGEM: o produto parado tem de parar lá também.
        ListingItem.objects.filter(product=product, is_sellable=True).update(is_sellable=False)


def _apply_gift_box(box: GiftBox, collection, report: dict) -> None:
    """Caixa presente: produto da casa. Sem GTIN, sem marca de revenda."""
    product = _get_or_build(box.sku, box.name, box.price_q, unit="un", weight_g=None, ncm=box.ncm,
                            report=report)
    if product.pk is None:
        product.save()
        report["created"].append(box)
    product.keywords.add(COLLECTION_REF, "presente", "caixa")
    _ensure_collection(product, collection)
    _sync_listings(product, product.base_price_q, report)


def _apply_placeholder(real: RealPlaceholder, report: dict) -> None:
    from shopman.offerman.models import ListingItem, Product

    product = Product.objects.filter(sku=real.sku).first()
    if product is None:
        report["missing"].append(real.sku)
        return
    fields: list[str] = []
    lines: list[str] = []
    for field, placeholder, value in (
        ("name", real.placeholder_name, real.name),
        ("base_price_q", real.placeholder_price_q, real.price_q),
    ):
        have = getattr(product, field)
        if have == value:
            continue
        if have != placeholder:
            report["conflicts"].append((real.sku, field, have, value))
            continue
        setattr(product, field, value)
        fields.append(field)
        lines.append(f"{field}: {have!r} → {value!r}")
    if "name" in fields and product.unit_weight_g != real.weight_g:
        lines.append(f"peso: {product.unit_weight_g} g → {real.weight_g} g")
        product.unit_weight_g = real.weight_g
        fields.append("unit_weight_g")
    metadata = _metadata(product)
    if "base_price_q" in fields or (metadata.get("price_tbd") and product.base_price_q == real.price_q):
        if metadata.pop("price_tbd", None):
            lines.append("preço deixa de ser provisório")
            product.metadata = metadata
            fields.append("metadata")
    if not fields:
        return
    product.save(update_fields=[*fields, "updated_at"])
    if "base_price_q" in fields:
        # A listagem guarda o preço de cada canal: o PDV cobra o da listagem,
        # não o do produto. Só troca o que ainda era o placeholder.
        ListingItem.objects.filter(product=product, price_q=real.placeholder_price_q).update(price_q=real.price_q)
    report["updated"].append((real.sku, lines))


def _link_aliases(report: dict) -> None:
    """Aponta o de-para do Yooga (sem produto, ou num placeholder que sai) ao produto real."""
    from django.db.models import Q
    from shopman.offerman.models import Product

    from shopman.backstage.models import ProductAlias

    products = {p.sku: p for p in Product.objects.filter(sku__in=set(YOOGA_NAMES.values()))}
    aliases = ProductAlias.objects.filter(source="yooga", external_name__in=YOOGA_NAMES).filter(
        Q(product__isnull=True) | Q(product__sku__in=LEAVING_PLACEHOLDERS)
    ).select_related("product")
    for alias in aliases:
        target = products.get(YOOGA_NAMES[alias.external_name])
        if target is None:
            continue
        before = alias.product.sku if alias.product_id else "—"
        alias.product = target
        alias.save(update_fields=["product"])
        report["aliases"].append((alias.external_name, before, target.sku))


def _apply_seed_resale_fiscal(entry: SeedResaleFiscal, report: dict) -> None:
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=entry.sku).first()
    if product is None:
        report["missing"].append(entry.sku)
        return
    lines = _sync_fiscal(product, _wanted_fiscal(entry.profile, entry.ncm, entry.cest, "UN"), report)
    if entry.weight_g is not None and product.unit_weight_g != entry.weight_g:
        lines.append(f"peso: {product.unit_weight_g} g → {entry.weight_g} g")
        product.unit_weight_g = entry.weight_g
    if lines:
        product.save(update_fields=["metadata", "unit_weight_g", "updated_at"])
        report["updated"].append((entry.sku, lines))


def _apply_supplier_cost(entry: SupplierCost, report: dict) -> None:
    """Custo do fornecedor no cadastro de compra, com a origem ao lado."""
    from shopman.buyman.models import Material, Supplier, SupplierMaterialCost

    material = Material.objects.filter(sku=entry.sku).first()
    if material is None:
        report["missing"].append(entry.sku)
        return
    supplier, created_supplier = Supplier.objects.get_or_create(
        ref=entry.supplier_ref, defaults={"name": entry.supplier_name},
    )
    lines: list[str] = []
    if created_supplier:
        lines.append(f"fornecedor {entry.supplier_ref} criado")
    cost, created = SupplierMaterialCost.objects.get_or_create(
        supplier=supplier, material=material,
        defaults={"cost_q": entry.cost_q, "is_preferred": True},
    )
    if created:
        lines.append(f"custo {entry.supplier_ref}: R$ {entry.cost_q / 100:.2f}/{material.unit} ({entry.source})")
    elif cost.cost_q != entry.cost_q:
        report["conflicts"].append((entry.sku, "custo", cost.cost_q, entry.cost_q))
    metadata = dict(material.metadata or {})
    purchase = dict(metadata.get("purchase") or {})
    origin = {"cost_q": entry.cost_q, "date": entry.date, "source": entry.source, "supplier": entry.supplier_ref}
    if purchase.get("cost_origin") != origin or metadata.get("supplier") != entry.supplier_ref:
        purchase["cost_origin"] = origin
        metadata["purchase"] = purchase
        metadata.setdefault("supplier", entry.supplier_ref)
        material.metadata = metadata
        material.save(update_fields=["metadata"])
        if not created:
            lines.append(f"origem do custo: {entry.source}")
    if lines:
        report["updated"].append((entry.sku, lines))


@dataclass(frozen=True)
class Opening:
    """Revenda que a produção também usa: a embalagem se abre num insumo pesado.

    Ver ``shopman/shop/services/package_opening.py``. Declarado aqui para que o
    banco novo (seed) e o que já roda (este comando) terminem iguais.
    """

    sku: str
    #: O insumo em que ela se abre — o que as fichas JÁ usam, para não mexer nelas.
    opened_sku: str
    opened_name: str
    opened_unit: str
    quantity: str
    shelf_life_days: int
    #: De onde veio a validade depois de aberta.
    source: str


OPENINGS: tuple[Opening, ...] = (
    # O tablete de 200 g abre em 0,200 kg de MANTEIGA-PRESIDENT-COM-SAL, o insumo
    # que as fichas das montagens já usam (a manteiga de wasabi) — então nenhuma
    # ficha muda. As massas usam OUTRA manteiga (a sem sal, a granel) e ficam
    # como estão. Validade depois de aberta: 30 dias refrigerada — orientação
    # usual de rótulo para manteiga com sal a 0–10 °C (pouca água livre, o sal
    # conserva); o lote do aberto nunca passa da validade da embalagem
    # (``package_opening._opened_batch``). ⚠️ Conferir no rótulo da Président
    # que chega: se ele disser menos, vale o rótulo.
    Opening("MANTEIGA-SAL-PRESIDENT-200", "MANTEIGA-PRESIDENT-COM-SAL", "Manteiga President com sal", "kg",
            "0.200", 30, "orientação usual de rótulo de manteiga com sal refrigerada (conferir no rótulo)"),
)


def _apply_opening(opening: Opening, report: dict) -> None:
    from shopman.buyman.models import Material

    from shopman.shop.services.package_opening import declare_opening

    package = Material.objects.filter(sku=opening.sku).first()
    if package is None:
        report["missing"].append(opening.sku)
        return
    current = (package.metadata or {}).get("opens_into") if isinstance(package.metadata, dict) else None
    if isinstance(current, dict) and current.get("sku"):
        return  # já declarado (aqui ou pelo Compras): quem declarou manda
    opened = Material.objects.filter(sku=opening.opened_sku).first()
    if opened is None:
        opened = Material(sku=opening.opened_sku, name=opening.opened_name, unit=opening.opened_unit)
        opened.full_clean()
        opened.save()
    declare_opening(package, opened_sku=opened.sku, quantity=opening.quantity, shelf_life_days=opening.shelf_life_days)
    report["updated"].append(
        (opening.sku, [f"quando aberto, vira {opened.sku} ({opening.quantity} {opened.unit})"])
    )


def apply_grocery(*, apply: bool) -> dict[str, list]:
    """Cria/atualiza a Mercearia real. Sem ``apply``, executa e desfaz.

    Chaves do relatório: ``created`` [GroceryItem | GiftBox], ``updated`` [(sku, linhas)],
    ``listed``/``unlisted`` [(sku, listagem)], ``conflicts`` [(sku, campo, atual,
    tabela)], ``refused`` [(sku, motivo)], ``no_price`` [(sku, motivo)],
    ``aliases`` [(nome no Yooga, antes, depois)],
    ``missing`` [sku], ``left_out`` [(sku, motivo)].
    """
    from shopman.offerman.models import Collection

    report: dict[str, list] = {
        "created": [], "updated": [], "listed": [], "unlisted": [], "conflicts": [],
        "refused": [], "no_price": [], "aliases": [], "missing": [],
        "left_out": sorted(LEFT_OUT.items()),
    }
    collection = Collection.objects.filter(ref=COLLECTION_REF).first()
    if collection is None:
        raise CommandError(f"A coleção `{COLLECTION_REF}` não existe neste banco.")

    with transaction.atomic():
        for item in GROCERY:
            _apply_item(item, collection, report)
        for box in GIFT_BOXES:
            _apply_gift_box(box, collection, report)
        for real in REAL_PLACEHOLDERS:
            _apply_placeholder(real, report)
        for entry in SEED_RESALE_FISCAL:
            _apply_seed_resale_fiscal(entry, report)
        for cost in SUPPLIER_COSTS:
            _apply_supplier_cost(cost, report)
        for opening in OPENINGS:
            _apply_opening(opening, report)
        _link_aliases(report)
        if not apply:
            transaction.set_rollback(True)
    return report


class Command(BaseCommand):
    help = "Cria a revenda real da Mercearia (PDV; canal remoto só com foto) e troca os placeholders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando executa e desfaz, e só mostra o relatório.",
        )

    def handle(self, *args, apply: bool = False, **options):
        report = apply_grocery(apply=apply)
        out = self.stdout
        if report["created"]:
            verb = "Criados" if apply else "Criaria"
            out.write(self.style.SUCCESS(f"\n{verb} {len(report['created'])} produto(s) de Mercearia:"))
            for item in report["created"]:
                gtin = getattr(item, "gtin", "") or "—"
                price = f"R$ {item.price_q / 100:6.2f}" + ("/kg" if getattr(item, "unit", "un") == "kg" else "")
                out.write(f"  {item.sku:38s} {item.name[:44]:44s} {price:12s} {gtin}")
        for sku, lines in report["updated"]:
            out.write(f"  {sku:38s} {'; '.join(lines)}")
        listed = {}
        for sku, ref in report["listed"]:
            listed.setdefault(ref, []).append(sku)
        for ref, skus in sorted(listed.items()):
            out.write(f"  listagem {ref}: +{len(skus)}")
        if report["aliases"]:
            out.write(f"  de-paras do Yooga reapontados (a venda antiga volta ao produto): {len(report['aliases'])}")
            for name, before, after in report["aliases"]:
                out.write(f"    {name[:46]:46s} {before} → {after}")
        for sku, ref in report["unlisted"]:
            out.write(self.style.WARNING(f"  {sku:38s} sai de {ref}: sem foto (ou a quilo) não se vende de longe"))
        for sku, field, have, want in report["conflicts"]:
            out.write(self.style.WARNING(f"  {sku:38s} {field} já é {have!r} (a tabela diz {want!r}) — mantido"))
        for sku, reason in report["no_price"]:
            out.write(self.style.WARNING(f"  {sku:38s} {reason}"))
        for sku, reason in report["refused"]:
            out.write(self.style.ERROR(f"  {sku:38s} recusado: {reason}"))
        if report["missing"]:
            out.write(self.style.WARNING(f"  fora do catálogo deste banco: {', '.join(report['missing'])}"))

        out.write(f"\nFicam de fora ({len(report['left_out'])}):")
        for sku, reason in report["left_out"]:
            out.write(f"  {sku:38s} {reason}")

        out.write(self.style.SUCCESS(
            f"\n{len(report['created'])} criado(s), {len(report['updated'])} atualizado(s), "
            f"{len(report['conflicts'])} divergência(s) mantida(s), {len(report['refused'])} recusado(s)."
        ))
        if not apply:
            out.write(self.style.WARNING("(ensaio: executado e desfeito, nada gravado. Para gravar: --apply)"))
