# Briefs de delegação F1–F5 (agente externo com tooling completa)
> 2026-11-10 · Cada frente = um worktree + um branch + um PR. Leia AGENTS.md e rode `make inflight` antes.

## F1 — Calibrar guards + escrever AST (após F0)
- Objetivo: ligar as 7 guards novas (scripts/check_*.py) ao Makefile/CI; calibrar o fail-closed
  (especialmente check_decision_authority, que deve FALHAR em origin/main por causa de _stock_decision,
  e depois passar quando o dual-run o remover); escrever guards AST para C3 (alvo importado), C6 (estado)
  e C11 (já draftada em check_ledger_immutability.py).
- Evidência: docs/reference/guard-map.md (seções 9/10), scripts/check_guard_map.py (GUARDS + UNCOVERED).
- Aceite: `make test-guard-map` verde; check_decision_authority falha com _stock_decision presente e passa após removê-lo.

## F2 — Dual-run do promise_for_sku (após F0)
- Objetivo: executar docs/plans/FASE-3-SPEC-DUAL-RUN-CUSTO-KERNELS.md §3.1 — caracterizar, shadow, cutover,
  apagar _stock_decision (shop/services/availability.py:686; call sites :554, :623).
- Aceite: `grep -r '_stock_decision' shopman/shop` vazio; check_decision_authority verde; suíte de disponibilidade verde.
- Coordenação: não tocar em stockman ao mesmo tempo que F4.

## F3 — Leitor de custo (após F0 + DECISÃO DO DONO)
- Objetivo: opção A (ligar CostBackend vivo + congelado) ou B (ADR de adiamento + remover colunas dormant).
- Bloqueio: precisa da palavra do dono (A ou B). Não decidir sozinho.

## F4 — Endurecer stockman/offerman/doorman (após F0)
- Objetivo: FASE-3 §3.3 — Stockman (SPEC concentrada, Quant.batch→FK, sem sentinela 999999); Offerman
  (contratos fechados, preço único); Doorman (_link_verified_identifier→bridge, sem engolir exceção).
- Aceite: os 4 gates por kernel (autoridade única, gate AST, SPEC concentrada, contract tests).
- Coordenação: não tocar em stockman ao mesmo tempo que F2.

## F5 — Squash de migrations (janela exclusiva, coordenada pelo dono)
- Objetivo: docs/plans/FASE-4-PLAN-SQUASH-MIGRATIONS.md — baseline por app, remover 17+3 duplicatas,
  limpar LEGACY_PREFIX_COLLISIONS, re-seed, suíte completa.
- Bloqueio: exige que NENHUMA outra frente esteja criando/renumerando migration. Coordenar janela com o dono.
