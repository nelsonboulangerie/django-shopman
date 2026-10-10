# OBS0310-F: Histórico do Gestor e filtro universal do kit

- **id:** OBS0310-F
- **branch:** claude/obs0310-gestor-historico
- **PR:** #1412
- **início / fim (UTC):** 2026-10-03 13:25 / 2026-10-03 14:45

## O que mudou
- Backend: `GET /api/v1/backstage/orders/history/` (`api/order_history.py`, `projections/order_history.py`).
  Pedidos concluídos, cancelados e devolvidos, pelo momento em que FECHARAM. Filtros no servidor:
  período (`date_from`/`date_to`, até um ano), `status`, `channel`, `payment` (`none` = não informado),
  `fulfillment`, `q` (ref, ref externa, nome, telefone), `page` (30 por página). Cada recorte volta com
  as opções e a contagem, contada com os outros recortes aplicados e o próprio solto. Venda de balcão do
  PDV fica de fora (mesma régua do quadro). Gate `shop.manage_orders`. Filtro desconhecido, data
  malformada e intervalo invertido: 400 no dialeto `{detail, field, errors}`. Contrato gerado em
  `generated/ordersContract.ts`.
- Kit: a `FilterBar` que já existia (Catálogo, Encomendas do PDV) virou o filtro universal: tipos
  `text`, `number-range`, `date-range`; busca na lista a partir de 8 opções; chip que reabre a edição do
  próprio campo; painel de baixo no celular com linha de chips rolável. URL: `filtersToQuery`,
  `filtersFromQuery`, `mergeFilterQuery` e o composable `useRouteFilters`. Contrato no README do kit,
  seção "Filtro universal".
- Gestor: página `/history` (período pelo `OperatorPeriodPicker`, busca, FilterBar, paginação), aba
  "Histórico" na barra de seções, e o detalhe aberto pelo Histórico volta para o Histórico com o mesmo
  recorte (`?from=history`).

## Prova
- vitest pos-nuxt `tests/pages/preorders.test.ts` (consumidor da FilterBar): 62 passed.
- pytest: `test_api_order_history.py` + `test_orders_schema_export.py` + `test_api_orders_surface.py`: 32 passed.
- vitest operator-kit: 100 arquivos, 1065 testes passaram. orders-nuxt: 49 arquivos passaram
  (o `orderDetailActions` foi refeito depois de tolerar rota sem query: 39 passed). typecheck e lint limpos.

## O que ficou de fora
- Ordenação da lista (sempre do fechamento mais recente para o mais antigo).
- Exportar CSV.

## Perguntas ao dono
1. Venda de balcão do PDV fica FORA do Histórico (ela é do caixa e inundaria a lista). Manter fora? (sim / 2 = entrar como canal "Balcão")
2. Pedido DEVOLVIDO aparece junto (situação "Devolvido", só quando existe no período). Manter? (sim / não)
