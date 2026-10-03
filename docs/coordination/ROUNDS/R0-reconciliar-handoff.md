# R0: reconciliar o HANDOFF, comando de estado e BOARD

- **id:** R0
- **sessão:** reconciliar-handoff-estado (Claude)
- **branch:** `claude/reconciliar-handoff-estado-308593`
- **PR:** #1375
- **estado final:** mergeado, #1375 (2026-10-02 15:37 UTC, `bddd02693`)
- **início / fim (UTC):** 2026-10-02 14:20 / 2026-10-02 15:00

## O que mudou

- `scripts/coordination_status.py` (`make coordination`): main, fila, PRs abertos, branches com
  atividade em 24 h, branches sem PR, reivindicações órfãs do BOARD, `OK`/`ATENÇÃO`. Só git; `gh`
  é atalho para título e estado do PR. Teste: `shopman/shop/tests/test_coordination_status.py`.
- `docs/coordination/BOARD.md` e `docs/coordination/ROUNDS/README.md` (o molde deste arquivo).
- HANDOFF: comando no topo, seção "0-rec", correções em §0.4 e §0.5.
- `PENDING-DECISIONS.md`: atualização "02/10 (dia)" com D34, D36, D37 e D40 respondidas.
- Branch remoto `claude/wp-telas-de-parede` (`48e2f2c99`) apagado: `git cherry` marca o único commit
  como já no `main` (#857). Restaurar: `git push origin 48e2f2c99:refs/heads/claude/wp-telas-de-parede`.

## Prova

Conferência da seção 0 do HANDOFF (escrita em 02/10 02:15 UTC, #1359) contra `origin/main` =
`c3c34d22f`, 02/10 14:20 a 14:48 UTC.

| # | Afirmação do HANDOFF | Veredito | Prova |
|---|---|---|---|
| 1 | #1350, #1342, #1351, #1293, #1257, #1356, #1357, #1362, #1353, #1355, #1358, #1361, #1352 mergeados | [CONFIRMADO] | `git log origin/main --grep='pull request #<n> '`: todos achados (`862ff8186` … `9244a70d6`). "Este PR" (frentes 2 e 3) é o #1359, mergeado (`d7f185627`) |
| 2 | #1340, #1354, #1220 a #1223 fechados sem merge | [CONFIRMADO] | ausentes do `main`; sem `refs/pull/<n>/merge` (o GitHub só mantém o ref de merge de PR aberto) |
| 3 | "Estado agora" | [REFUTADO] | 10 PRs entraram depois: `git log origin/main --first-parent d7f185627..origin/main` = #1364 a #1374 |
| 4 | PRs abertos | [CONFIRMADO, com acréscimo] | `git ls-remote origin 'refs/pull/*/merge'` = #1367, #232 a #235; `gh pr list --state open` = os mesmos 5. O #1367 está `BLOCKED`, vermelho desde 09:25 UTC (import interno do Craftsman, run 36988496707) |
| 5 | D34 depende do dono | [REFUTADO] | #1365: "D34 opção 1, aprovada pelo dono em 02/10" |
| 6 | D36 depende do dono; "Jev não rodou" | [REFUTADO] | drift: `JEV_API_KEY` e `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED` só no vivo; #1373: "HTTP 400 nas 44 chamadas ao Jev no alpha". Resposta escrita do dono não achada |
| 7 | D37 depende do dono | [REFUTADO] | #1371 e #1372: "Decisão do dono (02/10, D37)" |
| 8 | D40 depende do dono | [REFUTADO] | #1370 (`67f4f7700`): "Decisão do dono (02/10, 'Seed: sim')", Biorgânica → `FARINHA-NOVARA-T55`, Tradição sem malte; #1367: "com o aval escrito do dono (02/10)" |
| 9 | D35, D38, D39, D41 abertas | [CONFIRMADO] | nenhuma resposta em `DECISIONS.md` (vai até D-027) nem em commit; D38: `gh api …/actions/permissions/workflow` → `can_approve_pull_request_reviews: false` |
| 10 | Antigas D2, D8, D18(b,d,e), D22, D23, D25, D26, D27, D30, D31 abertas | [CONFIRMADO] | nenhuma nas tabelas de atualização do `PENDING-DECISIONS.md` nem em `DECISIONS.md` |
| 11 | Drift `[FAIL]` só por `SHOPMAN_COURIER_ADAPTER` | [REFUTADO] | `check_do_spec_drift.py --context shopman-do-app-admin` (só leitura), 14:40 UTC: SUMIRIAM = `JEV_API_KEY`, `SHOPMAN_COURIER_ADAPTER`, `SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED` |
| 12 | 23 checks obrigatórios | [CONFIRMADO] | `check_canonical_docs.py --live-required-checks`: "[OK] … matches live branch protection (23 contexts)" |
| 13 | Pix simulado | [CONFIRMADO] | `.do/app.subdomains.yaml:325` = `payment_mock`; o drift não acusa diferença nessa chave |
| 14 | ManyChat: "os 5 não existem", "liga no Admin" | [REFUTADO] | `MANYCHAT-ESTADO-0210.md` (#1366): `pagamento_falhou` enviado, em análise; faltam 4. Ligação é pelo `MANYCHAT_FLOW_MAP`, o campo do Admin é somente leitura |
| 15 | `node-forge` adiado (D-027) | [CONFIRMADO] | #1364 reconfirma com o dono |
| 16 | Branches sem PR: só `print-layouts` fica | [REFUTADO em parte] (⚠️ corrigido pelo R2: o comando contava head de PR **fechado** como "tem PR" e escondia 29 branches; ver `R2-relatorio-da-reconciliacao.md`) | `make coordination`: nenhum com trabalho novo; `claude/wp-telas-de-parede` sobrando (apagado), `dsh/handoff-onda1-e-p7-20260930` com o conteúdo no `main` e em uso por worktree do DSH; 15 `rescue/*` |
| 17 | Checkout principal 3135 commits atrás | [REFUTADO, número] | `git rev-list --count HEAD..origin/main` no principal: 3198, branch `codex/shopman-backstage-marketing-hardening` de 28/08 |
| 18 | §0.3 "nenhum pedido desde 01/10 14:44" | [NÃO CONSEGUI VERIFICAR] | pede leitura do banco do alpha; não feita nesta rodada |
| 19 | §0.5 `courier="auto"` não ligado | [NÃO CONSEGUI VERIFICAR] | pede leitura do Admin/banco do alpha |

Teste do comando: `pytest shopman/shop/tests/test_coordination_status.py` → `4 passed` (fila vazia,
`--strict`, tudo em ordem diz `OK`, fila parada + reivindicação órfã). Rodado contra o remoto real:
7,5 s, `OK`.

## O que ficou de fora

- Leitura do banco do alpha para §0.3 e §0.5: fora do escopo (só repositório e spec).
- Registro `D-0xx` em `DECISIONS.md` para D34/D36/D37/D40: não inventei decisão; anotei a fonte
  (mensagem de commit) no `PENDING-DECISIONS.md`.
- Corrigir o #1367: tem dono (R1).

## Perguntas ao dono

- D36: o Jev foi aprovado por você? Respondida em 02/10: sim, ele mesmo pôs a chave e fez o
  teste. Registro D-028.

## Armadilhas novas

- Sem `gh`, "PR aberto" = existe `refs/pull/<n>/merge`. Bate com o `gh` em 02/10 (5 de 5, um em
  conflito). PR que nasce em conflito pode não ter o ref.
- 42 PRs fechados ainda têm o branch vivo apontando para o head: "head na ponta de branch" NÃO
  quer dizer aberto.

## Próximo passo

R1: tirar o import interno do `import_recipe_versions.py:60` (dono da frente). F5: trazer as duas
chaves do Jev para o arquivo do spec (livre).
