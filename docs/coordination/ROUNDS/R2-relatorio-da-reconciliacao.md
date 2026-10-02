# R2 — relatório da reconciliação (Entrega 4 da ordem do R0)

- **id:** R2
- **sessão:** relatorio-entrega-4 (Claude)
- **branch:** `claude/relatorio-entrega-4-dc88bc`
- **PR:** #1376 (a linha do BOARD não entra: ver "O que mudou")
- **estado final:** na fila, #1376
- **início / fim (UTC):** 2026-10-02 15:50 / 2026-10-02 16:30

Conferência feita contra `origin/main` = `bddd02693` (#1375), 02/10 15:55 UTC. A ordem original
(Entregas 1 a 3, com o rascunho do BOARD) foi lida na transcrição da sessão do R0, não de prosa.

## O que mudou

`scripts/coordination_status.py` (`make coordination`), três pontos cegos fechados:

1. **PR fechado escondia branch.** Qualquer `refs/pull/<n>/head` tirava o branch da lista "SEM PR",
   inclusive de PR fechado sem merge. Agora só PR aberto tira; os outros aparecem com o número do
   PR fechado (29 hoje) ou como "conteúdo já no main" (7 a mais do que antes).
2. **CI não existia para o comando.** Com `gh`, cada PR aberto mostra `BLOCKED`/`DIRTY` e os checks
   vermelhos, e PR com auto-merge vermelho vira `ATENÇÃO`. Sem `gh`, uma linha diz que CI e
   auto-merge não foram medidos.
3. **BOARD velho passava.** Linha `EM_PR` citando PR que não está aberto vira
   `BOARD desatualizado` (era o caso da linha do próprio R0, 18 min depois do merge).

E: a seção de atividade em 24 h separa os branches já inteiros no `main` (32 de 34 linhas eram isso).

Documentos: `BOARD.md` (linha R0 sai; R1 com sessão; F2 com o tamanho real; armadilha 5; regra da
reivindicação por PR draft), `ROUNDS/README.md` (a linha sai no mesmo PR), `R0-…md` (estado final;
item 16), `HANDOFF.md` (topo, "0-rec" dos branches, "um minuto").

## Prova

`make coordination` antes (script do `main`) e depois, mesmo remoto, 15:55 UTC:

- antes: `SEM PR: (nenhum)` · `conteúdo já no main: dsh/handoff-onda1-e-p7-20260930` · `OK`
- depois: 29 linhas `(PR fechado sem merge: #N)`, 8 em "conteúdo já no main", e
  `ATENÇÃO: PR com auto-merge vermelho (não anda sozinho): #1367; BOARD desatualizado: #1375 não está aberto`

Testes novos em `shopman/shop/tests/test_coordination_status.py`:
`test_pr_fechado_nao_esconde_o_branch` e `test_board_em_pr_de_pr_que_ja_saiu`. Com o script do
`main`: `2 failed, 4 passed`. Com o novo: `6 passed`.

| # | Afirmação (R0, BOARD ou HANDOFF) | Veredito | Prova |
|---|---|---|---|
| 1 | R0: "Branches sem PR: nenhum com trabalho novo" | [REFUTADO] | 29 branches com PR fechado sem merge e commits fora do `main`, de +1 a +26 (`codex/shopman-legal-google-oauth-20260911`, #614) |
| 2 | R0/BOARD: "#1354 e #1357, com um minuto de diferença", "em 02/10" | [REFUTADO] | `gh pr view`: #1354 criado 2026-10-01 23:46 UTC, #1357 2026-10-02 00:04 UTC; primeiros commits 23:46 e 00:03. 18 min. O "um minuto" veio do comentário de fechamento do #1354 e da ordem |
| 3 | BOARD: R0 `EM_PR` #1375 | [REFUTADO] | `gh pr view 1375`: `MERGED 2026-10-02T15:37:02Z` |
| 4 | R0: "estado final: na fila, #1375" | [REFUTADO pelo tempo] | mergeado; corrigido no R0 |
| 5 | BOARD: R1 "sessão não identificada" | [CONFIRMADO que dá para identificar] | busca de transcrições por `import_recipe_versions`: sessão "Coordenador noturno 02/10"; o relatório dela diz "está na fila de merge" |
| 6 | R1 vermelho, `BLOCKED`, cinco checks | [CONFIRMADO] | `mergeStateStatus=BLOCKED`; FAILURE em Marketing — cadeia completa, Shop heavy, Shop rest, Testes (test-shop), Coverage Gate; último push 09:12 UTC |
| 7 | Drift: três chaves | [CONFIRMADO] | `check_do_spec_drift.py --context shopman-do-app-admin`, 16:00 UTC: SUMIRIAM = `JEV_API_KEY`, `SHOPMAN_COURIER_ADAPTER`, `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED` |
| 8 | 10 PRs depois da seção 0 (#1364–#1374) | [CONFIRMADO] | `git log origin/main --first-parent d7f185627..` = #1364 a #1375 (o #1375 é o R0) |
| 9 | Checkout principal 3198 atrás | [REFUTADO pelo tempo] | 3201 às 15:55 UTC |
| 10 | HANDOFF: "`make coordination` só git, sem `gh`" | [REFUTADO] | o script usa `gh` quando autenticado; sem ele não vê CI |

## O que ficou de fora

- Apagar os 29 branches de PR fechado: não é mecânica (alguns guardam trabalho recusado de
  propósito, outros podem ter sido perdidos). Ficou na F2, com a lista no comando.
- §0.3 e §0.5 do HANDOFF (pedido desde 01/10, `courier="auto"`): pedem leitura do banco do alpha.
- O comando sem `gh` continua cego a CI. Conserto proposto abaixo, não feito.

## Perguntas ao dono

nada novo (a D36 do R0 segue).

## Armadilhas novas

- Linha `EM_EXECUCAO` num branch não reivindica nada: só chega ao `main` pela fila. A reivindicação
  visível é o PR draft (BOARD, topo).
- `refs/pull/<n>/head` existe para PR fechado também; ele não prova que há PR aberto.

## Próximo passo

- R1: dono da sessão "Coordenador noturno 02/10" troca o import interno do `import_recipe_versions.py:60`.
- F2: triagem do dormente, com lista para o dono antes de apagar.
- Conserto proposto (livre): para o coordenador sem `gh`, um workflow agendado que roda
  `make coordination` com o `GITHUB_TOKEN` e grava a saída num ref do repositório
  (`refs/coordination/status`); `git fetch` lê. Hoje quem não tem `gh` não sabe que um PR está vermelho.
