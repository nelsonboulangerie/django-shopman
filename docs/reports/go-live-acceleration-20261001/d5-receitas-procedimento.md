# D5 — Receitas: o MODO DE FAZER (procedimento, etapas, tempos, anotação)

**Tarefa:** o dono disse *"temos alguma discussão valiosa sobre isso no repo, parece que se perdeu"*.
O tema é o **procedimento da receita** (etapas, instruções, tempos, temperatura, anotações).

**Árvore:** `origin/main` = `beb9bf973` (2026-10-01). Todo `git show` abaixo é contra `origin/main`.
O checkout local está em `codex/shopman-backstage-marketing-hardening` e **não** foi usado como
evidência. Nenhum comando git mutante. Nada editado além deste relatório.

---

## 0. Veredito em cinco linhas

1. **A discussão não se perdeu *dentro* do repo — ela nunca entrou no repo.** As quatro perguntas do
   dono estão escritas, com recomendação, em **D5 de um `PENDING-DECISIONS.md`** que existe **apenas**
   no branch **não mergeado** `claude/turno-autonomo-coordenacao-76dc5f`. Em `origin/main` esse arquivo
   **não existe** — só as 8 referências a ele no brief que o encomendou. **É este o achado central.**
2. **O que JÁ foi decidido e executado é a *forma* da etapa**, não o procedimento: desde 30/09/2026 a
   etapa é objeto `{name, instructions?, target_seconds?, note?}` (`craftsman/recipe_steps.py`,
   PR #1307, migração `craftsman/0015`). O `instructions` é literalmente documentado como
   *"O modo de fazer da etapa"*.
3. **Nunca foi decidido:** se o operador registra ou só lê; se a etapa tem temperatura; se a anotação
   mora na versão ou na ficha; e "Passos" vs "Etapas". Os quatro estão em **D5** (não mergeado) e em
   `05-receitas-estrutura.md` §7.2 (mergeado, mas em `docs/reports/`, que **não é** doc canônico).
4. **O duto até o chão de fábrica continua aberto, e a própria doc canônica diz isso:**
   `docs/reference/data-schemas.md:1593` — *"⚠️ **Nenhuma tela de execução lê as etapas.** … Levar as
   etapas ao chão de fábrica é decisão do dono, ainda aberta."*
5. **Há uma discussão anterior, mais ambiciosa, que também não chegou ao repo:** o dono tem uma
   **notação própria de panificação** para passos (verbo + alvo referenciado + parâmetros **tipados**),
   aprovada em princípio em 05/09/2026 e explicitamente **adiada por ele** ("NÃO IMPLEMENTAR ANTES DE
   CONVERSAR"). Ela vive só na memória do agente, nunca virou doc nem código.

---

## 1. O que JÁ foi DECIDIDO sobre procedimento — e onde está escrito

### 1.1 [FATO] A forma canônica da etapa — decidida, executada e documentada

**Decisão (escrita, no código):** `packages/craftsman/shopman/craftsman/recipe_steps.py:1-19`
(docstring — o arquivo inteiro é a decisão):

> ```
> """Etapas de produção: a forma única de ``Recipe.steps`` e ``RecipeVersion.steps``.
>
> Cada etapa é um objeto::
>
>     {"name": "Fermentação", "instructions": "Até dobrar de volume.", "target_seconds": 5400, "note": "..."}
>
> ``name`` é obrigatório; ``instructions`` (o modo de fazer), ``target_seconds``
> (tempo alvo, inteiro maior que zero) e ``note`` (anotação prática) são
> opcionais e só ficam gravados quando têm conteúdo.
> ...
> **Quem lê ``steps`` hoje: as telas do inventário de receitas (autoria) e o
> snapshot da fornada (``_recipe_snapshot.production.steps``), que só copia. Nenhuma
> tela de execução lê as etapas: levá-las ao chão de fábrica é decisão à parte.**
> """
> ```

O vocabulário é **fechado no código** — `recipe_steps.py:29`:

> ```python
> #: Chaves que uma etapa pode ter, na ordem em que são gravadas.
> STEP_KEYS = ("name", "instructions", "target_seconds", "note")
> ```

E há normalização que recusa o que não é dessa forma (`recipe_steps.py:44-47`, `:64-67`):

> ```python
> raise _invalid(number, f"chave desconhecida ({', '.join(unknown)}). Use {', '.join(STEP_KEYS)}.")
> ...
> raise _invalid(number, "o tempo alvo precisa ser um número inteiro de segundos maior que zero.")
> ```

**Onde mais está escrito (canônico):** `docs/reference/data-schemas.md` §"Recipe.steps /
RecipeVersion.steps", `1569` (a forma) e `1575`:

> `| \`instructions\` | \`string\` | O modo de fazer da etapa. Ausente quando vazio. |`

`data-schemas.md:1576` avisa a colisão de nome que já mordeu:

> `| \`target_seconds\` | \`int\` > 0 | Tempo alvo da etapa, em segundos. … **Não é o \`target_seconds\` do KDS** (\`projections/kds.py\`, SLA do chamado): mesmo nome, outro conceito. |`

**Prova de execução:**

```
$ git log --format="%h %ad %s" --date=short deec9c869 004ba81f1 3e230198a
deec9c869 2026-09-30 Receitas: etapas viram objeto (modo de fazer, tempo, nota) e a nota do item chega à ficha
004ba81f1 2026-09-30 Receitas: RecipeVersion.save normaliza as etapas; cofre restaura na forma nova
3e230198a 2026-10-01 Migração 0015: etapas que não são lista param a migração

$ git log --format="%h %ad %s" --date=short -1 cbcaf1bdd
cbcaf1bdd 2026-10-01 Merge pull request #1307 from nelsonboulangerie/night/o5a-steps-estruturados
```

**Também decidido no mesmo ato (ADR-027 §2):** publicar é o **único escritor** da ficha —
`docs/decisions/adr-027-recipe-book-authoring-vs-execution.md:41`:

> *"**Publicar é o único escritor.** \`publish_version\` faz upsert da \`Recipe(ref=entry.ref)\` com o BOM derivado, preserva o \`RecipeItem.meta\` … e carimba \`Recipe.meta["version_ref"]\`."*

Verificado no código: `packages/craftsman/shopman/craftsman/services/recipe_book.py:333-338` — as
etapas **são** copiadas da versão para a ficha:

> ```python
> recipe.steps = list(version.steps or [])
> recipe.is_active = True
> recipe.meta = {**(recipe.meta or {}), **version_meta}
> ```

### 1.2 [FATO] A anotação **de item** — decidida e entregue (a "fatia P" do diagnóstico)

`docs/reference/data-schemas.md:1606` (tabela `RecipeItem.meta`):

> `| \`note\` | \`string\` | \`publish_version\` (de \`formula.items[].note\`, via \`percentages._bom_items\`) | **Ninguém ainda** | Anotação prática do ingrediente escrita na fórmula ("a farinha do bairro pede 2% mais água"). … **não** é preservada da ficha anterior: a versão publicada decide se ela existe. Duas linhas do mesmo insumo somadas numa só levam as duas notas, separadas por \`; \`. |`

Código: `packages/craftsman/shopman/craftsman/contrib/formula/percentages.py:702-704`

> ```python
> def _note_meta(note: Any) -> dict:
>     text = note.strip() if isinstance(note, str) else ""
>     return {"note": text} if text else {}
> ```

⚠️ O campo está entregue, mas a coluna "Lido por" diz **"Ninguém ainda"** — é a mesma ferida do §1.1:
**o dado chega à ficha e ninguém o mostra no chão.**

### 1.3 [FATO] O que o operador **não** faz — decidido em 16/09/2026

Esta é a única das quatro perguntas com decisão **de verdade** registrada. Duas fontes, ambas escritas:

**Fonte canônica** — `docs/reference/data-schemas.md:1514`:

> `| \`steps_progress\` | \`int\` | Ninguém no backstage (o escritor \`CraftExecution.advance_step\` segue no Core, **sem chamador de superfície desde a decisão de 16/09/2026: a aba Produção tem uma ação só, Continuar**) | Ninguém | Ponteiro manual de passo, 1-based. Legado em ordens antigas; não é lido por projection. |`

**Fonte da decisão (memória do projeto)**
`~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/project_producao_continuar_unico_e_timers_opcionais.md`:

> **Decisão do Pablo, 16/09/2026** … **Sai**: \`Processar\`, modal "em processo" (\`1/4 · Mistura\`, \`Avançar para Fermentação\`, \`Estornar…\`, link \`Expedição →\`), cabeçalho "em processo", **sequência obrigatória de etapas**.
> **Timers**: ferramenta opcional, múltipla, independente de ordem/lote/etapa; SKU opcional; espelha a UX do timer do forno … e inclui **timers avulsos** ("creio que será o mais usado"). **Não alimenta BI oficial**; no máximo telemetria técnica.
> **Princípio: "se não obrigar vira adereço, se obrigar engessa"** — logo, utilidade prática, nunca fluxo.

Consequência de código: o escritor existe e está **morto**.
`packages/craftsman/shopman/craftsman/services/execution.py:152` (`CraftExecution.advance_step`),
com teste em `packages/craftsman/shopman/craftsman/tests/test_vnext.py:471-494` e **zero chamadores**.

---

## 2. O que foi discutido e NUNCA decidido

### 2.1 [FATO] As quatro perguntas do dono — escritas em **D5**, num arquivo que não está no `main`

`PENDING-DECISIONS.md` (branch `claude/turno-autonomo-coordenacao-76dc5f`, não mergeado), seção **D5**,
citada literalmente:

> ```markdown
> ## D5 — Receitas: modo de fazer (O5)
>
> **Contexto.** \`Recipe.steps\` é lista de strings soltas; nenhum operador vê procedimento (nem KDS,
> nem ticket de pesagem). A fatia A (steps como \`{name, instructions?, target_seconds?, note?}\`,
> sem migração) pode entrar sem você; as perguntas abaixo mudam o desenho seguinte.
>
> **Perguntas.** (a) O operador REGISTRA a etapa feita, ou só LÊ? (b) Etapa tem tempo e temperatura?
> (c) Anotação mora na versão ou na ficha? (d) O nome na tela é "Passos" ou "Etapas"?
> **Recomendação:** (a) só lê, por enquanto; (b) tempo sim, temperatura opcional; (c) na versão;
> (d) "Etapas" (já é o rótulo do campo).
> ```

**As quatro perguntas do dono são exatamente estas.** Nenhuma foi respondida por ele.

### 2.2 [FATO] O mesmo conteúdo, em versão mergeada — mas em `docs/reports/`

`docs/reports/go-live-acceleration-20260930-diag/05-receitas-estrutura.md` **está em `origin/main`**, e
§7.2 ("Decisão de produto (não é do agente)", linhas `439-460`) lista **cinco** decisões — as quatro
acima mais uma:

> `441` **1. O operador deve registrar etapa (botão "próxima etapa"), ou o procedimento é só leitura?** A casa já respondeu "só leitura" em 16/09/2026 (\`data-schemas.md:1513\`). Se a resposta mudar, \`advance_step\` está pronto — mas é a decisão que o dono precisa tomar, com o custo dela: toda fornada passa a ter um gesto a mais no chão de fábrica.
> `445` **2. A etapa precisa ter tempo e temperatura?** O dono adiou ("discutiremos em seguida") e depois pediu proposta … **Este é o divisor entre P e M.**
> `449` **3. A anotação prática é da VERSÃO (história, versionada) ou da FICHA (atual, mutável)?** … Recomendo versão. **Decisão do dono.**
> `452` **4. "Passos" ou "Etapas"?** O modelo diz etapa, toda a tela diz passo, a doc diz passo. Escolher uma antes de a superfície crescer — é rename barato hoje e caro depois (\`CLAUDE.md\`, zero-residuals).
> `455` **5. O achado \`missing_steps\` deve aparecer em tela?** …

⚠️ **Mas `docs/reports/` não é doc canônico** — e o próprio repo diz isso,
`docs/plans/WP-CANONICAL-GO-LIVE-TRUTH-2026-09-28.md:40`:

> *"Reports: história e evidência de uma data; **nunca procedimento operacional vigente**."*

Ou seja: **a discussão está no repo, mas num lugar que o repo declarou não ser a verdade.** Foi por isso
que ela "se perdeu".

### 2.3 [FATO] ⛔ Uma discussão ANTERIOR, mais ambiciosa, e explicitamente adiada pelo dono

`~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/project_linguagem_de_passos_da_receita.md`
— **não existe equivalente no repo.** Citação literal:

> **⏳ NÃO IMPLEMENTAR ANTES DE CONVERSAR.** O Pablo aprovou a estrutura, mas guardou uma
> **notação própria, curta e rápida, voltada a panificação**, que ele quer discutir. Ele
> mesmo pediu: *"se quiser deixar anotado para me lembrar de discutir isso"*. **Pergunte por
> ela antes de escrever qualquer linha de passo.**
>
> ## A estrutura acordada
> **Passo = verbo + alvo + parâmetros.**
> - **Verbo**: vocabulário FECHADO (alimentar, autolisar, escaldar, misturar, fermentar,
>   dobrar, dividir, bolear, modelar, laminar, gelar, assar, resfriar). Fechado é o que
>   permite cronometrar, validar, traduzir receita importada e comparar versões.
> - **Alvo**: REFERÊNCIA ao que a fórmula já declara (parte, ingrediente, mistura final,
>   massa) — nunca texto. …
> - **Parâmetros**: **tipados por dimensão** — exigência explícita do Pablo … ("precisamos saber o que trata de tempo, temperatura").
>
> ### Onde mora
> Dentro do mesmo JSON versionado da fórmula (\`RecipeVersion\`), não em tabela nova: mudar a
> fermentação **é** versão nova da receita.
>
> ### O que isso compra
> Passo com duração vira **linha do tempo**: conta de trás para frente de "pão na vitrine às
> 7h" para "alimentar o levain às 18h de ontem".
>
> ### Descartado
> Marcação em texto livre (\`Misture {{parte:levain}}\`): o padeiro decora sintaxe, o erro de
> digitação quebra o elo calado, e nada fica pesquisável.

**Nada disso virou código.** O que shipou (`{name, instructions, target_seconds, note}`) é a versão
**muito** mais simples: texto livre, sem verbo fechado, sem alvo referenciado, **sem temperatura**, sem
linha do tempo. **São duas conversas diferentes, e a mais rica é a que se perdeu.**
⚠️ A memória também avisa uma armadilha de física que continua valendo:

> ⚠️ **Temperatura NÃO é escala de razão** (0 °C não é ausência de temperatura): a conversão
> é afim (\`°F = °C × 9/5 + 32\`), não um fator. Enfiar temperatura na tabela de fatores
> existente quebra em silêncio.

---

## 3. O que se PERDEU — existe em algum lugar, mas não no doc canônico

| # | O que | Onde existe | Por que se perdeu |
|---|---|---|---|
| **L1** | **`PENDING-DECISIONS.md` inteiro** (16 decisões D1–D16, incluindo **D5 = as 4 perguntas do dono**) | branch `claude/turno-autonomo-coordenacao-76dc5f`, commit `821750516`; arquivo em disco em `.claude/worktrees/turno-autonomo-coordenacao-76dc5f/docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md` (14.661 bytes) | **O branch nunca mergeou.** `git merge-base --is-ancestor origin/claude/turno-autonomo-coordenacao-76dc5f origin/main` → **NOT MERGED**. Em `origin/main` o arquivo não existe. |
| **L2** | As 4 perguntas em prosa | `docs/reports/go-live-acceleration-20260930-diag/05-receitas-estrutura.md:439-460` (**está no main**) | `docs/reports/` é declarado **não-canônico** (`WP-CANONICAL-GO-LIVE-TRUTH-2026-09-28.md:40`). Ninguém procura decisão aberta em relatório de diagnóstico. |
| **L3** | A **notação própria de passos** do dono (verbo+alvo+parâmetros tipados) | **só** na memória do agente (`project_linguagem_de_passos_da_receita.md`) | Nunca virou doc do repo. O `RECIPE-MODELING-BRIEF.md` do `main` **não** a contém. |
| **L4** | O **processo real das 11 massas (92 etapas**: fase · etapa · tempo · temperatura · nota) | **só** no artifact do claude.ai `b8cd4fc0-c136-47d0-aac2-0a4c912e0e59` ("Fichas dos Pães") | `project_receitas_reais_dos_paes.md`: *"**Processo das 11 massas (92 etapas)** entrou no MESMO artifact (mesma URL), uma tabela por massa: fase (véspera · mistura · pointage · tourage · apprêt · forno), etapa, tempo, temperatura, nota."* **Não está no repo.** É a única fonte de temperatura real da casa que já existiu. |
| **L5** | `RecipeVersion.notes` **não tem destino na ficha** | `05-receitas-estrutura.md` §5.2 (no main) — e **continua verdadeiro hoje** | `services/recipe_book.py:333-338` (`_write_recipe`) escreve `name`, `output_sku`, `batch_size`, `steps`, `is_active`, `meta` — **`notes` não está na lista**. A anotação da versão morre no lado da autoria. Não há campo canônico que diga isso. |
| **L6** | O `missing_steps` com as palavras do dono | `shopman/backstage/data_readiness/operational.py:202-210` → *"Ficha executável existe, mas o modo de preparo não está registrado."* | Único leitor é o CLI `audit_recipe_material_day1`. Sem projection, sem tela, sem alerta. **Continua verdadeiro.** |
| **L7** | O irmão `04-*.md` da série de diagnóstico | — | A série tem `01`, `02`, `03`, `05`, `06`. **`04` nunca existiu** (`git log --all --diff-filter=A` → vazio). Buracos na numeração escondem que faltou algo. |

**Nota sobre a tarefa:** o `docs/plans/RECIPE-MODELING-BRIEF.md` **está rastreado** em `origin/main`
(186 linhas) — ao contrário do que supunha o enunciado. A cópia do worktree
`receitas-paes-producao-26a519` é anterior ao update de 24/09. E ele **já aponta** para o buraco,
`RECIPE-MODELING-BRIEF.md:43-46`:

> `5.` **Tempos e temperaturas por parte** (§7 Q4): desde 30/09/2026 a etapa é objeto
> \`{name, instructions?, target_seconds?, note?}\` (\`craftsman/recipe_steps.py\`), com tempo alvo
> por etapa; **temperatura e o vínculo etapa × parte seguem sem casa, e nenhuma tela de execução
> lê as etapas.**

---

## 4. As 4 perguntas do dono — a resposta JÁ está em algum lugar?

**Resposta curta: (a) sim, decidida em 16/09 e escrita em dois lugares — mas em nenhum deles *como
resposta a esta pergunta*. (b) meio: tempo sim (shipado), temperatura não. (c) não decidida — o código
respondeu por construção. (d) não decidida, e é a mais barata de fechar.**

| # | Pergunta | Estado | Onde está (com citação) |
|---|---|---|---|
| **(a)** | O operador **registra** a etapa, ou só **lê**? | ✅ **DECIDIDA — "só lê"**, em 16/09/2026. ⚠️ Mas escrita como *fato sobre `steps_progress`*, não como resposta a esta pergunta; e as duas fontes que a registram estão fora do doc canônico de vocabulário/ADR. | `data-schemas.md:1514`: *"o escritor \`CraftExecution.advance_step\` segue no Core, **sem chamador de superfície desde a decisão de 16/09/2026: a aba Produção tem uma ação só, Continuar**"*. Memória `project_producao_continuar_unico_e_timers_opcionais.md`: **"Sai**: … sequência obrigatória de etapas". Princípio do dono: *"se não obrigar vira adereço, se obrigar engessa"*. E `05-receitas-estrutura.md:441` diz que isso **é** a resposta, mas a enquadra como decisão a tomar. ⚠️ **A recomendação do agente em D5 é a mesma ("só lê, por enquanto")** — ninguém a ratificou. |
| **(b)** | A etapa tem **tempo** e **temperatura**? | ⚠️ **METADE.** **Tempo: SIM** — shipado em `recipe_steps.py:29` (`target_seconds`), com a colisão de nome já documentada em `data-schemas.md:1576`. **Temperatura: NÃO EXISTE em lugar nenhum** — e nunca foi decidida. | **Nada lê o tempo:** `data-schemas.md:1593-1595`: *"⚠️ **Nenhuma tela de execução lê as etapas.** KDS, Preparação (ticket de pesagem), etiqueta e board não mostram o modo de fazer, e **\`target_seconds\` não liga temporizador nenhum**. Levar as etapas ao chão de fábrica é decisão do dono, ainda aberta."* **Temperatura:** as chaves `prep_time_min`/`bake_temp_c` citadas no `help_text` de `Recipe.meta` são **isca** — nenhum código de produção as lê (`05-receitas-estrutura.md` §7.3). O dossier real de temperatura da casa (92 etapas de 05/09) **está só no artifact** (L4). |
| **(c)** | A anotação mora na **versão** ou na **ficha**? | ❌ **NÃO DECIDIDA** para o nível global. ✅ **Resolvida por construção** no nível do **item** (mora na fórmula → chega em `RecipeItem.meta["note"]`) e no nível da **etapa** (`note` dentro do objeto da etapa, na versão). | Recomendação escrita, marcada como decisão do dono — `05-receitas-estrutura.md:449`: *"A anotação prática é da VERSÃO (história, versionada) ou da FICHA (atual, mutável)? \`RecipeVersion.notes\` já é versionada e imutável; um \`Recipe.notes\` seria mutável e fora do governo do \`publish_version\` (ADR-027 §2). Recomendo versão. **Decisão do dono.**"* **O código já decidiu na prática:** `_write_recipe` (`recipe_book.py:333-338`) **não copia** `version.notes` — não há destino. E `data-schemas.md:1606` reforça para o item: *"a versão publicada decide se ela existe."* |
| **(d)** | **"Passos"** ou **"Etapas"**? | ❌ **NÃO DECIDIDA — e é a mais barata e a mais urgente.** A colisão está **viva** no código hoje. O doc de vocabulário fechado **não a cobre**. | **Modelo/Admin dizem "Etapas":** `models/recipe.py:69`, `models/recipe_book.py:207`, `contrib/admin_unfold/admin.py:156` — todos `verbose_name=_("Etapas")`. **Toda a tela diz "Passos":** `surfaces/production-nuxt/app/pages/recipes/[ref]/index.vue:405`, `[ref]/edit.vue:573` (*"Passos (um por linha)"*), `new.vue:439` (*"Passos lidos"*). **O doc canônico se contradiz:** a seção se chama "**Recipe.steps**" e a tabela diz "Etapas", mas `data-schemas.md:1589` fala em *"as telas do inventário … via \`RecipeStepProjection\`"*. ⛔ **`docs/reference/suite-vocabulary.md` — o doc dos vocabulários fechados — NÃO tem `passo` nem `etapa` em lugar nenhum** (`grep -n -i -E "passo\|etapa\|receita\|ficha\|procedimento"` → só as linhas 58, 59, 163, 164, 237, todas sobre outros assuntos). A §1 ("O que já está decidido — e não se reabre") **não inclui este eixo**. Recomendação do agente em D5: **"Etapas"** (*"(d) 'Etapas' (já é o rótulo do campo)"*). |

⚠️ **`05-receitas-estrutura.md:452` diz por que (d) é urgente:** *"Escolher uma antes de a superfície
crescer — é rename barato hoje e caro depois."*

---

## 5. Índice de evidência (para o próximo não repetir a busca)

**No `origin/main` (canônico):**
- `docs/reference/data-schemas.md:1559-1595` — `Recipe.steps / RecipeVersion.steps` (**a forma canônica**)
- `docs/reference/data-schemas.md:1514` — `steps_progress` + a decisão de 16/09
- `docs/reference/data-schemas.md:1606` — `RecipeItem.meta["note"]`
- `docs/reference/data-schemas.md:1544` — a linha do `meta["steps"]` **removida em 30/09** (era doc prospectiva que virou ficção; a correção foi executada)
- `docs/reference/suite-vocabulary.md` — **não cobre** o eixo passo/etapa (lacuna)
- `docs/decisions/adr-027-recipe-book-authoring-vs-execution.md` — autoria ≠ execução; publicar é o escritor único; a `Recipe` não muda de significado
- `docs/plans/RECIPE-INVENTORY-PLAN.md:68-69` — `steps` na versão, "vai para `Recipe.steps` ao publicar"
- `docs/plans/RECIPE-MODELING-BRIEF.md:28-46` — o que ficou superado e o que continua aberto (§0)
- `docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md:210-237` — **O5 · Receitas: modo de fazer — "PROCEDE, e é grave"**, com a fatia A e as 4 decisões do dono
- `docs/plans/WP-RECEITAS-DA-CASA.md` — F4 ("tempo e **ordem dos passos**"), 73 linhas, sem decisão de procedimento
- `docs/reports/go-live-acceleration-20260930-diag/05-receitas-estrutura.md` — **o diagnóstico completo** (469 linhas). §7.2 = as 5 decisões; §6.1 Opção A; §6.3 ⛔ "**NÃO criar `RecipeStep` como modelo**"
- `packages/craftsman/shopman/craftsman/recipe_steps.py` — a implementação e a sua docstring
- `packages/craftsman/shopman/craftsman/services/recipe_book.py:333-338` — o que o publish copia (e o que não copia)

**Fora do `origin/main` (o que se perdeu):**
- **`claude/turno-autonomo-coordenacao-76dc5f` → `docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md`, seção D5** ← **a resposta à pergunta do dono**
  `git show 821750516:docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md`
- `~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/`:
  `project_linguagem_de_passos_da_receita.md` (**a notação própria do dono**) ·
  `project_producao_continuar_unico_e_timers_opcionais.md` (**a decisão de 16/09**) ·
  `project_receitas_reais_dos_paes.md` (**o processo das 92 etapas + as 5 correções do dono**) ·
  `feedback_production_steps_must_have_timestamps.md` (o dono, 14/08: *"etapas de produção é pra ter timestamps sim, ok! isso foi concebido desde o início"*) ·
  `feedback_recipe_is_raw_dough_catalog_is_baked.md` · `project_fichas_reais_da_casa.md` ·
  `feedback_a_decisao_ja_tomada_mora_no_docs_vasculhe_antes_de_perguntar.md`
- Artifact `b8cd4fc0-c136-47d0-aac2-0a4c912e0e59` ("Fichas dos Pães") — **o único lugar com as 92 etapas de tempo e temperatura da casa**

---

## 6. Recomendação de fechamento (o que fazer com isto)

1. **Mergear (ou reaproveitar) o `PENDING-DECISIONS.md` do branch `claude/turno-autonomo-coordenacao-76dc5f`.**
   Ele contém **D1–D16**, não só D5 — é o registro mais completo de decisões abertas do dono e **não
   está no `main`**. Mover o que for durável para `docs/coordination/DECISIONS.md` (**o ledger
   append-only**, que hoje tem `D-001`…`D-009` e **nenhuma entrada sobre receitas/procedimento**).
2. **Levar as 4 perguntas ao dono com as recomendações já escritas** (D5) — ele nunca as viu.
   Perguntar **também pela notação própria dele** (L3): ele pediu explicitamente para ser lembrado.
3. **Fechar (d) "Passos" vs "Etapas" agora**, e **registrar em `suite-vocabulary.md` §1** — é o doc
   que existe exatamente para isto e está com a lacuna.
4. **Registrar temperatura como decisão aberta** com o custo dela (a armadilha da escala afim) e
   **resgatar as 92 etapas do artifact para o repo** (L4) antes que o artifact se perca — o dono já
   perdeu um scratchpad inteiro nesta frente (`project_receitas_reais_dos_paes.md`: *"⚠️ O scratchpad
   da sessão foi limpo no meio do trabalho"*).
5. **`RecipeVersion.notes` continua sem destino** (L5) — decidir se vai à ficha ou se a doc declara
   que a anotação global mora só na versão.

---

*Relatório D5 · agente de análise (DSH) · árvore de leitura `origin/main` = `beb9bf973` · 2026-10-01.
Nenhum comando git mutante; nada editado além deste arquivo.*
