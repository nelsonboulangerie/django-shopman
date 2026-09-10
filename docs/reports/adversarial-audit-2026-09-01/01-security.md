# Auditoria adversarial — autenticação, autorização e superfície de ataque

**Escopo:** auth do cliente (storefront + doorman), auth do operador (backstage + PIN/crachá),
IDOR/autorização a nível de objeto, webhooks, rate limiting, segredos/config, injeção e
exposição de dado, e a camada BFF Nuxt.

**Método:** leitura de código. Nenhuma suíte foi executada (banco compartilhado). Toda
afirmação marcada CONFIRMADO foi lida na fonte, com `arquivo:linha`. O que não deu para provar
só lendo está em *Suspeitas*.

**Contexto vivo assumido** (lido de `.do/app.alpha-subdomains.yaml`):
`SHOPMAN_OPERATOR_API_HOST=api.boulangerie.com.br`,
`SHOPMAN_OPERATOR_COOKIE_DOMAIN=.boulangerie.com.br`,
`SHOPMAN_ADMIN_HOST=admin.boulangerie.com.br`, as nove superfícies Nuxt proxiando para
`https://api.boulangerie.com.br`, e `daphne` sem `-v`.

> **Correção ao `docs/plans/fallbacks-perigosos-go-live.md`.** O Tier 4 do documento afirma que
> `SECRET_KEY` (E001) e `ALLOWED_HOSTS` (E002) têm buraco de runtime — *"⚠️ Sim"* nas duas
> linhas. **Isso está desatualizado.** `config/settings.py:1580-1586` tem `assert` no import do
> settings (portanto no boot de todo worker, não só em `check --deploy`), e não há
> `PYTHONOPTIMIZE` nem `python -O` no `Dockerfile` nem nos specs — os asserts são vivos. Cheguei
> a escrever os dois como P0 antes de conferir; deixo o registro porque o documento vai induzir
> a próxima pessoa ao mesmo erro. O que sobra é uma fresta estreita no `ALLOWED_HOSTS`, abaixo
> em P2-1.

---

## P0

### P0-1 — O log de acesso do daphne grava os tokens de webhook em texto puro no stream da DO

**CONFIRMADO** (achado do agente de config; verifiquei a cadeia inteira no daphne instalado)

- `.do/app.subdomains.yaml:215` e `.do/app.alpha-subdomains.yaml:409` — `run_command: daphne -b 0.0.0.0 -p 8000 config.asgi:application`, **sem `-v`**
- `daphne/cli.py:79` — `verbosity` default `1`; `cli.py:234-235` — `elif args.verbosity >= 1: access_log_stream = sys.stdout`
- `daphne/http_protocol.py:277-286` — loga `"path": uri` onde `uri = self.uri.decode("ascii")`, e `self.uri` é o **request-target cru, com query string** (`http_protocol.py:111-112` deriva `query_string` justamente fatiando `self.uri`)
- `daphne/access.py:18-25` — `request="%(method)s %(path)s"`, escrito no stream

E o token é a autenticação **única** desses três webhooks:
- `shopman/shop/webhooks/efi.py:334` — `request.query_params.get("token", "")`
- `shopman/shop/webhooks/ifood.py:222`, `shopman/shop/webhooks/machine.py:148` — idem
- a allowlist de IP da EFI é vazia por default (`config/settings.py:1206-1210`, decisão
  deliberada de disponibilidade) e o cabeçalho de mTLS é **advisory** (`efi.py:317-323`)

**Cenário concreto:** toda chamada legítima da EFI grava
`POST /api/webhooks/efi/pix/?token=<EFI_WEBHOOK_TOKEN> 200` no stream de log da DO, retido e
legível por qualquer pessoa com acesso ao console, por qualquer integração de log-shipping, por
um token de API da DO vazado, ou por um log colado num ticket de suporte. De posse do token, o
atacante POSTa um Pix confirmado para um `txid` de um pedido real. O caminho do dinheiro é
`efi.py:210` → `services/pix_confirmation.py:74` → `_confirm_pix_on_live_charge` → captura no
Payman → `dispatch(order, "on_paid")`. Pedido pago, pão entregue, R$ 0 recebido — o mesmo
desfecho do P0 do `E54`, por outra porta.

O `before_send` do Sentry (`config/settings.py:1481-1508`) resolve o vazamento **para o
Sentry**, e o comentário em `efi.py:330-332` se apoia nele. Não faz nada para o stdout.

**Correção:**
1. `daphne -v 0` nos dois specs (imediato), ou um filtro de access log que redija `token=`.
2. **Rotacionar os três tokens** — eles estão nos logs agora. Rotacionar a URL da EFI significa
   recadastrar (ver `reference_efi_webhook_url_token_na_query` na memória do projeto).
3. Onde o provedor permitir, migrar para o cabeçalho — `efi.py:333` já aceita
   `X-Efi-Webhook-Token`.

---

### P0-2 — Escalada de privilégio: `Gerente` → superusuário → Admin, via reset de PIN

**CONFIRMADO** · cadeia completa lida:

- `shopman/backstage/api/operations.py:784-818` (`OperatorPinResetView`) — `required_permission = "cashman.manage_operators"`
- `shopman/backstage/api/operations.py:428-430` — alvo resolvido por
  `filter(pk=raw_id, is_staff=True)` ou `filter(username=username, is_staff=True)`.
  **Sem recusa de conta superusuária.**
- `shopman/backstage/services/operator.py:181-194` (`reset_operator_pin`) — única guarda é
  `is_active`
- `shopman/backstage/api/operations.py:534-537` (`OperatorUnlockView`) — busca por `pk` sem
  filtro de staff
- `shopman/backstage/services/operator.py:63-83` (`_eligible`) — confere `is_active`,
  `is_staff` e `has_perm`; `has_perm` de superusuário devolve sempre `True`
- `shopman/backstage/api/operations.py:593` — `login(request, operator, backend=MODEL_BACKEND)`
- `shopman/shop/management/commands/setup_groups.py:164` — a persona Gerente **tem**
  `cashman.manage_operators`

**Cenário concreto:** o `setup_groups.py:129-132` diz, por escrito, que a Gerente é
deliberadamente mantida fora da apuração de caixa — *"ela opera, autoriza exceção e conta às
cegas; quem vê dinheiro é quem audita"* — e por isso não recebe `cashman.audit_shift`. Ela então:

1. `POST /api/v1/backstage/operators/pin/reset/` com `{"username": "admin"}` → a resposta devolve
   o PIN temporário **em claro** (`operations.py:818`).
2. `POST /api/v1/backstage/operator/unlock/` com `{"operator_id": <pk do admin>, "pin": "<temp>"}`
   → `login()` como superusuário.
3. `OperatorSessionDomainMiddleware` (`shopman/shop/middleware.py:142-145`) carimba
   `Domain=.boulangerie.com.br` no cookie. A aba ao lado abre
   `https://admin.boulangerie.com.br/admin/` como superusuário, com
   `SHOPMAN_ADMIN_REQUIRE_2FA` desligado por default.

`pin_must_change` **não é imposto em lugar nenhum** — grep confirma que ele só aparece no payload
de `OperatorSessionView` (`operations.py:324`, `:415`) como dica para a tela. Nenhum gate o lê.
Ela nem precisa rotacionar.

A partir daí: apuração de caixa, `POSCashRefundView`, `POSMovementView`, o export do P1-4 com
todo o PII de cliente, e o Admin inteiro.

Este é exatamente o buraco de 20/08 que `shopman/backstage/station_trust.py:130-157` descreve e
fecha **para a estação autônoma** (`if conta.is_superuser: return None`, com `logger.error`). A
mesma recusa não existe no caminho do PIN.

**Correção (três linhas):**
1. `reset_operator_pin` e `OperatorPinResetView` recusam alvo com `is_superuser=True`.
2. `_eligible` recusa `is_superuser` — o dono entra por senha + 2FA no Admin, nunca por PIN de
   balcão.
3. Impor `must_change` no gate: operador com `must_change=True` só alcança
   `OperatorPinChangeView`.

---

### P0-3 — O BFF apaga o IP do cliente: todo rate limit anônimo vira um bucket global

**CONFIRMADO** (achado independente meu e do agente de BFF) ·
`surfaces/operator-kit/server/utils/djangoProxy.ts:87-105` e
`surfaces/storefront-nuxt/server/utils/djangoProxy.ts:98-116`

Os dois proxies montam o mapa de cabeçalhos **do zero** — `accept`, `cookie`, `content-type`,
`origin`, `referer`, `x-csrftoken` — e nunca repassam `X-Forwarded-For` nem `X-Real-IP`. O
navegador fala com o Nitro same-origin (`apiPath('/api/v1/...')` —
`surfaces/storefront-nuxt/app/composables/useCartState.ts:263` e irmãos) e o Nitro abre conexão
nova para `https://api.boulangerie.com.br`.

Do lado Django, `RATELIMIT_IP_META_KEY = "shopman.shop.services.auth.client_ip"`
(`config/settings.py:423`) → `packages/doorman/shopman/doorman/utils.py:9-25`, rightmost do XFF.
O único XFF que chega é o que o edge da DO acrescenta **para o IP de saída do app Nitro** —
idêntico para todo cliente. O `AnonRateThrottle` do DRF (`config/settings.py:827,844-849`) usa
`BaseThrottle.get_ident`, e `NUM_PROXIES` não está definido em lugar nenhum: mesmo efeito.

O próprio `config/settings.py:415-422` descreve este cenário como o que **não pode** acontecer.

| Limite | Arquivo:linha | Efeito com bucket único |
|---|---|---|
| `Gates.ip_rate_limit` 20/h | `packages/doorman/shopman/doorman/gates.py:170-204`, chamado sem args em `services/verification.py:147` | **20 pedidos de código por hora, na loja inteira** — a 21ª pessoa lê "Muitas tentativas deste local" |
| OTP request `5/m` | `shopman/storefront/api/auth.py:461` | 5 pedidos de código por minuto na loja inteira |
| Checkout `3/m` | `shopman/storefront/api/views.py:453-461` | **3 checkouts anônimos por minuto na loja inteira** |
| verify-code / access-link / passkey `10/m` | `auth.py:204,516,550,790` | idem |
| Throttle anônimo do DRF `120/min` | `config/settings.py:827` | 120 requisições anônimas por minuto para toda a loja |

**Cenário concreto:** um laço de `curl` de uma máquina só, 21 chamadas em
`/api/v1/auth/request-code/`, e **ninguém mais consegue entrar na loja pela próxima hora**.
Vinte e uma. Sem botnet, sem proxy, sem nada. E o checkout anônimo cai junto, a três por minuto.

Isto é P0 de disponibilidade, não de confidencialidade — mas numa padaria que vai abrir a loja
online, "o login e o checkout param com um comando" é catastrófico do mesmo jeito. Como efeito
colateral, todo controle de abuso por IP do sistema é decorativo: o atacante está no mesmo
bucket que os clientes.

**Correção — as duas metades juntas, nunca separadas:**
1. Nos dois `djangoProxy.ts`, **anexar** o peer à cadeia em vez de inventá-la:
   `headers['x-forwarded-for'] = [getRequestHeader(event,'x-forwarded-for'), event.node.req.socket.remoteAddress].filter(Boolean).join(', ')`
2. Ajustar `DOORMAN_TRUSTED_PROXY_DEPTH` ao novo comprimento da cadeia (edge → BFF → edge →
   Django) e definir `REST_FRAMEWORK["NUM_PROXIES"]` no mesmo valor.

⚠️ Fazer só (1) troca um DoS por um IP **spoofável** — o cliente prepende o que quiser e o
rightmost-1 passa a ser dele. Medir a cadeia real primeiro com `SHOPMAN_LOG_CLIENT_IP`, que já
existe (`shopman/shop/services/auth.py:76-83`).

---

## P1

### P1-1 — Path traversal nos catch-alls do BFF: a loja pública vira proxy para todo o Django

**CONFIRMADO** (agente de BFF, com prova empírica contra o `h3` instalado) ·
`surfaces/storefront-nuxt/server/api/v1/[...path].ts:6-11`,
`surfaces/storefront-nuxt/server/utils/storefrontApiAllowlist.ts:29-31`,
`surfaces/storefront-nuxt/server/api/auth/[...path].ts:5-6` (sem allowlist nenhuma),
`surfaces/operator-kit/server/utils/djangoProxy.ts:83-84` + os 8 catch-alls de operador.

`event.context.params.path` é usado cru e não decodificado (h3 não normaliza router params);
concatenado no alvo, o parser de URL do `$fetch` colapsa os `..`. Provado:

```
GET /api/v1/../../admin/login/          → http://django/admin/login/
GET /api/v1/%2e%2e/%2e%2e/admin/login/  → http://django/admin/login/
isStorefrontApiPathAllowed('cart/../backstage/orders/') === true
```

`surfaces/storefront-nuxt/tests/securityBoundaries.test.ts:12-17` afirma que backstage não passa
pelo BFF público — o controle cai com um `../`.

**Cenário concreto:** como o cookie de operador é `Domain=.boulangerie.com.br`, o navegador do
operador manda a sessão dele **também** para `menu.boulangerie.com.br`. Hoje a allowlist contém
qualquer foothold same-site (XSS na loja, subdomínio tomado) aos endpoints de storefront; com a
travessia, o mesmo foothold vira `fetch('/api/v1/cart/../backstage/pos/cash/movement/', {method:'POST'})`
— e o próprio BFF fornece o `X-CSRFToken` e forja `Origin`/`Referer` (ver P2-4). É a diferença
entre "XSS na loja incomoda o cliente" e "XSS na loja move dinheiro no caixa".

**Correção:** decodificar uma vez e rejeitar (400) qualquer segmento que resulte em `.` ou `..`,
**antes** de montar o alvo e **antes** da allowlist, nos dois proxies. Mesmo tratamento em
`server/api/auth/[...path].ts` — ou apagá-lo, já que `auth/` é prefixo permitido na rota
`/api/v1/`.

---

### P1-2 — Link de rastreio/pagamento que NÓS empurramos concede device trust de 30 dias

**CONFIRMADO** · `shopman/shop/services/access_urls.py:71-89` +
`shopman/shop/services/notification.py:340-341` + `shopman/storefront/api/auth.py:295-308`

`AccessLinkExchangeView` documenta a regra em `auth.py:295-299`:

> "Link nascido de uma MENSAGEM que a pessoa enviou (`source=manychat`) prova posse do número…
> Link que NÓS empurramos (`internal`, campanha) não confia: mensagem se encaminha."

E implementa (`auth.py:300-308`): `if source == "manychat"` → `IDENTITY_DEVICE` na sessão **e**
`auth_service.trust_device(...)`, cookie de 30 dias (`DOORMAN.DEVICE_TRUST_TTL_DAYS = 30`).

Mas `build_tracking_access_url` e `build_payment_access_url` têm `source: str = "manychat"` como
**default** (`access_urls.py:71`, `:80`), e `notification.py:340-341` os chama sem passar
`source`. São exatamente os links que a loja **empurra** por WhatsApp/SMS/e-mail no
`payment_requested` e no acompanhamento.

O contraste prova que a intenção era outra: `campaign_identity.py:63` e
`shop/services/access.py:74` usam `Source.INTERNAL` explicitamente, e por isso escapam do ramo de
confiança.

**Cenário concreto:** o cliente encaminha "olha meu pedido" para o grupo da família; ou o e-mail
está numa caixa compartilhada; ou o SMS aparece na tela de bloqueio de um celular emprestado.
Quem tocar no link dentro do TTL ganha: sessão autenticada, `identity_strength = device`
(identidade FORTE), e cookie de dispositivo confiável de **30 dias** — que dispensa OTP para
sempre naquele navegador, permite **cadastrar uma passkey** (que vale para sempre; `auth.py:717,745`
só barram `knows_only_the_number`), ler telefone/e-mail/endereço completos, e cancelar pedidos.

Atenuante: TTL default de 5 min (`DOORMAN.ACCESS_LINK_EXCHANGE_TTL_MINUTES`) e uso único.

**Correção:** `source: str = "internal"` nos dois helpers — melhor ainda, exigir `source`
explícito (sem default) em `build_access_url`, para que "isto prova posse do número?" nunca seja
herdado por omissão. E um teste que afirme que um link de notificação **não** confia no
dispositivo.

---

### P1-3 — `identity_strength()` devolve o valor FORTE quando o marcador está ausente

**CONFIRMADO** · `shopman/storefront/identity.py:73-83`

```python
def identity_strength(request) -> str:
    """A força da identidade desta sessão. Ausente ⇒ ``device``."""
    ...
    return session.get(IDENTITY_SESSION_KEY) or IDENTITY_DEVICE
```

O marcador só é escrito em três lugares: `_record_identity_strength` (só para
`login_source == "campaign"` ou `"handoff"`), o ramo `manychat` de `AccessLinkExchangeView`, e
`PasskeyLoginView`. **O login por OTP e o `trusted_device_login` não escrevem nada** — e é essa a
justificativa da docstring.

O problema é a forma, não o caso conhecido. `AccessLinkCreateView`
(`packages/doorman/shopman/doorman/views/access_link.py:100`) aceita `metadata` arbitrária do
chamador, e qualquer link cunhado sem `login_source` — hoje, `build_tracking_access_url` e
`build_payment_access_url` são exatamente isso — produz sessão sem marcador, que este default lê
como **identidade forte**. O portão que existe para impedir "quem só conhece o número cadastra
passkey na conta de outra pessoa" (`auth.py:692-695`, `:717`, `:745`) fica aberto por omissão.

É a versão exata do princípio do item 18 do próprio `fallbacks-perigosos-go-live.md`: o default
de um campo de segurança tem que ser o valor restritivo, senão a omissão vira política.

**Correção:** default `IDENTITY_NUMBER`, e os três caminhos que de fato provam identidade passam
a **escrever** `IDENTITY_DEVICE` explicitamente
(`packages/doorman/.../services/verification.py:317`, `shop/services/auth.py:201`,
`storefront/api/auth.py:816`). Aí "sem marcador" volta a significar "não sabemos", que é a
verdade.

---

### P1-4 — O backup transacional exporta o PII de todo cliente, contra a promessa do próprio módulo

**CONFIRMADO** · `shopman/backstage/api/backup.py:51-66` +
`shopman/shop/backup/transactional.py:31-42` + `shopman/shop/backup/resources.py:352-354`

`resources.py:352-354` afirma: *"guestman — só a configuração (clientes são PII: LGPD, ficam no
backup do banco)"*. Verdade para a tabela `guestman.Customer`. Mas
`OrderSnapshotResource.Meta.fields` (`transactional.py:36-41`) inclui **`data`** — e
`docs/reference/data-schemas.md:72-74` documenta que `Order.data` carrega
`{"customer": {"name", "phone", "notes"}, "delivery_address": …, "delivery_address_structured": {…, latitude, longitude, place_id}}`.

**Cenário concreto:** `GET /api/v1/backstage/backup/?with_transactional=1` devolve **um XLSX com
nome, telefone, endereço e coordenadas de todo cliente que já comprou**. Uma requisição. Sem
step-up, sem linha de auditoria, sem rate limit, por GET.

Atenuante: `backstage.export_backup` não é concedida por `setup_groups` (grep sem resultado),
então hoje só superusuário a tem. **Mas** o P0-2 produz superusuário a partir da Gerente, e a
docstring do próprio endpoint (`backup.py:9-11`) diz que a permissão é "menos que ser
superusuário" — ou seja, ela existe para ser delegada.

**Correção:** remover `data` do `OrderSnapshotResource` (ou reduzi-lo a um subconjunto sem PII);
exigir step-up recente; gravar linha de auditoria com quem baixou, quando, e com qual escopo.

---

### P1-5 — 500 não autenticado em todo webhook por token: `compare_digest` com string não-ASCII

**CONFIRMADO** (agente de webhooks, com prova no interpretador do repo) ·
`shopman/shop/webhooks/efi.py:340`, `ifood.py:228`, `machine.py:152`,
`packages/doorman/shopman/doorman/views/access_link.py:78`,
`packages/guestman/shopman/guestman/gates.py:254`, `shopman/storefront/api/auth.py:446`

`hmac.compare_digest` sobre `str` levanta `TypeError` quando qualquer lado tem caractere
não-ASCII. O token vem de `request.query_params.get("token")` — atacante-controlado. `TypeError`
não é exceção do DRF, e `shopman/shop/api_errors.py:57` devolve `None` para o que o handler
default não reconhece → propaga para o 500 do Django.

```
$ .venv/bin/python -c "import hmac; hmac.compare_digest('é','abc')"
TypeError: comparing strings with non-ASCII characters is not supported
```

**Cenário concreto:** `POST https://api.…/api/webhooks/efi/pix/?token=%C3%A9`, sem autenticação
nenhuma → HTTP 500 e um evento no Sentry por requisição. Repetido, queima a cota do Sentry e
afoga o canal de erro, de modo que uma falha **real** de webhook de pagamento fica
indistinguível do ruído. É a única coisa que um atacante sem token consegue fazer contra o
endpoint da EFI, e o que ela compra é cobertura — o que casa desconfortavelmente com o P0-1.
Vale também para `auth.py:446`, que é o caminho do OTP.

**Correção:** comparar bytes nos seis call sites —
`hmac.compare_digest(token.encode("utf-8","surrogatepass"), expected.encode("utf-8"))` — com
teste de regressão mandando `?token=é`.

---

### P1-6 — `/api/webhooks/ifood/events/` liga sozinho, assinado pelo *client secret* do OAuth

**CONFIRMADO** (agente de webhooks) · `config/settings.py:545-547` +
`shopman/shop/webhooks/ifood_events.py:45-60`

```python
"webhook_hmac_secret": os.environ.get(
    "IFOOD_WEBHOOK_HMAC_SECRET", os.environ.get("IFOOD_CLIENT_SECRET", "")
).strip(),
```

A docstring do módulo (`ifood_events.py:17-19`) diz que o endpoint fica **desregistrado** até
alguém confirmar o esquema de assinatura, *"a menos que um segredo esteja definido"* — e o
fallback define um automaticamente, porque `IFOOD_CLIENT_SECRET` é obrigatório para a integração
direta (`config/settings.py:526`).

**Cenário concreto:** quem tiver o `IFOOD_CLIENT_SECRET` — credencial *bearer* que viaja em corpo
de requisição de token, está na env da DO e é conhecida também do lado do portal iFood — calcula
`HMAC-SHA256(body, client_secret)` e POSTa um `CANCELLED` forjado para qualquer `orderId`.
`shopman/shop/services/ifood_events.py:141-151` roteia direto para `_process_cancellation`, que
muta um `Order` real. Reusar um segredo de autenticação como chave de assinatura significa que um
vazamento em qualquer um dos dois papéis compromete os dois.

**Correção:** apagar o fallback. Sem `IFOOD_WEBHOOK_HMAC_SECRET` explícito, o endpoint responde
404 — genuinamente inerte até a homologação confirmar o esquema.

---

### P1-7 — Telefone e e-mail de cliente em texto puro nos logs estruturados

**CONFIRMADO** (agente de config) ·
`packages/doorman/shopman/doorman/adapter.py:165-186` — `extra={"target": target}` nos quatro
ramos de envio de OTP (`target` é o E.164 completo), `:258` `extra={"email": email}`,
`packages/doorman/shopman/doorman/services/verification.py:217`
`extra={"target": target_value}`; também `shopman/shop/adapters/otp_sms_comtele.py:76`,
`otp_sms_twilio.py:69`, `notification_email.py:231,234`, `notification_whatsapp.py:107`,
`otp_manychat.py:61`.

Amplificador: `shopman/shop/logging.py:48-51` — o `JsonLogFormatter` copia **toda** chave
não-reservada de `record.__dict__` para a linha JSON. Sem denylist, sem redação. Todo envio de
OTP serializa o telefone.

**Cenário concreto:** a lista telefônica completa da base de clientes se acumula no log da DO,
retido, legível por quem tem console, e exportável por qualquer integração de log. Sob LGPD é
tratamento não-minimizado de dado pessoal por subprocessador, sem controle de retenção. O
contraste está no próprio repositório: `shopman/storefront/api/telemetry.py:34-42` redige
e-mail e telefone com regex antes de logar — a disciplina existe, só não foi aplicada ao caminho
de auth.

Também: `shopman/shop/webhooks/machine.py:70-71` loga o corpo cru do webhook do entregador em
INFO — payload não documentado que pode carregar posição do entregador e dados do pedido.

**Correção:** um helper de máscara (`+5543****1997`) em todo site de `target`/`recipient`/`email`,
e um filtro de redação no `JsonLogFormatter` por lista de chaves conhecidas. Pôr o dump cru do
`machine` atrás de uma flag `MACHINE_WEBHOOK_TRACE`.

---

### P1-8 — `LogSender` (que loga o OTP em claro) está configurado nos DOIS specs de deploy

**CONFIRMADO** (agente de config) · `.do/app.subdomains.yaml:128-129` e
`.do/app.alpha-subdomains.yaml:213-215` setam
`DOORMAN_MESSAGE_SENDER_CLASS=shopman.doorman.senders.LogSender`;
`packages/doorman/shopman/doorman/senders.py:47-49` —
`logger.info(f"Code for {target} via {method}: {code}")`.

Não está P0 porque hoje é inalcançável, e a razão foi traçada: `config/settings.py:685-688` define
`DELIVERY_CHAIN = "sms,email"` quando `DEBUG=false`, e `adapter.py:152` só cai no
`MESSAGE_SENDER_CLASS` quando a cadeia está **vazia**. O único caminho que usa
`MESSAGE_SENDER_CLASS` incondicionalmente é `adapter.py:220` (`send_access_link`), cujo único
chamador (`AccessLinkService.create_and_send`, `services/access_link.py:451`) não tem chamador no
projeto — código morto.

**Cenário concreto:** está a **uma edição de env var** da catástrofe. Alguém setando
`SHOPMAN_OTP_DELIVERY_CHAIN=""` para contornar uma queda da Comtele liga, em silêncio, "imprimir
o código de login de todo cliente no log de produção". Dado que a Comtele está devolvendo 500
(memória do projeto), essa edição é plausível — é literalmente a primeira coisa que alguém tenta.

**Correção:** remover `DOORMAN_MESSAGE_SENDER_CLASS` dos dois specs, e fazer
`LogSender`/`ConsoleSender` recusarem rodar quando `settings.DEBUG` for `False`.

---

## P2

### P2-1 — O `assert` de `ALLOWED_HOSTS` é mais fraco que o check homônimo

**CONFIRMADO** · `config/settings.py:1584` — `assert ALLOWED_HOSTS != ["*"]`, igualdade de lista
**exata**. `DJANGO_ALLOWED_HOSTS="*,api.boulangerie.com.br"` produz `["*", "api.…"]`, o assert
passa, e o Django aceita qualquer `Host` (basta `"*"` estar na lista). O check equivalente
`SHOPMAN_E002` (`shopman/shop/checks.py:78-91`) faz `"*" in hosts`, que é o certo — mas roda só
em `check --deploy`, no job de pre-deploy.

Importa porque `request.get_host()` é entrada de decisão de segurança em dois lugares:
`packages/doorman/shopman/doorman/utils.py:59` (`safe_redirect_url` adiciona o host da requisição
aos permitidos) e `shopman/shop/middleware.py:149` (`_is_operator_host` decide o `Domain` do
cookie).

**Correção:** alinhar o assert ao check — `assert "*" not in ALLOWED_HOSTS`.

### P2-2 — `OperatorUnlockView` / `PinChangeView` / `BadgeLostView` sem rate limit de view

**CONFIRMADO** · `shopman/backstage/api/operations.py:511`, `:687`, `:613` — nenhum decorador
`ratelimit`, ao contrário de `OperatorLoginView` (`:436-439`, com `ip 30/m` + `username 5/m`).

O único freio é o lockout do `PinCredential` (`PIN_MAX_ATTEMPTS=5`, `PIN_LOCKOUT_MINUTES=5`,
`packages/doorman/shopman/doorman/conf.py:35-37`), e ele é **por credencial**, não por
requisitante. A matemática do lockout em si está correta
(`packages/doorman/shopman/doorman/models/pin_credential.py:170-182`: depois do lockout,
`attempts` continua incrementando, então cada tentativa seguinte relocka → ~12 tentativas/hora
contra um espaço de 10⁴ — força bruta online inviável).

**Cenário concreto — negação de serviço, não invasão:** quem tenha o cookie de estação (ou a
máquina do balcão por um minuto) enumera os `operator_id` por `OperatorEligibleView` (`:497`,
gate só de estação) e erra cinco PINs de cada conta. **Todos os operadores ficam bloqueados**;
repetido a cada 5 minutos, a loja não abre. O gerente também é uma conta com PIN, então não há
quem destrave pelo balcão.

**Correção:** `ratelimit(key="ip", …)` nos três (depois de resolver o P0-3, senão o limite é
global e inútil), e um `OperatorAlert` quando N contas entram em lockout na mesma janela.

### P2-3 — `AdminTwoFactorMiddleware` acena para o request passar quando a URL não resolve

**CONFIRMADO, ainda real** (item 13 de `fallbacks-perigosos-go-live.md`) ·
`shopman/backstage/middleware_2fa.py:28-29` e `:44-45`

```python
except NoReverseMatch:
    return self.get_response(request)   # :29  → passa
except NoReverseMatch:
    return False                        # :45  → "não precisa verificar"
```

Se `admin_2fa_verify` for renomeada, desregistrada, ou o URLconf falhar ao importar, o portão de
2FA vira no-op e todo `/admin/` abre para qualquer sessão staff. Um middleware de segurança que
não acha a própria view de verificação deve dar 500, não deixar passar.

Agrava-se com `SHOPMAN_ADMIN_REQUIRE_2FA` nascendo `False`: hoje o 2FA está desligado, então o
P0-2 chega ao Admin sem nem tocar neste caminho.

**Correção:** `raise` (500) nos dois `except`.

### P2-4 — O BFF desarma o CSRF do Django; sobra só o `SameSite=Lax`

**CONFIRMADO** (os dois agentes) · `surfaces/operator-kit/server/utils/djangoProxy.ts:97-112` e
`surfaces/storefront-nuxt/server/utils/djangoProxy.ts:108-123`

Para método não-seguro o proxy sobrescreve `Origin`/`Referer` com a origem do Django e deriva o
`X-CSRFToken` **do próprio cookie que está repassando** — header e cookie sempre batem. Sem
token, faz bootstrap contra `/admin/login/`. A checagem CSRF do Django passa
incondicionalmente para tudo que vem por BFF.

É tradeoff documentado (`config/settings.py:110-117`: *"a defesa CSRF real contra requests
cross-site é o SameSite=Lax destes cookies. NUNCA mudar para 'None'"*). Fica aqui porque é de
camada única, e porque o P1-1 amplia o raio: qualquer foothold **same-site** (e todo
`*.boulangerie.com.br` é same-site para efeito de cookie) herda acesso CSRF-abençoado a todo path
do Django.

**Correção:** manter o tradeoff, mas restaurar o double-submit sem custo para os apps (eles já
têm o token): rejeitar método não-seguro quando o cliente **não** apresentar `X-CSRFToken`, em
vez de sintetizá-lo do cookie. E fixar `SESSION_COOKIE_SAMESITE == "Lax"` num teste.

### P2-5 — Cookie de sessão do cliente só fica host-only por causa de um `.filter()` no TypeScript

**CONFIRMADO** · `shopman/shop/middleware.py:135-154` +
`surfaces/storefront-nuxt/server/utils/djangoProxy.ts:43-54` +
`.do/app.alpha-subdomains.yaml:161-172`

`OperatorSessionDomainMiddleware` reescreve `Domain=.boulangerie.com.br` em `sessionid` e
`csrftoken` para **toda** resposta servida em `api.boulangerie.com.br` — e as nove superfícies,
storefront incluído, proxiam para esse mesmo host. O que mantém a sessão do cliente host-only é o
BFF da loja tirar o `Domain=` de cada `Set-Cookie` relayado (`storefrontSetCookieHeader`).

A separação física entre o pote de cookies do cliente e o do operador — que a docstring do
middleware apresenta como isolamento — é, no vivo, um `.filter()` em Nitro. Qualquer caminho de
cliente que não passe pelo BFF entrega ao cliente um cookie de sessão válido em `gestor.`,
`pdv.`, `admin.`.

Não é escalada por si (`_operador` exige `is_staff`), mas é o cookie do cliente trafegando para o
host do Admin, e a defesa mora do lado errado da fronteira.

**Correção:** `_is_operator_host` deveria distinguir a **audiência** da requisição, não só o
host — por exemplo aplicar o `Domain` só quando o path é `/api/v1/backstage/` ou `/admin/`.

### P2-6 — Zona `.boulangerie.com.br` inteira compartilha uma sessão de operador

**CONFIRMADO** (agente de config) · `config/settings.py:1305` + `shopman/shop/middleware.py:154`
(`host == bare or host.endswith("." + bare)`). Dez subdomínios (`api.`, `admin.`, `gestor.`,
`kds.`, `pdv.`, `prod.`, `compras.`, `mkt.`, `central.`, `bi.`) sob um cookie só. Um XSS ou um
subdomínio tomado em qualquer ponto da zona rende a sessão do operador — que alcança gaveta,
devolução e reset de PIN (P0-2).

Tradeoff aceito de SSO, mas pede higiene de DNS estrita (nada de CNAME pendurado) e, para as
ações de dinheiro, valeria um token `__Host-` por superfície.

### P2-7 — `USE_X_FORWARDED_HOST = True` incondicional fora de DEBUG

**CONFIRMADO** (agente de config) · `config/settings.py:119-125`. `request.get_host()` é entrada
de decisão em `shopman/shop/middleware.py:149`. Limitado hoje por
`DJANGO_ALLOWED_HOSTS='api.boulangerie.com.br,admin.boulangerie.com.br'`
(`.do/app.alpha-subdomains.yaml:133-135`), que o Django valida — o conjunto alcançável são esses
dois. Impacto pequeno hoje, acoplamento frágil. **Correção:** env própria, default desligado.

### P2-8 — `SHOPMAN_REQUIRE_ACTIVE_OPERATOR=true` no spec vivo, e o código não lê a env

**CONFIRMADO** · `.do/app.alpha-subdomains.yaml:173` define a flag; grep em `**/*.py` e `**/*.ts`
não encontra **nenhuma** leitura. Resíduo da "Opção C" que a unificação de identidade aposentou
(`shopman/backstage/api/permissions.py:7-27`).

Inofensiva em runtime — mas é um controle de segurança fantasma no spec: quem auditar a
configuração vai ler `true` e acreditar que um portão está ligado. **Correção:** remover a chave,
ou apontar num comentário para a decisão que a aposentou.

### P2-9 — Ilha JSON do menuboard pode ser quebrada

**CONFIRMADO** (agente de config) · `shopman/shop/templates/menuboard/board.html:135` —
`<script id="menuboard-initial" type="application/json">{{ initial|safe }}</script>`, alimentado
por `shopman/shop/views/menuboard.py:46` (`json.dumps`). `json.dumps` não escapa `<`, `/`,
`U+2028`, `U+2029`: um nome de produto com `</script><script>…` termina o bloco e executa. O
conteúdo é autoral de staff e o menuboard está gateado a staff/display confiável
(`shopman/shop/menuboard_access.py:53-66`), então é insider/segunda ordem — mas o CSP
(`config/settings.py:1544-1551`) permite `'unsafe-eval'` e não usa nonce, então o script roda.
**Correção:** `django.utils.html.json_script`.

### P2-10 — SVG aceito como logo da loja, sem sanitização

**CONFIRMADO** (agente de config) · `shopman/shop/models/shop.py:14` inclui `.svg` na allowlist;
`validate_logo` (`:18-25`) confere **só extensão e tamanho**. Latente e não vivo: `config/urls.py:144-145`
serve `MEDIA_URL` apenas sob `DEBUG`, e o WhiteNoise serve só `STATIC_ROOT`. Vira XSS armazenado
no dia em que media ganhar backend/CDN na mesma origem. **Correção:** tirar `.svg`, ou sanitizar
no save, ou servir media de outra origem.

### P2-11 — `RequestCodeView` é a única view de auth sem `csrf_protect`

**CONFIRMADO** · `shopman/storefront/api/auth.py:461-466`. As irmãs
(`AccessLinkExchangeView:203`, `DeviceCheckView:515`, `VerifyCodeView:549`,
`PasskeyLoginView:789`) têm `@method_decorator(csrf_protect, …)`; esta não. Com
`authentication_classes = []` o DRF já aplica `csrf_exempt` à view inteira, então não há
checagem nenhuma.

Sendo honesto sobre o impacto: **é quase irrelevante**. O endpoint não exige sessão, então o
atacante chama por `curl`; o CSRF não protegeria nada que ele já não pudesse fazer. Reporto pela
inconsistência — uma exceção não declarada num conjunto uniforme convida a próxima — e porque
`FormParser` está ativo (o DRF não sobrescreve `DEFAULT_PARSER_CLASSES`), o que torna possível um
`<form>` cross-site sem preflight. **Correção:** aplicar por uniformidade, ou escrever na
docstring por que esta não tem.

### P2-12 — `TrustDeviceView` sem CSRF e sem rate limit

**CONFIRMADO** · `shopman/storefront/api/auth.py:606-630`. Sem `csrf_protect`, sem `ratelimit`, e
`authentication_classes = []`. Exige `request.customer`, e com `SameSite=Lax` um POST cross-site
não carrega o cookie. Impacto prático baixo; a correção é a mesma linha das irmãs.

### P2-13 — `StockAlertSubscribeView` grava telefone de terceiro sem prova de posse

**CONFIRMADO** · `shopman/storefront/api/availability.py:86-153`. Anônimo, `10/m` (global, por
P0-3). Aceita `phone` no corpo e registra assinatura que, quando o produto voltar, dispara
WhatsApp/SMS **para aquele número**.

**Cenário:** cadastrar o número de uma vítima em vários SKUs de giro alto e deixar a loja mandar
mensagem por conta própria — bombardeio por procuração, queimando crédito de mensagem da Nelson.
E é dado pessoal gravado sem consentimento verificável (LGPD). **Correção:** para anônimo,
confirmar posse pelo OTP que já existe, ou limitar a 1 assinatura ativa por telefone não
verificado.

### P2-14 — `KDSCustomerStatusView` é público e publica refs de pedido em tempo real

**CONFIRMADO** · `shopman/backstage/api/kds.py:214-226`, `permission_classes = []`, rota
`kds/pickup/` (`shopman/backstage/api/urls.py:187`).

A projeção é deliberadamente sem PII (`shopman/backstage/projections/kds.py:246-306` — sem nome,
telefone, total ou endereço; comanda pré-commit vira código opaco justamente porque
`tab_display` pode ser nome de cliente), o que é bom trabalho. Mas publica na internet a lista
viva de `Order.ref` e o volume da loja. E o `ref` é curto: `generate_order_ref`
(`packages/orderman/shopman/orderman/ids.py:45-68`) produz `{CANAL}-{YYMMDD}-{L##}` — **2.400
combinações por canal por dia**.

Nenhum endpoint que li aceita `ref` sem escopo, então isso hoje não vira acesso. Fica como "não
deixe nascer o primeiro endpoint que confie só no ref". **Correção:** exigir `IsTrustedStation`,
como o quadro de menu já faz — o painel fica numa TV da loja, não precisa ser público.

### P2-15 — Endpoints de webhook herdam o throttle anônimo de 120/min

**CONFIRMADO** (agente de webhooks) · `config/settings.py:827,844-849`; nenhum
`throttle_classes` sob `shopman/shop/webhooks/`. Uma redistribuição legítima da EFI ou um backlog
do Stripe vindo de um IP só toma 429 depois de 120/min. Autossanável (a EFI só para em 2xx), mas
o 429 fica indistinguível do abuso que ele deveria conter. **Correção:** `throttle_classes = []`
nas cinco views (já autenticadas por segredo) ou escopo próprio.

### P2-16 — `AttributeError` → 500 em corpo JSON não-objeto (pós-auth)

**CONFIRMADO** (agente de webhooks) · `shopman/shop/webhooks/efi.py:168` (`request.data.get(...)`
com `request.data` podendo ser `list`/`str`) e `shopman/shop/services/ifood_events.py:130-131`
(elementos da lista não validados como dict). `ifood.py:77-84` faz certo — é o contraste que
mostra a correção.

### P2-17 — Replay aberto no webhook ManyChat quando o payload não traz `id`

**CONFIRMADO** (agente de webhooks) ·
`packages/guestman/shopman/guestman/contrib/manychat/views.py:68-74` — `if nonce:` (sem nonce,
sem proteção), e a view nunca passa `timestamp=`, então a janela de 300s em
`packages/guestman/shopman/guestman/gates.py:261-268` é código morto neste caminho. Um corpo
assinado capturado vale para sempre e re-executa `sync_subscriber`, que reescreve
`CommunicationConsent` — "reafirmar um opt-in que o cliente acabou de revogar" é o desfecho real.

### P2-18 — `DEBUG=True` em produção desliga todos os checks e abre dois bypasses de auth

**CONFIRMADO** (agente de webhooks) · praticamente todo check em `shopman/shop/checks.py` começa
com `if settings.DEBUG: return []` (`:64, 80, 96, 211, 259, 281, 307, 336, 384, 407, 616, 638, 717`),
e **não existe** check que reprove `DEBUG and is_production()`. Enquanto isso `DEBUG` é o único
portão de dois ramos que aceitam sem autenticação:
`packages/guestman/.../manychat/views.py:52-55` (`allow_unsigned=bool(settings.DEBUG)`) e
`packages/doorman/.../views/access_link.py:66-69` (sem `ACCESS_LINK_API_KEY` + `DEBUG` ⇒ o
endpoint cunha login para qualquer cliente resolvível por `whatsapp_id`/`email`).

Atenuante: os asserts de `config/settings.py:1580-1586` só rodam sob `not DEBUG`, então
`DJANGO_DEBUG=true` também desligaria as travas de `SECRET_KEY`/`ALLOWED_HOSTS`. Uma env errada
abre tudo de uma vez. **Correção:** um check que levanta `Error` quando
`settings.DEBUG and is_production()`, e reordenar os demais para chavear por `is_production()`.

### P2-19 — `PIN_HMAC_KEY` e `OTP_HMAC_KEY` não são usados: uma chave é a raiz de tudo

**CONFIRMADO** (agente de config) · `packages/doorman/shopman/doorman/conf.py:38`
(`PIN_HMAC_KEY: str = ""` → cai em `SECRET_KEY`), idem `OTP_HMAC_KEY`
(`models/verification_code.py:20`). O `DOORMAN` em `config/settings.py:293-315` não define
nenhum dos dois.

Consequência: PIN, crachá, OTP, access link, device trust, sessão, CSRF e assinatura de
comprovante de caixa (`shopman/backstage/services/receipt_verify.py:42,63`) derivam todos da
mesma chave. Rotacionar `SECRET_KEY` depois de um incidente invalida **tudo isso de uma vez** —
inclusive todo QR de comprovante já emitido (`receipt_verify.py:58-63` reconhece e depende de
`SECRET_KEY_FALLBACKS`). E o PIN é HMAC **sem sal** sobre 10⁴: PINs iguais entre operadores
produzem digests iguais, visíveis no banco.

**Correção:** setar `PIN_HMAC_KEY` e `OTP_HMAC_KEY` como segredos independentes (o suporte já
existe), para desacoplar as rotações; e considerar sal por credencial no PIN.

### P2-20 — `ip-api.com` em HTTP puro, com o IP do cliente indo para terceiro

**CONFIRMADO** (agente de config) · `shopman/shop/services/devices.py:33` —
`url = f"http://ip-api.com/json/{ip}?fields=..."`, com `ip` vindo do `X-Forwarded-For`. **Não é
SSRF** (a autoridade da URL termina no primeiro `/`, e `urllib` recusa caractere de controle) —
mas é (a) HTTP em claro e (b) o IP do cliente enviado a um terceiro a cada carga da tela de
segurança da conta. **Correção:** `https://`, validar com `ipaddress.ip_address()` antes de
interpolar, e considerar remover a chamada.

### P2-21 — Assimetrias e buffers no BFF

**CONFIRMADO** (agente de BFF):
- `surfaces/operator-kit/server/utils/djangoProxy.ts:139-143` devolve o corpo do upstream cru
  para qualquer status e faz `appendResponseHeader` em `content-type`; o BFF da loja faz o
  oposto de propósito (`storefront/.../djangoProxy.ts:17-19,150-155`, troca HTML de erro por
  `{detail}`). Com `DJANGO_DEBUG=1` num upstream de operador, o traceback completo vai para o
  navegador. Usar `setResponseHeader` e portar `shouldSanitizeHtmlError`.
- `storefront/.../djangoProxy.ts:129-134` não passa `redirect: "manual"` (o de operador passa,
  `:116-122`): o BFF da loja segue redirect do upstream server-side. Não é SSRF credenciado
  (o fetch tira cookie em redirect cross-origin) e não achei view com `Location` influenciável.
- `readRawBody(event, false)` sem limite nos dois (`operator-kit:114`, `storefront:125-127`), em
  instâncias de 0,5 GB: um POST grande é bufferizado inteiro no Nitro antes de o
  `DATA_UPLOAD_MAX_MEMORY_SIZE` do Django ter chance.

### P2-22 — Docstring do crachá afirma 96 bits; o código emite 48

**CONFIRMADO** · `packages/doorman/shopman/doorman/models/pin_credential.py:222`
(`BADGE_BYTES = 6` → 48 bits, com a razão de impressão bem documentada em `:211-221`) contra
`:241` — *"a 96-bit token is not brute-forceable, so this is not coupled to the PIN lockout"*.
48 bits seguem inatacáveis online, então a conclusão vale; o número não. Uma justificativa de
segurança que cita número errado é a que ninguém revisa quando o número muda de novo.

### P2-23 — `test_webhook.py` dá cobertura falsa

**CONFIRMADO** (agente de webhooks) · `shopman/shop/tests/test_webhook.py:13` — arquivo inteiro
com `pytest.mark.skip`, mirando `/webhook/manychat/` (rota inexistente), afirmando `403` onde os
webhooks vivos devolvem `401`, e usando `SHOPMAN_WEBHOOK`, setting que não existe em lugar
nenhum. Um arquivo chamado `test_webhook.py` com um `test_invalid_auth_token` é exatamente o que
alguém grepa antes de concluir "auth de webhook está testada". Apagar.

---

## Suspeitas / precisa de acompanhamento

1. **O job de pre-deploy e o serviço web resolvem a mesma env?** 19 dos 23 checks de
   `shopman/shop/checks.py` são `@register(deploy=True)`, e rodam só no job
   (`.do/app.subdomains.yaml:370`, `.do/app.alpha-subdomains.yaml:830`:
   `check --deploy && migrate && setup_groups`) — que é um componente separado, com bloco de env
   próprio. Se um segredo estiver escopado ao serviço e não ao job (modo de falha já registrado
   em `fallbacks-perigosos-go-live.md:18`), o job passa e o web sobe mal configurado. **E006**
   (cache Redis compartilhado — o que faz todo `ratelimit` ser global e não por worker) é um
   deles. Uma conferência de um comando.
2. **Profundidade real da cadeia XFF.** `DOORMAN_TRUSTED_PROXY_DEPTH=1` e o comentário em
   `config/settings.py:295-300` admite que o rightmost na DO App Platform pode ser um nó de
   ingress que rotaciona. **A correção do P0-3 depende dessa medição** — errar a profundidade
   para o outro lado transforma o DoS num IP spoofável. Medir com `SHOPMAN_LOG_CLIENT_IP`.
3. **`EFI_WEBHOOK_IP_ALLOWLIST` no spec vivo.** Vazia por default
   (`config/settings.py:1206-1210`); combinada com o P0-1, o token na query é ponto único de
   falha sem segunda camada. Conferir se o spec vivo (não versionado) a define.
4. **`ACCESS_LINK_API_KEY` como bearer estático.** `AccessLinkCreateView` cunha sessão de login
   para **qualquer** cliente resolvível por `whatsapp_id`/`email`/`customer_id`
   (`packages/doorman/.../views/access_link.py:88-159`), com chave estática que vive na
   configuração de um SaaS de terceiro (ManyChat). Sem rotação, sem allowlist de IP, sem
   auditoria por cliente, sem rate limit por alvo. Não é bug — é a superfície mais consequente do
   sistema apoiada num único segredo compartilhado. Merece decisão explícita antes do go-live.
5. **Vazamento do token da EFI fora da aplicação.** O P0-1 cobre o stdout do daphne. O que não dá
   para verificar deste repo: se o edge da DO grava access log próprio com query string, e o que
   a EFI retém do lado dela. Tratar rotação como obrigatória de qualquer forma.
6. **`Order.ref` em endpoints futuros.** 2.400 combinações por canal/dia
   (`packages/orderman/shopman/orderman/ids.py:23-27`). Todo endpoint que li hoje escopa o
   lookup; a suspeita é sobre o próximo. Vale um teste de arquitetura que reprove view com
   parâmetro `ref` que não chame `get_accessible_order`.
7. **Canais `stock-`/`fomo-` do SSE** caem no `DefaultChannelManager`
   (`shopman/shop/eventstream.py:17-20,30`), que libera. Intencional ("keeping public stock
   updates"), mas expõe posição de estoque em tempo real na internet. Decisão de negócio.
8. **`Location` verbatim do BFF de operador** (`operator-kit/.../djangoProxy.ts:136-137`) — não
   achei view Django com `Location` influenciável pelo cliente, mas não enumerei todas.

---

## Verificado como seguro

Isto vale tanto quanto os achados: são os lugares onde já se olhou com olho adversarial.

**Autorização do backstage — sólida.** Varredura AST de **todas** as 100 views de
`shopman/backstage/api/`: toda view mutante declara `required_permission` (direto ou herdado de
`_CatalogBase`/`_BIBase`/`_CampaignBase`/`_FeedBase`/`_OrderActionBase`/`_ProductionActionBase`),
e **nenhuma subclasse sobrescreve `permission_classes` para afrouxar**. A única sobrescrita de
`required_permission` é `BICashView` (`bi.py:95`), que *aperta*:
`("backstage.view_bi", CASH_AUDIT_PERMISSION)`. As sem `required_permission` são deliberadas e
escopadas: `SignInListView` (`sign_ins.py:67` — `filter(user=request.user)` e nada mais, sem ramo
para staff privilegiado), `NotificationListView/ReadView/ActionView` (`_own(request)` em todas, e
`NotificationActionView:159` confere `has_perm("shop.manage_campaigns")` inline),
`AlertListView/AckView` (predicado `CanViewOperatorAlerts`), a antessala de PIN, e `HubView`.
**Não encontrei um só endpoint mutante do backstage sem avaliação de permissão contra quem opera.**

**`HasBackstagePermission` avalia contra quem opera.**
`shopman/backstage/api/permissions.py:151-161` — uma identidade só (`request.user`), sem o segundo
sujeito que abriu o buraco de 20/08. `_operador` (`:97-107`) exige `is_staff`, então **sessão de
cliente não alcança backstage** por construção.

**Estação autônoma recusa superusuário.** `shopman/backstage/station_trust.py:152-157`, com
`logger.error`. É o modelo que falta ao caminho do PIN (P0-2).

**Autorização de pedido do cliente.** `shopman/shop/services/customer_orders.py:37-47, 99-151` —
staff, ou ref concedido à sessão (`grant_order_access`, teto de 20 refs, `:57-70`), ou identidade
do cliente batendo com o `Order.data` selado. `Http404` **uniforme** para inexistente e para
negado (`:47`) → sem oráculo de enumeração. `OrderTrackingView`, `OrderConversationView` e as
cinco mutações de tracking passam todas por `get_accessible_order`.

**IDOR de conta — todos escopados.** `AddressDetailView` (`account.py:586-651`) usa
`account_service.get_address(customer.ref, pk)`, que devolve `None` para PK de outro cliente →
404 uniforme, com o raciocínio escrito no comentário. `AccountDeviceDetailView` (`:844`),
`AccountPasskeyDetailView` (`:1087`), `FavoriteDetailView` (`:1010`) idem, por
`customer_info.uuid`. `AccountExportView` (`:868-885`) exige `get_authenticated_customer` **e**
`_step_up_is_fresh` (OTP recente) antes do JSON com PII completo.

**A projeção de tracking não carrega PII.** `shopman/storefront/presentation/order_tracking.py` —
grep por phone/cpf/email/address devolve só o endereço **da loja** (`:132-135`, `:1216`).

**Autorização do SSE.** `shopman/shop/eventstream.py:22-95` — `user-<id>` só o dono (`:71-76`),
`order-<ref>` dono ou staff (`:78-95`), `backstage-<kind>` exige a mesma permissão da tela que o
canal alimenta, e **`kind` desconhecido é NEGADO** (`:58-60`), então canal novo nasce inacessível
em vez de aberto. `order_events_view` (`tracking.py:212-236`) faz o mesmo gate antes, com 404
uniforme, porque `django_eventstream` reportaria a recusa em banda sobre HTTP 200. Os nomes de
canal nunca são livremente escolhidos pelo cliente (`operator-kit/.../eventStream.ts:24-36`; os
dois segmentos vindos do cliente passam por `encodeURIComponent`).

**Criptografia do OTP.** `packages/doorman/.../models/verification_code.py:26,32` —
`secrets.randbelow(1_000_000)`, digest HMAC-SHA256, `hmac.compare_digest` (`:49`).
`_get_valid_code` (`services/verification.py:397-417`) pega **só o mais recente**, com
`select_for_update`; `request_code` invalida os anteriores (`:156-160`); `verify_for_login` é
`@transaction.atomic`. Tentativas com `F()+1` (`verification_code.py:196`). Aritmética: 5
códigos/15min × 5 tentativas = 25 palpites/15min por telefone contra 10⁶.

**Uso único do access link é à prova de corrida.** `AccessLinkService.exchange`
(`packages/doorman/.../services/access_link.py:178-288`) é `@transaction.atomic` com
`get_by_token(..., for_update=True)` (`:200`) antes do `mark_used` (`:236`). Token é
`secrets.token_urlsafe(32)` = 256 bits (`models/access_link.py:183`), guardado só como digest.

**Device trust está bem amarrado.** `DeviceTrustService.check`
(`packages/doorman/.../services/device_trust.py:66-94`) confere o par
`(subject_type, subject_id)` — cookie de um sujeito não abre outro. Cookie `HttpOnly`, `Secure`
(`USE_HTTPS = not DEBUG`), `SameSite=Lax` e **sem `Domain=`** (`:129-136`): host-only.

**`_debug_otp_allowed` falha fechado.** `shopman/storefront/api/auth.py:431-446` — três camadas
independentes: `DEBUG`, a flag explícita (`config/settings.py:92`, nasce `False` sem herdar de
nada), e o segredo `SHOPMAN_DEBUG_OTP_TOKEN` comparado com `secrets.compare_digest` (`:446`).
Sem token configurado e fora de `DEBUG`, **recusa** (`:441`). O item 3 do documento de fallbacks
está de fato fechado, e o `SHOPMAN_EXPOSE_DEBUG_OTP='true'` do alpha é inerte sem o token.

**`SECRET_KEY` e `ALLOWED_HOSTS` NÃO sobem com o default.** `config/settings.py:1580-1586` — dois
`assert` no import do settings, portanto no boot de todo worker, e nem `Dockerfile` nem os specs
usam `-O`/`PYTHONOPTIMIZE`. Contraria o Tier 4 do `fallbacks-perigosos-go-live.md`; ver a nota no
topo deste documento.

**`OrderPaymentMockConfirmView` tem porta dupla.** `shopman/storefront/api/payment.py:69-118` —
`mock_payment_enabled()` (ambiente) **e** `mock_payment_enabled(method)` (o método daquele
pedido, `:91-93`), ambos `Http404`, mais `get_accessible_order` e mutação idempotente.

**Redirects.** `_access_link_redirect` (`auth.py:157-179`) deriva o destino do **token**, nunca de
query param, e revalida `startswith("/") and not startswith("//")`. `BrowserHandoffView` (`:669`)
idem. `_safe_next` do 2FA (`shopman/backstage/views/two_factor.py:19-24`) exige prefixo `/admin/`
— `//evil.com` não passa. `shopman/storefront/intents/auth.py:174-175` idem.
`packages/doorman/.../utils.py:61` usa `url_has_allowed_host_and_scheme`.

**TOTP do Admin é throttled** por `django_otp` (`verify_is_allowed()` em
`otp_totp/models.py:112-114`) — não há força bruta de 6 dígitos. E o ramo `device is None` não
deixa passar: renderiza e para.

**Zero superfície de SQL injection.** `.raw(`, `.extra(`, `RawSQL`, `cursor.execute(` em todo
`shopman/` e `packages/` devolve exatamente dois hits, ambos `cursor.execute("SELECT 1")` de
health probe (`shopman/shop/views/health.py:36`,
`packages/doorman/shopman/doorman/views/health.py:20`). Nenhum SQL montado por string.

**Zero CORS.** Não há `django-cors-headers` em `INSTALLED_APPS` (`config/settings.py:164-239`),
nenhuma setting de CORS, nenhum `Access-Control-*` emitido por Python ou TypeScript. A combinação
catastrófica `CORS_ALLOW_ALL_ORIGINS` + credenciais é estruturalmente impossível — a arquitetura
de BFF dispensa CORS.

**Nenhuma injeção de template em Python.** Os 32 `mark_safe` concatenam literais ou valores já
`escape()`-ados (`shopman/shop/admin/widgets.py:33-35`,
`packages/orderman/shopman/orderman/admin_widgets.py:25-26`); todo `format_html` usa a forma
parametrizada. Os únicos três `|safe` em template são o menuboard (P2-9) e dois SVG gerados no
servidor.

**Nada de `eval`/`exec`/`pickle`/`yaml.load`.** O único `subprocess.run`
(`shopman/shop/services/dispatch_handoff.py:120`) usa argv fixo com `shutil.which` e pipe por
stdin — sem shell. Carregamento dinâmico de classe a partir do banco é allowlisted **duas** vezes:
`RuleConfig.clean()` (`shopman/shop/models/rules.py:19`) e independentemente no load
(`shopman/shop/rules/engine.py:141-150`, com comentário explicando que é defesa em profundidade
para o caso de a linha ter entrado por SQL cru).

**Geocode é exemplar.** `shopman/storefront/api/geocode.py:64-77` — `float()`, validação de
intervalo, `30/m`, chave do Maps nunca exposta. `shopman/shop/services/geocoding.py:135-141` monta
a URL com `urlencode` sobre base constante: sem SSRF.

**Telemetria é write-only e sanitizada.** `shopman/storefront/api/telemetry.py:28-67` — allowlist
de campos, truncagem por campo, query da URL descartada, e-mail e telefone redigidos, `30/m`.

**Assinatura do Stripe está correta.** Corpo cru lido antes do parse, assinatura obrigatória
(`webhooks/stripe.py:63-90`), `stripe.Webhook.construct_event` faz comparação constante **e**
tolerância de timestamp de 300s. Sem segredo, **recusa** (`:73-79`).

**Idempotência durável em todo caminho de dinheiro.** `shopman/shop/services/webhook_idempotency.py:79-108`
— `IdempotencyKey` do orderman com unique constraint, `select_for_update` e savepoint aninhado.
Chaves: Stripe `event.id`, EFI `endToEndId` com fallback `txid` (`efi.py:362-365`), iFood
`order_id`, Machine `(ride_ref, status)`.

**XFF da EFI usa o último hop** (`efi.py:347-359`), a única posição que o chamador não forja por
prepend.

**Nenhum `if not secret: accept`** em nenhum webhook — os seis falham fechados
(`efi.py:308-315`, `ifood.py:212-218`, `ifood_events.py:51-56`, `machine.py:139-145`,
`stripe.py:73-79`, `guestman/gates.py:234-239`, `access_link.py:66-68`).

**Corpo grande vira 400, não 500** — `DATA_UPLOAD_MAX_MEMORY_SIZE` não é sobrescrito, então o
default de 2,5 MB levanta `RequestDataTooBig` antes de qualquer código de webhook.

**Nenhum uso de `django.core.signing` / `TimestampSigner` / `salted_hmac`** em `shopman/`,
`packages/`, `config/`, e `SESSION_ENGINE` não é `signed_cookies` — então não há valor assinado
viajando para o cliente que uma `SECRET_KEY` conhecida tornasse forjável.

**Nenhum segredo em `runtimeConfig.public`.** Os nove `nuxt.config.ts` expõem só URLs base e
flags de UI; `djangoBaseUrl` é server-only. **Host do upstream não é cliente-controlável** — vem
só de `runtimeConfig`, e `resolveDjangoBaseUrl` recusa localhost em produção. **Nenhum cabeçalho
do cliente é repassado às cegas**; em particular `X-Shopman-Debug-Otp` **não** é encaminhável
pelo navegador. Nenhum `routeRules` cacheia resposta com cookie.

**Media não é servida em produção.** `config/urls.py:144-145` gateia
`static(MEDIA_URL, ...)` atrás de `if settings.DEBUG`.

**Perímetro da API.** `config/urls.py:104-134` — os ViewSets CRUD do kernel não estão montados,
com o raciocínio escrito e um teste de guarda (`shopman/shop/tests/test_api_perimeter.py`).

**DRF sem BasicAuth.** `config/settings.py:836-838` — só `SessionAuthentication`, com o
comentário nomeando a razão (abriria força bruta de senha staff sem lockout e contornaria o 2FA).
Default de permissão é `IsAuthenticated`; `AllowAny` é opt-in por view, e toda que rastreei
reconfere identidade no handler.

**Cabeçalhos de segurança e política de senha.** `SECURE_CONTENT_TYPE_NOSNIFF`,
`X_FRAME_OPTIONS = "DENY"`, `SECURE_REFERRER_POLICY` sempre ligados
(`config/settings.py:1521-1523`); `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/HSTS
1 ano + preload + subdomains sob `if not DEBUG` (`:1588-1593`); SameSite `Lax` explícito
(`:116-117`); `SESSION_COOKIE_HTTPONLY` nunca sobrescrito; os quatro validadores de senha com
`min_length: 10` (`:277-291`).

**Login de operador tem freio por username E por IP.** `shopman/backstage/api/operations.py:435-440`
— 5/min por username, 30/min por IP, ambos `block=False` com 429 amigável.

**Sentry configurado com privacidade.** `send_default_pii=False` mais `before_send` que tira a
query string de toda URL (`config/settings.py:1481-1508`), travado por
`shopman/shop/tests/test_sentry_query_scrubbing.py`. O raciocínio está certo — só precisa
alcançar o stdout (P0-1).
