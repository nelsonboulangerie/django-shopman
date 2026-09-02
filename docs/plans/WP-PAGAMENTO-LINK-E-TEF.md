# WP-PAGAMENTO — Link de pagamento (provedor, entrega, prazo) e TEF no balcão

> Estado: **frentes 1, 2 e 3 executadas (02/09/2026)**, empilhadas sobre o PR #484
> (a branch `claude/checkout-pdv-refinements-491373`, que pôs o link de pé). A frente 4
> segue pós-go-live. As sete perguntas do fim foram respondidas com as recomendações do
> próprio plano, e o Pablo reviu duas na mesma noite: **o prazo do link segue o ciclo
> do atendimento, não 24 h** ("normalmente o pão é para hoje ou para o dia seguinte, e
> só liberamos a encomenda remota contra o pagamento; isso precisa ser transparente e
> elegante para o cliente") e **o reenvio manual entra** ("pode ser muito importante").
> As duas viraram frentes próprias (3b e 5), abaixo.
>
> | # | Pergunta | Assumido |
> |---|---|---|
> | 1 | Provedor do link | **Stripe** (a Stone entra com o TEF, frente 4) |
> | 2 | Captura do link | **`automatic`**, sempre — não é env, é a natureza da forma |
> | 3 | Validade | **`min(agora + janela do canal, corte do atendimento)`** — janela `ChannelConfig.payment.link_timeout_minutes` (PDV: 120), corte = início do slot de retirada/entrega ou o fechamento da loja no dia do compromisso; régua do Stripe por cima (30 min – 24 h). UM relógio, escrito no intent e no Stripe |
> | 4 | Link vencido | **cancela sozinho** pela máquina existente + check `expired_payment_link` na reconciliação |
> | 5 | Reenvio manual | **entra** (frente 5): `notification.resend`, botão no PDV e no gestor de pedidos; a mesma URL enquanto vale — link vencido é pedido cancelado, o caminho é refazer a venda |
> | 6 | Balcão COMPLETED com link pendente | **não** — `_counter_handoff` recusa venda de link |
> | 7 | Cadeia do canal PDV | **WhatsApp → e-mail → SMS** |

## O que já está no ar (não replanejar)

- **Crédito e débito** são formas próprias do balcão e liquidam SEM gateway
  (`packages/payman/shopman/payman/models/intent.py:108-115`). A maquininha é física,
  o operador atesta. `card` saiu da oferta do PDV
  (`shopman/backstage/projections/pos.py:431`) e segue válido na loja online e no histórico.
- **Link de pagamento** (`link`, tecla L): forma do PEDIDO REMOTO, passa por gateway
  (`shopman/shop/services/payment.py:68` `initiate`), nasce `pending`, webhook captura.
  Adapter em `SHOPMAN_PAYMENT_ADAPTERS["link"]` (`config/settings.py:1020-1026`).
- **Três guardas**: `_link_payment_available` (`shopman/backstage/projections/pos.py:435-458`),
  `link_requires_full_payment` (`shopman/shop/services/pos.py:2546-2553`),
  `link_requires_customer_contact` (`shopman/shop/services/pos.py:891-913`).

---

## Frente 1 · Qual provedor atende o link: Stone ou Stripe

**O problema em uma frase.** O link nasceu apontando para o adapter do cartão sem que
ninguém tenha decidido de quem é a cobrança remota da casa, e a suposição de que trocar
é trocar uma env está **errada em um ponto**.

### O que existe hoje

| Fato | Onde |
|---|---|
| `link` resolve o adapter por env, com fallback no adapter do cartão | `config/settings.py:1020-1026` |
| `initiate` resolve o adapter por método e chama o contrato genérico | `shopman/shop/services/payment.py:108-136` |
| Contrato do adapter: `create_intent` → `PaymentIntent` (dataclass), com `metadata["checkout_url"]` | `shopman/shop/adapters/payment_types.py`; `payment_stripe.py:120-219` |
| Verbos que o orquestrador consome do adapter | `create_intent`, `capture`, `refund`, `cancel`, `check_gateway_status`, `get_status`, `gateway_payment_intent_id`, `construct_webhook_event`, `webhook_event_key`, `handle_webhook_event`, `handle_webhook` (`payment_stripe.py:120/234/302/381/414/448/530/561/569/896/1002`) |
| O adapter do Stripe já grava o método CERTO no Payman (`link` não vira `card`) | `payment_stripe.py:150-165` |
| Stripe já roda para o cartão da loja, verificado ao vivo em staging | `docs/plans/GO-LIVE-SMS-WHATSAPP-STATUS.md` |
| Prontidão do Stripe: adapter + `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` + `domain` com esquema + prefixo test/live coerente | `shopman/backstage/services/integration_readiness.py:267-312` |
| Webhook publicado | `shopman/shop/webhooks/urls.py:15` → `/webhooks/stripe/` |
| Domínio de retorno vem de `storefront_links`, com `SHOPMAN_DOMAIN` como reserva | `payment_stripe.py:46-63` |

**O que a Stone exigiria e ainda não existe:** não há uma linha de Stone no repositório
(`grep -rni "stone\|autotef"` em `shopman/`, `packages/`, `config/` → zero). Ir de Stone
significa **escrever um adapter novo inteiro** (11 verbos), publicar um webhook novo, uma
`stone_link_readiness()` em `integration_readiness.py`, credenciais e homologação com a
adquirente.

**Taxas:** não há NADA documentado no repositório sobre MDR de nenhum provedor — a
`GO-LIVE-CREDENTIALS-MATRIX.md` só fala de chaves. Comparação comercial é do Pablo, fora
do código.

### ⚠️ Trocar NÃO é só trocar uma env — três amarras no Stripe

Levantei isto lendo o código, e é a parte que muda a decisão:

1. **`_link_payment_available()` chama `stripe_card_readiness()` cravado**
   (`shopman/backstage/projections/pos.py:449,458`). Com `SHOPMAN_LINK_ADAPTER` apontando
   para outro provedor, a tecla L do PDV continuaria perguntando ao Stripe se pode aparecer —
   e sumiria do balcão exatamente quando o Stripe do cartão não estivesse configurado.
2. **`stripe_card_readiness` só olha `SHOPMAN_CARD_ADAPTER`**
   (`integration_readiness.py:277`). O `link` não tem linha própria na tela de prontidão.
3. **`_adapter_config` manda `capture_method` do bloco `SHOPMAN_STRIPE` para o link**
   (`shopman/shop/services/payment.py:1665-1668`) — vocabulário do Stripe vazando para
   uma forma que pode não ser dele.

Nada disso é grande, mas é código, não env. **A frase honesta é: "trocar de provedor é
trocar uma env MAIS generalizar a prontidão".**

### 🩸 E três defeitos do link que achei no caminho (não são hipóteses)

Estes valem dinheiro e entram nesta frente porque são do gateway:

1. **O link pago nunca é capturado.** `capture_method` nasce `"manual"`
   (`config/settings.py:1184`) e é aplicado ao link (`payment.py:1665-1668`). O webhook do
   Stripe só captura quando `method == "card"`
   (`shopman/shop/webhooks/stripe.py:165-170`). Resultado: cliente paga, o intent fica
   `authorized`, a autorização vence em ~7 dias no Stripe e **a padaria não recebe**.
2. **A rede contra webhook perdido não cobre o link.**
   `reconcile_payments` filtra `data__payment__method="card"` cravado
   (`shopman/shop/management/commands/reconcile_payments.py:250-253`), embora
   `reconcile_with_gateway_if_due` já aceite link (`payment.py:1261`).
3. **O acompanhamento do cliente não oferece pagar um pedido de link.**
   `shopman/shop/projections/order_tracking.py:395,401,~920` testam `{"pix","card"}`
   cravado. Quem abandona o checkout e volta pelo link do pedido não encontra botão nenhum.

### Decisão que precisa da palavra do Pablo

**Stripe ou Stone para o link, no go-live.**

| Opção | A favor | Contra |
|---|---|---|
| **A — Stripe** | Já de pé e verificado ao vivo; readiness, webhook, estorno, disputa e reconciliação já escritos e testados; custo de código ≈ zero | Mais um provedor no extrato (Efí Pix + Stripe cartão + Stone maquininha); reconciliação em três lugares |
| **B — Stone** | Um provedor só para cartão presencial (TEF) e remoto (link): um extrato, uma conciliação, uma negociação de taxa | Adapter novo inteiro + webhook + readiness + homologação. Semanas, não dias, e às vésperas do go-live |

**Recomendação: A (Stripe), agora.** Não é preferência técnica por Stripe — é que o link
já funciona nele e o go-live não tem folga para uma integração nova. A Stone entra depois,
junto com o TEF (frente 4), quando a conta de "um provedor só" fecha de verdade: aí o
adapter novo é um WP com tempo, e o gesto de virar continua sendo `SHOPMAN_LINK_ADAPTER`
— desde que a generalização abaixo esteja feita.

### Arquivos tocados

- `shopman/backstage/projections/pos.py` — `_link_payment_available` passa a resolver a
  prontidão PELO adapter configurado, não pelo Stripe cravado.
- `shopman/backstage/services/integration_readiness.py` — `payment_link_readiness()`
  própria, entrando em `build_provider_readiness`.
- `shopman/shop/webhooks/stripe.py` — capturar também `link` (ou ver a opção do
  `capture_method` abaixo).
- `shopman/shop/management/commands/reconcile_payments.py` — `method__in=["card","link"]`.
- `shopman/shop/projections/order_tracking.py` — `link` na cascata de promessa.
- `config/settings.py` — `SHOPMAN_LINK_CAPTURE_METHOD` (ou o link forçando `automatic`).
- `docs/guides/payments.md` — a tabela de métodos ganha a linha `link`.
- `.env.example` — `SHOPMAN_LINK_ADAPTER`.
- Testes: `shopman/shop/tests/` (webhook do link, reconcile, readiness).

**Tamanho: M** — ~1,5 dia. (A opção B seria **G**: 2–3 semanas + homologação.)

---

## Frente 2 · Enviar o link automaticamente

**O problema em uma frase.** O operador copia a URL e manda à mão, e quem manda à mão
esquece — sobretudo no horário de pico, que é exatamente quando o pedido remoto entra.

> **Correção de premissa (02/09/2026).** Os três canais estão de pé: **Comtele/SMS OK**,
> **WhatsApp funcionando** (falta só criar o template no painel do ManyChat) e **SMTP
> confirmado**. Não há contorno de credencial a planejar; isto é trabalho normal de
> implementação.

### O que existe hoje

| Fato | Onde |
|---|---|
| `notification.send(order, template)` cria uma Directive deduplicada por `(pedido, template)` | `shopman/shop/services/notification.py:56-115` |
| O handler entrega pela cadeia, retenta até 5 vezes e escala para `OperatorAlert` | `shopman/shop/handlers/notification.py:41-108` |
| A cadeia sai do `ChannelConfig.notifications` (backend + fallback) | `shopman/shop/services/notification.py:201-208`; `shopman/shop/config.py:176-181` |
| Destinatário por backend: manychat → `handle_ref`/telefone, email → e-mail, resto → telefone | `shopman/shop/services/notification.py:422-448` |
| O PDV grava `customer.phone` e `customer.email` no pedido | `shopman/shop/services/pos.py:1678-1688` |
| Todos os canais leem o MESMO `NotificationTemplate` do Admin; chave ausente sai literal | `shopman/shop/adapters/_notification_templates.py` |
| O ponto exato onde a URL nasce no PDV | `shopman/shop/services/pos.py:2727-2752` |

### ⚠️ O achado que trava tudo: hoje o pedido de PDV avisa o CONSOLE

O canal `pdv` não declara `notifications` (`config/management/commands/seed.py:4948-4990`),
então herda o nível loja: `Shop.defaults["notifications"] = {"backend": "console"}`
(`seed.py:768`). Com o `fallback_chain` default, a cadeia do PDV é
`["console", "sms", "email"]` — e `notification_console.send` **sempre devolve `True`**
(`shopman/shop/adapters/notification_console.py:44`), curto-circuitando a cadeia inteira.

**O WhatsApp (manychat) não está na cadeia do PDV.** Sem mexer nisto, o envio automático
do link é escrito e não sai. É configuração, não código — mas é gate.

### Desenho

1. **Cadeia do canal `pdv`** — `seed.py`, no `_pos_config`:
   `"notifications": {"backend": "manychat", "fallback_chain": ["email", "sms"]}`.
   O que fazer quando o cliente só tem um dos dois **já está resolvido pelo mecanismo**:
   `_resolve_recipient` devolve `None` para o backend sem destinatário e a cadeia pula
   (`notification.py:152-155`). Só e-mail → cai no e-mail. Só telefone → WhatsApp, e SMS
   se o ManyChat não resolver o assinante.
   Ordem escolhida: **WhatsApp → e-mail → SMS**. A URL do checkout é longa; WhatsApp e
   e-mail a entregam clicável e de graça, o SMS custa e trunca — é a última rede, não a
   segunda.

2. **Template novo `payment_link_sent`** (evento próprio, NÃO reusar `payment_requested`):
   a copy é outra ("anotamos seu pedido", não "conferimos a disponibilidade"), o gatilho é
   outro (fechamento da venda, não `_on_accepted`), e o dedupe de `payment_requested`
   (`notification.py:461-462`) colidiria com o aviso da loja online no mesmo pedido.
   - entra em `_ACTIVE_NOTIFICATION_TEMPLATES` (`notification.py:24-42`) — falha de entrega
     tem que gritar, não sumir;
   - fallback inline em `notification_manychat.MESSAGE_TEMPLATES`,
     `notification_email.SUBJECT_TEMPLATES`/`BODY_TEMPLATES` e `notification_sms`;
   - linha semeada em `config/management/commands/seed.py:7239+`.

3. **Contexto: falta o `checkout_url`.** `_build_context` (`notification.py:292-398`) grava
   `payment` e `payment_url`, e `payment_url` é o **acompanhamento**, não a cobrança.
   Pior: o PDV não grava `customer.uuid`, então nem magic link existe e o `payment_url` cai
   no link comum (`notification.py:369-374`) — que hoje não oferece pagar um pedido de link
   (frente 1, defeito 3). Então:
   - `_build_context` passa a exportar `checkout_url` (de `payment["checkout_url"]`);
   - `derive_context` (`_notification_templates.py:60-91`) ganha `payment_deadline`
     (o `expires_at` da frente 3, formatado "hoje às 18h" / "amanhã às 9h") e a chave
     auto-suprimível `payment_deadline_note`.

4. **Gatilho: Directive, não envio síncrono.** Em `pos.py`, logo depois de
   `payment_service.initiate(order)` ter voltado com `checkout_url`
   (`pos.py:2732-2745`), chamar `notification.send(order, "payment_link_sent")`.
   Por quê Directive:
   - `close_sale` já faz UMA ida à rede inline (o `initiate`), e ela é obrigatória — a URL
     precisa voltar para a tela. O ENVIO não precisa: um timeout de 15s do ManyChat
     (`SHOPMAN_MANYCHAT["timeout"]`) dentro da venda trava o balcão com o cliente na frente;
   - retry, idempotência e escalada já existem de graça no `NotificationSendHandler`
     (5 tentativas → `OperatorAlert` "notification_failed");
   - o dedupe por `(pedido, template)` garante que um retry do PDV não manda o link duas vezes.
   - **Consequência a aceitar:** o mesmo dedupe impede um "reenviar" pelo mesmo caminho.
     Reenvio manual pelo Gestor fica fora deste WP (ver Pergunta 5).
   - A tela continua mostrando a URL + "Copiar link" (`PosPaymentResult.vue:110-114`).
     O envio automático é o padrão; a cópia é a rede. A copy do resultado passa a dizer
     "Enviando por WhatsApp…" em vez de só "Aguardando o cliente pagar."
     (`PosPaymentResult.vue:67`).

### Especificação do template do ManyChat (para o Pablo criar no painel)

- **Categoria Meta:** Utility (é transacional — cobrança de um pedido que a pessoa fez).
- **Onde o namespace entra:** Admin → modelo de mensagem `payment_link_sent` → campo
  **"flow do WhatsApp (ManyChat)"** (`NotificationTemplate.whatsapp_flow_ns`,
  `shopman/shop/models/shop.py:535-541`). Vazio ⇒ a casa manda o texto direto por
  `sendContent`, que já funciona; com o flow preenchido, vai pelo template aprovado.
- **Campos personalizados que o flow precisa ter, com estes nomes EXATOS** (em inglês, como
  o resto do vocabulário de integração; são gravados por `setCustomFieldByName` antes do
  envio — `notification_manychat.py:_push_custom_fields`):
  `order_ref`, `customer_name_greeting`, `total`, `checkout_url`, `payment_deadline`.
  Campo que não existir no ManyChat sai vazio e vira warning no log — criar antes.
- ⚠️ **A armadilha registrada da casa, e o que ela obriga aqui:**
  - **não referencie o campo de sistema `phone` no flow.** Em contato de WhatsApp ele vem
    **NULO**; o preenchido é `whatsapp_phone`
    (`packages/guestman/shopman/guestman/adapters/auth.py:88`,
    `packages/guestman/shopman/guestman/contrib/manychat/resolver.py:241-246`). E do nosso
    lado `phone` está na denylist e **nunca é empurrado**
    (`notification_manychat.py:_FIELD_DENYLIST`);
  - **variável digitada à mão dentro do flow não renderiza** — o flow ignora o
    `flow_token`; toda variável tem que estar **ligada ao campo personalizado** de mesmo nome;
  - quem endereça é sempre o **`subscriber_id`**, resolvido pelo
    `ManychatSubscriberResolver` (DB → `findByCustomField` → `findBySystemField` →
    `createSubscriber(whatsapp_phone)`). Esse caminho nunca erra; telefone solto, sim.

### Copy proposta

**WhatsApp / ManyChat** (`payment_link_sent`):
```
Olá{customer_name_greeting}! Anotamos seu pedido {order_ref} — total {total}.
Para confirmar, é só pagar por aqui: {checkout_url}
O link vale até {payment_deadline}. Qualquer coisa, é só responder esta mensagem. 🥖
```

**E-mail** — assunto: `Pedido {order_ref}: link de pagamento`
```
Olá{customer_name_greeting}!

Anotamos seu pedido {order_ref}. Total: {total}.

Para confirmar, conclua o pagamento por aqui:
{checkout_url}

O link vale até {payment_deadline}. Passado o prazo ele deixa de funcionar e a
gente precisa refazer o pedido.

Qualquer dúvida, é só responder este e-mail.
Nelson Boulangerie
```

**SMS** (uma linha, sem acento decorativo, cabendo em um segmento):
```
Nelson Boulangerie: pedido {order_ref}, {total}. Pague ate {payment_deadline}: {checkout_url}
```

### Arquivos tocados

- `config/management/commands/seed.py` — cadeia de notificação do canal `pdv` + template semeado.
- `shopman/shop/services/notification.py` — `payment_link_sent` na lista ativa; `checkout_url` no contexto.
- `shopman/shop/adapters/_notification_templates.py` — `payment_deadline` / `payment_deadline_note`.
- `shopman/shop/adapters/notification_manychat.py`, `notification_email.py`, `notification_sms.py` — fallbacks.
- `shopman/shop/services/pos.py` — o gatilho depois do `initiate`.
- `surfaces/pos-nuxt/app/components/PosPaymentResult.vue` — copy do resultado.
- Testes: `shopman/shop/tests/` (gatilho, cadeia, contexto) + `surfaces/pos-nuxt/tests/`.

**Tamanho: M** — ~2 dias de código + o trabalho de painel do Pablo (criar campos e flow no ManyChat, submeter o template à Meta).

---

## Frente 3 · Validade do link

**O problema em uma frase.** Nenhum prazo é gravado: o `payment_stripe` nunca seta
`expires_at`, a tela não mostra nada, e o Stripe expira a sessão dele em 24h sem que a
casa saiba — então existe um relógio, ele é do outro, e ninguém aqui o lê.

### O que existe hoje

| Fato | Onde |
|---|---|
| O adapter do Stripe **nunca** seta `expires_at` | `payment_stripe.py:150-165` e `212-219` |
| O mock só seta para Pix | `payment_mock.py:131-132` |
| `_persist_intent` só agenda o timeout **se** houver `expires_at` | `payment.py:214-215` |
| O agendamento (Directive `payment.timeout`, deduplicada, `available_at=expires_at`) | `payment.py:1602-1635` |
| **O handler do vencimento já é genérico e já é seguro** | `shopman/shop/handlers/payment_timeout.py` |
| Ele re-agenda se chamado cedo, pergunta ao gateway antes de cancelar, e só cancela com resposta "não pago" | `payment_timeout.py:27-32`, `55-76` |
| `reconcile_payments` re-arma o timeout de intent PENDING vencida | `reconcile_payments.py:279-315` |
| A reconciliação diária já audita `link` | `financial_reconciliation.py:173` `_AUDITED_METHODS` |
| `expires_at` já viaja no contrato do PDV, só não é renderizado | `surfaces/pos-nuxt/app/types/pos.ts:553` |

**A boa notícia: a máquina inteira já existe e está parada por falta de um campo.**
Setar `expires_at` liga tudo: agendamento, re-arme, cancelamento seguro e o aviso
`payment_expired`.

### Quanto tempo vale, e onde gravar

**24 horas**, gravadas em `PaymentIntent.expires_at` — e, o mais importante, **o mesmo
valor mandado ao Stripe** no `Session.create(expires_at=...)`. O Stripe aceita de 30 min a
24 h; sem mandar, ele usa 24 h por conta própria e passamos a ter **dois relógios**, que é
a origem do problema atual. Um relógio só, escrito nos dois lados.

Botão: `SHOPMAN_PAYMENT_LINK_TTL_HOURS` (default 24), com clamp no teto de 24 h do Stripe.

**A tela mostra:** no resultado da venda, sob a URL — "Vale até **amanhã, 9h**"; e o aviso
ao cliente carrega o mesmo `payment_deadline` (frente 2). Sem prazo dito, "o link parou de
funcionar" vira ligação para o balcão.

### O que acontece com o PEDIDO quando o link vence

| | **A — cancela sozinho** | **B — fila de revisão no fechamento** |
|---|---|---|
| Como | `expires_at` ⇒ Directive `payment.timeout` ⇒ handler pergunta ao gateway ⇒ cancela + `payment_expired` | O intent vence no Stripe; o pedido fica; um check novo na reconciliação diária lista "links vencidos sem pagamento" e alguém decide no fechamento |
| Código novo | **quase zero** — só o `expires_at` | check novo em `financial_reconciliation.py` + superfície no fechamento |
| A favor | Estoque volta sozinho; o cliente é avisado; nada apodrece na fila | Nenhuma encomenda morre sem humano; o operador vê antes de o cliente perder a vaga |
| Contra | Encomenda de sábado cancelada às 3h da manhã de quinta, sem ninguém ver | Estoque preso até alguém olhar; se ninguém olhar, apodrece igual |

**Recomendação: A, com um pedaço do B por cima.** O cancelamento automático é o caminho
que o sistema já sabe percorrer com segurança — ele **pergunta ao gateway antes**
(`payment_timeout.py:59-68`), que é exatamente a garantia que falta a qualquer varredura
manual. E o pedaço do B que vale a pena não é uma fila alternativa, é a **rede para o que
o handler não alcança** (abaixo).

⚠️ **O que o handler NÃO alcança, e precisa de decisão.** Ele só age em pedidos
`NEW`/`ACCEPTED` (`payment_timeout.py:39-40`). Mas uma venda de PDV, retirada, para hoje,
fecha em **COMPLETED** na hora, pelo `counter_handoff`
(`shopman/shop/lifecycle.py:427-428` e `431-444`) — e o canal `pdv` tem
`payment.timing: "external"` (`seed.py:4950`), que desliga o gate de pagamento
(`lifecycle.py:718-722`). Ou seja: **um link de venda de balcão para hoje fecha a venda
como entregue e paga, sem um centavo capturado, e o vencimento passa sem efeito.**

O conserto certo é uma linha no `_counter_handoff`: venda cujo método é `link` **nunca** é
entrega de balcão — o pedido remoto tem trajeto pela frente por definição. Aí o pedido fica
`ACCEPTED`, o handler alcança, e o vencimento funciona.

Mais o pedaço do B: um check `expired_payment_link` na reconciliação diária
(`financial_reconciliation.py`), severidade `warning`, para o que escapar. É o acusador do
dia seguinte que a casa já usa em todo o resto.

### Arquivos tocados

- `shopman/shop/adapters/payment_stripe.py` — `expires_at` no `create_intent` e no `Session.create`.
- `shopman/shop/adapters/payment_mock.py` — mesmo prazo para o link (o dev tem que ver o vencimento).
- `config/settings.py` / `.env.example` — `SHOPMAN_PAYMENT_LINK_TTL_HOURS`.
- `shopman/shop/lifecycle.py` — `_counter_handoff` recusa venda de link.
- `shopman/backstage/services/financial_reconciliation.py` — check `expired_payment_link`.
- `shopman/backstage/projections/pos.py` + `surfaces/pos-nuxt/app/presentation/payment.ts` +
  `PosPaymentResult.vue` — mostrar "Vale até …".
- Testes: `shopman/shop/tests/` (timeout do link ponta a ponta) + `surfaces/pos-nuxt/tests/`.

**Tamanho: M** — ~2 dias.

---

## Frente 4 · TEF da Stone no balcão (crédito/débito)

**O problema em uma frase.** Hoje a captura de crédito e débito é **atestada pelo
operador**; com o TEF ela passa a vir do terminal com NSU e autorização — e a pergunta é o
que exatamente muda, para o WP futuro não reabrir o que já está certo.

### Confirmado lendo o código: muda só a ORIGEM DA PROVA

`PaymentService.settle` (`packages/payman/shopman/payman/service.py:211-336`) grava
`gateway=""`, `gateway_id=""` e um **`gateway_data` livre**, descrito no próprio docstring
como "dados livres de auditoria (ex.: terminal, operador)"
(`service.py:252`). Hoje o chamador manda
`{"collection": "terminal", "terminal_ref": …}` (`shopman/shop/services/payment.py:299-306`).

**É exatamente aí que o TEF pluga:** o mesmo `settle`, o mesmo `ref` de método, o mesmo
`gateway_data` — com a prova do terminal dentro. O valor, o status e a máquina de estados
não mudam em nada.

### O que precisa de campo novo (e por que nenhum é coluna)

Dentro de `gateway_data`, sob uma chave `tef`:
`nsu` (o número que a adquirente e a Stone reconhecem), `authorization_code`, `brand`,
`installments`, `terminal_serial`, `acquirer`.

Nenhum vira coluna: o CLAUDE.md é explícito (regra 1 e 2 de "Core é Sagrado") — informação
contextual vive no JSONField, e o `PaymentIntent.gateway_data` é o campo desenhado para
isso. As chaves entram em `docs/reference/data-schemas.md` antes de serem usadas.

### O que NÃO se mexe

- **`METHODS_WITHOUT_GATEWAY`** (`packages/payman/shopman/payman/models/intent.py:108-115`):
  `credit` e `debit` **continuam** lá. O TEF é um **terminal**, não um gateway REMOTO — não
  há webhook a esperar nem autorização que chegue de fora. Tirá-los da lista faria o
  `settle_terminal_tenders` pular o intent (`payment.py:299-301`) e a venda fecharia com
  **zero** `PaymentIntent`: o comentário no próprio modelo já registra esse buraco.
- **O `ref` da forma** (`credit`/`debit`), a tela do PDV, os atalhos de teclado.
- **O fechamento do dia e o B.I.**, que já separam crédito de débito
  (`shopman/backstage/presentation/status.py:48`, `shopman/backstage/projections/bi_payments.py:84`).
- **`asserted_at_terminal`**: é a porta de pix/card numa venda mista
  (`service.py:256-262`), não tem nada a ver com crédito/débito.

### O único ponto que o TEF de fato reabre: o estorno

Hoje o estorno de crédito/débito é **fato declarado** — sem adapter, o código vai direto ao
Payman (`payment.py:717-735` → `_refund_without_gateway:792-815`). Com TEF, o cancelamento
de verdade acontece **no terminal** (cancelamento no mesmo dia / estorno depois), e o
Payman deveria registrar o NSU do cancelamento. Isso é o WP do TEF, não este.

### Onde o TEF pluga, em uma linha

`shopman/shop/services/payment.py:299-306` — um `gateway_data` enriquecido pela captura do
terminal, com o resto do sistema intocado.

**Tamanho: M/G** — depende inteiramente do SDK da Stone (AutoTEF/Connect) e de o PDV rodar
onde ele roda. A parte NOSSA (aceitar e persistir a prova) é **P**: meio dia.

---

## Perguntas para o Pablo

1. **Stripe ou Stone para o link no go-live?**
   → *Recomendo **Stripe**.* Já está de pé e verificado; a Stone entra depois, junto do TEF,
   quando "um provedor só" compensa o adapter novo. Comparação de taxa é sua — não há nada
   documentado no repositório.

2. **O link pago deve capturar sozinho (`capture_method="automatic"`), ou continuar
   `manual` com a casa capturando depois?**
   → *Recomendo **automatic** para o link.* A venda do balcão já fechou; não existe um
   "aceite" posterior para justificar segurar a autorização. Hoje, com `manual`, **o
   dinheiro do link nunca entra** — é o defeito 1 da frente 1.

3. **Quanto tempo o link vale?**
   → *Recomendo **24 horas**, o teto do Stripe, mandado explicitamente para ele* — assim a
   casa e o gateway usam **o mesmo relógio**, em vez dos dois de hoje.

4. **Link vencido: o pedido cancela sozinho?**
   → *Recomendo **sim**, reusando a máquina que já existe (ela pergunta ao gateway antes de
   cancelar)*, mais um check `expired_payment_link` na reconciliação diária para o que
   escapar. Não recomendo depender só de alguém varrer no fechamento.

5. **Reenvio manual do link pelo Gestor entra neste WP?**
   → *Recomendo **não** — fica registrado como próximo passo.* O dedupe da Directive impede
   o reenvio pelo mesmo caminho, e o botão "Copiar link" no PDV já cobre o caso urgente.

6. **A venda de balcão pode virar "entregue" (COMPLETED) com link pendente?**
   → *Recomendo **não**.* Uma linha em `_counter_handoff` — venda de link nunca é entrega de
   balcão. Sem isso, o vencimento não alcança o pedido e a venda fica registrada como paga
   sem ter sido.

7. **A cadeia de notificação do canal PDV passa a ser WhatsApp → e-mail → SMS?**
   → *Recomendo **sim**.* Hoje ela é `console` primeiro, e o console sempre "dá certo" — ou
   seja, **nenhum aviso de pedido de PDV sai da casa hoje**. Isso muda todos os avisos do
   PDV, não só o link, e é para melhor.
