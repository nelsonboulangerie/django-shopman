# ADR-027 — Inventário de receitas: autoria versionada separada da ficha de execução

**Status:** Aceito (2026-09-03)
**Data:** 2026-09-03
**Escopo:** `craftsman` (`RecipeEntry`, `RecipeVersion`, `contrib/formula/percentages.py`), orquestrador (`backstage/services/recipe_*`, `projections/recipe_book.py`, `api/recipe_book.py`) e a superfície Produção (`surfaces/production-nuxt`)
**Plano:** [RECIPE-INVENTORY-PLAN](../plans/RECIPE-INVENTORY-PLAN.md)
**Refina:** [ADR-008](adr-008-pdp-nutrition.md) (Recipe é fonte do PDP), [ADR-011](adr-011-formula-and-cashshift.md) (`contrib/formula` é a vertical de panificação), [ADR-014](adr-014-surface-data-presentation-cut.md) (projection de dado vs presentation)

---

## Contexto

A `Recipe` do Craftsman é a **ficha de execução**: o BOM que `craft.plan` congela na
`WorkOrder`, que `finish` escala pelo coeficiente, que o `contrib/stockman` debita do
ledger e que a nutrição e os alérgenos do PDP leem. É uma por SKU, estável, e todo o
sistema depende disso.

O dono pediu algo que a ficha de execução não é: um **inventário de receitas** onde entrar
uma receita é barato (anotação, foto em qualquer língua, ou à mão), onde qualquer receita
pode ser convertida para o **padrão da casa (1000 g de farinhas totais)** guardando o que
foi informado como referência, onde receitas se **comparam**, onde uma receita pode ou não
estar **associada a um SKU** (e, quando está, é "a atual"), e onde a **evolução** de cada
receita fica registrada para cruzar com o B.I.

Duas opções foram consideradas:

1. **Esticar a `Recipe`** para virar também o modelo de autoria (rascunhos, versões,
   receitas sem SKU, quantidades originais). Cada consulta que hoje pergunta "ficha ativa do
   SKU" passaria a precisar filtrar rascunho, versão velha e receita-só-conhecimento;
   `craft.suggest` considera toda ficha ativa; o `ref` único por versão quebraria
   relatórios, códigos cegos e o seed por `ref`.
2. **Um aggregate de autoria ao lado**, cujo único caminho para a execução é **publicar**.

## Decisão

1. **Autoria e execução são dois modelos.** `RecipeEntry` (a receita, com sua linhagem,
   `kind`, associação opcional a SKU) e `RecipeVersion` (uma fórmula congelada, com
   `status` draft → published → superseded, `origin` imutável com o que foi informado, e
   `source` dizendo de onde veio) vivem no Craftsman, ao lado da `Recipe`. A `Recipe`
   não muda de significado.
2. **Publicar é o único escritor.** `publish_version` faz upsert da `Recipe(ref=entry.ref)`
   com o BOM derivado, preserva o `RecipeItem.meta` dos insumos que já existiam (é onde
   moram alérgenos, nutrição e densidade), desativa outra ficha ativa do mesmo SKU e
   carimba `Recipe.meta["version_ref"]`. A ficha continua **uma por SKU e com `ref`
   estável**: nada que hoje aponta por `ref` precisa mudar.
3. **A fórmula é base-first** (modelo do dono, BBGA/Hamelman): `formula.items` é a receita
   total com toda a farinha, `formula.parts` diz quanto passa por levain/autólise/yudane,
   e a **mistura final e o BOM são derivados**, nunca digitados. É isso que evita a dupla
   contagem da farinha quando a parte tem ordem de produção própria.
4. **A lente de padaria vem do conteúdo, não de um modo.** Não há "modo padaria": a
   receita que tem farinha ganha âncora `flour` e as métricas do padeiro; a que não tem
   ganha âncora `total` ou um ingrediente-âncora. Uma tela, painéis condicionais.
5. **A matemática é pura e mora na vertical de panificação** (`contrib/formula/percentages.py`,
   ADR-011): sem Django, só `Decimal`, testada isolada. O orquestrador só formata.
6. **A `WorkOrder` carrega a versão executada** (`_recipe_snapshot.version_ref`), então o
   B.I. cruza fornada × versão sem tabela nova.
7. **Referências de literatura são ajuda, não gate.** A tela mostra a faixa e marca "fora
   da faixa"; nunca recusa. O padeiro decide.

## Consequências

**Positivas** — a ficha de execução fica intocada e continua sagrada; rascunho e receita
sem SKU não vazam para planejamento nem para o estoque; versão é história de verdade
(imutável, com origem); a matemática tem um dono e um teste; a superfície não faz conta.

**Negativas** — dois modelos para "receita" exigem disciplina de vocabulário (na tela:
**receita** = entry, **versão** = version, **ficha** = Recipe de execução); a ficha e a
versão publicada podem divergir se alguém editar a `Recipe` pelo Admin — o `version_ref`
denuncia (a projection expõe se a ficha está em sincronia); o cofre (`export_backup`)
ainda não carrega os modelos novos.

## Fora desta decisão

Saldo de massa velha do dia no planejamento; Admin/Unfold para os modelos novos; cofre.
Estão listados no plano como pendências explícitas.
