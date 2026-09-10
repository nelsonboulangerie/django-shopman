# ADR-008: Ingredientes e informação nutricional no PDP — Product é superfície, Recipe é fonte opcional

**Status:** Aceito
**Data:** 2026-04-17
**Contexto:** O storefront precisa exibir "Ingredientes" e "Informações Nutricionais" no PDP. Havia dúvida entre armazenar em `Offerman.Product` (simples, duplica) ou derivar em tempo real de `Craftsman.Recipe` (fonte única, caro). Referência: [`do../plans/completed/PDP-DATA-FIELDS-PLAN.md`](../plans/completed/PDP-DATA-FIELDS-PLAN.md).

---

## Contexto

Dois domínios são legítimos candidatos a segurar esses dados:

- **Offerman.Product** — a superfície vendável, o que o storefront já consulta.
- **Craftsman.Recipe / RecipeItem** — a ficha técnica de produção; ingredientes moram aqui naturalmente como `RecipeItem.input_ref`.

Cada alternativa pura é frágil:

- **Só em Product:** duplica informação e abre caminho para divergência quando a receita muda. Obriga operador a manter dois pontos de verdade.
- **Só derivado de Recipe on-read:** computação cara no hot path do PDP, não cobre produtos **revendidos** (sem receita) e exige que a projeção conheça o domínio de produção.

Há também um terceiro sujeito silencioso: **bundles**. Um combo não tem receita própria — sua composição é a soma das partes. Derivar nutricional de bundle é cirurgicamente difícil de acertar (porções diferentes, unidades diferentes, contaminação cruzada) e errar rotulagem alimentar é risco regulatório.

## Decisão

**Híbrido, com Product como superfície e derivação materializada opcional.**

1. `Offerman.Product` ganha dois campos de **dado final, já pronto para exibir**:
   - `ingredients_text` (`TextField`, blank=True) — lista humana pt-BR, ordem decrescente de peso (hoje coberta pela RDC 727/2022).
   - `nutrition_facts` (`JSONField`, blank=True, default=dict) — dict serializado de um `dataclass NutritionFacts` frozen.

2. A projeção `ProductDetailProjection` consome **só esses dois campos**. Ingrediente e nutricional nunca são computados em tempo de request. O PDP é uma leitura fria.

3. Produtos **com** Recipe ativa têm derivação opt-in, materializada em escrita:
   - Service `shopman.shop.services.nutrition_from_recipe.fill_nutrition_from_recipe(product)` lê a receita ativa (`Recipe.output_ref == product.sku`, `is_active=True`), soma o perfil nutricional de cada `RecipeItem` (armazenado em `RecipeItem.meta["nutrition"]`), gera `ingredients_text` a partir de `RecipeItem.meta["label"]` em ordem decrescente de peso, e escreve de volta em `Product`.
   - Signal `post_save` em `Recipe` dispara o service após o save da receita.
   - Um flag `nutrition_facts["auto_filled"]` distingue valores derivados de override manual — o service só sobrescreve se o valor atual **não** for `auto_filled=False`.
   - Management command `fill_nutrition_from_recipe` faz backfill em lote.

4. Produtos **sem** Recipe (revendidos, combos, bebidas) são editáveis direto no admin com um form Unfold dedicado, um campo por nutriente, agrupado em fieldsets ("Porção", "Macronutrientes", "Micronutrientes"). JSON raw nunca aparece no admin.

5. **Bundles ficam de fora da derivação.** Produtos `is_bundle=True` não têm receita associada e a soma aritmética de nutricional de componentes é frágil demais para rotulagem alimentar — preferimos **nada** a **errado**. Se o operador quiser rotular nutricionalmente um combo, preenche manualmente no admin.

6. `Product.clean()` valida invariantes ANVISA estruturais:
   - Se **qualquer** campo nutricional está presente, `serving_size_g` é obrigatório.
   - Todos os campos numéricos são ≥ 0.
   - `trans_fat_g ≤ total_fat_g`, `saturated_fat_g ≤ total_fat_g`, `sugars_g ≤ carbohydrates_g`.

## O teste diagnóstico

Quando um campo novo de exibição precisa morar em Product vs derivar de Recipe:

| Sinal | Resposta |
|---|---|
| Precisa renderizar sem tocar outro domínio | Product carrega o dado final |
| Dados estruturais (BOM, quantidades, receita) que já moram em Recipe | Recipe continua dona |
| Derivação tem custo e é escrita rara | Materialize no Product via signal em Recipe |
| Produtos sem receita também precisam do campo | Product ganha o campo, com derivação opt-in |

`ingredients_text` + `nutrition_facts` satisfazem todos os sinais.

## Consequências

### Positivas

- **Leitura fria no PDP.** Projeção nunca importa `craftsman`.
- **Uma fonte de verdade por produto:** ou o operador edita (manual) ou a Recipe edita via signal. Flag `auto_filled` evita stomp.
- **Compatível com revendidos/bebidas/combos.** Não exige receita para ter rotulagem.
- **Compatível com operador que não usa Recipe.** Basta preencher no admin.
- **Rotulagem alimentar correta por padrão.** Bundle não alucina nutricional.

### Negativas

- **Dois pontos de verdade potenciais** para produtos com receita: se o operador edita a Recipe e também manualmente o Product, o flag `auto_filled=False` bloqueia sobrescrita — o operador precisa **saber** disso. Mitigação: admin expõe um toggle "derivado da receita" (próximo WP, não agora) e a história é visível em `HistoricalRecords`.
- **Soma nutricional correta depende da qualidade de `RecipeItem.meta["nutrition"]`.** Se o operador não preenche o perfil do insumo, o service gera `{}`. Isso é OK — vazio é melhor que chute.

### Mitigações

- Esta ADR existe.
- `Product.clean()` bloqueia estados incoerentes (campos sem `serving_size_g`, trans > total).
- Signal é idempotente (`auto_filled=True` é o único sinal verde para sobrescrita).
- Management command `fill_nutrition_from_recipe` permite backfill controlado.

## Alternativas consideradas

### A. Campo direto em Product, sem derivação automática

Rejeitada. Força o operador a manter rotulagem nutricional em dois pontos (Recipe para BOM, Product para PDP). Divergência inevitável em produção.

### B. Derivação on-read na projeção

Rejeitada. Custo de I/O no hot path do PDP, não cobre revendidos, e obriga a projeção a importar Craftsman — quebra a fronteira de domínio.

### C. Insumo como entidade (novo modelo Stockman.Ingredient)

Rejeitada **por ora**. `RecipeItem.input_ref` é string ref hoje; `RecipeItem.meta` é JSON extensível. Guardar o perfil nutricional do insumo em `meta["nutrition"]` resolve o problema sem migração de modelo novo. Se o domínio pedir um Ingredient first-class depois (fornecedor, lote, rotulagem regulatória própria), abre-se outro ADR.

### D. Cálculo nutricional para bundles

Rejeitada. Rotulagem alimentar errada é risco regulatório; preferimos deixar vazio.

## Adendo (2026-06-17): alérgenos/dieta também derivam da Recipe/BOM (WP-7)

A ADR original adiou o eixo dietético de propósito (nutrientes são soma aritmética; alérgenos são
**união** e exigem flags por insumo + UI). O WP-7 fecha essa lacuna espelhando o desenho da nutrição:

- `RecipeItem.meta` ganha o schema dietético via dataclass `shopman.craftsman.dietary.IngredientDietary`
  (`allergens` que o insumo **contém** + `diet` ∈ {vegan, vegetarian, animal}). Sem migração (JSONField).
- `shopman.shop.services.dietary_from_recipe.aggregate_dietary_from_recipe(product)` faz **união** de
  alérgenos e resolve a dieta: "100% vegetal" só se **todos** os insumos vegan; "vegetariano" se
  **nenhum** animal; "sem glúten"/"sem lactose" se **nenhum** insumo dispara. Grava em
  `Product.metadata['allergens']`/`['dietary_info']` (tokens que o filtro de preferências do storefront
  entende) com sentinel `metadata['dietary_auto_filled']` espelhando `nutrition_facts['auto_filled']`.
- **Segurança de rotulagem:** só materializa quando **todos** os insumos do BOM declaram perfil
  dietético. Um insumo não declarado torna o produto um no-op (allergen incompleto é perigoso) —
  mais rígido que o "vazio melhor que chute" da nutrição.
- O signal `post_save` em Recipe é o mesmo (`_connect_recipe_derivation_signal`): nutrição + dieta.
- Bundles continuam de fora (mesma razão do nutricional).

A expansão recursiva do BOM (cycle-detection, itens opcionais) foi extraída para
`shopman.shop.services.recipe_bom.expand_recipe_items`, compartilhada pelas duas derivações.

## Adendo (2026-09-05): a derivação carimba a versão, e o peso entra na família (WP-FICHA-DE-PRODUTO-E-PROMESSA, blocos C e D)

A ADR original resolveu **onde** o dado mora e **quem** pode escrevê-lo. Faltava a
terceira pergunta, que o dono fez em 05/09: *"nutricional e tudo o mais que apareça no
catálogo mas seja relativo ou derivado da receita do produto deve ter uma relação
estabelecida, para manter tudo sempre atualizado e sem falsa promessa para o cliente."*
Até aqui a derivação acontecia e não deixava rastro: publicada uma versão nova da ficha,
o PDP seguia mostrando o número velho com cara de atual.

- **Carimbo de origem.** Toda derivação grava
  `Product.metadata["derived_from"][<fato>] = {source, recipe_ref, version_ref, by, at}`
  (`shop.services.derived_provenance`). O `version_ref` sai de `Recipe.meta["version_ref"]`,
  que o inventário já escreve ao publicar (ADR-026).
- **Vencido é comparação exata**, nunca heurística: versão de origem gravada ≠ versão atual
  da ficha. Sem limiar, sem tolerância, sem data — data sabe que o tempo passou, não que a
  ficha andou.
- **Ficha sem versão não ganha número inventado.** Ficha nascida no seed ou no Admin nunca
  passou por `publish_version`; o carimbo dela é `""`, a mesma string que o snapshot da
  WorkOrder já usa para dizer isto. Vazio contra vazio não vence, e a leitura marca
  `is_versioned=False` — dizer "em dia" ali seria prometer um frescor que ninguém pode
  conferir.
- **Override manual continua sagrado, e agora envelhece.** `auto_filled=False` e
  `dietary_auto_filled=False` seguem bloqueando o recálculo. O que mudou é que o valor
  manual pode ser **assinado** (`record_manual_audit`, com autor e data, como as conversões
  de insumo da ADR-024) e, quando a ficha anda, ele é **reportado como vencido** para alguém
  reconferir — sem nunca ser recalculado.
- **O peso da peça vira o quarto fato derivado** (`shop.services.unit_weight_from_recipe`),
  e é **piso, não média**: `⌊(cru por unidade × (1 − perda de forno)) × (1 − folga)⌋`,
  arredondando sempre para baixo. A perda de forno é declarada por ficha; o padrão de 12%
  da casa sai rotulado `house_default`, estimativa nunca auditada. Peso posto à mão jamais é
  sobrescrito — o sentinela é o próprio carimbo, e a divergência aparece na leitura.
- **A leitura** é `backstage.projections.product_promise` (`api/v1/backstage/catalog/promise/`):
  por fato, o valor publicado, a origem, a versão, a defasagem e quem conferiu.

## Referências

- [`do../plans/completed/PDP-DATA-FIELDS-PLAN.md`](../plans/completed/PDP-DATA-FIELDS-PLAN.md)
- [`packages/offerman/shopman/offerman/nutrition.py`](../../packages/offerman/shopman/offerman/nutrition.py) — dataclass `NutritionFacts`
- [`shopman/shop/services/nutrition_from_recipe.py`](../../shopman/shop/services/nutrition_from_recipe.py) — derivação
- [`shopman/shop/projections/product_detail.py`](../../shopman/shop/projections/product_detail.py) — leitura
- **Nota de atualização (2026-09-10):** a RDC 360/2003 foi substituída. O
  schema desta ADR continua sendo uma projeção legada de PDP, não um contrato
  completo de rótulo comercial. A norma vigente de informação nutricional é a
  RDC 429/2020 com a IN 75/2020; ver ADR-028.
