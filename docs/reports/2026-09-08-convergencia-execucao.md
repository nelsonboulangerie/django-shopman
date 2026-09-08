# Convergência local · remoto · CI · deploy — relatório de execução

**Quando:** 2026-09-08, a partir de 17:48Z · **Host:** `macpab.local`
**Escopo:** eliminar ou documentar pendência operacional. **Não** é revisão de
prontidão para go-live — os bloqueadores de go-live seguem intocados e fora
deste documento, de propósito.

| | |
|---|---|
| `origin/main` no início | `47d0b854b1086c1d5a172333f22e5ae9fab4c531` |
| **último SHA operacional verificado** | `a5a56033935797364e92f636425463036d6d31ac` — deploy, imagens, spec drift e smoke conferidos aqui |
| SHAs intermediários | `3fb0e575c` (#571) · `af4334835` (#572, documentação) · `a5a560339` (#573) |
| worktrees | 47 → **13** |
| branches locais | 451 → **30** |
| branches remotas | 381 → **21** |
| stashes | 0 (antes e depois) |
| backup | `/Users/pablovalentini/Documents/Backups/django-shopman-convergence-20260908-145122` |
| backup incremental | `/Users/pablovalentini/Documents/Backups/django-shopman-convergence-incremental-20260908-164027` |

⚠️ **Os dois SHAs são coisas diferentes, de propósito.** O relatório não pode
afirmar o SHA do commit que o contém — seria autorreferência impossível. Ele
registra o último SHA em que a verificação operacional foi FEITA; o SHA final de
`origin/main` depois do merge deste documento vai num comentário do próprio PR.

Entrada: o [handoff de convergência](2026-09-08-convergencia-local-remoto-deploy-handoff.md)
do agente externo, mais um laudo de coordenação próprio do mesmo dia. As duas
análises foram re-medidas contra `origin/main` antes de virarem tarefa.

---

## 1. O defeito que estava aberto: o Alpha Smoke morria dentro da própria espera

O gatilho pós-deploy **nunca rodou**. Medido: **16 de 16** execuções por
`workflow_run` canceladas, contra **14 de 14** verdes pelo `cron`.

A causa não era concorrência — três consertos anteriores atacaram esse lado. Era
aritmética, dentro do job: `timeout-minutes: 5` com `sleep 420` no primeiro
passo. Run [`34246964010`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34246964010):
começou 15:47:01Z, morreu 15:52:16Z, passo da espera `cancelled`, as quatro
asserções `skipped`.

E nada ficava vermelho, porque **run cancelado não fica vermelho**. O alpha passou
três dias sem guarda pós-deploy, e a ausência de sinal foi lida como sinal bom —
que é a classe de falha que este workflow existe para impedir.

**Consertado no [#571](https://github.com/nelsonboulangerie/django-shopman/pull/571)**, em três peças:

1. **A espera deixou de ser cega.** `scripts/wait_for_do_deployment.py` pergunta à
   DigitalOcean e solta quando existe deployment criado *depois* do fim do Deploy
   Images e ele está `ACTIVE`; grita em `ERROR`/`CANCELED`; segue adiante,
   dizendo por quê, quando o push não tocou componente publicável. Espera fixa
   erra dos dois lados — curta demais atesta a versão anterior (verde
   mentiroso), longa demais estoura o teto.
2. **`scripts/check_workflow_budgets.py`** recusa teto de job que não cabe a espera
   declarada (folga exigida: 300s). Roda no `Quality + deploy contract`.
3. **`STOREFRONT_URL` sem default.** O antigo apontava para `alpha.`, cortado em
   01/09. Sem a variável o job para na primeira linha e diz por quê; o gate
   recusa `alpha.`/`staging.` como fallback.

De carona, o falso positivo de `scripts/audit-branches.sh`: ele decidia por uma
janela dos 300 PRs mergeados mais recentes, e o PR #135 já tinha caído fora dela
— `feat/badge-issue-screen`, entregue, aparecia como ⚠️ UNMERGED. A janela virou
cache; quem decide é a pergunta dirigida ao branch. PR fechado ganhou linha
própria: é decisão registrada do dono, não esquecimento.

### O probe pagou por si

A espera nasceu como Python dentro de shell dentro de YAML e morreu no runner com
`syntax error near unexpected token '('` — três níveis de citação. A entrada
`probe_deploy_wait` do `workflow_dispatch` pegou isso **antes do merge**, no run
[`34260221819`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34260221819).
Depois de extrair a lógica para script, o run
[`34260514889`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34260514889)
passou de ponta a ponta.

---

## 1-bis. A segunda correção — o #571 não bastava

Uma releitura adversarial do próprio conserto achou **duas portas de falso verde**
que sobreviveram ao #571. As duas foram provadas rodando a função antiga, não
deduzidas.

**a) O deployment do merge ANTERIOR entrava pela folga de 120 segundos.** A
escolha era `created_at >= fim_do_deploy − CLOCK_SKEW`.

```
referência = 2026-09-08T19:01:30Z menos 120s
escolheu   = ANTERIOR  phase=ACTIVE
→ o run de B aprovaria o deployment de A: SIM — FALSO VERDE
```

Como A começou antes, ele fica `ACTIVE` primeiro; o smoke de B aprovava a versão
de A.

**b) "Não vi deployment" virava sucesso por presunção.** Esgotado o teto, o
script dizia *"provavelmente o push não tocou componente publicável"* e retornava
zero. Se a DigitalOcean falhasse em criar o deployment de uma publicação **real**,
o silêncio virava verde. O run sobre `af433483` mostrou o custo do lado inocente:
**43 leituras de `phase=NONE` e 15 minutos** para concluir algo que o Deploy
Images já sabia.

**O conserto (#573): correlação por digest.** Relógio só sabe dizer "depois de".
O que amarra um deployment a um build é `cause_details.docr_push.image_digest` —
o spec do App Platform aponta para a tag **móvel** (`web`, `pos`) e não carrega o
SHA.

O Deploy Images passa a **declarar** o que publicou: cada componente registra
`{tag, immutable_tag, digest}`, e um job `manifest` que roda **sempre** — inclusive
quando não há o que construir — compõe o artefato `published-components`.

| manifesto | comportamento |
|---|---|
| lista vazia | pula a espera **na hora**. Quem construiu é quem diz que não construiu |
| com componente | espera deployment cujo digest esteja nela. Teto esgotado **REPROVA** |
| ilegível | erro. Upload perdido e "nada publicado" não podem terminar iguais |
| `ERROR`/`CANCELED` **nosso** | reprova; de outro run, não |

Os seis cenários do contrato têm teste, mais o comportamental que impede a volta
do relógio: o deployment anterior aparece como **o mais novo** e ainda assim
perde.

De carona, `scripts/audit-branches.sh` ganhou o estado `◷ PR ABERTO`. Head de PR
em revisão — os sete do Dependabot — enchia a coluna ⚠️, que é a única que exige
ação humana. Com a classificação certa ela caiu de **10 para 2 linhas**.

## 2. Reconciliação — CONFIRMADO · ALTERADO · REFUTADO

### 2.1 Onde o agente externo estava certo e eu errado

| Afirmação | Veredito | Evidência |
|---|---|---|
| Alpha Smoke se autocancela por `timeout: 5` × `sleep 420` | **CONFIRMADO** (meu laudo dizia "causa desconhecida") | job 15:47:01Z→15:52:16Z; asserções `skipped` |
| `claude/intelligent-chaum-8d76b5` — PR #368 fechado como supersedido | **CONFIRMADO** (eu dizia "trabalho real sem PR") | comentário do dono no #368; `MaterialPicker.vue` está no `main` |
| `docs/repo-hygiene-proposal` — PR #201 fechado, itens resolvidos | **CONFIRMADO** (eu dizia "nunca lida") | comentário do dono no #201, sete seções conferidas |
| `feat/badge-issue-screen` é falso positivo da janela de 300 PRs | **CONFIRMADO** | #135 `MERGED`; a auditoria consertada agora o classifica certo |

### 2.2 Uma afirmação minha que caiu sozinha

| Afirmação | Veredito | Evidência |
|---|---|---|
| `claude/admin-busca-global` ⛔ apagaria `backstage/0014` aplicada no alpha | **REFUTADO** | `git merge-tree --write-tree` devolve **a árvore do `main`**: o merge é no-op, diff zero |

Eu li `git diff origin/main...branch` — três pontos, que compara a **base de
merge** com a ponta do branch e não faz ideia do que o `main` fez desde então. O
branch renumerou aquela migração; o `main` fez a mesma renumeração depois, por
outro caminho. Hoje a `0014` é `0014_alter_cashshift_difference_q.py`, outra
migração inteiramente. Para julgar se um merge é seguro, pergunte ao merge.

### 2.3 Medições que envelheceram entre a fotografia externa e a execução

| Item | Fotografia externa | Medido na execução | Veredito |
|---|---|---|---|
| `main` local | `291e0e063`, 24 atrás | `47d0b854b`, **0/0** | **ALTERADO** |
| worktrees | 46, 15 sujas, 2 locked | 47, 15 sujas, 2 locked | **ALTERADO** (número) |
| branches locais | 449 | 451 | **ALTERADO** |
| checkout raiz | `codex/pdp-bg`, 644 atrás | `codex/shopman-backstage-prod-hardening`, 644 atrás | **ALTERADO** (trocou de branch durante a sessão) |

### 2.4 Confirmado sem ressalva

| Item | Evidência |
|---|---|
| Nenhum blob único em `multiple-fixes-pdp-sms-pdv` (374 arquivos) | 374/374 já existiram no histórico do `main` |
| `wp-rename-chaves-legadas` editava migration aplicada; abordagem recusada | conteúdo entrou pela `0035_promessa_que_a_casa_honra.py`; `attribute_defaults.py` do `main` é **superconjunto** do rascunho |
| `pensive-jennings` é rascunho anterior; `main` mais completo | `main` tem o `line_id` e o `manual_lines` que o local não tem |
| `safety/preserve-*` só diverge em screenshot de QA | 9 `.alpha-tmp/*.png` únicos; **todo** o código já esteve no `main` |
| `ficha-de-produto-e-promessa` patch-equivalente | o blob do único arquivo já esteve no `main` |
| spec drift = `FOCUS_NFE_ENVIRONMENT` + `SENTRY_DSN` | `check_do_spec_drift.py` exit 0; live=88 versionado=90 |
| proveniência das 10 imagens | tag móvel == tag imutável do commit de **primeira linha** que toca cada filtro |
| smoke manual do vivo | ready 200 · 44 SKUs / 18 vendáveis · checkout 400 · SSR 200, 118337 bytes |

---

## 3. Decisão por PR aberto

Nenhum PR humano ficou aberto. Os sete do Dependabot têm **uma única causa**, e a
medição que a revelou desmente as duas análises anteriores.

### O que eu afirmei e o que aconteceu

Meu laudo dizia: *"#233 e #234 estão **verdes** e travados só por checks
obrigatórios que não existiam quando rodaram — um `@dependabot rebase`
destrava."* Era mensurável e estava errado.

Pedi o rebase. Os dois rebasearam para `3fb0e575` e passaram de **0 falhas para
13 falhas cada**. O verde era artefato de base velha: o #233 rodou pela última
vez contra um `main` de 19/08.

```
#233  ERROR: Cannot install django-filter<26.0 and >=25.2 …
      ResolutionImpossible                        (make install, job "Backstage seed")
#234  ERROR: Cannot install qrcode<8.0 and >=7.4 …
      ResolutionImpossible
```

**REFUTADO**, por ação minha. E a lição é a mesma que derrubou meu outro achado:
verde antigo não é verde — é uma medição sobre uma base que já não existe.

### A causa única

O Dependabot bumpa o pin em `constraints.txt`/`pyproject.toml` da raiz e **nunca
toca a faixa declarada** onde ela realmente vive. Toda bump que cruza uma faixa
declarada dá `ResolutionImpossible` no `make install` — e aí *todo* job Python
reprova junto, o que faz o PR parecer catastrófico quando o defeito é uma linha.

| PR | Faixa que barra | Onde ela está |
|---|---|---|
| **#233** `django-filter` 26.1 | `django-filter>=25.2,<26.0` | `packages/guestman`, `packages/offerman`, raiz |
| **#234** `qrcode` 8.2 | `qrcode[pil]>=7.4,<8.0` | `pyproject.toml` da raiz |
| #235 `webauthn` 3.0 | `webauthn>=2.8,<3` | `packages/doorman/pyproject.toml:15` |
| #232 `cbor2` 6.1.4 | `webauthn 2.8` pede `cbor2<6` | **depende do #235** — sozinho nunca passa |
| #550 `python-runtime` (14) | `Django>=6.0,<6.1` em **12** packages; `django-unfold 0.92` no inventário canônico | `packages/*/pyproject.toml`, `docs/reference/unfold_canonical_inventory.md` |
| #427 `nuxt-framework` | `npm ci` recusa o lockfile (bindings de plataforma) | falha só em `marketing-nuxt` |
| #428 `build-tooling` (20) | idem, 10 checks | regenerar com Node 22 / `npx npm@10` |

### Decisão: FREEZE DE CONVERGÊNCIA — exceções formalmente aceitas

Os sete continuam abertos, **rotulados e rastreados**, não esquecidos:

- rótulo `bloqueado: contrato de dependência` nos sete;
- comentário em cada um com a faixa exata que barra e o que exige;
- **issue de rastreamento #574**, com as três frentes: Python/Django/Unfold ·
  WebAuthn+cbor2 e qrcode/django-filter · Nuxt e build tooling;
- registrado que **#232 e #235 têm de ser avaliados juntos** — o #232 sozinho
  nunca passa.

**Segurança conferida antes de congelar:** zero alertas Dependabot abertos.

```bash
gh api repos/nelsonboulangerie/django-shopman/dependabot/alerts --paginate \
  --jq '[.[]|select(.state=="open")]|length'     # → 0   (291 no histórico, todos `fixed`)
```

Nenhum dos sete fecha alerta de segurança, então o congelamento não deixa
vulnerabilidade em aberto e nenhum vira WP urgente.

⛔ **Não alargar faixa do Core sem análise de compatibilidade e suíte completa.**
Foi para não fazer isso às pressas que eles foram congelados.

## 4. Branches e worktrees

**Worktrees: 47 → 13.** Todas as removidas passaram, no instante da remoção, por
três provas: `git status -uall` sem blob único, nenhum processo em `lsof +D`, e
conteúdo comparado com `origin/main` **e seu histórico**.

- 20 removidas limpas · 9 sujas com zero blob único · 4 sujas com rascunho
  provadamente supersedido (`main` é superconjunto em todos os arquivos)

### Os sete worktrees dirty, um a um

| worktree | entradas | processo | veredito |
|---|---:|---|---|
| checkout raiz | 158 (`-uall`) | **9 processos vivos**, inclusive um `codex` (PID 7573) | **MANTER** — D7 bloqueado; ver Pendências |
| `codex/repo-convergence-handoff` | 1 | não | **INCORPORADO** — o handoff virou o #572; blob idêntico ao histórico do `main`. Removida |
| `app-bug-fixes-790f0b` | 8 | não | **SUPERSEDIDO** — `main` tem 261 linhas a mais no `seed.py`, 28 no `attribute_defaults.py`; a edição da migration **aplicada** `0033` é a abordagem recusada pelo ADR-015, e o conteúdo entrou pela `0035` nova. Removida |
| `dreamy-lalande-e6053c` | 2 | não | **ARQUIVAR** — dois `prova-*.mjs` ad-hoc (47 linhas, porta `3014` no código, sem contrato). Archive validado nos dois backups. Removida |
| `eloquent-grothendieck-1945b1` | 2 | não | **SUPERSEDIDO** — `main` tem 48 linhas a mais em `modifiers.py` e 253 no teste; o local não tem o `line_id` nem o `manual_lines`. Removida |
| `receitas-paes-producao-26a519` | 1 | **SIM** | **MANTER ATIVO** — brief idêntico ao `main`, mas há sessão viva |
| `django-shopman-buyman-nuxt` | 41 (`-uall`) | não | **SUPERSEDIDO** — ver abaixo. Removida |

### Buyman: o worktree que era o Purchase antes de ter esse nome

Ele vivia fora da árvore, em `~/Documents/Codex/2026-08-25/revisar/work/` — **o
único dos 47 nessa condição**; todos os outros ficam sob o repo ou em
`/private/tmp`. E `~/Documents` é negado a esta sessão pelo macOS:

```
$ ls .../work/django-shopman-buyman-nuxt        → Operation not permitted
```

⚠️ **Aqui eu errei uma medição e ela quase virou conclusão.** Um `stat -f`
devolveu `tipo=Directory mtime=Sep 3` e eu tomei aquilo como prova de que o
diretório existia. Existia — mas quando o dono o moveu para
`~/Dev/Claude/`, o `stat` seguinte continuou "respondendo", e foi o `test -e`
que revelou a verdade. **Em caminho sob sandbox, `stat` não serve como prova de
existência; `test -e` serve.** Foi o dono, vendo `No such file or directory` no
caminho antigo, que me obrigou a olhar de novo.

Movido para fora de `~/Documents`, o worktree ficou legível — e o que ele
guardava desmente o nome:

**Os 41 arquivos não são `buyman-nuxt`. São `surfaces/purchase-nuxt/`.** O
worktree se chamava buyman, mas o código que ele produziu é o Purchase. É por
isso que `surfaces/buyman-nuxt` nunca apareceu em commit nenhum: nunca houve um.

Teste forte nos 41:

| resultado | arquivos |
|---|---:|
| blob idêntico a versão já no histórico do `main` | **25** |
| existe no `main` com conteúdo diferente | **16** |
| **caminho ausente do `main`** | **0** |

E nos divergentes o `main` é massivamente maior — `operations.py` 1195 linhas só
no main contra 156 só no protótipo; `projections/purchase.py` 366 contra 8.

**Veredito: SUPERSEDIDO**, com prova semântica. O `purchase-nuxt` do `main` é
superconjunto funcional do protótipo, está no ar como componente `purchase`.
Preservado no backup incremental (patch de 17 KB, archive de 26 arquivos e a
tabela de prova acima) e removido.

**Branches locais: 451 → 30. Branches remotas: 381 → 21.** Zero erros nos dois
lados. O critério foi o mais forte disponível, aplicado **branch a branch e
re-verificado no instante da remoção**:

- `git merge-tree --write-tree origin/main <sha>` devolvendo a árvore do `main`
  — merge no-op, conteúdo integralmente lá; ou
- `git rev-list --count origin/main..<branch>` igual a **zero** — a branch não
  tem um único commit fora do `main`.

Locais: 324 por ancestralidade (`git branch -d`), 8 por no-op de squash, 89 por
zero-ahead. Remotas: 357 por zero-ahead. Protegidas por construção: `main`, as em
uso por worktree, e todo head de **PR aberto**.

⚠️ Head de **PR fechado** eu protegi na primeira passada e depois soltei, de
propósito: o registro da decisão mora no PR, no GitHub, não na ref. Uma branch
com zero commit fora do `main` não guarda decisão nenhuma — guarda ruído.

Ficam as 6 remotas com delta real: 5 do Dependabot mais
`safety/preserve-current-work-20260828-login-handoff` e
`claude/ficha-de-produto-e-promessa`. Nenhuma tem código ausente do `main` — as
duas últimas foram provadas blob a blob.

---

## 5. Backup

`/Users/pablovalentini/Documents/Backups/django-shopman-convergence-20260908-145122`

| artefato | verificação |
|---|---|
| `git-metadata.tar.gz` (`.git` inteiro, 294 MB) | `tar -tzf` ok — 31 417 entradas |
| `reachable-refs.bundle` | `git bundle verify`: *"records a complete history"* |
| restauração de amostra | clone do bundle → **460 refs**, `origin/main` = `47d0b854b` |
| `fsck-unreachable.txt` | 6 347 linhas, tirado **antes** de qualquer limpeza |
| patches por worktree suja | `status`, `diff HEAD`, `diff --cached`, untracked em tar |
| `SHA256SUMS` | **129 arquivos, 129 OK** na conferência final |

⚠️ **114 e 129 não se contradizem.** 114 era a contagem no instante do backup
(17:51Z). Depois dele entraram os 15 manifestos de `limpeza/` — o registro do que
foi removido, que é justamente o que torna a limpeza auditável. `129 − 15 = 114`.
O `SHA256SUMS` foi regerado ao final e confere inteiro.

Prova de recuperabilidade **depois** da limpeza: três branches apagadas ao acaso
foram encontradas no bundle, com assunto legível.

### Backup incremental

`/Users/pablovalentini/Documents/Backups/django-shopman-convergence-incremental-20260908-164027`

Criado porque o backup original é de 17:51Z e o plano de Produção mudou às
19:01Z. Contém: o snapshot do plano com `sha256`, e `status`/`diff HEAD`/
`diff --cached`/untracked de cada worktree dirty **remedidos no momento da
remoção**, além dos manifestos do que foi apagado.

⚠️ Nenhum `git gc`, `git prune` ou `git worktree prune` foi executado.

---

## 6. Arquivos locais

| arquivo | decisão |
|---|---|
| handoff de convergência do agente externo | **PROMOVIDO** — PR #572. Vivia untracked numa worktree do Codex |
| **plano novo de Produção** (74.434 bytes) | **PRESERVADO fora do repo** — ver abaixo |
| 4 relatórios de 2026-08-28 no checkout raiz | **ARQUIVADOS** no backup. Prompts de execução já cumpridos, não entrega |
| `prova-clique.mjs`, `prova-feeds.mjs` | **ARQUIVADOS** e validados nos dois backups. 47 linhas somadas, porta `3014` no código, sem contrato |
| `.alpha-tmp/` (19 MB) | **ARQUIVADO** no backup; não commitado — screenshots de QA podem conter dado de sessão |
| `docs/plans/backstage-app-audits-2026-08-29/` | 20 arquivos em disco, **0 divergentes** do `main` (que tem 40; os 20 restantes são commits que o raiz não alcançou). Reconciliam sozinhos quando o checkout atualizar |

### O plano de Produção, que o backup original não cobria

`docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md`

```
tamanho : 74.434 bytes
sha256  : f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d
mtime   : 2026-09-08T19:01:04Z   ← DEPOIS do backup (17:51:22Z)
```

**Existe só no checkout raiz**, não está no `main` e não está em branch nenhuma.
Como foi modificado depois do manifesto do backup, ele **não estava
comprovadamente preservado** — e é a única cópia.

Snapshot com hash em `/Users/pablovalentini/Documents/Backups/django-shopman-convergence-incremental-20260908-164027/plano/`.

⚠️ **Não foi commitado, e não foi levado para branch.** É um plano de
implementação de outra frente, sua sessão dona segue viva no checkout raiz, e
misturá-lo ao PR de convergência seria decidir por ela. Seu backlog funcional
**não foi executado** — está fora do escopo desta tarefa, por instrução.

**Estado: preservado fora do repositório, mantido por sessão ativa.**

## 7. Verificação final

### O Alpha Smoke real, por `workflow_run` — as duas provas

**Prova 1 — o #571 destravou o gatilho.** Run
[`34263203082`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34263203082)
sobre `3fb0e575c`: primeiro `workflow_run` a terminar `success` depois de 16
cancelados seguidos, com as quatro asserções executadas.

**Prova 2 — o #573 correlaciona por digest.** Run
[`34273202170`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34273202170)
sobre `a5a560339`:

```
manifesto: "digest": "sha256:622f99027ff2597c0346c0da4cfb608d66205f33e2bac5cd38409aaf0c33dcf9"
publicados por este run: web
20:10:19Z  EM_CURSO  deployment=dd0d2f81 phase=PENDING_BUILD
20:10:41Z  EM_CURSO  deployment=dd0d2f81 phase=DEPLOYING     (×6)
20:12:54Z  ACTIVE    deployment=dd0d2f81 phase=ACTIVE
deployment dd0d2f81 ACTIVE com a imagem deste run.
/ready/ => 200 · 44 SKUs / 18 vendáveis · checkout => 400 · home => 200 (118337 bytes)
```

⚠️ Repare no que o log **não** diz: em nenhum momento ele escolhe "o deployment
mais recente". Ele segue `dd0d2f81` porque o digest daquele deployment está no
manifesto — e o digest do deployment ativo confere byte a byte com o publicado:

```
manifesto              : sha256:622f9902…
deployment ativo (DO)  : sha256:622f9902…
```

### Estado do SHA final

| verificação | resultado |
|---|---|
| checks do SHA final | **29 concluídos, 29 `success`**, zero falhas |
| Deploy Images | [`34273012954`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34273012954) `success` — rebuildou `web` |
| deployment ativo | `dd0d2f81-57cf-4b78-9403-8ee5d017cb71` · **ACTIVE 47/47** · digest confere com o manifesto |
| proveniência das imagens | 10 de 10 coerentes; `web` em `a5a560339357` |
| `scripts/check_do_spec_drift.py` | exit 0 — só `FOCUS_NFE_ENVIRONMENT` e `SENTRY_DSN`, ambas declaradas |
| smoke manual | ready 200 · 44 SKUs / 18 vendáveis · checkout 400 · SSR 200, 118337 bytes, contém "Nelson" |
| `main` local | **igual a `origin/main`** |
| editable installs | 14 de 14 resolvem para o checkout raiz — nenhum aponta para worktree removida |
| tags | locais e remotas idênticas |

## 8. Pendências restantes

**Convergência técnica concluída; permanecem apenas as exceções Dependabot
formalmente aceitas e/ou sessões ativas identificadas abaixo.**

Nenhuma delas é defeito aberto de CI, deploy ou integridade de repositório. Todas
dependem de **sessão viva, permissão do sistema, ou decisão sobre o Core**.

| # | Pendência | Causa medida | Dono | Próxima ação |
|---|---|---|---|---|
| 1 | **7 PRs do Dependabot** | bump cruza faixa declarada → `ResolutionImpossible` no `make install`. Zero alertas de segurança abertos | Pablo | issue **#574**, três frentes. #232+#235 juntos |
| 2 | **Checkout raiz 650 commits atrás e dirty** | **9 processos vivos com cwd nele**, inclusive um `codex` (PID 7573). O hook `guard-paralelo` bloqueia `checkout` ali de propósito, e contorná-lo é proibido | Pablo | encerrar/coordenar as sessões; então `git checkout main && git pull --ff-only`, `make install`, e a bateria de gates |
| 3 | **2 worktrees locked** (`agent-ab3dc373225cb0b4c`, `agent-ad44b5a41338740f7`) | **PID 7002 vivo** desde 06:02Z. `git worktree remove` recusou sozinho | sessão dona | encerrar a sessão; repetir status/backup; então remover |
| 4 | **`receitas-paes-producao-26a519` dirty** | processo vivo; o único arquivo é idêntico ao `main` | sessão dona | nada agora |
| 5 | **Plano de Produção não commitado** | única cópia, no checkout raiz, alterado 19:01Z (depois do backup) | sessão dona | snapshot com `sha256` no backup incremental. Levar a branch própria é decisão de quem o escreve |
| 6 | **10 branches locais com delta real** | conteúdo que não bate com o `main`; são a única cópia fora do bundle | Pablo | preservadas de propósito. Classificadas na seção 4 |

### O que ficou fora de escopo, por instrução

- **Nenhuma revisão de prontidão para go-live.** Os bloqueadores seguem os do
  índice do memory (Tier 1 ligado, Pix em mock, NFC-e em homologação, e-mail no
  console, cartão que recusa no alpha). Nenhuma linha deste documento os toca.
- **O backlog funcional do plano de Produção não foi executado.**
- **Nenhuma faixa do Core foi alargada.**
