# 05 — Receitas: estrutura (modo de fazer e anotações práticas)

> Diagnóstico de estrutura. Perguntas do dono: (a) o sistema aceita **registro de procedimento,
> modo de fazer**? (b) existem **campos para anotações práticas internas**, e em que nível
> (global / item / parte / etapa)?
> Árvore: `/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration`
> (branch `dsh/handoff-onda1-e-p7-20260930`, 3 commits à frente de `origin/main`; `git log --oneline origin/main..HEAD`
> = `387048c44`, `22706a75c`, `abd4d8bf3`). Nada foi editado além deste arquivo.
> **Report irmão:** `06-receitas-ciclo-de-vida.md` cobre versionamento, anexos, avaliação e
> reputação. Este aqui não repete aquilo; onde os dois tocam, eu aponto.

## 0. Veredito em cinco linhas

1. **Existe UM lugar para "modo de fazer": sim, e é raso.** `Recipe.steps` é `JSONField(list)` de
   **strings soltas** (`packages/craftsman/shopman/craftsman/models/recipe.py:64`). Não tem texto
   longo, não tem tempo, não tem temperatura, não tem ordem executável, não tem responsável.
2. **Nenhum operador vê o procedimento.** Nem o KDS, nem a Preparação/pesagem, nem a etiqueta
   impressa, nem o board. O único consumidor de `steps` é uma linha que copia a lista para dentro
   de um snapshot que **ninguém lê** (`services/scheduling.py:83` → `_recipe_snapshot.production.steps`).
3. **O sistema já declara essa lacuna em texto.** `shopman/backstage/data_readiness/operational.py:202-210`
   emite o achado `missing_steps` com a mensagem *"Ficha executável existe, mas o modo de preparo
   não está registrado."* — mas só o comando de auditoria `audit_recipe_material_day1` o lê. Nenhuma tela.
4. **Anotações práticas existem em 3 dos 4 níveis pedidos**, todos **na camada de autoria**
   (inventário), nenhum na **ficha de execução**: receita (`RecipeEntry.notes`), versão
   (`RecipeVersion.notes`), linha de ingrediente (`RecipeItem.meta`). **Não existe nível "etapa"** —
   a etapa é string, não tem onde pendurar nota. E `Recipe`/ficha de execução **não tem campo de
   texto nenhum**.
5. **Tamanho do menor acréscimo coerente: P para "procedimento legível", M para "procedimento
   executável com tempos".** Nada de modelo novo; é `JSONField` que já existe, ganhando estrutura
   e **um leitor** — porque hoje o problema maior não é o campo, é que ninguém o lê.

---

## 1. Inventário: os modelos e os campos, com nome exato

### 1.1 `Recipe` — a **ficha de execução** (o BOM) [FATO]

`packages/craftsman/shopman/craftsman/models/recipe.py:31` — `class Recipe(models.Model)`.
Campos, um a um, com a linha:

| Campo | Tipo | Linha | Observação |
|---|---|---|---|
| `ref` | SlugField(unique, 50) | `recipe.py:41` | |
| `name` | CharField(200) | `recipe.py:47` | |
| `output_sku` | RefField("SKU") | `recipe.py:51` | |
| `batch_size` | Decimal(12,3) | `recipe.py:57` | rendimento base; escalonamento |
| **`steps`** | **JSONField(list)** | **`recipe.py:64`** | `help_text='Etapas de produção. Ex: ["Mistura", "Fermentação", "Modelagem", "Forno"]'` |
| `is_active` | Boolean | `recipe.py:70` | |
| `meta` | JSONField(dict) | `recipe.py:74` | `help_text` cita `prep_time_min`, `bake_temp_c` |
| `created_at` / `updated_at` | DateTime | `recipe.py:80` / `:84` | |

**Não existe `Recipe.notes`. Não existe `Recipe.instructions`. Não existe `Recipe.method`.** [FATO —
a lista acima é o modelo inteiro, `recipe.py:41-87`]

A validação de `steps` é só forma: precisa ser lista, e cada elemento string não vazia
(`recipe.py:117-124`). Aceita `["Mistura", "Forno"]` e aceita `["faz a massa", "assar"]` —
não distingue nome de etapa de instrução.

O `help_text` do `meta` (`recipe.py:78`) sugere `prep_time_min` e `bake_temp_c`. **Nenhum código de
produção escreve ou lê essas duas chaves** — elas só aparecem em doc e em um teste que usa
`prep_time_min` como chave arbitrária (detalhe e evidências em §7.3). São isca de documentação.

### 1.2 `RecipeItem` — a **linha de ingrediente** [FATO]

`recipe.py:216`. Campos: `recipe`(`:237`), `input_sku`(`:243`), `quantity`(`:250`),
`usable_factor`(`:260`), `unit`(`:273`), `sort_order`(`:280`), `is_optional`(`:284`),
`meta` — **JSONField** (`recipe.py:289`).

**Não existe `RecipeItem.notes`.** O nível "linha" só tem o `meta`, cujo inventário canônico está
em `docs/reference/data-schemas.md:1558-1566`: `allergens`, `diet`, `nutrition`,
`density_g_per_ml`, `role`, `cap_pct`. **Nenhuma chave de anotação livre está registrada lá.** [FATO]

### 1.3 `RecipeEntry` — a **receita** do inventário (autoria) [FATO]

`packages/craftsman/shopman/craftsman/models/recipe_book.py:18`. Campos: `ref`(`:32`),
`name`(`:38`), `kind`(`:39`, 9 tipos: bread…other), `output_sku`(`:45`),
**`notes` = `models.TextField(blank=True, default="")`** (`recipe_book.py:53`),
`is_archived`(`:54`), `current_version`(`:55`), `meta`(`:64`), timestamps(`:65-66`).

### 1.4 `RecipeVersion` — a **versão congelada** (autoria) [FATO]

`recipe_book.py:82`. `number`(`:103`), `status` draft/published/superseded (`:104`),
`label` — *"O que mudou"* (`:110`), `yield_quantity`(`:116`), `yield_unit`(`:123`),
`formula` JSONField (`:130`), `origin` JSONField (`:131`), `source` JSONField (`:137`),
**`steps` JSONField(list)** (`recipe_book.py:143`), **`notes` TextField** (`recipe_book.py:144`),
`created_by`(`:145`), `published_at`(`:147`), `meta`(`:148`).

Validação de `steps` aqui é ainda mais frouxa que na `Recipe`: só `isinstance(list)`
(`recipe_book.py:172-173`) — **nem o tipo dos elementos é checado**.

### 1.5 O schema da fórmula — onde mora a estrutura fina [FATO]

`docs/plans/RECIPE-INVENTORY-PLAN.md:89-131` (schema §3) e o validador real em
`packages/craftsman/shopman/craftsman/contrib/formula/percentages.py:902` (`validate_formula`).
Vocabulário fechado em `percentages.py:36-39`:

- `ROLES` (`:36`): flour, liquid, salt, yeast, fat, sugar, egg, dairy, inclusion, other;
- `ANCHOR_KINDS` (`:37`): flour, total, ingredient;
- `PART_KINDS` (`:38`): **preferment, autolyse, soaker, old_dough**;
- `UNITS` (`:39`): g, kg, mg, ml, L, un.

O item da fórmula **tem campo de anotação**: `{"sku","name","role","quantity","unit","note"}`
— `RECIPE-INVENTORY-PLAN.md:97` e `docs/reference/data-schemas.md:1572` (`note?`).

`validate_formula` (`percentages.py:902-981`) **não valida, não normaliza e não propaga `note`**:
  o laço de itens (`:924-943`) confere `sku`/`name`/`role`/`quantity`/`unit`/`grams_per_unit`/
  `density_g_per_ml` — e para aí. E `note` aparece em `percentages.py` só em `_range` (`:767`, `:772`),
  que é a **nota da faixa de referência da literatura** (ex. "Sal sobre a farinha total."), outro
  conceito com o mesmo nome. `contrib/formula/service.py`: `grep -n 'note'` → **0 resultados**. [FATO]

---

## 2. Os três eixos: item, parte e etapa — nomes exatos, sem colisão

O briefing do dono fecha isto explicitamente: *"`parte`, nunca `etapa`. `Recipe.steps` já existe
e significa etapa de processo"* (`.claude/worktrees/receitas-paes-producao-26a519/docs/plans/RECIPE-MODELING-BRIEF.md:36-37`).
O código honra a separação. [FATO]

| Eixo | Nome no código | Onde mora | O que é |
|---|---|---|---|
| **Item / ingrediente** | `RecipeItem` | `recipe.py:216` | linha da fórmula; `input_sku` + `quantity` + `unit` |
| **Parte** | `formula.parts[]` → `FormulaPartProjection` | `RECIPE-INVENTORY-PLAN.md:102-106`; `percentages.py:38`; `shopman/backstage/projections/recipe_book.py:194` | pedaço da fórmula que recebe tratamento antes (levain, autólise, yudane, massa velha) |
| **Etapa de processo** | `Recipe.steps` / `RecipeVersion.steps` | `recipe.py:64` / `recipe_book.py:143` | nomes de etapa: Mistura, Fermentação, Modelagem, Forno |

**A parte não é um modelo.** No banco ela existe como JSON dentro de `RecipeVersion.formula`.
Só depois de **publicar** ela vira linha física: ou um `RecipeItem` apontando para um SKU que tem
`Recipe` própria (BOM multinível, `recipe.py:225-227`), ou o item opcional de massa velha
(`RecipeItem.meta.role="old_dough"`, `data-schemas.md:1565-1566`), ou nada — quando a parte não
tem fórmula conhecida. [FATO]

**A colisão de vocabulário que existe é outra, e é de tela.** [FATO]
- o **modelo** diz "Etapas": `verbose_name=_("Etapas")` (`recipe.py:67`, `recipe_book.py:143`);
- a **tela de edição** diz "Passos (um por linha)": `surfaces/production-nuxt/app/pages/recipes/[ref]/edit.vue:571`;
- a **tela de leitura** diz "Passos": `surfaces/production-nuxt/app/pages/recipes/[ref]/index.vue:384`;
- o **Admin** diz "Etapas": `contrib/admin_unfold/admin.py:155`;
- a **referência** diz "Passos do KDS": `docs/reference/data-schemas.md:1543`;
- os **eventos de fornada** dizem "Passo avançado": `WorkOrderEvent.Kind.STEP_ADVANCED`, `work_order_event.py:100`.

Duas palavras (etapa/passo) para o mesmo eixo, e a tela e o modelo discordam. Não quebra nada hoje
porque o campo não é lido por ninguém na operação (§3), mas é dívida de vocabulário a fechar
**antes** de construir em cima.

---

## 3. Como KDS e Produção consomem a receita hoje

### 3.1 O KDS não lê receita. Nada. [FATO]

`grep -n 'recipe|Recipe|steps|ingredient' shopman/backstage/projections/kds.py` → **0 resultados**.
O KDS trabalha em cima de `KDSTicket`/pedido, não de ficha. O `target_seconds` do KDS
(`projections/kds.py:68`) é SLA do chamado, **não** tempo de etapa da receita — o nome é coincidência.

### 3.2 A Preparação (pesagem) mostra **só quantidade** [FATO]

A projeção do ticket de pesagem é fechada e não tem campo de procedimento:
`ProductionWeighingTicketProjection` (`shopman/backstage/projections/production.py:315-343`) =
`ticket_ref, recipe_ref, output_sku, name, output_quantity_display, dough_weight_display,
total_weight_display, theoretical_total_g, target_total_g, rounding_delta_total_g, sources_display,
ingredients[], table, blind_code, made_display, expiry_display, validity_configured,
validity_source` — **zero `steps`**.
`ProductionWeighingIngredientProjection` (`:280-296`) = sku, name, quantity_display,
target_display, annotation, is_subrecipe, theoretical/target/delta g, accepted min/max. **Zero nota livre.**

A tela `surfaces/production-nuxt/app/pages/mise-en-place.vue` só desenha isso: modo "Por preparo"
(pesagem real, fonte das etiquetas cegas, `:4-5`) e "Por insumo" (agregado, `:8`). No comentário
de abertura da tela não há uma linha sobre procedimento.

### 3.3 A etiqueta impressa é identificação, não modo de fazer [FATO]

`made_display` (data prevista), `expiry_display` (validade), `blind_code` (código cego do dia que
substitui o nome da receita, `production.py:338-339`). É o que sai na bobina. **O procedimento não sai.**

### 3.4 O board e o expedite não mostram procedimento [FATO]

`grep -r 'steps' surfaces/production-nuxt/app/pages/board.vue surfaces/production-nuxt/app/pages/expedite.vue`
→ 0. O board (`board.vue:2-11`) é painel Solari de lotes: nome, quantidade, horário, cor de status.

### 3.5 Onde os `steps` aparecem na tela — só na autocracia do inventário [FATO]

As **únicas** renderizações de `steps` em toda a suíte (`surfaces/`, 9 apps + layer):

- `surfaces/production-nuxt/app/pages/recipes/[ref]/index.vue:383-389` — painel "Passos" como `<ol>`, e `:390` a versão `notes`;
- `surfaces/production-nuxt/app/pages/recipes/[ref]/edit.vue:571` — textarea "Passos (um por linha)";
- `surfaces/production-nuxt/app/pages/recipes/new.vue:438-441` — "Passos lidos" do rascunho capturado por IA.

Ou seja: **o padeiro escreve o procedimento e o gestor o lê. O chão de fábrica nunca.** A tela
`/recipes` vive no app de Produção (`hub`/kiosk), mas é a superfície de **gestor**, não a de execução.

### 3.6 A trilha de etapa existe no Core e está **morta** — com prova documental [FATO]

`CraftExecution.advance_step` (`packages/craftsman/shopman/craftsman/services/execution.py:152`)
grava `WorkOrder.meta["steps_progress"]` (`:222`), `steps_progress_actor` (`:223`),
`steps_progress_updated_at` (`:224`) e um `WorkOrderEvent.Kind.STEP_ADVANCED` (`:231`).
Tem teste (`packages/craftsman/shopman/craftsman/tests/test_vnext.py:471-494`) e idempotência.

**Zero chamadores.** O `grep -rn 'advance_step|steps_progress|STEP_ADVANCED'` em todo o repo devolve
apenas: a definição no Core, o teste, **e a documentação que já registra a morte**:

> `docs/reference/data-schemas.md:1513` — `steps_progress` | `int` | *"Ninguém no backstage (o
> escritor `CraftExecution.advance_step` segue no Core, **sem chamador de superfície desde a
> decisão de 16/09/2026: a aba Produção tem uma ação só, Continuar**)"* | Ninguém | *"Ponteiro
> manual de passo, 1-based. Legado em ordens antigas; não é lido por projection."*

Isso é a resposta mais direta à pergunta (a): **a casa já construiu o rastreio de etapa, e depois
decidiu que o operador não o usa.** Reabrir isso é decisão de produto, não de código.

### 3.7 A única "etapa de processo" que o operador registra de verdade é o forno [FATO]

`WorkOrderEvent.Kind.OVEN_ARMED` ("Enfornado", `work_order_event.py:101`) e `OVEN_CONCLUDED`
("Retirado do forno", `work_order_event.py:102`) **estão ligados e vivos**: ação `oven_arm` /
`oven_conclude` em `shopman/backstage/services/production.py:241-242`, mutação
`postProductionMutation(.../oven/arm/)` na superfície
(`surfaces/production-nuxt/app/generated/productionContract.ts:1042,1046`), composable
`surfaces/production-nuxt/app/composables/useOvenFacts.ts:47`, gatilho em
`surfaces/production-nuxt/app/pages/expedite.vue:130-132`.

Traduzindo: **o sistema sabe registrar uma etapa de processo com fato, ator e timestamp — mas só
para as duas etapas do forno, cravadas em código.** Não é genérico, e não vem da receita.
Isso é o precedente mais próximo de "procedimento executável" que a casa tem. [FATO + INFERÊNCIA
do desenho — o código não declara a intenção de generalizar]

### 3.8 A rede de segurança que ninguém vê

`shopman/backstage/data_readiness/operational.py:202-210`:

```python
if not recipe.get("steps_count"):
    findings.append(_finding(
        "missing_steps", "traceability", "decision", output_sku,
        "Ficha executável existe, mas o modo de preparo não está registrado.",
    ))
```

`steps_count` vem de `len(recipe.steps or [])` (`operational.py:72`). [FATO]

Isso é o sistema dizendo, com as palavras do dono, que **a receita não é executável
inequivocamente sem modo de preparo** — categoria `traceability`, severidade `decision`.
**Mas o único consumidor é o comando de linha de comando `audit_recipe_material_day1`**
(`shopman/backstage/management/commands/audit_recipe_material_day1.py:10`) e o teste
(`shopman/backstage/tests/test_recipe_material_day1_audit.py:8`). Não há projection, não há tela,
não há alerta. O achado nasce e morre no terminal. [FATO]

---

## 4. A trilha do `steps` quando ele existe: escreve num lugar, morre no meio

Este é o achado central para a pergunta (a), e ele é surpreendente: **o dado viaja e desemboca
num beco sem saída.** [FATO, cadeia inteira verificada linha a linha]

```
Recipe.steps (recipe.py:64)  ─┐
RecipeVersion.steps (rb:143) ─┴─► build_recipe_snapshot (scheduling.py:54)
                                   └─ snapshot["production"]["steps"]  (scheduling.py:83)
                                        └─ WorkOrder.meta["_recipe_snapshot"]  (scheduling.py:186)
                                             └─ ██ NINGUÉM LÊ ██
```

A linha exata:
```
scheduling.py:83:  "steps": list((recipe.meta or {}).get("steps") or recipe.steps or []),
```

E a prova do beco: os **dois** únicos leitores de `snapshot["production"]` no sistema inteiro
(`shopman/backstage/services/production.py:1957` e `:3580`) fazem
`recipe_meta = snapshot.get("production") or work_order.recipe.meta` e leem **apenas
`shelf_life_days`** — o `steps` que o snapshot carrega passa ao lado.

Consequências, todas verificáveis:

- `Recipe.meta["steps"]` segundo `docs/reference/data-schemas.md:1543` seria
  `list[dict]` = `[{name, target_seconds}]`, *"Escrito por seed/admin | **Lido por KDS de produção**"*.
  **A linha está errada em três pontos** [FATO]:
  1. o seed **não** escreve `meta["steps"]` — escreve `Recipe.steps` como `list[str]`
     (`config/management/commands/seed.py:5053` → `_production_steps_for_recipe` `:5787-5805`,
     que devolve `["Mistura", "Fermentação", "Modelagem", "Forno"]` e variantes, sempre strings);
  2. o Admin **não** escreve `meta["steps"]` — o campo `steps_text` grava em `instance.steps`
     (`contrib/admin_unfold/admin.py:236-242`, `fieldsets` em `:415`, `exclude=("steps","meta")` em `:202`);
  3. o KDS de produção **não lê** nada disso (`projections/kds.py` não menciona `recipe` — §3.1);
     e `target_seconds` só existe como SLA de chamado (`projections/kds.py:68`), nunca por etapa de receita.
     O `grep -rn 'target_seconds'` no repositório não encontra **um único** ponto onde uma lista de
     passos com tempo por passo seja escrita ou lida.
- O único leitor real de `Recipe.meta["steps"]` é `scheduling.py:83` — que só copia. [FATO]

**Rótulo honesto:** a doc de `Recipe.meta` (§`data-schemas.md:1543`) descreve um KDS de etapas
que **não existe no código de hoje**. É doc prospectiva que ficou parecendo fato. Corrigir essa
linha é P e deveria entrar junto com qualquer trabalho de procedimento — senão o próximo agente
constrói em cima da ficção.

---

## 5. Pergunta (b): os quatro níveis de anotação, medidos

| Nível pedido pelo dono | Existe? | Campo exato | Onde | Chega ao chão de fábrica? |
|---|---|---|---|---|
| **Global (receita)** | ✅ na autoria / ❌ na execução | `RecipeEntry.notes` TextField | `recipe_book.py:53` | ❌ (só telas `/recipes`) |
| **Global (versão)** | ✅ | `RecipeVersion.notes` TextField | `recipe_book.py:144` | ❌ |
| **Global (ficha)** | ❌ | — | — | — |
| **Por item da receita** | ⚠️ parcial | `RecipeItem.meta` JSONField | `recipe.py:289` | ❌ (nenhuma chave de nota registrada) |
| **Por item (fórmula, autoria)** | ✅ no dado / ❌ na tela | `formula.items[].note` | plano `:97`, `data-schemas.md:1572` | ❌ |
| **Por parte** | ❌ | — | `formula.parts[]` não tem `note` no schema (`plan:102-106`) | ❌ |
| **Por etapa de processo** | ❌ | — | `steps` é `list[str]`; string não tem campo | ❌ |

### 5.1 O caso mais interessante: a nota de item existe no schema e é **descartada ao publicar** [FATO]

Cadeia verificada:

1. **A captura por IA já produz a nota.** O prompt do modelo pede `"note": str` por item e explica o
   uso (`shopman/backstage/services/recipe_capture.py:77-78`, regras em `:86-88`: *"Sempre que
   converter, escreva a conversão feita em note"*; *"`q.b.`, `a gosto` … viram quantity null com a
   expressão em note"*). `CapturedItem.note` existe (`recipe_capture.py:126`).
2. **A projection do rascunho preserva.** `shopman/backstage/projections/recipe_book.py:1008-1009`:
   `if item.note: line["note"] = item.note` — a nota entra na fórmula do rascunho.
3. **A apresentação do app preserva.** `surfaces/production-nuxt/app/presentation/recipeBook.ts:153`
   (`note: ""` em `newFormulaItem`), `:313` (nota do original quando difere do nome),
   `:357` (`note: typeof raw.note === "string" ? raw.note : ""`).
4. **A tela do editor NÃO mostra e NÃO edita.** A linha de ingrediente em
   `surfaces/production-nuxt/app/pages/recipes/[ref]/edit.vue:432-500` renderiza
   nome, SKU, quantidade, unidade, papel, `grams_per_unit` — **e nada de `note`**
   (`grep -n 'note' edit.vue` só acha as notas da *versão*, `:64, :80, :229, :268, :271`).
5. **A projeção da lente também não expõe.** `FormulaItemProjection`
   (`shopman/backstage/projections/recipe_book.py:174-188`) = sku, name, role, role_label,
   quantity_display, quantity_g, unit, pct_display, is_anchor, matched — **sem `note`**
   (confirmado no contrato gerado: `surfaces/production-nuxt/app/generated/recipeBookContract.ts`,
   `FormulaItemProjection` sem `note`, enquanto `FormulaMetricProjection:79` e o item de captura
   `:181` têm).
6. **Publicar joga fora.** `publish_version` → `_write_recipe`
   (`services/recipe_book.py:289-302`) monta cada `RecipeItem.meta` de
   `{**existing_meta, **line["meta"]}` — e `line["meta"]` vem de `_bom_items`
   (`percentages.py:662-709`), que **nunca emite a chave `note`** (monta `"meta": {}` nas
   linhas de base `:682` e de parte `:697`, e `meta={"role","cap_pct"}` só para massa velha `:707`).

**Resultado:** o padeiro pode escrever "esta farinha é a da padaria do bairro, pede 2% mais água" e
a frase **desaparece da ficha de execução no ato de publicar**. Fica preservada apenas na
`RecipeVersion.formula` (história), não no BOM que a fornada consome.

**O conserto é de uma linha** — `_bom_items` copiar `item.get("note")` para
`meta["note"]`, e `data-schemas.md:1558` ganhar a chave. Isso é **P**. [INFERÊNCIA — a linha é
pequena, mas exige decidir *se* a nota deve mesmo ir para o BOM; ver §7]

### 5.2 A ficha de execução (`Recipe`) não tem onde guardar uma anotação prática. Nenhuma. [FATO]

Somando §1.1 e §1.2: `Recipe` não tem `notes`; `RecipeItem` não tem `notes`; os únicos lugares de
texto livre são as `notes` de `RecipeEntry`/`RecipeVersion` e o `RecipeItem.meta`. Quando o
`publish_version` escreve a ficha, ele copia `version.steps` para `recipe.steps`
(`services/recipe_book.py:318`) e **não copia `version.notes`** — porque **não há destino**
(`_write_recipe` `:264-322` mexe em name, output_sku, batch_size, steps, is_active, meta).

Ou seja: **a anotação que o gestor escreve na versão morre do lado da autoria.** Se o dono quer
"anotação prática interna que o operador lê", hoje não há duto — falta o leitor, não só o campo.

---

## 6. O menor acréscimo coerente

Princípios que restringem a resposta, todos escritos: contextual → JSONField, não campo novo
(`CLAUDE.md`, "Core é Sagrado" §1-2); a `Recipe` é sagrada e estável (ADR-027 §2,
`docs/decisions/adr-027-recipe-book-authoring-vs-execution.md:40-45`); publicar é o **único**
escritor (`adr-027:41`); a vertical de panificação é `contrib/formula`, pura
(`adr-027:53-54`); e "publicar escreve a ficha … `steps`" já é o contrato (`adr-027` +
`RECIPE-INVENTORY-PLAN.md:78`).

### 6.1 Opção A — "procedimento legível" (P) ← recomendada para já

**Não abrir campo. Dar estrutura ao que já existe e um leitor.**

1. **Estruturar `RecipeVersion.steps`** de `list[str]` para `list[dict]` compatível com o que a
   doc já promete (o "passos do KDS"): `{"name": str, "instructions": str?, "target_seconds": int?,
   "note": str?}`. Aceitar string pura na entrada e normalizar (o `_steps()` de
   `shopman/backstage/services/recipe_book.py:84-92` já é o funil — é lá que normaliza).
   **Zero migração**: é JSON, e os dados existentes (`["Mistura", "Forno"]`) leem como
   `{"name": "Mistura"}`. [FATO sobre "zero migração": o campo é `JSONField` — `recipe_book.py:143`]
2. **Publicar copia a estrutura** para `Recipe.steps` (já copia hoje, `:318` — muda só a forma).
3. **Expor na superfície de execução.** O menor lugar honesto é o ticket de pesagem
   (`ProductionWeighingTicketProjection`, `production.py:315`) ganhar `steps` — a Preparação já é
   a tela onde o operador está com a ficha na mão, e a etiqueta já é impressa. Um campo na
   projection + um bloco no `mise-en-place.vue`.
4. **Corrigir `data-schemas.md:1543`** para descrever o que existe, não o que se pretendeu.

⚠️ **O que esta opção NÃO resolve:** "executável INEQUIVOCAMENTE" no sentido forte da pergunta.
Um texto de instrução continua sendo texto: não há ordem verificável, não há tempo, não há
"etapa 3 de 7 concluída". Resolve legibilidade e rastreabilidade de conteúdo; não resolve
execução.

### 6.2 Opção B — "procedimento executável", com tempos (M)

A — e mais:

5. **`target_seconds` por etapa** vira dado vivo: o temporizador de piso já existe
   (`surfaces/production-nuxt/app/composables/useFloorTimers.ts`, `kind: "oven" | "free"`) —
   a etapa com tempo alimenta o timer em vez de digitar minutos à mão.
6. **Reabrir (ou enterrar de vez) `advance_step`.** `CraftExecution.advance_step` já faz tudo:
   trava de linha, revisão otimista, evento append-only, idempotência
   (`execution.py:152-241`). Falta só o **chamador** — um botão "próxima etapa" na superfície, e a
   projection expondo `steps_progress`. **Mas isto é decisão de produto explícita**, porque a casa
   já decidiu o contrário em 16/09/2026 (`data-schemas.md:1513`: *"a aba Produção tem uma ação só,
   Continuar"*). Não reabrir por conta própria.
   Se reabrir: o B.I. já registrou o defeito do ponteiro escalar e pediu
   `steps_progress_history: [{step, at, actor}]` por append (`docs/plans/BI-INSIGHTS-MAP.md:365-371`) —
   e o `WorkOrderEvent.STEP_ADVANCED` **já é** esse histórico. O ponteiro em `meta` é redundante.

### 6.3 Opção C — **não** fazer (a armadilha)

**Não criar `RecipeStep` como modelo.** Seria campo/estrutura nova no Core sem necessidade provada
(CLAUDE.md regra 1), e o eixo já tem casa: `RecipeVersion.steps` na autoria, `Recipe.steps` na
execução. Um modelo novo cria duas verdades sobre "etapa" e reabre exatamente a colisão que
`RECIPE-MODELING-BRIEF.md:36-37` fechou. [INFERÊNCIA, mas ancorada em regra escrita]

### 6.4 Anotações (b) — o menor acréscimo

| Onde | Ação | Tamanho |
|---|---|---|
| **Item, do rascunho para a ficha** | `_bom_items` (`percentages.py:662`) copiar `note` → `meta["note"]`; registrar a chave em `data-schemas.md:1558` | **P** |
| **Item, na tela** | `FormulaItemProjection` ganhar `note` + uma célula no editor (`edit.vue:432-500`) | **P** |
| **Etapa** | cai de graça na Opção A §6.1.1 (`{"name", "instructions", "note"}`), porque a etapa deixa de ser string | **P**, junto com A |
| **Ficha de execução (global)** | ⚠️ **nada a criar**: a rota certa é o operador ler a anotação **da versão publicada**, que já existe e já é versionada — via a projection do ticket. Criar `Recipe.notes` seria o 4º lugar para a mesma frase, e o único que `publish_version` não governa | **decisão de produto** |
| **Parte** | se necessário, `note` no objeto da parte (`plan:102-106`), mesma mecânica do item | **P** |

A pergunta "global, por item, por parte ou por etapa?" tem resposta honesta: **os quatro níveis são
coerentes com o eixo a que pertencem, e três deles já têm casa.** O que não existe é o **duto** até
a execução — e é isso, não o campo, que faz o dono sentir que não tem onde anotar.

---

## 7. Tamanho e decisões de produto

### 7.1 Tamanho

| Entrega | Tamanho | Por quê |
|---|---|---|
| Corrigir `data-schemas.md:1543` (doc mente sobre KDS) | **P** | uma linha de doc; evita construir sobre ficção |
| Propagar `note` do item até `RecipeItem.meta` + registrar a chave | **P** | `_bom_items` + 1 linha de doc |
| Expor `note` do item na lente e no editor | **P** | dataclass + contrato gerado + 1 célula |
| Estruturar `steps` (`name`/`instructions`/`target_seconds`/`note`) + normalizar no funil | **P–M** | JSON, sem migração, mas mexe em `RecipeVersion.steps`/`Recipe.steps` e em quem serializa |
| Levar `steps` até o ticket de pesagem + tela | **P–M** | uma projection + um bloco em `mise-en-place.vue` |
| Temporizador por etapa | **M** | `useFloorTimers` já existe, mas exige ligar etapa→timer e testar |
| Reabrir `advance_step` na superfície | **M** | o Core está pronto e testado; falta chamador, projection e UI — e a decisão |
| Mover `steps_progress` para `steps_progress_history` | **M** | já pedido pelo B.I. (`BI-INSIGHTS-MAP.md:365-371`); o evento já existe |

### 7.2 Decisão de produto (não é do agente)

1. **O operador deve registrar etapa (botão "próxima etapa"), ou o procedimento é só leitura?**
   A casa já respondeu "só leitura" em 16/09/2026 (`data-schemas.md:1513`). Se a resposta mudar,
   `advance_step` está pronto — mas é a decisão que o dono precisa tomar, com o custo dela:
   toda fornada passa a ter um gesto a mais no chão de fábrica.
2. **A etapa precisa ter tempo e temperatura?** O dono adiou ("discutiremos em seguida") e depois
   pediu proposta (`RECIPE-MODELING-BRIEF.md:137-138`). Sem tempo, o procedimento é texto; com
   tempo, ele liga no temporizador de piso e vira executável de verdade. **Este é o divisor
   entre P e M.**
3. **A anotação prática é da VERSÃO (história, versionada) ou da FICHA (atual, mutável)?**
   `RecipeVersion.notes` já é versionada e imutável; um `Recipe.notes` seria mutável e fora do
   governo do `publish_version` (ADR-027 §2). Recomendo versão. **Decisão do dono.**
4. **"Passos" ou "Etapas"?** O modelo diz etapa, toda a tela diz passo, a doc diz passo. Escolher
   uma antes de a superfície crescer — é rename barato hoje e caro depois (`CLAUDE.md`,
   zero-residuals).
5. **O achado `missing_steps` deve aparecer em tela?** Ele já existe com a frase exata
   (`operational.py:202-210`) e não tem leitor humano. Subir para uma tela de gestor é P, mas
   decide-se o que a casa faz quando o achado acende em 90 fichas.

### 7.3 Onde procurei e não achei (para o próximo não repetir a busca)

- **Não existe** campo de procedimento além de `steps`: procurei `instructions`, `method`,
  `procedure`, `modo_de_fazer`, `preparo` em `packages/`, `shopman/`, `surfaces/` — nada além do
  achado `missing_steps` e dos textos de tela já citados.
- **Não existe** ficha técnica impressa com procedimento: as impressões existentes são
  `WeighingLabels.vue`, `ProductionLabelPrintDialog.vue` (etiquetas) e o ticket de pesagem (§3.2).
- **Não existe** upload de anexo (foto do caderno) na ficha — a foto existe só como entrada de
  IA (`recipe_capture`), nunca como arquivo guardado. Confirmado no report irmão 06 §3, que mede
  isso em detalhe; não duplico aqui.
- **`Recipe.meta["prep_time_min"]` e `bake_temp_c`** (sugeridos no `help_text` de `recipe.py:78`)
  **não são lidos por nenhum código de produção**. Aparecem só em: `docs/business-rules.md:621`
  (doc, como exemplo), `docs/plans/FOMO-MARKETING-SPECS.md:74` (F6 **propõe** usar
  `Recipe.meta.prep_time_min` para "Próxima fornada às Xh" no storefront — plano, não código) e
  `packages/craftsman/shopman/craftsman/tests/test_recipe_book.py:153,162` (usado como chave
  arbitrária para provar que `meta` sobrevive ao `publish`, não como campo real).
  O `prep_time_minutes` que existe de verdade é outro, do Shop, não da ficha
  (`shopman/shop/projections/order_tracking.py:1644`). [FATO]
- **Não rodei** o `audit_recipe_material_day1` nem o seed contra banco — sem DB nesta worktree.
  Portanto **não sei quantas das 92 fichas do seed estão sem `steps`** na prática
  (o seed sempre preenche via `_production_steps_for_recipe`, `seed.py:5787-5805`, o que sugere
  zero — mas isso é [NÃO VERIFICADO] contra o banco vivo).
