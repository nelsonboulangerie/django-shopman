# 06 — Checkout: Pix como padrão silencioso

**Tarefa nº06** · Árvore canônica: `/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration`
**SHA base:** `f0ffd02fde765493d734bae93a72bb361ed28fcf` (2026-09-29 15:36 UTC, `Merge pull request #1261`)
Todo `path:line` abaixo é dessa árvore. Método: leitura estática (nenhum arquivo de código foi tocado; só este relatório foi escrito).

---

## 1. Resumo executivo

1. **[FATO]** O Pix não é "uma opção pré-marcada por descuido": ele é o **primeiro item da lista** de `ChannelConfig.payment.method`, e o projeto transforma *posição na lista* em *default* em três lugares independentes — a projection marca `is_default=(i == 0)` (`shopman/storefront/presentation/checkout.py:445-452`), a projection calcula `default_payment_method` e o formulário Nuxt escreve esse valor em `state.payment_method` na hidratação (`surfaces/storefront-nuxt/app/pages/finalizar.vue:743-745`).
2. **[FATO]** A lista do canal `web` é `["pix", "card"]` (`config/management/commands/seed.py:6147`, herdada por `_remote_config` no canal `web` em `:6198-6203`). A ordem **é deliberada** — mas deliberada para o **concierge do WhatsApp** ("Pix primeiro, cartão segundo", `docs/plans/WHATSAPP-CONCIERGE-PLAN.md:138-140`), onde o bot **pergunta** a forma; o formulário web herdou a ordem e a converteu em silêncio em escolha.
3. **[FATO]** O **backend não inventa** forma de pagamento: `payment_method` é campo obrigatório do serializer (`shopman/storefront/api/serializers.py:35`), o `_post` revalida contra a lista do canal (`shopman/storefront/api/views.py:161-165`) e há teste travando 400 para vazio/ausente/inválido (`shopman/storefront/tests/api/test_checkout_principal_boundary.py:89-104`). **O default é 100% decisão de front**, alimentada pela projection.
4. **[FATO]** Confirmar em Pix sem intenção **cria pedido de verdade** e **reserva estoque dentro da transação do commit** (`shopman/shop/lifecycle.py:180-219`, `shopman/shop/services/stock.py:40-90`). Mas **nenhuma cobrança nasce no checkout**: no canal web o Pix é `post_commit`, então `payment.initiate` só roda no **aceite do operador** (`shopman/shop/lifecycle.py:803-810` e `:445-463`).
5. **[FATO]** O que nasce no commit é o alerta de pedido esquecido: `order.stale_new_alert` com `available_at = agora + 10min` (`shopman/shop/lifecycle.py:768-779`, `stale_new_alert_minutes: 10` no seed `:6146`).
6. **[FATO]** A reserva de estoque do pedido tem backstop de **48h** (`shopman/shop/services/stock.py:919` e `:928-958`) — não some em 30 min como o hold de carrinho.
7. **[FATO]** Depois do aceite: a cobrança Pix vale **10 min** (`payment.timeout_minutes: 10`, seed `:6147`), o `payment.timeout` é armado junto do intent (`shopman/shop/services/payment.py:2414-2445`, chamado em `:396-397`) e, vencido, **cancela o pedido** e devolve estoque + cupom + fidelidade (`shopman/shop/handlers/payment_timeout.py:54-97`).
8. **[FATO]** **Não é reversível na forma.** Não existe rota nem serviço para trocar a forma de pagamento de um pedido existente: o cliente só tem `cancel` (`shopman/storefront/api/urls.py:166`); o Gestor tem 14 rotas `orders/<ref>/*` (`shopman/backstage/api/urls.py:593-661`) e nenhuma de pagamento; o `order_edit` só reescreve `payment` quando **muda o valor** (`shopman/shop/services/order_edit.py:904-993`). **É a mesma lacuna que a tarefa nº07 nomeia** — e ela é o que torna este defeito caro.
9. **[FATO]** No mesmo domínio, **três posturas diferentes**: o formulário web pré-seleciona; o concierge **exige** escolha explícita (`shopman/storefront/concierge/tools.py:1032` e `:1042-1043`); o PDV **começa vazio** (`surfaces/pos-nuxt/app/composables/usePosSale.ts:649`). O formulário web é a exceção.
10. **[FATO]** O rótulo "(padrão)" que a queixa descreve **não existe na tela**: `is_default` é calculado no backend e nunca é renderizado (nenhum uso em `surfaces/storefront-nuxt/app/pages/finalizar.vue`; o único "Padrão" visível é o de endereço em `conta/enderecos.vue:158`). O testador deduziu "padrão" de um rádio já marcado.

---

## 2. Achados

### A1 — Onde o default nasce: posição na lista vira escolha, em três saltos [FATO]

| Salto | Arquivo:linha | O que faz |
|---|---|---|
| 1. Config | `shopman/shop/config.py:92-120` | `Payment.method: str \| list[str]`; `available_methods` devolve a lista **na ordem declarada**. **Não existe** chave `default_method` na dataclass. |
| 2. Projection | `shopman/storefront/presentation/checkout.py:429-452` | `_payment_methods()` → `is_default=(i == 0)`; o rótulo vem de `payment_method_label()` (`shopman/storefront/presentation/status.py:86-88`). |
| 2b. Default | `shopman/storefront/presentation/checkout.py:249-255` | `default_payment_method = remembered if remembered in refs else payment_methods[0].ref`. |
| 3. Front | `surfaces/storefront-nuxt/app/pages/finalizar.vue:743-745` | `if (!methods.some(m => m.ref === state.payment_method)) state.payment_method = value.default_payment_method \|\| methods[0]?.ref \|\| ''` — **escreve a escolha no estado do formulário sem o cliente ter tocado em nada**. |

O rádio é renderizado com `v-model="state.payment_method"` (`finalizar.vue:1839-1856`), então sai marcado já no primeiro render.

**[INFERÊNCIA]** A dupla fallback (`default_payment_method` **ou** `methods[0]?.ref`) garante que o campo *nunca* fica vazio, mesmo que o backend passe a devolver `""`. É esse `||` que fecha a porta de uma correção só no backend.

### A2 — De onde vem `["pix", "card"]`, e por que a ordem existe [FATO]

```
config/management/commands/seed.py:6143  _remote_config = {
config/management/commands/seed.py:6146      "confirmation": {"mode": "manual", "stale_new_alert_minutes": 10},
config/management/commands/seed.py:6147      "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
config/management/commands/seed.py:6198      (STOREFRONT_REF, "Loja online", 2, True, {**_remote_config, ...}),
config/management/commands/seed.py:6180      _whatsapp_config["payment"] = {"method": ["pix", "card"], "timing": "at_commit", ...}
```

A justificativa escrita vive no plano do concierge: *"**Pix primeiro, cartão segundo.** 80% dos brasileiros têm o Pix como meio principal (CNDL/SPC, 01/2026)"* (`docs/plans/WHATSAPP-CONCIERGE-PLAN.md:138-140`). No concierge isso governa **a ordem em que o bot oferece**, não uma escolha feita pelo cliente — `review_order` só aceita `pay=` explícito e devolve `missing: ["payment_method"]` se o cliente não disse.

**[INFERÊNCIA]** O default do formulário web é um **efeito colateral não intencional** de compartilhar `_remote_config` entre web e WhatsApp. Não encontrei nenhum plano, ADR ou comentário que decida "no formulário web o Pix vem marcado".

### A3 — O backend é estrito; a suavidade é do front [FATO]

- `shopman/storefront/api/serializers.py:35`: `payment_method = serializers.CharField(max_length=32)` — `required` e sem `allow_blank`.
- `shopman/storefront/api/views.py:161-165`: `if validated_data["payment_method"] not in checkout_context.payment_methods(CHANNEL_REF)` → 400 `{"detail": "Escolha uma forma de pagamento disponível neste canal.", "field": "payment_method"}`.
- `shopman/storefront/tests/api/test_checkout_principal_boundary.py:89-104`: parametriza `["", "cash", "external", "unknown", None]` e exige **400 e nenhum pedido criado**.
- **Dono da lista:** `shopman/shop/projections/checkout_context.py:50-58` → `ChannelConfig.for_channel(channel).payment.available_methods` (canal inexistente → `["cash"]`).

**[FATO] Segundo dono morto da mesma pergunta:** `shopman/storefront/intents/checkout.py:317-321` implementa exatamente o mesmo default posicional:

```python
def _resolve_payment_method(post, payment_methods: list[str]) -> str:
    if len(payment_methods) > 1:
        chosen = post.get("payment_method", payment_methods[0])
        return chosen if chosen in payment_methods else payment_methods[0]
    return payment_methods[0] if payment_methods else "cash"
```

`interpret_checkout()` (`:23`) **não tem chamador de produção** — grep por `interpret_checkout` só encontra definição, docstrings e planos antigos; de `shopman/storefront/intents/checkout.py` só são importados `_validate_preorder`, `_validate_slot` e `parse_change_for` (ex.: `shopman/storefront/api/views.py:433`, `shopman/storefront/concierge/tools.py:1014`, `:1020`, `:1279`). `_resolve_payment_method` só é exercitado por teste (`shopman/storefront/tests/test_checkout_error_paths.py:78-81`). **[INFERÊNCIA]** mexer só no backend seria mexer no caminho morto e deixar o vivo intacto.

### A4 — O que acontece concretamente ao confirmar em Pix sem intenção [FATO + INFERÊNCIA no encadeamento]

Com o canal `web` como está hoje (seed `:6143-6203`), **e o cliente confirmando**:

| t | O que acontece | path:line |
|---|---|---|
| 0 | `Order` criado, `status=new`, `data.payment = {"method": "pix"}` | `shopman/storefront/api/views.py:428-429`; `shopman/storefront/intents/checkout.py:234-235` |
| 0 | **Estoque reservado** (adota holds da sacola, retag para `order:<ref>`, backstop 48h) — **dentro da transação do commit** | `shopman/shop/lifecycle.py:180-219`; `shopman/shop/services/stock.py:40-90`, `:228-230`, `:919`, `:928-958` |
| 0 | Directives: **só** `order.stale_new_alert` (`available_at = agora + 10 min`). **Nenhuma directive de pagamento** — `post_commit` + `pix` não inicia pagamento no commit | `shopman/shop/lifecycle.py:768-779`; `:803-810` |
| 0 | Cliente cai em `/pedido/<ref>` e vê `store_checking`: *"Pedido recebido / Estamos conferindo a disponibilidade. Avisamos em seguida."* — **sem QR, sem a palavra Pix, sem prazo** | `shopman/shop/projections/order_tracking.py:1118-1120`; `shopman/storefront/presentation/order_tracking.py:940-961` |
| +10 min | Alerta ao operador (pedido parado em `new`). Nada cancela sozinho: `confirmation.mode = "manual"` não agenda timeout | `shopman/shop/lifecycle.py:768-779`; `shopman/shop/migrations/0054_disable_remote_auto_confirmation.py:19-24` |
| aceite | `_on_accepted`: `_requires_payment_before_physical_work` (true p/ pix) → `payment.initiate` → **agora sim** nasce o intent Pix e o `payment.timeout` no vencimento; notificação `payment_requested` | `shopman/shop/lifecycle.py:445-463`, `:838-841`; `shopman/shop/services/payment.py:2414-2445` |
| aceite +10 min | Se não pago: pergunta ao gateway, cancela a cobrança e **cancela o pedido**; libera estoque (via `on_cancelled` → `stock.release`), devolve uso do cupom, avisa `payment_expired` | `shopman/shop/handlers/payment_timeout.py:54-97`; `shopman/shop/services/cancellation.py:18-105`; `shopman/shop/lifecycle.py:402-427` |

**Quantificado:** hold do pedido = **48 h** de backstop (`stock.py:919`); cobrança Pix = **10 min** (`seed.py:6147` → `config.py:105` → `shopman/shop/adapters/payment_efi.py:340-342`, `payment_mock.py:141-143`); hold de carrinho = 30 min (`seed.py:6103`), mas **não** é o que vale depois do commit.

**[INFERÊNCIA]** O dano real é, em ordem: (1) um pedido que ninguém pediu entra na fila do operador e ocupa a atenção dele (que é o recurso escasso do balcão); (2) estoque reservado por até 48 h se ninguém cancelar; (3) se o operador aceitar, **um Pix real vai para o telefone do cliente** e há um relógio de 10 min correndo; (4) nenhum desses passos pode ser corrigido "trocando a forma" — só cancelando e refazendo.

**É reversível?** Sim, pela porta do cancelamento, enquanto o pedido estiver `new|accepted` e comprovadamente não capturado (`shopman/shop/services/payment.py:1258`, `:1568-1581`; `_CANCELLABLE_STATUSES = {"new", "accepted"}`). **Não**, pela porta da forma de pagamento.

### A5 — Não existe caminho para trocar a forma de pagamento [FATO]

- **Cliente:** `shopman/storefront/api/urls.py:158-185` — `tracking`, `cancel`, `confirm-received`, `rate`, `conversation`, `reorder`, `payment/<ref>/mock-confirm/`. **Nenhuma rota de forma de pagamento.**
- **Gestor:** `shopman/backstage/api/urls.py:593-661` — `cancel`, `reschedule`, `edit`, `edit/preview`, `notes`, `comment`, `advance`, `confirm`, `reject`, `assign`/`unassign`, `courier-*`, `equipment-back`, `settle-delivery-cash`, `resend-payment-link`. Nenhuma de pagamento.
- **Serviço:** `shopman/shop/services/order_edit.py:904-993` (`_payment_after`) só toca `data["payment"]` quando **(a)** o total mudou, **(b)** há devolução, ou **(c)** há saldo a receber (`:948`). O parâmetro `delivery_payment_method` só existe **dentro de `fulfillment`** e só quando sobra saldo (`:964`, `:984`). E `edit()` sai cedo quando nada mudou (`:413-414`). **"Quero só trocar de Pix para dinheiro na retirada", sem mexer em item, não tem caminho.**
- **O que existe perto disso:** `counter_takeover.take_over_pending_digital_charge` (`shopman/shop/services/counter_takeover.py:133`) — cancela a cobrança digital aberta e assume no balcão. **Mas só é oferecido em `preorders._hand_over`, contexto POS** (conforme a tarefa nº07, `docs/reports/go-live-acceleration-20260929/07-alterar-pedido-gestor.md` §A5/§R4).
- **Acerto na porta** (`operator_orders.settle_delivery_cash`, `shopman/shop/services/operator_orders.py:1290-1372`) escreve `payment["method"]` de verdade (`:1359`) — mas só para pedidos `collection == "on_delivery"` (dinheiro na entrega). Não alcança um Pix na retirada.

**[FATO] Encadeamento com a tarefa nº07:** a lacuna é uma só. O `07` conclui que "alterar a forma de pagamento" **não existe em lugar nenhum** e que `R4` é decisão de produto. Este relatório acrescenta o outro lado: **a tela da loja oferece, em um toque, uma escolha que depois não tem desfazer.** As duas tarefas descrevem o mesmo buraco visto de pontas opostas.

### A6 — POS/balcão: por que lá é diferente (e por que a diferença é legítima) [FATO]

| | Loja online | Concierge (WhatsApp) | PDV (balcão) |
|---|---|---|---|
| Estado inicial | `state.payment_method` **pré-preenchido** (`finalizar.vue:743-745`) | `selected = ""` se o canal tem >1 método (`concierge/tools.py:1032`) | `paymentTenders: []` (`usePosSale.ts:649`) |
| Gesto exigido | **nenhum** — o rádio já está marcado | `review_order(payment_method=...)`; `place_order` exige o campo (`tools.py:1193`, `:1213`, schema `:1894`) | operador **injeta** a tender (`PosPaymentWorkspace.vue:1388-1398`); `resolvePayment([])` devolve `paymentMethod: ""` (`posIntent.ts:82`) |
| Validação | front manda, servidor confere (`views.py:161`) | devolve `missing: ["payment_method"]` | `required: ["payment_method"]` no contrato (`backstage/projections/pos.py:1207`) |
| Métodos | `pix`, `card` (seed `:6147`) | `pix`, `card` (seed `:6180`) | `cash`, `credit`, `debit`, `mixed` + `link` (`pos.py:524`, `:1102-1112`) |

**Por que o balcão é diferente, e por que isso não é desculpa para a loja:** no PDV o dinheiro está na frente do operador e ele **atesta** o que aconteceu — a maquininha é física (`packages/payman/shopman/payman/models/intent.py:48-51`, `:104-114`). O gesto de injetar a tender *é* a atestação. Na loja não há ninguém para atestar: a escolha **é** a instrução de cobrança, e um rádio pré-marcado faz o sistema atestar por conta própria algo que o cliente nunca disse.

**O rigor que o projeto já exige do operador é maior, não menor:** o PDV não deixa fechar venda sem tender; o Gestor não deixa mudar valor com cobrança digital aberta (`order_edit.py:818-823`); o `payment_gate` barra a saída de mercadoria sem captura (`shopman/shop/services/payment_gate.py:39`). **[INFERÊNCIA]** Aplicar rigor menor ao cliente do que ao operador, justamente no campo do dinheiro, é incoerente com a casa.

### A7 — Quais métodos existem de fato hoje, e quais adapters estão configurados [FATO]

- **Métodos no domínio** (`packages/payman/shopman/payman/models/intent.py:40-70`): `pix`, `cash`, `card`, `credit`, `debit`, `link`, `external`, `account`.
- **Sem gateway** (`METHODS_WITHOUT_GATEWAY`, `:108-114`): `cash`, `credit`, `debit`, `external`, `account`.
- **Digitais com captura antecipada** (`shopman/shop/services/payment_gate.py:39`): `{"pix", "card", "link"}`.
- **Adapters** (`config/settings.py:1638-1680`):

| Método | Configuração | Valor |
|---|---|---|
| `pix` | `SHOPMAN_PIX_ADAPTER` ou `payment_mock` se `DEBUG` senão **`payment_efi`** | `settings.py:1645-1646` |
| `card` | `SHOPMAN_CARD_ADAPTER`, default **`payment_stripe`** | `settings.py:1654` |
| `link` | `SHOPMAN_LINK_ADAPTER`, default `payment_mock` em DEBUG senão o do cartão (**`payment_stripe`**) | `settings.py:1667-1672` |
| `cash`, `external` | `None` (sem gateway) | `settings.py:1678-1679` |
| `credit`, `debit` | **ausentes de propósito** — maquininha física, TEF é WP próprio | `settings.py:1673-1677` |

- **Canal `web` hoje:** `["pix", "card"]` — ou seja, a loja online **não oferece dinheiro** (seed `:6147`). O `cash` existe no código do checkout (`intents/checkout.py:236-251`, `views.py:430-443`) e no balcão, mas não está na lista do canal web.
- **O vivo (alpha/staging), pelo spec espelho do repositório** `.do/app.alpha-subdomains.yaml`:

| Chave | Valor | linha |
|---|---|---|
| `SHOPMAN_PIX_ADAPTER` | `shopman.shop.adapters.payment_mock` | `:313-316` |
| `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` | `true` | `:321-324` |
| `SHOPMAN_EXPOSE_MOCK_CAPTURE` | `true` | `:325-328` |
| `SHOPMAN_MOCK_PIX_AUTO_CONFIRM` | `false` | `:329-332` |
| `SHOPMAN_CARD_ADAPTER` | `shopman.shop.adapters.payment_stripe` | `:317-320` |

**[FATO]** Com `EXPOSE_MOCK_CAPTURE=true` e `MOCK_PIX_AUTO_CONFIRM=false`, quem confirma o Pix mock é **a pessoa**, pelo botão "Simular pagamento" (`shopman/shop/services/payment.py:2462-2474`; `surfaces/storefront-nuxt/app/components/PaymentBlock.vue:116-133`). O relógio do auto-confirm não corre. (O mesmo já está registrado no relatório 10 desta série, Achado 3.)
**[NÃO VERIFICADO]** o spec do repositório é *espelho*, não o spec aplicado (o próprio `docs/guides/deploy-digitalocean.md:57` avisa). Não conferi o vivo.

### A8 — O testador não tinha como marcar o pedido como teste [FATO]

Existe **um** lugar canônico que decide "isto é pedido de teste": `shopman/shop/services/order_helpers.py:32-56`, e a docstring é explícita — *"a marca já nasce na ingestão (`ifood_ingest` grava `data["ifood"]["is_test"]`)... **outra origem de teste, quando existir, ganha seu ramo nesta função e em mais lugar nenhum**"* (`:42-46`). Hoje a função só lê `data["ifood"]["is_test"]` (`:52-56`).

**[INFERÊNCIA]** Um pedido de teste vindo do storefront é indistinguível de um pedido real: reserva estoque (`stock.py:88-90` só suprime para teste de marketplace), entra na fila do Gestor e pode gerar cobrança. É exatamente o que aconteceu com o testador.

### A9 — O documento canônico está desatualizado sobre a confirmação [FATO]

`docs/reference/storefront-spec.md:156-159` afirma: *"**Storefront = otimista** (auto-confirma se o operador não cancelar no prazo — Directive `confirmation.timeout`...)"*. O código diz outra coisa: o seed põe `{"mode": "manual", ...}` no canal remoto (`config/management/commands/seed.py:6146`) e a migração `shopman/shop/migrations/0054_disable_remote_auto_confirmation.py:14-24` converteu `auto_confirm` → `manual` em bancos já existentes **de propósito** ("rollback não deve reativar aceite automático", `:6`).

**[FATO]** O `CLAUDE.md` também carrega a regra antiga como convenção ativa: *"**Confirmação otimista**: Pedido auto-confirma se operador não cancela dentro do prazo."* Ela **não** vale para o canal `web`/loja online hoje. **[INFERÊNCIA]** quem ler a convenção e não ler o seed vai projetar a tela errada — e a confusão importa aqui, porque "otimista" é justamente o argumento que alguém usaria para defender o pré-marcado.

### A10 — Existe, sim, uma tela de revisão com resumo — e ela mostra a forma de pagamento [FATO]

`BottomSheet` "Revise seu pedido" (`surfaces/storefront-nuxt/app/pages/finalizar.vue:2169-2269`), aberto por `continueFromPayment()` → `openConfirmSheet()` (`:1130-1142`). Ela mostra:
- itens em linha única (`:2186-2204`);
- `reviewSummaryRows` — **inclui a linha de pagamento** (`:949-963`; `:959`: `rows.push({ icon: paymentIcon(state.payment_method), lines: [paymentMethodLabel.value] })`);
- subtotal, descontos, taxa de entrega (`:2230-2246`);
- rodapé com Total em destaque e **um** botão (`:2251-2268`).

**[INFERÊNCIA]** A informação existe, mas a linha de pagamento tem **o mesmo peso visual** de "Retirada", "Endereço" e "Nome": é uma linha de valor entre quatro, sem rótulo ("Pagamento"), sem destaque e sem afirmação em linguagem natural. É o defeito de omotenashi "nota de rodapé do engenheiro" aplicado a dinheiro: o dado está lá, o *sentido* não.

### A11 — Há um precedente canônico na própria tela: o projeto já sabe forçar uma escolha [FATO]

`pixProviderTestExceeded` bloqueia o avanço e oferece **"Trocar forma de pagamento"** em um clique (`finalizar.vue:406-431`, `changeFromPix` em `:1161-1168`; `submitDisabled` em `:430-431`; aviso em `:1859-1881`). E o `total_changed` do servidor força **reconfirmação** sobre o número certo em vez de aceitar um palpite (`shopman/storefront/api/serializers.py:47-61`; `finalizar.vue:1295-1300`).

**[INFERÊNCIA]** O projeto já tem a peça de UI ("o gate recusou, aqui está a saída em 1 clique") e já tem o princípio ("invariante de dinheiro não depende de o chamador lembrar de um campo", `serializers.py:50-54`). O que falta é aplicar o princípio à escolha da forma, não só ao total.

---

## 3. O que já existe e funciona (não reinventar)

| Peça | Onde | Por que não refazer |
|---|---|---|
| Lista de métodos dirigida por `ChannelConfig` | `shopman/shop/config.py:92-120`; `checkout_context.py:50-58` | Trocar método é config no Admin, não código. |
| Validação autoritativa no servidor | `views.py:161-165`; `test_checkout_principal_boundary.py:89-104` | Não aceita método inventado nem ausente. |
| Preferência lembrada do cliente | `checkout_defaults` (`shopman/shop/services/checkout_defaults.py`; `presentation/checkout.py:210-219`, `:249-255`) + toggle `save_as_default` (`serializers.py:63-67`) | **Escolha já dita pelo cliente** — é o único default legítimo que existe hoje. |
| Tela de revisão com resumo | `finalizar.vue:2169-2269` | Existe e já lista a forma de pagamento. |
| Gate de pagamento antes de a mercadoria sair | `shopman/shop/services/payment_gate.py:39`; `lifecycle.py:838-841` | Pix/card/link não passam para a cozinha sem captura. |
| Cancelamento por vencimento que devolve tudo | `handlers/payment_timeout.py:54-97`; `cancellation.py:18-105` | Estoque, cupom e fidelidade voltam; cliente é avisado. |
| Padrão "o gate recusou, a saída está a 1 clique" | `finalizar.vue:1161-1168`, `:1859-1881` | Componente e copy já aprovados. |
| Marca canônica de pedido de teste, extensível por desenho | `order_helpers.py:32-56` | A docstring já reserva o lugar para "outra origem de teste". |
| `UiRadioGroup`, `UiCheckbox`, `useNextFocus` | `surfaces/storefront-nuxt/app/components/ui/`; `app/presentation/nextFocus.ts` | Primitivas canônicas; nenhuma tela nova precisa inventar. |

---

## 4. Lacunas / riscos

- **L1 — O default é posicional e invisível.** Não há `default_method` em `ChannelConfig` (`config.py:92-120`) e não há nada na tela que diga qual é o padrão. Quem reordenar `["pix","card"]` no Admin muda silenciosamente a forma de pagamento da loja inteira. Risco **alto**, porque a alavanca existe e não avisa.
- **L2 — `is_default` é calculado e jogado fora.** `shopman/storefront/presentation/checkout.py:449` produz o campo; nenhuma tela o lê. Código que promete uma intenção que ninguém cumpre.
- **L3 — Duplo dono da pergunta.** `_resolve_payment_method` (`intents/checkout.py:317-321`) e `presentation/checkout.py:249-255` respondem a mesma coisa com regras ligeiramente diferentes; o primeiro está morto. **[INFERÊNCIA]** Uma correção que só toque o backend pode parecer feita e não mudar nada.
- **L4 — Sem desfazer.** §A5 e tarefa nº07 §R4. É a lacuna que transforma um toque errado em cancelamento + refazer.
- **L5 — O testador não consegue se distinguir de um cliente.** §A8.
- **L6 — Docs contra o código.** §A9: `storefront-spec.md:156-159` e a convenção do `CLAUDE.md` descrevem `auto_confirm`; o canal web é `manual`.
- **L7 — O teste que trava o comportamento atual trava o errado?** `shopman/storefront/tests/web/test_projections_checkout.py:222-223` afirma `proj.payment_methods[0].is_default is True` **e** `default_payment_method == payment_methods[0].ref`. É a trava que impede a correção de ser só "o backend para de mandar default". Precisa ser atualizada junto, de propósito.
- **L8 — Ninguém mede.** Não encontrei telemetria de "qual forma foi escolhida" que distinga escolha ativa de default aceito. **[NÃO VERIFICADO]** procurei por contadores/eventos de payment no checkout do storefront e não achei nenhum.

---

## 5. Recomendações acionáveis, ordenadas por impacto/esforço

### R1 — O default só existe quando alguém o disse *(impacto alto, esforço baixo — recomendada)*

Duas fontes de default, e **só elas**: (a) a **preferência lembrada do cliente** (`checkout_defaults`), que é um ato explícito e passado dele; (b) um **default declarado na config** (`payment.default_method`), que é decisão escrita do dono, auditável no Admin. **Posição na lista deixa de ser default.**

Mudanças:
1. `shopman/shop/config.py:92-120` — adicionar `default_method: str = ""` ao dataclass `Payment`; em `validate()` (`:457-474`), recusar `default_method` que não esteja em `available_methods`. (`method` continua sendo a lista **de oferta**, na ordem em que a tela desenha.)
2. `shopman/storefront/presentation/checkout.py:249-255` — `default_payment_method` = lembrado se válido; senão `config.payment.default_method` se válido; senão `""`.
3. `shopman/storefront/presentation/checkout.py:449` — `is_default=(m == default)` em vez de `(i == 0)`.
4. `surfaces/storefront-nuxt/app/pages/finalizar.vue:743-745` — **remover o `|| methods[0]?.ref`**. O `validatePaymentStep` já sabe dizer "Escolha o pagamento." quando o campo está vazio (`:1036`), e a mensagem já está aprovada.
5. Atualizar `shopman/storefront/tests/web/test_projections_checkout.py:222-223` e `:302`.
6. `shopman/shop/admin/channel.py:44` — acrescentar `default_method` ao `help_text` do campo Pagamento.
7. Sem default declarado, o passo de pagamento exige **um toque**. Se o dono quiser Pix como padrão da casa, ele **escreve isso** — e aí vale.

**Prós:** coerente com o invariante de dinheiro já escrito (`serializers.py:47-61`); coerente com o concierge e com o PDV; zero mudança de arquitetura; reversível por config; o dono mantém a conversão do Pix declarando o default em vez de herdando-o.
**Contras:** com default declarado, o defeito *atencional* volta (ver R2 — por isso os dois andam juntos); exige uma decisão do dono ("qual é o padrão da casa?"), que hoje está implícita; um toque a mais no funil de quem compra por Pix.

### R2 — Tornar a escolha **audível** no resumo de confirmação *(impacto alto, esforço baixo — combinar com R1)*

No `BottomSheet` "Revise seu pedido":
- a linha de pagamento ganha **rótulo e destaque próprios** ("**Forma de pagamento: Pix**"), em vez de ser uma linha anônima entre quatro (`finalizar.vue:949-963`, `:2217`), reusando `OrderSummaryRows`;
- junto dela, a **troca em 1 clique** que já existe para o teto do Pix (`changeFromPix`, `:1161-1168`) passa a estar sempre disponível, não só quando o limite estoura;
- se houver default declarado ou lembrado, a tela **diz por quê** ("Como você pagou da última vez" / "Forma de pagamento padrão da loja") — é o critério de omotenashi: o leitor não deve precisar completar sentido nem lembrar do que a tela não mostra.

**Prós:** custo baixo, sem tocar o backend, e cobre o caso em que o default declarado existe; melhora também o cartão sem alterar comportamento.
**Contras:** sozinha **não resolve** a queixa — a falha do testador foi atencional; uma linha a mais num resumo de 5 linhas é fraca contra o hábito de tocar "Confirmar".

### R3 — Pedido de teste marcável no storefront *(impacto médio, esforço médio — ortogonal)*

Estender `order_helpers.is_test_order` (`shopman/shop/services/order_helpers.py:32-56`) com um segundo ramo, exatamente como a docstring prevê: um pedido nascido de conta marcada como teste/staff ganha `data["test_order"] = True` e entra nas supressões que a função já governa (estoque, cozinha, fiscal, aviso, fidelidade) — **sem** deixar de aparecer no Gestor, que é o que o testador precisa para conferir a tela.

**Prós:** resolve a classe inteira do problema (QA gerando lixo operacional), não só o Pix; reaproveita o mecanismo canônico.
**Contras:** precisa de uma marca de identidade confiável (conta ou telefone de teste) — e isso é decisão de produto sobre quem pode marcar; sem essa trava, vira porta para "pedido que não conta".

### R4 — Contrato explícito de "não escolhido" *(impacto médio, esforço baixo — se R1 for aceita)*

Fazer o backend **afirmar** que não há default: `default_payment_method: str = ""` como contrato do `CheckoutProjection` (`shopman/storefront/presentation/checkout.py:105`) e teste de contrato que **reprova** qualquer superfície que trate lista vazia como escolha. Fecha a porta para o `||` reaparecer.

### R5 — Higiene *(impacto baixo, esforço baixo — fazer junto)*

- Corrigir `docs/reference/storefront-spec.md:156-159` (loja online é `manual`, não otimista) e ajustar a convenção do `CLAUDE.md` para dizer que a postura é **por canal**.
- Remover `_resolve_payment_method` (`shopman/storefront/intents/checkout.py:317-321`) — dono morto da mesma pergunta. Remover também o teste que o cobre (`test_checkout_error_paths.py:74-81`), senão ele vira o único consumidor.
- **Não** escolher "marcar o rádio visualmente como padrão" como solução: seria dar um nome bonito a um default que ninguém decidiu. Se o dono quiser um padrão, ele se declara em config (R1).

### Comparação das abordagens (o que a pergunta pede)

| Abordagem | O que é | Prós | Contras | Veredito |
|---|---|---|---|---|
| **A — Nada pré-selecionado, nunca** | `state.payment_method` começa `""`; o passo exige toque mesmo para quem já pagou daquele jeito | Máxima coerência com o invariante de dinheiro; uma regra só, sem exceção; impossível errar por descuido | Descarta um ato explícito do próprio cliente (a preferência lembrada — que é o melhor default que existe); mais atrito para o público majoritário de Pix | Bom, mas joga fora informação legítima |
| **B — Default só quando dito (lembrado ou declarado) + confirmação visível** *(R1+R2)* | Lista é **oferta**; default é a preferência lembrada ou a declarada em config; o resumo afirma a forma em linguagem natural e oferece troca em 1 clique | Mantém a conveniência onde ela foi pedida; tira o default inventado por posição; torna o padrão auditável e reversível por Admin; preserva conversão quando o dono declara Pix | Duas fontes de default para explicar na tela; exige decisão explícita do dono; um pouco mais de UI | **Recomendada** |
| **C — Manter o default e só torná-lo visível** | Rádio continua pré-marcado por posição; ganha selo "padrão", realce no resumo e troca em 1 clique | Esforço mínimo; nenhum risco de queda de conversão | **Não resolve a queixa**: a falha é atencional, não informacional; mantém o default que ninguém decidiu e a mudança silenciosa por reordenação no Admin; L1/L2 continuam | Insuficiente como correção; útil como parte de B |

**Recomendação: B**, com **R3 (pedido de teste) em paralelo** e **R5 (higiene) junto**. A regra que ela instala é uma frase: *a loja não responde "como você quer pagar?" em nome do cliente — ela só repete o que ele já disse, ou o que a casa declarou por escrito.*

---

## 6. Perguntas abertas / o que não consegui verificar

1. **[NÃO VERIFICADO] O dono quer um default da casa?** Se sim, qual, e ele aceita que a tela diga "forma de pagamento padrão"? Sem essa resposta, R1 entrega "sem default" — e a queda de um toque no funil é uma decisão dele, não minha.
2. **[NÃO VERIFICADO] O ambiente em que o testador estava.** O spec do repositório diz `payment_mock` + `EXPOSE_MOCK_CAPTURE` no alpha (`.do/app.alpha-subdomains.yaml:313-328`), mas o spec vivo pode divergir (`docs/guides/deploy-digitalocean.md:57`). Se era o alpha com mock, **nenhum dinheiro real se moveu** — o dano foi operacional (pedido falso na fila, estoque reservado, atenção do operador). Se era Efí de testes, o QR foi gerado de verdade no provedor.
3. **[NÃO VERIFICADO] O operador chegou a aceitar o pedido do testador?** É o que separa "pedido parado em `new`" de "cobrança Pix emitida ao cliente". Não tenho acesso ao banco do alpha daqui.
4. **[NÃO VERIFICADO] Existe telemetria de escolha de forma de pagamento?** Procurei evento/contador que distinga escolha ativa de default aceito e não encontrei (L8). Sem isso, não há como medir o efeito de R1/R2 nem estimar quantos pedidos nascem "por default".
5. **[NÃO VERIFICADO] Colisão com a tarefa nº07.** Se a decisão de produto de lá for (i) "trocar a forma de uma cobrança pendente", este defeito fica mais barato de conviver; se for "não fazer nada", ele fica mais caro. As duas tarefas deveriam ser decididas na mesma mesa.
6. **[NÃO ENCONTRADO]** em nenhum lugar: plano, ADR, WP ou relatório que decida **qual é a forma de pagamento padrão da loja online**, ou que justifique o Pix pré-marcado no formulário web. Onde procurei: `docs/plans/`, `docs/decisions/`, `docs/reports/`, `docs/reference/`, `docs/_archive/` — termos `default_payment`, `método padrão`, `primeira forma de pagamento`, `pix primeiro`, `pré-selecionado`, `padrão da loja`. Os únicos hits são o plano do concierge (`WHATSAPP-CONCIERGE-PLAN.md:138-140`, que é sobre *ordem de oferta na conversa*) e `docs/_archive/specs/storefront-surface.md:655`, que só **lista** o campo `default_payment_method` na projection, sem decidir seu valor.
7. **[NÃO VERIFICADO] `Shop.defaults` no banco vivo.** `ChannelConfig.for_channel` faz a cascata *defaults → Shop.defaults → Channel.config* (`config.py:418-453`), então a **loja** também pode sobrescrever `payment.method`. Li o seed; não li o `Shop.defaults` do alpha.

---

## Anexo — comandos de verificação (todos somente leitura)

```bash
ROOT=/Users/pablovalentini/Dev/Claude/django-shopman/.dsh-worktrees/go-live-acceleration
cd "$ROOT" && git log -1 --format='%H %ci %s'          # f0ffd02fd 2026-09-29 15:36 +0000

# de onde vem o default (três saltos)
sed -n '92,120p' shopman/shop/config.py
sed -n '249,255p;429,452p' shopman/storefront/presentation/checkout.py
sed -n '743,745p;1839,1856p' surfaces/storefront-nuxt/app/pages/finalizar.vue

# a lista do canal web e o modo de confirmação
sed -n '6102,6104p;6143,6154p;6198,6203p' config/management/commands/seed.py

# o backend exige a escolha
sed -n '35p' shopman/storefront/api/serializers.py
sed -n '161,165p' shopman/storefront/api/views.py
grep -n "payment_method" shopman/storefront/tests/api/test_checkout_principal_boundary.py

# `_resolve_payment_method` é dono morto?
grep -rn "interpret_checkout" shopman/ packages/ config/   # só definição e docs

# onde o Pix é iniciado (não é no checkout)
sed -n '803,841p;445,463p' shopman/shop/lifecycle.py
sed -n '2414,2445p' shopman/shop/services/payment.py

# prazos
sed -n '919p;928,958p' shopman/shop/services/stock.py       # backstop 48h
sed -n '54,97p' shopman/shop/handlers/payment_timeout.py     # vencido → cancela

# não há rota de troca de forma
grep -n "orders/" shopman/storefront/api/urls.py
grep -n "orders/" shopman/backstage/api/urls.py | sed -n '1,30p'

# POS/balcão não tem default
grep -n "paymentTenders" surfaces/pos-nuxt/app/composables/usePosSale.ts
sed -n '64,83p' surfaces/pos-nuxt/app/utils/posIntent.ts

# concierge exige escolha explícita
sed -n '1031,1043p;1193,1214p' shopman/storefront/concierge/tools.py

# o vivo (spec espelho)
sed -n '308,336p' .do/app.alpha-subdomains.yaml
```
