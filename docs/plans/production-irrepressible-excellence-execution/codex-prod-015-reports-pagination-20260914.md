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
- A API aceita `page_size` (1–100), `sort` e cursor opaco assinado. O cursor é vinculado às datas, filtros, relatório, sort e tamanho da página; adulteração ou reutilização em outro escopo retorna validação 400.
- Apenas o rowset do `report_kind` selecionado é retornado/paginado; os demais campos permanecem no contrato como listas vazias. A projection original continua disponível completa para os chamadores internos e para exportação.
- Ordenação servidor-side cobre data (histórico), nome e quantidade, com desempate determinístico.
- O CSV respeita os filtros e sort aplicados, deliberadamente ignora cursor/tamanho de página e é transmitido linha a linha. A proteção compartilhada contra CSV formula injection e o helper legado de bytes foram preservados.

## Evidências

- [x] backend focal: `36 passed` em API, projection/service e schema export;
- [x] regressões específicas: página seguinte sem sobreposição, anterior, sort, cursor adulterado e cursor incompatível com filtros;
- [x] frontend focal: `10 passed` para query/export, composable de fetch e estado rascunho→Aplicar;
- [x] suíte completa Production Nuxt: `38 files / 283 tests passed`;
- [x] TypeScript (`nuxi typecheck`) aprovado com Node 22 após disponibilizar as dependências do operator-kit na worktree;
- [x] build Nuxt de produção aprovado;
- [x] ESLint focal, Ruff e `git diff --check` aprovados;
- [ ] deep-links/passaporte, colunas sticky/prioridade responsiva e matriz browser/AA são frentes separadas do mesmo item de programa e não são declaradas concluídas por este patch.

## Observações de execução

- `origin/main` avançou para `2aff555a538126d88e1e263864b751607012f50c` depois da criação da worktree. O patch permanece deliberadamente sobre o SHA-base registrado, sem merge/rebase/push.
- Nenhum provider, deploy, PR ou merge foi executado.
