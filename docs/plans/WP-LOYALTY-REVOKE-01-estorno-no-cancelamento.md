# WP-LOYALTY-REVOKE-01 — Estorno de pontos no cancelamento e na devolução

## Problema

O lifecycle credita pontos de fidelidade em `_on_completed` (`loyalty.earn(order)` →
Directive `loyalty.earn`, idempotente por `reference="order:{ref}"` +
`has_loyalty_transaction`). Nem `_on_cancelled` nem `_on_returned` estornam. Com o
counter_handoff (PR #305) a venda de balcão nasce `completed` e pode ser cancelada na
janela do PIN gerencial (`completed→cancelled` no lifecycle do canal pdv): cancela a
venda, os pontos ficam.

## Decisão principal: Directive `loyalty.revoke`, não estorno síncrono

O estorno é um comando async que precisa de retry confiável (o adapter pode falhar; o
earn pode estar em voo) e não precisa de retorno síncrono dentro do cancelamento —
exatamente o caso de Directive da [ADR-003](../decisions/adr-003-directives-sem-celery.md),
e o espelho do próprio `loyalty.earn`. Síncrono no lifecycle acoplaria o cancelamento
(que já faz estoque + pagamento + fiscal) a uma falha de fidelidade, que é não-crítica.

## Desenho

1. **Enfileirar** — `services/loyalty.py` ganha `revoke(order, reason)` (reason ∈
   {cancelled, returned}, só para a descrição da transação). Mesmo guard do earn
   (`total_q <= 0` → return). Criação via `directives.create_deduped` com
   `dedupe_key="loyalty.revoke:{order.ref}"` — no máximo uma directive viva por pedido.
   `_on_cancelled` e `_on_returned` chamam.

2. **Handler `LoyaltyRevokeHandler`** (topic `loyalty.revoke`):
   - resolve `customer_ref` (mesmo helper do earn); sem ref → no-op;
   - **dedupe**: já existe transação `adjust` com `reference="order:{ref}"` → skip
     (dois revokes = um estorno);
   - **earn nunca creditou**: sem transação `earn` para a reference →
     - se existe directive `loyalty.earn` viva (queued/running) para o pedido:
       `DirectiveTransientError` — re-agenda até o earn assentar;
     - senão: no-op (nada foi creditado, nada a estornar);
   - **estorno**: pontos = soma dos `points` das transações `earn` com a reference —
     a transação é a fonte da verdade, nunca recalcular pela config atual
     (`points_per_real` pode ter mudado entre o crédito e o estorno);
   - debita via `adapter.adjust_points(customer_ref, -points, ...)`.

3. **Guard no earn** — `LoyaltyEarnHandler` passa a pular pedidos em
   `cancelled`/`returned` (nunca creditar pedido cancelado). É a segunda metade da
   corrida earn-na-fila: mesmo se o revoke exaurir `MAX_ATTEMPTS` (5) esperando, o
   earn atrasado vê o status e não credita — o estado final é correto pelos dois
   caminhos. (O Directive não tem status "cancelled", então matar a directive earn na
   fila seria inventar um estado; o guard resolve sem tocar o Core do orderman.)

4. **Core (guestman)** — `LoyaltyService.adjust_points(customer_ref, points, ...)`:
   delta com sinal, tipo `ADJUST`, atômico com `select_for_update`, espelho de
   `earn_points`/`redeem_points`. Permite saldo negativo (cliente pode já ter gasto
   os pontos — o débito honesto registra a dívida; `redeem_points` recusaria com
   `LOYALTY_INSUFFICIENT_POINTS` e o estorno nunca aconteceria). `lifetime_points`
   intocado (contrato do campo: "nunca decresce"; o tier não regride).

   Por que tocar o Core: o tipo `ADJUST` já existe no modelo desde a v1 (o contrib
   `merge` grava `ADJUST` direto), só falta o método de service. Zero migração.
   A alternativa sem Core — reusar `redeem_points` — colide na idempotência com o
   resgate real do mesmo pedido (mesmo `reference` + mesmo type `redeem`) e recusa
   saldo insuficiente. Por isso o transaction_type do estorno é **`adjust`** (choice
   existente), não um "revoke" novo, que exigiria migração no guestman sem ganhar
   semântica.

5. **Adapter `customer`** — dois métodos novos: `adjust_points(...)` (wrapper do
   service) e `get_loyalty_transaction_points(customer_ref, reference,
   transaction_type)` (soma; leitura, mesmo padrão do `has_loyalty_transaction`).

## Fora do escopo (registrado, não implementado)

- **Devolver pontos resgatados** num pedido cancelado (o espelho do
  `loyalty.redeem`): o cliente pagou parte com pontos e o cancelamento devolve o
  dinheiro mas não os pontos. É o mesmo buraco do outro lado, amarrado à semântica
  do refund — resolvido no
  [WP-LOYALTY-RESTORE-01](WP-LOYALTY-RESTORE-01-devolucao-do-resgate.md)
  (Directive `loyalty.restore`, `adjust` positivo com reference própria
  `order:{ref}:restore` para não colidir com a dedupe deste WP).

## Testes

- lifecycle: `on_cancelled`/`on_returned` chamam `loyalty.revoke`.
- service: cria directive com dedupe_key; skip em total zero; segunda chamada com
  directive viva é dedupe-hit.
- flow (`test_loyalty_revoke_flow.py`):
  - cancelamento de venda completed estorna (saldo volta);
  - devolução estorna;
  - cancelamento antes do earn processar: revoke re-agenda (transient), earn atrasado
    não credita (guard), revoke seguinte no-op — saldo zero;
  - dedupe: dois revokes = um estorno;
  - pedido cancelado sem nunca completar = no-op;
  - estorno usa os pontos da transação earn, não a config atual;
  - saldo insuficiente (cliente já gastou) → saldo negativo, sem erro.

## Arquivos

- `packages/guestman/shopman/guestman/contrib/loyalty/service.py` (+`adjust_points`)
- `shopman/shop/adapters/customer.py` (+2 métodos)
- `shopman/shop/directives.py` (+`LOYALTY_REVOKE`)
- `shopman/shop/services/loyalty.py` (+`revoke`)
- `shopman/shop/handlers/loyalty.py` (+`LoyaltyRevokeHandler`, guard no earn)
- `shopman/shop/handlers/__init__.py` (registro)
- `shopman/shop/lifecycle.py` (`_on_cancelled`, `_on_returned`)
- `docs/reference/data-schemas.md` (payload `loyalty.revoke`)
