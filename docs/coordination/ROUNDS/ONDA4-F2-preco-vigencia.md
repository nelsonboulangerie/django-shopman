# ONDA4-F2: preço com vigência

- **Data:** 2026-10-20.
- **Branch:** `codex/preco-vigencia`.
- **Ordem:** `ORDERS/next-onda4.md`, frente 2.
- **Estado:** em execução, publicação draft durante a validação final.

## Entrega

A matriz projeta as datas da Listing em cada célula de canal. O selo descreve
as duas pontas quando existem, ou a única ponta definida. Feed não recebe preço
nem vigência inventada. A lista abre em Hoje e ordenada pelo início da vigência,
com atalhos do OperatorFilterPanel, datas personalizadas e a opção Qualquer data
para consultar também cadastros sem preço vinculado a canal.

A janela cruza vigências com limites inclusivos, no banco. As duas pontas precisam
casar na mesma Listing. O filtro de canal restringe a mesma consulta; paginação,
contagem e facetas continuam no servidor. O contrato da resposta informa a janela
consultada para evitar tratar resposta de outra janela como leitura atual.

## Validação em andamento

- Antes: 32 consultas para 2 e 62 produtos. O endpoint não emitia Server-Timing.
- O mixin canônico foi ligado à matriz. O teste de orçamento agora inclui 60
  ListingItems adicionais e exige crescimento do total de 2 para 62 sem aumentar
  as consultas da página de 10 linhas.
- Frontend focado: 80 passed. Typecheck inicial passou.
- Backend amplo: 118 passed e uma falha no guard de chaves fixas; o guard foi
  atualizado junto do contrato. Reexecução focada em andamento.
- Exportação do contrato executada: nenhum diff em ordersContract.ts, pois a
  matriz usa o mirror types/catalog.ts, alterado nesta frente.
- Capturas anteriores claro/escuro abertas. Build e capturas finais em andamento.
