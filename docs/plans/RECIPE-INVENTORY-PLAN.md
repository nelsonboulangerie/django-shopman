# RECIPE-INVENTORY-PLAN — inventário de receitas com versão, padrão da casa e lente de padaria

> Aberto em 2026-09-03. Pedido do dono: gerenciar um **inventário de receitas** de forma
> extremamente prática (entrada por anotação, por foto em qualquer língua, ou à mão),
> converter qualquer receita para o **padrão da casa (1000 g de farinhas totais)** guardando
> as quantidades informadas como referência, **comparar** receitas, **associar a SKU** (uma
> receita é a "atual"), **versionar** para cruzar com o B.I., e dar ao padeiro **valores de
> referência** sem tirar dele a decisão.
>
> Referência de domínio: `~/Downloads/HANDOFF-receitas-panificacao.md` (modelo BBGA/Hamelman
> decidido pelo dono: receita base → partes → mistura final calculada). Este plano é a
> implementação; a decisão de arquitetura mora na [ADR-027](../decisions/adr-027-recipe-book-authoring-vs-execution.md).

## 0. A decisão em uma frase

**Autoria e execução são duas coisas.** A `Recipe` do Craftsman continua sendo a **ficha de
execução** (o BOM que a fornada consome, a que o estoque debita, a que a nutrição lê). O
inventário nasce como aggregate próprio — `RecipeEntry` (a receita, com sua linhagem) e
`RecipeVersion` (uma fórmula congelada) — e **publicar** uma versão é o único caminho que
escreve na ficha de execução. A ficha continua uma só por SKU e estável (mesmo `ref`), então
relatórios, códigos cegos, seed e `WorkOrder.recipe` não mudam de significado.

## 1. Resposta à pergunta do dono: "modo padaria" ou tela dedicada?

**Nem um nem outro: a lente vem do conteúdo.** Uma receita que tem farinha ganha a lente de
padaria (porcentagem do padeiro sobre as farinhas, hidratação, sal, farinha pré-fermentada,
partes e mistura final). Uma receita sem farinha ganha a mesma tela com âncora diferente
(massa total = 100%, ou um ingrediente-âncora escolhido — o leite de um creme, o chocolate de
uma ganache). Não há botão "modo padaria" para esquecer ligado, nem tela paralela para
divergir. O que muda é:

- **a âncora** (`formula.anchor.kind`): `flour` (soma das farinhas), `total` (massa total) ou
  `ingredient` (um SKU). Sugerida pelo conteúdo **e pelo tipo** (`suggest_anchor_kind`:
  farinha é âncora só em pão, viennoiserie e massa doce, e quando é **estrutura**, ≥ 15%
  da massa; num béchamel com 7% ela é espessante, e um creme com 30% de farinha continua
  creme e fala em % da massa total), editável. O padrão da casa (1000 g) vale para qualquer
  âncora: 1000 g de farinha no pão, 1000 g de massa total no creme, 1000 g do
  ingrediente-âncora numa ganache;
- **os painéis** que aparecem: métricas de padaria só com âncora `flour`; "partes" só quando
  há parte; "mistura final" só quando alguma parte tem fórmula conhecida;
- **as referências** (`kind` da receita): pão, viennoiserie, massa doce, recheio, creme,
  molho, bebida, outra — cada uma com a sua tabela de valores da literatura.

Custo do padeiro: zero. Custo do sistema: um campo `kind` e uma `anchor` por versão.

## 2. Modelo de domínio (Craftsman core, migração `0007`)

```
RecipeEntry                        # a receita no inventário — a linhagem
  ref            slug único (== Recipe.ref quando publicada)
  name
  kind           bread | viennoiserie | sweet_dough | filling | cream | sauce | beverage | other
  output_sku     "" ou SKU (associação; "" = receita sem SKU, só conhecimento)
  notes
  is_archived
  current_version  FK → RecipeVersion (a última publicada), null
  meta, created_at, updated_at

RecipeVersion                      # uma fórmula congelada
  entry          FK
  number         1, 2, 3… por entry (unique entry+number)
  status         draft | published | superseded
  label          "o que mudou" (curto)
  yield_quantity, yield_unit       # rendimento da fórmula tal como escrita (kg | g | un | L | ml)
  formula        JSON (schema §3)
  origin         JSON — a receita COMO FOI INFORMADA (quantidades, unidades, texto), imutável
  source         JSON — {kind: manual|note|photo|ficha|import, text?, language?, image_name?, model?}
  steps          list[str] (vai para Recipe.steps ao publicar)
  notes
  created_by, created_at, published_at (null)
  meta
```

Regras:

- **Uma versão publicada por entry.** Publicar `n` marca a anterior `superseded`.
- **Publicar escreve a ficha de execução** `Recipe(ref=entry.ref)`: upsert de `name`,
  `output_sku`, `batch_size = yield`, `steps`, `meta["version_ref"] = "<ref>@<n>"`,
  `meta["output_unit"] = yield_unit` (o invariante de massa da ficha precisa da unidade
  declarada), e **substitui os `RecipeItem`** pelo BOM derivado (§4), **preservando o
  `RecipeItem.meta`** de SKU que já existia (é onde moram alérgenos/nutrição/densidade —
  ADR-008). Outra ficha ativa para o mesmo `output_sku` é desativada (a entry vira a atual).
- **`WorkOrder` já congela a ficha** (`meta["_recipe_snapshot"]`); o snapshot ganha
  `version_ref` (uma linha em `scheduling.py`) para o B.I. cruzar fornada × versão.
- **Bootstrap idempotente** das fichas que já existem: `bootstrap_recipe_book` cria uma entry
  por `Recipe` (ref igual) com a versão 1 publicada, `source.kind="ficha"`, e a fórmula na
  forma base (partes dissolvidas — §4). O seed chama isso no fim de `_seed_recipes`.

## 3. Schema de `RecipeVersion.formula`

```json
{
  "anchor": {"kind": "flour"},                 // "flour" | "total" | {"kind":"ingredient","sku":"LEITE"}
  "basis_g": 1000,                             // total da âncora quando padronizada; null se não
  "standardized": true,
  "items": [
    {"sku": "FARINHA-T55", "name": "Farinha T55", "role": "flour",  "quantity": 900, "unit": "g", "note": ""},
    {"sku": "",            "name": "farinha de castanha", "role": "flour", "quantity": 100, "unit": "g"},
    {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 700, "unit": "g"},
    {"sku": "OVOS", "name": "Ovos", "role": "egg", "quantity": 3, "unit": "un", "grams_per_unit": 55}
  ],
  "parts": [
    {"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment", "flour_pct": 20, "quantity": 400, "unit": "g"},
    {"sku": "PASTA-AUTOLIZADA", "entry_ref": "massa-pasta-autolizada", "kind": "autolyse", "flour_pct": 60, "quantity": 960, "unit": "g"},
    {"kind": "old_dough", "cap_pct": 20}
  ]
}
```

- `items` é a **receita base**: a fórmula total, com TODA a farinha (a do levain, da
  autólise e do yudane inclusive). `sku=""` = ingrediente ainda não casado com insumo do
  sistema (permitido em rascunho; **publicar exige todo `sku` preenchido**).
- `role` ∈ `flour | liquid | salt | yeast | fat | sugar | egg | dairy | inclusion | other`
  — sugerido por heurística multilíngue (`classify_ingredient`), editável. É o `role` que
  alimenta hidratação (`liquid`/flour), sal, fermento, e a âncora `flour`.
- `unit` ∈ `g | kg | ml | L | un`. Massa vira grama. Volume vira grama pela
  `density_g_per_ml` do item (ou 1,0 para `role=liquid` sem densidade, com aviso).
  Contagem só entra na conta com `grams_per_unit`; sem ele, fica fora com aviso.
- `parts` descreve **quanto da base passa por uma parte**. Uma parte com `sku` precisa de
  uma `RecipeEntry` com versão atual (a composição vem de lá, proporcionalmente). Com
  âncora `flour`, o padeiro declara `flour_pct` (farinha pré-fermentada, % da farinha
  total) e `quantity` é derivada; sem âncora `flour`, declara `quantity`.
  `kind` ∈ `preferment | autolyse | soaker | old_dough`.
- **`old_dough` não tem composição própria** (é a própria base da véspera): declara só o
  teto `cap_pct` da fórmula inteira. A mistura final "a cap%" encolhe TUDO por `(1 − cap)`.
  Ao publicar, vira `RecipeItem(input_sku=output_sku, is_optional=True,
  meta={"role":"old_dough","cap_pct":20})` — visível na ficha, fora do consumo
  (`is_optional` já é excluído do BOM). A leitura do saldo do dia é WP posterior.
- `basis_g`/`standardized`: **padronizar** = escalar a fórmula inteira para a âncora somar
  `basis_g` (padrão da casa: 1000). É reversível e sem perda: `origin` guarda o informado.

## 4. Matemática (Craftsman `contrib/formula/percentages.py`, pura)

`analyze(formula, part_formulas) -> FormulaAnalysis`:

- `anchor_total_g`, `total_mass_g`, `items` com `pct` (= g ÷ âncora × 100);
- métricas (só com âncora `flour`): `hydration_pct`, `salt_pct`, `yeast_pct`,
  `prefermented_flour_pct`, `fat_pct`, `sugar_pct`, `egg_pct`;
- `final_mix` = base − conteúdo das partes com fórmula (composição proporcional da versão
  atual da parte) — **nunca digitada, calculada**;
- `bom` = `final_mix` + as partes como itens (`LEVAIN 400 g`) — é isto que a ficha de
  execução recebe. É a defesa contra a dupla contagem da farinha (handoff §3);
- `warnings`: parte sem fórmula, parte maior que a base, contagem sem `grams_per_unit`,
  volume sem densidade, valor fora da referência.

`standardize(formula, basis_g=1000)`, `scale(formula, factor)`, `classify_ingredient(name, sku)`,
`looks_like_flour(name, sku)` (pt/en/fr/ja: farinha, flour, farine, 粉/小麦粉/強力粉/薄力粉,
centeio/rye/seigle/ライ麦, semolina, integral/whole/complète/全粒粉, fubá/cornmeal…),
`REFERENCE_RANGES` e `check_references(analysis, kind)`.

Referências (literatura: Hamelman *Bread*, Suas *Advanced Bread and Pastry*, convenção BBGA):
sal 1,8–2,2% (máx 2,5); fermento fresco 0,5–2% (máx 3; seco ≈ ⅓); hidratação por `kind`:
pão rústico 68–80, baguete/tradição 65–75, ciabatta 75–85, pão de forma/shokupan 60–72,
brioche 50–60 (líquido total), croissant 50–58; farinha pré-fermentada: levain 15–30 (máx 40),
poolish 20–40 (máx 50), biga 30–50 (máx 60), yudane/tangzhong 10–20 (máx 30), massa velha
15–25 (máx 30), autólise até 100. Enriquecidas: açúcar 10–20, manteiga (brioche) 40–60,
ovos 40–60. **São referência; o padeiro decide.** A tela mostra a faixa e marca "fora da
faixa" em tom calmo — nunca bloqueia.

## 5. Serviços (Craftsman `services/recipe_book.py`)

```python
create_entry(*, ref, name, kind="other", output_sku="", notes="", meta=None) -> RecipeEntry
create_version(entry, *, formula, yield_quantity, yield_unit, origin=None, source=None,
               steps=None, notes="", label="", created_by="") -> RecipeVersion   # draft, number = último+1
update_draft(version, *, formula=None, yield_quantity=None, yield_unit=None, steps=None,
             notes=None, label=None) -> RecipeVersion                              # só draft
publish_version(version, *, actor="") -> Recipe
diff_versions(a, b) -> FormulaDiff
bootstrap_entry_from_recipe(recipe) -> RecipeEntry | None                         # idempotente
part_formulas_for(formula) -> dict[str, dict]                                     # sku → formula da versão atual
```

Erros: `RecipeBookError(CraftError)` com códigos `FORMULA_INVALID` (campo em `field`),
`ENTRY_WITHOUT_SKU`, `ITEM_WITHOUT_SKU`, `VERSION_NOT_DRAFT`, `PART_WITHOUT_FORMULA`,
`PART_EXCEEDS_BASE`, `ENTRY_ARCHIVED`.

## 6. Orquestração (backstage)

- `services/recipe_capture.py` — **ler uma anotação ou foto** e devolver um rascunho
  estruturado (nome, rendimento, ingredientes com quantidade/unidade/`role`, passos, língua
  detectada, tradução para pt-BR, `original_text` por linha). Provedor: Anthropic via
  `AI_ASSIST_API_KEY` (mesmo pino de `copy_assist`), modelo `AI_ASSIST_MODEL`, imagem por
  base64. JSON estrito validado por pydantic (padrão de `bi/scenarios.py`). Sem credencial →
  `RecipeCaptureNotConfigured` (503 na API: a tela mostra "sem leitura automática neste
  ambiente", não erro).
- `services/recipe_book.py` (backstage) — casa ingrediente ↔ insumo (`Material` do Buyman +
  saídas de `RecipeEntry` com fórmula, via `rapidfuzz` + sinônimos multilíngues), monta
  `formula` a partir do rascunho, e embrulha os serviços do Craftsman.
- `projections/recipe_book.py` — dataclasses do contrato (§7), `build_*`.
- `api/recipe_book.py` + rotas em `api/urls.py` (§8).
- `export_recipe_book_schema` → `surfaces/production-nuxt/app/generated/recipeBookContract.ts`
  + teste de deriva (mesmo padrão do `export_production_schema`).

## 7. Projections (contrato com a superfície)

```python
RecipeEntryCardProjection: ref, name, kind, kind_label, output_sku, output_name, has_ficha: bool,
    current_version_number: int | None, version_count: int, draft_count: int,
    anchor_kind: str, hydration_display: str, updated_at_display: str, is_archived: bool
KindOptionProjection: value, label
RecipeBookListProjection: entries: tuple[RecipeEntryCardProjection, ...], kinds: tuple[KindOptionProjection, ...], count: int
RecipeBookAccessProjection: can_view: bool, can_edit: bool, capture_available: bool

FormulaItemProjection: sku, name, role, role_label, quantity_display, quantity_g: str, unit, pct_display, is_anchor: bool, matched: bool
FormulaPartProjection: sku, entry_ref, name, kind, kind_label, flour_pct_display, quantity_display, cap_pct_display, has_formula: bool
FormulaMetricProjection: code, label, value_display, low_display, high_display, max_display, tone, note
FormulaWarningProjection: code, message, tone
FormulaLensProjection: is_bakery: bool, anchor_kind, anchor_label, basis_display, standardized: bool,
    anchor_total_display, total_mass_display, items, final_mix, bom, parts, metrics, warnings
RecipeVersionProjection: id, number, status, status_label, label, yield_quantity: str, yield_unit, yield_display,
    source_kind, source_label, created_by, created_at_display, published_at_display, notes, steps: tuple[str, ...],
    lens: FormulaLensProjection, formula: dict, origin: dict
RecipeEntryDetailProjection: ref, name, kind, kind_label, output_sku, output_name, notes, is_archived,
    current_version_number: int | None, ficha_ref, versions: tuple[RecipeVersionProjection, ...]  # mais nova primeiro
RecipeCompareRowProjection: name, sku, role_label, a_display, b_display, delta_display, delta_pct_display, tone
RecipeCompareMetricProjection: label, a_display, b_display, delta_display, tone
RecipeCompareProjection: a_title, b_title, rows, metrics
ReferenceRangeProjection: code, label, low_display, high_display, max_display, note
RecipeReferenceProjection: kind, kind_label, ranges
IngredientOptionProjection: sku, name, unit, role, is_part: bool, entry_ref
CaptureItemProjection: name, original_text, quantity: str, unit, role, sku, match_confidence: str, candidates: tuple[IngredientOptionProjection, ...]
RecipeCaptureDraftProjection: name, kind, language, yield_quantity: str, yield_unit, items, steps: tuple[str, ...], notes, formula: dict
```

`tone` ∈ `ok | warning | muted`. Tudo já formatado (ADR-014): a superfície não faz conta.

## 8. API (`/api/v1/backstage/recipes/`)

| Método | Caminho | Corpo / query | Resposta |
|---|---|---|---|
| GET | `recipes/access/` | | `{access}` |
| GET | `recipes/` | `q`, `kind`, `archived=1` | `{book, access}` |
| POST | `recipes/` | `{ref?, name, kind, output_sku, notes, version?}` | `{entry}` (201) |
| GET | `recipes/<ref>/` | | `{entry, access}` |
| PATCH | `recipes/<ref>/` | `{name?, kind?, output_sku?, notes?, is_archived?}` | `{entry}` |
| POST | `recipes/<ref>/versions/` | `{from_version?, formula, yield_quantity, yield_unit, steps?, notes?, label?, origin?, source?}` | `{entry, version}` (201) |
| PATCH | `recipes/<ref>/versions/<n>/` | campos do rascunho | `{entry, version}` |
| POST | `recipes/<ref>/versions/<n>/publish/` | | `{entry}` |
| POST | `recipes/lens/` | `{formula, kind}` | `{lens}` |
| POST | `recipes/standardize/` | `{formula, basis_g?}` | `{formula, lens}` |
| GET | `recipes/compare/` | `a=<ref>@<n>`, `b=<ref>@<n>` | `{compare}` |
| GET | `recipes/reference/` | `kind` | `{reference}` |
| GET | `recipes/ingredients/` | `q` | `{options}` |
| POST | `recipes/capture/` | `{text?, image?: {data_base64, media_type}, language_hint?}` | `{draft}`; 503 sem credencial; 502 falha do provedor |

Permissão: **ler** = `backstage.operate_production` (o gate do app); **escrever** =
`shop.manage_production` (Cozinha já tem; é a mesma régua de "mexer acontece no app de
Produção"). Sem permissão nova, sem migração de permissão. Erros no dialeto canônico
(`{detail, field, errors}`).

## 9. Superfície (`surfaces/production-nuxt`)

- Rail: item **Receitas** (`book-open`), visível quando `recipes/access/` responde `can_view`.
- `/recipes` — inventário: busca, filtro por `kind`, chips "sem SKU" / "rascunho pendente",
  cartão com hidratação e versão atual. Ação "Nova receita".
- `/recipes/new` — três portas na mesma tela: **Anotação** (colar texto), **Foto**
  (câmera/arquivo, redimensionada no navegador para ≤1600 px antes de enviar), **Manual**.
  As duas primeiras chamam `capture` e caem no editor com o rascunho preenchido e os
  ingredientes casados (com candidatos para escolher).
- `/recipes/[ref]` — a receita: lente (âncora, tabela com g e %, métricas com faixa de
  referência, partes, mistura final, BOM), linha do tempo das versões, "Nova versão",
  "Publicar" (com o diff para a versão atual), "Comparar com…", "Associar SKU".
- `/recipes/[ref]/edit` — o editor: tabela editável (nome, insumo, quantidade, unidade,
  papel), partes, rendimento, passos; **prévia da lente** por `recipes/lens/` com debounce;
  botão **Padronizar para 1000 g de farinha** (mostra o antes/depois e guarda `origin`).
- `/recipes/compare` — duas versões lado a lado (mesma receita ou receitas diferentes),
  deltas por ingrediente e por métrica.
- Composables com `useFetch`/`$fetch` pelo BFF, presentation pura + vitest, tipos
  estreitados sobre `~/generated/recipeBookContract`.

## 10. Frentes e ordem

| WP | Onde | Estado |
|---|---|---|
| R1 modelos + serviços + math + bootstrap + testes | `packages/craftsman` | ✅ entregue (migração `0007`, +114 testes) |
| R2 UI | `surfaces/production-nuxt` | ✅ entregue (`/recipes`, `/recipes/new`, `/recipes/[ref]`, `/recipes/[ref]/edit`, `/recipes/compare`; +66 testes) |
| R3 captura + casamento + projections + API + export + testes + seed | `shopman/backstage`, `config` | ✅ entregue (`export_recipe_book_schema`, +133 testes) |
| R4 docs (ADR-027, data-schemas, commands) + integração + QA | raiz | ✅ QA no navegador sobre o seed real: bootstrap de 67 fichas, rascunho → padronizar → associar SKU → publicar → ficha com `version_ref`, comparação |

Decisões tomadas na integração (03/09): fermento natural (cultura) não é `yeast` (fica fora da
faixa de fermento biológico); `prefermented_flour_pct` soma só partes `preferment` (autólise
e yudane não fermentam); água pesada em grama publica contra insumo em litro pela densidade
(1,0 é física; outro líquido precisa de densidade declarada na linha, no `RecipeItem.meta` ou
no `Material.metadata`); publicar leva o perfil do insumo (`Material.metadata`) para a linha
nova da ficha; massa velha vai para a ficha como linha **opcional** (fora do consumo).

## 11. Fora deste plano (dito, não esquecido)

- Leitura do **saldo de massa velha** do dia no planejamento (`min(sobra, teto)`).
- **Cofre** (`export_backup`/`import_backup`) ainda não carrega `RecipeEntry`/`RecipeVersion`.
- Admin/Unfold para `RecipeEntry`/`RecipeVersion` (CRUD de conferência, atrás do gate).
- Comparação com dados de produção do B.I. por `version_ref` (o carimbo já sai daqui).
