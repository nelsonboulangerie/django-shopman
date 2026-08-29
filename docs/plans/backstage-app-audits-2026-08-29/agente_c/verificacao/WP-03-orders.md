# Verificação WP-03 — Gestor de Pedidos

> Terceiro par de olhos sobre o WP-03 do Agente G e a revisão do Agente D.
> Tudo abaixo foi lido no código da worktree `coordenar-sessoes-deploys-b9cdac`
> (descendente do main de 2026-08-29). Dois achados foram **provados executando**
> a suíte contra o servidor real (resultados citados na seção C).

---

## A. Superfície real (o que existe hoje)

### Backend — API do Gestor

| Caminho | O que é |
|---|---|
| `shopman/backstage/api/urls.py:287,306-322` | As 17 rotas do Gestor: `orders/`, `orders/<ref>/` + 15 ações |
| `shopman/backstage/api/operations.py:995-1012` | `OrderDetailView` — projection expandida do pedido |
| `shopman/backstage/api/operations.py:1014-1021` | `OrderQueueView` — fila de duas zonas |
| `shopman/backstage/api/operations.py:1026-1036` | `_OrderActionBase` — gate único `shop.manage_orders` de TODAS as ações |
| `shopman/backstage/api/operations.py:1046-1071` | `OrderAdvanceView` — lê `change_out` e `equipment` do corpo |
| `shopman/backstage/api/operations.py:1087-1096` | `OrderConfirmView` — 409 honesto via `OrderConflict` |
| `shopman/backstage/api/operations.py:1111-1132` | `OrderRejectView` — motivo obrigatório, 409 honesto |
| `shopman/backstage/api/operations.py:1142-1162` | `OrderCancelView` — **sempre 200** (ver C1) |
| `shopman/backstage/api/operations.py:1172-1177` | `OrderCancellationReasonsView` — lista viva do iFood |
| `shopman/backstage/api/operations.py:1187-1205` | `OrderSettleDeliveryCashView` — acerto COD |
| `shopman/backstage/api/operations.py:1215-1224` | `OrderEquipmentBackView` — maquininha voltou |
| `shopman/backstage/api/operations.py:1234-1243` | `OrderRequeueFiscalView` |
| `shopman/backstage/api/operations.py:1481-1535` | `OrderCourierDispatch/Cancel/QuoteView` |
| `shopman/backstage/api/operations.py:1545-1552` | `OrderNotesView` — nota de cozinha, sem ator |
| `shopman/backstage/api/operations.py:1568-1599` | `OrderAssign/Unassign/CommentView` |
| `shopman/backstage/api/catalog.py:30-32` | `_CatalogBase` — aba Catálogo do Gestor, gate `shop.manage_catalog` **(nenhum WP citou)** |
| `shopman/backstage/api/feeds.py:19-21` | `_FeedBase` — aba Feeds, gate `shop.manage_catalog` **(nenhum WP citou)** |
| `shopman/backstage/api/alerts.py:45-75` | Sino de alertas — gate `CanViewOperatorAlerts` (OR de todas as personas) **(nenhum WP citou)** |
| `shopman/backstage/api/permissions.py:106-133` | `HasBackstagePermission`; `_required_codes` (l.159-165) **já aceita tupla de permissões** |

### Backend — projections e serviços

| Caminho | O que é |
|---|---|
| `shopman/backstage/projections/order_queue.py:41` | `ACTIVE_STATUSES` (inclui `accepted`) |
| `shopman/backstage/projections/order_queue.py:104-196` | `OrderCardProjection` (48 campos, `can_*` pré-resolvidos) |
| `shopman/backstage/projections/order_queue.py:199-269` | `OperatorOrderProjection` — tem `can_confirm`, `can_advance`, `can_settle_delivery_cash`, **não tem `can_cancel`** |
| `shopman/backstage/projections/order_queue.py:434-504` | `_courier_block` — projeta `can_quote`/`can_dispatch`/`can_cancel` da corrida |
| `shopman/backstage/projections/order_queue.py:1035-1069` | `_fiscal_status` — enum projetado (`failed`/`pending`/`authorized`/…) |
| `shopman/backstage/services/orders.py` | Fachada de mutação (advance/cancel/settle/requeue/courier) |
| `shopman/shop/services/operator_orders.py:206-275` | `advance_order` — troco `courier_out` + custódia de aparelho |
| `shopman/shop/services/operator_orders.py:510-534` | `cancel_order` — **descarta o retorno de `cancel`** |
| `shopman/shop/services/cancellation.py:17-70` | `cancel` — retorna `False` sem levantar |
| `packages/orderman/shopman/orderman/models/order.py:57-69` | `DEFAULT_TRANSITIONS` — a autoridade real do cancelamento |
| `shopman/shop/handlers/ifood_status.py:54-97` | Enfileira o callback do iFood ao transicionar |
| `shopman/shop/services/ifood_callbacks.py:144-169` | `request_cancellation` — exige código, senão levanta |
| `shopman/shop/management/commands/setup_groups.py:101-238` | RBAC do deployment; Caixa = `operate_pos` + `manage_orders` |
| `shopman/backstage/projections/pos.py:940-1080` | **Precedente já existente** de manifest de ações (`Action(href, method, payload_schema)`) |
| `shopman/shop/projections/types.py:65-75` | `ORDER_STATUS_TONES` canônico (com `accepted`) |
| `shopman/shop/projections/types.py:79+` | dataclass `Action` — a primitiva do manifest já existe |
| `shopman/backstage/contracts.py` + `management/commands/export_orders_schema.py` | Gerador + teste de drift do read model |

### Frontend — `surfaces/orders-nuxt`

| Caminho | O que é |
|---|---|
| `app/pages/index.vue` (735 l.) | Board: 3 colunas, triagem, tabela, bulk, CSV, impressão, 4 diálogos |
| `app/pages/[ref].vue` (430 l.) | Detalhe: ações, courier, fiscal, notas, timeline |
| `app/pages/catalog.vue` / `app/pages/feeds.vue` | Abas Catálogo e Feeds **(nenhum WP as auditou)** |
| `app/composables/useOrdersBoard.ts` | Fetch + SSE + poll + `act`/`actMany` |
| `app/composables/useOrderDetail.ts` | Fetch + todas as ações do detalhe |
| `app/presentation/board.ts` | Transformações puras (tons, triagem, affordances, bulk, CSV) |
| `app/presentation/courier.ts` | Timeline/tom da corrida a partir da letra Machine |
| `app/generated/ordersContract.ts` | Espelho gerado do read model (drift-guarded) |
| `app/types/orders.ts:38-57` | `CourierBlock` **tipado à mão** — inclui `can_quote/can_dispatch/can_cancel` |
| `app/components/OrderCard.vue`, `OrderReasonDialog.vue`, `OrderCourierPanel.vue`, `AlertsBell.vue`, `GestorTopBar.vue` | Componentes |
| `server/api/v1/[...path].ts`, `server/routes/sse/orders.ts` | BFF Nitro + proxy SSE |
| `tests/board.test.ts`, `tests/components/orderDetailActions.test.ts`, `tests/e2e/*` | Suíte existente |

**O que os dois WPs não mencionaram:** as abas **Catálogo** e **Feeds** (com gate de
permissão diferente do resto do app), o **sino de alertas**, o **BFF/SSE**, o
**precedente do manifest de ações no PDV**, e o fato de o `CourierBlock` já ser
tipado com capabilities no frontend.

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (de quem) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | Cancelamento retorna 200 sem efeito para status não-cancelável (D, P0) | `operations.py:1162` → `backstage/services/orders.py:81-91` → `operator_orders.py:534` → `cancellation.py:49-54` | **CONFIRMADO** | Provei executando: `POST .../VERIF-READY/cancel/` → `200 {"ok": true}`, pedido segue `ready`. `DEFAULT_TRANSITIONS` (`order.py:63-66`) não permite `ready/dispatched/delivered/completed → cancelled`. |
| 2 | `cancellation.cancel` retorna `False` sem levantar (D) | `cancellation.py:49-54` | **CONFIRMADO** | Guard explícito com `logger.info` + `return False`. |
| 3 | `cancel_order` descarta o retorno (D) | `operator_orders.py:534` | **CONFIRMADO** | Assinatura `-> None`; a chamada é statement, não `return`. |
| 4 | "Backend falha depois" (G, P1 cancelamento) | idem | **REFUTADO** | O backend **não** falha: responde sucesso. A leitura do G subestima o achado; a do D é a correta. |
| 5 | UI monta action URL manualmente (G `:116,194` / D `:116,194`) | `useOrdersBoard.ts:124` e `:202` | **CONFIRMADO (linhas desatualizadas)** | O comportamento existe; as linhas citadas por ambos estão ~8 linhas atrás do arquivo de hoje. D repetiu os números do G sem reconferir. |
| 6 | Bulk advance manda `{}` (G `:185` / D `:185,209`) | `useOrdersBoard.ts:202` | **CONFIRMADO (linha desatualizada)** | `actMany` posta `body: {}` para todos os refs. |
| 7 | Backend `advance` espera `change_out`/`equipment` (G `:1054` / D `:1054-1066`) | `operations.py:1052-1066` | **CONFIRMADO** | Linhas praticamente exatas. |
| 8 | `_OrderActionBase` com permissão única (G `:1026` / D `:1026-1030`) | `operations.py:1026-1030` | **CONFIRMADO** | Exato. 13 endpoints herdam. |
| 9 | `ACTIVE_STATUSES` inclui `accepted` (G/D `:41`) | `order_queue.py:41` | **CONFIRMADO** | Exato. |
| 10 | Frontend não mapeia `accepted` (G `:16` / D `:16-26`) | `board.ts:16-26` | **CONFIRMADO** | Sem `accepted`; cai no `?? "neutral"` (`:29`). Usado em `OrderCard.vue:175`, `index.vue:527`, `[ref].vue:162`. |
| 11 | `STATUS_TONE["confirmed"]` é resíduo de rename (D, novo) | `board.ts:18` | **CONFIRMADO** | O rename foi `3b973a98f refactor(orderman)!: confirmed vira accepted no núcleo`, que tocou este mesmo arquivo. Resíduo adicional que D não viu: `tests/e2e/mockBackend.mjs:15` ainda gera `status: "confirmed"`. |
| 12 | Cancelar no detalhe é incondicional (G `:222`) | `[ref].vue:222` | **CONFIRMADO** | Linha exata; e o comentário em `:217-218` documenta a decisão ("segue sempre disponível") — decisão **errada**, ver E. |
| 13 | `bulkableRefs` exclui troco mas não equipamento (D `:474-478`) | `board.ts:467-479`, filtro em `:477` | **CONFIRMADO** | Exato. |
| 14 | Servidor aceita `equipment` vazio no bulk → "custódia vazia registrada" (D) | `operator_orders.py:238-256`, `_clean_equipment` em `:318-326` | **PARCIAL** | `_clean_equipment([])` devolve `[]` e o bloco `if taken:` (`:244`) **não grava nada**. Não existe "custódia vazia registrada" — existe *ausência* de registro. O risco é a maquininha sair sem rastro, não um lançamento sujo. Corolário: o "409 sem equipamento quando o canal exige" que D pede **não tem base**: nenhum canal *exige* aparelho (`board.ts:492` diz isso: "a maquininha é oferta do despacho"). |
| 15 | Caixa já tem `manage_orders` + `operate_pos` (D `:102-105`) | `setup_groups.py:101-105` | **CONFIRMADO** | Exato. |
| 16 | Courier é `Record<string, unknown>` → UI infere ações por string (G/D, P2) | `ordersContract.ts:147` vs `types/orders.ts:38-57` e `order_queue.py:498-500` | **REFUTADO no essencial** | O backend **já projeta** `can_quote`/`can_dispatch`/`can_cancel`, e o frontend **já os tipa** em `CourierBlock`. Só o espelho *gerado* é `Record` (porque o Python monta dict, não dataclass). A UI deriva da letra apenas o *tom* e a *timeline* — presentation legítima. Sobra um pedido de tipagem, não um bug. |
| 17 | Requeue fiscal depende de string `failed` (G/D, P2) | `[ref].vue:214` lê `order.fiscal_status === 'failed'`, projetado em `order_queue.py:1035-1062` | **REFUTADO** | `fiscal_status` é enum **projetado pelo servidor**, não heurística local. E `requeue_fiscal_emission` (`backstage/services/orders.py:165-200`) falha fechado com motivo e emite `fiscal_requeued`. Nada a consertar. |
| 18 | `fetchCancellationReasons` devolve `[]` em erro → free-text no iFood (D, novo) | `useOrdersBoard.ts:178-187`, `useOrderDetail.ts:65-74`, `OrderReasonDialog.vue:35-42` | **CONFIRMADO — e maior do que D disse** | O board tem uma **segunda cópia** da mesma lógica (`index.vue:159-185`), que D não viu. E a consequência real é pior: `request_cancellation` (`ifood_callbacks.py:152-157`) só cai no `cancellation_default_code`, que em `config/settings.py:536` tem default `""`. Sem código: pedido cancelado localmente, directive falha, iFood segue esperando. |
| 19 | `save_kitchen_note` sem auditoria (D, novo) | `operator_orders.py:681-691` | **CONFIRMADO** | Nenhum `emit_event`, nenhum `actor`. Contrasta com `assign_order` (`:710`) e `add_comment` (`:737`), que emitem. |
| 20 | `OrderCourierCancelView` aceita `reason_id` opcional (D, novo) | `operations.py:1500-1516` | **CONFIRMADO, mas irrelevante como escrito** | O frontend **nunca envia** `reason_id` (`useOrderDetail.ts:96-100` chama `act("courier-cancel")` sem corpo). Tornar obrigatório quebra a única tela que usa o endpoint. Ver E. |
| 21 | "Não há botão ativo sem capability do backend" é aceite a conquistar (G/D, P1 manifest) | `board.ts:225-257` (`cardAffordances`) | **JÁ VERDADEIRO no board** | Todas as affordances do card saem de `can_confirm`/`can_advance`/`advance_block_label`/`can_settle_delivery_cash`/`equipment_back_pending`. A exceção é o **detalhe**, e só no botão Cancelar. O manifest continua valendo como defesa de drift, mas não é o que causa erro hoje. |
| 22 | Contrato gerado cobre read model, não actions (G/D, P1) | `contracts.py`, `export_orders_schema.py`, `tests/test_orders_schema_export.py` | **CONFIRMADO** | E existe precedente pronto: `backstage/projections/pos.py:940+` monta `Action(ref, href, method, payload_schema)` para o PDV. Não é invenção — é replicar padrão da casa. |
| 23 | "Feeds vaza URLs de dev" (relatório alpha 28/08, P1) | `orders-nuxt/nuxt.config.ts:12-18`, `feeds.vue:16`, `catalog.vue:208` | **JÁ CORRIGIDO** | A chave virou `public.djangoBaseUrl` (PR #383). Nenhum dos dois WPs mencionou este item, nem que já estava fechado. |

---

## C. Achados confirmados, com gravidade recalibrada

### C1 — P0 · Cancelar pedido responde sucesso e não cancela

**Gravidade:** P0. Risco máximo (dinheiro não estornado, marketplace não avisado,
cliente esperando um pedido que a loja acha cancelado) × esforço mínimo (3 edições
pequenas, sem migração, sem mudança de contrato de leitura).

**Mecanismo, do clique ao efeito:**
1. Um pedido `ready` está na coluna Saída (é o estado mais comum ali). O cliente liga
   para desistir. O operador abre `/<ref>` e clica **Cancelar** — o botão está sempre
   visível (`[ref].vue:222`, sem `v-if`).
2. `OrderReasonDialog` aceita, `submitReason` (`[ref].vue:101-106`) chama
   `cancel(...)` → `useOrderDetail.act` → `POST /orders/<ref>/cancel/`.
3. `OrderCancelView.post` (`operations.py:1143-1162`) chama a fachada, que chama
   `operator_orders.cancel_order` (`:510-534`), que chama
   `cancellation.cancel` (`cancellation.py:17-70`).
4. `cancel` consulta `order.can_transition_to(CANCELLED)` (`:49`). Em
   `DEFAULT_TRANSITIONS` (`packages/orderman/.../order.py:63-66`), `ready`,
   `dispatched`, `delivered` e `completed` **não** listam `cancelled`. O canal `pdv`
   (`config/management/commands/seed.py:4836-4845`) também não, exceto de `completed`.
   → `return False`, com `logger.info`, sem exceção.
5. `cancel_order` ignora o retorno (`:534`). A view responde `200 {"ok": true}`
   (`:1162`). `act` devolve `true`, o diálogo fecha (`[ref].vue:105`), o `refresh`
   redesenha o mesmo pedido `ready`. Nenhum toast de erro. Nenhum estorno. Nenhum
   `requestCancellation` para o iFood.

**Prova executada** (pytest contra a stack real, `shopman/backstage/tests/`):
```
STATUS HTTP: 200 BODY: {'ok': True, 'ref': 'VERIF-READY'}
ORDER STATUS APOS CANCEL: ready
```

**Evidência de que é descuido, não decisão:** `reject_order` — a ação irmã, no mesmo
arquivo — trava com `select_for_update` e levanta `OrderStateConflict` → 409
(`operator_orders.py:150-156`, `backstage/services/orders.py:36-37`,
`operations.py:1128-1129`). O cancelamento é a única ação de pedido que não confere
o resultado.

**Fix mínimo (3 linhas + 3 linhas):**
- `shopman/shop/services/operator_orders.py:516` → assinatura `-> bool`; `:534` →
  `return cancel(order, reason=reason, actor=actor, extra_data=extra_data or None)`
- `shopman/backstage/services/orders.py:82-89` → capturar o retorno e
  `if not cancelled: raise OrderConflict(f"Pedido em {order.get_status_display()} não pode ser cancelado.")`
- `shopman/backstage/api/operations.py:1160` → inserir antes do `except OrderError`:
  `except OrderConflict as exc: return Response({"detail": str(exc)}, status=409)`
  (`OrderConflict` já é subclasse de `OrderError`, então a ordem importa)

O `useOrdersBoard.act`/`useOrderDetail.act` já tratam 409 com mensagem honesta
(`useOrdersBoard.ts:134-138`) — nada a mudar no frontend para o erro aparecer.

---

### C2 — P1 · O botão Cancelar existe onde o cancelamento é impossível

**Gravidade:** P1. É a metade preventiva do C1: o 409 conserta a mentira, o
`can_cancel` evita o gesto inútil. Esforço baixo — o model já sabe responder.

**Mecanismo:** `OperatorOrderProjection` (`order_queue.py:199-269`) projeta
`can_confirm`, `can_advance`, `can_settle_delivery_cash` — e nenhum `can_cancel`.
O detalhe então renderiza o botão sem guarda (`[ref].vue:222`), com o comentário
`:217-218` afirmando que Cancelar "segue sempre disponível". Não segue: só de `new`,
`accepted` e `preparing` (e de `completed` no canal `pdv`).

**Fix mínimo:** dois campos na projection do detalhe, calculados pela própria máquina
de estados (sem duplicar regra):
```python
can_cancel = order.can_transition_to(Order.Status.CANCELLED)
cancel_block_label = "" if can_cancel else f"Não é possível cancelar em {order.get_status_display()}"
```
e `v-if="order.can_cancel"` em `[ref].vue:222`. Depois rodar
`python manage.py export_orders_schema` (o teste de drift
`shopman/backstage/tests/test_orders_schema_export.py` falha sem isso).

---

### C3 — P1 · Cancelar/recusar pedido iFood vira texto livre quando a lista de motivos falha

**Gravidade:** P1. Fail-open num contrato externo, com estado divergente que ninguém
reconcilia. Duas cópias da mesma lógica.

**Mecanismo:**
1. `openDialog('cancel')`/`openReject()` busca os motivos do iFood
   (`useOrderDetail.ts:65-74`, `useOrdersBoard.ts:178-187`). Em **qualquer** erro
   (rede, 401 de OAuth, iFood fora) o `catch` devolve `[]`.
2. O modo marketplace é decidido por `reasons.length > 0`
   (`OrderReasonDialog.vue:35`) — e o board tem uma **segunda implementação**
   (`index.vue:159`). Com `[]`, o diálogo cai no modo texto livre e, no `cancel`,
   `canConfirm` aceita até reason vazio (`OrderReasonDialog.vue:41`).
3. O `cancellation_code` vai vazio. O pedido é cancelado localmente (transição
   válida em `accepted`/`preparing`). O signal enfileira o callback
   (`ifood_status.py:82-94`). `request_cancellation` (`ifood_callbacks.py:152-157`)
   cai no `cancellation_default_code`, que em `config/settings.py:536` tem default
   `""` → `IFoodCallbackError` → `DirectiveTransientError` → retry → falha definitiva.
4. Resultado: o pedido está cancelado na casa e **vivo no iFood**. O único sinal é
   o alerta "N directives falharam" que o relatório alpha de 28/08 já registrou.

**Fix mínimo (na ordem de valor):**
1. Distinguir "canal sem códigos" de "não consegui buscar": `fetchCancellationReasons`
   devolve `null` no `catch` (hoje `[]` colapsa os dois). Com `null`, o diálogo
   **bloqueia** cancel/reject de pedido `channel_ref == "ifood"` com mensagem
   ("Não consegui carregar os motivos do iFood — tente de novo"), nunca texto livre.
2. Unificar as duas cópias: o board deve usar `OrderReasonDialog` como o detalhe usa
   (elimina `index.vue:154-185`).
3. Se o dono aceitar, configurar `IFOOD_CANCELLATION_CODE` no spec vivo como rede.

---

### C4 — P2 · A maquininha sai no lote sem ninguém registrar que saiu

**Gravidade:** P2 (não P1). O troco — que é dinheiro da gaveta — **já está protegido
pelo servidor** (`operator_orders.py:231-232` levanta `ChangeOutRequired` → 409, e o
`actMany` mostra o erro por pedido). O que escapa é só o registro de custódia de um
aparelho físico. Perda possível: uma maquininha sem rastro no painel
"onde está" (`index.vue:287-297`). Esforço: uma linha.

**Mecanismo:** `bulkableRefs` (`board.ts:467-479`) filtra por
`c.can_advance && !dispatchAsksChange(c)` (`:477`). `dispatchAsksChange` (`:487-489`)
só olha troco. Um pedido `ready` de entrega, sem troco pedido, num canal com
`fulfillment.equipment` (o `pdv` tem `["card_machine"]`,
`seed.py:4823`) entra no lote, avança para `dispatched` com `equipment=[]`, e
`if taken:` (`operator_orders.py:244`) simplesmente não grava nada.

**Fix mínimo — uma linha, `board.ts:477`:**
```ts
      : (c: OrderCardProjection) => c.can_advance && !dispatchAsks(c);
```
`dispatchAsks` (`board.ts:493-497`) já cobre troco **e** equipamento, e o card já
carrega `equipment_options` (`ordersContract.ts:101`). O preflight de lote ("7 avançam,
2 precisam troco, 1 precisa maquininha") continua sendo boa UX, mas é opcional em cima
disso.

---

### C5 — P2 · Uma permissão só cobre fila, dinheiro, fiscal e courier

**Gravidade:** P2 (não P1). Risco real mas **interno**: quem tem `manage_orders` é
Caixa e Gerente (`setup_groups.py:101-105,149`) — não é um público aberto. O que
incomoda é a assimetria com o resto da casa, que já separa `audit_shift` de
`operate_pos` pela mesma razão.

**Mecanismo:** `_OrderActionBase.required_permission = "shop.manage_orders"`
(`operations.py:1030`) gateia igualmente: avançar pedido, **acertar dinheiro na
gaveta**, **reprocessar NFC-e**, **cancelar pedido pago** e **cancelar corrida
paga**. O Caixa recebe `manage_orders` para operar a fila — e leva junto o
cancelamento e o fiscal.

**Fix mínimo — a máquina já existe:** `_required_codes`
(`backstage/api/permissions.py:159-165`) já aceita tupla, e o padrão está em uso
(`("backstage.view_bi", "cashman.audit_shift")`, comentado em `:110-112`). Então basta
declarar por view, sem tocar na base:
```python
class OrderRequeueFiscalView(_OrderActionBase):
    required_permission = ("shop.manage_orders", "shop.manage_catalog")  # nome a decidir
```
⚠️ **Não** tirar `settle_delivery_cash` do Caixa: o acerto do dinheiro da entrega é
exatamente o trabalho dele. A separação certa é o inverso do que D propôs — o Caixa
mantém o dinheiro, e é **cancelamento/fiscal/courier** que sobem de exigência.
Ver pergunta H1.

---

### C6 — P2 · Nota de cozinha muda sem trilha

**Gravidade:** P2. A nota chega ao ticket do KDS e altera o que a cozinha faz.
Hoje é o único campo do pedido que qualquer operador reescreve sem deixar quem/quando.

**Mecanismo:** `OrderNotesView` (`operations.py:1545-1552`) nem calcula ator;
`save_kitchen_note` (`operator_orders.py:681-691`) sobrescreve `data["kitchen_note"]`
e salva. Vizinhos no mesmo arquivo emitem evento: `assign_order` (`:710`),
`mark_equipment_returned` (`:370`), `add_comment` (`:737`).

**Fix mínimo:** passar `actor=_actor(request)` da view e, em `save_kitchen_note`,
antes do save:
```python
order.emit_event(event_type="kitchen_note_updated", actor=actor,
                 payload={"before": (order.data or {}).get("kitchen_note", ""), "after": notes})
```

---

### C7 — P3 · Resíduo do rename `confirmed` → `accepted` no frontend

**Gravidade:** P3 (cosmético + higiene). Viola a convenção zero-residuals do CLAUDE.md,
e o custo é uma linha.

**Mecanismo:** `board.ts:16-26` tem `confirmed: "info"` (status que não existe no
model desde `3b973a98f`) e não tem `accepted`. Um card aceito renderiza pill cinza
neutra (`board.ts:29`) em vez de azul, em `OrderCard.vue:175`, `index.vue:527` e
`[ref].vue:162`. Resíduo adicional: `tests/e2e/mockBackend.mjs:15` ainda emite
`status: "confirmed"`, então o e2e nunca exercita `accepted`.

**Fix mínimo — `board.ts:18`:** trocar `confirmed: "info",` por `accepted: "info",`;
e `mockBackend.mjs:15` para `"accepted"`. A fonte canônica está em
`shopman/shop/projections/types.py:65-75` — vale espelhá-la, não reinventá-la.

---

## D. Achados NOVOS (que G e D perderam)

### D1 — P1 · Um typo de dinheiro no Gestor vira 500

**Gravidade:** P1. Dois campos de dinheiro digitados à mão, em fluxo de gaveta, com
resposta não-acionável. Fix de duas linhas.

**Mecanismo, provado executando:** `advance_order` da fachada chama
`parse_money_to_q` **fora** do `try` (`shopman/backstage/services/orders.py:53-55`);
`settle_delivery_cash` faz o mesmo (`:135` e `:138`). `parse_money_to_q`
(`backstage/services/pos.py:41-42`) levanta `POSError`, que é irmã de `OrderError`
(ambas `BackstageServiceError`, `backstage/services/exceptions.py:70`), não subclasse.
As views só capturam `OrderError` (`operations.py:1069-1071`, `:1203-1204`), o
`EXCEPTION_HANDLER` da casa (`shopman/shop/api_errors.py:49-52`) devolve `None` para
exceção não-DRF, e o Django responde **500**.

Prova executada:
```
File ".../shopman/backstage/services/orders.py", line 55, in advance_order
    change_out_q = parse_money_to_q(str(change_out_raw))
shopman.backstage.services.exceptions.POSError: Valor inválido.
ADVANCE RAISED: POSError Valor inválido.
```
O caminho do operador: diálogo "Troco para o entregador" (`[ref].vue:401-414`,
`index.vue:684-710`) ou "Acerto dinheiro" — campo de texto livre, `12,,30` ou `1.2.3`
e o servidor cai. A tela mostra "Falha na ação. Tente de novo."; o log mostra
stacktrace; ninguém sabe que foi o campo.

**Que isto é descuido, não decisão:** o mesmo arquivo, 13 linhas abaixo, comenta
explicitamente que a tela "merece o 400 com a mensagem do pacote, não um 500"
(`backstage/services/orders.py:148-152`) — para `CashError`. `POSError` ficou de fora.

**Fix mínimo — em `shopman/backstage/services/orders.py`, nas duas funções:**
```python
    except POSError as exc:
        raise OrderError(str(exc)) from exc
```
envolvendo as chamadas a `parse_money_to_q` (linha 55; linhas 135 e 138). Melhor
ainda, com `field`: o dialeto da casa (`docs/reference/errors.md`) aceita
`{"detail": ..., "field": "change_out"}` e a tela sabe destacar o campo.

---

### D2 — P2 · O Caixa vê abas que sempre respondem 403, e a tela chama isso de falha de rede

**Gravidade:** P2. Não é vazamento (o gate funciona); é o operador tomando um erro
irrecuperável com um botão "Tentar de novo" que nunca vai funcionar.

**Mecanismo:** `GestorTopBar.vue:13-17` declara as três abas numa `const` fixa, sem
consultar capability nenhuma. As abas Catálogo e Feeds batem em endpoints gateados por
`shop.manage_catalog` (`api/catalog.py:30-32`, `api/feeds.py:19-21`), permissão que o
grupo **Caixa não tem** (`setup_groups.py:101-105`: só `operate_pos` e `manage_orders`).
O resultado é 403, e `catalog.vue:349-351` renderiza *"Não foi possível carregar o
catálogo. Tentar de novo"* — mesma frase para permissão negada, sessão expirada e
rede caída. O board já sabe distinguir esses casos (`useOrdersBoard.ts:23,34` com
`flagIfStationLocked`); o catálogo não.

**Fix mínimo (o menor útil):** tratar 403 no `catalog.vue`/`feeds.vue` com mensagem
própria ("Seu perfil não tem acesso ao catálogo") **sem** botão de retry. O passo
completo — projetar as abas a partir de capabilities do servidor — é o mesmo trabalho
do manifest de ações (C/§B#22) e pode andar junto.

---

### D3 — P3 · `_courier_block` engole qualquer erro e o painel de corrida some sem aviso

**Gravidade:** P3. Provável raridade, mas o modo de falha é ruim: some a única tela de
onde se cancela/redespacha uma corrida paga.

**Mecanismo:** `order_queue.py:502-504` captura `Exception` amplo e devolve `None`
com `logger.debug` (não warning). O detalhe renderiza o painel com
`v-if="order.courier"` (`[ref].vue:229`). Qualquer erro dentro do bloco — inclusive
um `cache.get` indisponível (`:474`) — faz o painel inteiro desaparecer, sem linha
alguma na tela dizendo por quê.

**Fix mínimo:** subir para `logger.warning` e projetar
`courier = {"status": "", "error": {"message": "Não consegui ler a corrida agora"}}`
em vez de `None`, para o painel existir dizendo que degradou. O `OrderCourierPanel`
já sabe renderizar `courier.error` (`:53-58`).

---

### D4 — informativo · o sino de alertas dá "ack" com a permissão de *ver*

`AlertAckView` (`api/alerts.py:69-75`) usa o mesmo `CanViewOperatorAlerts` do
`AlertListView`, e esse predicado (`backstage/permissions.py:120-129`) é um OR de
**todas** as personas operacionais — Cozinha, Compras, KDS incluídos. Quem só deveria
ver silencia um alerta de reconciliação financeira. **Não é deste WP** (o
`AlertsBell.vue` é compartilhado com `production-nuxt`), mas alguém precisa ser dono.
Ver G/§"outro app".

**Não encontrei nada novo** em: vazamento de PII no SSE (`_sse_emitters.py:259-296`
manda só `ref`/`status`/`kind`), no BFF (`server/api/v1/[...path].ts` é proxy puro), ou
parsing frouxo nas ações (`equipment` e `equipment_back` são normalizados e validados
contra o canal em `_clean_equipment`). O CSV (`board.ts:402-420`) leva `customer_name`,
que pode ser um telefone formatado quando o pedido não tem nome
(`order_queue.py:358-361` + `_format_customer_display`) — é PII num arquivo baixado
sem trilha, mas fora do peso dos itens acima.

---

## E. Achados a DESCARTAR (de G ou D)

1. **"Backend falha depois" no cancelamento (G).** Refutado pelo código e pela
   execução: o backend responde 200. Entra no WP a leitura do D, não a do G.

2. **"Custódia vazia registrada" e "409 quando o canal exige equipamento" (D).**
   Sem base: `_clean_equipment([])` retorna `[]` e `if taken:` não grava nada
   (`operator_orders.py:244`); e **nenhum canal exige** aparelho — `board.ts:491-492`
   documenta que é oferta. Um 409 aqui inventaria uma regra de negócio que o dono nunca
   pediu. Fica só o C4 (uma linha no frontend).

3. **P2 "courier é heurística local" (G e D).** Refutado: `can_quote`/`can_dispatch`/
   `can_cancel` já são projetados (`order_queue.py:498-500`) e já são tipados no
   frontend (`types/orders.ts:54-56`). Sobra tipar o espelho gerado — cosmético, não
   entra como achado.

4. **P2 "requeue fiscal por string `failed`" (G e D).** Refutado: `fiscal_status` é
   enum projetado pelo servidor (`order_queue.py:1035-1062`) e o requeue falha fechado
   com motivo (`backstage/services/orders.py:175-185`). Nada a fazer.

5. **"`OrderCourierCancelView` deve exigir motivo" (D).** Como escrito, quebra a
   única tela que chama o endpoint — `useOrderDetail.ts:96-100` nunca envia `reason_id`,
   e `OrderCourierPanel.vue:19-26` não coleta nenhum. Exigir no servidor primeiro
   deixaria o operador sem cancelar corrida. Se o dono quiser motivo, é trabalho de
   UI **antes** do 400, não um 400 solto.

6. **"Não há botão ativo sem capability" como aceite do manifest (G e D).** Já é
   verdade no board (`board.ts:225-257`). O manifest continua valendo como defesa de
   drift e como pré-requisito do D2, mas vender como "conserta botão errado" é
   propaganda: o único botão errado hoje é o Cancelar, e o C2 o resolve sozinho.

7. **"Feeds vaza URLs de dev" (relatório alpha).** Já corrigido no PR #383
   (`nuxt.config.ts:12-18`). Não reabrir.

---

## F. Aceites verificáveis

| # | Aceite | Como se prova |
|---|---|---|
| F1 | `POST /orders/<ref>/cancel/` num pedido `ready`, `dispatched`, `delivered` ou `completed` responde **409** com o status atual na mensagem, e o pedido **não** muda de status | Teste de backend (pytest, `shopman/backstage/tests/test_api_orders_surface.py`), parametrizado nos 4 status. Assert duplo: `response.status_code == 409` **e** `order.status` inalterado. |
| F2 | `POST .../cancel/` num pedido `new`/`accepted`/`preparing` continua 200 e cancela | Mesmo teste — o caminho feliz não pode regredir. Já há cobertura parcial em `test_api_orders_surface.py:266-311` (`preparing`). |
| F3 | A projection do detalhe expõe `can_cancel` e `cancel_block_label`, e `can_cancel` é falso exatamente quando `order.can_transition_to(CANCELLED)` é falso | Teste de projection + `python manage.py export_orders_schema --check` (drift, `test_orders_schema_export.py`). |
| F4 | O botão Cancelar do detalhe não é renderizado quando `can_cancel` é falso | Teste de componente vitest em `tests/components/orderDetailActions.test.ts` (o arquivo já monta a barra de ações e assere presença/ausência de `data-action`). Marcar o botão com `data-action="cancel"`. |
| F5 | Pedido do canal `ifood` com `cancellation-reasons` indisponível **bloqueia** cancel e reject; nunca cai em texto livre | Teste vitest do `OrderReasonDialog` com `reasons: null` + `channel_ref: "ifood"` → `canConfirm === false`. Assert-negativo: nenhum `emit("confirm")` sai. |
| F6 | O board e o detalhe usam **um** diálogo de motivo | Assert estrutural: `grep` por `isMarketplaceReject` em `app/` retorna vazio (a cópia de `index.vue:159-185` sumiu). |
| F7 | Bulk advance exclui do lote todo pedido com `equipment_options` não vazio no próximo passo `dispatched` | Teste vitest em `tests/board.test.ts` (o describe "troco da entrega" já tem o caso irmão em `:317`). |
| F8 | Bulk advance de pedido que pede troco continua sendo recusado pelo servidor com 409 | Teste de backend: `POST .../advance/` com corpo `{}` num pedido delivery com `change_for_q > total` → `409`, `code == "change_out_required"`. |
| F9 | `change_out` e `amount` ilegíveis ("12,,30") devolvem **400** com `detail` acionável e `field`, nunca 500 | Teste de backend nas duas rotas (`advance`, `settle-delivery-cash`). Assert-negativo: `response.status_code != 500`. |
| F10 | Salvar nota de cozinha emite `kitchen_note_updated` com ator e diff | Teste de backend: `POST .../notes/` logado, depois `order.events.filter(event_type="kitchen_note_updated")` com `actor` e `payload["before"]/["after"]`. |
| F11 | `statusTone("accepted") === "info"` e `"confirmed"` não existe mais no mapa | Teste vitest em `tests/board.test.ts:82-89`. Assert-negativo: `expect(Object.keys(STATUS_TONE)).not.toContain("confirmed")` — ou, melhor, cobrir todos os `ACTIVE_STATUSES`. |
| F12 | Nenhum status de `ACTIVE_STATUSES` cai no fallback neutro | Teste de contrato: `order_queue.ACTIVE_STATUSES` exportado no schema gerado e iterado no vitest. |
| F13 | As abas Catálogo/Feeds distinguem 403 de falha de leitura, e não oferecem "Tentar de novo" numa negativa de permissão | Teste vitest do composable/página com erro `{status: 403}` → mensagem de permissão, `retry` ausente. |
| F14 | Se permissões finas forem adotadas: toda permission nova gateando endpoint é concedida a algum grupo | `shopman/shop/tests/test_group_permission_parity.py` — `operations.py` já está em `GATE_FILES` (`:45`) e o regex varre literais `"shop.*"` (`:52`), então o teste falha sozinho. Somar linha na `PARITY_TABLE`. |

Nenhum destes depende de infra ausente: iFood entra por mock do `fetch_cancellation_reasons`,
courier por `get_adapter("courier") is None`, e caixa pelo turno de teste que a suíte já monta.

---

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar (lista exata)

**Backend — só do Gestor, colisão baixa:**
- `shopman/backstage/api/operations.py` — **linhas 1026-1030 e 1142-1599**. ⚠️ Arquivo
  de 2.700+ linhas compartilhado com **WP-02 (PDV)**, **WP-04 (KDS)** e **WP-05
  (Produção)**: as ações de pedido vivem num bloco contíguo (1026-1599), mas
  `_actor` (`:124-133`) e `HasBackstagePermission` são comuns. **Coordenar por bloco de
  linhas, nunca reformatar o arquivo.**
- `shopman/backstage/services/orders.py` — arquivo inteiro é do Gestor. Sem colisão.
- `shopman/backstage/projections/order_queue.py` — do Gestor. Colisão possível com
  WP-04 se o KDS consumir `OrderCardProjection` (verificar antes).
- `shopman/shop/services/operator_orders.py` — ⚠️ **compartilhado**: `settle_delivery_cash`
  e `advance_order` são chamados pelo PDV e pelo fechamento. As mudanças deste WP
  ficam em `cancel_order` (`:510-534`) e `save_kitchen_note` (`:681-691`).
- `shopman/backstage/api/catalog.py` / `feeds.py` — só se D2 for adotado; toque mínimo.

**Fora de escopo mas necessário conferir:** `shopman/shop/services/cancellation.py` —
**não alterar**. Ele já responde certo (`False` para transição inválida); quem mente é
o chamador. Alterar `cancel` para levantar quebraria o self-cancel do cliente
(`customer_orders.py:517-519`) e o timeout de Pix, que dependem do retorno booleano.

**Frontend — `surfaces/orders-nuxt`, sem colisão com outros WPs:**
- `app/presentation/board.ts` (linhas 16-26, 477)
- `app/pages/[ref].vue` (linhas 214-224)
- `app/pages/index.vue` (linhas 154-185, se F6)
- `app/components/OrderReasonDialog.vue` (linhas 35-42)
- `app/composables/useOrderDetail.ts` (linhas 65-74), `useOrdersBoard.ts` (178-187)
- `app/generated/ordersContract.ts` (**gerado** — regerar, nunca editar à mão)
- `app/types/orders.ts`
- `tests/board.test.ts`, `tests/components/orderDetailActions.test.ts`,
  `tests/components/OrderReasonDialog.test.ts`, `tests/e2e/mockBackend.mjs`
- `app/pages/catalog.vue`, `app/pages/feeds.vue`, `app/components/GestorTopBar.vue` (só D2)

### Permissões novas e impacto em `setup_groups.py`

Se C5 for adotado (ver H1), o impacto é mecânico e o teste avisa sozinho:
- `shopman/shop/management/commands/setup_groups.py` é o **dono único** dos grupos e
  usa `set`, não `add` (`:12-16`): permissão que não estiver escrita ali é **revogada
  no próximo deploy**. Toda permission nova precisa entrar na lista de algum grupo.
- `shopman/shop/tests/test_group_permission_parity.py` já varre `operations.py`
  (`GATE_FILES:45`) atrás de literais `"shop.…"`/`"backstage.…"`/`"cashman.…"`
  (`_PERM_LITERAL:52`) e **falha** se ninguém conceder. Somar a linha na
  `PARITY_TABLE` (`:59+`).
- Recomendação (com base no que o RBAC já diz): **manter** `settle_delivery_cash` no
  Caixa (`:102-105`) — é o trabalho dele. Subir a exigência de **cancelamento
  pós-aceite**, **requeue fiscal** e **courier cancel** para o Gerente (`:123-190`).
  Isso preserva a paridade de persona e não destrava ninguém.

### O que pertence a outro app/dono

- **Estorno ao cliente após cancelamento** — o relatório alpha de 28/08 (§8) já
  registrou que o tracking do cliente não informa reembolso. É storefront, não Gestor.
- **Eventos iFood não-PLACED ackados e ignorados** (`ifood_events.process_events`,
  relatório alpha §7) — cancelamento feito pelo cliente no app iFood não reflete aqui.
  É o par simétrico do C3 e provavelmente vale mais; mas é integração iFood, não Gestor.
- **`AlertAckView`** (D4) — `AlertsBell.vue` é compartilhado com `production-nuxt`.
  Dono a definir entre WP-01/WP-05.
- **Disponibilidade da loja no iFood, editor de catálogo por canal** — relatório alpha
  §3; explicitamente fora do escopo aqui.
- **`MovementType` em português** — dívida conhecida do CLAUDE.md, WP próprio.

---

## H. Pergunta aberta para o dono do produto

**H1 — Quem cancela um pedido já pronto ou já na rua?**
Hoje ninguém consegue (a máquina de estados não permite `ready→cancelled`), mas a tela
finge que sim. Duas saídas incompatíveis, e ela decide o WP inteiro:
(a) **o cancelamento acaba quando o pão sai da vitrine** — então o fix é só o 409 + o
botão sumir, e o gesto certo depois disso é "Devolvido" (`returned`, que a máquina já
permite de `dispatched`/`delivered`/`completed`); ou
(b) **o gerente pode cancelar até a entrega** — então o canal precisa declarar
`ready/dispatched → cancelled` no `lifecycle.transitions` do `seed`, e isso arrasta
estorno, estoque e o callback do iFood.

**H2 — O que a loja faz quando o iFood não devolve a lista de motivos?**
Proposta: **bloquear** cancel/reject do pedido iFood e pedir para tentar de novo, nunca
aceitar texto livre (C3). O custo é o operador travado enquanto o iFood estiver fora.
A alternativa é configurar `IFOOD_CANCELLATION_CODE` como código-padrão e deixar passar
— o que envia ao cliente do iFood um motivo que não é o real. Qual das duas?

**H3 — Cancelar pedido e reprocessar NFC-e são gesto de Caixa ou de Gerente?**
O Caixa hoje faz os dois, porque `manage_orders` cobre tudo (C5). Separar é barato
(a máquina de permissão já aceita tupla) e não mexe no acerto de dinheiro, que fica
com ele. Mas se o balcão de manhã tem só o Caixa em pé, subir para Gerente significa
que um cancelamento espera alguém chegar.
