# Convergência local · remoto · CI · deploy — relatório de execução

**Quando:** 2026-09-08, 17:48Z → 18:5xZ (America/Sao_Paulo) · **Host:** `macpab.local`
**Escopo:** eliminar ou documentar pendência operacional. **Não** é revisão de
prontidão para go-live — os bloqueadores de go-live seguem intocados e fora
deste documento, de propósito.

| | |
|---|---|
| `origin/main` inicial | `47d0b854b1086c1d5a172333f22e5ae9fab4c531` |
| `origin/main` final | `3fb0e575caa5e1d298ebd6bf7307d8af3434515e` |
| `main` local | `3fb0e575c…` — **igual ao remoto** |
| worktrees | 47 → **18** |
| branches locais | 451 → **32** |
| branches remotas | 381 → **23** |
| stashes | 0 (antes e depois) |
| backup | `/Users/pablovalentini/Documents/Backups/django-shopman-convergence-20260908-145122` |

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

### Decisão: os sete ficam abertos, e é decisão fundamentada

Nenhum é flake e nenhum é bloqueio fantasma. Fechá-los descartaria bumps
legítimos; mergeá-los exige **alargar faixa declarada em `packages/*`** — o
Core — e o handoff é explícito em não ampliar escopo para revisão funcional sem
autorização. O #234 ainda troca a biblioteca que desenha **o QR que o cliente
escaneia para pagar**.

O conserto, quando for a hora, é um WP próprio e tem receita conhecida: alargar a
faixa em cada `packages/*/pyproject.toml` afetado, regenerar com
`scripts/check_constraints.py --write`, re-snapshotar o inventário do Unfold e
rodar a suíte inteira. #232 e #235 têm de subir **juntos**.

## 4. Branches e worktrees

**Worktrees: 47 → 18.** Todas as removidas passaram, no instante da remoção, por
três provas: `git status` limpo (ou zero blob único), nenhum processo em
`lsof +D`, e HEAD contido em `origin/main`.

- 20 removidas limpas · 9 removidas sujas com **zero blob único** provado
- **2 recusadas pelo próprio git**: `agent-ab3dc373225cb0b4c` e
  `agent-ad44b5a41338740f7`, locked pelo **PID 7002, que está vivo**. Não foram
  tocadas. É condição de parada, e o git a aplicou sozinho.

**Branches locais: 451 → 32. Branches remotas: 381 → 23.** Zero erros nos dois
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
| `SHA256SUMS` | 114 arquivos |

Prova de recuperabilidade **depois** da limpeza: três branches apagadas ao acaso
foram encontradas no bundle, com assunto legível.

⚠️ Nenhum `git gc`, `git prune` ou `git worktree prune` foi executado.

---

## 6. Arquivos locais

| arquivo | decisão |
|---|---|
| handoff de convergência do agente externo | **PROMOVIDO** — este PR. Vivia untracked numa worktree do Codex |
| 4 relatórios de 2026-08-28 no checkout raiz | **ARQUIVADOS** no backup. São prompts de execução já cumpridos, não entrega |
| `prova-clique.mjs`, `prova-feeds.mjs` | **ARQUIVADOS**. 47 linhas somadas, porta `3014` no código, sem contrato; `scripts/run_omotenashi_browser_qa.mjs` já faz isso com dono |
| `.alpha-tmp/` (19 MB) | **ARQUIVADO** no backup; não commitado — screenshots de QA podem conter dado de sessão |

---

## 7. Verificação final

### O Alpha Smoke real, por `workflow_run`

Run [`34263203082`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34263203082),
gatilho `workflow_run`, sobre `3fb0e575caa5` — **`success`, com as quatro
asserções executadas**:

```
18:28:19Z  deployment=308a459f… phase=PENDING_BUILD
18:28:41Z  deployment=308a459f… phase=PENDING_BUILD
18:29:03Z  deployment=308a459f… phase=DEPLOYING
   …seis leituras…
18:31:15Z  deployment=308a459f… phase=ACTIVE
deployment 308a459f… ACTIVE — o alpha está com o que subiu.
/ready/ => 200
skus no cardápio: 44; com disponibilidade: 18
POST /api/v1/checkout/ => 400
home => 200 (118337 bytes)
```

Espera real: **3min13s** — contra os 420s cegos de antes. E note o que a espera
cega teria feito: o `sleep 420` expiraria às 18:35:05, com o deployment já
`ACTIVE` — teria funcionado **desta vez, por sorte**. Nos deploys em que a DO
demora mais, ele mediria a versão anterior e ficaria verde. E com
`timeout-minutes: 5` ele nunca chegava lá de todo modo.

### Estado do SHA final

| verificação | resultado |
|---|---|
| checks obrigatórios de `3fb0e575c` | **25/25 verdes**, zero falhas |
| Deploy Images | [`34262972216`](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34262972216) `success` — rebuildou `web` |
| deployment ativo | `308a459f-6f72-46f4-b479-0e2bc7837557` · **ACTIVE 47/47** |
| proveniência das imagens | 10 de 10 coerentes; `web` agora em `3fb0e575caa5` |
| `scripts/check_do_spec_drift.py` | exit 0 — só `FOCUS_NFE_ENVIRONMENT` e `SENTRY_DSN`, ambas declaradas |
| smoke manual | ready 200 · 44 SKUs / 18 vendáveis · checkout 400 · SSR 200, 118337 bytes, contém "Nelson" |

---

## 8. Pendências restantes

| # | Pendência | Causa | Dono | Próxima ação |
|---|---|---|---|---|
| 1 | **7 PRs do Dependabot abertos** | faixa declarada em `packages/*` barra o bump; `ResolutionImpossible` no `make install` | Pablo | WP próprio: alargar faixa, `check_constraints.py --write`, re-snapshot do Unfold, suíte inteira. #232+#235 juntos |
| 2 | **Checkout raiz 644 commits atrás** | o hook bloqueia `checkout` ali de propósito; nenhum agente pode atualizá-lo | Pablo | `git pull` no raiz quando não houver sessão trabalhando nele |
| 3 | **2 worktrees locked** (`agent-ab3dc373225cb0b4c`, `agent-ad44b5a41338740f7`) | **PID 7002 vivo** — o próprio git recusou a remoção | sessão dona | encerrar a sessão; então `git worktree remove` |
| 4 | **3 worktrees sujas com bytes únicos** (`app-bug-fixes-790f0b`, `eloquent-grothendieck-1945b1`, `dreamy-lalande-e6053c`) | rascunhos anteriores ao `main` + 2 scripts de prova ad-hoc | Pablo | patches no backup; `git worktree remove --force <caminho>` quando quiser |
| 5 | **`receitas-paes-producao-26a519` suja com processo vivo** | sessão ativa | sessão dona | nada agora |
| 6 | **12 branches locais com delta real** | 4 têm PR fechado por decisão sua; as outras foram provadas sem código ausente do `main` | Pablo | nenhuma ação necessária; ficam por escolha |
| 7 | **4 relatórios de 28/08 e `.alpha-tmp/` no checkout raiz** | untracked; não pude escrever no raiz | Pablo | arquivados no backup; apagar do raiz quando quiser |

⚠️ Nenhuma destas é defeito aberto de CI, deploy ou integridade de repositório.
São decisões que dependem de quem tem a palavra ou a sessão.
