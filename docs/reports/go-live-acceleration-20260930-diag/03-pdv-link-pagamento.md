# 03 — PDV: link de pagamento no balcão e o envio que não chega

> Diagnóstico, não ensaio. Branch investigado: `dsh/handoff-onda1-e-p7-20260930`
> (worktree `go-live-acceleration`, 3 commits à frente de `origin/main`).
> Legenda: **[FATO]** = lido no código ou medido em comando, com caminho:linha ·
> **[INFERÊNCIA]** = conclusão a partir de fatos, com a hipótese alternativa dita ·
> **[NÃO VERIFICADO]** = o que não deu para checar, e onde procurei.

As duas perguntas do dono têm **respostas diferentes e independentes**:

| Pergunta | Veredito curto |
|---|---|
| (a) link de pagamento em venda de balcão faz sentido? | **Não como está.** A forma é de pedido REMOTO e está sendo oferecida no modo Balcão. A copy "NFC-e sai na retirada" não mente: ela reproduz fielmente um modelo que classifica a venda de link como remota. |
| (b) o link está sendo enviado? | **Despachado, sim. Entregue, não.** Os dois envios foram registrados como `accepted` pelo **manychat** e a cadeia parou no primeiro salto: **e-mail e SMS nunca foram tentados**. Não é o defeito do adapter de e-mail (esse já está corrigido); é o mesmo padrão, um salto antes. |

O cliente **Pablo** existe, o pedido existe e é **um só** em todo o banco do alpha.

---

## 0. A venda que o dono fez — os fatos brutos

Fonte: banco do alpha (`shopman-staging-postgres`, porta direta 25060, banco `shopman`),
somente `SELECT` sob `SET default_transaction_read_only=on`.

**[FATO]** Existe exatamente **um** pedido com `payment.method = 'link'` em 4.815 pedidos:

```
ref         | PDV-260930-R62
channel_ref | pdv          status | cancelled
created_at  | 2026-09-30 21:42:31+00        (18:42 em São Paulo)
cname       | Pablo Valentini
cphone      | 5543984049009
cemail      | pablondrina@gmail.com
```

**[FATO]** `data.pos.sales_mode = "counter"`, `fulfillment_type = "pickup"`,
`origin_channel = "pos"` — o operador fechou a venda **no modo Balcão**.
(consulta: `SELECT data->'pos', data->>'fulfillment_type' ... FROM orderman_order WHERE ref='PDV-260930-R62'`)

**[FATO]** A cobrança criada foi do **Stripe em modo de teste**:

```
payment.checkout_url         = https://checkout.stripe.com/c/pay/cs_test_a1FZ...
payment.provider_environment = "test"
payment.confirmation_mode    = "provider_simulated"
payment.is_test_confirmation = true
```

e `STRIPE_PUBLISHABLE_KEY = pk_test_51PCfiK...` está no spec do app
(`doctl apps spec get 40b86e35-... | sed -n '171,174p'`), com
`SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` (`sed -n '438,440p'`).

> **Consequência direta, independente de (a) e (b):** mesmo que o link tivesse chegado,
> **não havia como pagar** — é uma sessão `cs_test_`. Em alpha isso é esperado; em
> go-live é P0. Fica registrado porque a tela do PDV não diz isso ao operador.

**[FATO]** O intent morreu de vencimento:
`payman_paymentintent PAY-68CBBA0A857B | method=link | gateway=stripe | status=cancelled |
cancel_reason=payment_timeout | cancelled_at=22:12:36` — nunca `authorized`, nunca `captured`.

---

## 1. Pergunta (a) — link de pagamento em venda de balcão

### 1.1 O que a tela PROMETE

**[FATO]** Em `surfaces/pos-nuxt/app/presentation/saleResult.ts:105-115` e `:136-146`:

```
109:    case "awaiting_payment": return "NFC-e sai quando o pagamento confirmar";
110:    case "awaiting_pickup": return "NFC-e sai na retirada";
111:    case "awaiting_delivery": return "NFC-e sai na entrega";
```

**[FATO]** A mesma frase vai para o **papel** que o cliente leva
(`surfaces/pos-nuxt/app/presentation/receipt.ts:153-157`):

```ts
export function receiptFiscalHandoffLine(state: PosFiscalState): string {
  if (state === "awaiting_pickup") return "A nota fiscal sai na retirada.";
```

**[FATO]** E a tela de resultado, sobre o link
(`surfaces/pos-nuxt/app/components/PosPaymentResult.vue:84-86`, comentário que descreve
o que o operador lê): *"No LINK, a frase diz o que a casa FAZ com a URL — a cadeia
WhatsApp → e-mail → SMS enfileirada na venda"*. O texto que o operador **de fato** vê
vem do servidor (`shopman/backstage/projections/pos_payment_delivery.py:49-52`):
`"Envio aceito pelo WhatsApp às 18h42. Leitura não confirmada."`

### 1.2 O que o sistema FAZ (e por que a frase aparece)

Cadeia determinística, sem ramo oculto:

1. **[FATO]** `shopman/shop/services/order_helpers.py:249-276` — `is_counter_takeaway()`:

```
267:    if data.get("origin_channel") != "pos":      return False
269:    if (data.get("fulfillment_type") or "pickup") != "pickup": return False
271:    payment = data.get("payment") or {}
272:    method = str(payment.get("method") or "").strip().lower()
273:    if method == "link":
274:        return False
```

2. **[FATO]** `shopman/shop/services/fiscal.py:364-384` — `emission_waits_for_handoff()`
   devolve `not is_counter_takeaway(order)` → **True**.
3. **[FATO]** `fiscal.py:1013-1016` → `handoff_fiscal_state(order)` (`fiscal.py:424-430`)
   → `fulfillment_type == "pickup"` → **`awaiting_pickup`**.
4. **[FATO]** `awaiting_pickup` → chip "NFC-e sai na retirada" + recibo "A nota fiscal
   sai na retirada."

E a condição de entrada foi satisfeita nesta venda: **[FATO]**
`data.receipt.channels = ["email", "print"]` → `on_requested_receipt` devolve True
(`shopman/shop/fiscal_resolvers.py:81-99`) → `emission_expected` True
(`fiscal.py:887-902`). Sem isso o estado seria `not_expected` e a frase não apareceria.

### 1.3 É a copy que mente, ou o comportamento que está errado?

**O comportamento.** [FATO] A decisão está escrita e é deliberada — commit
`229be2462` (`git log -1 229be2462`):

> *"fix(lifecycle): venda de link nunca é entrega de balcão, e espera a captura"*
> *"O link é o pedido REMOTO: o cliente não está na loja, paga depois pelo celular e
> vem buscar. […] sem esta regra a venda fechava COMPLETED sem um centavo capturado,
> e o vencimento do link passava sem efeito."*

O commit está **certo** para o caso que ele descreve (encomenda por telefone/WhatsApp
anotada no balcão). O defeito é outro: **o PDV oferece `link` também no modo Balcão**,
e nesse modo o operador entregou o pão na hora. A premissa "a mercadoria ainda está na
casa" virou falsa, e a frase fiscal herda a falsidade.

**[FATO]** A prova de que o próprio código sabe disso está no comentário da projeção
(`shopman/backstage/projections/pos.py:487-489`):

```
# `link` é a forma do PEDIDO REMOTO anotado no balcão — encomenda por telefone,
# WhatsApp, o cliente que vai pagar do celular. Ela não é do gesto de balcão:
```

...e em `surfaces/pos-nuxt/app/components/PosPaymentResult.vue:140-145`:

```
<!-- LINK DE PAGAMENTO: para ENTREGAR, não para abrir aqui.
     Ele é a forma do PEDIDO REMOTO — encomenda por telefone, WhatsApp —, e
     nesse pedido o cliente NÃO está no balcão [...]
```

**[FATO]** Mas nada disso é enforçado na tela:

- `shopman/backstage/projections/pos.py:1107-1121` — `_payment_methods()` só filtra
  `link` por **prontidão do gateway** (`_link_payment_available`), nunca por modo de venda;
- `surfaces/pos-nuxt/app/components/PosPaymentWorkspace.vue:1387-1403` — renderiza
  `injectableMethods` sem nenhum gate por `salesMode`;
- `surfaces/pos-nuxt/app/composables/usePosSale.ts:635` — `salesMode` **nasce**
  `"counter"`, que é o modo em que o link apareceu;
- no servidor, os únicos guardas de `link` são `link_requires_customer_contact`
  (`shop/services/pos.py:1081-1103`) e `link_requires_full_payment`
  (`pos.py:3247-3259`). **Não existe** `link_requires_order_mode`.

**Portanto:** não é copy mentirosa — é uma superfície oferecendo no modo A uma forma
cujo comportamento é definido para o modo B. **É opção herdada indevidamente, sim.**

### 1.4 Faz sentido link em venda de balcão? Compare com a loja online

- Loja online (canal remoto): **faz sentido total** — o cliente não está na loja, a URL
  é o único caminho para o dinheiro, a mercadoria fica na casa até a retirada/entrega.
  Ali `awaiting_pickup` / "NFC-e sai na retirada" é **verdade**.
- Balcão com o cliente na frente: **não faz sentido**. Quem está no balcão paga com
  Pix (QR na tela), maquininha ou dinheiro — todas formas que o PDV já oferece e que
  liquidam no ato. O link acrescenta: uma URL que precisa ser entregue por fora, uma
  venda que **não fecha** (fica ACCEPTED, estoque reservado), uma cobrança em gateway
  externo e uma frase fiscal errada no recibo.

**Veredito (a):** o link é forma de **pedido remoto anotado no balcão** (o operador
atende o telefone e anota). Como *essa* intenção não tem porta própria no produto, ela
acabou pendurada na lista de formas do modo Balcão. O lugar certo do link é o modo
**Encomendas** (`sales_mode == "order"`), não a lista geral de formas.

### 1.5 Correção mínima de (a)

Uma trava, no mesmo molde de `_require_contact_if_payment_link`
(`shop/services/pos.py:1081-1103`), que já é o precedente exato deste tipo de recusa:

```python
# shopman/shop/services/pos.py, ao lado de _require_contact_if_payment_link
def _require_order_mode_if_payment_link(payload: dict) -> None:
    """Link é do pedido REMOTO anotado; no Balcão o cliente está na frente."""
    if _payload_payment_method_set(payload) != {"link"}:
        return
    if str(payload.get("sales_mode") or "").strip().lower() == "order":
        return
    raise PosIntentError(
        code="link_requires_order_mode",
        message="O link de pagamento é da encomenda, não da venda de balcão.",
        field="payment",
        focus="payment",
        recovery="Use Pix, cartão ou dinheiro. Para cobrar por link, lance como encomenda.",
    )
```

`payload["sales_mode"]` já chega ao `close_sale` (o PDV o envia:
`surfaces/pos-nuxt/app/utils/posIntent.ts:146`; o serviço já o normaliza em
`_inherit_sales_mode`, `pos.py:2597-2603`). No front, a mesma condição esconde a
forma em `PosPaymentWorkspace.vue` quando `salesMode === "counter"` — o servidor é a
trava, a tela é a cortesia.

**O que NÃO fazer:** mexer em `is_counter_takeaway` para "consertar a frase". Aquela
exclusão do link é a correção do commit `229be2462`, com teste-trava em
`shopman/shop/tests/test_counter_handoff.py:225-231` e
`shopman/shop/tests/test_payment_link_expiry.py:518-529`. Removê-la devolve a venda
que fechava COMPLETED sem um centavo capturado.

## 2. Pergunta (b) — o link está sendo enviado?

**Não é a mesma pergunta que "o link foi despachado?". Despachado foi. Entregue, não.**

### 2.1 Quem dispara, por onde

**[FATO]** O disparo é automático no fechamento da venda, não um clique:

- `shopman/shop/services/pos.py:3466-3469`
  ```python
  if method == "link" and payment.get("checkout_url"):
      _send_payment_link(order)
  elif method == "pix" and payment.get("copy_paste"):
      _send_payment_pix(order)
  ```
- `pos.py:3519-3539` — `_send_payment_link()` → `notification.send(order, "payment_link_sent")`
  (Directive, assíncrona; template `PAYMENT_LINK_TEMPLATE`, `services/notification.py:32`).
- O botão "Reenviar" da tela chama
  `POST /api/v1/backstage/pos/orders/<ref>/send-payment-notice/`
  (`shopman/backstage/api/urls.py:920`, `api/operations.py:3402-3423` →
  `notification_service.send_or_resend_payment_notice`, `services/notification.py:411-437`).

### 2.2 A evidência de envio, no banco de produção

**[FATO]** `orderman_directive` do pedido `PDV-260930-R62` (consulta por
`payload->>'order_ref'`, ordenada por `created_at`):

| id | template | criada | `notification_delivery` |
|---|---|---|---|
| 21849 | `payment_link_sent` | 21:42:36 | accepted / manychat / fingerprint `ba4a63a45feba615` |
| 21850 | `payment_link_sent` | 21:44:20 | accepted / manychat / fingerprint `ba4a63a45feba615` |
| 21852 | `order_cancelled` | 22:12:38 | accepted / manychat |
| 21853 | `payment_expired` | 22:12:39 | accepted / manychat |

- A 21849 é o disparo automático do fechamento; a 21850 é o clique de **Reenviar**.
- `ba4a63a45feba615` = `sha256("+5543984049009")[:16]` — confere com
  `services/notification.py:1428-1430` e com `_manychat_phone` (`notification.py:1214-1225`).
  **O destinatário tinha telefone válido e resolveu.** Não é caso de "sem contato":
  [FATO] `guestman_customer` para `MC-115B31B4` tem `phone=+5543984049009`,
  `email=pablondrina@gmail.com` e `CustomerIdentifier(manychat)=4605528796186498`.

### 2.3 A cadeia parou no primeiro salto — e-mail e SMS nunca foram tentados

**[FATO]** A cadeia do canal `pdv` é `["manychat", "email", "sms"]`:
`config/management/commands/seed.py:6068` —
`"notifications": {"backend": "manychat", "fallback_chain": ["email", "sms"]}`,
montada em `services/notification.py:594-601`.

**[FATO]** O laço para na **primeira** resposta de sucesso
(`services/notification.py:533-543`):

```python
result = notify(event=template, recipient=recipient, context=context, backend=backend_name)
if result.success:
    _record_delivery(payload, status="accepted", backend=backend_name, ...)
    return True, None
```

Como o manychat devolveu sucesso em 21:42:37, **os saltos 2 e 3 não existiram no log
nem no banco**: não há nenhuma linha `notification_delivery` com `backend` igual a
`email` ou `sms` para este pedido.

### 2.4 O achado anterior (adapter de e-mail) NÃO é a explicação — e já está corrigido

A tarefa apontou `docs/plans/fallbacks-perigosos-go-live.md` item 4 como suspeito.
**[FATO] Ele está desatualizado.** O conserto já está em `origin/main`:

```console
git show origin/main:shopman/shop/adapters/notification_email.py | grep -n "is_available" -A6
178:def is_available(recipient: str | None = None, **config) -> bool:
181:    Isto já foi bool(EMAIL_HOST or EMAIL_BACKEND), e era um fail-open
195:    if any(inerte in backend for inerte in _BACKENDS_INERTES):
196:        return False
```

`shopman/shop/adapters/notification_email.py:149-211` — backend de console/locmem/dummy
devolve `False`, SMTP sem host devolve `False`, e remetente de domínio reservado
(`.local`, `example.*`) devolve `False` (`remetente_entrega`, linhas 160-175). O
comentário do item 4 do documento descreve o mundo **anterior** a esse conserto.

**[FATO]** E o e-mail **funciona** neste deployment, medido:

- app spec: `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`,
  `EMAIL_HOST=smtp.gmail.com`, `EMAIL_PORT=587`,
  `DEFAULT_FROM_EMAIL="Nelson Boulangerie <nelson@boulangerie.com.br>"`
  (`doctl apps spec get 40b86e35-... | sed -n '321,341p'`) — remetente com domínio real,
  passa em `remetente_entrega`.
- `COMTELE_API_KEY` e `COMTELE_ROUTE` estão no spec (linhas 202-206) → `SHOPMAN_SMS`
  (`config/settings.py:965-977`) está **configurado**; o SMS não está inerte.
- [FATO] O e-mail **já entregou para o próprio Pablo**, dias antes:
  `orderman_directive 21833 | ref PDV-260929-G20 | template order_updated | created_at
  2026-09-29 15:18:12 | status accepted | backend email | recipient_fingerprint
  e5bdff12eb7045d6`, e `e5bdff12eb7045d6` = `sha256("pablondrina@gmail.com")[:16]`.

**Ou seja: o e-mail teria chegado. Ele só nunca foi tentado.**

### 2.5 Então o que explica "não recebi nem no WhatsApp nem no e-mail"

**[FATO]** O adapter do ManyChat declara sucesso a partir de `status: success` do
provedor, e o próprio código diz que isso **não é recibo de entrega**
(`shopman/shop/adapters/notification_manychat.py:79-84`):

```python
resp_data = json.loads(response.read().decode("utf-8"))
if resp_data.get("status") == "success":
    # Subscriber identity is not a delivery receipt.
    return {"success": True}
```

**[FATO]** O `message_id` fica vazio nesse caminho — o adapter devolve só
`{"success": True}`, e `_record_delivery` grava `message_id` somente quando há valor
(`services/notification.py:1431-1432`). O registro de 21:42:37 **não tem
`message_id`**. Não existe, do lado da casa, nada que se possa conferir no provedor.

**[FATO]** O template `payment_link_sent` **não tem flow aprovado**, então cai no
caminho de texto livre (`sendContent`), e não no de template:

- banco: `SELECT event, whatsapp_flow_ns FROM shop_notificationtemplate WHERE
  event='payment_link_sent';` → **vazio**;
- `config/settings.py:689-698` — `MANYCHAT_FLOW_MAP` só tem `order_rescheduled` e
  `order_updated`;
- o adapter escolhe o caminho em `notification_manychat.py:318-406` (`if flow_ns:`
  → `sendFlow`; senão → `sendContent`).

**[FATO]** O docstring do próprio adapter de texto livre diz o que isso significa
(`shopman/shop/adapters/notification_manychat.py:111-113`): *"No approved template
mapped → plain text (delivered only inside the 24h window)"* — e
`shopman/shop/checks.py:909-913` documenta o mecanismo da Meta: *"A Meta não deixa
texto livre sair para quem não interagiu nas últimas 24 horas (`code 3011`). O escape
é um template aprovado, que no ManyChat vira um flow."*

**[INFERÊNCIA — a explicação mais provável]** O ManyChat **aceitou** a chamada
(`status: success`) e a Meta **não entregou** a mensagem de texto livre; o registro
ficou `accepted` e a cadeia parou ali, então o e-mail — que funcionaria — nunca foi
tentado. É **o mesmo padrão de `fallbacks-perigosos` item 4** (sucesso falso no
primeiro salto curto-circuita a cadeia), mas **noutro adapter**: o de e-mail foi
consertado; o ManyChat, não.

**Corroboração que encontrei (e que me faz preferir essa hipótese):** [FATO] no
histórico do banco, o e-mail só aparece **uma** vez — e é exatamente num template que
**tem flow** (`order_updated`, `MANYCHAT_FLOW_MAP`). O caminho de flow é honesto
quando falha (`_flow_lacks_name` e `_push_custom_fields` devolvem `False`,
`notification_manychat.py:327-332` e `:356-363`) e a cadeia segue. O caminho de texto
livre **nunca falha** — por isso tudo que passa por ele morre em silêncio.

**[NÃO VERIFICADO]** *Por que* a Meta não entregou, exatamente. Não consegui distinguir
daqui entre: (i) fora da janela de 24h (`code 3011`); (ii) o assinante do Pablo estar
roteado por Instagram — [FATO] ele tem
`CustomerIdentifier(instagram)=8018656134842040` além de
`manychat=4605528796186498` e `whatsapp=+5543984049009` — e o `sendContent` cair no
canal errado. As duas produziriam o mesmo registro. **O teste que separa:** reenviar
agora com `MANYCHAT_FLOW_MAP` preenchido para `payment_link_sent` (caminho de flow,
que falha alto) e observar se o salto para o e-mail acontece; ou consultar
`/fb/subscriber/getInfo` do assinante `4605528796186498` para ver qual canal está de
pé (`whatsapp_phone` presente ou não).

### 2.6 O log de produção — o que deu e o que não deu

Pedido na tarefa: `doctl --context shopman-do-app-admin apps logs
40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f --type run`. **Rodei; não serve para esta
pergunta.** [FATO]:

- O componente `web` só emite log de acesso (gunicorn/uwsgi): `"GET
  /api/v1/backstage/... 200"`, `"GET /health/live/ 200"`. Um `grep -i` por
  notification / payment_link / payment_requested / "Email result" / Comtele /
  ManyChat / SMS sobre a saída inteira devolveu **zero** linhas de aplicação — só o
  path `/api/v1/backstage/notifications/` do gestor casou, por causa da palavra.
- As linhas de notificação moram no componente `directive-worker`
  (`orderman … process_directives`, `packages/orderman/shopman/orderman/management/commands/process_directives.py:246`).
  `doctl apps logs <id> directive-worker --type run` devolveu **23 linhas**, todas do
  boot a partir de `2026-09-30T23:16:02Z` mais três `"Diretivas concluídas: 1"` até
  `00:09`. **A janela não cobre 21:42** — o worker reiniciou às 23:16, 1h34 depois do
  evento.
- `grep` pelas mesmas palavras na saída do `directive-worker`: **vazio**.

**Portanto: o log de produção disponível não contém a evidência** — nem a favor, nem
contra. A evidência que resolve a pergunta está no banco (`orderman_directive`), e é
ela que uso. [FATO] Além disso, o ambiente está em redeploy contínuo (11 deployments
entre 17:17 e 00:13 de 30/09), então qualquer janela longa de log se perde no restart.

### 2.7 Correção mínima de (b)

Dois passos, nesta ordem — o primeiro é barato e resolve o dinheiro **hoje**:

**1. Fazer o salto de texto livre cair para o próximo canal quando não houver recibo.**
No mesmo lugar onde o e-mail já faz isso certo: o adapter do ManyChat. A chamada de
`sendContent` sem flow não deve devolver `success=True` como se fosse entrega —
`notification_manychat.py:371-406` deve devolver `False` quando não há `flow_ns`
**e** o evento exige aceite garantido (o conjunto já existe:
`services/notification.py:39-60`, `_ACTIVE_NOTIFICATION_TEMPLATES`, que inclui
`payment_link_sent` e `payment_requested`). Com isso a cadeia segue para o e-mail —
que está vivo e entregou para o mesmo cliente em 29/09 — e o link chega.

Variante mais restrita, se preferirem não mexer no caminho geral: dar ao
`payment_link_sent` um **flow aprovado** (`NotificationTemplate.whatsapp_flow_ns` ou
`MANYCHAT_FLOW_MAP`), como já existe para `order_updated`. Aí o envio passa pelo
caminho que falha alto e a cadeia funciona sozinha. Exige aprovação de template na Meta.

**2. Parar de gravar `accepted` para um aceite sem recibo.** O registro deveria
distinguir "o provedor aceitou" de "o provedor confirmou" — o vocabulário já existe
(`status: "unknown"` / `outcome_unknown`, `services/notification.py:545-548`), e o
`notification_delivery` de manychat não carrega `message_id` nenhum. Sem isso a tela
do PDV continua dizendo "Envio aceito pelo WhatsApp" e o operador não tem por que
desconfiar.

**3. (Guarda, para não voltar)** estender `check_whatsapp_flow_coverage`
(`shopman/shop/checks.py:905-970`) para os templates transacionais com
`requires_active_notification`, não só para `announcement_published`. Hoje um
`payment_link_sent` sem flow sobe em produção calado.

---

## 3. Resposta ao dono

**(a) "Faz sentido link de pagamento em venda de balcão?"** — Faz sentido para o
pedido REMOTO anotado no balcão (o cliente ligou, você anotou, ele paga pelo celular).
Não faz sentido na venda de balcão com o cliente na frente: quem está ali paga no Pix,
na maquininha ou em dinheiro. O PDV oferece a forma nos dois casos, e é daí que vem a
frase estranha.

**(a) "Diz NFC-e sai na retirada… wtf?"** — Não é a frase que mente: o sistema
classifica toda venda de link como "remota" (a mercadoria ficou na casa), decisão
deliberada do commit `229be2462` para não fechar a venda sem dinheiro capturado. Numa
venda de Balcão essa premissa é falsa, e a frase fiscal herda a falsidade — no chip da
tela **e no papel**: "A nota fiscal sai na retirada." A correção é não oferecer o link
no Balcão, não reescrever a frase.

**(b) "O link está sendo enviado?"** — Foi despachado **duas vezes** (automático às
21:42:36 e no Reenviar às 21:44:20) e as duas foram registradas como
`accepted / manychat`. Nada chegou porque a cadeia **para no primeiro sucesso** e o
ManyChat declarou sucesso sem entregar: **e-mail e SMS nunca foram tentados**.

**(b) "Não recebi nem no WA nem no email"** — O e-mail não é o culpado e não está
quebrado: o defeito do adapter de e-mail (`fallbacks-perigosos` item 4) já está
corrigido no `main` e **entregou** para esse mesmo endereço em 29/09 15:18. O culpado
é o ManyChat devolvendo `status: success` para um texto livre que a Meta não entrega,
sem `message_id` e sem flow aprovado para o `payment_link_sent`. Mesmo padrão do
item 4, um salto antes.

**Bônus que dói:** o link aponta para `checkout.stripe.com/c/pay/cs_test_…`
(`provider_environment: "test"`). Mesmo entregue, não havia como pagar.

---

## 4. Onde procurei e o que não achei

| Procurei | Onde | Resultado |
|---|---|---|
| Flow aprovado do `payment_link_sent` | banco (`shop_notificationtemplate.whatsapp_flow_ns`), `config/settings.py:689-698` | **não existe** — caminho de texto livre |
| Recibo do provedor do envio | `orderman_directive.payload.notification_delivery` | só status / backend / recorded_at / recipient_fingerprint, **sem `message_id`** |
| Log de aplicação do envio | `doctl apps logs <id> --type run` (web) e `… directive-worker --type run` | web só tem acesso; worker só o boot de 23:16 em diante — **janela não cobre 21:42** |
| Gate de `link` por modo de venda | `shop/services/pos.py`, `backstage/projections/pos.py`, `PosPaymentWorkspace.vue` | **não existe** (só prontidão de gateway e as duas travas de contato/valor) |
| Teste que afirma o comportamento fiscal do link no Balcão | `shopman/shop/tests/test_counter_handoff.py`, `shopman/shop/tests/test_payment_link_expiry.py` | existem, e **afirmam** o comportamento atual (link nunca é entrega de balcão) |
| Motivo exato da não-entrega na Meta | fora do alcance daqui (painel ManyChat/Meta, `getInfo` do assinante) | **não verificado** — hipóteses em §2.5 |
| Outro pedido de link no alpha | `SELECT count(*) FROM orderman_order WHERE data->'payment'->>'method'='link'` | **1** — este é o único caso; não há amostra maior para comparar |

**Sem consulta ao banco do alpha eu teria respondido (b) errado.** O código sozinho
mostra que o envio é despachado e que a cadeia para no primeiro sucesso; só o
`notification_delivery` gravado diz *qual* salto foi, e só a ausência de uma linha de
e-mail/SMS prova que os outros dois não foram tentados.

### Como reproduzir as consultas

```console
doctl --context shopman-do-app-admin databases connection dd2ca658-a9bd-4188-8b8a-9eea6618b7c3
psql "<URI direta, porta 25060, banco shopman>" -v ON_ERROR_STOP=1 -x
SET default_transaction_read_only=on;
SELECT id, payload->>'template', payload->'notification_delivery', created_at
FROM orderman_directive WHERE payload->>'order_ref' = 'PDV-260930-R62' ORDER BY created_at;
```

Tudo o que foi rodado contra o alpha foi `SELECT`, sob
`SET default_transaction_read_only=on`. Nenhum comando mutante de `git` foi executado.

---

## 5. Correções mínimas — resumo para a esteira

| # | Onde | O quê | Risco de não fazer |
|---|---|---|---|
| 1 | `shopman/shop/adapters/notification_manychat.py:371-406` | texto livre (`sendContent` sem `flow_ns`) devolve `False` para template de `_ACTIVE_NOTIFICATION_TEMPLATES`; a cadeia segue para e-mail/SMS | **dinheiro**: link de pagamento e pedido de compra morrem em silêncio |
| 2 | `shopman/shop/services/pos.py:1081-1103` (ao lado) | `_require_order_mode_if_payment_link` — `link` só com `sales_mode == "order"`; esconder a forma no Balcão em `PosPaymentWorkspace.vue` | nota fiscal com a frase errada na mão do cliente, e venda que não fecha no balcão |
| 3 | `shopman/shop/checks.py:905-970` | cobertura de flow também para templates transacionais ativos | configuração faltando sobe calada |
| 4 | `docs/plans/fallbacks-perigosos-go-live.md:101-125` | item 4 passou a resolvido — o conserto está em `origin/main`; o texto ainda descreve o mundo anterior | o próximo agente persegue um fantasma |
| 5 | investigação | `checkout_url` do alpha é `cs_test_` (Stripe test); conferir `STRIPE_SECRET_KEY`/`EFI_SANDBOX` antes do go-live | link que ninguém consegue pagar |
