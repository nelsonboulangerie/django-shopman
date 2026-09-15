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
- Apenas o rowset do `report_kind` selecionado é retornado/paginado; os demais campos permanecem no contrato como listas vazias. A projection original continua disponível completa somente para os chamadores internos legados; API e exportação usam os caminhos específicos por relatório.
- Histórico aplica ordenação e `LIMIT` no queryset antes de materializar linhas. Produtividade, desperdício e qualidade executam somente sua agregação, percorrendo fontes em chunks e mantendo em memória apenas os grupos necessários.
- O CSV respeita os filtros e sort aplicados, deliberadamente ignora cursor/tamanho de página, emite BOM/cabeçalho antes de consultar linhas e transmite o histórico em chunks. A proteção compartilhada contra CSV formula injection e o helper legado de bytes foram preservados.
- A aba aplicada, tabela e CSV permanecem coerentes; troca de relatório aplica imediatamente e normaliza sort incompatível, enquanto qualquer outro rascunho desabilita o download até `Aplicar`.
- Erros de data usam `aria-invalid`, descrição associada e região viva; a faixa atual e reconciliação de cursor também são anunciadas.

## Evidências

- [x] backend focal/adversarial: `47 passed` em API, projection/service, CSV adversarial e schema export;
- [x] regressões específicas: `LIMIT` real de materialização, ausência de agregados irmãos, primeira emissão CSV sem query, página seguinte/anterior, sort, cursor adulterado/incompatível e mutação entre/durante páginas;
- [x] frontend focal: query/export, stale cursor e estado rascunho→Aplicar, incluindo normalização de aba/sort;
- [x] suíte completa Production Nuxt: `38 files / 285 tests passed`;
- [x] TypeScript (`nuxi typecheck`) aprovado com Node 22 após disponibilizar as dependências do operator-kit na worktree;
- [x] build Nuxt de produção aprovado;
- [x] ESLint focal, Ruff e `git diff --check` aprovados;
- [ ] deep-links/passaporte, colunas sticky/prioridade responsiva e matriz browser/AA são frentes separadas do mesmo item de programa e não são declaradas concluídas por este patch.

## Observações de execução

- `origin/main` avançou para `2aff555a538126d88e1e263864b751607012f50c` depois da criação da worktree. O patch permanece deliberadamente sobre o SHA-base registrado, sem merge/rebase/push.
- Nenhum provider, deploy, PR ou merge foi executado.
