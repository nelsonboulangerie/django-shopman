# ADR-027 — Inventário de receitas: autoria versionada separada da ficha de execução

**Status:** Aceito
**Data:** 2026-09-03
**Escopo:** `craftsman` (`RecipeEntry`, `RecipeVersion`, `contrib/formula/percentages.py`), orquestrador (`backstage/services/recipe_*`, `projections/recipe_book.py`, `api/recipe_book.py`) e a superfície Produção (`surfaces/production-nuxt`)
**Plano:** [RECIPE-INVENTORY-PLAN](../plans/completed/RECIPE-INVENTORY-PLAN.md)
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
3. **A fórmula tem uma coleção única de ingredientes.** `formula.ingredients` contém tanto
   insumos simples quanto ingredientes produzidos por outra receita. “Prep” é apenas o
   jargão para um ingrediente que possui `recipe_version_ref`; não é tipo, coleção ou regra
   matemática. A participação congela a versão usada, portanto publicar uma nova versão da
   receita do ingrediente não altera fórmulas já publicadas.
4. **Quantidade é alvo dentro de limites.** Toda participação declara `target` e pode
   declarar `minimum` e `maximum`, com a invariante
   `0 <= minimum <= target <= maximum`. Exata, mínima, máxima e faixa são apenas presets de
   autoria dessa mesma estrutura, nunca modos persistidos. A execução procura a quantidade
   viável mais próxima do alvo e congela a quantidade efetivamente usada.
5. **Composição é `additional` ou `included`.** A composição adicional aumenta a fórmula.
   A composição inclusa redistribui ingredientes já declarados na fórmula global; mistura
   final e BOM são sempre derivadas. A operação interna é alocação, mas `allocated` não é
   vocabulário do domínio nem se confunde com reserva de estoque.
6. **A receita sugere; a receita-alvo decide.** A receita de um ingrediente pode oferecer
   padrões de quantidade e composição. Ao inseri-lo, esses valores são copiados para a
   receita-alvo e podem ser alterados ali. Não existe vínculo vivo nem atualização
   retroativa do uso.
7. **A lente de padaria vem do conteúdo, não de um modo.** Não há "modo padaria": a
   receita que tem farinha ganha âncora `flour` e as métricas do padeiro; a que não tem
   ganha âncora `total` ou um ingrediente-âncora. Uma tela, painéis condicionais.
8. **A matemática é pura e mora na vertical de panificação** (`contrib/formula/percentages.py`,
   ADR-011): sem Django, só `Decimal`, testada isolada. O orquestrador só formata.
9. **A `WorkOrder` carrega a versão executada** (`_recipe_snapshot.version_ref`), então o
   B.I. cruza fornada × versão sem tabela nova.
10. **Referências de literatura são ajuda, não gate.** A tela mostra a faixa e marca "fora
   da faixa"; nunca recusa. O padeiro decide.
11. **Desvio autorizado não reescreve a receita.** Quantidade fora dos limites interrompe a
    execução comum, mas gerente ou dono pode autorizar o desvio com motivo. A execução
    guarda alvo, quantidade real, autor, data, impacto e lotes; o motor recalcula pela
    quantidade e composição reais. Inconsistência física, lote bloqueado ou trava sanitária
    continuam não autorizáveis.
12. **Massa velha é estoque, não um tipo de fórmula.** “Registrar massa velha” cria um lote
    como “Massa velha de Pão Francês”, com quantidade, validade, origem na produção e
    fotografia da composição executada. A receita a usa como qualquer ingrediente, em
    geral com quantidade máxima e composição inclusa. O lote material encerra a explosão
    da BOM e não cria referência recursiva à receita atual.

## Consequências

**Positivas** — a ficha de execução fica intocada e continua sagrada; rascunho e receita
sem SKU não vazam para planejamento nem para o estoque; versão é história com origem
(emenda D11, 01/10/2026: o dono decidiu que "o padeiro pode fazer o que quiser", e versão
publicada ou substituída se edita e se apaga como qualquer registro; publicar continua sendo
o único escritor da ficha, e a impressão digital continua denunciando a ficha fora de
sincronia); a matemática tem um dono e um teste; a superfície não faz conta.

**Negativas** — dois modelos para "receita" exigem disciplina de vocabulário (na tela:
**receita** = entry, **versão** = version, **ficha** = Recipe de execução); a ficha e a
versão publicada podem divergir se alguém editar a `Recipe` pelo Admin — o `version_ref`
sozinho não denuncia (o Admin não mexe nele); a impressão digital do conteúdo, guardada na
versão ao publicar, pega (a projection expõe `execution_in_sync` desde 30/09/2026); o cofre
(`export_backup`) carrega os modelos novos desde o PR #1303.

## Fora desta decisão

Admin/Unfold para os modelos novos e cofre. Estão listados no plano como pendências
explícitas.
