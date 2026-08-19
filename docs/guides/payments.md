# Guia de Pagamentos

## Visão Geral

O sistema de pagamentos é composto por duas camadas:

1. **Payman Core** (`shopman.payman`) — Service layer agnóstico que gerencia o lifecycle de `PaymentIntent` e `PaymentTransaction` no banco
2. **Payment Handlers** (`shopman/handlers/payment.py`) — Handlers que conectam o lifecycle do pedido aos backends de gateway

O core não sabe nada sobre gateways (Efi, Stripe, etc.). Os backends implementam o `PaymentBackend` protocol e são configurados no orquestrador.

O Payman é o livro de pagamentos de **todos** os métodos, com ou sem gateway
([ADR-022](../decisions/adr-022-cashman-ledger.md)): dinheiro e cobrança externa
não passam por adapter, mas passam pelo Payman. É isso que dá ao mix de meios de
pagamento um dono só e deixa a reconciliação financeira enxergar dinheiro.

### Métodos

| Método | Gateway | Como o intent nasce | Quem cria | Estorno |
|--------|---------|---------------------|-----------|---------|
| `pix` | Efí (ou mock) | `create_intent` pending → webhook autoriza/captura | `payment.initiate` (loja online, WhatsApp, PDV) | adapter → `PaymentService.refund` |
| `card` | Stripe Checkout (ou mock) | `create_intent` pending → webhook captura | `payment.initiate` | adapter → `PaymentService.refund` |
| `cash` | nenhum (`gateway=""`) | **capturado no ato** via `PaymentService.settle`, quando a coleta é no terminal (`Order.data.payment.collection == "terminal"`, PDV) e depois do total selado | `payment.initiate`, chamado por `close_sale` do PDV | `PaymentService.refund` direto (sem adapter), no cancel/devolução |
| `external` | nenhum (`gateway=""`) | idem `cash` (maquininha avulsa recebida no terminal) | idem | idem |
| `account` | nenhum (`gateway=""`) | **autorizado** na venda (= deve; `PaymentService.charge_to_account`, `gateway_data.customer_ref`) e **capturado** no acerto (= pagou; `capture(gateway_data={settled_with, settled_by})`), FIFO por venda inteira | PDV, só para cliente com `Customer.metadata.house_account` (`shop/services/house_account`) | cancel da venda → `PaymentService.cancel` (a dívida morre; nada a estornar). Saldo devedor = `account_balance_q` (Σ autorizados; derivado, nunca tabela) |

Dinheiro **fora do terminal** não tem intent até o acerto: pedido da loja online
em dinheiro (retirada ou entrega) e COD do PDV (`collection == "on_delivery"`)
ficam sem `intent_ref`; o intent nasce quando o dinheiro troca de mãos (WP-3 do
[CASHMAN-PLAN](../plans/CASHMAN-PLAN.md)). Marketplace (`external` sem coleta no
terminal) também segue sem intent aqui.

O caixa físico (turno, gaveta, sangria, troco) não é pergunta do Payman: é do
pacote `cashman`. O único fato compartilhado é o tender em dinheiro: captura no
Payman, lançamento `sale` no livro-caixa, ligados pelo `ref` do intent.

## Modelo de Dados

### PaymentIntent

Representa uma intenção de pagamento vinculada a um pedido.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | str | Identificador único (auto: `PAY-XXXXXXXXXXXX`) |
| `order_ref` | str | Referência do pedido (string, sem FK) |
| `method` | str | `pix`, `card`, `cash`, `external` |
| `status` | str | Estado atual do pagamento |
| `amount_q` | int | Valor em centavos |
| `currency` | str | ISO 4217 (default: `BRL`) |
| `gateway` | str | Nome do gateway (`efi`, `stripe`, etc.); vazio para `cash`/`external` liquidados via `settle` |
| `gateway_id` | str | ID da transação no gateway externo (vazio sem gateway) |
| `gateway_data` | JSON | Dados extras do gateway (QR code, chave PIX, etc.) |
| `expires_at` | datetime | Expiração do intent |

### PaymentTransaction

Registro imutável de cada operação financeira sobre um intent.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `intent` | FK | PaymentIntent associado |
| `type` | str | `CAPTURE` ou `REFUND` |
| `amount_q` | int | Valor da transação em centavos |
| `gateway_id` | str | ID da transação no gateway |

## Lifecycle

```
PENDING → AUTHORIZED → CAPTURED → REFUNDED
   │          │
   ├→ FAILED  ├→ FAILED
   │          │
   └→ CANCELLED └→ CANCELLED
```

**Estados terminais:** `CAPTURED`, `REFUNDED`, `FAILED`, `CANCELLED`.

`settle` (métodos sem gateway) percorre a mesma máquina, `PENDING → AUTHORIZED →
CAPTURED`, numa única transação: autorização e captura são o mesmo gesto porque
a nota já está na gaveta. Só o signal `payment_captured` é emitido.

## PaymentService API

Todas as operações state-changing usam `@transaction.atomic` + `select_for_update()`. Cada transição emite o signal correspondente.

```python
from shopman.payman import PaymentService, PaymentError

# Criar intent
intent = PaymentService.create_intent("ORD-001", 1500, "pix")

# Sem gateway (dinheiro no balcão, cobrança externa): nasce capturado.
# `amount_q` é o valor do tender (o que ficou na gaveta depois do troco).
intent = PaymentService.settle("ORD-002", 1500, "cash", idempotency_key="order-payment:ORD-002:cash:1500:g0")

# Autorizar (gateway confirmou fundos)
PaymentService.authorize(intent.ref, gateway_id="efi_txid_123")

# Capturar
tx = PaymentService.capture(intent.ref)

# Reembolsar (parcial ou total)
PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")

# Cancelar (antes da captura)
PaymentService.cancel(intent.ref)

# Queries
intent = PaymentService.get(ref)
intents = PaymentService.get_by_order("ORD-001")
active = PaymentService.get_active_intent("ORD-001")
intent = PaymentService.get_by_gateway_id("efi_txid_123")

# Aggregates
total_captured = PaymentService.captured_total(ref)
total_refunded = PaymentService.refunded_total(ref)
```

## Fluxo PIX Completo

O fluxo PIX é o mais complexo. Envolve handlers, webhooks e timeouts:

```
1. Pedido confirmado (status → CONFIRMED)
   │
2. on_order_lifecycle() → pipeline.on_confirmed inclui PIX_GENERATE
   │
3. PixGenerateHandler executa:
   ├── PaymentBackend.create_intent() → GatewayIntent (QR code, copiar-colar)
   ├── PaymentService.create_intent() → persiste no DB
   ├── Salva dados PIX no Order.data (qr_code, copy_paste, expires_at)
   ├── Cria directive: notification.send (lembrete de pagamento)
   └── Cria directive: pix.timeout (timer de expiração)
   │
4. Cliente paga via PIX
   │
5. Gateway envia webhook → EfiPixWebhookView
   ├── PaymentService.authorize(ref)  → PENDING → AUTHORIZED
   ├── PaymentService.capture(ref)    → AUTHORIZED → CAPTURED
   └── on_payment_confirmed(order) hook:
       ├── Cria directive: stock.commit
       └── Cria directive: notification.send (pagamento confirmado)
   │
6. [Timeout] Se não pago a tempo:
   └── PixTimeoutHandler executa:
       ├── PaymentService.cancel(ref) → PENDING → CANCELLED
       ├── Order → CANCELLED
       └── Cria directive: stock.release + notification.send
```

### Configuração PIX

Via `ChannelConfig.payment`:

```python
ChannelConfig.Payment(
    method="pix",
    timeout_minutes=15,    # Tempo para pagar antes de cancelar
)
```

O timeout total de hold de estoque deve cobrir: confirmação + pagamento + margem. Veja `confirmation.calculate_hold_ttl()`.

## Backends Disponíveis

### MockPaymentBackend

Para testes e desenvolvimento. Simula fluxo completo com PIX mockado.

```python
SHOPMAN_PAYMENT_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_mock",
}
```

### Efí PIX

Integração com Efí para PIX real via Payman. Em staging/homologação, mantenha
`EFI_SANDBOX=true` e use certificado/credenciais de homologação.

```python
SHOPMAN_PAYMENT_ADAPTERS["pix"] = "shopman.shop.adapters.payment_efi"
SHOPMAN_EFI = {
    "sandbox": True,
    "client_id": "...",
    "client_secret": "...",
    "certificate_path": "/path/to/efi.pem",
    "pix_key": "...",
}
SHOPMAN_EFI_WEBHOOK = {"webhook_token": "..."}
```

### Stripe Checkout

Integração com Stripe Checkout para cartão. Staging/test deve usar chaves
`sk_test_` / `pk_test_`; chaves live são bloqueadas pelo smoke de sandbox.

```python
SHOPMAN_PAYMENT_ADAPTERS["card"] = "shopman.shop.adapters.payment_stripe"
SHOPMAN_STRIPE = {
    "publishable_key": "pk_test_...",
    "secret_key": "sk_test_...",
    "webhook_secret": "whsec_...",
    "capture_method": "manual",
    "domain": "https://staging.example.com",
}
```

## Signals

Todos emitidos por `PaymentService` após cada transição:

| Signal | Quando | Payload |
|--------|--------|---------|
| `payment_authorized` | PENDING → AUTHORIZED | `intent`, `order_ref`, `amount_q`, `method` |
| `payment_captured` | AUTHORIZED → CAPTURED | `intent`, `order_ref`, `amount_q`, `transaction` |
| `payment_refunded` | Refund registrado | `intent`, `order_ref`, `amount_q`, `transaction` |
| `payment_cancelled` | PENDING/AUTHORIZED → CANCELLED | `intent`, `order_ref` |
| `payment_failed` | Qualquer → FAILED | `intent`, `order_ref`, `error_code`, `message` |

## Handlers do Orquestrador

| Handler | Topic | Descrição |
|---------|-------|-----------|
| `PaymentCaptureHandler` | `payment.capture` | Captura pagamento autorizado |
| `PaymentRefundHandler` | `payment.refund` | Processa reembolso via backend |
| `PixGenerateHandler` | `pix.generate` | Cria PIX charge com QR code e timeout |
| `PixTimeoutHandler` | `pix.timeout` | Cancela pedido se PIX não pago a tempo |

## Tratamento de Erros

```python
from shopman.payman.exceptions import PaymentError

try:
    PaymentService.capture(ref)
except PaymentError as e:
    print(e.code)     # "invalid_transition"
    print(e.message)  # "Não é possível capture: status atual é pending..."
    print(e.as_dict())
```

Códigos de erro: veja [errors.md](../reference/errors.md#paymenterror-payman).

## Smoke Operacional

Antes de release ou mudança em webhook/gateway:

```bash
make smoke-gateways
make smoke-gateways-sandbox
```

O primeiro comando usa fixtures locais com rollback e valida o contrato interno.
O segundo exige credenciais/staging reais para Focus NFe homologação, Efí
sandbox e Stripe test; sem elas, retorna `blocked_by_credentials` para evitar
falsa aprovação de sandbox. Também bloqueia configuração de produção em staging.
