# D42 — PDV: o envio da venda leva o total mostrado; o servidor recusa se mudou

- **id:** D42
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente em worktree próprio)
- **branch:** claude/pdv-total-esperado
- **PR:** #1389
- **estado final:** mergeado #1389
- **início / fim (UTC):** 2026-10-02 18:20 / 2026-10-02 19:30

## O que mudou
Dono: "sim, agora" (02/10, chat). `shopman/shop/services/pos_intent.py:63,254`: chave `expected_total_q` (inteiro ≥ 0). `shopman/shop/services/pos.py:350`: `close_sale` chama `_ensure_expected_total` (~:470), que recalcula pela mesma conta da revisão e recusa, antes de qualquer escrita, total diferente para cima ou para baixo: 422 `total_changed`, "O total mudou de R$ 30,00 para R$ 26,00. Confira com o cliente antes de cobrar.", `context {old_total_q, new_total_q}` (mesmo nome do checkout da loja). Retentativa com `client_request_id` que já virou pedido devolve a venda feita. `shopman/backstage/api/operations.py:5646` exige o campo (`expected_total_required` sem ele; único cliente é o `usePosSale.ts`). PDV: `posIntent.ts` (`withExpectedTotal`, `isTotalChangedRefusal`), `usePosSale.ts` manda `review.total_q`, mostra a recusa e refaz a revisão. Contrato em `docs/reference/backstage-pos-surface-contract.md`.

## Prova
`shopman/backstage/tests/test_pos_total_esperado.py` (6): sem a mudança 6 reprovam; com ela 6 passam. `usePosSale.expectedTotal.test.ts` (2): 2 reprovam / 2 passam. backstage 7483 passed, shop 10879 passed, pos-nuxt 1450 passed; CI obrigatória verde.

## O que ficou de fora
A recusa chega como toast (some em segundos); o que fica é o total novo já revisado. Resta uma janela curta entre a conferência e o commit (a mesma do checkout da loja, E03). `close_sale` chamado direto em Python (só testes) ainda pode omitir o campo.

## Perguntas ao dono
nada

## Armadilhas novas
O fechamento do PDV agora EXIGE `expected_total_q` pela HTTP: cliente novo do `/pos/sale/close/` tem de mandar o total que mostrou.

## Próximo passo
nada
