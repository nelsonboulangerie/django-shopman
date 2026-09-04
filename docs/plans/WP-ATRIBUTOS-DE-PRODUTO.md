# WP-ATRIBUTOS — Atributos de produto com definição: um registro, valores no produto, zero legado

> Estado: **proposto (2026-09-04), a pedido do dono.** Insight dele: "um sistema de
> atributos ultra flexível, chave/valor, que sirva até para grades, cores e
> tamanhos". A resposta dos PIMs (Akeneo, Shopify metafields, Saleor, Odoo) é a
> mesma: **chave/valor sim, mas com definição**; sem registro de atributo,
> "cor", "Cor" e "côr" convivem e nenhuma regra consegue ler.
>
> | # | Pergunta | Decidido / recomendado |
> |---|---|---|
> | 1 | Tabela nova? | **Sim, uma, no Core:** `offerman.AttributeDefinition`. O catálogo é do Offerman; a definição de atributo é estrutural e consultável, o caso em que a regra da casa pede tabela, não JSON |
> | 2 | Onde ficam os valores? | `Product.metadata["attributes"]`, validados contra a definição por um service; nenhuma coluna nova em `Product` |
> | 3 | Legado? | **Nenhum.** `allergens`, `dietary_info`, `serves` (chaves soltas de metadata) e `unit_weight_g` (coluna) viram atributos definidos, com migração de dados e todos os leitores atualizados; o nome antigo some |
> | 4 | B.I.? | **Atualizado no mesmo WP.** O papel de consumo vira atributo `papel_consumo` do produto; a tabela do B.I. sobra só para linhas do histórico sem produto no catálogo |
> | 5 | Tags (`keywords`, taggit)? | ficam: linguagem livre para busca, SEO e afinidade. Atributo é fato; tag é palavra |

## Por que tabela, e por que só uma

A regra da casa é usar JSON para dado contextual e discutir tabela quando o dado é
estrutural e consultável em escala. A **definição** de um atributo é exatamente
isso: seu tipo, seus valores permitidos e para que serve são consultados por
todas as superfícies, pelo Admin e pelo motor de sugestão. O **valor** por
produto é contextual e mora no JSON que o produto já tem.

```
AttributeDefinition (offerman)
  ref            slug único ("sabor", "natureza", "alergenos", "porcoes", "peso_unidade_g", "papel_consumo")
  label, hint    rótulos para o gestor
  type           choice | multi_choice | number | text | boolean
  options        [{"value": "doce", "label": "Doce", "meta": {...}}]   (choice/multi)
  unit           "g", "porções" (number)
  purposes       subconjunto de {"facet", "rule", "feed", "variant", "label"}
  required       o produto precisa ter valor? (o Admin acusa os que faltam)
  ordering, is_active
```

`options[].meta` é o que faz o papel de consumo caber sem tabela própria: cada
opção carrega `reading`, `beverage`, `eat_in_weight`, que hoje são colunas de
`ConsumptionRole`.

## Valores e proveniência

```
Product.metadata["attributes"] = {
  "natureza":       {"value": "comida",        "source": "derived"},
  "sabor":          {"value": "doce",          "source": "ai", "reviewed": false},
  "alergenos":      {"value": ["leite","ovos"],"source": "manual"},
  "porcoes":        {"value": 2,               "source": "manual"},
  "peso_unidade_g": {"value": 70,              "source": "manual"},
  "papel_consumo":  {"value": "hibrido",       "source": "manual"},
}
```

`source` é a proveniência (`manual`, `ai`, `derived`, `recipe`), e `reviewed`
diz se um valor sugerido pela IA foi aprovado. É o que `dietary_auto_filled` e
`ProductConsumptionTag.reviewed` faziam cada um de um jeito; agora é uma coisa só.

Acesso pelo código: `product.attr("sabor")` devolve o valor tipado (ou o
default da definição), `product.set_attr("sabor", "doce", source="manual")`
valida e grava. Consulta: `Product.objects.filter(metadata__attributes__sabor__value="doce")`.

## O que morre, e o que nasce no lugar

| Hoje | Vira | Leitores a atualizar |
|---|---|---|
| `metadata["allergens"]` (lista) | atributo `alergenos` (multi_choice, opções = a lista canônica dos alergênicos, `purposes: label, facet`) | PDP, ficha/rótulo, catálogo, seed |
| `metadata["dietary_info"]` + `dietary_auto_filled` | atributo `dieta` (multi_choice: vegano, sem glúten, …; proveniência substitui o sentinela) | PDP, filtros da loja, preferências alimentares, `nutrition_from_recipe`, seed |
| `metadata["serves"]` | atributo `porcoes` (number) | PDP, seed |
| `Product.unit_weight_g` (coluna) | atributo `peso_unidade_g` (number, unidade g, `purposes: rule, label`) | `apply_product_measurements`, `nutrition_from_recipe`, rótulo manual, catálogo/PDP, admin do Offerman |
| `ConsumptionRole` (5 papéis) | opções de `papel_consumo`, com `meta` (reading, beverage, eat_in_weight) | inferência do B.I., hub de configurações |
| `ProductConsumptionTag` (por SKU texto, inclusive histórico) | para SKU do catálogo: `papel_consumo` no produto. Para linha do histórico **sem produto** (combos do Yooga): `HistoricalConsumptionTag`, no B.I., onde a história mora | `backstage/services/consumption.py`, seed do histórico |
| (não existe) | atributos `natureza` e `sabor` (choice, `purposes: rule`) | motor de sugestão (WP-SUGESTÃO) |

`fiscal` e `social` **não** entram: são esquemas de outros donos (fiscalman e o PIM
social), já canônicos. `purchase`, `lead_time_hours`, `made_to_order`, `ready_from`
ficam onde estão por enquanto; podem virar atributo depois, um a um, sem pressa.

Migrações: uma no Offerman (tabela + dados: cria as definições do sistema, move os
quatro valores para `attributes`, remove `unit_weight_g`), uma no Backstage
(papéis → opções; etiquetas com produto → atributo; etiquetas sem produto →
`HistoricalConsumptionTag`; apaga as duas tabelas antigas). Pré-go-live: sem alias,
sem nome antigo.

## B.I.: o padrão novo, sem perder a inferência

A inferência de salão × balcão passa a ler `papel_consumo` do produto (via
`ProductAlias` para SKUs do histórico que resolvem a produto) e, na falta,
`HistoricalConsumptionTag` para linhas que só existem no histórico. Mesmos
pesos, mesmo `eat_in_weight`, agora na `meta` da opção. A tela de curadoria do
B.I. ("de-para pendente", "sem etiqueta") passa a apontar para o produto quando
há produto, e para a etiqueta histórica quando não há. Nenhum relatório muda de
número: é o gate de aceite deste WP (rodar o B.I. antes e depois e comparar).

## Variantes (grades, tamanhos, cores)

Não entram agora, mas ficam possíveis sem retrabalho: uma definição com
`purposes: variant` (ex.: `tamanho`) e um `variant_of` entre SKUs, quando a casa
precisar. Cada variante continua sendo um SKU com preço e estoque próprios, como
já é com unidade × pack.

## Onde o gestor mexe

- Admin do Offerman: CRUD de `AttributeDefinition` (Unfold canônico).
- Painel do produto no Gestor: os atributos aparecem como campos tipados (escolha,
  múltipla, número), com o assist de IA propondo valor e marcando `source: ai`;
  o gestor aprova. É o mesmo assist que hoje escreve descrição.
- O Admin lista produtos com atributo obrigatório em branco.

## Fases

| Fase | Entrega | Gate |
|---|---|---|
| F1 | `AttributeDefinition` + `attr/set_attr` + migração dos quatro legados + leitores atualizados + seed + Admin | `make test` verde; PDP, rótulo e catálogo idênticos antes e depois |
| F2 | `papel_consumo` como atributo; `HistoricalConsumptionTag`; inferência do B.I. lendo o padrão novo; tabelas antigas apagadas | relatórios do B.I. com os mesmos números antes e depois |
| F3 | `natureza` e `sabor` com carga derivada das coleções; painel do produto com assist | é a F1 do [WP-SUGESTÃO](WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md) |

## Referências

- [WP-SUGESTÃO](WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md) (consome `natureza`, `sabor`, `peso_unidade_g`)
- `docs/reference/data-schemas.md` (as chaves de `Product.metadata` que saem e a que entra)
- `shopman/backstage/models/consumption.py`, `packages/offerman/.../models/product.py`
