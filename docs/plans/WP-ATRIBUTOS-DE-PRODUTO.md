# WP-ATRIBUTOS — Atributos de produto com definição: um registro, valores no produto, zero legado

> Estado: **proposto (2026-09-04), a pedido do dono, revisto no mesmo dia por análise adversarial.**
> Veredito: **o Core não muda.** O registro de atributos é configuração do tenant e
> mora em `shop/models`, como `RuleConfig` e `OmotenashiCopy`; os valores ficam no
> `Product.metadata` que já existe. O peso por unidade continua coluna. A migração do
> papel de consumo do B.I. fica adiada até um leitor precisar dela.
>
> Insight do dono: "um sistema de
> atributos ultra flexível, chave/valor, que sirva até para grades, cores e
> tamanhos". A resposta dos PIMs (Akeneo, Shopify metafields, Saleor, Odoo) é a
> mesma: **chave/valor sim, mas com definição**; sem registro de atributo,
> "cor", "Cor" e "côr" convivem e nenhuma regra consegue ler.
>
> | # | Pergunta | Decidido / recomendado |
> |---|---|---|
> | 1 | Tabela nova? | **Sim, uma, no orquestrador:** `shop.AttributeDefinition`. É configuração do tenant (como `RuleConfig`); o Core (Offerman) não muda |
> | 2 | Onde ficam os valores? | `Product.metadata["attributes"]`, validados contra a definição por um service em `shop`; nenhuma coluna nova em `Product` |
> | 3 | Legado? | **Nenhum nome antigo.** `allergens`, `dietary_info`, `serves` viram atributos definidos (migração de dados + leitores). `unit_weight_g` **continua coluna** (fato físico de primeira classe, com integridade no banco); o registro o define e aponta para a coluna |
> | 4 | B.I.? | **Adiado (F3).** O papel de consumo vira atributo só quando um leitor precisar; hoje o motor de sugestão precisa de natureza e sabor, não do papel. Quando vier, a tabela do B.I. sobra só para linhas do histórico sem produto |
> | 5 | Tags (`keywords`, taggit)? | ficam: linguagem livre para busca, SEO e afinidade. Atributo é fato; tag é palavra |

## Por que tabela, por que só uma, e por que em `shop`

A regra da casa é usar JSON para dado contextual e discutir tabela quando o dado é
estrutural e consultável em escala. A **definição** de um atributo é exatamente
isso: seu tipo, seus valores permitidos e para que serve são consultados por
todas as superfícies, pelo Admin e pelo motor de sugestão. O **valor** por
produto é contextual e mora no JSON que o produto já tem.

E ela é **configuração do tenant**, não regra de catálogo: a Nelson decide que
"sabor" existe e vale "doce/salgado/neutro"; outro tenant decidiria outra
coisa. Configuração mora em `shop/models`, ao lado de `RuleConfig`,
`NotificationTemplate` e `OmotenashiCopy`. O Offerman continua sabendo só de
produto, preço, vitrine e `metadata`.

```
AttributeDefinition (shop)
  ref            slug único ("sabor", "natureza", "temperatura", "alergenos", "porcoes", "peso_unidade_g")
                 é DADO do tenant, em português, como as coleções `paes`/`folhados`
  label, hint    rótulos para o gestor
  type           choice | multi_choice | number | text | boolean
  options        [{"value": "doce", "label": "Doce", "meta": {...}}]   (choice/multi)
  unit           "g", "porções" (number)
  purposes       subconjunto de {"facet", "rule", "feed", "variant", "label"}
  required       o produto precisa ter valor? (o Admin acusa os que faltam)
  ordering, is_active
```

`storage` diz onde o valor mora: `metadata` (o padrão) ou `column:<nome>` para os
poucos fatos físicos que merecem coluna (peso por unidade). `options[].meta` é o
que permitirá, na F3, o papel de consumo caber sem tabela própria (cada opção
carrega `reading`, `beverage`, `eat_in_weight`).

## Valores e proveniência

```
Product.metadata["attributes"] = {
  "natureza":       {"value": "comida",        "source": "derived"},
  "sabor":          {"value": "doce",          "source": "ai", "reviewed": false},
  "alergenos":      {"value": ["leite","ovos"],"source": "manual"},
  "porcoes":        {"value": 2,               "source": "manual"},
}
# peso_unidade_g: definido no registro com storage "column:unit_weight_g"; papel_consumo: F3.
```

`source` é a proveniência (`manual`, `ai`, `derived`, `recipe`), e `reviewed`
diz se um valor sugerido pela IA foi aprovado. É o que `dietary_auto_filled` e
`ProductConsumptionTag.reviewed` faziam cada um de um jeito; agora é uma coisa só.

Acesso pelo código em `shop/services/attributes.py` (o Core não ganha método):
`attributes.get(product, "sabor")` devolve o valor tipado (ou o default da
definição), `attributes.set(product, "sabor", "doce", source="manual")` valida e grava. Consulta: `Product.objects.filter(metadata__attributes__sabor__value="doce")`.

## O que morre, e o que nasce no lugar

| Hoje | Vira | Leitores a atualizar |
|---|---|---|
| `metadata["allergens"]` (lista) | atributo `alergenos` (multi_choice, opções = a lista canônica dos alergênicos, `purposes: label, facet`) | PDP, ficha/rótulo, catálogo, seed |
| `metadata["dietary_info"]` + `dietary_auto_filled` | atributo `dieta` (multi_choice: vegano, sem glúten, …; proveniência substitui o sentinela) | PDP, filtros da loja, preferências alimentares, `nutrition_from_recipe`, seed |
| `metadata["serves"]` | atributo `porcoes` (number) | PDP, seed |
| `Product.unit_weight_g` (coluna) | **fica coluna**; o registro define `peso_unidade_g` com `storage: column:unit_weight_g` (`purposes: rule, label`) | nenhum leitor muda |
| `ConsumptionRole` + `ProductConsumptionTag` | **F3, só quando um leitor pedir:** opções de `papel_consumo` com `meta`; etiqueta sem produto no catálogo vira `HistoricalConsumptionTag` no B.I. | inferência do B.I., hub de configurações |
| (não existe) | atributos `natureza`, `sabor` e `temperatura` (choice, `purposes: rule`) | motor de sugestão (WP-SUGESTÃO), que os lê por REGRA configurável, nunca por nome fixo no código |

`fiscal` e `social` **não** entram: são esquemas de outros donos (fiscalman e o PIM
social), já canônicos. `purchase`, `lead_time_hours`, `made_to_order`, `ready_from`
ficam onde estão por enquanto; podem virar atributo depois, um a um, sem pressa.

Migrações: uma em `shop` (tabela + dados: cria as definições do sistema e move
`allergens`, `dietary_info`, `serves` para `attributes` em cada produto). Nenhuma no
Offerman. A do Backstage fica para a F3. Pré-go-live: sem alias, sem nome antigo.

## B.I.: o padrão novo, sem perder a inferência (F3, adiada)

Quando um leitor pedir, a inferência de salão × balcão passa a ler `papel_consumo` do produto (via
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

- Admin do `shop`: CRUD de `AttributeDefinition` (Unfold canônico).
- Painel do produto no Gestor: os atributos aparecem como campos tipados (escolha,
  múltipla, número), com o assist de IA propondo valor e marcando `source: ai`;
  o gestor aprova. É o mesmo assist que hoje escreve descrição.
- O Admin lista produtos com atributo obrigatório em branco.

## Fases

| Fase | Entrega | Gate |
|---|---|---|
| F1 | `shop.AttributeDefinition` + `shop/services/attributes.py` + migração dos três legados de metadata + leitores atualizados + seed + Admin; `natureza`, `sabor` e `temperatura` com carga derivada das coleções; painel do produto com assist | `make test` verde; PDP, rótulo e catálogo idênticos antes e depois. É a F1 do [WP-SUGESTÃO](WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md) |
| F2 | feed do Google Merchant / Meta lendo os atributos com `purposes: feed`; filtros da loja por atributo | quando o feed voltar à fila |
| F3 (adiada) | `papel_consumo` como atributo; `HistoricalConsumptionTag`; inferência do B.I. lendo o padrão novo; tabelas antigas apagadas | só com um leitor que ganhe com isso; relatórios do B.I. com os mesmos números antes e depois |

## Análise adversarial (04/09/2026)

Perguntas do dono: "podemos/devemos fazer essa alteração no Core? merece o esforço?"

- **Core:** não precisa. Definição é configuração (`shop`); valor é `metadata`
  (já existe). O desenho anterior punha a tabela no Offerman por afinidade de
  domínio, não por necessidade; a regra da casa vence.
- **Peso em JSON:** troca integridade por uniformidade e mexe em oito arquivos
  para ganhar nada. Fica coluna, definido no registro.
- **B.I. agora:** risco nos números da inferência sem leitor que ganhe. Adiado.
- **Vale o esforço:** sim, no recorte da F1 (1 a 2 dias): consolida quatro
  chaves soltas, destrava o motor de sugestão e o feed, e não toca no Core.
- **Quando:** depois do piloto do concierge, antes de religar a sugestão de
  adicional, atrás dos bloqueadores de go-live.

## Referências

- [WP-SUGESTÃO](WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md) (consome `natureza`, `sabor`, `peso_unidade_g`)
- `docs/reference/data-schemas.md` (as chaves de `Product.metadata` que saem e a que entra)
- `shopman/backstage/models/consumption.py`, `packages/offerman/.../models/product.py`
