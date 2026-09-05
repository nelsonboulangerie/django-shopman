# Auditoria adversarial do contrato do storefront

> ⚠️ **SEVERIDADE REVISADA — leia [`verify-02-06-storefront-admin.md`](verify-02-06-storefront-admin.md) antes de agir por este laudo.**
> 
> Um passe de refutação em 01/09 atacou cada P0 deste arquivo com uma régua única
> (P0 = perde dinheiro, corrompe dado, viola segurança, ou impede tarefa central sem
> contorno). **5 P0 alegados → 1 sobreviveu** (o PATCH de perfil, e ele JÁ está corrigido em `eb98961fb`). O de alérgenos foi refutado: o seed preenche `food_safety_notice`, então o painel sempre desenha.
> 
> As contagens NO CORPO deste arquivo são as originais e estão infladas. O fato de
> cada achado quase sempre se sustenta; a **severidade** não.

**Escopo:** `shopman/storefront/` (Django, `/api/v1/`) ↔ `surfaces/storefront-nuxt/` (Nuxt 4.5.2 + BFF Nitro).
**Método:** leitura completa de `api/urls.py` e de todas as views/serializers atrás dele; leitura das páginas, composables, `presentation/`, `utils/` e `server/` do app Nuxt; diff campo a campo.
**Somente leitura.** Nenhum arquivo do repositório foi alterado, nenhum teste foi executado.

Raiz de todos os caminhos: `/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agente-c-audit-fixes-0dcab9/`

---

## P0

### P0-1 — A chave de idempotência do cliente NUNCA chega ao Django; "Pedir de novo" vira no-op por 24h

**Duas quebras encadeadas, no mesmo caminho.**

1. O BFF monta os headers do zero e **não repassa** `x-idempotency-key`:
   `surfaces/storefront-nuxt/server/utils/djangoProxy.ts:98-123` — só `accept`, `cookie`, `content-type`, `origin`, `referer`, `x-csrftoken`.
2. Mesmo que repassasse, o Django procura outro nome de header:
   `shopman/shop/services/remote_mutations.py:37` — `request.headers.get("Idempotency-Key")`.
   O cliente manda `x-idempotency-key` (nome diferente, não é questão de caixa):
   `surfaces/storefront-nuxt/app/pages/finalizar.vue:921`, `app/composables/useReorder.ts:17`,
   `app/pages/pedido/[ref]/index.vue:235` e `:264`.

Consequência: `idempotency_key_from_request` sempre cai no `fallback`, que é **determinístico**
(`shopman/storefront/api/surface.py:409` → `f"reorder:{ref}:{mode or 'default'}"`).
O registro `IdempotencyKey` vive **24h** (`remote_mutations.py:94`) e o `run_idempotent_mutation` do reorder
**não passa `cache_response`**, então o default `response_code < 500` guarda a resposta de sucesso
(`remote_mutations.py:77-82`).

**Reprodução:** cliente toca "Pedir de novo" no pedido `NB-2026-0001` (sacola vazia) → itens entram, toast
"Itens adicionados ao carrinho.", vai para `/sacola`. Duas horas depois, esvazia a sacola e toca "Pedir de
novo" **no mesmo pedido** → o servidor devolve o corpo cacheado (`replayed=True`), `useReorder.ts:22-24`
faz `setFromServer(cart_de_2h_atras)`, mostra o mesmo toast de sucesso e navega para `/sacola` — **onde nada
foi adicionado**. Repete por 24h.

Mesma classe (menos grave, porque o replay é o comportamento desejado): `rate:{ref}` — reavaliar um pedido
dentro de 24h devolve a nota antiga em silêncio (`shopman/storefront/api/tracking.py:549`).

**Correção:** (a) repassar `x-idempotency-key`/`idempotency-key` em `djangoProxy.ts`; (b) aceitar ambos os
nomes em `idempotency_key_from_request`; (c) no reorder, ou escopar o fallback pela sessão + timestamp, ou
passar `cache_response=lambda _b, c: False` — a operação não é naturalmente idempotente.

---

### P0-2 — `PATCH /api/v1/account/profile/` é um PUT disfarçado: o portão de boas-vindas apaga e-mail, sobrenome e aniversário

- O Nuxt manda **só** `first_name`: `surfaces/storefront-nuxt/app/pages/entrar.vue:421-426`.
- A view lê os quatro campos incondicionalmente; chave ausente vira `""`/`None`:
  `shopman/storefront/api/account.py:358-361`, `:368-373`, `:375-380`.
- E-mail vazio significa **apagar o ContactPoint primário**:
  `shopman/shop/services/account.py:149-151` (`else: ContactPoint.objects.filter(...).delete()`), seguido de
  `:153-158`, que grava `last_name=""` e `birthday=None`.

**Reprodução:** cliente com e-mail e aniversário cadastrados cai no portão de boas-vindas (dispara sempre que
o nome guardado tem emoji ou `& + | /` — `shopman/storefront/intents/auth.py:54-62`, exatamente os nomes
importados do ManyChat), confirma o nome → e-mail deletado, sobrenome e aniversário zerados. Sem aviso.

**Correção:** aplicar semântica PATCH — só tocar as chaves presentes em `payload`; ou exigir que o portão
mande o objeto completo.

---

### P0-3 — Uma única falha transitória apaga a tela de acompanhamento e ela nunca se recupera sozinha

`useAsyncData` do Nuxt **reseta `data` para o default em qualquer rejeição**:
`node_modules/nuxt/dist/app/composables/asyncData.js:375-376` (nuxt 4.5.2)
— `asyncData.error.value = createError(error); asyncData.data.value = unref(options.default())`.

Na tela de acompanhamento não há `default`, então `data.value` vira `undefined` e
`tracking` vira `null` (`surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue:53-58`).
E **todos** os caminhos de auto-recuperação são guardados por `tracking.value?.is_active`:

- poll: `pedido/[ref]/index.vue:204-206`
- volta de foco/reconexão: `:172`
- push SSE: `:180`
- expiração de deadline: `:214-218`

Com `tracking === null`, `is_active` é `undefined` → **nenhum deles volta a rodar**.

**Reprodução:** cliente com o pedido "saiu para entrega" deixa a tela aberta. Um poll cai (queda de sinal no
elevador, 502 de 3 s durante um deploy, ou o 429 compartilhado do P1-1). A tela troca para
"Não foi possível carregar o acompanhamento agora" (`:451-458`) e **fica ali para sempre**, mesmo com a rede
de volta e o pedido já entregue. Só o botão "Tentar de novo" resolve.

Mesma mecânica, menor impacto: `finalizar.vue:229-236` (uma falha de `refresh()` após cupom/fidelidade/
rascunho de entrega desmonta o formulário inteiro para "Checkout indisponível") e `sacola.vue:15-17,132`
(o `useCartState` sobrevive, mas a página mostra o alerta de erro em vez dos itens que ainda tem em memória).

**Correção:** passar `getCachedData`/`default` que preserve o último payload, ou manter uma cópia
(`lastGood`) e gatear os timers por `orderRef` em vez de `tracking.value?.is_active`.

---

### P0-4 — "Pedir de novo" nunca pergunta antes de mexer numa sacola cheia, e "Substituir" adiciona

O backend só devolve o 409 de conflito quando o `mode` **não** vem:
`shopman/storefront/api/surface.py:403` — `if cart_has_items and mode not in {"replace","append"}`.

O front **sempre** manda `mode`, com default `'append'`:
`surfaces/storefront-nuxt/app/composables/useReorder.ts:10` (`mode: 'append'|'replace' = 'append'`),
`:20` (`body: { mode }`), `:45` (`performAction(action, mode = 'append')`).

Duas consequências:

1. **O 409 é inalcançável.** Toda a `ReorderConflictProjection`
   (`shopman/storefront/presentation/reorder.py:34-95`) e os três diálogos que a consomem
   (`app/pages/pedido/[ref]/index.vue:875-898`, `app/pages/conta/index.vue:235-247`,
   `app/pages/conta/pedidos.vue:150-160`) são **código morto**. O cliente com a sacola montada toca
   "Pedir de novo" e os itens do pedido antigo são somados sem qualquer pergunta.
2. **Se o diálogo aparecesse, "Substituir" somaria.** `performAction(conflictReplaceAction)` é chamado sem
   o segundo argumento (`conta/index.vue:243`, `conta/pedidos.vue:157`,
   `pedido/[ref]/index.vue:892` via `performReorderSafely`), então o `mode` volta ao default `'append'` —
   o `action.payload_schema` do backend diz `{"mode": {"const": "replace"}}` e é ignorado.

Contraste correto no mesmo repo: `app/pages/oferta/[ref].vue:35,45` — primeira chamada **sem** `mode`,
o 409 sobe, a tela pergunta.

**Correção:** `submit(orderRef, mode?: 'append'|'replace')` com `mode` opcional e `body: mode ? {mode} : {}`;
`performAction` deve derivar o `mode` de `action.payload_schema.properties.mode.const` (ou do `action.ref`).

---

### P0-5 — Alérgenos: `has_any` é `@property`, nunca é serializado, e o painel some

`projection_data` percorre **só** `dataclasses.fields()` — propriedades não entram:
`shopman/storefront/api/projections.py:14-18`.

`has_any` é `@property` em três projeções da PDP:
`shopman/storefront/presentation/product_detail.py:65-67` (alérgenos), `:97-99` (nutricional), `:113-115`
(conservação).

O Vue usa exatamente essas chaves como condição de exibição:
`surfaces/storefront-nuxt/app/pages/produto/[sku].vue:299` (`product.allergen?.has_any || …`) e `:329`.
O tipo mente e esconde o problema do typecheck: `app/types/shopman.ts:97` e `:103` declaram `has_any?`.

**Reprodução:** produto com `metadata.allergens = ["glúten","leite"]`, sem `ingredients_text` e com
`Shop.food_safety_notice` vazio (`product_detail.py:534-542` → `trace_notice=""`). A condição vira
`undefined || null || ""` → falsa: o acordeão "Ingredientes e restrições" **não renderiza**, e as linhas
`:304-305`, que listariam os alérgenos, ficam inalcançáveis. **Dado de alérgeno calculado pelo backend fica
invisível para o cliente.** Idem "Conservação" (`:329`) para um produto que só tem `shelf_life_label`.

**Correção:** transformar `has_any` em campo do dataclass (calculado no `build_*`), ou fazer
`projection_data` incluir propriedades declaradas. E corrigir o tipo TS para não-opcional.

---

## P1

### P1-1 — O BFF não repassa o IP do cliente: todo visitante anônimo divide um único balde de rate-limit

- `RATELIMIT_IP_META_KEY = "shopman.shop.services.auth.client_ip"` (`config/settings.py:423`), que resolve
  pelo `X-Forwarded-For` e cai em `REMOTE_ADDR` quando ele não existe
  (`packages/doorman/shopman/doorman/utils.py:19-25`).
- O BFF **não envia** `x-forwarded-for` nem `x-real-ip`: `surfaces/storefront-nuxt/server/utils/djangoProxy.ts:98-123`.
- Todo tráfego da loja passa pelo BFF (same-origin): `app/composables/useShopmanApiPath.ts:3-7` devolve
  caminho relativo; `server/api/v1/[...path].ts` e `server/api/auth/[...path].ts` fazem o proxy.

`key="user_or_ip"` salva o cliente **logado** (o doorman faz `django.contrib.auth.login` —
`packages/doorman/shopman/doorman/services/verification.py:317`), mas:

- **Anônimo divide o balde.** `PUT /api/v1/cart/skus/{sku}/` é `120/m`
  (`shopman/storefront/api/surface.py:756`) — ~120 toques de `+`/`-` por minuto **na loja inteira**
  antes de todo visitante anônimo tomar 429.
- **Views com `authentication_classes = []` divide o balde até para o logado**, porque o DRF força
  `request.user = AnonymousUser`: `OrderTrackingView` (`api/tracking.py:146`, limite `120/m` em `:151-157`),
  `OrderConversationView` (`api/conversation.py:57`), `AccountSummaryView` (`api/account.py:409`),
  `OrderHistoryView` (`:671`), `ActiveOrderCountView` (`:711`).

**Reprodução:** 15 clientes anônimos navegando o cardápio numa manhã de sábado; cada um ajusta quantidade
umas 8 vezes por minuto → o 16º recebe "Muitas alterações na sacola. Aguarde um instante." sem ter feito nada.

**Correção:** repassar `x-forwarded-for` (append do IP real) em `djangoProxy.ts` e ajustar
`DOORMAN_TRUSTED_PROXY_DEPTH`; e dar `authentication_classes = [SessionAuthentication]` às views de leitura
que hoje têm `[]`, para o balde por usuário voltar a valer.

---

### P1-2 — 401/500 nas telas de conta viram "estado vazio legítimo"

Nenhuma página de `/conta` desestrutura `error` do `useFetch` (só `conta/favoritos.vue:10` o faz), e não há
interceptor global de 401 (`app/plugins/` só tem `errorReporter.client.ts`):

- `app/pages/conta/pedidos.vue:25` → `:31` (`history.value?.orders ?? []`) → `:96` renderiza
  **"Você ainda não fez pedidos"**. O backend não tem try/except em `OrderHistoryView.get`
  (`shopman/storefront/api/account.py:682-702`), então um 500 na projeção conta a mesma história.
- `conta/enderecos.vue:23` → `:125` "Nenhum endereço salvo".
- `conta/seguranca.vue:37` → `:399` "Nenhum dispositivo confiável".
- `conta/index.vue:21` → `:35-38` "Nenhum pedido ainda" (o `AccountSummaryView` protege `active_orders` em
  `account.py:422-435`, mas **não** as duas contagens em `:461` e `:467`).

**Reprodução:** sessão expira enquanto a aba está aberta; o cliente toca "Meus pedidos" → o histórico
inteiro dele aparece como "você nunca comprou aqui".

**Correção:** ler `error` em cada página e separar três estados (erro / vazio / carregando); e um
tratamento comum de 401 que reencaminhe para `/entrar?next=…`.

---

### P1-3 — Banner de happy hour promete desconto que a precificação pode não aplicar

- `happy_hour_state()` lê `get_rule_params("happy_hour")`, que **ignora o escopo de canal** da regra:
  `shopman/shop/projections/storefront_context.py:77` → `shopman/shop/rules/engine.py:74-86`.
- O modifier que de fato desconta lê o gate com canal:
  `shopman/shop/modifiers.py:472` → `get_channel_rule_params("happy_hour", channel.ref)` (`engine.py:104-116`,
  devolve `None` quando a regra é de outro canal).
- A projeção repassa o estado sem checar: `shopman/storefront/presentation/catalog.py:824-832`, exposto em `:310`.
- A tela afirma como fato: `surfaces/storefront-nuxt/app/pages/menu.vue:420-422` —
  *"{{ discount_percent }}% de desconto aplicado no cardápio"*.

**Reprodução:** `RuleConfig` de `happy_hour` restrita a `channels=[pos]`, dentro da janela →
`/api/v1/storefront/menu/` devolve `happy_hour.active=true, discount_percent=25`, todos os `price_display`
em preço cheio, e o banner diz que 25% já está aplicado. É exatamente o bug que o próprio código documenta
como já corrigido para promoções (`catalog.py:578-584`).

---

### P1-4 — Cross-sell pode levar a uma PDP que dá 404

- Cross-sell filtra só por `is_published`, sem o listing do canal:
  `shopman/storefront/presentation/product_detail.py:327-331` → `catalog.py:355-372` →
  `shopman/shop/projections/catalog_context.py:72-79`.
- A PDP exige o listing: `product_detail.py:222-223` + `:385-396`; a API devolve 404
  (`shopman/storefront/api/surface.py:303-304`).
- Renderizado como card clicável normal: `app/pages/produto/[sku].vue:344-354`.

E o guard de 404 da PDP **só roda no setup**: `app/pages/produto/[sku].vue:15-24` — a `useFetch` refaz o
fetch quando o `sku` muda (`:16`, key como função), mas o `if (error.value?.statusCode === 404) throw
createError(...)` de `:22` é uma linha única do setup. Mesmo padrão em `app/pages/colecao/[ref].vue:22-31`.

**Reprodução:** de `/produto/A`, clicar no card de B (publicado mas fora do listing) → 404 do backend, página
**continua 200** e mostra o alerta vermelho "Não foi possível abrir este produto / Tente de novo" — erro de
rede aparente para um 404 permanente, e um soft-404 indexável.

---

### P1-5 — Endpoints públicos vazam SKU não publicado (oráculo de enumeração)

`product_exists` não é escopado: `shopman/shop/projections/catalog_context.py:30-33` (`Product.objects.all()`),
reexportado em `shopman/storefront/services/catalog.py:30-31`. Usado por:

- `shopman/storefront/api/availability.py:57-58` (GET, sem auth `:52-53`, **sem rate-limit**)
- `shopman/storefront/api/availability.py:104-105` (POST notify)
- `shopman/storefront/api/fomo.py:56-57` (GET, sem auth `:51-52`, sem rate-limit)

Enquanto `GET /api/v1/storefront/products/<sku>/` e `/api/v1/catalog/products/<sku>/` devolvem 404
(`surface.py:303-304`, `catalog.py:104-113`).

**Reprodução:** produto rascunho `SKU-DRAFT` (`is_published=False`).
`GET /api/v1/availability/SKU-DRAFT/` → 200 com quantidade; `GET /api/v1/fomo/SKU-DRAFT/` → 200 com
`sold_today`/demanda (`presentation/fomo.py:156-194`); `GET /api/v1/storefront/products/SKU-DRAFT/` → 404.

---

### P1-6 — 409 de estoque/hold no commit não recarrega o carrinho nem manda o cliente para a sacola

`map_order_error` classifica `blocking_issues`/`stale_checks`/`hold_expired`/`in_progress` como **409**
(`shopman/shop/services/checkout.py:172-179`), sem `field`.
O catch do front (`app/pages/finalizar.vue:955-1004`) só chama `refresh()` no caso `total_changed` (`:971-975`);
para 409 sem `field` ele apenas escreve `serverError` e dispara um toast (`:958`, `:1004`).

**Reprodução:** cliente monta a sacola às 8h, deixa a aba aberta, confirma às 10h. O croissant esgotou →
409 `blocking_issues`. A tela mostra a mensagem, mas o resumo lateral continua listando o croissant com preço
e total antigos, e o botão "Confirmar" segue habilitado — o cliente tenta de novo em loop sem saber qual item
tirar. Idem quando o slot de retirada expira (400 `delivery_time_slot`, `shopman/storefront/api/views.py:240-248`):
a lista `pickup_slots` da tela é a do último `refresh()`, então o horário recusado continua desenhado como
disponível.

**Correção:** chamar `refresh()` em todo 409 de commit (e no 400 de `delivery_time_slot`), e para
`blocking_issues` oferecer o caminho de volta à `/sacola` — onde o banner de indisponibilidade já existe.

---

### P1-7 — Rate-limit / cooldown do OTP volta como 400 e a tela pinta erro vermelho em vez do estado calmo

`shopman/storefront/api/auth.py:498-502` devolve **400** com a mensagem de "Muitas tentativas…" para
`RATE_LIMIT`/`COOLDOWN`/`IP_RATE_LIMIT` (`shopman/shop/services/auth.py:99-110`).
O front decide a variante calma **só pelo status HTTP**:
`surfaces/storefront-nuxt/app/presentation/auth.ts:42` (`if (input.status === 429)`), consumido em
`app/pages/entrar.vue:346` e `:478-485`. Só o caminho do decorator devolve 429 de verdade (`auth.py:470-474`).

---

### P1-8 — A tela de segurança diz que o cliente não tem passkey quando na verdade tomou 403

`app/pages/conta/seguranca.vue:64-78` — `loadPasskeys` captura **tudo** e faz `passkeys.value = []`, então o
403 `identity_confirmation_required` de `AccountPasskeyListView` (`shopman/storefront/api/account.py:1070-1077`)
vira o estado vazio "Você ainda não ativou" (`:343-354`). O comentário em `:70-73` afirma que o convite de
confirmação aparece — não aparece: `needsConfirmation` só é setado dentro do catch de `enroll()`
(`app/composables/usePasskey.ts:191-193`).

---

### P1-9 — Erros de servidor chegam ao cliente como "revise seus dados" (400 onde cabe 5xx / 409)

- `shopman/storefront/api/account.py:383-390` — **qualquer** exceção de `update_profile` vira 400
  "Não foi possível atualizar seu perfil agora", renderizado sob o título **"Revise seu perfil"**
  (`app/pages/conta/perfil.vue:185-188`). Isso engole o conflito **acionável** de e-mail:
  `shopman/shop/services/account.py:134-135` levanta `ValueError("E-mail já está em uso.")` — a razão real e
  o `field: "email"` nunca chegam ao formulário (é o 409 que falta).
- Mesmo padrão em `account.py:559-564` (criar endereço) e `:615-623` (editar endereço).

---

### P1-10 — Falhas silenciosas sem `catch` em ações de conta

- `app/pages/conta/enderecos.vue:59-72` (`Definir padrão`): `try/finally` sem `catch`. 401/400/500 → nada
  acontece na tela e a promise rejeitada escapa. Pior: o backend valida o `?action=` **antes** da auth
  (`shopman/storefront/api/account.py:639-642` vs `:643-645`), então sessão expirada recebe 400 e não 401.
- `app/pages/conta/index.vue:51-68` (logout): `try/finally` sem `catch`. Numa falha, o diálogo fecha,
  `session.reset()` e `navigateTo('/')` não rodam, e o cliente segue logado sem qualquer mensagem.
- `app/pages/conta/seguranca.vue:57` ignora o `failed` de `useWhatsAppConfirm`
  (`app/composables/useWhatsAppConfirm.ts:21,44-57`); o endpoint é `10/m` por IP
  (`shopman/storefront/api/whatsapp_verify.py:28-30,45-48`) → o botão para de girar e nada acontece.

---

### P1-11 — `TrustDeviceView` e `LogoutView` sem proteção CSRF

`shopman/storefront/api/auth.py:606-611` (`TrustDeviceView`) e `:87-92` (`LogoutView`) têm
`authentication_classes = []` e **não** têm `@csrf_protect`. `APIView` do DRF é `csrf_exempt`, e sem
`SessionAuthentication` o `enforce_csrf` nunca roda. Compare com `VerifyCodeView`/`DeviceCheckView`/
`AccessLinkExchangeView`, que carregam o decorator (`auth.py:203`, `:515`, `:549`).
Um POST cross-site consegue plantar o cookie de dispositivo confiável de 30 dias
(`auth.py:619-629`) ou derrubar a sessão do cliente.

---

### P1-12 — Notícia de "loja fechada" é calculada pelo backend e renderizada por ninguém

`shopman/storefront/presentation/home.py:320-364` monta a notícia com `priority="global"` (título
"Loja fechada agora", ações "Ver cardápio" / "Falar no WhatsApp"), anexada em `:299`.
A home filtra exatamente essa prioridade fora: `surfaces/storefront-nuxt/app/pages/index.vue:43` —
`notices.filter(n => n.priority !== 'global')`. O outro detentor (`app/composables/useShopSession.ts:83,137,152`)
não é lido em lugar nenhum. O cliente só recebe o selinho "Fechado agora" (`index.vue:352`).

---

### P1-13 — Coleção ativa e vazia perde o próprio nome

Com zero produtos listados, `build_catalog` curto-circuita com `sections=()`
(`shopman/storefront/presentation/catalog.py:266-277`); o nome ainda viaja em `categories` (`:325-336`) e
`active_category_ref` (`:272`). O front não lê nenhum dos dois e tira o título de `sections`:
`surfaces/storefront-nuxt/app/pages/colecao/[ref].vue:38-44`.
Resultado: `/colecao/paes-especiais` renderiza `<h1>Coleção</h1>`, breadcrumb "Coleção", `<title>Coleção</title>`
e `og:description` "Coleção". (`:40` ainda cai em `sections[0]`, o que tituraria a página com a coleção errada
num payload de múltiplas seções.)

---

### P1-14 — Preço zero renderiza em branco

`shopman/storefront/presentation/catalog.py:541` e `product_detail.py:342` emitem string vazia
(`price_display=_money(effective_q) if effective_q else ""`), e o ramo `"R$ 0,00"` de `_money`
(`catalog.py:716-719`) é inalcançável para `price_display`. O front não tem fallback:
`app/components/ProductTile.vue:96`, `app/components/ProductListItem.vue:44`,
`app/pages/produto/[sku].vue:269` e `:363`. Enquanto isso o og/JSON-LD anuncia `0.00`
(`app/presentation/seo.ts:27-29,85,140`, usado em `[sku].vue:96`).

---

### P1-15 — `/api/v1/geocode/reverse/` devolve o erro interno em inglês, com 502

`shopman/storefront/api/geocode.py:74-77` — `Response({"detail": str(exc)}, status=502)`.
As mensagens levantadas são `"GOOGLE_MAPS_API_KEY not configured."`, `"No result (status=ZERO_RESULTS)."`
(`shopman/shop/services/geocoding.py:128,156,160`). O front imprime `detail` literal
(`app/components/AddressPicker.vue:415`, `:479` via `app/utils/httpError.ts:31-34`) e classifica 502 como
transitório/retentável (`httpError.ts:24-27`).

---

### P1-16 — Exportar dados é uma navegação de página inteira para um endpoint que pode responder JSON 403

`app/pages/conta/seguranca.vue:129` — `window.location.assign(apiPath('/api/v1/account/export/'))`.
Com o step-up vencido (janela de 10 min, `shopman/storefront/api/account.py:55-56`), a resposta é 403
`{"detail":…, "code":"step_up_required"}` (`account.py:78-82`, `:878-879`) — renderizada como JSON cru na
aba do cliente. O caminho feliz devolve `HttpResponse` (`:882-884`): duas linguagens de conteúdo na mesma URL.

---

## P2

### Contrato do dialeto de erro

- **404 do allowlist do BFF não fala o dialeto.** `surfaces/storefront-nuxt/server/api/v1/[...path].ts:9` —
  `createError({statusCode:404, statusMessage:'Not Found'})` produz `{statusCode, statusMessage, message, url}`,
  sem `detail`. (Nenhum caminho legítimo do app cai fora do allowlist hoje —
  `server/utils/storefrontApiAllowlist.ts:1-15` cobre todos os 50 caminhos que o front usa.)
- **Django fora do ar não fala o dialeto.** `server/utils/djangoProxy.ts:129-134` — `ignoreResponseError`
  só suprime status não-2xx; um `ECONNREFUSED` rejeita e o handler não tem try/catch → o Nitro devolve
  500 com o corpo padrão do h3, sem `detail`.
- **Três nomes para o mesmo conceito** dentro do slice de conta: `{"detail","code"}`
  (`shopman/storefront/api/account.py:80`), `{"detail","error_code"}` (`account.py:1073-1075`, `:1100-1102`,
  `auth.py:721-725`, `:747-751`) e `{"detail","error":{"code":…}}` (`account.py:961-970`). Só `error_code`
  tem leitor (`app/composables/usePasskey.ts:191`).
- **`errors` nunca é emitido** por nenhum endpoint de conta/auth. As funções `interpret_*` que produzem esse
  shape (`shopman/storefront/intents/account.py:26-30`, `intents/auth.py:86-98`) são **código morto** — os
  únicos chamadores estão em `shopman/storefront/tests/test_auth_intents.py`; a API duplica a validação
  inline (`account.py:362-366`, `auth.py:570-578`).
- **400 de campo sem `field`:** `account.py:642`, `:738` (`key`), `:762` (`channel`), `:904`/`:911` (`code`),
  `:947` (`acknowledged`); `auth.py:588-592`; `geocode.py:69`, `:72`.
- `shopman/storefront/api/views.py:426` — `raise` para exceção não mapeada → 500 HTML do Django.
  Mitigado pelo BFF, que sanitiza HTML 4xx/5xx em `{detail: "Não foi possível responder agora."}`
  (`djangoProxy.ts:17-19,150-153`) — mas isso torna uma falha de CSRF indistinguível de uma queda do servidor.
- `shopman/storefront/api/telemetry.py:87` — 429 com corpo **vazio** (deliberado, mas fora do dialeto).

### Códigos de status

- `shopman/storefront/api/account.py:713-716` — `ActiveOrderCountView` devolve **200 `{"count": 0}`** para
  requisição não autenticada: sessão morta é indistinguível de "sem pedidos ativos".
- `shopman/storefront/api/auth.py:230-231`, `:488-489`, `:539-540`, `:580-581` — com `HAS_AUTH` falso todo
  endpoint de auth devolve **200 `{"ok": true}`** sem fazer nada; `entrar.vue:389` então alimenta
  `setFromAuthSession` com um payload sem `is_authenticated`, o que zera a sessão
  (`useShopSession.ts:92-102`) e mesmo assim navega para o `next`.
- Coleção inexistente: **404** em `/api/v1/storefront/menu/<ref>/` (`surface.py:267-268`) e
  **200 + `[]`** em `/api/v1/catalog/products/?collection=<ref>` (`catalog.py:51-53` →
  `catalog_context.py:228-230`).
- `shopman/storefront/api/account.py:639-642` — `request.data.get("action")` levanta `AttributeError` → 500
  se o corpo for um array JSON.
- `shopman/storefront/api/account.py:859-865` — revogar dispositivo de terceiro devolve **200
  `{"revoked": true}`** (anti-enumeração deliberada), mas a UI mostra "Dispositivo removido." para um no-op.
- `shopman/storefront/api/account.py:898-911` — `AccountStepUpView` sem decorator de `ratelimit`, ao
  contrário de `VerifyCodeView` (`auth.py:516`).
- **Sem vazamento 404-vs-403** em endereços (`account.py:607-609`, `:633-634`, `:647-648`), passkeys
  (`:1107-1108`) e `saved_address_id` no checkout (`views.py:586-590`) — o comentário em `views.py:586-587`
  documenta a escolha corretamente.

### Contrato morto (backend manda, ninguém lê)

- **`payment_status` no acompanhamento.** `app/types/shopman.ts:872` declara e
  `app/pages/pedido/[ref]/index.vue:193` lê (`t.payment_status_label || t.payment_status`), mas o campo foi
  **removido de propósito** do serializer (`shopman/storefront/api/tracking.py:107-110`;
  `OrderTrackingSerializer` em `api/serializers.py:276-328` não o tem). Sempre `undefined`.
- **`summary` e `line` da resposta do `PUT /api/v1/cart/skus/{sku}/`.** Montados em
  `shopman/storefront/services/cart_mutations.py:124-180`, tipados em `app/types/shopman.ts:544-567`,
  **nenhum leitor** — `useCartState.ts:299` usa só `response.cart`. E `summary.grand_total_q` está
  **errado**: `cart_mutations.py:140-141` define `grand_total_q = subtotal_q`, ignorando a taxa de entrega.
  Armadilha latente para quem vier consumir.
- **`skipped` / `skipped_items` do reorder.** `shopman/storefront/api/surface.py:418-425` devolve os itens
  que não puderam voltar; `useReorder.ts:22-24` ignora e mostra "Itens adicionados ao carrinho." — inclusive
  quando **todos** foram pulados (`ok` é sempre `True`, `surface.py:419`). Contraste correto:
  `app/pages/oferta/[ref].vue:50,123` conta os pulados.
- **Endpoints inteiros sem consumidor no storefront Nuxt:** `/api/v1/catalog/products/`,
  `/api/v1/catalog/products/<sku>/`, `/api/v1/catalog/collections/` (`api/catalog.py`),
  `GET /api/v1/availability/<sku>/` (`api/availability.py:33-80`), `/api/v1/fomo/<sku>/` e o canal SSE
  `fomo-<sku>` (`api/fomo.py`, `api/urls.py:107-115`), `/api/v1/orders/<ref>/conversation/`
  (`api/conversation.py` — consumido por ManyChat, não pela loja).
  Onde divergem do contrato que precisariam cumprir: `api/serializers.py:84` renomeia `base_price_q` → `price_q`
  e omite `is_paused`/`is_notifiable`/`dietary_warnings`/`tags`; `serializers.py:107` tipa `available_qty`
  como **string** enquanto a projeção usa `int|null` (`presentation/catalog.py:503-512`).
- **Home:** `opening_hours` (`presentation/home.py:247-250`) e a copy que existiria para renderizá-lo
  (`:460-461`); `shop_status.message/opens_at/closes_at` (`:239-245`); `omotenashi.moment/greeting/shop_hint`
  (`:225-233`); `sections_copy.how_step_*`, `tomorrow_label`, `tomorrow_hook` (`:455-457`, `:468-469`);
  `origin_channel` (`:257-264`).
  `primaryAction` é estruturalmente sempre `null`: `_home_actions` só devolve `reorder`
  (`home.py:403-423`) e `app/pages/index.vue:41` filtra `priority==='primary' && !ref.includes('reorder')`.
  `home.featured_items` é cortado em 3 (`home.py:255`) e a UI fatia 6 num grid de 3 colunas
  (`index.vue:56`, `:285`).
- **Catálogo/PDP:** `active_category_ref` (`catalog.py:309`), `categories` (`:242`), `featured` (`:302`),
  `slug` (`:528`), `qty_in_cart` (`:556`), `is_bundle` e `breadcrumb_category`
  (`product_detail.py:357`, `:368`), `nutrition.servings_per_container` (`:604`), `allergen.serves` (`:455`).
- **Conta/auth:** `customer_ref`/`customer_email` (`auth.py:66,69`), `identity_strength` (`:255`, `:290`),
  `device_trusted` (`:306`, `account.py:922`), `expires_in_minutes` (`auth.py:688`),
  `delivery_method` (`:387`), `supported_hint` (`account.py:1081-1083`), `recent_order_count` (`:460`),
  `loyalty.stamps_completed` (`:444`), `loyalty.transactions`/`tier` (`:439-454`),
  `active_orders[].actions` (`:471-472`), `item_count` (`:479`), `status_color`
  (`presentation/account.py:177`, a UI usa só `status_tone`), e os corpos de resposta de
  revoke/step-up/favoritar (`account.py:839`, `:862`, `:922`, `:973-977`, `:1035`).
- **Tracking:** `timeline`, `eta_display`, `is_preorder`, `when_display`, `status_color`,
  `confirmation_countdown`/`confirmation_expires_at`, `payment_pending`/`payment_expired`/`payment_confirmed`,
  `is_debug`, `last_updated_display`, `delivery_fulfillments`/`pickup_fulfillments` (a tela usa só a lista
  achatada `fulfillments`) não têm leitor em `app/pages/pedido/[ref]/index.vue`.

### Rotas mortas em payload do backend

- `shopman/storefront/presentation/checkout.py:467` — `_auth_action()` aponta para
  **`/login?next=/checkout`**. No app Nuxt não existe `/login` nem `/checkout` (as rotas são `/entrar` e
  `/finalizar` — ver `app/pages/`). `app/pages/finalizar.vue:298` **prefere** esse href
  (`authAction.value?.href || '/entrar?next=/finalizar'`), então o fallback correto nunca é usado.
  Alcançável quando a sessão expira com a tela aberta e o cliente abre "Trocar conta" (`:1794` →
  `goToAuthRoute`, `:906-908`) → 404. Mesma classe do bug de `next_url` que `api/views.py:435-439` documenta
  como já corrigido.

### Outros

- `app/pages/sacola.vue:117` renderiza `cart.grand_total_display` **sem** o atenuador de `summary_pending`
  que as outras duas ocorrências usam (`:287`, `:345`, `:380`). Durante uma mutação otimista o cabeçalho
  mostra "2 itens · R$ 9,00" (contagem nova, total antigo) até a reconciliação.
- `app/pages/conta/index.vue:28`, `:60`, `:74` — `summary.value?.copy.greeting_prefix`: a corrente opcional
  para em `summary`; um corpo sem `copy` lança. Todas as páginas irmãs guardam a mesma chave
  (`pedidos.vue:53`, `favoritos.vue:17`, `enderecos.vue:31`, `seguranca.vue:110`). Latente, não vivo.
- `GET /api/v1/tracking/<ref>/` **escreve**: `resolve_timeouts_if_due`, `reconcile_payment_with_gateway_if_due`,
  `ensure_payment_intent` e `consume_just_placed` (`api/tracking.py:175-204`). Um GET de uso único
  (`just_placed`) é frágil a prefetch/SSR duplo.
- `app/pages/produto/[sku].vue` e as tiles do menu têm **tetos de quantidade diferentes**:
  `ProductTile.vue:109` / `ProductListItem.vue:113` passam `item.available_qty`, que é `null` quando o
  backend pulou o cálculo (`presentation/catalog.py:503-512`), e `QuantityControl.vue:31` não limita; a PDP
  limita com `product.available_qty ?? product.max_qty` (`[sku].vue:282`, `:376`).
- `app/presentation/cart.ts:25-27,45-52` multiplica `base_price_q` (calculado a `qty=1` e sensível ao
  subtotal — `presentation/catalog.py:456-469,540`) por `qty` na linha otimista. Aritmética inteira, sem
  float; a divergência é contratual, não de arredondamento, e é reconciliada no `drain` da fila.
- `/busca` com catálogo vazio não renderiza nada abaixo da barra de busca
  (`app/pages/busca.vue:169-252`); o backend chega a mandar `search_empty_state`/`empty_state`
  (`presentation/catalog.py:274-276`).
- `shopman/storefront/presentation/catalog.py:56-61` — `get_channel_listing_ref()` devolve `None` em qualquer
  exceção, e `api/catalog.py:47-48` alimenta isso em `published_products`, que **derruba o join de listing**
  quando o ref é falsy (`catalog_context.py:82-90`): um canal mal configurado publica todo produto
  `is_published` com 200.
- `shopman/shop/services/fomo.py:59-64` inicializa `available_qty = 0` e engole exceção; `presentation/fomo.py:156-175`
  trata `<= 0` como esgotado → uma falha de leitura de estoque vira prova social de urgência falsa.
  Latente enquanto ninguém consome FOMO.
- Strings longas sem clamp: `promotion_label` (`ProductTile.vue:84`, `[sku].vue:252`), `customer_name`
  (`index.vue:255`), `title`/`message` de notice (`index.vue:212-215`), `label`/`description` de seção
  (`menu.vue:456-464`), `sku` no fallback de imagem (`ProductImageFallback.vue:24`).
  (`name` e `short_description` **estão** com `line-clamp-2`.)
- `shopman/storefront/api/availability.py:120-140` — cliente logado sem telefone no cadastro recebe 400
  **sem `field`**, e `StockNotifyButton.vue:59-63` roteia isso para um toast genérico: o sininho falha para
  sempre sem oferecer o campo de telefone.

---

## Inventário de endpoints

`auth` = classes de autenticação DRF declaradas. `[]` significa que `request.user` é **AnonymousUser**
mesmo com sessão Django válida (impacta `key="user_or_ip"` — ver P1-1).

| Rota (`/api/v1/…`) | Método | auth DRF | Consumidor Nuxt | Estado |
|---|---|---|---|---|
| `storefront/home/` | GET | `[]` | `pages/index.vue` | ⚠️ notice `global` descartada (P1-12); muito campo morto |
| `storefront/menu/` · `storefront/menu/<col>/` | GET | `[]` | `pages/menu.vue`, `busca.vue`, `colecao/[ref].vue` | ⚠️ happy hour (P1-3), coleção vazia sem nome (P1-13) |
| `storefront/products/<sku>/` | GET | `[]` | `pages/produto/[sku].vue` | ⚠️ `has_any` some (P0-5); 404 tardio (P1-4) |
| `storefront/cart/` | GET | `[]` | `useCartState`, `sacola.vue`, `useShopmanCsrfHeaders` | ✅ |
| `storefront/checkout/` | GET | `[]` | `pages/finalizar.vue` | ⚠️ `auth_action.href` morto (P2) |
| `storefront/client-error/` | POST | `[]` | `utils/clientErrorReport.ts` | ⚠️ 429 com corpo vazio |
| `cart/skus/<sku>/` | PUT | Session | `useCartState.setSkuQty` | ⚠️ `summary`/`line` mortos e errados (P2); 429 compartilhado (P1-1) |
| `cart/coupon/` | POST/DELETE | Session | `useCartState.applyCoupon/removeCoupon` | ✅ |
| `checkout/` | POST | Session | `finalizar.vue:917` | ⚠️ 409 não recarrega o carrinho (P1-6) |
| `checkout/draft/` | PATCH | Session | `finalizar.vue:579` | ✅ |
| `checkout/loyalty/` | PATCH | Session | `finalizar.vue:101` | ✅ |
| `offers/<ref>/claim/` | POST | Session | `pages/oferta/[ref].vue` | ✅ (modelo correto de conflito 409) |
| `orders/<ref>/reorder/` | POST | Session | `useReorder` | 🔴 idempotência (P0-1), conflito inalcançável (P0-4), `skipped` mudo (P2) |
| `tracking/<ref>/` | GET | `[]` | `pedido/[ref]/index.vue` | 🔴 wipe em falha (P0-3); `payment_status` morto; GET que escreve |
| `tracking/<ref>/events/` | SSE | Django session | `useOrderTrackingStream` via `/sse/pedido/<ref>` | ✅ (gate por `request.user`, que existe para cliente logado) |
| `orders/<ref>/cancel/` | POST | Session | `postAction` (href do backend) | ✅ |
| `orders/<ref>/waitlist-confirm/` | POST | Session | `pedido/[ref]/index.vue` | ✅ |
| `orders/<ref>/confirm-received/` | POST | Session | `postAction` | ✅ |
| `orders/<ref>/rate/` | POST | Session | `submitRating` | ⚠️ replay de 24h engole a segunda nota (P0-1) |
| `orders/<ref>/conversation/` | GET | `[]` | — (ManyChat) | ⚪ morto para a loja |
| `payment/<ref>/mock-confirm/` | POST | Session | `pedido/[ref]/index.vue` | ✅ (DEBUG/staging) |
| `availability/<sku>/` | GET | `[]` | — | ⚪ morto + vaza SKU rascunho (P1-5) |
| `availability/<sku>/notify/` | POST | Session | `StockNotifyButton.vue` | ⚠️ 400 sem `field` (P2) |
| `fomo/<sku>/` · `fomo/<sku>/events/` | GET/SSE | `[]` | — | ⚪ morto + vaza SKU rascunho (P1-5) |
| `catalog/products/` · `/<sku>/` · `catalog/collections/` | GET | `[]` | — | ⚪ morto; contrato divergente (P2) |
| `geocode/reverse/` | POST | `[]` | `AddressPicker.vue` | ⚠️ vaza erro interno com 502 (P1-15) |
| `auth/session/` | GET | `[]` | `middleware/account.ts`, `useShopSession` | ✅ |
| `auth/access/` | POST | `[]` | `pages/a.vue` | ✅ (`@csrf_protect`) |
| `auth/device-check/` · `request-code/` · `verify-code/` | POST | `[]` | `pages/entrar.vue` | ⚠️ 400 no lugar de 429 (P1-7) |
| `auth/trust-device/` | POST | `[]` | `pages/entrar.vue` | 🔴 sem CSRF (P1-11) |
| `auth/logout/` | POST | `[]` | `conta/index.vue` | 🔴 sem CSRF (P1-11); falha silenciosa (P1-10) |
| `auth/handoff/` | POST | Session | `useBrowserHandoff` | ✅ |
| `auth/passkey/register/options|register|login/options|login` | POST | Session / `[]` | `usePasskey` | ⚠️ 403 vira estado vazio (P1-8) |
| `auth/whatsapp/start/` | POST | `[]` | `useWhatsAppConfirm`, `useWhatsappVerify` | ⚠️ 429 sem tratamento (P1-10) |
| `account/summary/` | GET | `[]` | `conta/index.vue` | ⚠️ 500/401 → "nenhum pedido" (P1-2) |
| `account/profile/` | GET/PATCH | Session | `conta/perfil.vue`, `entrar.vue` | 🔴 PATCH destrutivo (P0-2); `copy` só no GET |
| `account/addresses/` · `/<pk>/` | GET/POST/PATCH/DELETE | Session | `conta/enderecos.vue`, `finalizar.vue`, `AddressLabelSheet` | ⚠️ P1-2, P1-9, P1-10 |
| `account/favorites/` · `/<sku>/` | GET/POST/DELETE | Session | `useFavoritesState`, `conta/favoritos.vue` | ✅ |
| `account/orders/` | GET | `[]` | `conta/pedidos.vue` | ⚠️ P1-2 |
| `account/orders/active/` | GET | `[]` | `useShopSession` | ⚠️ 200 `{count:0}` para não autenticado |
| `account/preferences/food|notifications/` | POST | Session | `conta/preferencias.vue` | ⚠️ 400 sem `field` |
| `account/passkeys/` · `/<id>/` | GET/DELETE | Session | `conta/seguranca.vue` | ⚠️ P1-8 |
| `account/devices/` · `/<uuid>/` | GET/DELETE | Session | `conta/seguranca.vue` | ⚠️ P1-2; revoke de terceiro → 200 |
| `account/step-up/` | POST | Session | `conta/seguranca.vue` | ⚠️ sem rate-limit |
| `account/export/` | GET | Session | `conta/seguranca.vue` | ⚠️ dois contratos na mesma URL (P1-16) |
| `account/delete/` | POST | Session | `conta/seguranca.vue` | ⚠️ corpo de resposta ignorado |

---

## Verificado e limpo

Coisas que procurei e **não** encontrei — para ninguém reauditar:

- **Dinheiro bate ponta a ponta.** `grand_total_q = subtotal_q + delivery_fee_q`
  (`shopman/shop/projections/cart.py:284`) e `_ensure_total_matches` compara com a soma de **todos** os itens
  da sessão (`shopman/shop/services/checkout.py:116-141`), que inclui a linha `__DELIVERY_FEE__` mantida em
  sincronia pelo modifier (`shopman/shop/modifiers.py:1071-1112`) — os dois números coincidem. Resgate de
  pontos e cupom reduzem `line_total_q` antes da soma (`modifiers.py:1324-1334`), então também entram.
  O front manda `cart.grand_total_q` como baseline (`finalizar.vue:924`) e o serializer torna o campo
  **obrigatório** (`api/serializers.py:46`) — não dá para commitar sem baseline.
- **Nenhuma aritmética float sobre centavos.** `formatCentavos` (`app/presentation/cart.ts:9-12`) e
  `priceFromQ` (`app/presentation/seo.ts:27-29`) dividem inteiro por 100 — exato no domínio de um double.
  O backend formata com `Decimal` (`packages/utils/shopman/utils/monetary.py:80-81`).
- **A linha otimista não recalcula o resumo.** `applySkuQty` marca `summary_pending: true` e deixa
  subtotal/total intactos (`app/presentation/cart.ts:180-199`) — o cliente nunca vê um total inventado no
  cliente. (Falta só o atenuador no cabeçalho da sacola, ver P2.)
- **Idempotência do commit funciona.** `finalizar.vue:916,928` mantém o `attemptKey` em erro e só o
  regenera no sucesso; o `idempotency_key` viaja **no corpo**
  (`app/utils/checkoutPayload.ts:49`), que é o caminho que `idempotency_key_from_request` de fato lê —
  por isso o checkout escapa do P0-1.
- **Guardas autoritativos do commit estão todos no servidor:** data no passado, além de `max_preorder_days`,
  dia fechado, expediente encerrado, slot vencido, endereço vazio, zona não coberta
  (`shopman/storefront/api/views.py:143-282`), todos com `{detail, field, errors}` e roteamento de passo no
  front (`finalizar.vue:981-1002` → `checkoutStepForField`).
- **Sem vazamento de existência.** `saved_address_id` de terceiro e ref de pedido de terceiro devolvem 404
  uniforme (`views.py:586-590`, `shopman/shop/services/customer_orders.py:37-47`); o gate do SSE é o mesmo
  (`api/tracking.py:212-236`).
- **Allowlist do BFF cobre tudo.** Os 50 caminhos `/api/v1/...` usados pelo app estão dentro dos 13 prefixos
  de `server/utils/storefrontApiAllowlist.ts`, incluindo a raiz `checkout` (a igualdade sem barra em `:30`).
- **Versão de API é graceful.** `X-API-Version` divergente só gera warning no Nitro, nunca bloqueia
  (`server/utils/apiVersion.ts:20-31`).
- **SSE tem fallback real.** Recusa do Django é 404 (não frame in-band), o `EventSource` morre de vez e o poll
  assume (`api/tracking.py:212-227`, `server/utils/eventStream.ts:52-55`,
  `app/composables/useOrderTrackingStream.ts:39-42`). O `abort` no `close` do cliente derruba o upstream
  (`eventStream.ts:31`). **Ressalva:** se o refetch canônico falhar, cai no P0-3.
- **Estados de rede com retry** existem nas cinco telas de catálogo (`index.vue:157-165`, `menu.vue:409-417`,
  `busca.vue:159-167`, `colecao/[ref].vue:111-119`, `produto/[sku].vue:147-155`), na sacola
  (`sacola.vue:132-140`), no checkout (`finalizar.vue:1061-1066`) e no acompanhamento
  (`pedido/[ref]/index.vue:451-458`).
- **Fila serial de mutações do carrinho** é sólida: rajada de toques não se perde nem chega fora de ordem, o
  estado otimista não é atropelado por fetch passivo, e o `cartIssue` sobrevive à navegação para `/sacola`
  (`app/composables/useCartState.ts:179-195`, `:235-245`, `:288-328`).
- **Cookies do storefront** têm o `Domain` removido no repasse (`server/utils/djangoProxy.ts:44-54`) e o CSRF
  é semeado sob demanda (`:56-80`).
- **`AddressLabelSheet`** resolve mesmo quando fechado por gesto, então o cliente nunca fica preso em
  `/finalizar` com o pedido já criado (`app/components/AddressLabelSheet.vue:65-80`).
