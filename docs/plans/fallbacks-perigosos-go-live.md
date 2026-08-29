# Fallbacks perigosos — inventário para o go-live

> **O princípio.** Em caminho de dinheiro ou de acesso, **a omissão configura o
> comportamento restritivo, e a degradação é ruidosa.** Falhar fechado, ou falhar
> aberto e gritando. Nunca falhar aberto e calado.

Este documento nasceu de um P0 real (pedido `E54` no alpha): o cliente escolheu
cartão, nunca viu a página do Stripe, e a loja anunciou **"Pagamento
autorizado"**. Um minuto depois a confirmação otimista capturava a autorização de
mentira. Pedido pago, pão entregue, zero dinheiro.

O defeito **não** era "existe um mock". Era o padrão que o mock encarnava:

| Camada | Como degradava |
|---|---|
| Default do registry | "ninguém configurou gateway" resolvia para o simulador |
| Default de função | `auto_authorize = config.get("auto_authorize", True)` — permissivo por omissão |
| Guarda de ambiente | `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` só existia num `@register(deploy=True)`, que roda em `manage.py check --deploy` e **nunca** no boot nem por requisição |
| Suíte | três testes **afirmavam** que o cartão do simulador nascia `authorized` — um teste que afirma o bug jamais o pega |

Cada linha abaixo é uma instância viva do mesmo padrão. Ordenado por dano, não
por facilidade.

**Legenda:** ✅ corrigido nesta rodada · 🟨 metade fechada, resto é frente própria · ⬜ aberto, vira frente própria.

---

## Tier 1 — perde dinheiro ou entrega acesso, em silêncio

### 1. ⬜ `EFI_SANDBOX` nasce `true`: todo Pix real cobra num gateway que não recebe

- `config/settings.py:1142` — `os.environ.get("EFI_SANDBOX", "true")`
- `shopman/shop/adapters/payment_efi.py:49` — `return SANDBOX_URL if config.get("sandbox", True) else PRODUCTION_URL`

**Risco: dinheiro.** Permissivo por omissão em duas camadas.

**Hoje, se der errado:** esquecer `EFI_SANDBOX=false` no go-live e todo intent de
Pix nasce em `pix-h.api.efipay`. O QR é estruturalmente válido, o pedido mostra
"aguardando pagamento", e uma confirmação de sandbox fecha o ciclo. Pedido pago,
pão entregue, R$ 0 na conta real. `SHOPMAN_E003`/`E009` conferem só a *presença*
de credencial — nunca o ambiente. É exatamente o buraco do `ALLOW_MOCK`.

**Correção proposta:** `EFI_SANDBOX` sem default. Ambiente de cobrança é decisão
explícita: ausente ⇒ `ImproperlyConfigured` no boot do app (o padrão que o
`doorman` já usa em `apps.py`, ver Tier 4). Enquanto isso não existir, incluir
`EFI_SANDBOX` no `check_payment_adapters` como erro fora de `staging`.

> Não corrigido aqui de propósito: virar o default para `false` faria o dev local
> sem `.env` falar com a Efí de produção — troca um risco por outro. A correção
> certa é "explícito ou não sobe", e ela toca o boot do app, que é frente da Efí.

### 2. ⬜ `FOCUS_NFE_ENVIRONMENT` nasce `homologacao`: nota fiscal sem validade

- `config/settings.py:1072` — `os.environ.get("FOCUS_NFE_ENVIRONMENT", "homologacao").strip().lower() or "homologacao"`
- `shopman/shop/adapters/fiscal_focusnfe.py:204` — `str(config.get("environment") or "homologacao")`
- `config/settings.py:1090` — a NF-e de compras herda o mesmo default

**Risco: fiscal / dinheiro.** Permissivo por omissão, duas vezes na mesma linha.

**Hoje, se der errado:** a emissão *dá certo*, a Focus devolve chave de acesso,
`order.data["nfce_access_key"]` é gravada, a DANFE imprime, o operador acredita
que a venda está documentada — e não há NFC-e no SEFAZ. Cada venda de balcão vira
venda não declarada, descoberta pelo contador, não pelo sistema.

**Correção proposta:** mesma forma do item 1 — ambiente fiscal explícito ou
`ImproperlyConfigured`. E `check_fiscal_adapter` passa a reprovar
`environment=homologacao` quando `SHOPMAN_ENVIRONMENT=production`.

⚠️ A suíte trava a homologação como caminho feliz:
`shopman/shop/tests/test_fiscal_focusnfe.py:40,184,219` afirmam a URL
`homologacao.focusnfe.com.br`. Nenhum teste exige que produção seja alcançável.

### 3. ⬜ `SHOPMAN_EXPOSE_DEBUG_OTP` liga sozinho, e a inferência lê texto livre

- `config/settings.py:98` — `_env_bool("SHOPMAN_EXPOSE_DEBUG_OTP", DEBUG or SHOPMAN_ENVIRONMENT == "staging")`
- `config/settings.py:76-90` — `_default_shopman_environment()` devolve `"staging"` se a **substring** `staging` aparecer em `SHOPMAN_DOMAIN`, `WHATSAPP_STOREFRONT_URL`, `DJANGO_ALLOWED_HOSTS`, `APP_DOMAIN` ou `APP_URL`
- Consumidor: `shopman/storefront/api/auth.py:363-383` põe o código OTP vivo na resposta JSON

**Risco: segurança.** É o bloqueador de go-live já registrado, com um agravante
novo: **a porta abre sozinha por causa de uma string.**

**Hoje, se der errado:** um CNAME esquecido ou um `DJANGO_ALLOWED_HOSTS` que
ainda lista o host de staging vira `SHOPMAN_ENVIRONMENT=staging`, que liga o OTP
de debug, e **qualquer pessoa pede código para qualquer telefone e lê a resposta**
— tomada de conta completa. O guarda `SHOPMAN_E010` lê o *mesmo*
`SHOPMAN_ENVIRONMENT` envenenado, então não dispara.

**Correção proposta:** `SHOPMAN_ENVIRONMENT` deixa de ser inferido de substring —
env explícita, com `ImproperlyConfigured` na ausência fora de `DEBUG`. E
`SHOPMAN_EXPOSE_DEBUG_OTP` nasce `False` sempre, sem herdar de nada.

### 4. ⬜ O adapter de e-mail devolve sucesso enquanto o backend só imprime

- `shopman/shop/adapters/notification_email.py:238-240` — `is_available` devolve `bool(EMAIL_HOST or EMAIL_BACKEND)`
- `config/settings.py:799-802` — `EMAIL_BACKEND` cai no `console.EmailBackend`

**Risco: dinheiro.** É o canal que carrega `payment_requested` (o link de
pagamento) e `purchase_request` (o pedido ao fornecedor).

**Hoje, se der errado:** `EMAIL_BACKEND` é *sempre* verdadeiro (o próprio default
é uma string), então `is_available()` é incondicionalmente `True`. `send()` chama
`send_mail(fail_silently=False)`, o backend de console escreve em stdout e não
levanta, então `send()` devolve `True`. Em
`shopman/shop/services/notification.py:159-175` esse `True` **curto-circuita a
cadeia inteira de fallback** — SMS e WhatsApp nunca são tentados. O cliente nunca
recebe o link de pagamento; o log diz "Email sent".

**Correção proposta:** `is_available` passa a exigir um backend que realmente
entregue (`EMAIL_HOST` configurado **e** backend ≠ console/locmem/dummy). Adapter
inerte devolve `False`, para a cadeia seguir — é o que o
`otp_sms_comtele.py:51-56` já faz certo.

> **Não corrigido aqui:** é da frente de notificação de login, conforme
> combinado.

---

## Tier 2 — dinheiro/estoque errado, com rastro

### 5. ✅ Default de pagamento resolvia para o simulador

- `shopman/shop/adapters/__init__.py` — `_DEFAULTS["payment"]` agora é todo `None`
- `config/settings.py` — `card` nasce `payment_stripe`; `pix` nasce `payment_mock` **só em `DEBUG`**, e `payment_efi` fora dele

Era a origem do P0. `_DEFAULTS` sozinho não bastava: a camada de settings é
consultada **antes** e sempre define as duas chaves, então o último recurso nunca
era alcançado. A trava honesta mora nos dois lugares.

### 6. ✅ `payment_mock` autorizava sozinho, e rodava em qualquer ambiente

- `shopman/shop/adapters/payment_mock.py` — `auto_authorize` **removido**; intent nasce `pending`
- `_ensure_simulation_allowed()` em `create_intent` e `capture`: fora de `DEBUG`, sem `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`, levanta
- `_refuse_card()`: **cartão não existe no simulador** — o que precisa ser testado no cartão (redirect, 3DS, recusa, webhook) só existe no gateway, e o Stripe entrega tudo em modo de teste

### 7. ✅ `get_adapter` trocava um método de pagamento por outro, calado

- `shopman/shop/adapters/__init__.py` — `_method_value()` + `_NO_METHOD_FALLBACK`

**Hoje, se desse errado:** pedir `method="card"` numa configuração que só define
`pix` devolvia **o adapter do Pix**, sem log. Latente enquanto o settings define
as duas chaves — mas `Shop.integrations["payment"]` é JSON livre no Admin, com
prioridade máxima: um gestor salvando `{"pix": "...payment_efi"}` fazia toda
cobrança de cartão passar pelo adapter do Pix. Agora método não configurado é
`None`, com `logger.warning`.

### 8. ✅ Gateway real sem credencial escrevia cobrança antes de falhar

- `shopman/shop/adapters/payment_stripe.py` — `StripeNotConfigured`, levantado **antes** de qualquer chamada de rede **e antes** de `PaymentService.create_intent`
- `shopman/shop/adapters/payment_efi.py` — `EfiNotConfigured`, mesma forma

**Hoje, se desse errado:** o Stripe criava a linha no Payman, falhava ao falar com
a API, e a recuperação de `payment.initiate` (`_existing_active_intent`) então
**adotava o intent órfão como se fosse bom**, limpando o erro do pedido. Cobrança
que o gateway nunca viu virava a cobrança do pedido. Na Efí, `client_id` vazio
virava tentativa de autenticação com credencial em branco (ou `KeyError` cru).

### 9. ⬜ `allow_untracked` nasce `True` **e** a leitura falha para o mesmo `True`

- `shopman/shop/config.py:126` — `allow_untracked: bool = True`
- `shopman/shop/services/stock.py:664-671` — `except Exception: return bool(ChannelConfig().stock.allow_untracked)`

**Risco: dado / estoque.** Default permissivo e `except` que devolve o permissivo,
no mesmo lugar.

**Hoje, se der errado:** um canal que não declara `allow_untracked: false` — ou
qualquer canal cuja leitura de config levante — commita pedidos com SKUs que o
catálogo não conhece, `hold_id=None, untracked=True`. E
`lifecycle._verify_holds` (`shopman/shop/lifecycle.py:964`) conta `untracked` como
satisfeito, então a defesa em profundidade também passa. Pedido que não reservou
nada, vendendo estoque que não existe, sem alerta.

**Correção proposta:** dataclass nasce `False`; canal que quer vender sem rastreio
declara. E o `except` devolve o **restritivo**, não o default.

### 10. ⬜ `preorder` nasce `True` e falha aberto do mesmo jeito

- `shopman/shop/config.py:122` · `shopman/shop/services/stock.py:645-654`

**Risco: dado.** PDV e marketplace estão documentados como precisando
`preorder: False`. Um soluço de config vira hold só de demanda com `quant=None` —
promessa de assar algo que ninguém planejou.

### 11. ⬜ `_sku_known_to_catalog` degrada para `True`, e a docstring diz o contrário

- `shopman/shop/services/stock.py:394-406` — docstring: *"Fail-closed: se o contrato não responde, exigimos a reserva."*; código: `except Exception: return True`

**Risco: dado.** No call site `stock.py:136` (`if not allow_untracked and not
_sku_known_to_catalog(...): raise`), `True` **pula** a rejeição de SKU
desconhecido — fail-**open** justamente onde importa. Se o validador levantar, o
portão `allow_untracked=False` para de funcionar.

### 12. ⬜ `_from_shop_integrations` engole qualquer erro de banco

- `shopman/shop/adapters/__init__.py:93-95` — `except Exception: logger.debug(...); return None, False`

**Risco: dinheiro / fiscal.** Um soluço de DB ao ler `Shop.integrations` descarta
em silêncio a escolha explícita do gestor e cai para settings. E `logger.debug`
é invisível em nível normal. **Degradação de configuração de dinheiro tem que ser
`warning`, no mínimo.**

---

## Tier 3 — fail-open em decisão de segurança

### 13. ⬜ O middleware de 2FA do Admin deixa passar quando a URL não resolve

- `shopman/backstage/middleware_2fa.py:26-30` — `except NoReverseMatch: return self.get_response(request)`
- idem `:42-45` — `except NoReverseMatch: return False` ("não precisa verificar")

**Risco: segurança.** Se `admin_2fa_verify` for renomeada, desregistrada, ou o
URLconf falhar ao importar, o portão de 2FA vira no-op e todo `/admin/` abre para
qualquer sessão staff. **Um middleware de segurança que não acha a própria view
de verificação deve dar 500, não acenar para o request passar.**

### 14. ⬜ `notifications.get_backend(None)` resolve para o console

- `shopman/shop/notifications.py:33-37` — `if name is None: name = "console"`
- `shopman/shop/adapters/notification_console.py:45,48-50` — `send`/`is_available` devolvem `True` incondicionalmente

**Risco: dinheiro-adjacente.** Hoje devolve `None` em produção (o console só é
registrado sob `DEBUG`), mas o **desenho** é "não especificado ⇒ o falso".

### 15. ⬜ `_external.inert()` devolve sucesso em qualquer ambiente após `suppress()`

- `shopman/shop/adapters/_external.py:42-43` — `if _suppressed_reason is not None: return True`
- Devolvem **sucesso** no ramo inerte: `notification_sms.py:92-97`,
  `notification_whatsapp.py:97-102`, `notification_manychat.py:230-235`
- `suppress()` (`_external.py:29-32`) é **global de processo, sem exigir `DEBUG`**, e é chamado por `config/management/commands/seed.py:287`

**Risco: dinheiro / dado.** Qualquer caminho que alcance `suppress()` num worker
de produção transforma toda notificação em sucesso silencioso pelo resto da vida
daquele processo. O adapter de OTP acertou (`otp_sms_comtele.py:51-56` devolve
`False` no ramo inerte, para a cadeia seguir) — é o modelo.

### 16. ⬜ O resolver fiscal degrada para "só se o operador pedir"

- `shopman/shop/services/fiscal.py:49-52` — `except Exception: logger.warning(...); return _default_emission_decision(order)`

**Risco: fiscal.** Um typo em `SHOPMAN_FISCAL_EMISSION_RESOLVER`, ou um
`ImportError` dentro de um resolver, reverte em silêncio para "emite só se o
operador marcou" — NFC-e para de sair, venda após venda, sem nada em tela
nenhuma. A própria docstring de `check_fiscal_emission_resolver` reconhece isso —
e o check é `@register(deploy=True)`.

### 17. ⬜ `_payment_idempotency_key_reusable` devolve `True` quando a busca falha

- `shopman/shop/services/payment.py:1233-1237`

**Risco: dinheiro (menor).** `True` = "reusa a chave guardada". Se o intent
daquela chave foi uma falha terminal, um soluço de DB faz o retry reusar uma
chave envenenada no gateway — que repete a falha guardada em vez de criar
cobrança nova, e o cliente não consegue pagar. Falha na direção de *não* cobrar,
por isso Tier 3 — mas é o ramo permissivo escolhido no `except`, em `logger.debug`.

---

## Uma classe acima — quando o permissivo não é esquecimento, é o default do tipo

### 18. 🟨 `Action.idempotency` nasce `"none"`: toda ação nova do PDV nasce sem trava de replay

> **Metade 1 fechada (29/08).** O default virou `"required"` no dataclass, nas duas
> fábricas de ação (`storefront/api/actions.py`, `shop/projections/order_tracking.py`)
> e no fallback da superfície; as 14 ações que legitimamente dispensam trava passaram
> a declarar `"none"` de propósito. O guarda é
> `shopman/shop/tests/test_action_idempotency_contract.py`: ação mutável nova com
> `"none"` reprova o CI, e as oito mutações de caixa estão lá como **dívida nomeada**
> que só pode encolher. **Metade 2 continua aberta** — é ela que fecha o buraco em
> runtime, e é a Onda 2 do WP-00 (Bloco A, P0-A2).

- ~~`shopman/shop/projections/types.py:91` — `idempotency: str = "none"`~~ → `"required"` ✅
- ~~`surfaces/pos-nuxt/app/presentation/actions.ts:64` — `?? "none"`~~ → `?? "required"` ✅
- `shopman/backstage/projections/pos.py:940-1275` — as 29 ações do `_pos_actions`

**Risco: dinheiro.** Extraindo mecanicamente as 29 ações que o PDV oferece, **três**
declaram alguma trava — `close_sale` (`:987`, `required`), `customer_resolve`
(`:1196`, `required`) e `fire_tab` (`:1252`, `client_request_id`). As **oito
mutações de dinheiro do caixa** declaram `none` explicitamente: `open_cash_shift`
(`:1035`), `close_cash_shift` (`:1045`), `cash_movement` (`:1056`), `refund_cash`
(`:1126`), `settle_account` (`:1136`), `request_change` (`:1146`),
`serve_change_request` (`:1156`), `cancel_change_request` (`:1166`). Outras
**sete** nem mencionam o campo e herdam `none` do default — entre elas
`cancel_recent_sale` (`:1022`, POST) e `clear_tab` (`:1219`, DELETE).

> O item foi escrito contra 25 ações e revisado contra 29: entre uma medição e
> outra, a PR #396 (trava de gaveta) acrescentou `drawer_unlock_attempt`,
> `drawer_left_open`, `drawer_block` e `drawer_blind` — as quatro nasceram `none`.
> Não é dinheiro, é trilha de auditoria, e o duplo toque suja a trilha em vez da
> gaveta. Mas é a tese deste item acontecendo em tempo real, sem ninguém errar:
> a ação nova nasce sem trava porque o tipo diz que tudo bem.

**Hoje, se der errado:** o operador toca "Sangria" no 4G do balcão, a gravação
entra e a resposta morre no timeout. Ele toca de novo, porque a tela não mudou. O
livro-caixa aceita as duas linhas e o turno fecha com uma diferença fantasma que
ninguém consegue explicar — o livro é append-only, então a correção é outra linha,
não um desfazer. Em `refund_cash` o mesmo duplo toque paga o cliente duas vezes.

E **não há segunda linha de defesa**: as `UniqueConstraint` que o
`cashman/migrations/0003_entry_one_line_per_order.py` acrescentou depois de um
TOCTOU real cobrem só `sale` e `cod_settled` — os `kind` que têm `order_ref`. O
próprio comentário do modelo (`packages/cashman/shopman/cashman/models/entry.py:223`)
diz por quê: "`order_ref` vazio fica de fora porque não há pedido a que amarrar".
Sangria, suprimento, fundo de troco, devolução e acerto de conta são exatamente os
`kind` sem `order_ref`. A trava de banco que salvou a venda não alcança o caixa.

**Correção proposta:** duas metades da mesma frente.

1. ✅ **Virar o default para o restritivo** — feito em 29/08. `idempotency: str =
   "required"` em `types.py`, o mesmo `?? "required"` em `actions.ts`, e as duas
   fábricas de ação junto (sem elas a inversão seria cosmética: o call site que
   omite o campo herdaria o default DELAS). Ação que legitimamente dispensa trava
   (`customer_lookup`, `reverse_geocode`, `review_sale`, as leituras) declara `none`
   **de propósito**, com a razão escrita na allowlist do teste de contrato — a
   declaração virou decisão registrada em vez de silêncio.
2. **Ligar as oito mutações de caixa no replay que já existe** — mais
   `cancel_recent_sale` e `clear_tab`. `shopman/shop/services/pos.py:273-524` já
   faz claim e replay por `client_request_id`, com ponte para o `IdempotencyKey`
   do orderman (`UniqueConstraint(scope, key)` + `select_for_update`). Não é infra
   nova: é ligar no caixa o que já roda na venda.

> ⚠️ As duas metades não se separam. Hoje o campo é **puramente declarativo** —
> nenhum componente do PDV o lê, e a garantia do `close_sale` vem do serviço, não
> do campo. Virar o default sozinho não fecha nenhum buraco em runtime; o que ele
> faz é impedir que a ação nº 30 nasça insegura sem ninguém perceber.

**Por que isto não é mais um dos 17.** Os itens acima são fallbacks de
**configuração**: alguém esquece uma env e o sistema degrada. Este é permissivo por
**default de dataclass**, e isso é pior — ninguém precisa esquecer nada. A ação
seguinte nasce sem trava por construção, escrita por quem não sabia que o campo
existia. A versão dura do princípio que abre este documento: **o default de um
campo de segurança tem que ser o valor restritivo, senão a omissão vira política.**

Origem: `docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md`,
Bloco A (achados P0-A1, P0-A2, P1-A3).

---

## Tier 4 — checks de deploy que precisariam valer em runtime

Todos em `shopman/shop/checks.py`, com `@register(deploy=True)`: rodam em
`manage.py check --deploy` e **nunca** no boot nem por requisição.

| Check | Valida | Buraco de runtime |
|---|---|---|
| `check_secret_key` (E001) | `SECRET_KEY` ≠ default de dev | ⚠️ **Sim.** O default é literal (`config/settings.py:71`), e essa chave deriva o HMAC do OTP, do PIN, do link de acesso e da assinatura do comprovante de caixa. Chave conhecida = OTP/PIN/comprovante forjáveis |
| `check_allowed_hosts` (E002) | sem `*` | ⚠️ **Sim.** Default é `"*"` (`:104`) |
| `check_payment_adapters` (E003/W006/E009) | adapters + credenciais | ✅ Fechado para o mock (runtime em `payment_mock`). ⚠️ **Não cobre `EFI_SANDBOX` (item 1) nem chave test-vs-live do Stripe** |
| `check_debug_otp_exposure` (E010) | OTP de debug só em dev/staging | ⚠️ **Sim, e pior:** lê o mesmo `SHOPMAN_ENVIRONMENT` envenenável (item 3), então não dispara |
| `check_shared_cache_backend` (E006) | Redis em prod | ⚠️ **Sim.** LocMem em prod faz o `django-ratelimit` virar por-worker: os limites de OTP/login multiplicam pelo número de workers |
| `check_fiscal_emission_resolver` (E013) | resolver configurado | ⚠️ **Sim** (item 16). E não checa `FOCUS_NFE_ENVIRONMENT` |
| `check_operator_cookie_domain` (E014) | hosts sob o domínio-pai | ⚠️ Leve — divergência quebra CSRF/sessão em silêncio |
| `check_webhook_tokens` (E004) | tokens EFI/iFood | Não — os endpoints já falham fechados |
| `check_guestman_webhook_secret` (W009) | segredo ManyChat | Não — `Gates.provider_event_authenticity` falha fechado em runtime |
| `check_doorman_access_link_api_key` (E008) | chave do link de acesso | **Não — é o padrão certo.** `packages/doorman/shopman/doorman/apps.py:23-33` levanta `ImproperlyConfigured` **no boot**. É o modelo para consertar E001/E002/E006 |
| `check_staging_autopilot` (E012) | autopilot fora de prod | **Não — padrão certo.** `services/staging_autopilot.py:56-73` reconfere em runtime |
| `check_mock_capture_exposure` (E015) | captura simulada fora de prod | **Não — padrão certo.** `services/payment.py:1090-1095` reconfere por requisição **e** exige que o adapter daquele método seja o simulado |

**Regra a adotar:** todo check de deploy cujo invariante é de dinheiro, acesso ou
fiscal precisa de um par em runtime — no boot (`AppConfig.ready`, como o doorman)
ou no ponto de uso (como `mock_capture_allowed`). O check de deploy vira
conferência antecipada, não a única trava.

---

## Flags de simulação/bypass — o que acontece se vazarem

| Flag | Default | Trava em runtime | Se vazar para produção |
|---|---|---|---|
| `EFI_SANDBOX` | **`true`** | **nenhuma** | Pix cobra onde não entra dinheiro (item 1) |
| `FOCUS_NFE_ENVIRONMENT` | **`homologacao`** | **nenhuma** | NFC-e sem validade fiscal (item 2) |
| `SHOPMAN_EXPOSE_DEBUG_OTP` | **herda de env inferida** | mesma env envenenável | OTP na resposta ⇒ tomada de conta (item 3) |
| `SHOPMAN_PIX_ADAPTER` | `payment_mock` **só em DEBUG** ✅ | `_ensure_simulation_allowed` ✅ | — |
| `SHOPMAN_CARD_ADAPTER` | `payment_stripe` ✅ | `_refuse_card` + `StripeNotConfigured` ✅ | — |
| `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` | `False` | `payment_mock` ✅ | Reabre o simulador de Pix |
| `SHOPMAN_EXPOSE_MOCK_CAPTURE` | `False` | por requisição ✅ | Botão "marcar meu pedido como pago" para o cliente |
| `SHOPMAN_MOCK_PIX_AUTO_CONFIRM` | `False` | via `payment_mock` ✅ | Todo Pix se autoconfirma sem dinheiro |
| `SHOPMAN_STAGING_AUTOPILOT` | `False` | ✅ | Pedidos andam sozinhos: cobram, baixam estoque, emitem nota |
| `SHOPMAN_MENUBOARD_PUBLIC` | `false` | por requisição ✅ | Publica tabela de preços do PDV + SSE de estoque |
| `SHOPMAN_ADMIN_REQUIRE_2FA` | **`False`** | fail-open em `NoReverseMatch` (item 13) | 2FA do Admin nasce desligado e o caminho de enforcement tem passagem |
| `SHOPMAN_ENABLE_CONSOLE_NOTIFICATION_ADAPTER` | `False` | nenhuma | Registra em produção o adapter que sempre devolve `True` |

⚠️ **No alpha hoje** (spec vivo da DO): `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true`,
`SHOPMAN_EXPOSE_MOCK_CAPTURE=true`, `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true` (8s),
`SHOPMAN_EXPOSE_DEBUG_OTP=true`, `EFI_SANDBOX=true`. Todas legítimas para o alpha
e **todas na lista de remoção do go-live** —
ver `docs/runbooks/go-live-preflight.md`.

---

## O que a suíte precisa parar de fazer

O bug sobreviveu a várias rodadas de QA porque **os testes afirmavam o
comportamento permissivo**. Casos encontrados:

- `shopman/shop/tests/test_pix_confirmation_mock.py` — três asserções
  `status == "authorized"` num intent recém-criado no simulador, uma delas num
  teste de **cartão**. ✅ corrigidas nesta rodada.
- `shopman/shop/tests/test_fiscal_focusnfe.py:40,184,219` — travam a URL de
  homologação como caminho feliz. ⬜
- `config/settings_test.py` — pinos que descrevem o ambiente de teste
  (`SHOPMAN_EXPOSE_DEBUG_OTP=True`, `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True`).
  Legítimos, **desde que** a porta fechada tenha teste próprio com
  `@override_settings` — é o que
  `shopman/shop/tests/test_payment_never_authorized_without_gateway.py` faz.

**Regra:** todo default permissivo num caminho de dinheiro/acesso precisa de um
teste que exercite a **porta fechada**, não só a aberta.
