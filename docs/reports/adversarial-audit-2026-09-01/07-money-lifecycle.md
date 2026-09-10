# Auditoria adversarial — dinheiro, estoque e lifecycle de pedido

Escopo lido: `shopman/shop/lifecycle.py`, `production_lifecycle.py`, `services/` (payment,
stock, pos, cancellation, loyalty, fiscal, notification, pix_confirmation,
webhook_idempotency, remote_mutations), `handlers/`, `modifiers.py`, `adapters/payment_*`,
`webhooks/efi.py`, `packages/orderman` (commit, directive, order, session),
`packages/payman` (service, models), `packages/stockman` (holds), `packages/craftsman`
(execution, scheduling, contrib/stockman), `packages/cashman` (entry, shift, ledger),
`packages/guestman/contrib/loyalty`, `backstage/api/operations.py`,
`backstage/services/financial_reconciliation.py`, `config/settings_test.py`,
`config/management/commands/seed.py`, `management/commands/{sweep_stuck_orders,
maintenance_worker,process_directives}`.

Leitura obrigatória feita: `docs/plans/fallbacks-perigosos-go-live.md`. **Cinco dos 18
itens que o documento marca como abertos já foram corrigidos e o documento está velho**
(ver "Doc desatualizado" no fim). O resto deste relatório vai além dele.

Regra de honestidade adotada: cada achado abaixo cita o arquivo:LINHA que eu **li**.
Onde não consegui provar a sequência inteira em código, o achado está em `## Suspected`.

---

## P0

Nenhum achado P0 confirmado — no sentido estrito de "perde dinheiro/estoque em silêncio,
sem acusador, num caminho alcançável hoje". Isto é resultado, não gentileza: as três
travas que mais importam (`secure_stock` dentro da transação do commit,
`_claim_paid_dispatch`/`captured_at` como guard único do `on_paid`, e a
`UniqueConstraint(shift, order_ref)` da venda no livro-caixa) estão de pé e eu as verifiquei
uma a uma. Os dois candidatos que chegaram mais perto de P0 estão em **P1-1** (venda de
PIX/cartão no PDV que conclui e emite NFC-e antes da captura) e **P1-2** (soquete entre o
commit da venda e a linha do livro-caixa) — os dois têm acusador, e é só por isso que não
são P0.

---

## P1

### P1-1. Venda de PIX/cartão no PDV **conclui, baixa estoque, emite NFC-e e credita pontos ANTES de existir cobrança**

**Severidade:** P1 (entrega sem receber; detectado só na reconciliação do dia seguinte).

**Arquivos/linhas:**
- `config/management/commands/seed.py:4943-4944` — canal `pdv`:
  `{"confirmation": {"mode": "immediate"}, "payment": {"method": "cash", "timing": "external"}}`
- `shopman/shop/lifecycle.py:718-722` — `_requires_payment_before_physical_work()` devolve
  `False` incondicionalmente quando `config.payment.timing == "external"`
- `shopman/shop/lifecycle.py:390` — o gate de captura do `_on_accepted` é justamente esse
- `shopman/shop/lifecycle.py:760-767` — `_stock_fulfill_allowed()` devolve `True` para
  `timing=="external" and method != "external"` **sem olhar o Payman**
- `shopman/shop/lifecycle.py:427-428` — `_counter_handoff` + `transition_status(COMPLETED)`
- `shopman/shop/lifecycle.py:522-525` — `_on_completed` → `loyalty.earn` + `fiscal.emit`
- `shopman/shop/services/pos.py:377-390` — `_settle_pos_sale` só é chamado **depois** de
  `close_sale` fechar a transação, e a criação do intent de gateway acontece lá
- `shopman/shop/services/pos.py:2716-2735` — o ramo `gateway_only` do `_settle_pos_sale`,
  onde `payment_service.initiate(order)` finalmente roda

**Sequência concreta:**
1. Operador fecha uma venda no PDV com `payment_method = "pix"`.
2. `close_sale` commita: `CommitService._do_commit` cria o Order (`NEW`), emite
   `order_changed(created)`, `secure_stock` é no-op (timing external), `on_commit` agenda
   o dispatch.
3. `_on_commit` → `_handle_confirmation` com `mode="immediate"`:
   `ensure_confirmable` retorna cedo (timing external, `lifecycle.py:83-84`);
   `ensure_payment_captured` também retorna cedo (`lifecycle.py:128-129`).
   → `transition_status(ACCEPTED)`.
4. `_on_accepted`: `_requires_payment_before_physical_work` = `False` → **o gate de captura
   nunca roda**. `_stock_fulfill_allowed` = `True` → `stock.fulfill(order)` baixa o estoque.
   `_counter_handoff` é `True` (origin pos, pickup, sem data futura) e o canal declara
   `accepted → completed` no `lifecycle.transitions` (`seed.py:4972`) → `COMPLETED`.
5. `_on_completed` → `loyalty.earn` (pontos creditados) + `fiscal.emit` (NFC-e).
6. **Só agora** `_settle_pos_sale` chama `payment_service.initiate(order)` e cria o intent
   PIX no gateway, em estado `pending`.
7. O cliente vai embora sem escanear o QR. O pedido fica `COMPLETED`, com NFC-e emitida,
   estoque baixado, pontos creditados e **zero centavo capturado**.

**Acusador que existe (por isso não é P0):**
`shopman/backstage/services/financial_reconciliation.py:629-646` —
`fulfilled_digital_order_underpaid` (severidade `error`) dispara para pedido em
`{PREPARING, READY, DISPATCHED, DELIVERED, COMPLETED}` com método pix/card e
`net_q < total_q`. Roda em `reconcile_financial_day`, no `maintenance_worker`, sobre **o dia
anterior**. Ou seja: o pão saiu ontem, o alerta chega hoje.

**Correção proposta:** o gate de trabalho físico não pode derivar de `payment.timing`
sozinho. `_requires_payment_before_physical_work` deve olhar o MÉTODO antes do timing:
se `_payment_method(order, config) in _UPFRONT_DIGITAL_PAYMENT_METHODS`, exigir captura
mesmo em canal `external` — a exceção "external" existe para dinheiro/maquininha avulsa,
não para um intent de gateway que o próprio sistema acabou de criar. Simetricamente,
`_stock_fulfill_allowed` (`lifecycle.py:762`) deve exigir `_payment_is_captured` quando o
método é digital. Enquanto isso não existir, o PDV deve **inverter a ordem**: criar o
intent (`_settle_pos_sale`) antes de deixar o lifecycle concluir, ou segurar o
`counter_handoff` para métodos de gateway.

---

### P1-2. `IntegrityError` engolido dentro de `transaction.atomic` **sem savepoint** no Payman — a recuperação de corrida vira 500 no Postgres

**Severidade:** P1 (venda do balcão fica sem cobrança registrada; erro 409 na cara do
operador com o cliente na frente).

Este é exatamente o padrão que `shop/services/webhook_idempotency.py:88-96` documenta,
consertou para si **e não foi propagado para o Payman**. Duas instâncias:

**Instância A — `PaymentService.create_intent` chamado de dentro de `settle`:**
- `packages/payman/shopman/payman/service.py:210-211` — `settle` é `@transaction.atomic`
- `packages/payman/shopman/payman/service.py:294-304` — `settle` chama `cls.create_intent(...)`
- `packages/payman/shopman/payman/service.py:169-181` — `PaymentIntent.objects.create(...)`
  **sem `with transaction.atomic()` próprio**
- `packages/payman/shopman/payman/service.py:182-196` — `except IntegrityError:` seguido de
  `PaymentIntent.objects.filter(...).first()`
- Constraint que dispara: `pay_intent_idempotency_key_unique`
  (`packages/payman/shopman/payman/models/intent.py:122-126`)

**Sequência concreta:**
1. Operador toca "Finalizar" duas vezes numa venda em dinheiro (rede do salão oscilando).
   O `_claim_sale_request` (`shop/services/pos.py:413-470`) serializa os dois `close_sale`,
   mas `_settle_pos_sale` roda **fora** dessa transação
   (`shop/services/pos.py:379-381`), e o `_cash_idempotent` não cobre `close_sale`.
2. Duas chamadas concorrentes de `payment_service.settle_terminal_tenders` calculam a mesma
   chave estável `order-payment:{ref}:cash:terminal` (`shop/services/payment.py:271`).
3. `PaymentService.settle` abre `atomic`, chama `create_intent`; ambas não enxergam a linha
   da outra (READ COMMITTED). A perdedora leva `IntegrityError` no `create()` da linha 170.
4. No PostgreSQL o `IntegrityError` **aborta a transação inteira**, não só a instrução.
   O `except` da linha 182 executa `PaymentIntent.objects.filter(...)` numa transação já
   envenenada → `InternalError: current transaction is aborted, commands ignored until end
   of transaction block`.
5. Esse erro sobe por `_settle_pos_sale` → o `except Exception` de
   `shop/services/pos.py:2760-2772` levanta
   `PosIntentError(code="sale_settlement_failed", status=409)`: **"Venda criada, mas a
   cobrança não foi registrada. NÃO refaça a venda."** — a venda existe, o dinheiro está na
   gaveta, e não há intent nem linha `sale` no livro.

**Instância B — `PaymentService.refund`:**
- `packages/payman/shopman/payman/service.py:583-584` — `refund` é `@transaction.atomic`
- `packages/payman/shopman/payman/service.py:683-691` —
  `PaymentTransaction.objects.create(...)` sem savepoint
- `packages/payman/shopman/payman/service.py:692-703` — `except IntegrityError:` seguido de
  `PaymentTransaction.objects.filter(...).first()`
- Constraint: `pay_transaction_idempotency_key_unique`
  (`packages/payman/shopman/payman/models/transaction.py:76-80`)
- O comentário da linha 693-695 diz literalmente que essa é "a rede final… uma corrida que
  escapou do lock deste intent" — a rede não pega, ela quebra.

**Correção proposta:** copiar o idioma que o próprio repositório já tem em três lugares
(`shop/services/webhook_idempotency.py:88`, `shop/services/pos.py:454`,
`packages/cashman/.../ledger.py:118`): envolver **só o `create()`** num
`with transaction.atomic():` aninhado, para o `IntegrityError` cair num savepoint e o
`except` poder consultar.

---

### P1-3. `loyalty.redeem` e `loyalty.earn` criam Directive **sem `dedupe_key`**, e o re-despacho do `on_commit` as duplica

**Severidade:** P1 (débito/crédito duplo de pontos com mais de um worker de directives;
lixo de fila garantido mesmo com um).

**Arquivos/linhas:**
- `shopman/shop/services/loyalty.py:37-43` — `redeem()` usa `Directive.objects.create(...)`
  cru, **sem** `dedupe_key`
- `shopman/shop/services/loyalty.py:61-67` — `earn()` idem
- Contraste no mesmo arquivo: `revoke()` (`:86`) e `restore()` (`:115`) usam
  `directives.create_deduped(..., dedupe_key=...)`. Também usam `create_deduped`:
  `services/fiscal.py:99` e `services/notification.py:104`. As duas exceções são as duas
  que mexem em saldo de ponto.
- `shopman/shop/lifecycle.py:212` — `on_commit` está em `DURABLE_PHASES`
- `shopman/shop/lifecycle.py:284` — `loyalty.redeem(order)` roda no meio do `_on_commit`
- `shopman/shop/lifecycle.py:238-239` — o marcador durável só é gravado **depois** do
  handler retornar
- `shopman/shop/management/commands/sweep_stuck_orders.py:60-64` — pedido `NEW` sem marcador
  `on_commit` é re-despachado

**Sequência concreta:**
1. Pedido web com resgate de pontos commita. `_on_commit` roda: `stock.hold`,
   `_record_availability_decision`, **`loyalty.redeem` cria a Directive #1**.
2. Logo depois, ainda dentro do mesmo `_on_commit`, algo levanta — `payment.initiate` numa
   configuração sem adapter é tratada, mas `fulfillment.create` (`lifecycle.py:290`),
   `notification.send` (`:297`) ou a transição aninhada do `_handle_confirmation`
   (`:638`) não são. O marcador `lifecycle.on_commit = "done"` **não** é gravado.
3. 15 min depois o `sweep_stuck_orders` re-despacha `on_commit`. `stock.hold` é no-op
   (chave `hold_ids` presente), `_record_coupon_use` é no-op (marcador
   `coupon_use_recorded`) — mas **`loyalty.redeem` cria a Directive #2**.
4. Com **um** worker de `process_directives` o dano para aqui: as duas directives são
   processadas em sequência e a segunda vê
   `adapter.has_loyalty_transaction(customer_ref, reference="order:X", type="redeem")`
   (`shopman/shop/handlers/loyalty.py:122-128`) e desiste.
5. Com **dois ou mais** workers, `select_for_update(skip_locked=True)`
   (`packages/orderman/.../process_directives.py:153`) entrega uma para cada. Os dois
   executam `has_loyalty_transaction` **fora** do lock da conta e ambos passam;
   `LoyaltyService.redeem_points` só trava a conta **depois**
   (`packages/guestman/shopman/guestman/contrib/loyalty/service.py:149-160`). Resultado:
   o cliente é debitado duas vezes pelo mesmo pedido. O mesmo vale para `earn` (crédito
   dobrado).
6. Segunda linha de defesa: **não existe**. `LoyaltyTransaction`
   (`packages/guestman/shopman/guestman/contrib/loyalty/models.py:144`) tem o campo
   `reference` mas **nenhuma `UniqueConstraint`** sobre `(account, reference,
   transaction_type)`.

**Correção proposta:** (a) `redeem`/`earn` passam a usar `create_deduped` com
`dedupe_key=f"loyalty.redeem:{order.ref}"` / `f"loyalty.earn:{order.ref}"` — é o que as
irmãs já fazem; (b) `UniqueConstraint(fields=["account","reference","transaction_type"],
condition=~Q(reference=""))` em `LoyaltyTransaction`, para o check-then-write do handler
deixar de ser TOCTOU. As duas metades são independentes e as duas valem.

---

### P1-4. Venda do PDV commitada com o dinheiro na gaveta e **sem linha no livro-caixa**, se o processo morre entre a transação e a liquidação

**Severidade:** P1 (diferença de fechamento sem dono; a atribuição ao pedido se perde).

**Arquivos/linhas:**
- `shopman/shop/services/pos.py:315-357` — a transação de `close_sale` termina na linha 357
- `shopman/shop/services/pos.py:359-390` — `_mark_tab_committed`,
  `_reconcile_order_payment_to_total`, `_settle_pos_sale` e `fiscal_service.emit` rodam
  **fora** dela, deliberadamente (o comentário das linhas 359-365 explica por quê)
- `shopman/shop/services/pos.py:2742-2751` — só ali nascem o intent do Payman e a linha
  `sale` do livro
- `shopman/shop/management/commands/maintenance_worker.py:41-99` — a lista de sweeps **não
  tem** nada que reconcilie "pedido do PDV commitado sem linha `sale`"

**Sequência concreta:** o operador finaliza uma venda de R$ 38 em dinheiro; a transação
commita (Order `COMPLETED`, estoque baixado, NFC-e enfileirada); o processo morre (deploy,
OOM, o pod é reciclado) antes de `_settle_pos_sale`. Resultado: nenhum `PaymentIntent`,
nenhuma `Entry(kind=sale)`. No fechamento, `expected_before_count`
(`packages/cashman/.../ledger.py:238`) não conhece esses R$ 38 e o `count` registra uma
**sobra** de R$ 38 que ninguém sabe explicar. A reconciliação financeira do dia seguinte
(`_check_cash_ledger`) compara Payman × livro — e como **os dois** lados estão vazios para
esse pedido, ela não acusa nada.

**Nuance importante:** o `_settle_after_shift_closed`
(`shopman/shop/services/pos.py:2781-2860`) foi escrito exatamente para desmentir a
afirmação "vira uma sobra na conferência" no caminho de turno fechado. No caminho de
**crash**, porém, a sobra realmente aparece (a contagem ainda não aconteceu) — só que sem
`order_ref` nenhum ligado a ela.

**Correção proposta:** um sweep no `maintenance_worker` (`sale_without_ledger_entry`) que
varra Orders do canal PDV com `payment.collection == "terminal"`, mais velhos que N minutos,
sem `Entry(kind=sale, order_ref=...)` — e que faça a liquidação tardia pelo caminho já
existente do `_settle_after_shift_closed` (nota no turno + alerta crítico) quando o turno já
fechou, ou `_record_sale` quando ainda está aberto.

---

### P1-5. As 12 ações de caixa que continuam `idempotency="none"` — e o `refund_cash` que já não está entre elas

**Severidade:** P1 para a trilha de auditoria e a leitura da gaveta; **não** P0 porque as
cinco mutações que movem dinheiro já foram travadas (ver "Doc desatualizado").

Ainda declaram `idempotency="none"` e **não** passam pelo `_cash_idempotent`:
- `cancel_recent_sale` — `shopman/backstage/projections/pos.py:1050` (POST destrutivo)
- `drawer_open` (`:1096`), `drawer_unlock_attempt` (`:1106`), `drawer_left_open` (`:1116`),
  `drawer_block` (`:1126`), `drawer_blind` (`:1136`), `drawer_unlock` (`:1146`)
- `clear_tab` (`:1213` — DELETE), e mais quatro leituras/ações menores

`drawer_unlock` é o mais incômodo dos "cosméticos": é `Entry.APPROVAL_REQUIRED`
(`packages/cashman/.../entry.py:117-119`), ou seja, gasta a segunda assinatura do gerente, e
um duplo toque grava duas liberações assinadas para um destrave só. `cancel_recent_sale` é
pior: é POST destrutivo sob PIN, sem trava de replay.

**Correção proposta:** estender `_cash_idempotent`
(`shopman/backstage/api/operations.py:2170`) a `cancel_recent_sale` e às seis ações de
gaveta, e declarar `idempotency="client_request_id"` nas seis. Não é infra nova — o
`run_idempotent_mutation` já está em pé e provado nas outras cinco.

---

### P1-6. `_verify_holds` conta `untracked=True` como reserva satisfeita, e o gate que produz `untracked` falha aberto em três camadas

Este é o item 9/11 do documento de fallbacks — **verifiquei que continua vivo, linha a
linha**, e acrescento o caminho completo:

- `shopman/shop/config.py:126` — `allow_untracked: bool = True` (default permissivo)
- `shopman/shop/config.py:122` — `preorder: bool = True` (idem)
- `shopman/shop/services/stock.py:670-677` — `_channel_allows_untracked`:
  `except Exception: return bool(ChannelConfig().stock.allow_untracked)` → devolve o
  **permissivo** quando a leitura da config falha
- `shopman/shop/services/stock.py:402-406` — `_sku_known_to_catalog`: a docstring da linha
  398 diz *"Fail-closed: se o contrato não responde, exigimos a reserva"*; o código diz
  `except Exception: return True`. No call site `stock.py:135-141`
  (`if not allow_untracked and not _sku_known_to_catalog(...): raise`), `True` **pula** a
  rejeição — fail-**open** exatamente onde importa
- `shopman/shop/lifecycle.py:964` — `held_skus = {... if h.get("hold_id") or h.get("untracked")}`
  → a defesa em profundidade também aceita `untracked` como satisfeito

**Sequência concreta:** o validador de SKU levanta (o `ComposedSkuValidator` consulta o
catálogo; um soluço de DB basta). O canal `pdv` declara `allow_untracked: False`
(`seed.py:4953-4957`), mas `_sku_known_to_catalog` devolve `True`, o `raise` não acontece,
a linha entra em `hold_ids` como `{"hold_id": None, "qty": 0, "untracked": True}`
(`stock.py:142`), `_verify_holds` a conta como satisfeita e o pedido nasce vendendo estoque
que nunca foi reservado. Sem alerta: `_alert_unknown_sku` só é chamado no caminho brando.

**Correção proposta:** três linhas, cada uma independente. (1) `stock.py:406` →
`return False` (é o que a docstring promete); (2) `stock.py:677` e `:660` → devolver o
restritivo (`False`) no `except`, não o default; (3) `config.py:122,126` → nascer `False`, e
o canal que quer vender sem rastreio declarar. Opcionalmente, `lifecycle.py:964` deixa de
aceitar `untracked` e passa a exigir `hold_id`, com uma allowlist explícita por canal.

---

## P2

### P2-1. Desconto manual do operador é `float` e **não tem clamp de percentual**

`shopman/shop/modifiers.py:894-902` — `_calc_manual`:
```python
value = float(manual.get("value") or 0)
...
return min(monetary_div(int(round(price_q * value)), 100), price_q)
```
Duas coisas. (a) `value` é `float` num caminho de dinheiro — o resto do módulo usa `Decimal`
(`_qty_decimal`, `_line_qty`) e a promoção percentual usa `int` com clamp explícito
(`modifiers.py:830-833`: `min(max(int(promo.value or 0), 0), 100)`). (b) **não há clamp**:
um `value = 150` produz `price_q * 1.5 / 100`, que o `min(..., price_q)` corta em
"produto de graça" em vez de recusar. O preço nunca fica negativo (o `min` protege), então
não é P1 — mas o operador que digita 150 recebe "100% de desconto" em silêncio, e o gate de
gerente só dispara se o desconto passar do teto (`pos.py:1859`), o que 100% sempre passa.
**Correção:** `value = min(max(_decimal_discount_value(...), 0), 100)`, com o mesmo helper
`Decimal` que `pos.py:2280` já tem.

### P2-2. Canal `pdv` não declara `preorder: False`, contrariando a própria documentação da config

`shopman/shop/config.py:122-125` diz textualmente *"PDV e marketplaces devem declarar False
no Channel.config"*. O seed (`config/management/commands/seed.py:4953-4957`) declara
`check_on_commit`, `allow_untracked` e `sells_nonconforming` — **não** `preorder`. O PDV
herda `preorder=True`, então uma encomenda de balcão para uma data sem fornada planejada
vira hold de DEMANDA (`quant=None`) em vez de recusa. É defensável como produto (o balcão
recebe encomenda), mas hoje a config e a documentação da config discordam, e é a
documentação que orienta quem for mexer. **Correção:** declarar `preorder` explicitamente
no `_pos_config`, com o valor que a casa quer, e corrigir o comentário de `config.py`.

### P2-3. Hold de DEMANDA nasce sem `expires_at` e o sweep de expirados nunca o alcança

`packages/stockman/shopman/stockman/models/hold.py:28-33` — `expired()` filtra
`expires_at__lt=now`; hold com `expires_at IS NULL` nunca entra.
`shopman/shop/services/stock.py:625-628` — `_retag_hold_for_order` só carimba o backstop de
48h em holds **adotados da sessão**; o hold criado direto pelo `create_hold(...,
allow_demand=True)` (`stock.py:176-186`) não passa por ali. `_is_fermata_hold`
(`stock.py:631-644`) isenta de propósito a reserva de fila, e o comentário reconhece que a
reserva de demanda *"não tem fornada que a resolva"* — mas o caminho que criaria o backstop
para ela não existe. Dano limitado: hold de demanda tem `quant=None`, então não retém
estoque físico; infla projeção de demanda e mantém o pedido preso a uma reserva morta.

### P2-4. `_from_shop_integrations` descarta a escolha do gestor com `logger.debug`

`shopman/shop/adapters/__init__.py:85-88` — `except Exception: logger.debug(...); return
None, False`. Item 12 do documento, confirmado vivo. Um soluço de DB ao ler
`Shop.integrations` faz a configuração de gateway do gestor virar a de settings, e
`logger.debug` é invisível em produção. **Correção:** `logger.warning`, no mínimo —
degradação de configuração de dinheiro não é evento de debug.

### P2-5. `_payment_idempotency_key_reusable` devolve o permissivo quando a busca falha

`shopman/shop/services/payment.py:1447-1449` — `except Exception: logger.debug(...); return
True`. Item 17, confirmado vivo. Falha na direção de *não* cobrar (reusa uma chave
possivelmente envenenada, o gateway repete a falha guardada), por isso P2 — mas é o ramo
permissivo escolhido no `except`, em `debug`.

### P2-6. Middleware de 2FA do Admin abre a porta em `NoReverseMatch`

`shopman/backstage/middleware_2fa.py:25-30` (`except NoReverseMatch: return
self.get_response(request)`) e `:43-45` (`except NoReverseMatch: return False`). Item 13,
confirmado vivo. Fora do escopo estrito de dinheiro, mas é o mesmo padrão: um portão de
segurança que não acha a própria view de verificação deve dar 500, não acenar.

### P2-7. `_external.suppress()` é global de processo e **não exige `DEBUG`**

`shopman/shop/adapters/_external.py:29-32` e `:41-43` — `if _suppressed_reason is not None:
return True`, antes de qualquer checagem de `DEBUG`. Chamado por
`config/management/commands/seed.py:287`. Item 15, confirmado vivo. Qualquer caminho que
alcance `suppress()` num worker de produção transforma toda notificação em sucesso
silencioso pelo resto da vida daquele processo — e os adapters de notificação devolvem
`True` no ramo inerte, o que **curto-circuita a cadeia de fallback** em
`services/notification.py:161-166`. **Correção:** `suppress()` recusa fora de `DEBUG`, ou o
`inert()` exige `DEBUG` também no ramo suprimido.

### P2-8. Resolver fiscal degrada para "só se o operador pedir"

`shopman/shop/services/fiscal.py:48-52` — `except Exception: logger.warning(...); return
_default_emission_decision(order)`. Item 16, confirmado vivo. Um `ImportError` dentro de um
resolver reverte em silêncio para "emite só se o operador marcou": NFC-e para de sair, venda
após venda, sem nada em tela nenhuma.

### P2-9. `get_backend(None)` resolve para o console

`shopman/shop/notifications.py:33-37` — `if name is None: name = "console"`. Item 14,
confirmado vivo. Hoje devolve `None` em produção (o console só é registrado sob `DEBUG`, ver
`config/settings.py:1068-1070`), mas o **desenho** é "não especificado ⇒ o falso".

### P2-10. `EFI_SANDBOX` e `FOCUS_NFE_ENVIRONMENT` continuam permissivos por omissão

`config/settings.py:1168` — `os.environ.get("EFI_SANDBOX", "true")`.
`config/settings.py:1098` — `os.environ.get("FOCUS_NFE_ENVIRONMENT", "homologacao")`.
Itens 1 e 2 do documento, confirmados vivos, sem trava de runtime. Repito aqui só para o
inventário ficar completo — o documento já os descreve bem e a correção proposta lá
(explícito ou `ImproperlyConfigured` no boot, no molde do
`packages/doorman/.../apps.py`) continua sendo a certa.

---

## Tests that lie

### T-1. A suíte roda com o gate de aprovação gerencial de desconto **desligado**

`config/settings_test.py:52` — `SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q = 0`.
`shopman/shop/services/pos.py:2460-2462` documenta que **`0` DESLIGA o teto**, e
`_approval_reasons` (`pos.py:1858-1859`) confirma: `if threshold_q > 0 and discount_q >
threshold_q`. Produção nasce em `500` (`config/settings.py:1136-1137`).
Ou seja: **todo teste que não faz override roda com "qualquer desconto passa sem gerente"**
— o controle antifraude de dinheiro está desligado no baseline.
*Mitigação que existe:* há testes de porta fechada com `@override_settings` —
`shopman/backstage/tests/test_pos_stress_guards.py:122,142,150` (=500) e
`test_pos_headless_surface_contract.py:555,578` (=50). E `price_override`
(`pos.py:1860-1861`) exige gerente independentemente do teto. Mesmo assim, o baseline
permissivo é o oposto da regra que o próprio documento de fallbacks fecha com:
*"todo default permissivo num caminho de dinheiro precisa de um teste que exercite a porta
fechada"* — aqui a porta **aberta** é que é o default do baseline.
**Correção:** pinar `= 500` em `settings_test.py` (o valor de produção) e usar
`@override_settings(...=0)` nos poucos testes que precisam do teto desligado.

### T-2. `test_fiscal_focusnfe.py` trava a homologação como caminho feliz

`shopman/shop/tests/test_fiscal_focusnfe.py:40` (`..._maps_nfce_payload_to_homologation_endpoint`),
`:184` (`..._uses_homologation_basic_auth_and_json`), `:219`
(`assert captured["url"] == "https://homologacao.focusnfe.com.br/v2/nfce?..."`).
Confirmado vivo (item 2 do documento). Nenhum teste exige que produção seja alcançável;
inverter o default de `FOCUS_NFE_ENVIRONMENT` reprovaria três testes, o que faz da suíte um
argumento **contra** a correção.

### T-3. Nenhum teste cobre a corrida de `IntegrityError` do Payman (P1-2)

`packages/payman/shopman/payman/tests/test_concurrency.py` (152 linhas) existe e cobre
transições sob lock, mas não exercita **duas chamadas de `settle`/`refund` com a mesma
`idempotency_key` sob concorrência real** — que é o único jeito de o `except IntegrityError`
das linhas 182 e 692 ser alcançado. E, mesmo se fosse escrito, no SQLite da suíte local o
`IntegrityError` **não envenena a transação** como no Postgres, então o teste passaria e o
defeito continuaria. Este é o caso canônico de "a suíte roda como a produção" falhando: o
gate de runtime (`make test-runtime`, contra Postgres) é o único lugar onde o teste teria
valor, e ele não tem esse caso.

### T-4. Invariantes de dinheiro/estoque **sem teste nenhum** que eu tenha encontrado

- "Venda do PDV com método de gateway não conclui antes da captura" (P1-1) — não existe;
  o comportamento atual é o oposto e nada o afirma nem o nega.
- "`loyalty.redeem` não cria duas Directives para o mesmo pedido" (P1-3) — não existe;
  `test_action_idempotency_contract.py` cobre o campo declarativo das ações do PDV, não os
  criadores de Directive.
- "Pedido do PDV commitado sempre tem linha `sale` no livro do turno" (P1-4) — o caminho
  de turno fechado tem teste (o `_settle_after_shift_closed` é bem coberto pela prosa);
  o caminho de crash não é testável sem um sweep que ainda não existe.
- `Entry` sem `UniqueConstraint` para `refund`/`cash_in`/`cash_out`/`float_in`/
  `account_settled` (`packages/cashman/.../entry.py:217-230`) — não há teste que afirme que
  a ausência é intencional nem que a trava de aplicação (`_cash_idempotent`) a substitui.

---

## Suspected

### S-1. Lost update sistêmico em `order.save(update_fields=["data"])` a partir de instância obsoleta

O padrão aparece em pelo menos oito lugares e sempre grava o **JSONField inteiro** a partir
do objeto em memória:
`shopman/shop/lifecycle.py:1016-1017`, `:343-344`, `:365-366`;
`shopman/shop/services/payment.py:198-199`, `:403-406`, `:1521-1524` (`_record_initiate_error`);
`shopman/shop/services/stock.py:236-237`;
`shopman/shop/services/cancellation.py:62-66`.

O caso mais fácil de imaginar: o operador cancela um pedido enquanto o webhook do PIX
confirma. `cancellation.cancel` leu o `order` no início da request; o webhook, em outra
conexão, gravou `payment.captured_at` via `_claim_paid_dispatch`
(`services/pix_confirmation.py:486-508`, esse sim sob `select_for_update`). O `save` do
`cancel` sobrescreve `data` inteiro com a versão velha e **apaga `captured_at`**.

**Por que fica em Suspected:** o dano financeiro é contido, e de propósito — o Payman é a
fonte canônica (`payment.get_payment_status`, `has_sufficient_captured_payment`), então
`_on_cancelled` → `payment.refund` ainda encontra o saldo capturado e estorna. O que se
perde é o carimbo que o `sweep_stuck_orders._payment_captured` usa como atalho, e ele tem
fallback pelo Payman (`sweep_stuck_orders.py:73-83`). Não consegui construir uma sequência
em que dinheiro ou estoque se perca — mas também não encontrei nada que **impeça** a
próxima chave a entrar em `order.data` de não ter uma fonte canônica atrás dela. Os três
lugares que fazem certo (`pix_confirmation._record_pix_receipt` e `_claim_paid_dispatch`,
`payment.settle_from_gateway:1123-1136`) mostram que a casa já sabe o idioma:
`select_for_update` + reler `data` do banco. Vale generalizar.

### S-2. `_handle_planned` e `_handle_started` da ponte craftsman→stockman não têm marcador de perna

`packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:225-262` (`_handle_planned`)
e `:333-380` (`_handle_started`) creditam Quant **sem** os marcadores duráveis que
`_handle_finished` ganhou (`STOCK_CONSUMED_KEY`/`STOCK_REALIZED_KEY`, `:44-46`) e **sem** o
`_leg_lock`. `_handle_planned` também não passa `reference=work_order.ref` ao `receive`
(diferente de `_handle_adjusted`, que passa — `:295`).

**Por que fica em Suspected:** verifiquei que `production_changed(action="started")` só sai
uma vez por WO — `CraftScheduling.start` exige `status == PLANNED` sob `select_for_update`
e grava `STARTED` na mesma transação
(`packages/craftsman/shopman/craftsman/services/scheduling.py:286-304`), então uma segunda
chamada levanta `INVALID_STATUS` antes do `.send()`. O mesmo vale para `finish`
(`services/execution.py:79-96`). Para `planned`, cada `plan()` cria uma **WorkOrder nova**
(`scheduling.py:59-89`), o que torna dois créditos o comportamento correto (duas fornadas).
Não achei o caminho de replay — mas a assimetria (uma perna blindada com lock+marcador,
três sem nada) é o tipo de coisa que envelhece mal, e `realize_finished_production`
(`handlers.py:180-189`) já prova que o sweeper chama esses handlers **direto**, fora do
signal.

### S-3. O reaper de directives pode duplicar a execução de um handler lento

`packages/orderman/.../process_directives.py:26-60` (`_reap_stuck_directives`) devolve para
`queued` toda directive `running` há mais de `--reap-timeout` minutos. Ele não distingue
"worker morto" de "handler lento": um `payment.refund` que ficou pendurado num timeout de
gateway maior que o teto volta para a fila e é pego por outro ciclo enquanto o primeiro
ainda roda. **Por que fica em Suspected:** não localizei o valor de `--reap-timeout` usado
no deployment (o `maintenance_worker` não chama `process_directives`; o comando roda como
processo próprio), e os handlers de dinheiro são idempotentes pelo Payman, então o dano
provável é log e alerta duplicados, não dinheiro. Vale confirmar o valor no spec da DO.

### S-4. `stock.revert` (devolução) não tem marcador de idempotência, ao contrário de `revert_fulfilled`

`shopman/shop/services/stock.py:363-386` — `revert()` chama `adapter.receive_return` para
cada item, sem nenhuma marca. Contraste explícito com `revert_fulfilled`
(`stock.py:317-361`), que ganhou `order.data["reverted_hold_ids"]` justamente porque *"o
RETURN move não muda o status do hold, então sem essa marca um on_cancelled re-disparado
creditaria o estoque de novo"*. **Por que fica em Suspected:** `on_returned` **não** está em
`DURABLE_PHASES` (`lifecycle.py:212`), então o `sweep_stuck_orders` não o re-despacha, e
`RETURNED` é terminal em todos os mapas de transição que li
(`packages/orderman/.../models/order.py:69`, `seed.py:4988`) — não achei o segundo disparo.
Mas o raciocínio que justificou o marcador em `revert_fulfilled` vale igual aqui, e a
ausência é assimetria, não decisão registrada.

### S-5. Reserva de dinheiro do `refund_cash` lê o saldo fora do lock

`shopman/shop/services/payment.py:648-668` — `_payman_refundable_amount(intent_ref)` roda
**antes** do `select_for_update` que `PaymentService.refund` faz internamente
(`packages/payman/.../service.py:1260-1263`). Duas chamadas concorrentes de `refund_cash`
leem o mesmo saldo positivo. **Por que fica em Suspected — e provavelmente seguro:** a
segunda transação chega em `PaymentService.refund`, relê `captured_q - returned_q` **sob o
lock** (`service.py:652-655`) e levanta `already_refunded`; como `refund_cash` não captura
`PaymentError`, o `with db_transaction.atomic()` da linha 660 desfaz tudo e **nenhuma
segunda linha `refund` entra no livro**. Verifiquei o caminho e ele fecha. Registro aqui só
porque o `refund_cash` depende de um `raise` de outro pacote para a sua própria atomicidade,
o que é correto por acidente de composição, não por contrato escrito.

---

## Verified-safe

Coisas que procurei quebrar e não consegui — registradas para a próxima auditoria não
gastar o mesmo tempo:

1. **Oversell sob concorrência no checkout web.** `secure_stock`
   (`lifecycle.py:164-203`) roda **dentro** da transação do `CommitService._do_commit`
   (ligado em `shopman/shop/apps.py:240-244`, antes do `on_commit`), com
   `require_all=True`; o `select_for_update` de Quant em
   `packages/stockman/.../services/holds.py:217` serializa os commits do mesmo SKU e quem
   chega sem estoque levanta `ValidationError(insufficient_stock)` **antes** de o pedido
   existir. Todo o resto do lifecycle é adiado para depois do COMMIT
   (`apps.py:248`), então nenhuma chamada de rede acontece com a Session travada.

2. **Consumo duplo de hold.** `StockHolds.fulfill`
   (`packages/stockman/.../services/holds.py:371-408`) exige `status == CONFIRMED` sob
   `select_for_update` e trava o Quant antes do `Move`. Segunda chamada levanta
   `INVALID_STATUS`. O `stock.fulfill` do orquestrador conta o erro e abre alerta crítico
   `stock_fulfill_failed` (`shopman/shop/services/stock.py:282-299`) — fail-loud, correto.

3. **Crédito duplo da fornada.** As duas pernas de `_handle_finished`
   (`craftsman/contrib/stockman/handlers.py:572-592`) carimbam o marcador **antes** de
   escrever, **sob** `_leg_lock` (`select_for_update` + releitura do `meta` do banco). O
   comentário de `:107-137` documenta o incidente real (24 madeleines viraram 48) e o
   conserto. Confirmei que o carimbo e a escrita ficam na mesma transação.

4. **Replay de webhook do PIX.** `webhook_idempotency.claim`
   (`shopman/shop/services/webhook_idempotency.py:47-107`) tem o savepoint próprio no
   `create()` — o defeito que a instrução desta auditoria mandava procurar **já está
   corrigido aqui** (o que não vale para o Payman, ver P1-2). O `confirm_pix`
   (`services/pix_confirmation.py`) trata os cinco desfechos de valor
   (ausente/ilegível/a menos/a maior/cobrança morta) e nenhum deles levanta — a Efí só
   reentrega em não-2xx, e problema de conteúdo não é curável por reentrega. Pagamento
   parcial **não** captura (`:164-176`), e é a decisão certa: o Payman admite uma captura
   por intent.

5. **`on_paid` disparado duas vezes.** O guard é único e durável: `payment.captured_at`,
   gravado sob `select_for_update` por `_claim_paid_dispatch`
   (`pix_confirmation.py:486-508`) e por `settle_from_gateway`
   (`services/payment.py:1123-1136`), sempre **antes** do `dispatch`.

6. **Venda do PDV duplicada por duplo toque.** `_claim_sale_request`
   (`shopman/shop/services/pos.py:413-470`) usa a `UniqueConstraint(scope, key)` da
   `IdempotencyKey` **com savepoint próprio** no `create()` (`:454`), e escreve o
   `order_ref` na trava ainda dentro da transação (`_answer_sale_claim`, `:483-497`) — o
   comentário de `:167-176` explica por que perguntar ao pedido não funcionaria. Correto.

7. **Fechamento cego do caixa.** `close_shift`
   (`packages/cashman/.../services/shifts.py:96-124`) calcula `expected_before_count` **sob**
   `select_for_update` do Shift, e `ledger.record` (`.../ledger.py:110-141`) relê o turno
   sob o **mesmo** lock antes de gravar qualquer linha. Os dois caminhos se serializam: não
   há como uma venda em voo entrar depois da contagem. `Entry` é append-only por
   `save()`/`delete()`/`QuerySet.update()` (`entry.py:33-40`, `:233-241`), com o limite
   honesto ("não protege do DBA") escrito na docstring do módulo.

8. **`total_q` do pedido é imutável.** `SEALED_FIELDS`
   (`packages/orderman/.../models/order.py:75`) inclui `total_q` e `snapshot`, e
   `save()` levanta `ImmutabilityError` (`:211-224`). Isso fecha a família inteira de
   ataques "o total muda depois do intent criado": o `idempotency_key` do pagamento embute
   `amount_q` (`services/payment.py:1402`) e `_existing_active_intent` filtra por
   `amount_q` (`:1470`) — os dois só são coerentes porque o total não pode mudar.

9. **Estorno duplo.** `PaymentTransaction` tem `UniqueConstraint(idempotency_key)` parcial
   (`packages/payman/.../models/transaction.py:76-80`) e é imutável por `save`/`delete`/
   `QuerySet` (`:8-19`, `:83-92`). `_refund_without_gateway`
   (`services/payment.py:761-782`) grava a chave **nos dois campos** (`gateway_id` e
   `idempotency_key`), como o comentário explica. `refund()` deduplica por método quando há
   vários intents (`:531-538`).

10. **Idempotência das cinco mutações de dinheiro do caixa.** Ver "Doc desatualizado"
    abaixo — está fechada em runtime, não só declarada.

11. **`_acquire_idempotency_lock` do CommitService.**
    `packages/orderman/.../services/commit.py:158-176` usa `get_or_create`, que o Django já
    envolve num savepoint interno — o `IntegrityError` da corrida não envenena a transação.
    Idem `remote_mutations._acquire` (`shopman/shop/services/remote_mutations.py:92-108`).

12. **Blindagem da cauda do `production_changed`.** `resilient_receiver`
    (`shopman/shop/handlers/_resilient.py`) protege só a cauda cosmética; a perna de
    estoque (receiver #0) continua podendo gritar, que é a política declarada. O sync de
    pedido↔fornada, blindado, ganhou rede própria
    (`services/production._ensure_order_links_closed`), e o `sweep_unrealized_production`
    está na lista do `maintenance_worker`
    (`management/commands/maintenance_worker.py:82-84`).

---

## Doc desatualizado — cinco itens de `fallbacks-perigosos-go-live.md` já corrigidos

Estes ainda aparecem como `⬜ aberto` ou `🟨 metade fechada` no documento e **eu verifiquei
que estão fechados no código de hoje**. Vale atualizar o documento antes que alguém gaste
uma rodada neles:

| Item | Estado real | Prova |
|---|---|---|
| **4** — adapter de e-mail devolve sucesso com backend de console | **Corrigido** | `shopman/shop/adapters/notification_email.py:239-241` — `_BACKENDS_INERTES = ("console","locmem","dummy")`, e `is_available` os recusa |
| **18 (metade 2)** — 8 mutações de caixa sem trava de replay | **Corrigido para as 5 que movem dinheiro** | `shopman/backstage/api/operations.py:2170-2233` (`_cash_idempotent` + `run_idempotent_mutation`), aplicado em 8 views (`:2281,2324,2366,2691,2734,2772,2812,2874`); as ações declaram `idempotency="client_request_id"` em `backstage/projections/pos.py:1060,1076,1086,1156,1166`. **Resta** o que listei em P1-5 |
| **7** — `get_adapter` trocava método de pagamento | Corrigido (o doc já marca ✅) | `shopman/shop/adapters/__init__.py:91-96` — `_NO_METHOD_FALLBACK` |
| — | `webhook_idempotency::_acquire` (o defeito que esta auditoria foi mandada procurar) | **Já tem savepoint**: `shopman/shop/services/webhook_idempotency.py:88-96`. O irmão **não** tem: ver P1-2 |
| **3** — `SHOPMAN_EXPOSE_DEBUG_OTP` | Corrigido (o doc já marca ✅) | `config/settings.py:88-92` |

Continuam vivos, confirmados linha a linha: **1** (`settings.py:1168`), **2**
(`settings.py:1098`), **9/10/11** (ver P1-6), **12** (P2-4), **13** (P2-6), **14** (P2-9),
**15** (P2-7), **16** (P2-8), **17** (P2-5).
