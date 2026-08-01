# PAYMENT-TRACKING-MERGE-PLAN — o pagamento volta para o acompanhamento

**Status:** proposto, aguardando OK do Pablo (2026-08-01).
**Tese do Pablo:** *"pagamento é algo que deveria ser consultado/gerido pelo
acompanhamento, que é justamente onde o cliente de fato está."* Concordo, e o
levantamento abaixo mostra que a separação atual não paga o próprio custo.

## 1. Por que fundir

### A pergunta "o cliente deve dinheiro agora?" tem TRÊS donos

| onde | função | para quê |
|---|---|---|
| roteamento | `customer_orders.requires_payment_gate` | empurra o cliente para `/pagamento` e suprime o yoin |
| copy do acompanhamento | `order_tracking._build_promise` (ramo `payment_pending`) | escreve "Pagar agora" e some com o resto |
| copy do pagamento | `payment_status._build_payment_promise` | escreve a tela inteira do Pix/cartão |

Três respostas independentes para o mesmo fato. Nenhum teste obriga as três a
concordarem. **Foi exatamente isso que produziu o bug de 2026-08-01** (a tela de
pagamento dizia "Estamos conferindo a disponibilidade" com a padaria fechada,
enquanto o acompanhamento já sabia dizer "conferimos quando abrirmos, às 9h").
Aquele conserto uniu **uma** das perguntas (`store_review_deferred_state`). As
outras continuam soltas.

### As duas máquinas de estado já se sobrepõem

30 definições de estado no total — 13 na tela de pagamento, 17 no
acompanhamento — e a sobreposição é literal:

| fato | nome no pagamento | nome no acompanhamento |
|---|---|---|
| pago | `paid` | `payment_confirmed` |
| prazo do Pix venceu | `expired` | `payment_expired` |
| cancelado | `cancelled` | `cancelled` |
| cartão autorizado, capturando | `card_authorized` | `card_authorized` |
| loja fechada, olha na abertura | `pix_waiting_opening` | `availability_deferred` |
| loja conferindo disponibilidade | `pix_waiting_confirmation` | `availability_check` |

Seis fatos, doze nomes. Cada par é uma chance de divergir.

### O acompanhamento já sabe de tudo e mesmo assim expulsa o cliente

`order_tracking.py:672` desenha um botão "Pagar agora" que manda o cliente para
a outra tela. Ou seja: a tela onde o cliente está já detectou que há pagamento
pendente, já tem painel de promessa, contador, banner de offline e ações — e
ainda assim delega para uma segunda tela que refaz o raciocínio do zero.

### O argumento a favor de duas telas não sobrevive

"Momento focado de pagamento" seria a justificativa. Mas:

- **Cartão:** o momento focado é a página do Stripe, que é externa. Nossa tela é
  uma sala de espera com um link.
- **Pix:** QR + copia-e-cola + contador é um **bloco**, não uma página.

Pagamento é um **estado do pedido**, não um lugar.

## 2. O desenho

### Uma pergunta

A promessa do pedido responde **"de quem é a bola agora, e o que ela precisa?"**
Todo estado se encaixa em uma das cinco posses. Isso é a espinha; o resto é
consequência.

### Uma cascata, com ordem justificada

Primeiro match vence. A ordem não é gosto — cada degrau é mais urgente que o
seguinte, e é isso que impede pagamento e entrega de brigarem:

```
1. TERMINAL          o pedido acabou; nada mais importa
2. PRAZO ESTOURADO   o Pix venceu; nem cobrar nem preparar faz sentido
3. BOLA DO CLIENTE   ele precisa agir AGORA (pagar, autorizar, tentar de novo)
4. BOLA DO GATEWAY   esperando confirmação de fora (cartão capturando)
5. BOLA DA LOJA      o cliente só espera (conferir, preparar, expedir)
6. REPOUSO           recebido (fallback)
```

### Os estados (30 → 19)

| # | posse | estado | vem de |
|---|---|---|---|
| 1 | terminal | `cancelled` | `cancelled` ×2 |
| 2 | terminal | `returned` | `returned` |
| 3 | terminal | `delivered` | `delivered` |
| 4 | terminal | `completed` | `completed` |
| 5 | prazo | `payment_expired` | `payment_expired` + `expired` |
| 6 | cliente | `payment_pix_ready` | `pix_payment_requested` + `pix_payment_before_confirmation` |
| 7 | cliente | `payment_card_ready` | `card_checkout_requested` + `card_authorization_requested` |
| 8 | cliente | `payment_retry` | `intent_error` + `card_checkout_pending` |
| 9 | gateway | `payment_authorized` | `card_authorized` ×2 |
| 10 | loja | `payment_confirmed` | `payment_confirmed` + `paid` |
| 11 | loja | `store_closed` | `availability_deferred` + `pix_waiting_opening` |
| 12 | loja | `store_checking` | `availability_check` + `pix_waiting_confirmation` |
| 13 | loja | `payment_preparing` | `pix_waiting_code` |
| 14 | loja | `preorder_scheduled` | idem |
| 15 | loja | `preparing` | idem |
| 16 | loja | `ready_pickup` | idem |
| 17 | loja | `ready_delivery` | idem |
| 18 | loja | `dispatched` | idem |
| 19 | repouso | `received` | idem |

**Some de vez:** `no_online_payment` (existia só porque dava para chegar na tela
de pagamento errada — sem tela, sem estado) e `payment_pending`/`payment_requested`
do acompanhamento, que eram a versão grossa e cega do que os estados 6-8 dizem
direito.

**Por que `payment_authorized` e não `card_authorized`** (decisão do Pablo,
2026-08-01): o nome antigo amarra o estado a um meio de pagamento sem
necessidade — se entrar carteira digital ou qualquer método com reserva antes
da captura, o fato é o mesmo. E é `authorized`, não `authorizing`: a
autorização já aconteceu; o que está pendente é a **captura**. Nomear o fato
consumado, não o processo.

**Pares que viram um estado + nota de rodapé, não dois estados:**
`pix_payment_requested` vs `pix_payment_before_confirmation` diferiam só em "a
loja já aceitou". Isso é uma frase de rodapé ("Ainda estamos conferindo a
disponibilidade"), não um estado — o cliente faz a mesma coisa nos dois:
copia o código e paga.

### O invariante que torna isso seguro

O medo legítimo é pagamento e entrega se atropelarem. Não podem, e dá para
**provar**:

> `payment_is_due(order)` ⇒ `order.status ∈ {new, accepted}`

Porque o avanço do operador já é barrado por
`operator_orders.advance_block() == PAYMENT_NOT_CAPTURED` enquanto o dinheiro
não entra (verificado hoje, no card do gestor), e o Pix vencido cancela o
pedido em vez de deixá-lo andar. Logo os degraus 3-4 (bola do cliente/gateway)
**nunca** competem com os degraus de preparo/expedição: são mutuamente
exclusivos por construção.

Isso vira **teste de invariante** (`shopman/shop/tests/test_invariants.py`),
não comentário. Se alguém um dia permitir avançar sem pagar, o teste cai antes
da tela mentir.

### A pergunta ganha um dono

`customer_orders.requires_payment_gate` deixa de existir como decisão de
roteamento (não há mais para onde rotear) e vira **`payment_is_due(order)`** —
um predicado, um dono, consumido por:

- a cascata da promessa (degraus 6-8),
- `channel_policy` (o action ref `pay`),
- `conversation.py` (o link que o WhatsApp manda — agora o do acompanhamento).

Três consumidores, uma verdade. É a mesma correção estrutural do
`store_review_deferred_state`, aplicada à pergunta maior.

## 3. O que morre

Zero legado, zero redirect de cortesia — a rota some.

| some | onde |
|---|---|
| rota `/pedido/{ref}/pagamento` | `surfaces/storefront-nuxt/app/pages/pedido/[ref]/pagamento.vue` (445 linhas) |
| `storefront_links.path_order_payment` / `order_payment_url` | `shopman/shop/services/storefront_links.py` |
| `customer_orders.requires_payment_gate` | vira `payment_is_due` |
| `_payment_gate_url`, `requires_payment_gate`, `payment_gate_url` na API | `shopman/storefront/api/tracking.py`, `serializers.py` |
| `PaymentData.promise` / `PaymentPromiseData` como máquina própria | `shopman/shop/projections/payment_status.py` |
| `present_payment` como tela | `shopman/storefront/presentation/payment.py` |
| ~15 chaves de copy `PAYMENT_PROMISE_*` duplicadas | `shopman/shop/omotenashi/copy.py` |
| bug latente: `/pedido/{ref}/pagamento/` **com** barra final | `shopman/shop/services/conversation.py:117` (diverge de todos os outros; morre junto) |

**Fica** (só muda de casa): o bloco de Pix (QR, copia-e-cola, contador,
expirado), o bloco de cartão (botão do Stripe), a caixa de "simular pagamento"
em DEBUG, e os endpoints `POST /api/v1/payment/{ref}/mock-confirm/` e o
webhook. O `GET /api/v1/payment/{ref}/` e `/status/` somem: o acompanhamento já
tem `GET /api/v1/tracking/{ref}/` e o SSE `order-<ref>`, que passam a carregar
o bloco de pagamento.

## 4. Ordem de execução

Cada arco fecha verde por conta própria.

**Arco A — o predicado.** `payment_is_due` nasce em `customer_orders`, com
teste. Os três consumidores atuais passam a chamá-lo. Nada muda na tela ainda.

**Arco B — a cascata unificada.** Os 19 estados nascem em
`order_tracking._build_promise`, absorvendo os ramos de `payment_status`. A
`TrackingPromiseData` ganha o bloco de pagamento (`pix_qr_code`,
`pix_copy_paste`, `pix_expires_at`, `checkout_url`) como dados. Teste de
invariante + tabela de estados (um teste por estado, com o mundo que o produz).

**Arco C — a copy.** As chaves `PAYMENT_PROMISE_*` sobreviventes viram
`TRACKING_PROMISE_*`; as duplicadas morrem. `omotenashi_usage_map` regenerado —
o guardrail de chave órfã é quem confere o serviço.

**Arco D — a superfície.** `pagamento.vue` some; seus blocos viram
`components/order/PaymentBlock.vue`, renderizado dentro do painel do
acompanhamento quando a promessa é dos degraus 5-8. Uma página, um poll, um SSE.

**Arco E — os links.** Os 15 pontos que apontavam para `/pagamento` passam a
apontar para `/pedido/{ref}`. Inclui Stripe (`success_url`/`cancel_url`),
notificações (`payment_url` no contexto), magic link (`auth.py`), checkout
(`views.py`), conversação e o QA do backstage.

**Arco F — seed e dados.** Os 2 templates de notificação (`payment_requested`,
`payment_failed`) no `seed.py`. Banco zerado + `make seed` — sem migração de
dados, conforme a etapa do projeto.

**Arco G — a prova.** `make test` (~5.000) + `make admin` + `make lint` +
vitest do storefront. E o teste que amarra o que sobrou: um pedido, um estado,
**uma** frase.

## 5. O que você precisa reconfigurar

**Stripe: nada.** Verifiquei — `success_url` e `cancel_url` são enviados por
sessão, pelo nosso código (`adapters/payment_stripe.py:112-128`), não ficam no
painel. O endpoint de webhook não muda.

**Nada mais é externo.** Os outros links (WhatsApp, magic link) são gerados por
nós a cada envio.

## 6. Riscos, e o que cobre cada um

| risco | cobertura |
|---|---|
| a cascata unificada errar a ordem e mostrar "pague" num pedido já em preparo | o invariante `payment_is_due ⇒ status ∈ {new, accepted}`, como teste |
| perder um estado no caminho | tabela de 19 testes, um por estado, cada um construindo o mundo que o produz |
| link antigo em WhatsApp já enviado | pré-go-live: não há mensagem antiga em campo |
| a página do acompanhamento inchar | os blocos de pagamento entram como componente, não como `v-if` no meio da página; a página cresce ~120 linhas e a outra (445) some |
| SSE não acordar o bloco de Pix | o canal `order-<ref>` já é o mesmo; hoje a tela de pagamento tem stream próprio — passa a ter um só |

## 7. Custo honesto

Arcos A-C são backend puro e é onde mora o cuidado (a cascata). D-E são
mecânicos e amplos (15 pontos + uma página). F-G são ritual.

Estimativa: **1 sessão de trabalho concentrado**, com `make test` verde entre
cada arco. O saldo é −445 linhas de página, −11 estados, −2 respostas
independentes para a mesma pergunta, e uma classe inteira de bug (duas telas
discordando) que deixa de ser possível por construção.
