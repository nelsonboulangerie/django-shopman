# Prontidão para alpha — levantamento de 2026-08-12

> Varredura verificada no código, no git e no spec LIVE do DigitalOcean. Não é
> releitura de memória: cada linha abaixo saiu de um comando rodado hoje.
> Complementa a [ALPHA-READINESS-AUDIT](../plans/ALPHA-READINESS-AUDIT.md), que
> continua factualmente correta — nada do que ela afirma envelheceu.

## Veredito

**O alpha não está bloqueado por código.** A suíte está verde, o lint está limpo,
as migrações estão em dia e os caminhos críticos (checkout, pagamento,
acompanhamento, cascata, SSE) já foram exercitados de ponta a ponta no staging.

O que falta é de três naturezas, e só uma delas é trabalho de engenharia:

1. **Um gate que apagou sem ninguém ver** — `gateways.local` está vermelho há
   ~3 semanas (achado novo, §3). É o único item técnico que merece conserto
   antes de chamar gente.
2. **Combinados com o testador** — o staging é 100% mock; se isso não for dito,
   cada simulação vira um falso furo.
3. **Insumos do dono** — credenciais e QA físico. Não são código.

---

## 1. Estado do `main` — verde

| Verificação | Resultado |
|---|---|
| `make test` | ✅ **4.192 passed, 16 skipped**, 28 subtests, 197s |
| `make lint` (ruff + Admin/Unfold) | ✅ **All checks passed** + 254 testes de Admin canônico |
| `makemigrations --check --dry-run` | ✅ **No changes detected** |
| Working tree | ✅ limpo, **sem stash** |

⚠️ **A worktree principal está 8 commits atrás do `origin/main`.** O que falta
puxar é a frente da gaveta do PDV e o leitor de crachá (PRs #133/#134, já
mergeados). Um deles, `e8c5c420`, faz uma coisa que importa: adiciona
`test-drawer-agent` à cadeia do `make test`. Ou seja — **os 351 testes do agente
da gaveta não rodaram no número acima**, porque localmente eles ainda estão fora
do runner. Puxar o main resolve.

```bash
git pull --ff-only origin main && make test
```

## 2. Branches e trabalho pendente

**Aberto de verdade (3 itens):**

| Item | Estado | Ação |
|---|---|---|
| [PR #135](https://github.com/pablondrina/django-shopman/pull/135) — crachá na tela | ✅ **4 checks verdes**, 1 commit à frente | Pronto para merge |
| [PR #129](https://github.com/pablondrina/django-shopman/pull/129) — rename de ref | 🔴 vermelho, mas **só por estar 28 commits atrás** | Rebase resolve, ver abaixo |
| `claude/zen-dijkstra-9db6b0` → `263f3036` | ⚠️ **órfão: 1 commit sem PR aberto** | Abrir PR ou descartar |

O vermelho do #129 **não é um defeito do PR**: o job falha em
`makemigrations --check` pedindo `shop/0011_alter_campaign_audience_rules.py` —
migração que **já existe no `main`** (o check local passa limpo). É defasagem, não
regressão.

O commit órfão `263f3036` corrige um domínio inventado cravado no agente da
gaveta (`pdv.boulangerie.com.br` é o certo). Nasceu depois do merge do #134 e
ficou sem PR — é o tipo de conserto que se perde.

**Branches mortas (0 commits à frente do `origin/main`) — podem ser apagadas:**
`feat/f3b-absorb-showcase`, `plan/campaign-evolution`, `fix/pdv-stress-findings`,
`claude/amazing-hopper-d1ee66`, `claude/festive-wing-1ca6c1`, `alpha-readiness`,
e `claude/jovial-mahavira-5bcc47` (seu commit entrou no main como `164ef10d`).

Há **7 worktrees** ativas; 5 apontam para branches já absorvidas.

## 3. 🔴 Achado novo — o gate de gateway apagou em silêncio

`make release-readiness` **falha hoje**, e não pelos bloqueios externos
conhecidos:

```
counts: passed=4 failed=1 blocked_external=3
- [FAIL] gateways.local: At least one local gateway fixture failed.
         4 failed / 1 passed
```

As 4 fixtures que caíram são exatamente as que provam a correção de dinheiro:

- `efi/pix_duplicate_webhook`
- `efi/pix_late_after_cancel_refund`
- `stripe/payment_succeeded_duplicate_webhook`
- `stripe/refund_cumulative_out_of_order`

Todas com o mesmo erro: `ValidationError: [unknown_sku] GATEWAY-SMOKE-SKU não
está no nosso catálogo.`

**Diagnóstico: a fixture está defasada, o produto está certo.** O guard que
recusa SKU fora do catálogo (`allow_untracked=False`,
[`shop/services/stock.py:431`](../../shopman/shop/services/stock.py)) entrou em
**2026-07-24** (`24d91bd5`, gate de SKU untracked por canal). O smoke, em
[`gateway_smoke.py:397`](../../shopman/backstage/services/gateway_smoke.py),
injeta um SKU sintético com preço arbitrário — coisa que o servidor,
corretamente, **não aceita mais** de ninguém.

O que dói não é o erro: é que a última leitura verde foi **2026-06-26**, um mês
antes do guard entrar. **Durante ~3 semanas o gate que atesta webhook duplicado,
refund e evento fora de ordem não atestou nada** — e ninguém soube, porque
`release-readiness` não está em nenhuma cadeia de CI.

### ✅ Consertado (2026-08-13)

A fixture ganhou **catálogo próprio** (`_ensure_catalog`), criado dentro da
transação que já sofre rollback — então o smoke roda em banco limpo e **não passa
a depender do seed**. Só o contrato do Offerman, nenhum Quant no Stockman: item
conhecido pelo catálogo e não rastreado passa como `untracked` sem exigir reserva.
O guard não foi tocado, e as fixtures seguem exercitando a **mesma** política do
canal web de produção (`allow_untracked=False`) em vez de afrouxá-la para si.

Ao consertar, apareceu um segundo achado que só o primeiro escondia: com o
produto no catálogo, as 4 fixtures passaram a falhar com
`PaymentError: [invalid_amount] Valor deve ser positivo`. Motivo — **o preço sai
do catálogo, nunca do chamador**, e o produto novo não tinha preço de canal. Foi
preciso um `Listing` (cuja `ref` casa com `Channel.ref`) com o preço.

Medido para provar quem manda: com o `Listing` a **1234** e a linha da sacola
pedindo **1000**, o pedido fecha em **1234** (`captured_q: 1234`,
`refunded_q: 1234`). Ou seja, o `unit_price_q` que a fixture mandava era **morto
e enganoso** — foi removido.

**Resultado:** `gateways.local` **5 passed / 0 failed**, de volta à baseline de
26/06.

### 🔒 Causa-raiz fechada: o gate agora está em CI

Consertar a fixture não bastava — o que deixou o gate apagar 3 semanas foi ele
**não estar em nenhum workflow**. `make release-readiness` virou passo do
**Runtime Gate**, em **modo não estrito**: falha só em falha real e tolera os 3
bloqueios que dependem de credencial externa (verificado: exit 0 hoje). Sem isso,
o próximo guard novo apaga a fixture de novo e ninguém vê.

## 4. Features críticas — o que já foi exercitado de verdade

Da auditoria (§7–§8), com pedidos reais no staging:

| Frente | Estado |
|---|---|
| **Checkout** | ✅ `WEB-260811-Q84` fechado com `expected_total_q` batendo com a tela |
| **Cascata completa** | ✅ `WEB-260811-Q02`: Recebido → Aceito → Pago → Preparo → Pronto → Concluído |
| **SSE ao vivo** | ✅ `WEB-260812-D14`, dois eventos empurrados sem refresh |
| **Virada do dia** | ✅ passou sozinha |
| **Desconto de funcionário** | ✅ decidido e implementado (`EmployeeRule.pickup_only`) |
| **PDV** | ✅ achados do teste de estresse corrigidos (`cd4b41c1`) |
| **Pagamento real** | ❌ mock — a cascata foi provada, o gateway não |
| **Lado do operador** | ⚠️ só o piloto automático avançou; aceitar/recusar e bump do KDS **nunca foram tocados por humano** |
| **Cupom, happy hour, D-1** | ⚠️ não exercitados |
| **QA físico** (térmica, som do KDS, gaveta, crachá) | ❌ nada testado no balcão |

O buraco de cobertura mais honesto é o **lado do operador**: tudo que se viu foi
o robô do staging apertando os botões. Ninguém provou que uma pessoa consegue
recusar um pedido.

## 5. Staging vs produção

> ⚠️ **Correção (2026-08-13).** A primeira versão desta seção afirmava que "não
> existe app de produção na DigitalOcean". **Está errado**, e o erro foi de
> método: rodei `doctl` no contexto `shopman-staging-deploy` e li "nenhuma app
> chamada produção" como "nenhuma produção". Duas apps de produção estão no ar há
> anos, e o domínio de produção já serve o Shopman.

**O que está no ar em produção hoje:**

| App | Criada | Hostname | Estado |
|---|---|---|---|
| `nb-site` | 2021 | `www.nelsonboulangerie.com.br` | ✅ HTTP 200 — landing page |
| `nb-catalog-app` | 2023 | `menu.nelsonboulangerie.com.br` | ✅ HTTP 200 — o menu que os clientes usam |

**E o Shopman já está no domínio de produção.** A app `shopman-staging`
reivindica, no próprio spec, **7 hostnames de `boulangerie.com.br`** como ALIAS —
todos respondendo HTTP 200:

`gestor.` · `pdv.` · `kds.` · `prod.` · `central.` · `mkt.` · `api.`

O enunciado correto é mais estreito e mais útil: **não existe um deployment
separado de produção do Shopman.** O domínio de produção aponta para a app cujo
nome diz "staging" e cuja config é de staging — mock de pagamento, `LogSender`,
autopilot ligado, OTP na tela. Isso é deliberado no pré-go-live (a auditoria já
tratava `gestor.boulangerie.com.br` como o gestor de staging), mas muda o que
"go-live" significa: **não é criar app e apontar DNS.** É escolher entre

- **(a)** virar os envs desta app para real — o DNS já está pronto, ou
- **(b)** criar uma segunda app e repontar 7 ALIAS + os domínios de staging.

⚠️ **A loja do cliente é a única superfície sem hostname de produção.** O apex
`boulangerie.com.br` **não tem registro web nenhum** — só MX, SPF, DKIM, DMARC e
verificações. Todo aparelho de operador tem seu subdomínio; a loja não tem
endereço. Se o testador for orientado a ir em "boulangerie.com.br", ele não chega
a lugar nenhum.

**Endereço a usar no convite do alpha** (medido em 2026-08-13):

| Hostname | Serve | Estado |
|---|---|---|
| `staging.nelsonboulangerie.com.br` | a loja do cliente | ✅ HTTP 200, 1,3s |
| `api.boulangerie.com.br` | a API do Django | ✅ `/health/` e `/ready/` 200 |
| `boulangerie.com.br` (apex) | nada | ❌ sem registro web |

Spec LIVE de hoje confirma a §3 da auditoria — nada mudou desde 11/08:

| Env | Valor | Efeito |
|---|---|---|
| `SHOPMAN_PIX_ADAPTER` | `payment_mock` | QR não é de gateway nenhum |
| `SHOPMAN_CARD_ADAPTER` | `payment_mock` | não é Stripe test |
| `DOORMAN_MESSAGE_SENDER_CLASS` | `LogSender` | **nenhum SMS sai** |
| `SHOPMAN_EXPOSE_DEBUG_OTP` | `true` | o código aparece na tela — é o que faz o login funcionar |
| `SHOPMAN_STAGING_AUTOPILOT` | `true` | o pedido anda sozinho |

Credenciais **presentes** no spec mas não usadas: Efí (sandbox), Stripe (test),
Comtele (rota 17), iFood, ManyChat, Meta. **Trocar três envs torna Pix, cartão e
SMS reais — custo zero de código.**

Credenciais **genuinamente ausentes**: `MANYCHAT_WEBHOOK_SECRET` e Focus NFe
(homologação).

## 6. Segurança e hardening — sólido

O boot recusa configuração insegura por **12 system checks** (`SHOPMAN_E001`–`E012`):
SECRET_KEY default, `ALLOWED_HOSTS` com `*`, mock de pagamento sem permissão
explícita, webhook sem token, Redis ausente, SQLite em produção, adapter real sem
credencial, **OTP de debug fora de não-produção**, e **piloto automático em
produção**. O autopilot ainda se cala por conta própria, além do check.

Pendências (todas do dono, nenhuma é código):

- **2FA do Admin**: existe e é testado; falta enrollar operadores e virar
  `SHOPMAN_ADMIN_REQUIRE_2FA`.
- **IP allowlist**: decidido como ingress (Cloudflare), não middleware. Faltam as faixas.
- **`admin/admin` do staging**: precisa morrer antes de produção, via `bootstrap_admin`.
- **Faxina**: `guia-credenciais-broadcast.pdf` ainda está na raiz do projeto
  (gitignored, mas no disco). `_to_delete/` já saiu.

## 7. Seed — pronto

- ✅ `omotenashi.seed`: **11/11 cenários** com dados.
- ✅ 59 SKUs do Cardápio 2027, coleções, bundles, receitas, personas, cupons,
  loyalty, zonas de entrega, slots, encomenda, happy hour, D-1.
- ✅ `--profile qa` determinístico.
- ⚠️ Fotos vêm de `raw.githubusercontent.com` (10) e Unsplash (25). O GitHub não
  é CDN e limita hotlink — se estrangular no alpha, 10 produtos ficam sem foto.

---

## Ordem de ataque

**Antes de chamar testadores:**

1. ✅ `git pull --ff-only` — main em `97da26d1`, agente da gaveta na cadeia do `make test`.
2. ✅ **`gateways.local` consertado** e pendurado no Runtime Gate (§3).
3. Mergear o #135, rebasear o #129, resolver o commit órfão `263f3036`.
4. Podar as 7 branches mortas.
5. ⚠️ **Decidir o endereço da loja para o alpha** (§5). O apex não resolve. Ou se
   cria o registro do apex, ou o convite manda o testador para
   `staging.nelsonboulangerie.com.br`. O que não pode é o convite dizer
   "boulangerie.com.br" — ali não tem nada.

**Combinar com os testadores** (não é código, mas define se a rodada presta):

6. Avisar que Pix/cartão são "Simular pagamento" e que a entrada é por
   **"Usar outro número"** — senão a pessoa manda o código no WhatsApp e nada volta.

**Decisão do dono:**

7. Sair do mock? Três envs e as credenciais já estão lá. ⚠️ Testar a Comtele
   antes — estava em HTTP 500 em 10/08.
8. Sessão com humano no gestor: aceitar, recusar, iniciar preparo, bump no KDS.
9. QA físico do balcão: térmica, gaveta, crachá, som do KDS.
10. **Go-live = (a) virar os envs desta app ou (b) app separada + repontar 7
    ALIAS?** (§5) Decisão de arquitetura, não de data.

**Não bloqueia alpha:** NFC-e (obrigação legal de go-live), homologação iFood de
produção, Fiscalman S5, Buyman fases 2–4.
