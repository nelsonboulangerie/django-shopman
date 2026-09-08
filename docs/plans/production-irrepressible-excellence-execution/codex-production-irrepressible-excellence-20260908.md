# Execução — Produção rumo à excelência irreprimível

- Sessão: `codex-production-irrepressible-excellence-20260908`
- Início: 2026-09-08, `America/Sao_Paulo`
- Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-production-irrepressible-20260908`
- Branch: `codex/production-irrepressible-excellence-20260908`
- SHA-base: `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`
- Escopo: `surfaces/production-nuxt` e cadeia Django/Craftsman/Stockman/Orderman descrita no plano.
- Checkout compartilhado original: preservado; havia arquivos não rastreados alheios e nenhum foi transportado, exceto o plano normativo.
- Plano de entrada: SHA-256 `f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d`, idêntico no checkout de origem e no worktree.

## Commits locais

| Commit | Slice | Arquivos | Provas | Dependências |
|---|---|---|---|---|
| `749f8f1e2` | Registro do plano normativo | `docs/plans/PRODUCTION-IRREPRESSIBLE-EXCELLENCE-PLAN-2026-09-08.md` | SHA-256 conferido; `git diff --cached --check` | SHA-base |
| `bd0c56268` | Filtros tipados e estritos | `_production_filters.py`, `operations.py` e testes | RED: 5 falhas/1 passe; GREEN: 43 aprovados; Ruff e `git diff --check` | P0.0 |

## Preparação e baseline

Documentos lidos integralmente antes da primeira alteração de implementação:

- plano desta execução;
- ADR-012, ADR-014, ADR-017 e ADR-018;
- `docs/engineering/backstage-design-system.md`;
- `docs/engineering/unfold_admin_page_playbook.md`;
- `docs/engineering/unfold_canonical_policy.md`;
- `docs/reference/unfold_canonical_inventory.md`;
- skill local `.codex/skills/unfold-admin-canonical/SKILL.md`.

Não há `AGENTS.md` rastreado na árvore do worktree.

| Data | Comando | Resultado | Observação |
|---|---|---|---|
| 2026-09-08 | `npm test` em `surfaces/production-nuxt` | 20 arquivos, 110 testes aprovados | Primeira coleta falhou porque `.nuxt/tsconfig.app.json` ainda não existia no worktree novo; apó `npm run postinstall`, baseline reproduzido exatamente. |
| 2026-09-08 | `npm run typecheck` | aprovado | Foi necessário disponibilizar os `node_modules` locais de `production-nuxt` e `operator-kit` no worktree; nenhuma dependência/lock foi alterada. |
| 2026-09-08 | `npm run lint` | aprovado | Sem achados. |
| 2026-09-08 | `npm run test:e2e` | 5 aprovados | Confirma o baseline e reproduz o contrato incorreto do menuboard público no teste `guards.spec.ts`. |
| 2026-09-08 | `python -m pytest` nos cinco arquivos centrais indicados em WP-P0.0 | 58 aprovados em 8,74 s | Subconjunto central atual. |
| 2026-09-08 | `python -m pytest shopman/backstage/tests/test_*production*.py ...` | 178 aprovados em 15,53 s | Cobertura mais ampla que os 105 testes citados pela auditoria; inclui Produção, QC, forno, quick finish e retry. |
| 2026-09-08 | `test_production_excellence_baseline.py -q -s` | 2 aprovados | Dataset determinístico de 100 WOs e placar abaixo. |
| 2026-09-08 | host publicado, desktop e viewport 390 × 844 | shell de Produção carrega; dados operacionais retornam estado de reconexão e login | Inspeção anônima, somente leitura, sem tentativa de autenticação. |
| 2026-09-08 | host publicado `/menuboard` | 200 anônimo com catálogo e preço reais | Reproduz PROD-009 no sistema publicado; nenhum dado foi copiado para fixture. |
| 2026-09-08 | host publicado `/api/v1/backstage/production/` | 403 anônimo | O gate de dados operacionais está ativo. |
| 2026-09-08 | host publicado `/api/v1/storefront/menu/` | 200 anônimo, 140.380 bytes | Confirma que o menuboard paralelo consome contrato público volumoso. |

### Placar observado — 100 WOs

Medição local funcional (SQLite/test client); é baseline comparativo, não p95 de produção.

| Superfície | Queries | Tempo local | Payload |
|---|---:|---:|---:|
| board | 492 | 160,245 ms | 231.844 B |
| KDS | 74 | 16,519 ms | 16.641 B |
| QC | 78 | 22,383 ms | 34.053 B |
| mise en place | 85 | 24,942 ms | 5.971 B |
| relatórios | 146 | 37,232 ms | 32.055 B |
| pesagem | 17 | 14,079 ms | 1.797 B |
| alertas | 8 | 2,521 ms | 266 B |

### Cabeçalhos anônimos observados no host publicado

As quatro respostas verificadas usam `Cache-Control: private` e `cf-cache-status: BYPASS`. Não foram observados CSP, `frame-ancestors`, `object-src`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` ou HSTS. O aceite final de P0.5 continuará exigindo scanner no host após implantação; esta execução não implanta.

## Gates humanos

| Gate | Estado | Trabalho seguro em curso | Escolha pendente |
|---|---|---|---|
| D1 — matriz de autoridade | aberto | infraestrutura de capabilities, testes de negação e proposta de matriz | capacidades finais e aprovações por persona |
| D2 — estação confiável | aberto | device posture e enforcement configurável | mutações que exigem estação provisionada |
| D3 — perda total | aberto | prova da lacuna, invariantes e contrato backward-compatible | nome/semântica contábil se o lifecycle/ADR precisar mudar |
| D4 — menuboard físico | aberto | aposentar contrato público e preparar entrada canônica por `ref` | refs das TVs e janela de troca |
| D5 — pesagem | aberto | contrato de sessão/eventos, simulador e fluxo manual por flag | processo, tolerância, lotes, política e hardware reais |
| D6 — capacidade | aberto | discovery documentado e projeção de conflito | recurso escasso real |
| D7 — omotenashi medido | aberto | instrumentação, roteiro e budgets provisórios | baseline de turnos e metas finais |
| D8 — piloto/rollout | aberto | build, runbook, flags, dashboards e rollback | estação, equipe, janela, owner e abort criteria |

## Matriz achado → prova → mudança → observabilidade

| ID | Achado atual | Teste vermelho/prova | Mudança | Teste verde | Observabilidade | Estado |
|---|---|---|---|---|---|---|
| PROD-001 | gate grosso abre todas as ações e APIs constroem acesso total | auditoria estática + testes atuais de coarse gate | pendente | pendente | capabilities projetadas e 403 por capability | aberto; política final D1/D2 |
| PROD-002 | `rev`/idempotência não atravessam a borda | auditoria de API/cliente e tipos gerados | pendente | pendente | conflito e tentativa correlacionados | aberto |
| PROD-003 | quick finish cria WO antes de validar shortage/retry | auditoria de `apply_quick_finish` | pendente | pendente | tentativa/WO correlacionadas | aberto |
| PROD-004 | step/oven atualizam estado sem trava/revisão/idempotência uniforme | auditoria de serviços | pendente | pendente | eventos append-only | aberto |
| PROD-005 | `force=bool("false")` ativa override e não exige razão/aprovação | teste de borda a adicionar | pendente | pendente | executor/aprovador/razão/snapshot | política final D1/D2 |
| PROD-006 | perda total é rejeitada; `finished or quantity` criaria saída vendável | testes QC/Stockman a adicionar | correção preventiva + contrato proposto | pendente | ledger/passaporte | semântica final D3 |
| PROD-007 | mise/pesagem usam planejado/receita viva; zero conhecido some | testes de snapshot/zero a adicionar | pendente | pendente | métricas de divergência | aberto |
| PROD-008 | grade desconhecida vira default e defeito desconhecido some | teste estrito a adicionar | pendente | pendente | erro tipado por ref | aberto |
| PROD-009 | menuboard público confirmado em teste e no host | `guards.spec.ts` + GET anônimo publicado 200 | pendente | pendente | probe 403/404/launcher canônico | rollout D4 |
| PROD-010 | host sem headers defensivos; upstream local permissivo | captura de headers e auditoria de config/proxy | pendente | pendente | release check/scanner | aberto |
| PROD-011 | N+1 medido: board 492 queries/100 WOs | baseline versionado | pendente | budgets 1/10/100 | query count, latência e payload | aberto |
| PROD-012 | frontend escolhe `[0]` em múltiplas WOs | teste atual institucionaliza comportamento | pendente | pendente | evento de escolha explícita | aberto |
| PROD-013 | polling ressuscita após unmount; writes não bloqueiam stale/offline | teste de corrida a adicionar | pendente | pendente | freshness/reconciliação | aberto |
| PROD-014 | alertas não têm audiência/ciclo/ações projetadas | auditoria de serviço/composable | pendente | pendente | seen/ack/resolved por ator | aberto |
| PROD-015 | reports sem Apply/paginação; filtros eram permissivos | RED 5 falhas; auditoria frontend | validação estrita e janela 93 dias | 43 testes aprovados | 400 canônico por campo | parcial |
| PROD-016 | checklist local sem revisão; impressão é `window.print()` | auditoria frontend | pendente | pendente | hash/diff/estado de job | aberto |
| PROD-017 | falhas de foco, alvo, motion e semântica modal | auditoria frontend | pendente | pendente | axe/matriz de dispositivo | aberto |
| PROD-018 | Unfold canônico passa, config/passaporte incompletos | `make admin`: 229 aprovados | pendente | pendente | release checks/config resolvida | aberto |
| PROD-019 | apenas peso-alvo/print, nenhuma pesagem executada | auditoria domínio/frontend | desenho seguro pendente | pendente | sessão/leituras/lote | D5 |
| PROD-020 | capacidade nominal em `meta`, passos JSON vivos | auditoria domínio | discovery/projeção advisory pendentes | pendente | overlap/duração | D6 |
| PROD-021 | sem instrumentação de toque/handoff/baseline de turno | auditoria frontend | instrumentação/roteiro pendentes | pendente | métricas privacy-safe | D7 |

## WPs

| WP | Estado | Evidência/resumo | Próximo passo |
|---|---|---|---|
| P0.0 | parcial | baseline funcional, fixtures representativas, placar e auditorias versionados; host publicado inspecionado anonimamente | falta acesso autorizado a dados operacionais reais para produzir fixtures reais anonimizadas; não substituir por dados públicos/Pessoais |
| P0.1 | em preparação | auditoria confirmou gate grosso e `_full_access()` nas APIs | infraestrutura de capabilities; D1/D2 fecham grants finais |
| P0.2 | em execução | filtros/datas estritos verdes; schema/rev/idempotência ainda abertos | requests/actions/envelopes gerados e serializers de mutação |
| P0.3–P0.5 | auditados, não implementados | riscos reproduzidos por leitura e host | introduzir testes vermelhos e slices atômicos |
| P1.1–P1.6 | não iniciados | mutações dependem de P0.1–P0.3 | aguardar P0 |
| P2.1–P2.3 | não iniciados | substituição de fluxo depende de piloto P1 e D5–D7 | apenas preparação segura quando desbloqueada |

## Riscos novos e colisões

- Nenhuma colisão de escrita detectada no worktree exclusivo.
- O comando exato que originou os 105 testes backend da auditoria não está documentado no repositório. Foi preservada a evidência histórica e executada uma seleção atual mais ampla, com 178 aprovações.
- Avisos de sourcemap/depreciação apareceram no build E2E, sem falha; classificar no hardening se permanecerem após os WPs.
- O pacote editável `shopman-refs` do Python global passou a apontar para um worktree externo inexistente durante a sessão. Os comandos seguintes fixam `PYTHONPATH` para os pacotes deste worktree; nenhuma instalação global foi alterada.
- A inspeção anônima não dá acesso a WOs, pedidos, estoque ou QC reais. O requisito de fixtures reais anonimizadas permanece explícito, sem copiar catálogo público para fingir equivalência operacional.
