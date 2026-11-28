# ARQUIVAR-A: produto no Core

- **id:** ARQUIVAR-A
- **branch:** `codex/arquivar-core-produto`
- **PR:** #1945
- **estado final:** na fila, #1945
- **data:** 2026-10-20
- **ordem:** `docs/coordination/ORDERS/2026-10-19-arquivar.md`

## Entrega

- `Product.is_active` com default ativo, índice e migração `offerman.0005`, inclusive histórico.
- `Product.objects.active()`, `archived()` e `available_for_sale()` como caminhos canônicos.
- Produto arquivado não recebe preço, não passa como publicado/vendável nos contratos de estoque e
  produção, não entra nas buscas padrão, coleções ou substitutos e chega ao snapshot de canal como
  indisponível para que o mecanismo de retração existente opere.
- Arquivar e desarquivar preservam `is_published` e `is_sellable` e disparam `product_updated`, pois
  `is_active` integra `_PROJECTABLE_FIELDS`.
- Admin/Unfold nativo: lista padrão sem arquivados, filtro explícito “Arquivados”, selo e ações de
  detalhe Arquivar/Desarquivar em diálogo oficial `BaseDialogForm`. Nenhum template, HTML ou CSS
  customizado foi criado.

## Prova

- Offerman completo: **288 passed, 1 skipped**.
- Contrato focado de modelo, arquivamento e consultas: **39 passed**.
- Sinais e ações do Admin: **42 passed**; integração HTTP do filtro e dos diálogos: **6 passed**.
- Integração adicional do Admin composto: **11 passed**.
- `make admin`: **300 passed**, gate canônico aprovado.
- `make test-migrations`: **4 passed, 0 failed, 2 skipped**; schema do zero e grafo consistentes,
  nenhuma migração pendente e nenhuma colisão nova.
- Contagem de consultas, 2 e 30 produtos: projeção **5 → 5**; informações de SKU **3 → 3**;
  busca de SKU **3 → 3**; informações de produto **3 → 3**; busca de produto **3 → 3**.
- Numeração de `packages/offerman/shopman/offerman/migrations`: nenhuma duplicata.

## Fora da frente

- Nenhuma projection de superfície, app Nuxt ou território reservado foi alterado.
- A varredura das superfícies e a retração/reenvio com transporte simulado permanecem nas Frentes B
  e C da ordem.
- Não houve captura visual: a mudança usa exclusivamente primitives nativas de `ModelAdmin`, filtro
  e diálogo Unfold, sem tela ou template customizado.
