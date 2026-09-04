# WP-ATRIBUTOS-RENAME — as três chaves legadas mudam de casa, e o Core vai junto

> Estado: **aberto (2026-09-04), pedido pelo dono no mesmo dia — "já precisa fazer
> o WP dedicado o quanto antes"**.
> Nasce da F1 do [WP-ATRIBUTOS](WP-ATRIBUTOS-DE-PRODUTO.md), que entregou o
> registro apontando para as chaves onde os valores já moram. Este WP move os
> valores e apaga os nomes antigos.

## O que a F1 deixou pendente, e por quê

A F1 tinha duas decisões do dono que colidiam:

- **decisão 3** — "`allergens`, `dietary_info` e `serves` migram para atributos
  definidos, com migração de dados e TODOS os leitores atualizados. Os nomes
  antigos somem."
- **gate de aceite** — "nenhum arquivo de `packages/*` modificado nesta fase."

Elas colidem porque **quem escreve essas três chaves é o Core**: o
`ProductAdminForm` do Offerman
(`packages/offerman/shopman/offerman/contrib/admin_unfold/nutrition_form.py`) é o
editor vivo do rótulo, e lê e grava `metadata["allergens"]`,
`metadata["dietary_info"]`, `metadata["serves"]` e `metadata["dietary_auto_filled"]`.
Mover as chaves sem tocá-lo deixaria o formulário lendo vazio — um editor de
rótulo que não mostra os alérgenos que estão gravados.

Decisão do dono (04/09): **ponteiro agora, rename depois, e o rename o quanto
antes.** A F1 declarou os três atributos com `storage: "metadata:<chave>"`, do
mesmo jeito que `peso_unidade_g` aponta para `column:unit_weight_g`. Nada se
moveu, nenhum leitor mudou, o gate do rótulo passou por construção.

## O que este WP faz

| Hoje (pós-F1) | Depois |
|---|---|
| `alergenos` → `storage: metadata:allergens`, tipo `multi_text` | `storage: attributes`, tipo `multi_choice` com a lista canônica |
| `dieta` → `storage: metadata:dietary_info`, tipo `multi_text` | `storage: attributes`, tipo `multi_choice` |
| `porcoes` → `storage: metadata:serves` | `storage: attributes` |
| `metadata["dietary_auto_filled"]` (sentinela própria) | proveniência do registro (`source="recipe"`, `reviewed`) |

A mudança de tipo é a parte que **só este WP pode fazer**. Hoje `alergenos` e
`dieta` são `multi_text` (lista de termos livres) porque o registro não controla
a escrita delas: o formulário do Offerman entrega texto separado por vírgula, e
declarar uma lista fechada seria o registro prometer uma restrição que ele não
tem como aplicar. Quando o editor passar a ser o registro, a lista fechada
passa a valer — e aí "glutén" digitado errado é recusado na hora, em vez de
virar um alérgeno novo em silêncio.

## Escopo, arquivo por arquivo

**Core (`packages/*`) — o que este WP autoriza tocar:**

- `offerman/contrib/admin_unfold/nutrition_form.py` — os campos
  `allergens_text` / `dietary_info_text` / `serves_text` passam a ler e gravar
  pelo service de atributos, e `dietary_auto_filled` sai.
- `offerman/tests/test_admin_nutrition.py`, `test_service.py`, `test_v2.py` — o
  que asserta as chaves antigas.
- ⚠️ `craftsman/dietary.py` e o admin do Craftsman **ficam fora**: o
  `allergens` de lá é `RecipeItem.meta`, fato por INSUMO. Nome igual, coisa
  diferente — é de onde o `dietary_from_recipe` deriva o do produto.

**Orquestrador e superfícies:**

- `shop/services/dietary_from_recipe.py` — escreve pelo service, e a decisão de
  não sobrescrever passa a ler proveniência em vez de `dietary_auto_filled`.
- `shop/services/nutrition_from_recipe.py`, `backstage/services/catalog.py`
  (o `_DETAIL_META_LIST_FIELDS` e o PATCH do painel do produto).
- `storefront/presentation/catalog.py`, `product_detail.py`, `dietary.py`.
- `config/management/commands/seed.py` — os ~90 produtos com `allergens`.
- `surfaces/orders-nuxt` (`CatalogProductPanel.vue`, `types/catalog.ts`) e
  `surfaces/storefront-nuxt` (`types/shopman.ts`, `presentation/menu.ts`,
  `ProductTile.vue`, `pages/produto/[sku].vue`) — o contrato de API muda, então
  BE e FE mudam no mesmo PR (é a regra das chaves de projection).

**Migração de dados:** uma em `shop`, movendo os três valores de cada produto
para `metadata["attributes"]` com `source` derivado de `dietary_auto_filled`
(True → `recipe`, False/ausente → `manual`), e apagando as chaves antigas.
Reversível.

## Gate de aceite

- PDP, rótulo, catálogo e ficha nutricional **idênticos antes e depois**,
  comparados em teste — não no olho. É o mesmo gate da F1, e agora ele tem
  trabalho de verdade a fazer.
- Nenhuma ocorrência de `allergens`, `dietary_info`, `serves` ou
  `dietary_auto_filled` sobre `Product.metadata` em lugar nenhum do repositório
  (o `RecipeItem.meta` do Craftsman continua, e é intencional).
- Alérgeno fora da lista canônica é **recusado** no Admin, com mensagem.
- `make test`, `make admin`, `ruff` verdes.

## Ordem

Depois da F1 inteira (#510, #511, #512) e **antes** de o feed de catálogo (F2 do
WP-ATRIBUTOS) começar a ler atributos: o feed vai citar `alergenos` e `dieta`, e
é melhor que ele nasça lendo o nome definitivo.

## Referências

- [WP-ATRIBUTOS](WP-ATRIBUTOS-DE-PRODUTO.md) · [WP-SUGESTÃO](WP-SUGESTAO-ADICIONAL-E-SUBSTITUTO.md)
- `shopman/shop/models/attributes.py` (o `storage` e o porquê dos três modos)
- `shopman/shop/services/attributes.py` (a nota sobre `dietary_auto_filled`)
- [ADR-015](../decisions/adr-015-backward-compat-policy-post-prod.md) — pré-go-live,
  rename zera o nome antigo; depois do go-live seria expand-contract
