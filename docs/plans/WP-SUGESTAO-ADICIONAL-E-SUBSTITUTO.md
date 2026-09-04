# WP-SUGESTÃO — Adicional que combina e substituto à altura: um motor, dois objetivos

> Estado: **proposto (2026-09-04), perguntas respondidas pelo dono no mesmo dia (abaixo).** Nasce do piloto do
> concierge: a regra de adicional em vigor ("o item mais popular que não está na
> sacola", a mesma do carrinho do site) ofereceu Água a quem levava pão. O dono
> pediu um mecanismo **simples, robusto e elegante**, o mesmo para o site e para o
> chat, e um irmão para substituição quando o item pedido não existe ou acabou.
>
> | # | Pergunta | Recomendado (a confirmar) |
> |---|---|---|
> | 1 | Sinais | histórico de vendas (co-ocorrência, ano inteiro com peso decrescente) + três facetas de vocação do SKU (natureza, sabor, consumo) + coleção + palavras-chave + gramatura. **Sem** "combina com" por SKU como pré-requisito; ele existe só como ajuste fino, opcional |
> | 2 | Onde vive a regra | `shop/projections/suggestions.py`, uma função pura sobre uma tabela de afinidade recalculada de madrugada |
> | 3 | Quem consome | carrinho do site (hoje `build_cart.upsell`), concierge (`review_order.suggestion` e `set_item` sem estoque), PDV depois |
> | 4 | Palavras-chave | as que já existem em `Product.keywords`; a IA do Gestor **sugere** no painel do produto, o gestor aprova |
> | 5 | Explicabilidade | toda sugestão carrega `reasons` (códigos); o Admin mostra e o B.I. mede aceitação |

## O que já existe (o WP não inventa sinal)

| Sinal | Onde | Estado |
|---|---|---|
| Substituto por palavras-chave + mesma coleção + pontuação | `packages/offerman/.../contrib/substitutes/substitutes.py::find_substitutes` (`Product.keywords`) | no ar; é o que o estoque devolve em `CartUnavailableError.substitutes` |
| Vocação do SKU: leitura (consumo no local / para levar / híbrido), tipo de bebida, peso de salão | `shopman/backstage/models/consumption.py` (`ConsumptionRole`, `ProductConsumptionTag`) | no ar, alimenta o B.I. |
| Histórico de vendas com itens por venda | `backstage_historicalsale` / `historicalsaleitem` (81 mil vendas importadas) + pedidos nativos (`orderman_order`/`orderitem`) | no ar |
| Popularidade | `shop/projections/storefront_context.popular_skus` (favoritos do Guestman) | no ar, fraco: favorito ≠ vendido |
| Portões de canal e disponibilidade | `catalog_context.visible_skus_in_channel`, `listing_sellable_map`, `availability.check` | no ar; já filtram o adicional de hoje |
| Assist de IA no painel do produto | `shopman/backstage/api/catalog.py::CatalogAiAssistView` + `shop/services/copy_assist` | no ar para descrição e legenda |

O que falta é **um lugar** que combine esses sinais com pesos, e não uma regra por superfície.

## A vocação do produto: três facetas, nenhuma coleção nova

O "papel de consumo" de hoje (`ConsumptionRole`: consome aqui / leva / híbrido,
bebida preparada / pronta, peso de salão) responde "senta ou leva" para o B.I. e
fica como está. O motor precisa de mais duas perguntas, e cada uma é uma
**faceta do produto**, não uma coleção:

| Faceta | Valores | Para quê |
|---|---|---|
| Natureza | comida · bebida · acompanhamento (manteiga, geleia, molho) · outro (varejo, grão) | regras de adicional genéricas: comida → acompanhamento, comida → bebida, bebida → bebida |
| Sabor | doce · salgado · neutro | fronteira do substituto (doce → doce) e a regra doce → café |
| Consumo | o papel de hoje, intocado | contexto de salão × balcão (B.I. e filtro do adicional) |

Moram no mesmo registro de vocação do SKU (`ProductConsumptionTag` ganha
`nature` e `flavor`), editáveis no painel do produto e sugeridas pela IA.
Coleção continua sendo o mapa do cliente, publicada por mérito de vitrine: não
se cria coleção para o motor, nem coleção oculta, nem regra de "só a primária".
Carga inicial derivada das coleções atuais (doces → doce, bebidas → bebida) e
revisada uma vez; produto novo nasce com sugestão da IA e aprovação do gestor.
Faceta em branco vira "outro/neutro" e o motor cai para coleção e palavras-chave.

## Desenho: um motor, dois objetivos

```
suggest(objective, *, cart_skus, anchor_sku=None, channel_ref, context) -> tuple[Suggestion, ...]
   objective = "complement" (adicional)  |  "substitute" (no lugar de)
   Suggestion = {sku, name, price_display, score, reasons: ("bought_together", "beverage_for_food", "same_collection", "keyword:centeio", ...)}
```

Uma função pura em `shop/projections/suggestions.py`, sem IO além de ler a
tabela de afinidade e o catálogo. Os mesmos **portões** para os dois objetivos:
visível no canal, vendável, disponível agora, fora da sacola (adicional) ou fora
do próprio item (substituto). Sugestão que não passa nos portões não existe.

### Sinais e pesos por objetivo

| Sinal | Adicional | Substituto | Fonte |
|---|---|---|---|
| Co-ocorrência (lift do par no histórico, ano inteiro com peso decrescente) | forte | fraco (quem compra junto não substitui) | tabela de afinidade |
| Natureza complementar (comida → acompanhamento; comida → bebida; bebida → bebida; doce → café) | forte | nulo | facetas |
| Sabor (doce → doce, salgado → salgado) | filtro para doce → café | fronteira | facetas |
| Gramatura (o mais próximo disponível, sem faixa) | nulo | forte | peso por unidade do produto |
| Contexto de consumo (retirada, entrega, salão) | filtro: no salão vale bebida; na entrega não sugere sorvete | filtro | `context` (fulfillment/canal) |
| Mesma coleção | fraco | forte; fora da coleção só quando dentro não há disponível, no mesmo sabor | `Collection` |
| Palavras-chave em comum | nulo | forte | `Product.keywords` |
| Proximidade de nome (fuzz) | nulo | médio | nome |
| Faixa de preço | mais barato que a média da sacola | ±30% do item | listing do canal |
| Popularidade (vendido, não favoritado) | desempate | desempate | tabela de afinidade |
| Ajuste manual ("combina com", "substituível por") | soma, nunca pré-requisito | idem | `Product.metadata["pairs_with"]`, opcional |

O resultado é uma lista curta e ordenada; a superfície decide quantos mostra
(o carrinho do site um, o concierge um por conversa, o substituto até três).

### A tabela de afinidade

Um model pequeno `ProductAffinity(sku_a, sku_b, together_count, lift, window_days,
computed_at)` recalculado pelo `maintenance_worker` (comando
`compute_product_affinity`, uma vez por noite) a partir do histórico importado e
dos pedidos nativos. Robustez: produto novo, sem histórico, cai nos sinais de
vocação e coleção; histórico fino (poucos pares) não gera lift acima do ruído
(mínimo de suporte). Nada é calculado na hora do pedido.

### Palavras-chave com a IA no lugar certo

As palavras-chave já são o coração do substituto e são úteis para busca e SEO.
No painel do produto do Gestor, o mesmo assist que escreve descrição passa a
**sugerir palavras-chave** (a partir de nome, descrição, coleção, vocação); o
gestor aprova ou edita. A IA nunca grava sozinha. Assim o dado nasce barato e
sem ficha por SKU.

## Fases

| Fase | Entrega | Gate |
|---|---|---|
| F1 | facetas natureza/sabor no registro de vocação (migração + carga derivada das coleções + revisão no Admin), porque as regras de adicional dependem delas; `ProductAffinity` + comando noturno; `suggestions.suggest("complement")` com portões e `reasons`; `build_cart.upsell` passa a usar; concierge religa `CONCIERGE_SUGGEST_ADD_ONS` | teste com a sacola do piloto: pão → café/manteiga, nunca água por popularidade |
| F2 | `suggest("substitute")` unificando `find_substitutes` (keywords + coleção + fuzz + preço + disponibilidade); estoque e concierge consomem | item esgotado devolve até três à altura |
| F3 | assist de palavras-chave em lote com Search Console/Trends como fonte; Admin lista sugestões com `reasons`; B.I. mede aceitação por superfície | métrica: aceitação ≥ 10% no chat |
| F4 (opcional) | `pairs_with` / `substitute_for` como ajuste fino, e contexto de salão para o PDV | só se F1–F3 pedirem |

## Respostas do dono (04/09/2026)

1. **Histórico:** ano inteiro com peso decrescente (custa nada: cálculo noturno).
2. **Vocação:** "comida → acompanhamento" genérico, em vez de manteiga/geleia por SKU; e revisar o papel de consumo com as facetas acima, sem estragar o que o B.I. já lê.
3. **Substituto:** dentro da coleção primeiro, fora como reserva; doce → doce e salgado → salgado são fronteira.
4. **Palavras-chave:** rodar o assist em lote, com peso de SEO: fontes Google que valem são o Search Console (buscas reais que já trazem ao site; API gratuita, exige autorização da propriedade) e o Trends (volume relativo para desempatar sinônimos). Keyword Planner exige conta do Ads: fora.
5. **Gramatura:** o mais próximo disponível, sem faixa.

## Referências

- [WHATSAPP-CONCIERGE-PLAN](WHATSAPP-CONCIERGE-PLAN.md) (a sugestão no chat é uma por conversa; desligada até F1)
- `docs/plans/BI-DATA-FOUNDATION-PLAN.md` (vocação de consumo), `packages/offerman/.../contrib/substitutes/`
