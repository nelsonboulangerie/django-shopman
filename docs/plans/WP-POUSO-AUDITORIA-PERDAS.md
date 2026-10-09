# WP-POUSO-AUDITORIA-PERDAS: o que do Gestor e do kit existe fora do pouso

- **Data:** 08/10/2026, 22h.
- **Ref auditada:** `origin/claude/pouso-nuxtui-operador` = `f9a9ae9f8` (PR #1555).
- **Escopo:** correções de tela do Gestor (`surfaces/orders-nuxt`) e do kit (`surfaces/operator-kit`).
- **Pedido:** o dono reviu as prévias do pouso e sentiu falta de correções já feitas
  ("padding superior na Linha do tempo da página do detalhe do pedido no Gestor, entre
  outros detalhes espalhados"). Suspeita: trabalho perdido entre sessões.
- **Modo:** só leitura. Nada foi corrigido; esta é a lista para a correção que vem depois.

## Veredito

1. **No git, nenhuma correção commitada do Gestor ou do kit ficou fora do pouso.** Todo head
   de PR da pilha (#1518 a #1554, menos o #1539 de propósito) é ancestral do pouso; o `main`
   também; nenhum dos 53 merges do pouso perdeu linha na resolução de conflito; os commits
   de outros branches que não estão no pouso são cópias equivalentes ou frente fechada por
   decisão.
2. **A falta que o dono viu tem causa medida, e é a prévia, não o código.** De 19:22 a
   22:03 a prévia do Gestor (`viewer-gestor`, porta 33124, e o túnel) serviu o `c68ddd747`
   (#1545 com o K4), que **não tinha os cinco PRs irmãos**: #1520, #1522, #1524, #1526 e
   #1527. A Linha do tempo com respiro é o #1526. Desde 22:03 a prévia serve o pouso, e a
   Linha do tempo tem 16 px em cima e embaixo (medido no navegador).
3. **A prévia ainda mente num ponto: o mock está velho.** O mock da porta 38893 (pid 16467)
   subiu às 20:00, com a worktree no `c68ddd747`, e guarda a fixture antiga na memória. Por
   isso a Linha do tempo ainda mostra "06/10 às 15:04 · - → Novo", que o #1526 corrigiu no
   servidor e na fixture. Reiniciar o mock resolve; o código do pouso está certo.
4. **Perda real, uma só:** trabalho **nunca commitado** na worktree
   `agent-a411fd0f4e66e733c` (branch local `claude/operador-nuxtui-onda0-conjunto-minimo`,
   sem remoto). O principal é o selo "ao vivo" do cabeçalho em português, com quatro tons,
   que o próprio arquivo diz "confirmado pelo dono em 08/10/2026 (onda 0.M)". O pouso ainda
   mostra "On"/"Off".
5. **O resto que falta é pendência que nunca foi feita**, não perda: itens F4, F7 e F8 e
   três P1 do laudo `WP-GESTOR-CANON-LAUDO.md` (tabela no fim).

## Achados

### A1. Prévia do Gestor sem os cinco PRs irmãos, de 19:22 a 22:03 (explica a Linha do tempo)

- **Na língua do operador:** a prévia mostrava a Linha do tempo do detalhe encostada no
  cabeçalho e na base do cartão; a barra de lote dizia "Concluir" em vez de "Sair da
  seleção"; o Em andamento não estava em duas linhas; a Saída larga tinha faixa vazia; o
  detalhe do pedido iFood com negociação caía com erro 500.
- **Onde:** worktree `.claude/worktrees/viewer-gestor`, reflog em
  `.git/worktrees/viewer-gestor/logs/HEAD`.
- **Por quê:** a prévia foi montada a partir do `origin/claude/gestor-conjunto-minimo`
  (#1545) com merges locais do K4. O #1545 está empilhado no #1533, e os irmãos #1520,
  #1522, #1524, #1526 e #1527 saem do #1519 por outro galho. Eles só entraram no pouso às
  20:54 (`36b727468`, `07318caae`, `6e8ee37a3`, `505d70211`), e a prévia só trocou para o
  pouso às 22:03.
- **Evidência:**

  ```
  $ tail .git/worktrees/viewer-gestor/logs/HEAD
  1bb966332 → c68ddd747  1791498171 (08/10 19:22)  merge origin/claude/operador-nuxtui-k4-rail-tres-estados
  c68ddd747 → f9a9ae9f8  1791507839 (08/10 22:03)  checkout: ... to origin/claude/pouso-nuxtui-operador

  $ git merge-base --is-ancestor <head do PR> c68ddd747
  #1520 2ee72e004 NAO · #1522 06c6e7519 NAO · #1524 39265d11d NAO
  #1526 846677ab3 NAO · #1527 02abf2872 NAO
  #1518 SIM · #1519 SIM · #1521 SIM · #1528 SIM · #1530 SIM

  $ git cherry -v c68ddd747 846677ab3
  + 2ee72e004 fix(orders): o detalhe do pedido iFood com negociação não cai mais com 500
  + 743f2c18f WIP fix(gestor): Linha do tempo do detalhe com respiro; status sem "- -> Novo"
  + 846677ab3 fix(gestor, operator-kit): negociação iFood em card próprio; ...
  ```

- **Estado agora:** resolvido no pouso e na prévia (ver A2 para o que ainda aparece).

### A2. Mock da prévia com a fixture de antes do #1526

- **Na língua do operador:** a Linha do tempo do detalhe diz "06/10 às 15:04 · - → Novo" e
  "- → Aceito". O título já é o status; o "- →" repete e confunde.
- **Onde:** processo `node tests/visual/mockBackend.mjs` (pid 16467, `MOCK_PORT=38893`,
  iniciado às 20:00 em `viewer-gestor/surfaces/orders-nuxt`).
- **Por quê:** o mock lê as fixtures ao subir. Às 20:00 a worktree estava no `c68ddd747`,
  sem a fixture regravada pelo `846677ab3`. A troca para o pouso às 22:03 reiniciou o Nuxt
  (22:04), não o mock. O arquivo em disco já está certo.
- **Evidência:**

  ```
  $ curl -s 127.0.0.1:38893/api/v1/backstage/orders/WEB-261006-H58/ | ...timeline
  [{"label": "Novo", ..., "detail": "- -> Novo"}, {"label": "Aceito", ..., "detail": "- -> Aceito"}]

  $ python3 (conta "- -> " em viewer-gestor/.../fixtures/recorded-django.json)
  0

  $ git grep -n "def _event_detail" origin/claude/pouso-nuxtui-operador -- shopman/backstage/projections/order_queue.py
  2794 ... "Mudança de status não ganha detalhe próprio ... saía "- -> Novo" (dono, 08/10/2026)"
  ```

- **O que fazer:** reiniciar o mock da 38893 (e por precaução o da 38894 do B.I.). Também
  deixa de faltar na prévia a galeria completa do #1520 (`galleryCards.mjs`), que mudou
  depois das 20:00.

### A3. Selo "ao vivo" em português com quatro tons: só na worktree, nunca commitado (PERDA)

- **Na língua do operador:** todo cabeçalho do Gestor mostra "On 21:27". É inglês e não diz
  o quê. A versão feita e não guardada mostra: ao vivo, ponto verde e a hora ("10:12");
  calmo, neutro e a cadência por extenso ("Atualiza a cada 60 s"); atrasado, âmbar,
  "Última leitura às 10:04"; desligado, ponto vermelho, "Sem conexão". É o P0-5 / F3 do
  laudo do Gestor.
- **Onde:** worktree `/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agent-a411fd0f4e66e733c`,
  branch local `claude/operador-nuxtui-onda0-conjunto-minimo` (sem remoto), HEAD
  `5574d28a9`. Arquivo `surfaces/operator-kit/app/components/OperatorLiveStatus.vue`
  (modificado 08/10 14:05:53). No pouso, `OperatorLiveStatus.vue:36`:
  `const state = computed(() => (props.tone === "off" ? "Off" : "On"));`.
- **Por quê não está:** a frente "onda 0.M" (conjunto mínimo) ficou sem commit nesta
  worktree; o conjunto mínimo foi refeito e commitado no K3 (#1543, `3bfc8fdf1`), que não
  trouxe o selo. A descrição do #1543 só cita o `OperatorLiveStatus` para dizer que o selo
  passou a herdar a variante do tema.
- **O mesmo diff não commitado traz mais, e aqui o K3 decidiu diferente por escrito:**
  - tipografia: os papéis `op-*` remapeados para os cinco tamanhos (`operator-suite.css`).
    O #1543 diz "os 5 tamanhos e os 2 pesos estão documentados; a trava cobre só o seguro".
    O remapeamento das classes não entrou;
  - raio único `--ui-radius: 0.3125rem` (`operator-theme.css`). O #1543 diz "Raio: não
    entrou" e explica por quê. Não é perda: é decisão posterior;
  - `OperatorKitchenSinkMinimalSet.vue` (arquivo novo, não rastreado) e textos do README,
    do `app.config.ts`, `UiButton`/`UiIconButton`/`UiNativeSelect` (`@deprecated`). O pouso
    já tem a seção "Conjunto mínimo da suíte" no README (`README.md:458`), com outro texto.
- **Evidência:**

  ```
  $ (cmp de cada arquivo da worktree contra 5574d28a9)
  M surfaces/operator-kit/README.md
  M surfaces/operator-kit/app/app.config.ts
  M surfaces/operator-kit/app/assets/css/operator-base.css
  M surfaces/operator-kit/app/assets/css/operator-suite.css
  M surfaces/operator-kit/app/assets/css/operator-theme.css
  M surfaces/operator-kit/app/components/OperatorKitchenSink.vue
  M surfaces/operator-kit/app/components/OperatorKitchenSinkDashboard.vue
  M surfaces/operator-kit/app/components/OperatorKitchenSinkExercises.vue
  M surfaces/operator-kit/app/components/OperatorLiveStatus.vue
  M surfaces/operator-kit/app/components/UiButton.vue
  M surfaces/operator-kit/app/components/UiIconButton.vue
  M surfaces/operator-kit/app/components/UiNativeSelect.vue
  M surfaces/operator-kit/app/fixtures/operatorKitchenSink.ts
  M surfaces/operator-kit/tests/components/SuiteChrome.test.ts
  M surfaces/operator-kit/visual/capture-before-after.mjs
  ? surfaces/operator-kit/app/components/OperatorKitchenSinkMinimalSet.vue

  $ (linhas do OperatorLiveStatus.vue da worktree ausentes do pouso): 32 de 37
  + const OFF_LABEL = "Sem conexão";
  + const TONE_COLOR = { live: "success", calm: "neutral", late: "warning", off: "error" } as const;
  + if (props.tone === "late") return props.time ? `Última leitura às ${props.time}` : props.label;

  $ git log --all -S"OperatorKitchenSinkMinimalSet"   → nenhum commit cria o arquivo
  $ git ls-remote --heads origin claude/operador-nuxtui-onda0-conjunto-minimo   → vazio
  ```

- **O que fazer:** antes de qualquer limpeza de worktree, guardar esse diff (commit num
  branch de resgate ou `git diff > patch`). Na correção, trazer o `OperatorLiveStatus` (e o
  teste `SuiteChrome.test.ts` que o acompanha) e conferir se a trava do piloto do Gestor
  (`canonicalPilot.guardrails.test.ts`, que exigia "On/Off") muda junto, como o laudo pede.

## A Linha do tempo do detalhe, versão por versão

| Quando | Ref | O que fez com o respiro |
|---|---|---|
| 07/10 10:54 | `52bbec51e` (#1518) | O comentar foi para o `#footer` do card, o que deixa o `NuxtTimeline` como filho único do corpo. |
| 07/10 18:26 | `947cc0881` (#1519) | Regressão: a regra do card `has-[>[data-slot=root]:only-child>[data-slot=item]]:py-0`, feita para o Accordion do Em andamento, também casou com o `NuxtTimeline` (mesma anatomia raiz > item, filho único desde a linha de cima). Corpo do card ficou `padding: 0 16px`. |
| 08/10 | `743f2c18f` (#1526) | Correção: a regra passa a exigir `[data-state]`, que só o item do Accordion tem. |
| 08/10 | `846677ab3` (#1526) | Completa: negociação iFood em card próprio (`#after-summary`), prazo "08/10 às 07:49", fixture sem "- -> Novo". |
| 08/10 20:54 | `36b727468` (pouso) | Merge do #1520 e do #1526 no pouso, sem conflito nesses arquivos (remerge-diff vazio). |
| agora | `f9a9ae9f8` (pouso) | `surfaces/operator-kit/app/app.config.ts:201`: `body: "p-4 sm:p-4 has-[>[data-slot=root]:only-child>table]:p-0 has-[>[data-slot=root]:only-child>[data-slot=item][data-state]]:py-0"`. É a versão certa. |

**Medido na prévia (pouso, 22:20, `/WEB-261006-H58` a 379 px):** corpo do card "Linha do
tempo" com `padding-top: 16px` e `padding-bottom: 16px`; os itens do `NuxtTimeline` não têm
`data-state` (o componente só o põe com `v-model`/`default-value`, `Timeline.vue:47-55` do
Nuxt UI 4.11.3), então o `py-0` não casa.

## Onde se procurou, e o que se achou

### Branches com commits fora do pouso que tocam Gestor ou kit

Comando: `git branch -a --no-merged origin/claude/pouso-nuxtui-operador`, filtrado por
`git rev-list --count pouso..<branch> -- surfaces/orders-nuxt surfaces/operator-kit`;
depois `git cherry -v pouso <branch>` (`-` = cópia equivalente já no pouso).

| Branch | Fora do pouso | Situação |
|---|---|---|
| `claude/gestor-toolbar-calendario` (local) | 5 merges | Merges locais dos irmãos, divergente do remoto (7 atrás, 11 à frente). `git cherry` não mostra nenhum `+`; remerge-diff dos 5 merges nos caminhos do app: 0 linhas. Nada a recuperar. |
| `claude/gestor-local-preview-stack` (local) | 4 | Todos `-` no `git cherry`: viraram #1521, #1522, #1524 e o Accordion do #1524. |
| `codex/orders-canonical-shell` (PR #1516) | 33 | Fechado por decisão do dono em 07/10 ("a migração do Gestor segue pelo #1518"). Não é perda. O que o laudo aproveitava dele (toque de 44/48 px só no ponteiro grosso, alvo do FilterChip) está na frente F9 do laudo, aberta. |
| `codex/orders-canonical-recovery` (worktree Codex) | 1 commit + 63 arquivos não commitados | Ver "Worktrees" abaixo. O commit (harness visual) tem equivalente no pouso (`tests/visual/*`). |
| `codex/nuxt-ui-form-controls`, `codex/wp-nuxt-ui-forms-sequence` | 1 cada | `-` no `git cherry`: já entraram. |
| `claude/detalhe-do-pedido-compartilhado` | 1 (`5c37b5812`, "wip ... antes da recuperação", 28/09) | Substituído por `51273000f` (no pouso). |
| `claude/clientes-no-gestor-tela`, `-api`, `claude/tres-perfis-fiscais` | 1 a 5 | Todos `-`: entraram no `main` em 24/09. |
| `codex/orders-validation-*`, `codex/orders-pre-brief-20260911` (10 e 11/09) | 18 a 56 | Anteriores à migração. O markup deles morreu com ela; a lógica (intenções, rascunhos de caixa, recibos) existe no `main` com outros commits. Fora do escopo desta auditoria e não conferido linha a linha (ver a drenagem de 16/09 antes de mexer). |
| dependabot e `rescue/*`, `adv/*`, `golive-rebase/*` (agosto e setembro) | 1 a 6 | Fora do escopo (versões ou sondas de integração). |

### PRs abertos e fechados sem merge

`gh pr list --state all --limit 200`, e para cada um não mergeado
`git merge-base --is-ancestor <headRefOid> pouso`:

- **Ancestrais do pouso:** #1518, #1519, #1520, #1521, #1522, #1524, #1525 (fechado),
  #1526, #1527, #1528, #1530, #1531, #1532 (fechado), #1533, #1534, #1535, #1536, #1540,
  #1541, #1542, #1543, #1544, #1545, #1546, #1547 a #1554.
- **Fora, de propósito:** #1539 (proposta do Kitchen Sink, material de decisão).
- **Fora, fechado por decisão:** #1516 (acima).
- **Os demais fora** são Dependabot ou não tocam Gestor/kit (#1424, #1418, #1354).

### `main`

- `git merge-base --is-ancestor origin/main origin/claude/pouso-nuxtui-operador` → sim.
- `git log 838ce00e6..origin/main -- surfaces/orders-nuxt surfaces/operator-kit` → vazio:
  depois da base da migração, o `main` não tocou nesses caminhos, então não há correção do
  `main` que o pouso possa ter desfeito.
- Os 53 merges de `origin/main..pouso`, com `git show --remerge-diff -- surfaces/orders-nuxt/app surfaces/operator-kit/app`:
  só `505d70211` e `6e8ee37a3` tiveram conflito (em `app.config.ts`), e as duas resoluções
  mantiveram os dois lados (o comentário do `[data-state]` e o do destaque; o comentário
  do card aninhado e o `accordion.label`).
- As deleções grandes de `git diff origin/main pouso -- surfaces/orders-nuxt/app` são a
  própria migração (snapshot `7e6bb83de`, pai = `838ce00e6`). O que ela apagou sem decisão
  já está no laudo (P0-6, `PhoneExitList`).
- Sobrevivência linha a linha: cada linha adicionada por cada commit não-merge de
  `838ce00e6..pouso` foi procurada no pouso. As que sumiram foram removidas por commits
  posteriores e deliberados da pilha (ex.: `URGENT_REMINDER_MINUTES = 1` virou o intervalo
  adaptativo `reminderIntervalMs` com piso de 1 min, `suiteChrome.ts:360`; os quatro
  `NuxtInput type="date|time"` do período do canal viraram `UiDateRangeField` +
  `UiTimeRangeField` em `5ff5f3652`; `variant="subtle"` saiu dos selos pelo K3). Nenhuma
  remoção veio de merge.

### Worktrees (inclusive `~/.codex/worktrees`)

Os arquivos de cada worktree em `surfaces/orders-nuxt/app` e `surfaces/operator-kit/app`
foram comparados com o HEAD dela (sem `git -C`, comparando o arquivo com
`git show <HEAD>:<arquivo>`), mais os não rastreados.

| Worktree | Não commitado | Situação |
|---|---|---|
| `.claude/worktrees/agent-a411fd0f4e66e733c` | 16 arquivos do kit | **PERDA (A3).** |
| `~/.codex/worktrees/orders-canonical-recovery` | 63 arquivos (Gestor e kit) + `OperatorSuiteShell.vue` não rastreado | Última edição 07/10 00:04, antes do snapshot `7e6bb83de` (07/10 10:30, "cópia fiel de /private/tmp/orders-canonical-stage"). Comparado depois de passar o Prettier nos três lados: o que sobra são variantes anteriores que a pilha trocou de propósito (alturas `h-control`, cartões no lugar de modal, `NuxtFormField` do comentar no corpo). Ex.: a `OperatorOrderTimeline.vue` dela tem o comentar dentro do corpo, a versão que causava o problema da Linha do tempo. Nada a trazer. |
| `~/.codex/worktrees/164b` (`codex/operator-kitchen-sink`) | 2 arquivos, 06/10 17:14 | 4 linhas de comentário sobre altura de controle no ponteiro fino; a ideia é a do #1516 (F9). Nada a trazer. |
| `.codex-worktrees/...whatsapp-golive-unblock-20260926` | kit inteiro ausente | Checkout esparso de outra frente. Não é trabalho. |
| demais 55 worktrees | nada nesses caminhos | inclusive `viewer-gestor`, `gestor-detalhe-layout`, `gestor-aviso-critico`, `gestor-menus-dropdown`, `gestor-toolbar-calendario`, `gestor-local-preview-1d5a90`, `orders-nuxt-ui-migration-b4c49c` e o checkout principal. |

### Outros lugares

- `git stash list`: vazio.
- `/private/tmp/orders-canonical-stage`: não existe mais; o conteúdo é o `7e6bb83de`.
- Scratchpad da sessão de migração, `gestor-conjunto/*.patch` (08/10 18:56 a 18:59): o
  `gestor-conjunto-minimo.patch` final está no pouso (todas as linhas de app presentes); o
  `u0.patch` e o `actions.patch` são rascunhos (`color: 'neutral'` nos itens de menu) que o
  patch final já não trazia.

## Laudo do Gestor (`WP-GESTOR-CANON-LAUDO.md`), item a item

| Item | O que é | No pouso? | Onde |
|---|---|---|---|
| P0-1 | Detalhe iFood com negociação caía com 500 | sim | #1520, `OrderIFoodNegotiations.vue` com `placeholder` |
| P0-2 | Cabeçalho apagou o `#below` (abas de Ajustes do PDV) | sim | #1521 |
| P0-3 | "Concluir" da barra de lote | sim | #1522, "Sair da seleção" |
| P0-4 / F1 | CI dos herdeiros | sim, menos os 2 vermelhos do tema que pedem o aceite do dono | saúde da pilha |
| P0-5 / F3 | Selo "On/Off" em inglês, binário | **não; feito e perdido** | A3 |
| P0-6 / F7 | Saída do celular sem deslizar para entregar e sem polegar | não; nunca feito | `PhoneExitList` só existe antes do snapshot; decisão 2 do laudo |
| P1-1 / F2 | Data, hora e período nativos | sim | `OperatorPeriodPicker.vue:339, 348, 381` (`UiDateField`); `ChannelPeriodCalendar.vue:17, 30` (`UiDateRangeField`, `UiTimeRangeField`); nenhum `type="date|time"` no Gestor nem no kit |
| P1-2 / F4 | Aviso leva ao pedido, mas não à resposta | não; nunca feito | `[ref].vue` sem `useNextFocus` nem foco no `#ifood-negotiations` |
| P1-4 | Barra do celular corta rótulos | não conferido em tela | K4 refez a barra inferior |
| P1-5 / F6 | Dois ⋯, dois toasters | ⋯ sim (`OrderCardMenu.vue:107`, `NuxtDropdownMenu`, #1530); `OperatorSonner` não existe mais no kit | |
| P1-6 / F8 | Vocabulário | não; nunca feito | "Ciente de todos" (`BoardMenu.vue:54`), "Agendados" (`index.vue:1996`, `OrderCard.vue:523`), "Etapa" (`index.vue:273`, `board.ts:616`), "Falha na ação. Tente de novo." (`useOrdersBoard.ts:616`) |
| P1-7 | "+9" soma pedidos que pedem você com os em andamento | não; nunca feito | `queue.ts:275-292` (`restLine`) |
| P1-8 | Tempo congelado na Lista | não; nunca feito | `index.vue:1834` usa `elapsed_seconds` |
| P2-9 | Spinner à mão | não; nunca feito | `index.vue:1515, 1526`, `CustomerMergeDialog.vue:286`, `OperatorReasonDialog.vue:183`, `OperatorSuiteSearch.vue:426`, `catalog.vue:1812` |
| #1526 "Falta" 1 a 4 | Resumo iFood no padrão, negociação em card próprio, prazo curto, fixture | sim | `846677ab3` |

## Lista para a correção

1. **Reiniciar o mock da prévia do Gestor** (38893) e, por precaução, o do B.I. (38894).
   Sem isso a Linha do tempo segue mostrando "- → Novo" e o dono vê de novo uma correção
   "perdida" que está no código.
2. **Resgatar o diff da worktree `agent-a411fd0f4e66e733c`** antes de qualquer limpeza, e
   trazer ao pouso o `OperatorLiveStatus` em português com os quatro tons (P0-5/F3), com o
   teste dele e a trava do piloto. Tipografia e raio dessa worktree foram decididos de outro
   jeito no #1543: não trazer sem nova palavra do dono.
3. **Pendências do laudo que nunca foram feitas** (não são perda, mas são o que o dono vai
   continuar notando): F4 (aviso leva à resposta), F7 (Saída do celular, depende da decisão
   2 do laudo), F8 (vocabulário), P1-7 ("+N" sem soma), P1-8 (tempo vivo na Lista), spinners.

## O que não foi verificado

- Os commits de setembro do Codex (`codex/orders-validation-*`) não foram conferidos linha a
  linha contra o `main`: são anteriores à migração e o markup deles não existe mais.
- A barra do celular (P1-4) e o hydration mismatch (P1-3) não foram vistos em tela.
- Só a Linha do tempo foi medida no navegador; os demais itens estão por código e por git.
