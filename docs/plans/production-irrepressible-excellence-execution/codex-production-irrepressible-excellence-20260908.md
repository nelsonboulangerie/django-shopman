# Execução — Produção rumo à excelência irreprimível

- Sessão: `codex-production-irrepressible-excellence-20260908`
- Período: 2026-09-08 a 2026-09-09, `America/Sao_Paulo`
- Worktree exclusivo: `/Users/pablovalentini/Dev/Claude/.codex-worktrees/django-shopman-production-irrepressible-20260908`
- Branch: `codex/production-irrepressible-excellence-20260908`
- SHA-base: `b589e22c5c6963e79c4bf735b79eaf928b9ae6f7`
- HEAD técnico antes deste registro: `1e4af38c67da386191ca2a85641aa14cec0fe5fc`
- Plano de entrada: SHA-256 `f435f49347391b7d1bdb0e9de29a3278d14d17897bb93022b2880679014ac68d`.
- Estado de entrega: último resultado automatizável seguro; não é “pronto para piloto”, “rollout concluído” nem “plano concluído”.

O checkout compartilhado original foi preservado. O plano foi o único input não commitado
transportado ao worktree. Não houve merge, push, PR, deploy, escrita em produção, uso de
credencial real ou operação de hardware.

## Protocolo e preparação

Foram lidos integralmente o plano, ADR-012, ADR-014, ADR-017, ADR-018, o design system do
Backstage, o playbook e a política canônica do Unfold e o inventário Unfold. Não existe
`AGENTS.md` rastreado na árvore. A skill `unfold-admin-canonical` foi aplicada à revisão e
implementação do Admin: configuração permanece em fieldsets/widgets/inlines oficiais e a
operação diária permanece no Nuxt.

O protocolo multiagente foi executado com escopos serializados no mesmo worktree:

- `audit_domain_admin`: auditou e implementou os adapters de fórmula/reposição e o Admin;
  8 focais, Craftsman 260/2 skips e Stockman 266/14 skips.
- `audit_frontend_p0p1`: auditou P0.2/P0.5/P1, implementou borda HTTP e guard de mutação;
  o relatório exclusivo está em `codex-audit-frontend-p0p1-p0-5-20260908.md`.
- `audit_backend_p0`: encerrou por limite externo de uso depois de entregar achados; o agente
  raiz reproduziu, corrigiu e validou cada achado aproveitado.
- O agente raiz manteve ownership de contratos/migrations, reconciliou as integrações e rodou
  as suítes amplas. Nenhum subagente criou commit ou tocou outro worktree.

## Commits locais

| Commit | Slice | Evidência principal |
|---|---|---|
| `749f8f1e2` | plano normativo | hash do input e diff staged conferidos |
| `bd0c56268` | filtros/datas estritos | 43 testes verdes após 5 RED |
| `3bf936877` | baseline versionada | fixtures e placar de 100 WOs |
| `73d50e01f` | verdade de quantidade/qualidade | snapshot, started qty, catálogo estrito |
| `1d7495956` | zero-output seguro | zero não vira estoque vendável |
| `9e85d0ede` | projeções em lote | budgets abaixo, sem N+1 observado |
| `3cc03df58` | capacidades efetivas | negação por linha/action/API e alertas escopados |
| `a066b14f7` | mutações revisionadas | ator, revisão, idempotência, locks e conflitos tipados |
| `d003be80d` | contrato/cliente gerado | schema versionado e geração sem drift |
| `dd2aabfda` | integridade/action contracts | domínio, saga, alertas, pedidos, forno, Admin e testes |
| `1e4af38c6` | superfície de operador | guard stale/offline, QC, actions, headers e corte do menuboard |

## Baseline e placar após a mudança

Medição funcional local em SQLite/test client com 100 WOs; serve como comparativo, não como
p95 de produção.

| Projeção | Antes: queries / ms / bytes | Depois: queries / ms / bytes | Resultado |
|---|---:|---:|---|
| board | 492 / 160,245 / 231.844 | 18 / 39,235 / 312.380 | N+1 removido; payload cresceu pelo contrato de actions/freshness |
| KDS | 74 / 16,519 / 16.641 | 7 / 9,621 / 70.125 | budget estável |
| QC | 78 / 22,383 / 34.053 | 12 / 26,350 / 129.233 | facts/actions explícitos |
| mise en place | 85 / 24,942 / 5.971 | 14 / 11,472 / 6.711 | snapshot/started qty em lote |
| relatórios | 146 / 37,232 / 32.055 | 13 / 14,056 / 32.798 | filtros estritos e drilldown |
| pesagem | 17 / 14,079 / 1.797 | 18 / 9,696 / 2.561 | tabela fechada/versionada; execução real segue D5 |
| alertas | 8 / 2,521 / 266 | 8 / 3,207 / 1.442 | lifecycle, audiência e actions no payload |

## Resultado por pacote de trabalho

| WP | Estado verdadeiro | Resultado/evidência | Limite restante |
|---|---|---|---|
| P0.0 | técnico local concluído | fixtures versionadas, 100 WOs, métricas antes/depois e matriz de risco | fixture real anonimizada depende de acesso autorizado |
| P0.1 | infraestrutura concluída | `resolve_production_access`, filtragem, actions e endpoints usam a mesma capability; SSE espelha todos os grants do board | grants/aprovadores finais são D1; postura final é D2 |
| P0.2 | concluído | contrato v2, action metadata/proof, erros tipados, filtros estritos, cliente gerado e freshness | OpenAPI global antigo não é um gate verde; ver riscos |
| P0.3 | concluído em SQLite; runtime aberto | locks, revisão, idempotência, saga quick-finish recuperável, forno e step append-only, pedidos fail-closed | corrida real precisa PostgreSQL/Redis |
| P0.4 | concluído; D3 resolvido | started/snapshot, partição, catálogo estrito, conservação, desvio auditado e perda total auditável | decisão D3 registrada em 09/09 |
| P0.5 | código/build concluídos | headers/cache, upstream fail-fast, `/menuboard` removido, nenhum fetch storefront, Playwright 6/6 | edge/host, TVs e cutover são D4/D8 |
| P1.1 | concluído localmente | assemblers em lote, `generated_at`, `source_revision`, `fresh_until`, versão e action proof | p95 representativo depende de runtime/piloto |
| P1.2 | slice seguro concluído | múltiplas WOs expostas; nenhuma escolha `[0]`; edição/ação preserva contexto e conflitos | medição real de esforço é D7 |
| P1.3 | concluído | forno server-stamped, retry, QC por partição, confirmação de desvio, fechamento exato e perda total | matriz física depende de D7 |
| P1.4 | contrato honesto concluído | preparação usa snapshot/started qty; pesagem é projeção fechada e declara que ainda não executa pesagem | sessão/tolerância/impressão auditada são P2.1/D5 |
| P1.5 | parcial seguro | filtros estritos, drilldown existente, alertas escopados/acionáveis e ack distinto de resolve | export/paginação completa e SLO humano não foram inventados |
| P1.6 | concluído localmente | todos os blocos `ProductionConfig`, validação/release checks e passaporte somente leitura em Unfold; `make admin` verde | política final de approvals permanece D1 |
| P2.1 | bloqueado corretamente | pré-condições e lacuna documentadas | P1 precisa de piloto e D5 precisa decisão/hardware |
| P2.2 | bloqueado corretamente | nenhuma capacidade genérica foi inventada | P1 precisa de piloto e D6 de discovery |
| P2.3 | bloqueado corretamente | actions/alertas já reduzem ambiguidade sem nova política | depende de D7 e piloto |

## Matriz dos 21 resultados

| ID | Estado | Prova resumida/pendência |
|---|---|---|
| PROD-001 | infraestrutura entregue; D1/D2 | capability governa projeção, API, SSE e alerta; matriz final não foi presumida |
| PROD-002 | entregue | 8 mutações usam contrato gerado, ator, rev, chave estável e action proof |
| PROD-003 | entregue | quick finish tem preflight, uma WO por tentativa, replay e recuperação/compensação explícita |
| PROD-004 | entregue | step/oven sob transação, lock, rev e eventos append-only |
| PROD-005 | parcial; D1 | força exige capability, razão e snapshot assinado; aprovador distinto/final depende de D1 |
| PROD-006 | entregue; D3 resolvido em 09/09 | perda total conclui com `finished_qty=0`, WASTE integral e outcome auditável; não usa estorno |
| PROD-007 | entregue | planned usa planejado; started usa iniciado; snapshots congelados alimentam leitura/QC |
| PROD-008 | entregue | grade/defeito ausente, inativo ou desconhecido falha fechado |
| PROD-009 | código entregue; D4 | rota paralela removida; owner Django por ref preservado; TVs não mapeadas |
| PROD-010 | código entregue; host pendente | Nitro/BFF têm headers/cache/env fail-fast; scanner do edge exige deploy autorizado |
| PROD-011 | entregue localmente | budgets 100-WO acima; p95 real depende de PostgreSQL/dataset representativo |
| PROD-012 | entregue | seleção implícita removida e testada com múltiplas WOs |
| PROD-013 | entregue | stale/offline bloqueia write, preserva input e só permite refresh/reaplicação consciente |
| PROD-014 | entregue | audiência, dedupe, lifecycle, ação contextual e ack ≠ resolve |
| PROD-015 | parcial | validação/janela/drilldown cobertos; paginação/export completos não foram ampliados sem contrato |
| PROD-016 | parcial | checklist/etiquetas declaram verdade atual; job de impressão auditado pertence a D5/P2.1 |
| PROD-017 | parcial; D7/hardware | targets/guard/foco básicos e E2E passam; axe, leitor real e matriz visual humana continuam abertos |
| PROD-018 | entregue localmente | Unfold canônico, config estruturada, checks e passaporte; Admin 234/234 |
| PROD-019 | D5 | pesagem executada não iniciada antes de processo/tolerância/hardware reais |
| PROD-020 | D6 | passos/capacidade real não iniciados antes do discovery de gargalo |
| PROD-021 | D7 | instrumentação/budgets propostos; eficácia exige observar turnos e piloto |

## Provas automatizadas finais

| Gate/comando | Resultado |
|---|---|
| Backstage completo | 2.433 aprovados, 25 skips, 24 subtests; 487,51 s |
| Shop completo após regressões focais | 2.577 aprovados, 16 skips, 26 runtime deselectados, 10 subtests; 100,56 s |
| Craftsman | 260 aprovados, 2 skips |
| Stockman | 266 aprovados, 14 skips |
| Orderman | 289 aprovados |
| fluxo HTTP autêntico GET → action proof → POST | KDS advance → QC oven arm → conclude → finish, um evento de cada tipo |
| Produção Nuxt Vitest | 23 arquivos, 130 testes aprovados |
| Operator Kit Vitest | 17 arquivos, 177 testes aprovados |
| typecheck + lint Produção | aprovados |
| build Nuxt/Nitro Produção | aprovado com ambiente/HTTPS explícitos; warnings de sourcemap/depreciação |
| Playwright | 6/6: login, shell, menuboard ausente, headers, 404 e reconnect offline |
| `export_production_schema --check` | aprovado; arquivo gerado sem drift |
| `makemigrations --check --dry-run` | aprovado |
| `scripts/check_migrations.py` | 3 aprovados, 2 skips pré-go-live esperados |
| `make admin` | Unfold maturity aprovado + 234 testes aprovados |
| Ruff sobre Python alterado + `git diff --check` | aprovado |

## Gates que não estão verdes

- Runtime: `scripts/check_runtime_gate.py` falhou fechado porque não há `DATABASE_URL`,
  PostgreSQL, `REDIS_URL` nem `EVENTSTREAM_REDIS`. Os três testes novos de corrida de
  planejamento estão registrados em `DEFAULT_RUNTIME_TEST_PATHS`; nenhum resultado de SQLite
  é apresentado como prova de concorrência real.
- Release readiness em uma base temporária migrada e `seed --flush --profile qa`: 5 checks
  locais passaram, mas a matriz global Omotenashi ficou 9/11; faltam os cenários pré-existentes
  `mobile.payment.pix_pending_near_expiry` e `mobile.payment.pix_expired`. Há 3 bloqueios
  externos: credenciais de sandbox, evidência física/manual e URL de pre-prod. O banco original
  foi restaurado e a base temporária foi apagada.
- OpenAPI global: `manage.py spectacular --validate` gerou YAML, mas o extractor global reporta
  139 erros únicos e 8 warnings de APIs não tipadas fora/ao redor deste contrato. Portanto não é
  chamado de gate verde; o schema específico de Produção é o artefato versionado aprovado.
- `npm audit` do lock atual reportou 3 vulnerabilidades (2 moderadas, 1 alta). Não foi executado
  `audit fix`, pois isso alteraria dependências/lock fora do contrato e sem revisão de impacto.
- Docker não está instalado neste host; a imagem não foi construída. Browser/hardware reais,
  impressão 80 mm, balança e leitor de tela físico não foram simulados como evidência.

## Gates humanos — decisão exata necessária

| Gate | Fato e alternativas | Recomendação | Escolha necessária |
|---|---|---|---|
| D1 autoridade | capabilities e negação já existem; pode-se usar grants por grupo ou approvals por ação | grupos concedem leitura/operação comum; force, quick finish e void de alto impacto exigem step-up com aprovador distinto | matriz final por persona e lista de ações com aprovador obrigatório |
| D2 estação | `PRODUCTION_TRUSTED_STATION_CAPABILITIES` falha fechado por capability | exigir estação em mutações de chão/forno/QC; permitir consulta gerencial fora dela | conjunto exato de capabilities e processo de provisionar/revogar estação |
| D3 perda total | **Resolvido em 09/09/2026:** outcome `total_loss`, WO `finished`, WASTE integral e zero vendável; pedidos comprometidos bloqueiam até resolução | implementação e testes entregues | nenhuma decisão pendente |
| D4 TVs | Nuxt paralelo acabou; Django por `ref` é único owner | mapear cada TV a ref/credencial e fazer cutover sem redirect adivinhado | refs, credenciais, owner e janela de troca |
| D5 pesagem | hoje há alvo/etiqueta, não execução | piloto manual advisory antes de integração de balança ou bloqueio | processo, tolerâncias, lote/FIFO, impressora/balança e momento de bloquear |
| D6 capacidade | nenhum dado prova se gargalo é forno, masseira, bancada ou pessoa | instrumentar sobreposição primeiro, modelar somente o recurso observado | recurso, capacidade, calendário e regra de conflito |
| D7 omotenashi | budgets existem, baseline de turno não | observar Cozinha e Gerência com roteiro idêntico antes/depois | turnos, participantes, metas e autorização de coleta privacy-safe |
| D8 piloto | build candidato existe, mas gates anteriores/runtime/host estão abertos | uma estação/equipe, flags advisory, abort criteria e rollback ensaiado | estação, equipe, janela, owner, métricas e autorização de deploy |

## Manifesto de cobertura

Classificação dos arquivos/áreas exigidos na seção 12:

- **Alterar:** `nuxt.config.ts`, `app.vue`, `ProductionStageGrid.vue`, `QcCloseScreen.vue`,
  `ShortageDialog.vue`, `AlertsBell.vue`, `expedite.vue`, composables de board/KDS/QC/forno/
  alertas, tipos, contrato gerado, proxy/headers do Operator Kit, API/filtros/permissões/
  projeções/serviços/modelos de produção/alertas/forno, handlers Stockman/pedido, configuração,
  Admin de Shop/qualidade/WO, checks, ADR-018, READMEs, robots e testes correspondentes.
- **Aposentar:** `app/pages/menuboard.vue`; seus assertions públicas foram substituídas por
  ausência de rota e ausência de fetch ao storefront. O menuboard Django canônico foi preservado.
- **Preservar com teste:** rotas `index`, `plan`, `mise-en-place`, `board` e `reports`; login,
  header, SplitFlap, WeighingLabels; primitivos UI locais; adaptive poll, blind map, board pages,
  flap audio, timers, reports access, reports presentation e sessão genérica. Não foram
  reescritos quando o risco já era coberto ou pertencia aos gates D4–D7.
- **Mover/consolidar:** política de headers/cache e validação do upstream foram para o
  `operator-kit`; writes de fórmula/reposição agora resolvem o adapter canônico do host por
  setting, removendo imports Backstage dos pacotes kernel; o adapter Stockman legado virou proxy.
- **Preservar sem mudança material:** package/lock, favicon, gitignore, configs Vitest/ESLint/
  TS/UI, CSS/tokens, configs/URLs de deploy e componentes UI gerados. Não havia dependência nova
  necessária, o cânone existente foi suficiente e mudar esses hotspots não melhoraria o aceite.

## Riscos de integração e rollback

1. A branch `main` observada no handoff está em `e0740f8a7`, muito à frente do SHA-base e com
   mudanças sobrepostas. A integração precisa ser um rebase/merge semântico em worktree novo,
   seguido de todas as suítes; não aplicar arquivos inteiros “ours/theirs”.
2. `main` já possui migrations Backstage até `0047`; as migrations locais `0039`/`0040` colidem
   nominalmente e devem ser renumeradas/regeneradas depois da integração. Em Craftsman, `main`
   possui `0007_recipe_book`, enquanto esta linha tem outro `0007` e `0008`; reconciliar o grafo
   e gerar merge migration quando necessário.
3. `app/generated/productionContract.ts` é hotspot gerado: integrar backend primeiro e executar
   novamente `export_production_schema`, nunca resolver o arquivo manualmente.
4. Rollback local da superfície é desligar o leitor/flag e voltar ao reader anterior, sem
   reverter eventos já gravados. A rota pública `/menuboard` não deve ser restaurada como rollback.
5. CSP ainda usa `script-src 'unsafe-inline'` para a hidratação Nuxt; `unsafe-eval` e origens
   externas permanecem fechados. Nonce é hardening futuro, não motivo para relaxar a política.

## Fechamento da integração com `main` — 09/09/2026

A dívida de integração acima foi resolvida numa worktree isolada, sem escrever na checkout
principal e sem push/deploy:

- branch: `codex/production-excellence-integrate-main-20260909`;
- base: `origin/main` em `e0740f8a7`;
- origem funcional: os 12 commits de
  `codex/production-irrepressible-excellence-20260908` até `292e2a853`;
- estratégia: cherry-pick semântico, preservando o histórico; nenhum arquivo conflitante foi
  aceito integralmente como `ours`/`theirs`.

Resoluções materiais:

1. A semântica recente de margem de rendimento, seleção explícita de múltiplas WOs, grants de
   relatório do Gerente, navegação Admin e pagamentos da `main` foi combinada com snapshots,
   capabilities, CAS, idempotência, freshness e action proofs desta execução.
2. O cliente Nuxt continuou derivado de `export_production_schema`; o arquivo gerado foi
   regenerado depois do backend, não resolvido à mão.
3. O grafo de migrations foi linearizado: `shop.0038_qualitygrade_is_active` segue a folha
   `0037`; Backstage usa `0048`–`0052` após a folha `0047`; Craftsman consolida os choices
   finais em `0008_alter_workorderevent_kind`, dependente de `0007_recipe_book`.
4. Testes antigos foram adaptados ao contrato irreversível final — ator, `expected_rev`,
   `idempotency_key`, prova fresca e linhagem histórica de pedidos — sem afrouxar os guards.
5. O projection assembler passou a importar `normalize_recipe_item_unit` pela fachada pública
   de `craftsman.models`; o probe do runtime gate passou a construir um `PYTHONPATH` hermético
   para worktrees que reutilizam uma venv de outra checkout.

Provas finais sobre a linha integrada:

| Gate | Resultado integrado |
|---|---|
| Backend completo | 3.594 aprovados, 16 skips, 26 deselectados e 10 subtests; 135,59 s |
| Migrações | 3 checks aprovados; schema criado do zero; 2 skips pré-go-live esperados |
| Produção Nuxt | lint, typecheck e build aprovados; 30 arquivos / 203 testes |
| Operator Kit | 21 arquivos / 217 testes |
| schema de Produção | 6 testes; contrato regenerado sem drift |
| smoke local autenticado | `/`, `/plan`, `/mise-en-place`, `/expedite`, `/reports` e `/board` carregados sem erro |
| diff | worktree limpa após os commits de integração; `git diff --check` aprovado |

Os gates humanos D1–D8, runtime PostgreSQL/Redis, hardware, host/edge e piloto continuam
explicitamente abertos. A integração fecha a dívida Git/migrations; não transforma essas
decisões externas em aprovação implícita.

## Refino de produto decidido com o dono — 09/09/2026

O diálogo operacional posterior fechou semânticas que o plano original havia deixado como
gate e elas foram implementadas diretamente sobre a linha integrada:

1. A linguagem da superfície é **Planejado → Produzido → Concluído**; o gesto é **Confirmar**.
   Os nomes internos `planned/started/finished` foram preservados para evitar migração semântica
   do ledger.
2. Os próprios botões Ótimo, Normal, Razoável e Mínimo são os graus de QC. Normal é o padrão e
   recebe o saldo automático. Cada grau aparece no máximo uma vez; Ótimo/Normal pedem somente
   quantidade, Razoável/Mínimo pedem quantidade + um motivo principal, e Perda permanece
   quantidade + motivo. Não existem ações paralelas “Detalhar” ou “Registrar variação”.
3. Grau governa preço/elegibilidade; motivo explica a causa. `Batch.quality_grade_ref` congela
   esse fato junto ao lote. Canais remotos aceitam invariavelmente apenas `excellent|standard`,
   inclusive diante de override equivocado; somente o PDV local pode habilitar markdown.
4. Perda total agora é uma conclusão auditável: insumos/execução são consumidos, WASTE integral
   é gravado, `finished_qty=0`, nenhum lote vendável nasce e o evento registra
   `production_outcome.kind=total_loss`. Não é `void` nem estorno. Pedidos comprometidos continuam
   bloqueando o fechamento até resolução explícita.
5. Timer é lembrete local múltiplo por fornada e de duração livre: repete até **Visto**, memoriza
   a última duração e permite `+1/+5/+10`. **Visto** só silencia; não retira do forno, não abre QC
   e não conclui produção. O fato “retirou do forno” é gravado ao entrar no QC.
6. `production_stock_shortfall` pertence à audiência Produção e aponta para a WO na matriz;
   resolução com cliente continua pertencendo ao Gestor, não ao alerta técnico do chão.

Migrations aplicadas localmente: `backstage.0053`, `stockman.0003`, `shop.0039` e `shop.0040`.
A superfície
ficou disponível em `http://127.0.0.1:3005/expedite`, com Django reiniciado em
`http://127.0.0.1:8000`.

Provas deste refino:

| Gate | Resultado |
|---|---|
| Backend de integração (produção/QC/config/alertas/canais) | 243 aprovados |
| Stockman completo | 273 aprovados, 14 skips |
| Craftsman — cenários de conclusão | 33 aprovados |
| Contrato HTTP de Produção | 65 aprovados |
| Nuxt completo | 31 arquivos / 214 testes aprovados |
| Typecheck + ESLint | aprovados |
| Ruff + `git diff --check` | aprovados |
| `makemigrations --check --dry-run` | sem drift |
| Migrations locais | rollback/reapply de `shop.0039/0040` e `backstage.0053` aprovados |

A revisão adversarial posterior também fechou três falhas de segurança operacional: o fechamento
exige conservação exata (`produzido + perda = total que entrou`); perda total elimina a oferta
planejada sem criar estoque fantasma; e holds remotos congelam a política de graus permitidos e a
revalidam no fulfillment. `Visto` em alertas apenas registra ciência: o alerta continua ativo até
resolução, e o destino contextual vem do backend, não de inferência do cliente.

O fechamento de uma WO parcialmente iniciada também cancela somente o saldo daquela WO que não
entrou em produção, preservando contribuições de outras WOs no Quant compartilhado. O grau é
persistido no `Batch` com conflito fail-closed. Holds criados pelo contrato novo levam uma versão
explícita da política; hold ativo legado sem essa versão não materializa nem é entregue. Como o
canal não era um fato obrigatório no legado, o cutover real deve inventariar e recriar esses holds
antes de ativar a versão — não existe backfill seguro por suposição.

Com isso, o gate **D3 — perda total** está resolvido por decisão explícita do dono e prova
automatizada. D1/D2/D4–D8 permanecem sujeitos às decisões e evidências externas já registradas;
este refino não as presume.

### Fechamento adversarial do refino

A última rodada multiagente removeu quatro becos sem saída operacionais: links de alertas agora
levam a `q + target_date` e as telas respeitam ambos; yield baixo e falha de rastreabilidade abrem
na Expedição; um retry bem-sucedido encerra a falha de rastreabilidade; e uma causa ainda aberta
não volta a gerar alertas só porque passaram 12 horas. **Yield baixo** foi classificado
explicitamente como fato histórico/BI: quantidade e motivo já foram registrados no QC, portanto o
registro/notificação é preservado e encerrado pelo ator de sistema, sem inventar uma pendência
eterna para o operador. A migration `backstage.0054` encerra os registros legados equivalentes.

Provas finais adicionais: 242 testes do recorte integrado; 48 testes focais de alerta/produção;
274 testes Stockman com 14 skips; 30 testes Craftsman de execução/conclusão; 216 testes Nuxt;
typecheck, ESLint, Ruff, `git diff --check`, `manage.py check` e
`makemigrations --check --dry-run` aprovados. A revisão multiagente final não encontrou blocker,
P0 ou P1 após o reparo.

Por decisão explícita do dono, o seed também passou a ser tratado como contrato executável deste
domínio. Estoque perecível demonstrativo conhecido como Normal recebe `standard`; o histórico de
produção passa pelo mesmo resolvedor de partição do QC e cobre Ótimo, Normal, Razoável, Mínimo,
graus mistos, motivos ortogonais, conservação e perda total. Cada OUTPUT tem lote e snapshot da
política; cada WASTE tem motivo e nunca grau/lote. Razoável/Mínimo exigem causa por identidade do
grau, mesmo que o markdown configurado seja zero.

O seed pode atualizar lotes que carregam sua própria assinatura, inclusive os gerados por versões
anteriores da carga, mas recusa reclassificar qualquer lote real. Medições sintéticas de forno são
fatos concluídos de BI (não timers locais), levam `metadata.seed=nelson`, nascem somente de WOs do
seed e nunca substituem uma medição real. `--flush` remove as medições junto com todas as WOs para
não deixar refs órfãs; o seed sem flush renova somente fatos sintéticos. As oito provas operacionais
do seed — suíte completa mais proteções focais — passaram, e a carga sem flush atualizou com sucesso
o banco local usado pela superfície.

A rodada final acrescentou ainda a mesma trava do trio congelado de QC nos Admins Unfold e fallback,
e alinhou o dashboard legado ao lifecycle canônico: **Visto** mantém a causa ativa até `resolved_at`.
O gate canônico do Admin aprovou 245 testes; o recorte integrado aprovou 199; o Nuxt aprovou 217,
além de typecheck, ESLint, Ruff, `git diff --check`, `manage.py check` e ausência de drift de
migrations. A revisão multiagente derradeira não encontrou blocker, P0 ou P1 remanescente.

## Fermata, entrega ativa e corte de dados — 09/09/2026

O ensaio manual solicitado pelo dono revelou um falso positivo importante: uma Directive podia
terminar como entregue sem destinatário real. A cópia recebida por SMS confirmou a semântica
correta do evento — a fornada ficou disponível e aguardava a decisão do cliente —, mas expôs que
o sistema precisava diferenciar aceite externo, opt-out legítimo e ausência/falha de rota.

O fechamento deste slice estabeleceu os seguintes invariantes:

1. A fermata só abre janela depois que todos os holds planejados do pedido foram materializados e
   toda reserva das demais linhas continua viva. Estado, prazo e outbox são gravados na mesma
   transação; uma falha ao enfileirar o aviso não inicia um relógio silencioso.
2. Confirmação, sweep e liberação serializam a Order e seus Holds. A liberação é idempotente,
   devolve todas as linhas do pedido e nunca transforma uma linha sob demanda (`quant=None`) em
   capacidade física para servir o próximo cliente.
3. Avisos transacionais ativos falham alto quando identidade, preferências, destinatário ou
   backend estão indisponíveis. Opt-out explícito e pedido anônimo administrado pelo PDV/iFood são
   skips auditáveis; link de pagamento sem destino nunca é skip.
4. A Directive guarda prova minimizada da entrega: status, backend realmente tentado,
   identificador do provider quando existente e fingerprint irreversível do destinatário. Replay
   depois de aceite não reenvia. `IdempotencyKey` mantém a identidade original permanente, mesmo
   depois de a Directive terminar; reenvio explícito usa identidade própria.
5. Os canais `web` e `whatsapp` passam a receber por data migration a política de fermata de dois
   dias, janela de 15 minutos, cobrança na confirmação e cadeia `manychat → sms → email`. iFood
   permanece sem fila própria. O seed reproduz exatamente esse contrato.
6. O catálogo de QC do seed é reconstruído por `--flush` e reparado atomicamente sem violar ranks
   únicos. Conflito com catálogo não canônico é recusado antes de mutação parcial.
7. Lote nomeado sem fato `Batch` correspondente falha fechado em leitura unitária, leitura bulk e
   reserva sob allowlist de QC; estoque genuinamente sem lote permanece elegível e pode completar
   o fulfillment.
8. A migration `shop.0042` congela a versão/allowlist nos holds ativos legados somente quando o
   canal pode ser provado por Order, Session ou propósito de WorkOrder. Dono desconhecido aborta o
   deploy em vez de inventar política. O rollback remove apenas os campos marcados pelo próprio
   backfill.
9. O teto remoto usa a maior capacidade integralmente reservável entre hoje e a **primeira**
   fornada elegível, nunca a soma de datas incompatíveis. Catálogo e reserva consultam o mesmo
   scope de posição, validade e QC; fornada inelegível não vira promessa.
10. `qa_scenarios --arm` valida tudo antes de escrever e congela um snapshot reversível. O reset
    desfaz somente os deltas do próprio comando, preserva movimentos reais intermediários e
    restaura as pausas anteriores em vez de reconstruir um alvo presumido do seed.
11. Holds físicos sem janela e pedidos confirmados sem cobrança/outbox são receipts duráveis:
    o sweep os reconcilia com chaves idempotentes. Assim, queda do processo depois do commit não
    exige outra fornada nem outro clique do cliente para convergir.
12. A confirmação de pedido misto cruza todos os `hold_ids` adotados no pedido com os holds vivos
    sob lock. Reserva ausente, expirada ou terminal em qualquer linha bloqueia a CTA do pedido
    inteiro. Liberação multi-item faz rollback integral e só serve o próximo após soltar locks.

Inventário somente leitura da alpha antes do corte: dois holds ativos legados, ambos ligados a
pedidos já concluídos; nenhum pedido ativo afetado. Foram encontrados quatro Quants históricos
com batch textual órfão, três com saldo zero e um com saldo 2, sem holds ou pedidos dependentes.
Isso não bloqueia o cutover, mas permanece como higiene histórica explícita.

Provas finais deste slice:

| Gate | Resultado |
|---|---|
| Shop completo | 3.656 aprovados, 17 skips, 26 deselectados e 10 subtests |
| Stockman completo | 278 aprovados, 14 skips |
| Storefront web completo | 613 aprovados |
| Seed — contratos e cenários operacionais | 74 aprovados |
| Notificação/idempotência/consentimento | 231 aprovados, 2 skips PostgreSQL |
| Waitlist focal | 41 aprovados, 1 skip PostgreSQL |
| Migrações | 3 checks aprovados; banco vazio migrado; 2 skips pré-go-live esperados |
| Qualidade estática | Ruff e `git diff --check` aprovados |
| Django | sem drift de models/migrations; somente warnings locais esperados de SQLite/fiscal |

A concorrência real específica de notification receipts e cobrança pós-confirmação continua
marcada para PostgreSQL e registrada no executor obrigatório de runtime; SQLite local prova os
replays determinísticos, mas não é apresentado como prova da disputa física. O canal
ManyChat ainda depende de um Utility Flow aprovado para mensagens proativas fora da janela de 24
horas; a queda imediata para SMS/e-mail permanece a rede operacional real. A autorização do dono
neste diálogo permite publicar o candidato na **alpha** e validar host/edge; não equivale ao piloto
de turno nem encerra D1/D2/D4–D8.
