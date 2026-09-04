# WP-SUGESTÃO — Adicional que combina e substituto à altura: um motor, dois objetivos

> Estado: **proposto (2026-09-04), aguarda palavra do dono.** Nasce do piloto do
> concierge: a regra de adicional em vigor ("o item mais popular que não está na
> sacola", a mesma do carrinho do site) ofereceu Água a quem levava pão. O dono
> pediu um mecanismo **simples, robusto e elegante**, o mesmo para o site e para o
> chat, e um irmão para substituição quando o item pedido não existe ou acabou.
>
> | # | Pergunta | Recomendado (a confirmar) |
> |---|---|---|
> | 1 | Sinais | histórico de vendas (co-ocorrência) + vocação do SKU (B.I.) + coleção + palavras-chave. **Sem** "combina com" por SKU como pré-requisito; ele existe só como ajuste fino, opcional |
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
| Co-ocorrência (lift do par no histórico, 90 dias) | forte | fraco (quem compra junto não substitui) | tabela de afinidade |
| Vocação complementar (comida → bebida; bebida → bebida; doce → café) | forte | nulo | `ConsumptionRole` |
| Contexto de consumo (retirada, entrega, salão) | filtro: no salão vale bebida; na entrega não sugere sorvete | filtro | `context` (fulfillment/canal) |
| Mesma coleção | fraco | forte | `Collection` |
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
| F1 | `ProductAffinity` + comando noturno + `suggestions.suggest("complement")` com portões e `reasons`; `build_cart.upsell` passa a usar; concierge religa `CONCIERGE_SUGGEST_ADD_ONS` | teste com a sacola do piloto: pão → café/manteiga, nunca água por popularidade |
| F2 | `suggest("substitute")` unificando `find_substitutes` (keywords + coleção + fuzz + preço + disponibilidade); estoque e concierge consomem | item esgotado devolve até três à altura |
| F3 | assist de palavras-chave no painel do produto; Admin lista sugestões com `reasons`; B.I. mede aceitação por superfície | métrica: aceitação ≥ 10% no chat |
| F4 (opcional) | `pairs_with` / `substitute_for` como ajuste fino, e contexto de salão para o PDV | só se F1–F3 pedirem |

## Perguntas para o dono

1. Janela do histórico: 90 dias, ou o ano inteiro com peso decrescente?
2. Vocação complementar: as regras comida→bebida, bebida→bebida, doce→café bastam para começar, ou há outras da casa?
3. Substituto: só na mesma coleção, ou pode cruzar (folhado esgotado → brioche)?
4. Assist de palavras-chave: sugere em lote para o catálogo inteiro uma vez, ou só produto a produto?

## Referências

- [WHATSAPP-CONCIERGE-PLAN](WHATSAPP-CONCIERGE-PLAN.md) (a sugestão no chat é uma por conversa; desligada até F1)
- `docs/plans/BI-DATA-FOUNDATION-PLAN.md` (vocação de consumo), `packages/offerman/.../contrib/substitutes/`
