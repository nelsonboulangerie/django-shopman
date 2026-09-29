# 07 — Alterar pedido no Gestor (loja online)

**Árvore lida (canônica):** `.dsh-worktrees/go-live-acceleration` — HEAD `f0ffd02fde765493d734bae93a72bb361ed28fcf`, branch `dsh/go-live-acceleration-20260929` (2026-09-29) [FATO: `git rev-parse HEAD`].
Todo `path:line` abaixo é relativo a essa raiz. Nada foi executado além de leitura; nenhum arquivo foi alterado além deste relatório.

Legenda: **[FATO]** verificado no código/saída · **[INFERÊNCIA]** dedução minha · **[NÃO VERIFICADO]** não consegui confirmar.

---

## 1. Resumo executivo

1. **A solução canônica já existe e está no ar.** É o mecanismo **"pedido + ajustes"**: o `Order` continua **selado** e a alteração vive **ao lado**, em `Order.data["adjustment"]`, com **um único escritor** (`order_composition.record`) e **um único caminho de leitura** (`effective_items()` / `effective_total_q()`). Quem lê item ou total de pedido lê daí — a regra é dura e está escrita no módulo (`shopman/shop/services/order_composition.py:1-41`).
2. **A regra de negócio é `shopman/shop/services/order_edit.py`** (1.367 linhas): `plan()` (a prévia da tela, nada é gravado, `:273`) e `edit()` (sob `select_for_update`, transacional, `:398`). Cobre **itens (lista final)**, **observação do cliente**, **retirada ↔ entrega** (com a taxa de entrega como linha do ajuste) e **data/janela** (delegando ao reagendar, na mesma transação).
3. **Ela não é exclusiva de encomenda.** O único corte é: status fora de `{new, accepted, preparing}`, canal `ifood`, pedido de teste e NFC-e autorizada (`order_edit.state_refusal`, `order_edit.py:244-267`). **[INFERÊNCIA] Um pedido da loja online em `new`/`accepted`/`preparing` já é editável pelo serviço hoje, sem uma linha de código nova.**
4. **A porta já tem a permissão do Gestor.** `POST /api/v1/backstage/orders/<ref>/edit/preview/` e `POST /api/v1/backstage/orders/<ref>/edit/` (`shopman/backstage/api/urls.py:647-648`, views `operations.py:2354` e `:2399`), ambas com `required_permission = "shop.manage_orders"` — a mesma permissão que o Gestor já usa.
5. **O que falta não é mecanismo — é exposição.** O Gestor não oferece o gesto por dois motivos: (a) o servidor só monta o bloco `counter` (que carrega `edit` e `reschedule`) no contexto `"pos"` (`order_queue.py:782-795`); (b) **nenhuma** tela de `surfaces/orders-nuxt` chama as rotas. E isso está **declarado fora de escopo**, por escrito, desde 26/09: `docs/plans/ENCOMENDAS-PDV-PLAN.md:229` — *"Edição de pedido no Gestor."* sob o título *"Fora de escopo, registrado"*.
6. ⚠️ **O exemplo da queixa — "alterar a forma de pagamento" — NÃO está coberto pelo mecanismo canônico.** `order_edit` mexe no **valor** e no **destino da diferença**; nunca reescreve a **forma** de um pedido cujo valor não muda (`_payment_after`, `order_edit.py:904-993`, com o early return em `:413-414`). Não existe rota nem serviço para isso (14 rotas `orders/<ref>/*` em `urls.py:593-661`, nenhuma de pagamento). **Isso é capacidade nova, não transposição.**

**Resposta curta:** a solução canônica é *"o pedido + um ajuste ao lado, um só escritor, todo leitor lendo a composição"*, materializada em `order_edit` + `order_composition`. Transpor para o Gestor é **expor o gesto que já existe** (barato) **mais decidir o que fazer com "trocar a forma de pagamento"** (que hoje não existe em lugar nenhum).

---

## 2. Achados

### A1. Como o `Order` é imutável, e o que É permitido alterar

**[FATO]** `Order.SEALED_FIELDS = ["ref", "channel_ref", "session_key", "snapshot", "total_q", "currency"]` (`packages/orderman/shopman/orderman/models/order.py:77`). Qualquer `save()` que mude um deles levanta `ImmutabilityError` (`order.py:220-233`).

**[FATO]** O que **é** mutável: `status` (com `DEFAULT_TRANSITIONS`, `order.py:59-71` e validação em `:238-252`), todo o `data` (JSONField, `order.py:100-103`) e o audit log append-only `OrderEvent` (`order.py:411-443`).

**[FATO]** Isto já foi discutido e decidido antes, e a conclusão está escrita: `docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-03-agente-c-gestor-pedidos.md:93-96` — *"Cancelar nunca feriu a imutabilidade do pedido. `SEALED_FIELDS` é [...] `status` não está lá — é mutável por desenho, porque é o ciclo de vida. O que é selado é a régua (snapshot), o preço e a identidade."*

**[FATO]** **Não existe ADR sobre a imutabilidade do `Order`** (grep `imut|selad|SEALED` em `docs/decisions/` → nenhum ADR sobre `Order.SEALED_FIELDS`); o mais próximo é a **ADR-034** (parte selada do pedido, `Order.snapshot`) e a **ADR-006** (semântica de status). A imutabilidade está documentada em `docs/reference/system-spec.md:211-212` e `docs/reference/data-schemas.md:240`.

### A2. O mecanismo canônico, linha por linha

**O contêiner (`shopman/shop/services/order_composition.py`)**

| Peça | Onde | O que faz |
|---|---|---|
| `KEY = "adjustment"` | `:52` | A chave em `Order.data` |
| `EffectiveItem` | `:55-74` | Objeto de **leitura** com os MESMOS nomes de atributo de `OrderItem` — trocar `order.items.all()` por `effective_items(order)` é uma linha |
| `record()` | `:286-309` | **ÚNICO escritor.** Guarda **estado final absoluto** (`{source, event_id, revision, applied_at, items, total_q, sealed_total_q}`), nunca delta; lista original intacta nas linhas e no `total_q` selado |
| `effective_items()` / `effective_total_q()` | `:149-166` | O pedido com o ajuste por cima |
| `effective_items_by_order_id()` | `:169-196` | Versão em lote, 2 consultas, sem N+1 (fila do Gestor, B.I.) |
| `_adjusted_rows()` | `:209-217` | Filtro `data__has_key` no banco — ajuste é tratado como exceção |
| `diff()` / `describe()` / `is_empty()` | `:223-280` | "o que mudou", em português de tela |

**[FATO]** Registrado em `docs/reference/data-schemas.md:240`, que fecha com a regra: *"⚠️ Ninguém soma isto por conta própria"*.

**O serviço (`shopman/shop/services/order_edit.py`)**

- **[FATO] Portas de entrada:** `state_refusal(order)` devolve `(code, frase)` (`:244-267`) e é a **mesma régua** que `edit()` usa — a tela decide pelo mesmo critério do servidor. Recusas: status fora de `{new, accepted, preparing}` (`EDITABLE_STATUSES`, `:69`), `ready`+ (`:71-78`), canal `ifood` (`:256`), pedido de teste (`:258`), **NFC-e autorizada** (`fiscal_authorized`, `:238-241` e `:260-264`, com o encaminhamento "cancele e refaça").
- **[FATO] Prévia:** `plan(order, *, lines, notes, fulfillment, schedule)` (`:273-397`) devolve um `EditPlan` (`:140-170`) com itens novos, total anterior/novo, diferença, `settlement`, `balance_before_q`/`balance_after_q`, `requires_manager_approval`, `customer_note` e `data_updates`. **Nada é gravado.**
- **[FATO] Gravação:** `edit(...)` (`:398-487`): trava o pedido (`:411`), recalcula o plano, sai cedo se nada mudou (`:413-414`), exige `approved_by` quando a redução é de pedido pago (`:415-419`), grava `data_updates` **antes** de estoque/cozinha (`:421-431`), chama `apply_final_items` (`:438-446`), reagenda na mesma transação (`:452-461`), emite `order_edited` (`:462-466`), enfileira o estorno de gateway **depois do commit** (`:468-472`), religa produção (`:473-474`) e avisa o cliente (`:475`).
- **[FATO] O caminho comum:** `apply_final_items()` (`:183-232`) — grava o ajuste e traz **estoque** (`stock.reconcile_to_items(..., require_all=True)`) e **cozinha** (`kds.reconcile_to_lines`) juntos; se a mercadoria já saiu, o ajuste vale e o físico **não** se desfaz (`:227-231`, com `GOODS_STILL_IN_THE_HOUSE` vindo de `fiscal_service.GOODS_NOT_DISPATCHED`, `:90`). **O `ORDER_PATCHED` do iFood passa pelo mesmo caminho** (`data-schemas.md:240`).
- **[FATO] Preço:** o item que já estava mantém o preço vendido (`_kept`, `:1256-1266`); o que entra sai pelo preço do catálogo **no canal do pedido** via `OffermanPricingBackend` (`_Pricing`, `:1158-1207`); quantidade a mais com preço diferente vira **linha própria** (`:621-628`); **nenhuma regra promocional é reavaliada** (`:41-43`).
- **[FATO] Dinheiro (`_settlement`, `:794-846`):** quatro destinos — `SETTLE_NONE` (nada), `SETTLE_COLLECT` (saldo a receber), `SETTLE_REFUND_GATEWAY` (estorno parcial no Stripe/Efí, executado **fora da transação** em `:1021-1038` via `payment.refund` com `idempotency_key`, e `alert_refund_failed` em falha), `SETTLE_REFUND_CASH` (devolução da gaveta), `SETTLE_REFUND_CARD_MACHINE` (pendência guiada). Meio que não sabe devolver parte **recusa**: conta da casa (`:813-817`), cobrança digital aberta (`:818-823`), pagamento em mais de um meio (`:832-839`), saldo dividido em mais de uma forma pendente (`:950-955`).
- **[FATO] PIN de gerente:** `requires_manager_approval = settlement.kind in REFUND_KINDS` (`:388`), exigido em `:415-419`; na API é `pos_tabs_service.validate_manager_override(..., action="order_edit_refund")` (`operations.py:2428-2433`).
- **[FATO] Aviso ao cliente:** `_notify_customer` (`:1136-1146`) envia `order_updated` com `occurrence=_edit_count(order)` (sem isso a 2ª edição calava); o texto é montado por regra a partir da diferença (`customer_note`, `:1044-1078`; resumo acima de 3 mudanças, `:1081-1104`). O template Meta `pedido_atualizado` está **✅ APROVADO em 29/09/2026** (`docs/reference/whatsapp-templates-meta.md:302`, flow `content20260929130117_994990`; mapa evento→template em `:559`).

**Quem lê a composição (o que já foi convertido) [FATO — grep `order_composition` em `shopman/`]**

`backstage/projections/order_queue.py:717,752` (detalhe e cards) · `backstage/projections/preorders.py:491` (janela do reagendar) · `shop/services/kds.py:388-391` · `shop/handlers/production_order_sync.py:599-623,813-815` · `shop/handlers/returns.py:55-58` · `shop/services/payment.py:1491-1526` (`on_account_q`, `balance_due_q`) · `shop/services/notification.py:768-770` · `shop/projections/order_tracking.py:301,390,1436-1446` · `shop/views/fiscal_danfe.py:202-205` · `backstage/services/order_edit`… e a lista canônica de consumidores está em `docs/reference/data-schemas.md:240`.

### A3. O que a aba "Encomendas" (PDV) faz hoje — o que será transposto

**[FATO] O gesto é do servidor, não da tela.** O detalhe do balcão monta `order.counter` com `hand_over`, `cancel`, `reschedule`, `edit` (`shopman/backstage/projections/preorders.py:445-461`). O `edit` vem de `_edit(order)` (`:496-505`), que chama `order_edit.state_refusal(order)` e devolve `{allowed, block_reason, cancel_and_redo, revision}` — ou seja, **a régua do editor é literalmente a do serviço canônico**.

**[FATO] A tela:** `surfaces/pos-nuxt/app/pages/preorders/[ref].vue:218-228` mostra "Editar encomenda" só com `counter.edit.allowed`; com NFC-e autorizada, o botão some e entra "Cancelar e refazer" com o motivo (`:229-241`). O clique **não abre um editor novo** — navega para `/?edit=<ref>` (`:68-71`), e a **própria tela de venda** carrega a comanda virtual (`surfaces/pos-nuxt/app/pages/index.vue:949`).

**[FATO] Os três endpoints que a tela usa** (`surfaces/pos-nuxt/app/composables/usePosOrderEdit.ts`): `POST pos/preorders/<ref>/edit-session/` (`:61`) para montar a comanda virtual; `POST orders/<ref>/edit/preview/` (`:102`) para a prévia; `POST orders/<ref>/edit/` (`:123`) para gravar. O reagendar vai por `POST orders/<ref>/reschedule/` (`usePosPreorderActions.ts:160`), com a revisão **da data** (`:162`).

**[FATO] Dois andares, um mecanismo.** `shopman/shop/services/pos_edit_session.py` (417 linhas) é a **camada de sessão/tela** — comanda virtual `handle_type="pos_edit"`, sem `tab_ref`, que não dispara cozinha nem fecha venda; ela **delega a régua** a `order_edit.state_refusal` (`:63-65`). A dependência é de mão única: `pos_edit_session` importa `order_edit` (`:58`), nunca o contrário. **Ambos estão em uso**; não são mecanismos concorrentes.

**[FATO] O bug de 29/09 já corrigido (a prova de que a composição é a fonte):** commit `b0acbb392` *"Remarcar encomenda editada reserva os itens que valem agora, não os do nascimento"* — `stock.hold` lia `order.snapshot` (o pedido como nasceu) e recusava por um item que o cliente já tinha tirado ("Croissant Mini está pausado" numa encomenda que já era Baguette Campagne). Correção em `shopman/shop/services/reschedule.py` (`+9/-3`) e `shopman/shop/services/stock.py` (`+17/-1`), com teste em `shop/tests/test_order_edit.py` (`+22`).

### A4. Por que não dá para alterar no Gestor

**[FATO] O servidor não emite o gesto.** `OrderDetailView.get` chama `build_operator_order(order, user=request.user)` **sem** `context` (`shopman/backstage/api/operations.py:1695`) → o default é `context="orders"` (`order_queue.py:690`, `:522`). E só o ramo `context == "pos"` popula `counter` (`order_queue.py:782-795`); no Gestor o campo fica `None` (`order_queue.py:529`). Não há leitura de query param: **o Gestor não consegue pedir `context=pos` pela URL**.

**[FATO] O fluxo do Gestor também não tem o gesto.** `operator_orders.operational_actions` (`shopman/shop/services/operator_orders.py:1638-1705`) emite `confirm`, `reject`, `advance`, `notes`, `comment`, `assign`/`unassign`, `courier-back`, `equipment-back` — **nenhum `edit` nem `reschedule`**. As ações extras da projection (`order_queue.py:802-846`) são `cancel`, acerto de entrega, courier, `requeue-fiscal`, `resend-payment-link`.

**[FATO] O front não chama.** Grep de `reschedule|/edit/|edit/preview|order_edit` em `surfaces/orders-nuxt/app`: **3 ocorrências, todas comentários de tipo no contrato gerado** (`app/generated/ordersContract.ts:475`, `:485`, `:501`). Zero em `.vue`, composables ou presentation. **As únicas chamadas de app em `surfaces/` inteiro estão em `surfaces/pos-nuxt/app/composables/usePosOrderEdit.ts:61,102,123`.**

**[FATO] Está declarado fora de escopo.** `docs/plans/ENCOMENDAS-PDV-PLAN.md:225-229`, seção *"Fora de escopo, registrado"*, item literal: *"Edição de pedido no Gestor."*

**[FATO] Há um teste canônico prendendo isso:** `shopman/backstage/tests/test_order_detail_context.py:85-92` — `test_no_gestor_o_fluxo_inteiro_e_nenhum_bloco_de_balcao`, com `assert order["counter"] is None` (`:90`). O espelho é `:95-113`, com `assert set(counter) >= {"hand_over", "cancel", "reschedule", "edit", ...}` (`:112`).

**[FATO] Não há trava de permissão por superfície.** `OrderEditView`/`OrderEditPreviewView`/`OrderRescheduleView` exigem só `shop.manage_orders` (`operations.py:2361-2362` e `_OrderActionBase.required_permission`, `operations.py:1740`), e `state_refusal` recusa por **estado/canal/teste/fiscal**, nunca por superfície. **[INFERÊNCIA] A barreira real hoje é a ausência de UI e de `counter.allowed` — não a autorização.**

**[FATO] E o Gestor já recebe a revisão de graça:** `order_queue.py:741` monta `revisions` com `("advance", "kitchen_note", "assignment", "schedule", "edit")` — o `revisions.edit` que o `base_revision` da edição exige **já chega ao Gestor**.

### A5. "Alterar a forma de pagamento" — a lacuna real

**[FATO] O serviço não reescreve a forma sem mudar o valor.** `_payment_after()` (`order_edit.py:904-993`) só toca `Order.data["payment"]` quando (a) o total mudou (para atualizar `amount_q`/`tenders`), (b) há devolução (a forma recebida encolhe) ou (c) há saldo a receber (`balance_after_q > 0`, `:948`). O parâmetro `delivery_payment_method` só é aceito **dentro do `fulfillment`** e só quando sobra saldo (`:964` e `:984`). Mais: `data_updates["payment"]` só entra no plano se itens/observação/recebimento mudaram (`:390`), e `edit()` **sai cedo** quando `result.changed` é falso (`:413-414`). **[INFERÊNCIA] Logo: "só quero trocar de Pix para dinheiro na retirada", sem mudar item, não tem caminho — nem no PDV, nem no Gestor.**

**[FATO] Não existe rota.** As rotas `orders/<ref>/*` (`urls.py:593-661`) cobrem `cancel`, `reschedule`, `edit`, `edit/preview`, `notes`, `comment`, `advance`, `confirm`, `reject`, `assign`, `unassign`, `courier-*`, `settle-delivery-cash`. As que têm "payment" no nome são `resend-payment-link` (`:642`), `pos/orders/<ref>/send-payment-notice/` (`:920`) e `pos/payment/<ref>/status/` (`:925`).

**[FATO] O que existe hoje, e é perto:**
- **Escolher a forma no ato do recebimento.** `operator_orders.settle_delivery_cash` aceita `tenders` — *"o cliente combinou dinheiro e paga no cartão, ou a encomenda nem dizia a forma. Substitui as formas pendentes: só dinheiro, débito ou crédito, somando o que falta"* (`operator_orders.py:1195-1199`). É gated por `_can_settle_delivery_cash` (`order_queue.py:1966-1977`: método `cash|credit|debit|mixed`, `collection == "on_delivery"`, sem `cod_settled_at`, pedido no estado de retirada/entrega) e **já está exposto no Gestor** (`surfaces/orders-nuxt/app/pages/[ref].vue:278`, "Acertar entrega / Receber na retirada").
- **Cancelar a cobrança digital aberta.** `payment.cancel(order, reason)` (`shop/services/payment.py:1228`) e `payment.cancel_stale_intents` (`:1263`); no balcão, `counter_takeover.take_over_pending_digital_charge` (`shop/services/counter_takeover.py:133`) — mas ele só é oferecido via `preorders._hand_over` (`preorders.py:464-478`), **contexto pos**.
- **Devolver dinheiro pela gaveta.** `payment.refund_cash(order, *, shift, actor, ...)` (`payment.py:1017`) **exige turno aberto** (`:1036-1037`: `"Abra o caixa para devolver o dinheiro da venda"`).

**[FATO] E a pendência da devolução em dinheiro é invisível no Gestor.** `pending_cash_refunds` e `pending_card_machine_refunds` são **funções derivadas** (`payment.py:844` e `:933`, "nunca uma tabela", `:844-856`) expostas **apenas na projection do PDV, presas a um turno aberto e a um canal de terminal** (`shopman/backstage/projections/pos.py:2066-2067` e `:2106-2137`, lendo `cash_shift.terminal.channel_ref`). O Gestor não tem "Precisa de você".

### A6. Pedido de loja online × encomenda

**[FATO] É o mesmo `Order`, o mesmo modelo, a mesma trilha.** O que difere é dado, não tipo: `channel_ref`, `data.delivery_date`/`delivery_time_slot`, `data.fulfillment_type`, `data.payment.collection` (`"terminal"` vs `"on_delivery"`; `docs/reference/data-schemas.md:396`), `data.origin_channel`.

**[FATO] O corte da seção Encomendas é explícito:** `preorders.find_preorder` devolve `None` para pedido inexistente, em `order_ticket.EXCLUDED_STATUSES` (cancelado/devolvido) ou que seja venda de Balcão (`is_pos_counter_order`) — `shopman/backstage/projections/preorders.py:426-442`.

**[INFERÊNCIA] Consequência prática:** a encomenda da loja online (com data combinada) **já aparece na aba Encomendas e já é editável no balcão hoje**. O que não aparece ali é o pedido online **imediato** (sem data) — mas o endpoint `/edit/` o aceitaria do mesmo jeito, porque a régua é por estado, não por data.

### A7. Reembolso no Payman: existe, e é por meio

**[FATO]** `payment.refund(...)` (`payment.py:674`), `_refundable_intents` (`:766`), `_refund_without_gateway` (`:1176`), `refund_cash` (`:1017`), `record_card_machine_refund` (`:974`), `alert_refund_failed` (`:1202`), `overpaid_q` (`:808`), `captured_balance_q` (`:1461`), `balance_due_q` (`:1506`). O `order_edit` já usa `payment_service.refund(amount_q=..., idempotency_key=...)` para o estorno parcial de gateway (`order_edit.py:1035`).

---

## 3. O que já existe e funciona (não reinventar)

| Capacidade | Onde | Estado |
|---|---|---|
| Pedido imutável + alteração ao lado | `order_composition.py` (`KEY`, `record`, `effective_*`) | **no ar**, é o caminho do iFood `ORDER_PATCHED` e do balcão |
| Editar itens/observação/recebimento/data de um pedido, com prévia | `order_edit.plan` / `order_edit.edit` | **no ar** (WP-E6 PR 1) |
| Ajuste + estoque + cozinha numa transação | `order_edit.apply_final_items` | **no ar** (mesmo caminho do iFood) |
| Recusa sem saldo na data | `stock.reconcile_to_items(require_all=True)` | **no ar** |
| Reagendar (5 lugares costurados: data, directive, lembrete, holds, produção) | `shop/services/reschedule.py` | **no ar** |
| Diferença a mais → saldo; a menos → estorno no mesmo meio | `_settlement`/`_payment_after` + `payment.refund`/`refund_cash`/pendências | **no ar** |
| PIN de gerente em redução de pedido pago | `validate_manager_override(action="order_edit_refund")` | **no ar** |
| Aviso ao cliente com o que mudou e o destino do dinheiro | `order_updated` + template Meta **aprovado 29/09** | **no ar** |
| Escolha da forma de pagamento **no ato do recebimento** | `operator_orders.settle_delivery_cash(tenders=...)` + botão no Gestor | **no ar** |
| Detalhe do pedido é UM contrato para Gestor e PDV | `build_operator_order(context=...)` | **no ar** (WP-E7) |
| `revisions.edit` já chega ao Gestor | `order_queue.py:741` | **no ar** |
| Endpoints de edição/reagendar com a permissão do Gestor | `urls.py:646-648`, `shop.manage_orders` | **no ar** |
| Comanda virtual (não é comanda, não dispara cozinha, não fecha venda) | `pos_edit_session.py` | **no ar**, exclusivo da tela do PDV |

---

## 4. Lacunas / riscos

**L1 — O gesto não é emitido no contexto do Gestor.** [FATO] `order_queue.py:782` vs `:529`. Sem isso não há como a tela saber se pode oferecer "Editar" nem por quê não pode — a tela seria obrigada a decidir, e a regra da casa é que **o servidor decide** (`order_queue.py:516-521`, `docs/reference/...` e o teste `test_order_detail_context.py`).

**L2 — "Trocar a forma de pagamento" não existe em lugar nenhum.** [FATO] §A5. É a lacuna que a queixa nomeia. Sem decisão de produto aqui, transpor o editor de itens **não resolve a queixa**.

**L3 — O editor é a tela de venda do PDV.** [FATO] `pos_edit_session.py` existe para que o carrinho, a grade, o F7 e o F8 funcionem como o operador já sabe. O Gestor **não tem carrinho** (o detalhe só lê; `OperatorOrderDetail.vue` tem slots `summary`, `actions`, `after-profile`, `kitchen-note`). Transpor o editor *de itens* para o Gestor é construir um segundo editor — ou aceitar que a edição de itens aconteça no PDV.

**L4 — Devolução em dinheiro não tem onde acontecer no Gestor.** [FATO] `refund_cash` exige turno (`payment.py:1036`) e a pendência (`pending_cash_refunds`) só aparece na sessão de caixa do PDV (`pos.py:2106-2125`). Uma edição iniciada no Gestor que reduza um pedido pago em dinheiro **cria uma pendência que o Gestor não mostra**.

**L5 — Cobrança digital aberta trava mudança de valor.** [FATO] `open_digital_charge` (`order_edit.py:818-823`): quem não pagou o Pix muda o pedido e ouve *"Receba ou cancele essa cobrança antes de mudar o valor"*. Cancelar a cobrança hoje só tem porta pela tela do balcão (`counter_takeover`, oferecida em `preorders._hand_over`). [INFERÊNCIA] Para o caso WhatsApp ("cliente quer trocar o item e ainda não pagou"), esse é o primeiro obstáculo real.

**L6 — Risco fiscal.** [FATO] A NFC-e da encomenda sai na **saída da mercadoria** (#1173), então quase sempre não há nota e a edição acontece; com nota autorizada o serviço recusa com `fiscal_authorized` e a tela troca por "Cancelar e refazer" (`order_edit.py:260-264`; `preorders._edit`, `:503`). O ajuste também alimenta o DANFE (`views/fiscal_danfe.py:202-205`) e a emissão (`fiscal._build_fiscal_items`, citado em `data-schemas.md:240`). **Expor o gesto no Gestor não cria risco fiscal novo — mas cria a tentação de editar depois da nota, e a régua tem de ser a mesma.**

**L7 — Risco de estoque.** [FATO] No balcão o estoque recusa sem saldo na data (`require_all=True`, `order_edit.py:445`), o que é diferente do iFood (brando, `require_all=False`). E o bug de 29/09 (`b0acbb392`) mostrou que **ler o snapshot em vez da composição** faz a reserva ressuscitar item que o cliente tirou. Qualquer caminho novo que toque reserva tem de passar por `order_composition.effective_items`.

**L8 — Risco de concorrência.** [FATO] A base das mutações é a revisão `edit` (`operational_revision(order, field="edit")`, `operator_orders.py:1607-1619`, que cobre status, total, `adjustment`, `order_notes`, `fulfillment_type`, endereço, data, `payment` e `nfce_access_key`) + `Idempotency-Key` + `expected_actor_id` + fingerprint (`_context_response`, `operations.py:1742-1815`). Revisão velha → 409 (`backstage/services/orders.py:424-425`). **[INFERÊNCIA] Habilitar no Gestor exige que a tela mande `base_revision: revisions.edit` — que ela já recebe.** O Gestor tem `useOrderIntention.ts:98-101` montando `/orders/<ref>/<operation>/`; bastaria `"edit"`/`"reschedule"` na allowlist de `useOrderDetail.ts:66` (hoje ausentes).

**L9 — Risco de notificação duplicada/errada.** [FATO] O aviso é deduplicado por `order+aviso+occurrence` (`order_edit.py:1142-1146`), e o reagendar dentro da edição vai com `notify=False` (`order_edit.py:456`) para sair **uma mensagem só**. Um caminho novo no Gestor que chame `reschedule` direto **e** `edit` mandaria duas mensagens.

**L10 — Higiene documental.** [FATO] `surfaces/pos-nuxt/app/composables/usePosPreorderActions.ts:152` afirma *"Reagendar: a MESMA rota do Gestor"* — a rota é a mesma, mas **o Gestor não a chama** (grep §A4). E `docs/plans/ENCOMENDAS-PDV-PLAN.md:148-149` ainda diz que o texto do `order_updated` é RASCUNHO, enquanto `whatsapp-templates-meta.md:302` registra **aprovado em 29/09**.

---

## 5. Recomendações acionáveis (ordenadas por impacto/esforço)

### R1 — Servidor: emitir o bloco de gestos no contexto `"orders"` *(impacto alto, esforço baixo)*
**[INFERÊNCIA]** Extrair de `preorders.build_counter_block` (`preorders.py:445-461`) a parte que é **régua pura** (`_edit`, `:496-505`; `_reschedule`, `:481-493`; `_cancel`, `:508-526`) e passá-la a ser montada também no contexto `"orders"` — com um envelope novo (ex.: `manage`) ou ampliando `counter`. Consequências obrigatórias:
- atualizar `shopman/backstage/tests/test_order_detail_context.py:90` (`assert order["counter"] is None`);
- reabrir, por escrito, `docs/plans/ENCOMENDAS-PDV-PLAN.md:229`;
- decidir o nome do bloco (a decisão do dono de 28/09 é "o contexto decide as ações, **no servidor**", `order_queue.py:516-521`).

### R2 — Gestor: expor "Reagendar" *(impacto médio-alto, esforço baixo)*
**[FATO]** É o gesto mais barato de transpor: o serviço já existe e é idempotente (`reschedule.py`), o diálogo já existe em `PosPreorderRescheduleDialog.vue`, e a revisão (`revisions.schedule`) já chega ao Gestor (`order_queue.py:741`). Falta: o botão no slot `#actions` (`surfaces/orders-nuxt/app/pages/[ref].vue:261-311`), `"reschedule"` na allowlist de `useOrderDetail.ts:66`, e o diálogo (candidato natural a subir para `operator-kit`, já que POS e Gestor passariam a compartilhar). **Não depende de R1 se a tela gate pelo `counter/manage.allowed` — depende.**

### R3 — Gestor: editar itens — escolher entre A e B *(impacto alto, esforço médio/alto)*
- **A — Deep-link para o PDV em modo edição.** O Gestor mostra "Editar encomenda" e leva para `https://pdv.../?edit=<ref>` (o PDV já abre a comanda virtual, `index.vue:949`). Zero UI nova; exige que quem atende o WhatsApp esteja num terminal com caixa — o que **não** é o caso do gestor que fala com o cliente.
- **B — Editor no Gestor.** Um carrinho simplificado (busca de SKU + quantidade + observação + recebimento + data) montando o mesmo corpo de `orderEditBody` (`presentation/orderEdit.ts:63-117`) e chamando os **mesmos** endpoints. É o único caminho que serve o caso WhatsApp ponta a ponta, e é onde mora o esforço. **[INFERÊNCIA]** O servidor não muda em nenhum dos dois.

### R4 — Decidir e desenhar "trocar a forma de pagamento" *(impacto alto na queixa, esforço médio — decisão de produto antes de código)*
**[INFERÊNCIA]** Três semânticas distintas, com desenhos distintos (ver §6): (i) trocar a forma de uma **cobrança pendente** (Pix aberto → paga na retirada); (ii) trocar a forma de um pedido **já pago** (exige estornar e recobrar); (iii) **escolher a forma no ato** (já existe, §A5). Se for (i), o trabalho é: cancelar o intent vivo (`payment.cancel`/`counter_takeover`), reescrever `payment.method`/`collection`/a tender pendente e reavisar — provavelmente um `change_payment_method` novo em `order_edit.py`, com a **mesma** régua de plano/prévia/evento/aviso e o mesmo PIN.

### R5 — Decidir onde a devolução em dinheiro acontece *(impacto médio, esforço baixo/médio)*
Ou o Gestor ganha um "Precisa de você" (expondo `pending_cash_refunds`/`pending_card_machine_refunds` fora do turno, hoje presas a `cash_shift.terminal.channel_ref`, `pos.py:2106-2137`), ou a tela do Gestor diz explicitamente "a devolução em dinheiro fica na Sessão de caixa do PDV" — que é a frase que o PDV já usa (`PosPreorderCancelDialog.vue:34`).

### R6 — Higiene *(esforço mínimo)*
Corrigir `usePosPreorderActions.ts:152` ("a MESMA rota do Gestor" sem consumidor no Gestor) e o status do template em `ENCOMENDAS-PDV-PLAN.md:148-149`.

---

## 6. Perguntas abertas / o que não consegui verificar

1. **O que exatamente significa "alterar a forma de pagamento" neste caso?** [NÃO VERIFICADO] As três leituras de §R4 levam a trabalhos diferentes: (i) *ainda não pagou* (Pix aberto/link vivo) e quer pagar de outro jeito; (ii) *já pagou* (cartão online capturado) e quer migrar para dinheiro na retirada; (iii) *paga na entrega/retirada* e quer mudar a forma combinada. **Só (iii) existe hoje** (`settle_delivery_cash`). Preciso de um caso concreto do WhatsApp para não desenhar a coisa errada.
2. **Pedido imediato da loja online também entra no escopo?** [NÃO VERIFICADO] A queixa diz "pedidos da Loja Online" sem qualificar. A aba Encomendas cobre pedidos com data (`find_preorder`, `preorders.py:426-442`); o endpoint `/edit/` aceitaria um pedido imediato, mas a régua de data/estoque é outra.
3. **Quem opera o Gestor tem caixa?** [NÃO VERIFICADO] `refund_cash` exige turno aberto (`payment.py:1036`). Se quem atende o WhatsApp não tem turno, a devolução em dinheiro será sempre uma pendência para o PDV — e isso muda a UX.
4. **O Gestor deveria ser a superfície do atendimento por WhatsApp?** [NÃO VERIFICADO] Não achei plano nem decisão que diga quem opera a conversa. Se for o concierge (`shopman/storefront/concierge/tools.py:186` já chama `sessions.modify_session`, mas isso é **sessão**, não pedido), o caminho é outro.
5. **A permissão basta?** [NÃO VERIFICADO empiricamente] Não testei em runtime se um operador com `shop.manage_orders` consegue, de fato, chamar `POST /orders/<ref>/edit/` hoje pelo Gestor sem UI. É leitura de código: não há trava por superfície (§A4).
6. **Não verifiquei** estado de PRs/branches remotos (`claude/encomenda-editar-pendencias`, `claude/ultimas-vendas-pela-saida`), nem rodei testes (`PYTHONPATH`/`PYTHON` não configurados para a worktree). Toda evidência aqui é leitura estática na revisão `f0ffd02fd`.
7. **Não encontrado** em lugar nenhum: plano, ADR ou relatório que projete edição de pedido **no Gestor** ou troca de forma de pagamento de pedido **já fechado**. Onde procurei: `docs/plans/`, `docs/reports/`, `docs/decisions/`, `docs/reference/` — termos `amend`, `retificar`, `alterar pedido`, `editar pedido`, `loja online` + editar/alterar/mudar/trocar, `trocar forma de pagamento`. Os únicos hits relevantes foram `ENCOMENDAS-PDV-PLAN.md:229` (fora de escopo) e `WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md:171` ("alterar pedido depois de criado" listado em **"Out"**).

---

## Anexo — índice de evidências por arquivo

| Arquivo | Linhas citadas |
|---|---|
| `packages/orderman/shopman/orderman/models/order.py` | 77, 220-233, 59-71, 100-103, 411-443 |
| `shopman/shop/services/order_composition.py` | 1-41, 52, 55-74, 149-166, 169-196, 209-217, 223-280, 286-309 |
| `shopman/shop/services/order_edit.py` | 1-44, 69, 71-78, 90, 95-105, 140-170, 183-232, 238-241, 244-267, 273-397, 388, 398-487, 413-414, 415-419, 445, 456, 462-475, 794-846, 904-993, 1021-1038, 1044-1078, 1136-1146, 1158-1207 |
| `shopman/shop/services/reschedule.py` | 1-27, 198-224 |
| `shopman/shop/services/pos_edit_session.py` | 56-113 (`open_edit_session`, delega `:63-65`) |
| `shopman/shop/services/operator_orders.py` | 1177-1221, 1607-1619, 1638-1705 |
| `shopman/shop/services/payment.py` | 674, 844-856, 933, 1017-1037, 1228, 1461, 1491, 1506 |
| `shopman/backstage/projections/order_queue.py` | 516-554, 690-706, 707-795, 741, 752, 802-846, 1966-1977 |
| `shopman/backstage/projections/preorders.py` | 257-276, 426-461, 464-505, 508-526 |
| `shopman/backstage/projections/pos.py` | 2066-2067, 2106-2137 |
| `shopman/backstage/api/operations.py` | 1695, 1740, 1742-1815, 2248-2272, 2275-2341, 2354-2385, 2399-2449, 2627-2656 |
| `shopman/backstage/api/urls.py` | 593, 642, 646-648, 837, 883-898 |
| `shopman/backstage/services/orders.py` | 403-432 |
| `shopman/backstage/tests/test_order_detail_context.py` | 85-113 |
| `shopman/backstage/tests/test_api_order_edit.py` | 103-108, 111-130, 133-152, 155-166, 169-184, 187-208, 242-275 |
| `surfaces/pos-nuxt/app/composables/usePosOrderEdit.ts` | 57-74, 95-116, 119-154 |
| `surfaces/pos-nuxt/app/composables/usePosPreorderActions.ts` | 152, 156-178 |
| `surfaces/pos-nuxt/app/pages/preorders/[ref].vue` | 68-71, 218-241 |
| `surfaces/orders-nuxt/app/pages/[ref].vue` | 261-311, 278, 247-370 |
| `surfaces/orders-nuxt/app/composables/useOrderDetail.ts` | 66, 98-101 (via `useOrderIntention.ts`) |
| `surfaces/orders-nuxt/app/generated/ordersContract.ts` | 475, 485, 486-503, 585 |
| `docs/plans/ENCOMENDAS-PDV-PLAN.md` | 58-70, 114-132, 134-202, 204-223, 225-229 |
| `docs/reference/data-schemas.md` | 163-165, 240, 380, 396, 397, 1819 |
| `docs/reference/whatsapp-templates-meta.md` | 302-305, 559 |
| `docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-03-agente-c-gestor-pedidos.md` | 84-99 |
| `docs/plans/WP-CHECKOUT-ADDRESS-LOCATION-DIVERGENCE-2026-09-28.md` | 171 |

**Commits citados** [FATO — `git log`]: `5a655b8a3` (28/09, serviço + API da edição) · `5f78487be` (28/09, a tela de venda vira o editor) · `b0acbb392` (29/09, remarcar lê os itens vigentes) · `523dfcb8b` (`feat(pos): reorganize Encomendas for counter flow`) · `a05f82af9` / `9f2655650` / `8358f9296` (28–29/09, Encomendas unificada).
