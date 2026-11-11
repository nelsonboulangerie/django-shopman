# STATUS da consolidação autônoma — 2026-11-10

## O que foi entregue (nesta sessão, todos arquivos NOVOS, sem conflito)

- docs/reports/auditoria-reset-v5-2026-11-10.md — auditoria v5 (veredito APROVA COM REPAROS).
- docs/plans/PROPOSA-FINAL-CONSOLIDACAO-PRE-GO-LIVE.md — proposta v6.
- docs/plans/RUNBOOK-CONSOLIDACAO-URGENTE-2026-11-10.md — runbook (corrigido).
- docs/reference/guard-map.md — mapa de guardas (índice das portas invariantes).
- scripts/check_guard_map.py — guarda do próprio mapa (roda, confere completude).
- docs/decisions/adr-044-substituibilidade-na-borda.md + adr-045-envelope-de-fato-operacional.md (+ índice).
- scripts/check_decision_authority.py — gate: duplicação de autoridade (aplica-se a _stock_decision).
- scripts/check_signal_on_commit.py — gate heurístico: ADR-025 (signal fora de on_commit).
- scripts/check_money_integer.py — gate heurístico: C2 (dinheiro float/decimal).
- scripts/check_read_side_immutability.py — REPORT-ONLY: C10 (aponta candidatos, não falha).

## Verdades que precisam ficar registradas (não esconder)

1. **Checkout defasado.** O trabalho foi escrito sobre 65b658d3, ~200 commits atrás de origin/main
   (057fe9105). Arquivos NOVOS não conflitam; o README.md editado pulou ADR-042/043 (que só existem
   no origin/main). A esteira (commit/push/PR) DEVE partir de um worktree fresco de origin/main.
2. **Verificação local não vale.** Os guards rodaram contra o checkout defasado: check_decision_authority
   deu 'OK' localmente mas SABEMOS que _stock_decision existe em origin/main. A calibração final
   (fail-closed nos violações reais) só acontece no CI, contra o código fresco.
3. **Guards heurísticos, não definitivos.** C10 virou report-only (regex não distingue dict.update de
   ORM.update — a casa já usa AST no test_import_boundaries.py por isso). C3 (refs), C6 (ciclo de Order)
   e C11 (ledger imutável) AINDA NÃO têm guarda: exigem análise AST, não regex. Estão marcadas como
   'convenção' no guard-map.
4. **Não toquei** em código de kernel/orquestrador nem em migrations: Fase 3 (dual-run do promise_for_sku,
   leitor de custo, endurecimento) e Fase 4 (squash de migrations) ficaram como SPECS/pendências, porque
   mutar código compartilhado de um checkout defasado com 262 worktrees ativas seria irresponsável.

## O que falta (para quem continuar, em ordem)

1. Worktree fresco de origin/main + reaplicar os arquivos novos + README com 042/043/044/045.
2. Rodar os guards no CI e calibrar: confirmar check_decision_authority falha com _stock_decision presente;
   calibrar check_signal_on_commit (verificar se os candidatos de offerman/refs/guestman/fiscal são
   violação real de ADR-025 ou fire-and-forget legítimo).
3. Fase 3: concluir dual-run (matar _stock_decision), ligar leitor de custo, endurecer stockman/offerman/doorman.
4. Fase 4: squash de migrations (coordenação com worktrees).
5. Guardas AST para C3/C6/C11 (seguir o padrão de test_import_boundaries.py).

## F0 — reaplicado sobre origin/main 057fe9105 (coordenação, 2026-11-10)

- Os arquivos acima saíram do checkout principal (65b658d3, não commitados) e entraram por um
  branch novo de origin/main. O índice de ADRs agora lista 042 e 043 (já no main) seguidas de 044 e 045.
- São **9** guards novas, não 7 nem 4: `check_cross_kernel_refs`, `check_decision_authority`,
  `check_guard_map`, `check_ledger_immutability`, `check_lifecycle_functional`, `check_money_integer`,
  `check_order_lifecycle_owner`, `check_read_side_immutability`, `check_signal_on_commit`. Nenhuma
  está ligada ao Makefile/CI ainda: isso é a F1.
- **Contradição arbitrada:** a PROPOSA-FINAL §0.5 e §3 diz "superfícies não importam kernel" e chama
  de violação os imports de leitura do backstage. O RUNBOOK (posterior) corrige: o
  `test_import_boundaries.py` enforça a fronteira matizada (leitura de model público pode; internals,
  write primitives do orderman e lifecycle direto em view não podem). Vale o RUNBOOK; a §3 da proposta
  não é frente de trabalho.
- O guard-map dizia "A Constituição aponta para cá"; não aponta. O ponteiro fica para a F1.
- Nomenclatura vinculante: a função do Stockman hoje se chama `promise_decision_for_sku`; o nome
  canônico é `promise_for_sku`. O rename é parte da F2.
