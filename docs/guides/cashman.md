# Guia do Caixa (cashman)

## Visão Geral

O caixa físico é um pacote do Core, `shopman.cashman` ([ADR-022](../decisions/adr-022-cashman-ledger.md)),
com três models e uma regra:

1. **`Terminal`** — o aparelho (ref, canal, configuração de hardware em `metadata`). Não guarda dinheiro.
2. **`Shift`** — a custódia: quem (operador) está com qual gaveta (terminal), de quando a quando.
   **Zero coluna de dinheiro**, nem cache. Um turno aberto por operador e um por terminal (constraint).
3. **`Entry`** — o livro do turno, append-only: uma linha por coisa que aconteceu na gaveta, com o
   **efeito no saldo** assinado (`amount_q`; zero quando o evento não mexe em dinheiro).

A regra: **esperado, contado e diferença são provados pelo livro, não guardados em coluna.**
`Σ amount_q` do turno é o que a gaveta devia ter; o fechamento cego é um lançamento `count`
(`contado − esperado`) que faz o livro bater com a gaveta física; a diferença é essa linha.

O pacote não conhece pedido, pagamento nem PDV: `order_ref`/`payment_ref` são strings. Quem sabe o
que é uma venda é o orquestrador (`shopman/shop`), que grava no livro; quem opera o turno é o
backstage, pelos services do pacote. O único fato compartilhado com o Payman é o tender em dinheiro:
captura no Payman (`PaymentService.settle`), linha `sale` no livro, ligados pelo `ref` do intent
(ver [Guia de Pagamentos](payments.md)).

## Modelo de Dados

### Terminal

| Campo | Descrição |
|-------|-----------|
| `ref` | Slug único (`pdv-main` é o default, `Terminal.default()`). |
| `label`, `location_ref`, `channel_ref` | Identificação; o canal é o do PDV (`pdv`). |
| `is_active` | Terminal desligado não abre turno. |
| `metadata` | Configuração do aparelho (gaveta, trava, favoritos). Schema em [data-schemas.md](../reference/data-schemas.md#cashmanterminalmetadata). |

### Shift

| Campo | Descrição |
|-------|-----------|
| `terminal`, `operator` | A custódia: qual gaveta, com quem. |
| `status` | `open` → `closed`. Só. |
| `opened_at`, `closed_at` | Quando. |

Constraints: `cashman_shift_open_operator_uq` e `cashman_shift_open_terminal_uq` (um aberto por
operador, um por terminal). Permissões (no model, content type `cashman.shift`):
`operate_pos`, `audit_shift`, `adjust_shift`, `manage_operators`. `setup_groups` concede
(Caixa opera; Gerente ajusta; Dono audita).

### Entry

| Campo | Descrição |
|-------|-----------|
| `shift`, `operator`, `at` | Em que turno, quem agiu, quando. `operator` pode não ser o dono do turno (fechamento supervisório). |
| `kind` | O tipo (tabela abaixo). **O sinal mora no tipo** e o banco confere (`CheckConstraint cashman_entry_sign_by_kind`). |
| `amount_q` | Efeito no saldo, assinado, em centavos. Zero para evento sem dinheiro. |
| `order_ref`, `payment_ref` | O pedido e o intent do Payman, quando há. Strings: o pacote não importa orderman/payman. |
| `parent` | O lançamento que este responde, resolve ou corrige (mesmo turno). |
| `approved_by` | A segunda assinatura: sangria, destrave, troco atendido, correção. |
| `reason`, `payload` | Motivo curto; o específico de cada tipo (schema em data-schemas.md). |

Imutável por guard (`save` de linha existente, `update()` e `delete()` levantam): correção é
lançamento novo apontando para o que corrige.

| Tipo | Sinal | Quem grava | O que é |
|------|-------|-----------|---------|
| `float_in` | > 0 | `open_shift` | Fundo de troco. |
| `sale` | ≥ 0 | shop (`pos.close_sale`) | **Uma linha por venda**: o efeito em dinheiro (zero para pix/cartão/external e COD); `payload.intents` aponta os intents por método. |
| `cod_settled` | > 0 | shop (`settle_delivery_cash`) | Dinheiro da entrega chegou ao balcão: no turno de quem RECEBEU. |
| `cash_in` / `cash_out` | > 0 / < 0 | backstage (`register_cash_movement`) | Suprimento / sangria. Sangria exige `approved_by` e motivo. |
| `refund` | < 0 | shop (`payment.refund_cash`) | Dinheiro devolvido ao cliente, pela gaveta de quem devolveu. **Cancelar não é devolver**: o cancel deixa pendência; esta linha é o gesto físico, com PIN. |
| `courier_out` / `courier_in` | < 0 / ≥ 0 | shop (`advance_order` no despacho / `settle_delivery_cash`) | Troco que saiu com o entregador e o que voltou (zero fecha o ciclo). Custódia temporária, não pagamento. |
| `account_settled` | > 0 | shop (`house_account.settle_account`) | Cliente acertou a conta EM DINHEIRO: uma linha por intent `account` capturado, no turno de quem recebeu. |
| `count` | ± | `close_shift` | Fechamento cego: `contado − esperado`. Depois dele, `Σ` = o que a gaveta tinha. |
| `count_correction` | ± | `correct_count` (turno fechado, `approved_by`, motivo) | Ajuste gerencial auditado. |
| `drawer_open`, `drawer_unlock` | 0 | backstage | Gaveta aberta sem venda (motivo); trava liberada pelo gerente. |
| `change_requested` → `change_served` / `change_cancelled` | 0 | backstage | Pedido de troco ao balcão e sua resolução (`parent`). Net zero. |
| `receipt_result` | 0 | backstage | O que aconteceu com o comprovante da sangria/suprimento (`parent`). |
| `note` | 0 | backstage / migração | Anotação gerencial (turno fechado); turno legado aberto no corte. |

## Services

```python
from shopman.cashman import services as cash

shift = cash.open_shift(operator=user, terminal=None, float_q=10000)   # Terminal.default() se None
cash.record("sale", shift=shift, operator=user, amount_q=1500, order_ref="A01", payment_ref="pi_1",
            payload={"method": "cash", "received_q": 2000, "change_q": 500, "intents": {"cash": "pi_1"}})
cash.record("cash_out", shift=shift, operator=user, amount_q=-5000, approved_by=manager, reason="Cofre")

cash.balance(shift)                 # Σ amount_q até agora
cash.open_shift_for(user)           # o turno aberto do operador, ou None
cash.open_shift_for_terminal(term)  # idem por terminal
cash.change_requests(shift)         # pedidos de troco dobrados (pending/served/cancelled)
cash.timeline(shift)                # o livro em ordem

count = cash.close_shift(shift, counted_q=6490, actor=user, notes="")   # fechamento cego
cash.expected_before_count(shift)   # Σ antes do count
cash.counted(shift)                 # o que o operador contou
cash.difference(shift)              # o amount_q do count (+ correções)
cash.correct_count(shift, delta_q=10, actor=manager, approved_by=owner, reason="moeda no chão")
cash.is_closed(shift_id)
```

`record` recusa **antes de tocar no banco**, com `CashError(code)`: tipo desconhecido ou reservado
(`float_in`/`count` só nascem em `open_shift`/`close_shift`), sinal errado para o tipo, `parent`
faltando ou de tipo/turno errado, segunda assinatura faltando, turno fechado (só
`count_correction`, `note` e `receipt_result` entram em turno fechado).

## Signals

| Signal | Quando | Payload |
|--------|--------|---------|
| `shift_opened` | turno aberto (on_commit) | `shift` |
| `shift_closed` | turno fechado (on_commit) | `shift`, `count` |
| `entry_recorded` | cada lançamento (on_commit) | `entry` |

O backstage usa `entry_recorded` para o SSE do PDV (pedidos de troco) e o B.I. lê o livro pela
canônica (ADR-021).

## Quem lê o quê

| Pergunta | Fonte | Onde |
|----------|-------|------|
| Leitura X/Z do PDV (sem o esperado: **fechamento cego**) | livro + Payman | `backstage/projections/cash_session.py` |
| Esperado × contado × diferença por turno | livro (`services.difference`) | Admin `cashman.Shift` (readonly, `audit_shift`); B.I. `by_operator` |
| Dinheiro do dia: Payman × livro, por pedido | `PaymentTransaction` × `Entry` | `backstage/services/financial_reconciliation.py` (`cash_ledger_mismatch`, `courier_change_unsettled`) |
| Devoluções em dinheiro pendentes | derivado (pedido cancelado × intent cash capturado) | `shop/services/payment.py::pending_cash_refunds` |
| Troco da entrega (saiu / voltou) | livro por `order_ref` | `shop/services/operator_orders.py::courier_change` → card do gestor |

## Tratamento de Erros

```python
from shopman.cashman.exceptions import CashError

try:
    cash.record("cash_out", shift=shift, operator=user, amount_q=-5000)
except CashError as e:
    e.code       # "APPROVAL_REQUIRED"
    e.message    # "Saída de caixa exige a assinatura de quem autorizou."
    e.as_dict()
```

O backstage traduz `CashError` para `POSError` (dialeto `{detail, field, errors}` da API).

## Histórico

O caixa legado (`backstage.POSTerminal`/`CashShift`/`CashMovement`, ADR-011) entrou no livro uma
vez e sumiu na migração `backstage/0030_cashman_backfill_and_cut` (WP-5 do
[CASHMAN-PLAN](../plans/CASHMAN-PLAN.md)); as linhas nascidas dali levam `payload.legacy`.
Diagnóstico e desenho: [CASH-LEDGER-ARCHITECTURE.md](../plans/CASH-LEDGER-ARCHITECTURE.md).
