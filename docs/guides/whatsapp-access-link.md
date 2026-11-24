# Login por WhatsApp via access link (ManyChat)

Guia de configuração do login por WhatsApp unificado no fluxo de **access link** do
doorman. Um fluxo só no ManyChat, um endpoint de geração, um exchange. SMS (Comtele)
segue como fallback. Substitui o antigo reverse-OTP (ver
[ACCESS-LINK-UNIFICATION-PLAN](../plans/completed/ACCESS-LINK-UNIFICATION-PLAN.md)).

## A ideia

Não precisamos de OTP. O caminho mais divulgado pode ser o mais simples: quem manda
`#menu` no WhatsApp recebe um **access link** seguro para entrar e ver o cardápio. Quando
o cliente vem do site com sacola/destino, o botão pré-preenche `#menu NB-XxXx`: o código
carrega **contexto** (a sacola anônima + o destino), não credencial. A identidade é o
**número que envia a mensagem** (zero-telefone); o código nunca autentica ninguém.

Quem não usa WhatsApp cai no **fallback SMS** (Comtele), o fluxo OTP clássico
(`RequestCodeView` + `DELIVERY_CHAIN`).

## Fluxo

```
1. Site → POST /api/v1/auth/whatsapp/start/         → { code: "NB-XxXx", deep_link, wa_number }
   (guarda {cart_session_key, next} sob o código, no cache, uso único, TTL 10 min)
2. Cliente toca "Abrir o WhatsApp" → wa.me abre `#menu NB-XxXx` → envia
3. ManyChat (Flow) → POST /api/auth/access/create/  (S2S, API key)
   body: { customer_id/subscriber, access_code: "<a mensagem inteira>", next: "/menu" }
   → o create extrai o NB-XxXx, resolve o contexto e dobra na metadata do token
   → responde { access_url: ".../a?t=<token>", has_context: true|false, access_flow, token, expires_at }
4. O create libera a aba de origem e devolve `access_url` ao ManyChat.
5. Cliente volta ao site → `POST /api/v1/auth/whatsapp/claim/`
   → loga a sessão + mantém a sacola e o destino naquele navegador.
6. O Shopman envia pelo ManyChat uma mensagem curta com botões nativos. O botão
   principal aponta para `access_url` e funciona como reserva. O segundo botão,
   quando existe, encerra um acesso não reconhecido. Nenhuma URL aparece no texto.
7. Se o cliente usar o botão principal: `/a?t=<token>` →
   `POST /api/v1/auth/access/` (exchange) → loga a sessão + adota a sacola
   (`cart_session_key`) + redireciona (`metadata.next`).
```

### A aba de origem entra sozinha (26/09/2026)

A queixa dos testadores que chegavam pelo site era a volta: "vai pro WhatsApp, envia uma
tal mensagem, depois sai do WhatsApp de novo por um link". O link abria no navegador
embutido do WhatsApp, e a aba onde a pessoa estava continuava em "Vamos entrar?". O
padrão dos benchmarks (OTPless, RFC 8628, o QR do WhatsApp Web) é outro: **o login
termina onde começou.**

```
1. /start guarda também a IMPRESSÃO DIGITAL da sessão que apertou o botão (sha256 da
   chave de sessão, nunca a chave) e o rótulo do dispositivo ("Safari / iPhone").
2. O create, ao consumir o NB-XxXx, cria um SEGUNDO access link (sem entrega) e o
   deixa esperando sob aquela impressão digital (`link_state.release_to_origin`).
   Só então cria o link da mensagem — a mensagem diz "você já entrou", e isso já é
   verdade quando ela sai.
3. A aba pergunta `POST /api/v1/auth/whatsapp/claim/` quando volta a ficar visível
   e, enquanto está na tela, com backoff de 4 s, 7 s e 15 s. Achou a liberação → troca
   o token pelo MESMO
   caminho do link (`exchange_access_token`) e entra, lembrando o dispositivo.
4. A mensagem (`access_link_site`) manda voltar ao site e oferece dois botões:
   `Entrar na loja`, como reserva, e `Não fui eu`, para `/encerrar-acesso#<ref>` →
   `POST /api/v1/auth/whatsapp/revoke/`: cancela a liberação pendente ou derruba a
   sessão e o dispositivo que ela abriu. A referência vale 24 h.
```

O código **não é credencial**: vazado, ele não abre nada em outro navegador, porque a
liberação mora sob a sessão de origem. O risco que sobra é o golpe da "mensagem
encomendada" (alguém convence a vítima a enviar a mensagem com o código DELE); a defesa
escolhida pelo dono é avisar e deixar derrubar, sem toque extra para quem é honesto.

### O botão de volta: celular e computador (23/10/2026, escada sem fricção)

Decisão do dono (`docs/plans/COORDENACAO-GO-LIVE.md` §6): a resposta do WhatsApp traz o
botão de volta, e ONDE a entrada acontece depende de onde o login começou
(`access.site_origin_is_phone`, pelo agente de usuário; desconhecido conta como celular).

```
CELULAR  /start não guarda origem (estado `site_return: "phone"`). A mensagem é a
         `access_link` com o botão "Voltar à loja" (o access link): a entrada acontece
         no navegador que o botão abrir e NUNCA é liberada para outra aba. Se for o
         mesmo navegador da aba que esperava, o `claim` dela percebe pelo cookie
         (sessão autenticada com identidade forte → `done`).
COMPUTADOR /start guarda a origem e o rótulo ("Chrome / Windows"). O create deixa a
         liberação esperando como antes, mas o `claim` só a entrega depois do toque no
         botão da mensagem, que NOMEIA o que libera: "Liberar o Chrome" (o WhatsApp
         corta rótulo de botão em 20 caracteres; o corpo diz "com o Chrome no
         Windows"). O botão abre `/liberar-acesso#<ref>` → `POST
         /api/v1/auth/whatsapp/release/`; a referência de liberar é separada da de
         encerrar. O "Não foi você?" continua na bolha de cima e derruba tudo.
```

O `/start` devolve `return_mode` (`message_button` | `release_this_tab`) e `return_button`
(o rótulo do botão), e a tela de entrada usa o mesmo nome nos passos e na espera
(`LOGIN_WA_STEPS`, `LOGIN_WA_WAITING`, `LOGIN_WA_WAITING_PHONE`, com `{button}`).

`#menu` digitado direto no WhatsApp não tem aba de origem e segue exatamente como antes.
O checkout e a tela de Segurança (`useWhatsAppConfirm`) usam a mesma volta: a página
onde a pessoa tocou se confirma sozinha.

## Endpoints

| Método | Rota | Auth | Uso |
|--------|------|------|-----|
| POST | `/api/v1/auth/whatsapp/start/` | pública (rate-limit 10/min) | Site: gera o código NB + deep link. Body opcional `{"next": "/checkout"}`; a sacola vem da sessão. |
| POST | `/api/auth/access/create/` | **API key S2S** | ManyChat: gera o access link. Aceita `access_code` (a mensagem inteira; o código é extraído). |
| POST | `/api/v1/auth/access/` | pública | Exchange do token → sessão logada + adoção de sacola + redirect. |
| POST | `/api/v1/auth/whatsapp/claim/` | pública (CSRF, 40/min) | A aba de origem entra (`status: done`), espera o toque em "Liberar o Chrome" da resposta, com a mensagem já recebida (`awaiting_release`, só no computador), ou segue esperando a mensagem (`pending`). |
| POST | `/api/v1/auth/whatsapp/release/` | pública (CSRF, 10/min) | "Liberar o Chrome": `{ref}` deixa a aba do computador entrar. |
| POST | `/api/v1/auth/whatsapp/revoke/` | pública (CSRF, 10/min) | "Não foi você?": `{ref}` desfaz a entrada liberada pela mensagem. |

O `create` autentica com a `DOORMAN_ACCESS_LINK_API_KEY` (header `Authorization: Bearer
<chave>` ou `X-Api-Key`). Fail-closed: sem chave, rejeita fora de DEBUG.

## Variáveis de ambiente

```env
# WhatsApp da loja (E.164 só dígitos). Vazio = usa Shop.phone; sem nenhum dos
# dois, /start responde 503 whatsapp_unavailable e a tela promove SMS/ajuda.
SHOPMAN_WHATSAPP_VERIFY_NUMBER=554333231997
# Mensagem pré-preenchida do botão (opcional; {shop} = nome da loja, {code} = NB-XxXx).
# ⚠️ Tem de conter uma palavra-chave do flow no ManyChat. Default abaixo.
SHOPMAN_WA_ACCESS_MESSAGE_TEMPLATE=Olá! Quero entrar no site da {shop} (ref. {code})

# Chave server-to-server do create. OBRIGATÓRIA fora de DEBUG.
DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>
# Base pública da loja Nuxt: onde o access_url aponta (.../a?t=<token>).
DOORMAN_ACCESS_LINK_ENTRY_URL=https://<loja>

# ManyChat (Flow + notificações outbound). Ver release-secrets-runbook.md
MANYCHAT_API_TOKEN=<token da API ManyChat>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC inbound>

# Fallback SMS (Comtele) — já plugado em DELIVERY_SENDERS['sms']
COMTELE_API_KEY=<api key Comtele>
COMTELE_ROUTE=<id da rota transacional>
```

O prefixo do código (`NB-`) e o TTL (10 min) são do doorman
(`DOORMAN.LINK_STATE_CODE_PREFIX` / `LINK_STATE_TTL_SECONDS`). O "Não foi você?" vale
24 h (`LINK_REVOKE_TTL_SECONDS`).

## Configuração do Flow no ManyChat (a parte "F3")

1. **Trigger** — um *Keyword* de WhatsApp, "A mensagem contém", apontando para a
   automação (no alpha: `Fluxo Login Cardápio`), com DUAS palavras:
   - `#menu` — a entrada orgânica de quem digita no WhatsApp;
   - `quero entrar no site` — a mensagem pronta do botão do site ("Olá! Quero entrar
     no site da Nelson Boulangerie (ref. NB-XxXx)"). Configurada em 26/09/2026.

   O trigger **não é a fronteira de segurança** — o Django é o portão (código no
   cache, single-use, TTL, rate-limit; a identidade é o número da Meta). Não crie um
   trigger "com sacola" e outro "sem sacola": o ManyChat não decide isso. Ele só manda
   a mensagem recebida; o backend responde `has_context`, e a automação condiciona a
   copy depois. Também não use `NB-` como gatilho: `NB-*` é payload técnico de contexto,
   não intenção do cliente. O fallback manual da loja copia a mensagem completa, nunca
   só o código.
2. **External Request** (Dev Tools, plano Pro):
   - Method: `POST`
   - URL: `https://api.<seu-domínio>/api/auth/access/create/`
   - Header: `Authorization: Bearer {{DOORMAN_ACCESS_LINK_API_KEY}}`
   - Body (JSON):
     ```json
     {
       "subscriber": {
         "id": "{{Subscriber ID}}",
         "whatsapp_id": "{{WhatsApp ID}}",
         "first_name": "{{First Name}}",
         "last_name": "{{Last Name}}"
       },
       "access_code": "{{Last Text Input}}",
       "next": "/menu"
     }
     ```
     Além de mandar `{{WhatsApp ID}}` no payload, crie um Custom User Field
     pesquisável no ManyChat (ex.: `shopman_whatsapp_id`) e grave nele o mesmo
     `{{WhatsApp ID}}`. Configure o ID desse campo em
     `MANYCHAT_WHATSAPP_ID_FIELD_ID`; notificações como "Me avise" usam esse
     espelho para descobrir o `subscriber_id` sem depender do campo sistêmico
     `phone`.

     Para templates aprovados de "Me avise"/fornada, o Shopman grava campos
     customizados antes de disparar o flow: `product_name`, `product_sku`,
     `product_image_url`, `available_qty`, `availability_phrase` e `action_url`.
     Como o botão do WhatsApp no ManyChat só aceita variável no final da URL, use
     `https://alpha.nelsonboulangerie.com.br/produto/{{product_sku}}` no CTA.
     No corpo do template, prefira `{{availability_phrase}}` a montar
     `{{available_qty}} unidades` dentro do ManyChat.

     Copy recomendada para o template aprovado:

     ```text
     Olha só: *{{product_name}}* acabou de sair do forno! {{availability_phrase}}
     Toque para garantir seu pedido.
     ```

     CTA recomendado: `Quero garantir`. Evite `Reserva para mim` enquanto o
     clique só abre a página do produto; reserva, no Shopman, acontece depois da
     ação de compra/checkout.

     `access_code` = a mensagem inteira que o cliente enviou. Selecione **Last Text
     Input** pelo seletor de variáveis do ManyChat; não digite um placeholder manual
     se ele não aparece naquele contexto. **Não precisa de regex no ManyChat** — o Django
     extrai o `NB-XxXx` do texto quando ele existe. Se a mensagem for só `#menu`, o
     backend trata como login orgânico e usa `next: "/menu"`; não marca sacola expirada.
     Se vier `NB-*`, o destino guardado no código ganha do fallback `/menu`.

     O backend também aceita o mesmo texto em `state_code`, `code`, `last_input_text`,
     `last_text_input`, `message` ou `text`, inclusive dentro de `metadata`,
     `custom_fields` ou `fields`. Isso existe para tolerar nomes diferentes no External
     Request; a regra continua a mesma: sem o texto/código `NB-*`, não há como recuperar
     a sacola anônima daquele browser.

     Se o Keyword Trigger não expuser o Last Text Input no External Request, use uma
     automação ponte via Default Reply/Last Text Input para capturar a mensagem e
     chamar o mesmo flow. Sem a mensagem inteira, o backend ainda consegue logar pelo
     WhatsApp, mas não consegue recuperar a sacola anônima do site.
3. **Resposta ao cliente**: não monte uma segunda mensagem no Flow. O sinal
   `access_link_created` entrega a resposta pela API SendContent do ManyChat, dentro
   da janela aberta pela mensagem que a pessoa acabou de enviar. A copy fica em
   `NotificationTemplate` e os botões ficam no adapter do Shopman:
   - com sacola: `Continuar pedido`;
   - sem sacola: `Entrar na loja`;
   - quando o login começou no site: envia primeiro um balão curto com
     `Encerrar acesso` e depois o balão principal;
   - cada balão contém somente um botão de URL, conforme o contrato real do
     WhatsApp na conta ManyChat;
   - se o ManyChat rejeitar explicitamente os botões, o Shopman tenta uma única vez
     em texto simples, com os links nomeados, e registra a degradação sem dados do
     cliente.

   O External Request ainda recebe `access_url`, `has_context`, `handoff_expired` e
   `access_flow` para diagnóstico. Não grave o token em campo persistente do contato
   e não envie outra mensagem no Flow. Isso evita duplicidade e mantém as credenciais
   fora do perfil do cliente.

   Ao tocar, a loja abre em `/a?t=<token>`, troca o token, loga e cai no destino
   (cardápio/checkout/conta) já com a sacola quando havia contexto. Se o código do site
   expirou, o link ainda entra, mas a loja avisa que a sacola não veio desta vez.

> Quando `access_url` volta preenchido, a mensagem já liberou a aba de origem e o link
> recebido no WhatsApp fica como reserva. Não há SSE; a aba consulta o `claim` com
> backoff e também permite a conferência manual.

## Continuar pelo WhatsApp: a sacola vai para a conversa (OC-16)

O mesmo código `NB-` leva a sacola da loja para a conversa com a Nice, e não para outro
navegador. A sacola oferece "Continuar pelo WhatsApp" só quando a ponte está ligada
(`SHOPMAN_CONCIERGE_ENABLED` e `CONCIERGE_TRANSFER_ENABLED`) e a loja tem número (X1).

```
1. Sacola → POST /api/v1/cart/continue-in-conversation/
   → session_transfer.offer(web → whatsapp) + estado NB {conversation_cart_transfer: oferta}
   → { code, message, deep_link, wa_number }   (a sacola da loja não muda)
2. wa.me abre "Olá! Quero continuar por aqui a sacola que montei no site (ref. NB-XxXx)"
3. A mensagem chega à Nice (resposta padrão do ManyChat, NÃO o fluxo de login)
4. A Nice lê o código, consome o estado e chama session_transfer.accept com o vínculo
   verified_customer da conversa: a sacola anônima passa a ser do cliente verificado;
   a sacola com dono só vai para o dono. A Nice diz que a sacola chegou e o que mudou.
```

⚠️ A mensagem NÃO contém "quero entrar no site" nem `#menu`, para não disparar o Flow de
login no ManyChat. Ela precisa cair na automação que entrega a mensagem à Nice (a resposta
padrão). Se cair no Flow de login por engano, o access link sai sem sacola: a troca do link
ignora a chave `conversation_cart_transfer`, e a sacola continua na loja.

## A Nice manda o site e diz onde a sacola está (OC-18)

O caminho inverso, pela conversa (§4.4 do plano da Etapa II omnicanal). Tudo em
`storefront/concierge/site_passage.py`, chamado em `service.run_turn` logo depois da
chegada pelo código `NB-` e antes do motor; frase da casa, sem modelo. Com a ponte
desligada, nada disto responde e o turno segue como antes.

```
1. "quero ver as fotos no site" / "manda o link do site" / "prefiro terminar pelo site"
   → tools.send_web_link (checkout quando a conversa tem sacola, cardápio quando não)
   → "Continue no site: <link>" + "Sua sacola vai junto."
     (oferecer não tira a sacola daqui; a troca do link é o aceite)
2. A mensagem seguinte, com a sacola aceita no site (Session.data["transferred_to"]):
   a resposta do turno + "Sua sacola está no site, com 2 itens (R$ 1,80). Posso trazer
   os itens para cá, se quiser."
   Uma vez só (a conversa esquece a chave), e só com a sacola do site ainda aberta. A
   oferta inversa só aparece quando é possível agora (ponte ligada, número verificado).
3. "traz a sacola pra cá" / "prefiro pedir por aqui" → tools.bring_site_cart: oferta e
   aceite no mesmo turno (session_transfer.offer + accept), a mesma régua do "Trazer
   para cá" da loja. Com sacola aqui também, os itens entram nela (mescla, decisão do
   dono de 24/11): "Trouxe os itens do site para cá."
```

**Pela entrada sem identificador de mensagem (ADR-050), decisão da Coordenação na #3529.**
A entrada de hoje do ManyChat só dá a autoridade de sacola, e com ela o convite com a sacola
vale em três condições, escritas no código e testadas em `test_ponte_da_nice.py`
(`test_3529_condition_*`):

1. **O link só leva a sacola.** A oferta é `items_only` (só itens, quantidades e a data e o
   horário da fornada: nada de cliente, endereço, presente, observação, pagamento ou cupom) e
   o `AccessLink` leva `cart_only`: a troca (`auth._exchange_cart_only`) gasta o link sem abrir
   sessão (`access.redeem_without_session`), não confia no dispositivo e não devolve nome nem
   telefone. A sacola chega sem dono; a prova de quem é acontece no site, no fechamento.
2. **O mesmo crachá do convite de hoje.** O mesmo `AccessLink`, com a mesma audiência e o
   mesmo prazo (`ACCESS_LINK_EXCHANGE_TTL_MINUTES`), de uso único pelo mesmo portão do doorman.
3. **Só para aquele assinante.** O link só se cunha dentro do turno da conversa (a cerca do
   turno e o vínculo, `assert_turn_authority`) e sai na resposta dela; a ferramenta não aceita
   destinatário.

Sem sacola, o link seria um acesso à conta, e por esta entrada vai o endereço público do
cardápio. A volta acha a sacola que a conversa mandou pelo `transferred_to` dela, mesmo sem
dono.

O cliente que não pede o site nunca recebe o link (§5.3, C09). Frase com negação ("não
quero o site", "o site não abre") não é pedido; a fala que só diz o canal ("prefiro pedir
por aqui") recebe "Claro, seguimos por aqui." e a sacola, se houver.

### Ligar a ponte no ambiente de testes

A chave é `CONCIERGE_TRANSFER_ENABLED` (env de runtime, nível de app, lida em
`config/settings.py` como `SHOPMAN_CONCIERGE["transfer_enabled"]`). Ela já existe: não
se cria outra (ADR-042). Ligar é decisão da Coordenação, e muda o app vivo:

1. `make deploy-spec-drift context=shopman-do-app-admin` (o versionado contra o vivo).
2. `doctl apps spec get <APP_ID> --context shopman-do-app-admin > /tmp/spec-vivo.yaml`
   (o contexto que lê databases; nunca aplicar `.do/app.alpha-subdomains.yaml` por cima).
3. No bloco `envs:` do app, `CONCIERGE_TRANSFER_ENABLED` de `'false'` para `'true'`.
4. `doctl apps update <APP_ID> --spec /tmp/spec-vivo.yaml --context shopman-do-app-admin --wait`
   (env de runtime: sem rebuild).
5. Espelhar o valor em `.do/app.alpha-subdomains.yaml` num PR, para o drift não acusar.

⚠️ A chave liga as duas pontas: a Nice (este fluxo) **e** os gestos da loja do OC-16.
"Continuar pelo WhatsApp" só aparece (e a API só aceita) para quem a Nice atende: cliente
com vínculo na coorte (`CONCIERGE_ALLOWED_SUBSCRIBERS`), ou todo visitante quando a Nice
atender todos (o mesmo predicado da home, OC-06). "Trazer a sacola do WhatsApp" só aparece
quando há sacola aberta na conversa. Desligar é o passo 3 com `'false'`.

Estado: ligada no alpha em 24/11/2026 pela Coordenação (decisão do dono, DEV-2026-085).

## Degradação da sacola (handoff_expired)

Omotenashi: nunca sumir com a sacola em silêncio. Se o código veio mas **não resolveu**
(expirou/já usado), o create marca `metadata.handoff_expired = true` (distinto do login
orgânico, que não tem `access_code`). No exchange, a resposta traz `handoff_expired: true`
+ `notice`, e a loja mostra um toast gentil: *"Você entrou! Sua sacola não veio desta vez
porque o link expirou. É só montar de novo."* (copy configurável, chave
`LOGIN_HANDOFF_EXPIRED`). O login em si nunca falha por isso. Com a aba de origem
entrando sozinha, a sacola nem sai do lugar: o transporte só importa para quem usa o
link de reserva.

## Fallback SMS (Comtele)

Primário da `DELIVERY_CHAIN` em produção (`["sms", "email"]`). Para ativar em
staging/alpha, configure `COMTELE_API_KEY` e `COMTELE_ROUTE` — o `ComteleSMSSender` sai
do estado inerte. Na tela, o link discreto `Prefere receber um código por SMS?` revela o
campo e usa o fluxo clássico:

```
POST /api/v1/auth/request-code/  { "phone": "+55...", "delivery_method": "sms" }
POST /api/v1/auth/verify-code/   { "phone": "+55...", "code": "123456" }
```

## Segurança

- **O código NB não autentica.** A identidade é o número de WhatsApp que envia a
  mensagem (zero-telefone). O código só anexa contexto (destino + sacola).
- Pior caso de sequestro do código: o atacante anexa a *sacola* da vítima ao próprio
  login — dado de baixo valor, sem PII, mitigado por TTL curto + single-use. **Nenhum
  estado do código carrega PII.**
- `next` passa por `safe_redirect_url` na geração e re-checagem no consumo (sem
  open-redirect; o link é sempre `.../a?t=<token>`, sem querystring de destino).
- `create` fail-closed sem `DOORMAN_ACCESS_LINK_API_KEY` fora de DEBUG. `start` tem
  rate-limit por IP (10/min).
- Token do access link: single-use, TTL 5 min, hash HMAC, exchange transacional
  (`select_for_update`). Ver `packages/doorman/.../services/access_link.py`.
- Régua da loja no `create` (OC-09, `shopman/shop/views/access_link.py`): `ttl_minutes`
  acima de 1440 (24 h) ou que não seja número é recusado com 400 `invalid_input`, sem
  cunhar; `audience` fora de `web_general`/`web_checkout`/`web_account` também. O corpo
  documentado acima não manda nenhum dos dois. A troca (`/a`) recusa audiência fora da
  loja sem gastar o token.
- Liberação da aba de origem: sob `sha256("doorman-origin:" + session_key)`, uso único,
  TTL do código. `claim` sem sessão ou de outra sessão responde `pending` e não revela
  nada. `revoke` apaga a sessão (`SESSION_ENGINE`) e desativa o `TrustedDevice`.

## Frontend (storefront-nuxt)

Uma tela só (`app/pages/entrar.vue`), WhatsApp como caminho primário:

- **`app/components/WhatsappVerifyPanel.vue`** — antes do toque: a explicação
  (`LOGIN_WA_WHY`), três passos (`LOGIN_WA_STEPS`) e um botão (deep link `wa.me`
  pré-aquecido). Depois do toque: a espera (`LOGIN_WA_WAITING`) e, só aí, o plano B —
  envio manual (mensagem + copiar + abrir de novo). O SMS é um link discreto abaixo.
- **`app/composables/useWhatsappVerify.ts`** — `start(next)` leve: devolve
  `{code, deepLink, waNumber, status}` e preserva a mensagem preparada durante a
  espera, para que uma recarga não troque o código nem apague o plano B manual.
- **`app/composables/useWhatsappReturn.ts`** — a volta: `arm()` no toque; pergunta ao
  `claim` quando a aba fica visível e, na tela, com backoff de 4/7/15 s, por até 10 min.
  Expõe espera, demora, falha de rede/consulta e expiração, além de uma conferência
  manual. Início e prazo moram no `sessionStorage` (o Safari descarta abas em segundo
  plano), portanto a recarga não apaga o contexto nem recomeça o relógio.
- **`app/pages/encerrar-acesso.vue`** — o "Não foi você?". Um toque para encerrar, nunca
  ao abrir (a prévia do link não pode derrubar ninguém).
- **`app/pages/a.vue`** — landing do access link (a reserva): troca o token via BFF
  `/api/auth/access/`, adota a sacola, redireciona.

## Testar localmente com Cloudflare Tunnel

O único serviço que **precisa ser público** é o Django — para o External Request do
ManyChat alcançar o `create`, e para o cliente abrir o `access_url` (a base do link é
`DOORMAN_ACCESS_LINK_ENTRY_URL`, que deve apontar para o túnel do storefront). O
`settings.py` já libera `*.trycloudflare.com` em `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`
no modo dev.

1. **`.env` (dev)** — mínimo:
   ```env
   SHOPMAN_WHATSAPP_VERIFY_NUMBER=554333231997     # o WhatsApp ligado ao ManyChat
   DOORMAN_ACCESS_LINK_API_KEY=<segredo forte>     # em DEBUG o create aceita sem, mas configure p/ testar de verdade
   DOORMAN_ACCESS_LINK_ENTRY_URL=https://<tunnel-storefront>.trycloudflare.com
   ```
2. **Django + túnel** — `make run` sobe `0.0.0.0:8000` + directive worker + um quick
   tunnel Cloudflare (URL em `.tunnel.log`). Levante também um túnel para o storefront
   (`:3000`) e use essa URL em `DOORMAN_ACCESS_LINK_ENTRY_URL`.
3. **Storefront (Nuxt)** — `NUXT_DJANGO_BASE_URL=http://127.0.0.1:8000 npm run dev` (ou
   `node .output/server/index.mjs` num build). Abra `/entrar` no celular via o túnel.
4. **ManyChat** — no External Request, aponte para `https://<tunnel-django>/api/auth/access/create/`
   com `access_code: {{Last Text Input}}` (selecionado pela UI do ManyChat) e
   `next: "/menu"`.
5. **Fluxo de teste**: no celular, adicione um item em estoque → checkout → "Abrir o
   WhatsApp" → o WhatsApp abre com `#menu NB-XXXX` → envie → o Flow chama o `create` →
   volte ao navegador ("◀ Safari" no iPhone, voltar no Android): a aba já entrou, com a
   sacola, no checkout. O link da mensagem é a reserva.

> Quick tunnels trocam de URL a cada `make run` (reaponte o ManyChat **e**
> `DOORMAN_ACCESS_LINK_ENTRY_URL`). Para URL fixa, use um named tunnel do Cloudflare.

## Testes

```bash
make test-framework   # backend: start leve, create (code/handoff), exchange (sacola/notice)
cd surfaces/storefront-nuxt && npm run test:unit   # front: transforms + guardrails de surface
```

Backend: `shopman/shop/tests/test_login_site_aba_de_origem.py` (a aba de origem entra,
outro navegador não, "Não foi você?" antes e depois), `shopman/storefront/tests/test_whatsapp_verify.py` (start leve),
`packages/doorman/.../tests/test_security.py` (create: dobra sacola/next, extrai da
mensagem, degrada, marca handoff), `shopman/storefront/tests/web/test_auth_access_api.py`
(exchange: adoção de sacola, handoff notice).
