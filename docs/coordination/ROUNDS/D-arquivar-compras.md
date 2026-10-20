# D — Arquivados no Compras

- **id:** D
- **branch:** `codex/arquivar-compras`
- **PR:** #1946
- **estado final:** na fila (#1946, auto-merge ligado)
- **data:** 2026-10-20

## Objetivo

As listas de insumos e fornecedores do Compras mostram somente cadastros em uso por
padrão. O filtro explícito **Arquivados** troca o recorte para os cadastros arquivados,
com selo e contagens coerentes. A ação de arquivar ou restaurar permanece fora desta
frente.

## O que entrou

- A projeção aplica o recorte antes da contagem e da paginação, tanto para insumos quanto
  para fornecedores.
- A API aceita `material_archive=archived` e `supplier_archive=archived`; o BFF repassa
  apenas o filtro da lista correspondente.
- As duas telas usam a dimensão canônica **Cadastro**, a opção **Arquivados** e o selo
  **Arquivado**. O contador de cada aba vem do total do respectivo recorte.
- O mock hermético do navegador ganhou cadastros arquivados e respeita o mesmo contrato
  de filtro do backend.

## Evidência

- Backend focal: `47 passed in 25.30s`.
- Frontend focal: `2` arquivos e `8` testes passaram; ESLint dos arquivos tocados passou.
- Consultas da projeção: `28` no recorte corrente e `28` no recorte arquivado.
- API medida com `Server-Timing`: `33` consultas no recorte corrente e `32` no arquivado;
  o teste fixa que o recorte arquivado não pode custar mais que o corrente.
- Navegador, build de produção: `36 passed`, cobrindo insumos e fornecedores, antes e
  depois do filtro, em tema claro e escuro nos nove viewports canônicos, com varredura
  de geometria e zero respostas HTTP 4xx/5xx. As capturas foram abertas e conferidas.

### Correção do gate do PR

O primeiro CI executou a nova prova em toda a matriz e encontrou `16` falhas idênticas
fora do desktop: a captura final ainda mantinha o painel de filtros aberto, e a varredura
de geometria avaliava a opção interna **Envelope operacional** (`20×20`) como alvo de
toque. A causa foi reproduzida localmente (`4 failed` no tablet deitado). O cenário agora
fecha o popover ou a gaveta pelo gesto correspondente antes da captura final; assim a
varredura volta a medir a lista arquivada, que é o estado em prova. A matriz completa
passou em seguida (`36 passed`).

## Limite conhecido

O `npm run typecheck` global continua vermelho em dois usos preexistentes de
`navigateTo`: `app/pages/base/suppliers.vue:169` e `app/pages/index.vue:193`. A primeira
linha já existia antes desta frente e a segunda página não foi tocada; os testes, o lint
focal e o navegador passam. Nenhuma ação de arquivar ou restaurar foi criada.
