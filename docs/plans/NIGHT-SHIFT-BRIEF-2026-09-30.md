# NIGHT-SHIFT BRIEF — turno autônomo de 30/09 para 01/10/2026

> **Você (Claude) é o coordenador desta madrugada.** O dono está fora do computador e não vai
> responder. Nada aqui depende dele para andar — o que depender vai para `PENDING-DECISIONS.md`
> e você segue para a próxima frente.
>
> **LEIA ESTE ARQUIVO INTEIRO ANTES DE QUALQUER COISA.** E **releia antes de cada frente nova** —
> ele pode ter sido completado depois que você o leu pela primeira vez.

**Handshake:** se a seção **「FILA — OBSERVAÇÕES DO DONO」** ainda estiver marcada como
`⏳ EM COMPLETAMENTO`, espere 10 minutos e releia. Outra sessão está terminando de apurá-la.
Não comece as frentes daquela seção antes de ela estar completa; comece pelas outras.

**Contexto que você precisa:** `docs/reports/go-live-acceleration-20260929/HANDOFF.md` (estado,
armadilhas, o que já foi feito) e `docs/coordination/DECISIONS.md` (D-001 a D-009).

---

## 1. O que você pode e o que não pode

**Pode, sozinho:** escrever código · abrir branch e PR · enfileirar merge (`gh pr merge`) · rodar
testes · ler produção · medir com `curl` · criar worktrees · **lançar quantas sessões/agentes
quiser** e dividir as frentes entre eles.

**NÃO pode, e não é negociável:**
- `doctl apps update` no spec vivo — **exceto** a recuperação do item 4 abaixo
- revogar ou criar token · mexer em credencial · `disable_push_subscriptions`
- mudar comportamento de produto · publicar em Marketing/iFood · mandar mensagem a cliente
- tocar em dinheiro, fiscal ou apagar dado
- **decidir qualquer coisa que seja do dono** — vai para `PENDING-DECISIONS.md`

## 2. Regras de convivência (o repo tem várias sessões)

- **Uma frente = um branch = um PR.** Nunca dois trabalhos no mesmo branch.
- **Antes de abrir frente:** `gh pr list` + `make inflight`. Chip que duplica PR aberto se dispensa.
- **Dois PRs em paralelo no máximo.** Cada PR custa ~29 checks e uma posição na fila de merge;
  três ou quatro congestionam em vez de acelerar.
- **Não use o checkout principal** (`/django-shopman`) para escrever. Só worktree.
- `git add` só com arquivo nomeado.
- Antes de PR: checar colisão de numeração de migração
  (`ls <app>/migrations | sed 's/_.*//' | sort | uniq -d`).

## 3. Armadilhas do deploy — leia duas vezes

1. ⛔ **NUNCA** `apps update --spec` com um arquivo que não veio do spec VIVO. O update
   **substitui** o spec inteiro. Foi assim que o app congelou por 21 h em 29/09.
2. Contexto: **`shopman-do-app-admin`**. O `default` é vazio e falha alto **de propósito**.
3. **Antes** de qualquer `apps update`: `make deploy-spec-drift context=shopman-do-app-admin`.
   Se houver linha em SUMIRIAM, **pare**.
4. **Depois** de aplicar: `spec get` e compare os **42 SECRET** antes × depois. Têm de ser idênticos.
   Se algum mudou, restaure do backup imediatamente.
5. `deploy_on_push` está `false` nos 8 componentes — **quem cria o deployment é o
   `deploy-images.yml`**, um por run, causa `manual`.

## 4. 🚨 Recuperação pré-aprovada (a ÚNICA escrita no ambiente vivo autorizada)

**Quando:** um run do Deploy Images falhou **e nada foi ao ar** (o app continua no deployment
anterior, e merges novos param de chegar em produção).

**O que fazer, exatamente:**
1. Backup: `doctl --context shopman-do-app-admin apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f > /tmp/antes.yaml`
2. Edite textualmente, trocando `deploy_on_push: {}`/`enabled: false` por `enabled: true` **nos 8
   componentes com imagem** (web, storefront-nuxt, operator-floor, operator-office,
   directive-worker, maintenance-worker, ifood-poll-worker, release). **Só isso.**
3. `diff` — têm de ser **8 linhas**, nada mais. Se for diferente, PARE.
4. Aplique com `apps update`. **Confirme os 42 SECRET depois.**
5. Registre no `NIGHT-REPORT.md`, com o motivo.

**Se o app estiver FORA DO AR** (home ou `/health/live/` ≠ 200): **PARE TUDO**, escreva no
`NIGHT-REPORT.md` em letras grandes e não tente mais nada. Não improvise recuperação.

## 5. Protocolo de registro (obrigatório)

Mantenha **atualizados a cada PR**, no seu branch de trabalho:

- **`docs/reports/go-live-acceleration-20260930-diag/NIGHT-REPORT.md`** — o relatório da manhã.
  Por frente: o que entrou (número do PR), o que está na fila, o que quebrou e por quê, e o que
  ficou pendente. **Escreva como se o dono fosse ler às 7h com pressa.**
- **`docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md`** — cada decisão do dono
  que você encontrou: o contexto em 3 linhas, as opções, e sua recomendação. **Nunca decida você.**

## 6. FILA DAS FRENTES

### 6.1 Já prontas para atacar (não dependem do dono)

| # | Frente | Arquivos | Nota |
|---|---|---|---|
| **F1** | **#1291 está VERMELHO**: ele desliga `deploy_on_push` no arquivo, mas `test_nuxt_deploy_config.py:156` ainda exige o valor LIGADO | `.do/app.alpha-subdomains.yaml`, teste | É o **último item do drift**. Sem ele, `make deploy-spec-drift` não fica verde |
| **F2** | `brace-expansion` no audit do operator-kit faz o check "Marketing — cadeia completa" reprovar **em todos os PRs** | `surfaces/operator-kit/package*.json` | Vermelho crônico que todos ignoram é pior que nenhum check |
| **F3** | **P2 (Core)** — a disponibilidade é **~1,3 s = 60% da projeção** do `menu/`. É o maior ganho que sobra | `packages/stockman/`, `shop/services/waitlist.py`, `shop/projections/catalog_context.py` | ⚠️ é **Core**: revisão própria, `make test-stockman`, e **provar equivalência semântica antes/depois** |
| **F4** | **Projeção da sacola** — com sacola, `home/` e `menu/` fazem **~200 consultas**, e o custo está na sacola, não no catálogo | a mapear | Caminho do cliente **logado**. Meça antes |
| **F5** | **PWA travado** (queixa do dono) | `surfaces/storefront-nuxt/` (sw, nuxt.config, usePwaUpdate, PwaUpdateToast, app.vue) | **Portar do `operator-kit`**, que resolveu o mesmo no PDV em 17/09. Não reinvente |
| **F6** | **Bug do "segundo clique"** (queixa do dono) | `surfaces/storefront-nuxt/` (carrossel de carrinho) + `shopman/storefront/api/surface.py` | Dois bugs distintos. Relatório: `04-bug-segundo-clique.md` |

**Ordem sugerida:** F1 e F2 primeiro (são pequenas e destravam o resto). Depois F5 e F6 em paralelo
(não colidem com nada). **F3 por último e sozinha** — é Core e merece atenção inteira.

⛔ **F3 e F4 são o mesmo código**: nunca em paralelo entre si. F5 e F6 não colidem com elas.

### 6.2 ⏳ EM COMPLETAMENTO — 「FILA — OBSERVAÇÕES DO DONO」

*(Esta seção será preenchida pela sessão gestora em poucos minutos. **Releia este arquivo** antes de
começar a seção 6.2. Ela trará os vereditos das observações do dono sobre: login por WhatsApp
(nome/sobrenome), a rota `/menu`, link de pagamento no PDV, rejeição de pedido no Gestor, e o
cluster de Receitas.)*

### 6.3 NÃO FAÇA

- ⛔ **P7 do relatório 13** (`_quantity__gt=0` em `tracked_skus`): **refutado e perigoso** — faz um
  SKU esgotado deixar de ser rastreado e o gate libera `999999` **sem limite**, vendendo o que
  acabou. Existe trava: `test_sold_out_sku_stays_tracked.py`. **Não remova e não reaplique.**
- ❌ **P9** do mesmo relatório: medido em **1,5 ms**, não vale o esforço.
- WP-5 (trava por dispositivo no PDV): parado de propósito, espera desenho do atendimento.

## 7. Ao amanhecer

O dono chega cedo. O que ele espera: **`NIGHT-REPORT.md` respondendo, em uma tela, o que entrou,
o que está na fila e o que precisa dele** — e `PENDING-DECISIONS.md` com as escolhas que só ele faz.
