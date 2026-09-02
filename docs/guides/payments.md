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
| `credit` / `debit` | **nenhum** — maquininha física do balcão | nasce e captura no mesmo gesto (`settle`, `gateway=""`) | `PaymentService.settle` | reembolso manual, fora do sistema |
| `link` | Stripe Checkout via `SHOPMAN_LINK_ADAPTER` (default = o do cartão; simulador em DEBUG) | `create_intent` pending → **captura automática** no gateway (`capture_method="automatic"`, sempre — `STRIPE_CAPTURE_METHOD` vale só para `card`) → webhook confirma | `payment.initiate`, chamado por `close_sale` do PDV (pedido remoto) | adapter → `PaymentService.refund` |

### O balcão não fala com gateway — e o TEF não vai mudar isso

`credit` e `debit` são o **gesto de balcão**: a maquininha é física, o cartão é
passado fora do sistema e o operador atesta o que aconteceu. Eles vivem em
`PaymentIntent.METHODS_WITHOUT_GATEWAY` e **não têm entrada** em
`SHOPMAN_PAYMENT_ADAPTERS` — a ausência é a configuração.

Quando o **TEF da Stone** entrar (WP próprio), o que muda é só a ORIGEM DA PROVA:
a captura deixa de ser atestada pelo operador e passa a vir do terminal, com NSU
e autorização. O `ref` da forma não muda, a tela não muda, o fechamento do dia
não muda. O ponto de entrada é a captura do intent (`PaymentService.settle` com
`gateway_data`) — **não** `payment.initiate`, que é a porta do gateway remoto.

⚠️ Forma de balcão que sai de `METHODS_WITHOUT_GATEWAY` abre um **buraco
silencioso de receita**: o `PaymentService` pula o intent, a venda commita, o
cashman grava a linha e o dinheiro some do Payman, do fechamento e do B.I., sem
erro nem alerta. Guardado por
`test_pos_cash_ledger.py::test_venda_so_em_cartao_do_balcao_liquida_sem_gateway`.

`link` é o oposto: pedido remoto anotado no balcão, sem maquininha e **com**
gateway. No go-live quem o atende é o **Stripe** (WP-PAGAMENTO, frente 1); a
Stone entra depois, junto do TEF. Trocar de provedor é trocar
`SHOPMAN_LINK_ADAPTER` — e só, porque tudo o que é do link pergunta ao adapter,
não ao Stripe:

- a **prontidão** (`payment_link_readiness`, linha `payment_link` do painel de
  integrações) é resolvida pelo adapter configurado; é ela que a tecla L do PDV
  consulta para aparecer. Provedor sem prontidão conhecida fica em aviso e o
  balcão **não oferece** o link — falha fechado, até o provedor novo trazer a
  própria `*_readiness` para cá;
- o **webhook** do Stripe e o `reconcile_payments` (rede contra webhook perdido)
  cobrem toda sessão hospedada — `payment.HOSTED_CHECKOUT_METHODS`, `card` e
  `link` —, não um literal `"card"`;
- o **acompanhamento** do cliente oferece o `checkout_url` de um pedido de link
  como oferece o do cartão (mesmo degrau `payment_card_ready`, `payment_method`
  próprio).

O link **captura sozinho**: `_adapter_config` manda `capture_method="automatic"`
para `link` sempre. A venda do balcão já fechou quando a URL nasce; não há um
aceite posterior da loja que justifique segurar a autorização (que é o que o
`manual` do cartão da loja online compra). Enquanto herdava o `manual` do bloco
`SHOPMAN_STRIPE`, o cliente pagava, o intent ficava `authorized`, a autorização
vencia no Stripe e a padaria nunca recebia.
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
| `method` | str | `pix`, `cash`, `credit`, `debit`, `card`, `link`, `external` |
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

### Validade do link de pagamento

O link (`method="link"`, o pedido remoto anotado no PDV) tem prazo, e o prazo é **um relógio
escrito nos dois lados**: o adapter grava `PaymentIntent.expires_at` e manda o mesmo instante ao
Stripe em `Session.create(expires_at=...)`. Sem mandar, o Stripe expirava a sessão em 24 h por conta
própria e a casa não sabia — dois relógios.

**O prazo segue o ciclo do atendimento**, não uma env:

```
expires_at = min(agora + janela do canal, corte do atendimento)   # preso à régua do Stripe
```

- **janela do canal** — `ChannelConfig.payment.link_timeout_minutes` (default **120**; o canal
  `pdv` semeado declara 120). É o teto: um link de 24 h segurava estoque por um dia inteiro para
  um pão que é para hoje ou para amanhã, e a encomenda remota só é liberada contra o pagamento.
- **corte do atendimento** (`shop/services/payment_deadline.service_cutoff`) — o instante em que
  o pedido precisa estar pago para a casa cumprir: o **início da janela combinada** quando existe
  (`delivery_time_slot`, canônico `"slot-09"` ou meia hora `"14:00-14:30"`); senão o **fechamento
  da loja no dia do compromisso** (`delivery_date` + `Shop.opening_hours`); sem compromisso
  nenhum, o fechamento de hoje. Sem expediente conhecido para o dia, não há corte — vale só a
  janela.
- **régua do Stripe** — piso 30 min, teto 24 h − 1 min (`shop/adapters/_payment_link.py`). Corte
  já passado ou a menos de 30 min (venda de link às 17h50 para retirar às 18h) vale o piso: a casa
  aceita esse caso raro em vez de recusar a venda com o cliente ao telefone.

A janela e o corte chegam ao adapter pelo `_adapter_config` (`link_timeout_minutes` e
`link_expires_by`, ISO), como o Pix faz com `pix_timeout_minutes` — o adapter não conhece pedido
nem calendário. O mock segue o mesmo cálculo.

O que o `expires_at` liga (a máquina já existia; faltava o campo):

1. `payment.initiate()` grava `order.data["payment"]["expires_at"]` — a tela do PDV mostra
   "Pague até hoje às 16h para garantir o pedido", o aviso ao cliente diz a consequência ("Para
   garantir o pedido, é só pagar até hoje às 16h. Depois disso a reserva é liberada.") e o
   acompanhamento da loja repete o prazo (`promise.deadline_at`, `deadline_kind="payment"`) com
   a mesma nota de rodapé;
2. `_schedule_payment_timeout` agenda a Directive `payment.timeout` com `available_at=expires_at`;
3. `PaymentTimeoutHandler` re-agenda se chamado cedo, **pergunta ao gateway** antes de cancelar e só
   cancela com resposta "não pago" — aí libera o estoque e envia `payment_expired`;
4. `reconcile_payments` re-arma o timeout de intent vencido cuja directive se perdeu;
5. a reconciliação diária acusa `expired_payment_link` (warning) para o que escapar.

⚠️ A venda de link **nunca é entrega de balcão**: `lifecycle._counter_handoff` recusa o método `link`
(o pedido remoto tem trajeto pela frente), e o link exige captura antes do trabalho físico mesmo no
canal `pdv` (`payment.timing="external"`). Sem isso a venda fechava COMPLETED sem um centavo
capturado, e o vencimento não a alcançava mais.

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
