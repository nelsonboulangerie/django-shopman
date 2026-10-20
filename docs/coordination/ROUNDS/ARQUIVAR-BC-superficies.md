# ARQUIVAR-BC: superfícies e trava transversal

- **id:** ARQUIVAR-BC
- **branch:** `codex/arquivar-superficies`
- **PR:** #1947
- **estado final:** na fila, #1947
- **data:** 2026-10-20
- **ordem:** `docs/coordination/ORDERS/2026-10-19-arquivar.md`

## Entrega

- Loja online e busca usam a leitura canônica ativa e não expõem produto arquivado.
- A matriz do Gestor esconde arquivados por padrão e oferece o filtro explícito **Arquivados**,
  composto com coleção e acompanhado do selo **Arquivado**. Publicado e vendável permanecem
  intactos; todas as células ficam indisponíveis enquanto o produto está arquivado.
- Google e Meta retiram o item dos feeds. Os snapshots de iFood e Meta mantêm o SKU como
  indisponível para o caminho retract-aware existente.
- Arquivar dispara reconcile e retrai o item remoto; desarquivar reenvia. A prova usa o
  `CatalogProjectHandler` e um transporte simulado, sem editar o adapter do iFood reservado pelo
  PR #1905.
- B.I., pendências de vocação e pendência fiscal ignoram produtos arquivados.
- A trava transversal concentra loja, busca, matriz, Google, Meta, iFood e B.I. num caso que mantém
  `is_published=True` e `is_sellable=True` no produto arquivado.

## Provas

- A trava executada contra a Frente A pura (`72a0dfd88`) falhou porque a loja ainda devolvia
  `ARQUIVADO`; com a varredura desta frente, passou.
- Backend ampliado, incluindo Server-Timing: **350 passed, 4 skipped**.
- Orders Nuxt: **74 passed**; typecheck, lint e build verdes.
- Browser de produção: carga direta do Catálogo em celular e mesa, **5 passed**; filtro, chip e selo
  Arquivado em claro/escuro, zero resposta 4xx/5xx, **1 passed**. As quatro capturas
  `arquivar-superficies-*` foram abertas e conferidas.
- Consultas do catálogo: montagem rica em **29**; escala constante, **6 produtos = 25** e
  **66 produtos = 25**.
- `makemigrations --check --dry-run`: nenhuma mudança pendente; a frente não cria migração.

## Integração

- O trabalho começou empilhado sobre a Frente A, ainda draft, e só foi finalizado depois do merge
  do PR #1945 e de `git merge origin/main`, como determina a ordem.
- O PR #1905 continuava aberto e mergeável na conferência final; o arquivo
  `shopman/shop/adapters/catalog_projection_ifood.py` permaneceu intocado.
