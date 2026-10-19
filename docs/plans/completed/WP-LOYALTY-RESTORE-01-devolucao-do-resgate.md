# WP-LOYALTY-RESTORE-01 — Devolução dos pontos resgatados no cancelamento e na devolução

## Problema

O cliente paga parte do pedido com pontos: o `LoyaltyRedeemModifier` aplica o
desconto no commit e a Directive `loyalty.redeem` debita
`order.data["loyalty"]["applied_discount_q"]` pontos (transação `redeem`,
`reference="order:{ref}"`). Quando o pedido cancela ou devolve,
`payment.refund(order)` devolve o dinheiro capturado e o
[WP-LOYALTY-REVOKE-01](WP-LOYALTY-REVOKE-01-estorno-no-cancelamento.md) estorna
os pontos GANHOS — mas os pontos RESGATADOS ficam perdidos. É o mesmo buraco do
outro lado, deixado explicitamente fora do escopo do WP anterior.

## Decisão principal: devolver SEMPRE no cancelamento/devolução, não atrelado ao refund do dinheiro

O resgate é desconto já aplicado ao total — o débito de pontos só é justo se a
venda existiu. Cancelou/devolveu, os pontos voltam, independente de o refund do
dinheiro acontecer, falhar ou nem existir (pedido sem captura). A âncora que
torna isso seguro é a fonte da verdade: a devolução credita a **soma das
transações `redeem`** do pedido, nunca o payload nem a config. Se o débito
nunca aconteceu — o guard pulou, ou o redeem morreu terminal com o alerta
`loyalty_redeem_uncovered` (desconto dado sem baixa de pontos) — a soma é zero
e a devolução é no-op: creditar ali seria devolver o que nunca saiu.

## Desenho

1. **Enfileirar** — `services/loyalty.py` ganha `restore(order, reason)`
   (reason ∈ {cancelled, returned}, só para a descrição da transação). Guard:
   `order.data["loyalty"]["applied_discount_q"] <= 0` → return (pedido sem
   resgate nem entra na fila). Criação via `directives.create_deduped` com
   `dedupe_key="loyalty.restore:{order.ref}"`. `_on_cancelled` e `_on_returned`
   chamam, ao lado do `revoke`.

2. **Handler `LoyaltyRestoreHandler`** (topic `loyalty.restore`):
   - resolve `customer_ref` (mesmo helper do earn); sem ref → no-op;
   - **dedupe**: já existe transação `adjust` com
     `reference="order:{ref}:restore"` → skip (dois restores = uma devolução);
   - **pontos** = `-soma` das transações `redeem` com `reference="order:{ref}"`
     (o redeem grava `points` NEGATIVOS — inverter o sinal). Soma ≤ 0:
     - se existe directive `loyalty.redeem` viva (queued/running) para o
       pedido: `DirectiveTransientError` — re-agenda até o redeem assentar;
     - senão: no-op (o débito nunca aconteceu — guard do redeem, ou terminal
       `loyalty_redeem_uncovered`; devolver seria creditar em dobro);
   - credita via `adapter.adjust_points(customer_ref, +points, ...)` — nunca
     `earn_points`, que mexeria em `lifetime_points`/tier por uma devolução.

3. **Guard no redeem** — `LoyaltyRedeemHandler` passa a pular pedidos em
   `cancelled`/`returned` (espelho do guard do earn). É a segunda metade da
   corrida redeem-na-fila: cancelamento chega antes do worker debitar → o
   restore re-agenda (transient) e o redeem atrasado vê o status e não debita
   — o estado final é correto pelos dois caminhos.

## Dedupe: por que a reference do restore é `order:{ref}:restore`

O revoke do WP anterior já grava `adjust` com `reference="order:{ref}"`, e a
sua idempotência é exatamente "existe `adjust` com esta reference → skip". Se
o restore gravasse `adjust` na MESMA reference, cada um veria a transação do
outro como a própria: revoke depois de restore pularia o estorno do earn, e
vice-versa — venda completed com resgate cancelada perderia um dos dois
lançamentos. Reference própria (`order:{ref}:restore`) separa os dois sem
tocar no revoke; a alternativa (mesma reference + filtrar pelo sinal dos
points) exigiria mudar o contrato de `has_loyalty_transaction` e reabrir o
handler estável do WP anterior. A leitura do que devolver continua na
reference original (`order:{ref}`), onde o redeem escreveu.

## Core e adapter: zero mudanças

`LoyaltyService.adjust_points` (delta com sinal) e os métodos de adapter
`adjust_points`/`get_loyalty_transaction_points` já existem desde o
WP-LOYALTY-REVOKE-01. Este WP é só framework: directive + service + handler +
guard + lifecycle.

## Testes

- lifecycle: `on_cancelled`/`on_returned` chamam `loyalty.restore`.
- service: cria directive com dedupe_key; skip sem `applied_discount_q`; duas
  chamadas = uma directive.
- flow (`test_loyalty_restore_flow.py`):
  - cancelamento de venda com resgate devolve os pontos (saldo volta);
  - devolução idem;
  - dedupe: dois restores = uma devolução;
  - cancelamento antes do redeem processar: restore re-agenda (transient),
    redeem atrasado não debita (guard), restore seguinte no-op — sem crédito
    em dobro;
  - pedido sem resgate = no-op;
  - devolução usa a transação `redeem`, não o payload;
  - convivência revoke+restore no mesmo pedido: venda completed com resgate,
    cancelada — earn estornado E resgate devolvido, cada um pela sua
    reference, sem uma dedupe engolir a outra (re-execução dos dois handlers
    não muda o saldo).

## Arquivos

- `shopman/shop/directives.py` (+`LOYALTY_RESTORE`)
- `shopman/shop/services/loyalty.py` (+`restore`)
- `shopman/shop/handlers/loyalty.py` (+`LoyaltyRestoreHandler`, guard no redeem)
- `shopman/shop/handlers/__init__.py` (registro)
- `shopman/shop/lifecycle.py` (`_on_cancelled`, `_on_returned`)
- `docs/reference/data-schemas.md` (payload `loyalty.restore`)
