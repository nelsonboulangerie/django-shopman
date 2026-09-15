# Execução — PROD-015: relatórios operacionais paginados

**Data:** 14 de setembro de 2026

**Worktree exclusivo:** `/tmp/shopman-production-reports.eawUWg`

**Branch:** `codex/production-reports-pagination-20260914`

**SHA-base:** `84e07c01d04eba4ed0deabdae0d2df18dde77c53` (`origin/main` no início da execução)

**Escopo:** fechar somente o gap automatizável comprovado do WP-P1.5/PROD-015: validação anterior ao request, aplicação explícita de filtros, paginação/cursor, ordenação servidor-side e exportação síncrona controlada. Deep-links, FilterBar/ColumnPicker, responsividade visual e qualquer decisão de BI ficaram fora deste patch.

## Estado reproduzido

- `reports.vue` construía a query diretamente dos `v-model`; cada tecla e cada seleção alteravam o `useFetch`.
- O endpoint validava o intervalo máximo de 93 dias, mas retornava todas as linhas e não aceitava cursor, tamanho de página ou ordenação.
- O download CSV era protegido contra fórmula e limitado a 93 dias, porém montava o arquivo inteiro em `StringIO` antes de responder.
- O limite histórico de dez linhas em desperdício impedia paginação real desse relatório.

## Implementação

- Filtros de rascunho e filtros aplicados foram separados; digitar/selecionar não muda a query até `Aplicar`.
- Datas invertidas, ausentes e intervalos acima de 93 dias são bloqueados no cliente antes do request; o backend continua sendo a autoridade e mantém a validação estrita.
- A API aceita `page_size` (1–100), `sort` e cursor opaco assinado. O cursor é vinculado às datas, filtros, relatório, sort, tamanho da página e revisão do conjunto; adulteração/reuso em outro escopo retorna 400, enquanto mutação entre páginas ou durante a montagem retorna 409 com reconciliação explícita.
- O contrato v1 legado continua retornando histórico, produtividade, desperdício e qualidade juntos por padrão. O cliente Nuxt envia o opt-in explícito `selected_only=true`; só nesse modo o rowset selecionado é paginado e os siblings permanecem vazios, sem alterar silenciosamente integrações existentes.
- Histórico aplica ordenação e `LIMIT/OFFSET` no queryset antes de materializar linhas. Produtividade e desperdício percorrem somente sua fonte em chunks e calculam médias com acumuladores exatos de memória constante; qualidade deriva da autoridade canônica `effective_partitions`, portanto a última `QUALITY_CORRECTED` substitui a partição física original.
- O CSV respeita os filtros e sort aplicados, ignora cursor/tamanho de página, emite BOM/cabeçalho antes de consultar linhas e transmite o histórico em chunks. Ele não alega snapshot transacional durante uma resposta streaming: vincula a exportação à revisão do conjunto e interrompe o stream se detectar mudança concorrente. A proteção compartilhada contra CSV formula injection e o helper legado de bytes foram preservados.
- O download deixou de ser um anchor direto: o composable controla pending/success/failure/session-expiry, cancelamento por `AbortController` e bloqueio enquanto filtros estão sujos/inválidos ou o cursor está stale.
- A aba aplicada, tabela e CSV permanecem coerentes; troca de relatório aplica imediatamente e normaliza sort incompatível, enquanto qualquer outro rascunho desabilita o download até `Aplicar`.
- Erros de data usam `aria-invalid`, descrição associada e região viva; a faixa atual e reconciliação de cursor também são anunciadas. Um 409 entra em estado dedicado bloqueado/recovery-only e não renderiza uma tabela vazia enganosa.

## Evidências

- [x] backend focal/adversarial: `50 passed` em API, projection/service, CSV adversarial e schema export;
- [x] regressões específicas: SQL `LIMIT/OFFSET` capturado com budget de queries, ausência de agregados irmãos, contrato legado com siblings, opt-in single-kind, primeira emissão CSV sem query, correção QC refletida em JSON/CSV, médias online, página seguinte/anterior, sort, cursor adulterado/incompatível e mutação entre/durante páginas/exportação;
- [x] frontend focal: lifecycle/cancelamento de export, query opt-in, stale cursor e estado rascunho→Aplicar, incluindo normalização de aba/sort;
- [x] suíte completa Production Nuxt: `38 files / 287 tests passed`;
- [x] TypeScript (`nuxi typecheck`) aprovado com Node 22 após disponibilizar as dependências do operator-kit na worktree;
- [x] build Nuxt de produção aprovado;
- [x] ESLint focal, Ruff e `git diff --check` aprovados;
- [ ] deep-links/passaporte, colunas sticky/prioridade responsiva e matriz browser/AA são frentes separadas do mesmo item de programa e não são declaradas concluídas por este patch.

## Observações de execução

- `origin/main` avançou para `2aff555a538126d88e1e263864b751607012f50c` depois da criação da worktree. O patch permanece deliberadamente sobre o SHA-base registrado, sem merge/rebase/push.
- Nenhum provider, deploy, PR ou merge foi executado.
