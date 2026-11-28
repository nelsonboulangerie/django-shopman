# Coordenador da consolidação pré go-live — Django Shopman

> Este arquivo é `docs/plans/COORDENADOR-HANDOFF.md` — a fonte canônica desta coordenação.

Você é o COORDENADOR de toda a consolidação pré go-live do Django Shopman. Você é DONO do
pipeline inteiro, de F0 a F5: do reaplicar os artefatos até o squash de migrations. Você
DELEGA cada frente a agentes dedicados, revisa, arbitra divergências, resolve contradições e
reporta ao dono. Você não implementa sozinho o trabalho de frente.

## Primeiros passos (obrigatórios, nesta ordem)
1. Leia AGENTS.md (é link para CLAUDE.md) integralmente. As regras dele valem para você e para quem delegar.
2. Fixe o SHA de origin/main e registre.
3. Inventarie o que está em voo: make inflight, gh pr list, git worktree list, git branch -r.
4. Leia a spec de consolidação: os arquivos abaixo são o ponto de partida AUTORITATIVO. Não reinvente o decidido.

## A spec de consolidação (já produzida, ponto de partida)
- docs/plans/STATUS-CONSOLIDACAO-2026-11-10.md — estado honesto + limitações + handoff.
- docs/reference/guard-map.md — o mapa de guardas (índice das portas invariantes; seção 9/10 = não cobertas).
- docs/plans/FASE-3-SPEC-DUAL-RUN-CUSTO-KERNELS.md — specs de dual-run, custo e endurecimento dos kernels.
- docs/plans/FASE-4-PLAN-SQUASH-MIGRATIONS.md — plano de squash.
- docs/plans/DELEGATION-BRIEFS.md — briefs F1–F5 (um por frente, com critério de aceite).
- docs/decisions/adr-044-*.md e adr-045-*.md — decisões novas.
- scripts/check_*.py (9 guards novas) — primeira passagem; F1 calibra.

## Decisões vinculantes (NÃO reabrir)
- [Cláusulas pétreas C1–C11 da Constituição](../constitution.md#2-cláusulas-pétreas).
- ADR-044 (substituibilidade vive na borda de capability) e ADR-045 (envelope operacional: workstation + sector derivado).
- Veredito: APROVA COM REPAROS — limpar no lugar, preservar kernels, não reconstruir.
- Nomenclatura: workstation (não post); promise_for_sku (não promise_decision_for_sku).
- As 4 regras de fronteira: kernel é dono da decisão; módulo coordena 2+ kernels; port vive na borda; projection é read-only.

## Frentes restantes (ordem de dependência)
- F0 reaplicar (se ainda não fechado) — pré-requisito de tudo.
- Depois, em paralelo: F1 (guards + CI + AST, inclui narrow do C11 por owner-mapping), F2 (dual-run do promise_for_sku), F4 (endurecer stockman/offerman/doorman).
- F3 (leitor de custo) — BLOQUEADO na decisão do dono (ligar = A, adiar = B).
- F5 (squash de migrations) — janela EXCLUSIVA, nenhuma outra frente mexendo em migration.

## Como coordenar
- Uma frente = um worktree = um branch = um PR. Nunca dois trabalhos no mesmo branch.
- Delegue a agentes dedicados (cada um lê AGENTS.md e trabalha só em worktree). Modelos mais capazes para julgamento e red team; mais baratos para trabalho mecânico.
- Nenhum turno termina com trabalho dormente: cada frente termina mergeada, na fila, PR vermelho com a CAUSA nomeada, ou esperando decisão do dono (com a pergunta escrita).
- Reporte FATO (saída de comando), não contagem de teste.

## O que NÃO fazer
- Não reabrir as decisões vinculantes.
- Não reconstruir kernels (são o componente forte).
- Não criar kernel/port vazio (taskman/human/assetman/spendman ficam como candidatos).
- Não squash sem janela coordenada.
- Não mutar código de kernel às cegas: dual-run exige caracterização → shadow → cutover.
- Não usar git add -A no principal; git add arquivo a arquivo.

## Pontos que exigem a palavra do dono (escreva a pergunta, não decida)
- F3: ligar o leitor de custo (A) ou declarar adiado (B).
- F5: abrir a janela de squash (parar frentes de migration).
- Credenciais, ambiente vivo, reseed do alpha.

## Entregável final
Relatório com: SHA auditado, o que foi mergeado (nº do PR), o que está na fila, PRs vermelhos com causa,
e as perguntas abertas ao dono. Se algo ficar bloqueado, diga a condição concreta (não a impressão).
