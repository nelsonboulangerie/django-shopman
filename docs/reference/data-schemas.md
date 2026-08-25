# Data Schemas — JSONField Reference

> Inventário completo de chaves usadas nos JSONFields do Core e App.
> **Regra**: toda nova chave deve ser documentada aqui antes de ser usada.
> Ver também: [CLAUDE.md](../../CLAUDE.md) § "Core é Sagrado".

---

## Session.data

Unidade mutável pré-commit (carrinho). Populado pelo App (views, CartService, handlers).
O Core não impõe schema — a governança é por convenção documentada aqui.

### Chaves de negócio (populadas por views/services)

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `customer` | `dict` | CheckoutView, POS, API (`set_data`), iFood webhook | CommitService, handlers | Dados do cliente: `{name, phone, notes, ref, price_tier, cpf, address}` |
| `fulfillment_type` | `string` | CheckoutView, POS, API, iFood webhook | CommitService, MinimumOrderValidator | `"pickup"` ou `"delivery"` |
| `delivery_address` | `string` | CheckoutView, API, iFood webhook | CommitService, CustomerIdentificationHandler | Endereço formatado (texto livre) |
| `delivery_date` | `string` | CheckoutView | CommitService | ISO date (`YYYY-MM-DD`). Se futuro, indica encomenda |
| `delivery_time_slot` | `string` | CheckoutView | CommitService | Ref do slot configurado em `Shop.defaults["pickup_slots"]` (`"slot-09"`, `"slot-12"`, `"slot-15"`); o label ("A partir das 09h") resolve via `storefront.services.pickup_slots.slot_label` |
| `order_notes` | `string` | CheckoutView, iFood webhook | CommitService, KDS ticket (`customer_note`) | Observações do pedido escritas pelo **cliente** no checkout. Exibida no ticket do KDS (nota do cliente). Distinta da `kitchen_note` (nota do operador) |
| `origin_channel` | `string` | CartService, POS, iFood webhook | CommitService, hooks.py | Canal de origem: `"web"`, `"whatsapp"`, `"ifood"`, `"pos"`, `"instagram"` |
| `coupon_code` | `string` | CartService.apply_coupon | CouponModifier, CartService.get_cart_summary | Código do cupom aplicado (uppercase) |
| `outside_business_hours` | `bool` | BusinessHoursRule (validation) | CheckoutView, CommitService | `True` se pedido feito fora do horário. Não bloqueia checkout — apenas flag informativa |
| `delivery_address_structured` | `dict` | CheckoutView (`set_data`) | CommitService | Endereço estruturado do Google Places: `{route, street_number, complement, neighborhood, city, state_code, postal_code, place_id, formatted_address, delivery_instructions, is_verified, latitude, longitude}` |
| `payment` | `dict` | CheckoutView (`set_data`), POS, API | CommitService, hooks, handlers | Dados de pagamento iniciais: `{method}` (+ `change_for_q` em centavos quando dinheiro **na entrega** e o cliente pediu troco). Enriquecido por handlers pós-commit (intent_ref, status, etc.) |
| `delivery_fee_q` | `int` | DeliveryFeeModifier (via `session.save`) | CommitService, CartService, tracking view | Taxa de entrega efetiva em centavos. 0 = grátis (faixa/zona grátis ou subtotal ≥ `rules.free_delivery_above_q`). Resolvida por **faixa de distância** (`DeliveryDistanceBand`, motor) com **zona** (`DeliveryZone` modo `override`) como exceção. Só presente quando `fulfillment_type == "delivery"` e há cobertura. Reavaliada a cada passagem dos modifiers (depende do subtotal). Mapeável a `vFrete` na NF-e — **nunca** vira OrderItem |
| `delivery_fee_override_q` | `int \| null` | POS (`build_session_ops`) | `pos._resolve_delivery_fee` | A **exceção** de taxa que o operador do balcão assumiu para esta entrega (combinado de porta, cortesia), em centavos. `null`/ausente = sem exceção, e a taxa é a que o motor resolve pelo endereço — nunca leia ausência como zero. Existe porque no PDV a taxa deixou de ser digitada: o campo livre era um segundo dono do preço, e duas vendas do mesmo endereço saíam diferentes conforme quem estava no caixa. Fica gravada ao lado da `delivery_fee_q` que ela produziu, para o rascunho retomado não voltar à tabela da loja em silêncio |
| `delivery_zone_error` | `bool` | DeliveryFeeModifier (via `session.save`) | DeliveryZoneRule validator | `True` quando o endereço está fora da área: sem faixa de distância que o cubra, ou zona `exclude` casada. Bloqueia commit |
| `delivery_distance_km` | `float` | DeliveryFeeModifier (via `session.save`) | checkout/tracking (transparência) | Distância loja→endereço em km (1 casa), quando calculável (lat/lng presentes). Exibida ao cliente p/ justificar a taxa. Ausente quando não há coordenada |
| `delivery_address_id` | `int` | `web/views/checkout.py` | `checkout_defaults.py` | FK para `CustomerAddress.pk`. Usada para inferir defaults na sessão. **Não propagada ao Order.data** — somente em Session.data |
| `stock_check_unavailable` | `list[dict]` | `lifecycle._check_availability` (via `check_on_commit`) | — | SKUs rejeitados por indisponibilidade durante check pré-commit. Cada entry: `{sku, error_code}`. Presente quando pedido é cancelado por `auto_reject_unavailable` |
| `manual_discount` | `dict` | POS `pos_close` view | `ModifyService` (via `set_data`) | Desconto manual do operador: `{type, value, discount_q, reason}`. `type`: `"percent"` ou `"fixed"` |
| `tab_ref` | `string` | POS tab service | POS tab service, projections | Referência canônica da comanda. Aceita texto curto alfanumérico; referências numéricas de até 8 dígitos continuam normalizadas com zeros. Ex: `"00001007"`, `"MESA ANA"` |
| `tab_display` | `string` | POS tab service | POS UI, Order.data | Rótulo curto para operador. Em numéricos, remove zeros à esquerda; em texto, preserva o rótulo informado. Ex: `"1007"`, `"mesa ana"` |
| `pos_operator` | `string` | POS tab service | POS projections, Order.data | Username do operador que abriu/tocou o POS tab |
| `last_touched_at` | `string` | POS tab service | POS projections | Timestamp ISO da última interação operacional |
| `fired_lines` | `list[str]` | POS `fire_pos_tab` (`session.save`) | `_tab_payload` (flag `fired` por item) | Marker UI de quais `line_id` da comanda já foram disparados à cozinha (KDS). Mirror do ledger autoritativo (tickets KDS por `session_key`, que sobrevive ao commit); escrito direto, sem re-pricing. Disparo progressivo curso-a-curso. **Não propagado ao Order.data** — o ledger pós-commit são os próprios `KDSTicket` |
| `fiscal` | `dict` | POS checkout | Order.data | Preferências fiscais capturadas no checkout: `{issue_document, tax_id}` |
| `receipt` | `dict` | POS checkout | Order.data, NFCeEmitHandler (e-mail da nota) | Preferência de comprovante: `{channels: [print\|email], email}` — canais MULTI: imprimir E enviar não competem; lista vazia = sem comprovante |
| `is_gift` | `bool` | CheckoutView, API (`set_data`) | CommitService, KDS/expedição | `True` quando o pedido é presente (entrega para terceiro). Só presente quando é presente. Ver [GIFT-UX-PLAN](../plans/GIFT-UX-PLAN.md) |
| `recipient` | `dict` | CheckoutView, API (`set_data`) | CommitService, KDS/expedição | Destinatário do presente: `{name, phone}`. **Não** é identidade (não vira Customer) nem sobrescreve o comprador. Integridade garantida por `intents.gift.build_gift_data` (nunca parcial). **Obrigatório só na ENTREGA**; em retirada ("embalar para presente") é opcional/omitido |
| `gift_message` | `string` | CheckoutView, API (`set_data`) | CommitService | Mensagem do presente para o destinatário. **Separada** de `order_notes` (operacional/cozinha). Opcional; só presente quando informada |
| `gift_hide_values` | `bool` | CheckoutView, API (`set_data`) | CommitService, nota/etiqueta, KDS | `True` para ocultar valores na nota/etiqueta do presente. Só presente quando `True` (ausência = mostrar valores) |
| `customer_rating` | `dict` | `OrderRateView` (storefront tracking) | `OrderAdmin` (coluna + detalhe), dashboard do Admin (média móvel + comentários), alerta `low_rating` (nota ≤2) | Avaliação do pedido pelo cliente: `{rating, comment, submitted_at, source}`. Só presente após o cliente avaliar. Loop fechado (RATING-LOOP-PLAN): a loja lê a nota no Admin e é avisada em nota baixa. Ver [[project_customer_rating_intent]] |

### Chaves de sistema (geridas pelo Core)

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `checks` | `dict` | WriteCheckResultService, ModifyService (reset) | CommitService, StockReleaseHandler, CheckoutView | Resultados de checks: `{check_code: {rev, at, result}}` |
| `issues` | `list[dict]` | WriteCheckResultService, ModifyService (reset) | CommitService, ResolveIssueService, admin, CheckoutView | Issues de validação: `[{id, code, source, blocking, message, data}]` |

### Paths permitidos via `set_data` (OpSerializer)

O `ModifyService` aceita operações `set_data` nas seguintes paths:
`customer`, `delivery`, `payment`, `notes`, `meta`, `extra`, `custom`, `tags`,
`discounts`, `fees`, `tip`, `coupon`, `source`, `operator`, `table`, `tab`,
`fulfillment_type`, `delivery_address`, `delivery_address_structured`,
`delivery_date`, `delivery_time_slot`, `order_notes`,
`is_gift`, `recipient`, `gift_message`, `gift_hide_values`.

Paths **proibidas** (geridas pelo sistema): `checks`, `issues`, `state`, `status`,
`rev`, `session_key`, `channel`, `items`, `pricing`, `pricing_trace`, `__`.

### Exemplo completo

```json
{
  "customer": {"name": "João Silva", "phone": "5543999990001", "notes": "Alergia a nozes"},
  "fulfillment_type": "delivery",
  "delivery_address": "Rua das Flores 123 - Centro - Londrina",
  "delivery_date": "2026-04-01",
  "delivery_time_slot": "slot-09",
  "order_notes": "Sem cebola",
  "origin_channel": "whatsapp",
  "coupon_code": "WELCOME10",
  "checks": {
    "stock": {
      "rev": 3,
      "at": "2026-03-30T10:00:00Z",
      "result": {
        "holds": [{"hold_id": "H-1", "expires_at": "2026-03-30T10:30:00Z"}]
      }
    }
  },
  "issues": []
}
```

---

## Order.data

Pedido canônico (selado). Populado pelo CommitService (cópia de Session.data) e por handlers pós-commit.

### Chaves copiadas de Session.data (CommitService._do_commit)

A lista de chaves propagadas está explícita em `commit.py`, método `_do_commit()`:

```python
for key in (
    "customer", "fulfillment_type", "delivery_address",
    "delivery_address_structured", "delivery_date",
    "delivery_time_slot", "order_notes",
    "origin_channel", "payment",
    "delivery_fee_q",
    "is_gift", "recipient", "gift_message", "gift_hide_values",
):
```

> `is_gift` / `recipient` / `gift_message` — presente (entrega para terceiro),
> ver [GIFT-UX-PLAN](../plans/GIFT-UX-PLAN.md). Só presentes quando o pedido é
> presente; a integridade (recipient nunca parcial) é garantida na escrita por
> `shopman.storefront.intents.gift.build_gift_data`.

**Para adicionar uma nova chave ao fluxo Session→Order, adicione-a nessa lista.**

### Chaves adicionadas por modifiers pré-commit (Session.data → Order.data)

| Chave | Tipo | Escrito por | Descrição |
|-------|------|-------------|-----------|
| `delivery_fee_q` | `int` | DeliveryFeeModifier | Taxa de entrega em centavos. 0 = grátis |

### Chaves computadas pelo CommitService

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `is_preorder` | `bool` | `True` se `delivery_date > hoje`. Calculado no commit |

### Chaves adicionadas por handlers pós-commit

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `payment` | `dict` | CommitService (propaga `{method}` de Session.data), `payment.initiate()`, webhooks | Muitos (ver abaixo) | Dados de pagamento. Contrato: `{intent_ref, method}`. Status de pagamento vive em Payman — nunca duplicado aqui. Ver detalhamento abaixo. |
| `customer_ref` | `string` | CustomerIdentificationHandler | CheckoutInferDefaultsHandler | Ref do Customer criado/encontrado |
| `fulfillment_created` | `bool` | FulfillmentCreateHandler | FulfillmentCreateHandler (idempotência) | Flag: Fulfillment object criado |
| `cancellation_reason` | `string` | PixTimeoutHandler, PaymentTimeoutHandler, ConfirmationTimeoutHandler, OrderCancelView, GestorOrderRejectView | hooks._on_cancelled | Motivo (auditoria): `"pix_timeout"`, `"card_timeout"`, `"confirmation_timeout"`, `"customer_requested"`, texto livre. **Pode conter código de máquina — nunca exibir ao cliente.** |
| `cancellation_note` | `string` | `operator_orders.cancel_order` (via OrderCancelView `customer_note`) | `lifecycle._on_cancelled` | Justificativa **voltada ao cliente**, escrita/escolhida pelo operador (preset). Só existe em cancelamento por operador com motivo informado; entra na notificação `order_cancelled` (`{reason_note}`). Ausente ⇒ mensagem genérica. Distinta de `cancellation_reason` (que carrega códigos de máquina) |
| `rejected_by` | `string` | GestorOrderRejectView | — | Username do operador que rejeitou |
| `kitchen_note` | `string` | OrderNotesView (`operator_orders.save_kitchen_note`) | OperatorOrderProjection (`kitchen_note`), KDS ticket (`kitchen_note`) | Nota da cozinha escrita pelo operador no gestor (tags pré-configuradas `Shop.kitchen_note_tags` anexadas + texto livre). **Exibida no ticket do KDS** para a produção. Distinta da `order_notes` (nota do cliente, do checkout) e dos `operator_comment` do histórico |
| `assignment` | `dict` | OrderAssignView (operator_orders.assign_order) | OrderCardProjection (`assigned_operator`) | Operador que assumiu o pedido ("estou atendendo"): `{operator_id, operator_name, at}`. Removido por OrderUnassignView |
| `returns` | `list[dict]` | ReturnService | ReturnHandler | Histórico de devoluções (ver detalhamento) |
| `nfce_access_key` | `string` | NFCeEmitHandler | NFCeEmitHandler (idempotência), ReturnService | Chave de acesso NFCe |
| `nfce_number` | `int` | NFCeEmitHandler | — | Número do documento |
| `nfce_danfe_url` | `string` | NFCeEmitHandler | — | URL do DANFE PDF |
| `nfce_qrcode_url` | `string` | NFCeEmitHandler | — | URL do QR code |
| `nfce_cancelled` | `bool` | NFCeCancelHandler | NFCeCancelHandler (idempotência) | NFCe cancelada |
| `nfce_cancellation_protocol` | `string` | NFCeCancelHandler | — | Protocolo de cancelamento |
| `nfce_series` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | Série do documento NFC-e emitido via FocusNFe |
| `nfce_protocol` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | Número do protocolo de autorização |
| `nfce_xml_url` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | URL do XML autorizado |
| `nfce_status` | `string` | `shop/handlers/fiscal.py` (FocusNFe) | — | Status da emissão (ex.: `autorizado`, `erro`) |
| `nfce_email_sent_at` | `string` | NFCeEmitHandler (`_send_receipt_email`) | NFCeEmitHandler (idempotência do envio) | ISO datetime de quando o Focus aceitou enviar a nota por e-mail. Só entra quando o provedor aceitou; reenvio manual (Últimas vendas do PDV) não depende dele |
| `receipt_printed_at` | `string` | `POSSaleReceiptEscposView` (`_stamp_first_print`) | `POSSaleReceiptEscposView` (decisão de 2ª via) | ISO datetime da PRIMEIRA composição do recibo não fiscal (`receipt-escpos`). Presente ⇒ toda composição seguinte sai carimbada "2a VIA". Marca na composição, não na confirmação do papel |
| `danfe_printed_at` | `string` | `POSDanfeEscposView` (`_stamp_first_print`) | `POSDanfeEscposView` (decisão de 2ª via) | ISO datetime da PRIMEIRA composição da DANFE em bobina (`danfe-escpos`). Mesma semântica de `receipt_printed_at` — o servidor decide "2ª via", a tela não chuta |
| `fiscal.tax_id` | `string` | POS checkout (só com `issue_fiscal_document`) | `on_request_or_tax_id`, `_fiscal_customer` (payload da emissão) | CPF/CNPJ **pedido NESTA venda** ("CPF na nota"). ⚠️ Nunca ler `customer.tax_id` para fins fiscais: aquele é cadastro/CRM — usá-lo tornava o CPF compulsório para cliente identificado |
| `availability_decision` | `dict` | `lifecycle.approve_with_adjustments()`, `lifecycle.approve_order()`, `lifecycle.reject_order()` | `lifecycle.has_availability_approval()`, `lifecycle.ensure_confirmable()`, `services/stock.py` | Decisão do operador sobre disponibilidade: `{approved: bool, decisions: [{sku, original_qty, approved_qty, action}], decided_at, decided_by}`. Guard para confirmação |
| `cancelled_by` | `string` | `services/cancellation.py` | `hooks._on_cancelled` | Identificador de quem cancelou: `"customer"` ou `"operator:<username>"` |
| `session_key` | `string` | hooks._on_cancelled | hooks._on_cancelled | Chave de sessão original (referência para release holds) |
| `hold_ids` | `list[dict]` | `StockService.hold(order)` | `StockService.fulfill(order)`, `StockService.release(order)` | Holds do Stockman adotados no commit. Cada entry: `{sku, hold_id, qty}` |
| `lifecycle` | `dict` | `lifecycle.dispatch()` (via `_mark_phase_complete`, fases em `DURABLE_PHASES`) | `sweep_stuck_orders`, `reconcile_payments`, `lifecycle.phase_complete()` | Marcador durável de conclusão de fase: `{on_commit: "done", on_confirmed: "done", on_paid: "done", on_cancelled: "done"}` (só as chaves das fases já completas). O dispatch roda pós-commit (não durável); um crash entre o COMMIT da transição e o fim do handler perde a fase (hold, fulfill, ticket KDS, notificação, estorno). O `dispatch()` grava o marcador APÓS o handler retornar; o sweeper re-despacha, idempotente, as fases sem marcador (NEW→`on_commit`, CONFIRMED→`on_confirmed`, pagos→`on_paid`, CANCELLED→`on_cancelled`) |
| `loyalty` | `dict` | `LoyaltyRedeemModifier` (via `CommitService`) | `services/loyalty.py` (redeem), `LoyaltyRedeemHandler` | Resgate de pontos: `{redeem_points_q: int, applied_discount_q: int}`. `redeem_points_q` = pedido pelo cliente; `applied_discount_q` = desconto efetivamente aplicado (clampado ao subtotal) — é o valor DEBITADO. Propagada Session→Order na lista do `_do_commit()` |
| `awaiting_wo_refs` | `list[string]` | `shop.handlers.production_order_sync` | Backstage pedidos/producao projections | Refs de WorkOrders que cobrem itens produzidos do pedido. Contextual, derivável e limpável em void. |
| `pos_committed_at` | `string` | `shop/services/pos.py` (`_mark_tab_committed`) | — | Timestamp ISO de quando a comanda foi finalizada no POS |
| `client_request_id` | `string` | `shop/services/pos.py` (`_mark_tab_committed`) | `_existing_sale_by_client_request_id` (dedupe) | Chave de idempotência do checkout direto POS. Espelhada em `pos.client_request_id` |
| `pos` | `dict` | `shop/services/pos.py` (`_mark_tab_committed`, `close_sale`) | POS projections | Contexto POS selado no Order: `{terminal_ref, client_request_id, direct_checkout, intent_version, customer_memory_action}`. **Não há `cash_shift_id`**: a atribuição da venda ao turno é a linha `sale` no livro do `cashman` (ADR-022), nunca etiqueta no pedido |
| `external_order_code` | `string` | `shop/services/ifood_ingest.py` | — | Código do pedido no marketplace iFood. Duplicado em `ifood.order_code` |
| `merchant_id` | `string` | `shop/services/ifood_ingest.py` | — | ID do merchant na iFood. Duplicado em `ifood.merchant_id` |
| `ifood` | `dict` | `shop/services/ifood_ingest.py` | — | Contexto da iFood (só em pedidos ingeridos via `ifood_ingest`): `{order_code, merchant_id, created_at}` |
| `courier` | `dict` | `CourierDispatchHandler`, `services/courier.apply_status` | `_courier_block` (projection do gestor), webhook Machine (lookup por `data__courier__id_mch`), notificação (`courier_tracking_url`) | Corrida de entrega na logística externa (Machine). Ver detalhamento abaixo |
| `dispatch` | `dict` | `operator_orders.advance_order` (despacho da entrega da casa), `mark_equipment_returned` / `settle_delivery_cash(equipment_back=True)` | `operator_orders.equipment_custody` / `equipment_out`, card e quadro do gestor (`equipment_*`) | Custódia do **dispositivo** que saiu com o entregador (maquininha): `{equipment: ["card_machine"], equipment_out_at, equipment_out_by, equipment_back_at?, equipment_back_by?}`. Refs permitidas vêm de `ChannelConfig.fulfillment.equipment`. Não é dinheiro: fora do livro do `cashman`. "Onde está a maquininha" é derivado (saiu e não voltou) |

### courier — detalhamento

Corrida de entrega via logística externa (Machine/Gaudium). Escrito pelo
`CourierDispatchHandler` (abertura) e por `services/courier.apply_status`
(funil único de status: webhook + polling convergem nele). Status usa a letra
crua da Machine (`D` distribuindo, `G` aguardando aceite, `P` pendente, `A`
aceita, `S` em espera, `E` em andamento, `F` finalizada, `N` não atendida,
`C` cancelada, `U` agrupada); labels pt-BR só na projection.

```jsonc
"courier": {
  "provider": "machine",
  "id_mch": "184532",              // corrida ATIVA (string); some quando N/C arquiva
  "status": "E",                   // letra Machine crua
  "requested_at": "2026-07-07T18:02:11-03:00",
  "dispatched_at": null,           // setado no primeiro E (coleta)
  "finished_at": null,             // setado no F
  "driver": {"name": "", "phone": "", "vehicle_plate": "", "vehicle_model": ""},  // a partir de A
  "tracking_url": "",              // link de rastreio da parada (a partir de A)
  "confirmation_code": "",
  "estimate": {"value_q": 1250, "minutes": 18.0, "km": 4.2},  // custo interno (centavos)
  "final_value_q": null,           // finished.final_value convertido p/ centavos
  "last_event_at": "iso",
  "last_source": "webhook",        // "webhook" | "poll" | "dispatch" | "operator:<nome>"
  "attempts": [                    // corridas anteriores (N/C ou canceladas p/ re-despacho)
    {"id_mch": "184501", "status": "N", "requested_at": "iso", "ended_at": "iso"}
  ],
  "error": {"message": "...", "at": "iso"}  // falha terminal do despacho; limpo no re-despacho
}
```

### Chaves seed-only para QA adversarial

Estas chaves só devem ser escritas por seed/dados demo. Elas existem para
exercitar jornadas de seguranca, confiabilidade e atendimento, sem virar
contrato de negocio em producao.

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `edge_case` | `string` | Nelson seed | QA manual/automatizado, relatorios de auditoria | Marcador deterministico de cenario adversarial. Ex: `"low_attention_payment_pending"`, `"late_payment_after_cancel"`, `"marketplace_stale_confirmation"` |


### Chaves lidas por views (convenience — fallback para vazio)

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `customer_name` | `string` | — | **Não usar.** Views agora lêem `customer.name` canônico com fallback para `order.handle_ref`. Reservado para canais legados que achatam o nome |
| `delivery_method` | `string` | pedidos._enrich_order, kds._enrich_order, PedidoAdvanceView | **Não escrito pela checkout padrão.** Falls back para `""`. Previsto para canais que usam `delivery_method` em vez de `fulfillment_type` |
| `customer_phone` | `string` | NotificationHandler._resolve_recipient | **Não escrito diretamente.** Fallback quando `customer.phone` não encontrado |

### payment — detalhamento

**Contrato**: `{intent_ref, method}` são as chaves canônicas. Status de pagamento vive
em Payman (`PaymentService`) — nunca duplicado em `order.data`. Demais chaves são
dados de display (UI) ou audit (rastreabilidade).

```json
{
  "method": "pix",
  "intent_ref": "INT-abc123",
  "idempotency_key": "order-payment:ORD-001:pix:2500:...",
  "amount_q": 2500,
  "qr_code": "data:image/png;base64,...",
  "copy_paste": "00020126...",
  "expires_at": "2026-03-30T10:15:00Z",
  "e2e_id": "E123456789",
  "pix_receipts": {"E123456789": 2500},
  "paid_amount_q": 2500,
  "captured_at": "2026-03-30T10:12:00Z",
  "client_secret": "pi_xxx_secret_yyy",
  "transaction_id": "TXN-001",
  "error": "Gateway timeout (truncado a 200 chars)"
}
```

Classificações: **canonical** = fonte de verdade para decisões; **display** = dados de UI, nunca usado para lógica; **audit** = rastreabilidade; **idempotency** = flag de deduplicação.

**Status de pagamento NÃO está aqui** — consulte sempre `payment_svc.get_payment_status(order)` (canonical source: Payman).

**Invariante de canal — quem escreve `payment` escreve o valor FINAL.** O documento
fiscal deriva o desconto do que está aqui: o adapter NFC-e calcula
`valor_desconto = produtos + frete − pagamento`. Um `payment` defasado (menor que
`order.total_q` depois de uma edição pós-pagamento) não vira erro — vira um
**desconto que não houve** dentro de um XML válido, subdeclarando a venda. O PDV
já sela isso em `_reconcile_order_payment_to_total` (`shop/services/pos.py`) e
todo canal novo (ManyChat, iFood direto) herda a mesma disciplina. Guarda:
`shop/services/fiscal._payment_below_total` recusa emitir e levanta o alerta
`fiscal_payment_mismatch` em vez de mandar o documento errado.


| Sub-chave | Tipo | Classe | Escrito por | Lido por | Descrição |
|-----------|------|--------|-------------|----------|-----------|
| `method` | `string` | **canonical** | CheckoutView → CommitService; POS (`shop/services/pos.py`) | lifecycle, views, handlers | `"pix"`, `"card"`, `"cash"`, `"external"`; `"mixed"` quando o PDV recebe em mais de um meio (ver `tenders`) |
| `intent_ref` | `string` | **canonical** | `payment.initiate()` | `payment_svc.get_payment_status`, PaymentStatusView, reconciliação financeira | Ref do intent no Payman. Pix/cartão: intent do gateway. `cash`/`external` **com `collection == "terminal"`** (venda do PDV): intent capturado no ato (`PaymentService.settle`, `gateway=""`), gravado depois do total selado (ADR-022). Sem `collection` (loja online) ou `on_delivery` (COD): ausente até o acerto (`settle_delivery_cash` grava). Venda **mista** do PDV não tem `intent_ref` no topo: cada `tenders[].intent_ref` aponta o intent do seu método (pix/cartão dentro de mista nascem `asserted_at_terminal` no `gateway_data`). `account` ("em conta", só cliente com `Customer.metadata.house_account`): intent nasce **autorizado** (= deve; `PaymentService.charge_to_account`, `gateway_data.customer_ref`) e vira capturado no acerto (`gateway_data.settled_with/settled_by`); saldo devedor = Σ autorizados (derivado) |
| `idempotency_key` | `string` | idempotency | `payment.initiate()` | adapters Payman/gateway | Chave da tentativa de pagamento para retry seguro; não é status e não libera fluxo operacional |
| `amount_q` | `int` | **canonical** | `payment.initiate()`, POS (`_reconcile_order_payment_to_total`) | PaymentView, templates, emissão de NFC-e (`shop/services/fiscal`) | Valor em centavos. **Tem de ser o valor final da venda** (ver invariante acima): a NFC-e deriva o desconto dele. Em venda mista quem manda é a soma dos `tenders` |
| `qr_code` | `string` | display | `payment.initiate()` | PaymentView template | QR code image (data URI) — PIX only |
| `copy_paste` | `string` | display | `payment.initiate()` | PaymentView template | Brcode PIX copia-e-cola — PIX only |
| `expires_at` | `string` | display | `payment.initiate()` | PaymentStatusView (expiração) | ISO datetime de expiração do QR — PIX only |
| `client_secret` | `string` | display | `payment.initiate()` | PaymentView template | Stripe PaymentIntent secret — card only |
| `e2e_id` | `string` | audit + idempotency | `EfiPixWebhookView` | EfiPixWebhookView (deduplicação) | End-to-end ID da transação PIX |
| `pix_receipts` | `object` | audit + idempotency | `confirm_pix` | `confirm_pix` (soma dos recebimentos) | Um Pix por chave (`e2e_id`, ou `txid:<txid>` quando o chamador não tem e2e) → centavos. Existe para que dois Pix parciais SOMEM até cobrir a cobrança sem que a reapresentação do mesmo Pix conte duas vezes |
| `paid_amount_q` | `int` | audit | `confirm_pix` | `confirm_pix` (suficiência do recebido) | Total recebido em Pix para o pedido = soma de `pix_receipts`. **Não é prova de pagamento**: quem diz se a venda está paga é o Payman |
| `captured_at` | `string` | audit + idempotency | `confirm_pix` / `payment.capture()` / POS | `confirm_pix` (guard de re-dispatch do `on_paid`) | ISO datetime da captura SUFICIENTE (só gravado quando o valor capturado cobre `total_q`; pagamento parcial não grava) |
| `transaction_id` | `string` | audit | `payment.capture()` | — | Transaction ID do adapter pós-capture |
| `marked_paid_by` | `string` | legacy audit | endpoint removido | leitura histórica apenas | Campo legado de versões antigas; não é status de pagamento, não deve liberar fluxo operacional e não existe mais como ação de operador |
| `error` | `string` | audit | `payment.initiate()` | — | Mensagem de erro se create_intent falhou (max 200 chars) |
| `collection` | `string` | **canonical** | POS (`shop/services/pos.py`) | POS, cash service | `"terminal"` (recebido no balcão) ou `"on_delivery"` (recebido na entrega) |
| `tenders` | `list[dict]` | **canonical** | POS (`shop/services/pos.py`), acerto de entrega | POS, leitura X/Z, reconciliação | Linhas do pagamento: `{method, amount_q, collection, status, terminal_ref?, received_at?, reference?, intent_ref?}`. `intent_ref` é o intent do Payman daquele método (um por método; venda mista tem um por linha de método). **Sem `cash_shift_id`**: turno é lançamento no livro do `cashman` |
| `cash_received_q` | `int` | **canonical** | POS (`shop/services/pos.py`) | fechamento de caixa, B.I. de troco | Soma das linhas em espécie recebidas no terminal. É o que identifica venda em dinheiro num pagamento misto, em que `method` vira `"mixed"` |
| `tendered_q` | `int` | measurement | POS (`shop/services/pos.py`) | B.I. de troco | Quanto o cliente entregou em espécie. **Ausente quando o operador não digitou** — ausência de medição, nunca "pagou justo" |
| `change_q` | `int` | measurement | POS (`shop/services/pos.py`) | POS (revisão), B.I. de troco | Troco devolvido, em centavos. Escrito junto com `tendered_q`. É a única fonte de troco do sistema: `HistoricalSale` (export externo) **não tem troco**, e por isso a previsão de necessidade de troco lê só pedido nativo |
| `cod_settled_at` / `cod_settled_by` | `string` | audit | `operator_orders.settle_delivery_cash` | acerto (guard de repetição), gestor | Quando e quem acertou o dinheiro da entrega no balcão. O turno que recebeu **não** fica aqui: é a linha `cod_settled` no livro do `cashman` |
| `change_for_q` | `int` | **canonical** | checkout da loja (`storefront/api/views.py`, `intents/checkout.py`) e PDV (`shop/services/pos.py`, campo "Troco para quanto?" do checkout): dinheiro **na entrega** e o cliente disse com quanto paga | `operator_orders.change_out_suggested_q` (despacho: sugestão `change_for − total`, que vira `courier_out` no livro do caixa), projection do gestor (`change_for_q`/`change_label` no card) | Com quanto o cliente vai pagar na porta, em centavos. Era dado morto até o WP-9 do CASHMAN-PLAN: hoje o despacho pergunta quanto o entregador leva e o acerto quanto voltou |

### returns — detalhamento

```json
[
  {
    "timestamp": "2026-04-01T14:30:00Z",
    "actor": "operador@loja.com",
    "reason": "Cliente insatisfeito",
    "type": "partial",
    "items": [
      {"line_id": "L1", "sku": "CROIS-01", "qty": 2, "refund_q": 1500}
    ],
    "refund_total_q": 1500,
    "refund_processed": true
  }
]
```

### Exemplo completo (Order.data)

```json
{
  "customer": {"name": "João Silva", "phone": "5543999990001"},
  "fulfillment_type": "delivery",
  "delivery_address": "Rua das Flores 123",
  "delivery_address_structured": {
    "route": "Rua das Flores",
    "street_number": "123",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86020-000",
    "formatted_address": "Rua das Flores 123, Centro, Londrina - PR",
    "latitude": -23.31,
    "longitude": -51.16,
    "is_verified": true
  },
  "delivery_date": "2026-04-02",
  "delivery_time_slot": "slot-09",
  "order_notes": "Sem cebola",
  "origin_channel": "web",
  "is_preorder": true,
  "payment": {
    "method": "pix",
    "intent_ref": "INT-abc123",
    "idempotency_key": "order-payment:WEB-010426-ABCD:pix:2500:...",
    "amount_q": 2500,
    "e2e_id": "E123456789",
    "paid_amount_q": 2500
  },
  "customer_ref": "CUST-001",
  "fulfillment_created": true,
  "session_key": "sk_abc123"
}
```

---

## Order.snapshot

Snapshot selado do pedido no momento da criação. **Imutável** — nunca editado após o commit.
Escrito uma única vez por `CommitService._do_commit()`.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `items` | `list[dict]` | hooks._build_directive_payload (stock.hold), customers.OrderingOrderHistoryBackend | Itens da sessão: `[{line_id, sku, name, qty, unit_price_q, line_total_q, meta}]`. Campos extras no topo da linha NÃO sobrevivem ao `Session._normalize_items` (whitelist) — flag contextual de linha vive em `meta` |
| `data` | `dict` | handlers/customer.py (fallback), hooks (stock.commit holds) | Cópia integral de `session.data` no momento do commit |
| `pricing` | `dict` | customers.OrderingOrderHistoryBackend | Pricing da sessão: `{total_q, subtotal_q, discount_q, ...}` |
| `rev` | `int` | hooks._build_directive_payload (stock.hold) | Revisão da sessão no commit |
| `seed` | `string` | seed | QA/auditoria | Marcador de origem para dados demo. Não usado em lógica de negócio |
| `seed_namespace` | `string` | seed | QA/auditoria | Grupo deterministico do seed, ex: `"security_reliability_edges"` |
| `seed_key` | `string` | seed | seed idempotente, QA/auditoria | Chave unica do cenario seed para evitar duplicacao em reruns |

### Exemplo completo

```json
{
  "items": [
    {
      "line_id": "L1",
      "sku": "CROIS-01",
      "name": "Croissant Clássico",
      "qty": 2,
      "unit_price_q": 750,
      "line_total_q": 1500,
      "meta": {}
    }
  ],
  "data": {
    "customer": {"name": "João Silva", "phone": "5543999990001"},
    "fulfillment_type": "pickup",
    "origin_channel": "web",
    "checks": {"stock": {"rev": 1, "at": "...", "result": {"holds": []}}},
    "issues": []
  },
  "pricing": {
    "subtotal_q": 1500,
    "discount_q": 0,
    "total_q": 1500
  },
  "rev": 1
}
```

---

## Directive.payload

Payload da tarefa assíncrona. Schema varia por `topic`.

### Chaves comuns (presentes na maioria dos directives)

| Chave | Tipo | Presente em | Escrito por | Descrição |
|-------|------|-------------|-------------|-----------|
| `order_ref` | `string` | Todos exceto admin checks | hooks._build_directive_payload | Ref do pedido |
| `channel_ref` | `string` | stock.*, payment.capture | hooks._build_directive_payload | Ref do canal |
| `session_key` | `string` | stock.*, payment.capture, admin checks | hooks._build_directive_payload | Chave da sessão original |
| `origin_channel` | `string` | Directives gerados por hooks | hooks._build_directive_payload | Canal de origem (informativo) |

### Payloads por topic

#### `stock.hold`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | StockHoldHandler |
| `channel_ref` | `string` | hooks | StockHoldHandler |
| `session_key` | `string` | hooks | StockHoldHandler |
| `rev` | `int` | hooks | StockHoldHandler (stale check) |
| `items` | `list[dict]` | hooks | StockHoldHandler |

Write-back: `holds` (list de hold objects do backend)

#### `stock.commit`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | StockCommitHandler |
| `channel_ref` | `string` | hooks | StockCommitHandler |
| `holds` | `list[dict]` | hooks (from snapshot checks) | StockCommitHandler |

#### `confirmation.timeout`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks._on_order_created | ConfirmationTimeoutHandler |
| `expires_at` | `string` | hooks._on_order_created | ConfirmationTimeoutHandler |

#### `preorder.activate`

Despertador da encomenda (pedido com `delivery_date` futura): o lifecycle adia
KDS e baixa e agenda esta directive com `available_at` na madrugada da data.
Dedupe: `preorder.activate:{order_ref}`.

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | lifecycle._schedule_preorder_activation | PreorderActivateHandler |
| `channel_ref` | `string` | lifecycle._schedule_preorder_activation | PreorderActivateHandler |
| `delivery_date` | `string` (ISO) | lifecycle._schedule_preorder_activation | auditoria |

#### `pix.generate`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | PixGenerateHandler |
| `amount_q` | `int` | hooks | PixGenerateHandler |
| `pix_timeout_minutes` | `int` | hooks (from channel config) | PixGenerateHandler (default 10) |

Write-back: spawns `pix.timeout` e `notification.send` (reminder)

#### `pix.timeout`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | PixGenerateHandler | PixTimeoutHandler |
| `intent_ref` | `string` | PixGenerateHandler | PixTimeoutHandler |
| `expires_at` | `string` | PixGenerateHandler | PixTimeoutHandler |

#### `mock_pix.confirm`

Só dev/staging: o adapter `payment_mock` agenda a confirmação do PIX que nunca
vai chegar de gateway nenhum. Nasce apenas com `mock_pix_auto_confirm=True`, e
o handler recusa (`DirectiveTerminalError`) se a chave vier diferente — a
autoconfirmação é opt-in explícito, nunca inferida.

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | `adapters.payment_mock` | MockPixConfirmHandler |
| `txid` | `string` | `adapters.payment_mock` | MockPixConfirmHandler → `confirm_pix` |
| `e2e_id` | `string` | `adapters.payment_mock` | MockPixConfirmHandler → `confirm_pix` |
| `amount` | `string` | `adapters.payment_mock` | MockPixConfirmHandler → `confirm_pix` |
| `mock_pix_auto_confirm` | `bool` | `adapters.payment_mock` | MockPixConfirmHandler (recusa se ≠ `True`) |

> `amount` é decimal em reais como string (`"12.50"`), não centavos — é o
> formato de fio do gateway, convertido por `_amount_to_q`. **Chamava-se
> `valor`**: o nome era da API da Efí e vazou para um payload nosso, que só o
> nosso handler lê. Renomeada junto com o resto do caminho de pagamento; o
> `valor` sobrevive apenas onde é contrato da Efí de verdade
> (`pix_item["valor"]`, `{"valor": {"original": …}}`).

#### `payment.capture`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks / web view | PaymentCaptureHandler |
| `intent_ref` | `string` | hooks / web view | PaymentCaptureHandler |
| `amount_q` | `int` | hooks / web view | PaymentCaptureHandler |
| `session_key` | `string` | hooks (opcional) | PaymentCaptureHandler (fallback lookup) |
| `channel_ref` | `string` | hooks (opcional) | PaymentCaptureHandler (fallback lookup) |
| `method` | `string` | web view (opcional) | PaymentCaptureHandler |

Write-back: `transaction_id` (string)

#### `payment.timeout`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | PaymentTimeoutHandler |
| `intent_ref` | `string` | hooks | PaymentTimeoutHandler |
| `expires_at` | `string` | hooks | PaymentTimeoutHandler |
| `method` | `string` | hooks | PaymentTimeoutHandler (default `"card"`) |

#### `payment.refund`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks.on_payment_confirmed | PaymentRefundHandler |
| `intent_ref` | `string` | hooks.on_payment_confirmed | PaymentRefundHandler |
| `amount_q` | `int` | hooks.on_payment_confirmed | PaymentRefundHandler |
| `reason` | `string` | hooks.on_payment_confirmed | PaymentRefundHandler |

Write-back: `refund_id` (string)

#### `production.late_check`

Heartbeat auto-reagendável de alertas de produção (WP-PE0). Payload **vazio** —
é um singleton por loja, não referencia pedido. Armado por
`ensure_late_check_scheduled()` em qualquer `production_changed` (e pelo seed);
o handler roda `check_late_started_orders()` + `check_forgotten_planned_orders()`
e reenfileira a si mesmo em `production.alerts.late_check_cadence_minutes`
(0 = desligado), zerando `attempts`. Duplicatas colapsam mantendo a mais antiga.

#### `card.create`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | CardCreateHandler |
| `amount_q` | `int` | hooks | CardCreateHandler |

Write-back: `intent_ref` (string)

#### `notification.send` (order notification)

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks, handlers | NotificationSendHandler |
| `template` | `string` | hooks (pipeline `topic:template`), handlers | NotificationSendHandler (default `"generic"`) |
| `origin_channel` | `string` | hooks | NotificationSendHandler (informativo) |
| `reason` | `string` | handlers (cancelamento) | NotificationSendHandler._build_context |
| `amount_q` | `int` | PixGenerateHandler (reminder) | NotificationSendHandler (informativo) |
| `copy_paste` | `string` | PixGenerateHandler (reminder) | Template (não handler) |
| `tracking` | `dict` | FulfillmentUpdateHandler | Template (não handler) |
| `context` | `dict` | CommitService (preorder reminder) | Template (não handler) |

Templates de notificação: `"order_confirmed"`, `"order_cancelled"`, `"order_cancelled_by_customer"`,
`"order_rejected"`, `"order_processing"`, `"order_ready"`, `"order_dispatched"`, `"order_delivered"`,
`"payment_confirmed"`, `"payment_expired"`, `"payment.reminder"`, `"preorder_reminder"`,
`"production_cancelled"`, `"generic"`.

#### `notification.send` (system notification)

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `event` | `string` | stock alerts, _stock_receivers | NotificationSendHandler |
| `context` | `dict` | stock alerts, _stock_receivers | NotificationSendHandler |

Valores de `event`: `"stock.alert.triggered"`, `"system"`.

#### `fiscal.emit_nfce`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | NFCeEmitHandler |
| `items` | `list[dict]` | hooks | NFCeEmitHandler |
| `payment` | `dict` | hooks | NFCeEmitHandler |
| `customer` | `dict` | hooks (opcional) | NFCeEmitHandler |
| `additional_info` | `string` | hooks (opcional) | NFCeEmitHandler |

#### `fiscal.cancel_nfce`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | NFCeCancelHandler |
| `reason` | `string` | hooks | NFCeCancelHandler |

#### `return.process`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | ReturnService | ReturnHandler |
| `items` | `list[dict]` | ReturnService | ReturnHandler |
| `refund_total_q` | `int` | ReturnService | ReturnHandler |
| `return_index` | `int` | ReturnService | ReturnHandler (default 0) |

#### `fulfillment.create`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | FulfillmentCreateHandler |
| `channel_ref` | `string` | hooks | FulfillmentCreateHandler |

#### `fulfillment.update`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | FulfillmentUpdateHandler |
| `fulfillment_id` | `string` | hooks | FulfillmentUpdateHandler |
| `new_status` | `string` | hooks | FulfillmentUpdateHandler |
| `tracking_code` | `string` | hooks (opcional) | FulfillmentUpdateHandler |
| `carrier` | `string` | hooks (opcional) | FulfillmentUpdateHandler |

#### `courier.dispatch`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | `courier.request_dispatch` | CourierDispatchHandler |
| `channel_ref` | `string` | `courier.request_dispatch` | — (auditoria) |
| `actor` | `string` | `courier.request_dispatch` (`lifecycle.on_ready` ou `operator:<nome>`) | CourierDispatchHandler (auditoria no evento) |

Write-back em `Order.data["courier"]` (ver detalhamento). `dedupe_key` =
`courier.dispatch:{order_ref}:{tentativa}`.

#### `courier.sync`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | CourierDispatchHandler / CourierSyncHandler (reagenda) | CourierSyncHandler |

Heartbeat de polling do status da corrida (fallback do webhook Machine).
Auto-reagendável a cada `Shop.defaults.delivery.courier_poll_seconds` (default
60; `0` desliga). Morre em status terminal (F/N/C).

#### `loyalty.earn`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | LoyaltyEarnHandler |

#### `loyalty.revoke`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | `services/loyalty.py` (revoke, via `_on_cancelled`/`_on_returned`) | LoyaltyRevokeHandler |
| `reason` | `string` | idem | LoyaltyRevokeHandler (`cancelled` \| `returned`, só para a descrição da transação) |

Estorna exatamente o que a transação `earn` do pedido creditou (transação
`adjust` negativa com a mesma `reference="order:{ref}"`). Se o earn nunca
creditou, é no-op; se o earn ainda está na fila, re-agenda (transient) até o
earn assentar. `dedupe_key` = `loyalty.revoke:{order_ref}`.

#### `loyalty.restore`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | `services/loyalty.py` (restore, via `_on_cancelled`/`_on_returned`) | LoyaltyRestoreHandler |
| `reason` | `string` | idem | LoyaltyRestoreHandler (`cancelled` \| `returned`, só para a descrição da transação) |

Devolve exatamente o que a transação `redeem` do pedido debitou (transação
`adjust` positiva com `reference="order:{ref}:restore"` — reference própria
para não colidir com a dedupe do `loyalty.revoke`, que grava `adjust` na
reference original). Se o redeem nunca debitou, é no-op; se o redeem ainda
está na fila, re-agenda (transient) até o redeem assentar.
`dedupe_key` = `loyalty.restore:{order_ref}`.

#### `checkout.infer_defaults`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `order_ref` | `string` | hooks | CheckoutInferDefaultsHandler |

#### `accounting.create_payable`

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `reference` | `string` | externo (opcional) | PurchaseToPayableHandler |
| `description` | `string` | externo | PurchaseToPayableHandler |
| `amount_q` | `int` | externo | PurchaseToPayableHandler |
| `due_date` | `string` | externo | PurchaseToPayableHandler |
| `category` | `string` | externo | PurchaseToPayableHandler |
| `supplier_name` | `string` | externo (opcional) | PurchaseToPayableHandler |
| `notes` | `string` | externo (opcional) | PurchaseToPayableHandler |

Write-back: `entry_id` (string)

#### `campaign.occur`

A ocasião de uma campanha agendada. A vassoura (`arm_scheduled_campaigns`, no ciclo de
manutenção) **arma** a directive com `available_at` no minuto exato; quem **dispara** é o
`process_directives --watch` (~2s). É por isso que uma relâmpago das 17h30 sai às 17h30 e
não às 17h34, sem broker nenhum e sem mexer em threshold da [ADR-003](../decisions/adr-003-directives-sem-celery.md).

Dedupe: `campaign:{campaign_id}:{YYYYMMDDTHHMM}` — a chave é da **ocasião**, não da
campanha, então a relâmpago de amanhã também sai.

| Chave | Tipo | Escrito por | Lido por |
|-------|------|-------------|----------|
| `campaign_id` | `int` | campaign_service.arm_scheduled | CampaignOccurrenceHandler |
| `occurrence_key` | `string` | campaign_service.arm_scheduled | CampaignOccurrenceHandler |

⚠️ O `occurrence_key` também vai para `Announcement.occurrence_key`, que tem UNIQUE
**parcial** (só quando não vazio). São dois pares de olhos contra a mesma falha: mensagem
em dobro chega ao cliente e não tem desfazer. Anúncio de evento fica com a chave vazia de
propósito — duas fornadas do mesmo pão são dois anúncios legítimos.

---

## Channel.config

Configuração do canal. Schema formal via `ChannelConfig` dataclass em `shopman/shop/config.py`.

### Cascata de configuração

```
ChannelConfig.defaults() ← Shop.defaults ← Channel.config
```

O método `ChannelConfig.for_channel(channel_or_ref)` faz o merge profundo (deep_merge).
Chave ausente no override = herda. Chave presente (mesmo None) = sobreescreve.

### 1. Confirmation — como o pedido é aceito?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `mode` | `string` | `"immediate"` | `"immediate"` (auto-confirma), `"auto_confirm"` (auto-confirma após timeout), `"auto_cancel"` (cancela após timeout), `"manual"` (aguarda) |
| `timeout_minutes` | `int` | `5` | Timeout para modes auto_confirm/auto_cancel |

Lido por: `hooks._on_order_created`, `ConfirmationTimeoutHandler`, `confirmation.py` helpers, `CheckoutView`, `TrackingView`.

### 2. Payment — como o cliente paga?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `method` | `string \| list[str]` | `"counter"` | `"counter"`, `"pix"`, `"card"`, `"external"`, ou lista |
| `timeout_minutes` | `int` | `15` | Timeout para PIX/card. Card timeout = `timeout_minutes * 2` |

Property: `available_methods` → sempre retorna lista.

Lido por: `hooks._build_directive_payload`, `hooks._maybe_schedule_card_timeout`, `confirmation.py` helpers, `CheckoutView._get_payment_methods`.

### 3. Stock — comportamento de reserva de estoque

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `hold_ttl_minutes` | `int \| None` | `None` | TTL das reservas. None = sem expiração |
| `safety_margin` | `int` | `0` | Margem de segurança (unidades a subtrair do disponível) |
| `planned_hold_ttl_hours` | `int` | `48` | TTL para holds planejados (fermata) |
| `allowed_positions` | `list[str] \| None` | `None` | Posições de estoque aceitas. None = todas vendáveis |
| `allow_untracked` | `bool` | `true` | SKU fora do CATÁLOGO pode entrar em pedido sem reserva (seam de integração/smoke). Canais de CLIENTE declaram `false` — typo de SKU falha limpo no gate de commit (`ValidationError(unknown_sku)`, sem pedido, sem hold). Produto que existe no catálogo mas não é rastreado pelo Stockman segue passando |
| `default_lead_time_hours` | `int` | `0` | Antecedência mínima (horas) para registrar DEMANDA (encomenda sem fornada planejada) quando o produto não declara `Product.metadata.lead_time_hours`. `0` = sem exigência. Lido por `shop/services/lead_time.py` |

Lido por: `StockHoldHandler`, `confirmation.py` helpers, `apps._validate_hold_ttl`.

### 4. Pipeline — o que acontece em cada fase?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `on_commit` | `list[str]` | `[]` | Directives ao criar pedido |
| `on_confirmed` | `list[str]` | `[]` | Directives ao confirmar |
| `on_processing` | `list[str]` | `[]` | Directives ao iniciar preparo |
| `on_ready` | `list[str]` | `[]` | Directives ao ficar pronto |
| `on_dispatched` | `list[str]` | `[]` | Directives ao despachar |
| `on_delivered` | `list[str]` | `[]` | Directives ao entregar |
| `on_completed` | `list[str]` | `[]` | Directives ao completar |
| `on_cancelled` | `list[str]` | `[]` | Directives ao cancelar |
| `on_returned` | `list[str]` | `[]` | Directives ao devolver |
| `on_payment_confirmed` | `list[str]` | `[]` | Directives ao confirmar pagamento |

Notação: `"topic:template"` para notificações com template (ex: `"notification.send:order_confirmed"`).

Lido por: `hooks.on_order_lifecycle`, `hooks._on_order_created`, `hooks.on_payment_confirmed`.

### 5. Notifications — por onde avisamos?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `backend` | `string` | `"manychat"` | Backend primário: `"manychat"`, `"email"`, `"console"`, `"sms"`, `"webhook"`, `"whatsapp"`, `"none"` |
| `fallback_chain` | `list[str]` | `["sms", "email"]` | Cadeia de fallback se primário falhar |
| `routing` | `dict \| None` | `None` | Roteamento por tipo de notificação (reservado) |

Lido por: `NotificationHandler._resolve_backend_chain`, `setup._check_registered_backends`.

### 6. Rules — quais validators/modifiers ativar?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `validators` | `list[str]` | `[]` | Validators ativos: `"business_hours"`, `"min_order"` |
| `modifiers` | `list[str]` | `[]` | Modifiers ativos: `"shop.discount"`, `"shop.employee_discount"`, `"shop.happy_hour"` |
| `checks` | `list[str]` | `[]` | Checks obrigatórios: `"stock"` |

Lido por: `setup.py` (registro), validators, modifiers.

### 7. Lifecycle — como o pedido transita entre status?

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `transitions` | `dict \| None` | `None` | Transições permitidas: `{status: [status, ...]}` |
| `terminal_statuses` | `list[str] \| None` | `None` | Status terminais (não transitam mais) |
| `auto_transitions` | `dict \| None` | `None` | Transições automáticas: `{"on_payment_confirm": "processing"}` |
| `auto_sync_fulfillment` | `bool` | `False` | Sync automático fulfillment → order status |

Lido por: `hooks.on_payment_confirmed`, `FulfillmentUpdateHandler`.

### Chaves fora do ChannelConfig schema

Estas chaves são lidas diretamente de `channel.config` como dict bruto, sem passar pelo `ChannelConfig`:

| Chave | Lido por | Descrição |
|-------|----------|-----------|
| `cutoff_hour` | CheckoutView._get_cutoff_info | Hora de corte para pedidos do dia (default 18) |

### Presets

| Preset | Confirmation | Payment | Stock TTL | Notifications | Validators |
|--------|-------------|---------|-----------|---------------|------------|
| `pos()` | immediate | counter | 5 min | console | business_hours |
| `remote()` | auto_confirm/5min | [pix, card]/15min | 30 min | manychat | business_hours, min_order |
| `whatsapp()` | auto_confirm/5min | [pix, card]/15min | 30 min | whatsapp | business_hours, min_order |
| `marketplace()` | auto_cancel/5min | external | None | none | (vazio) |

---

## Shop.defaults

Configurações padrão da loja — camada intermediária na cascata de configuração de canais.

```
ChannelConfig.defaults() ← Shop.defaults ← Channel.config
```

O schema é idêntico ao `ChannelConfig` (ver seção `Channel.config` acima). Chaves ausentes
em `Shop.defaults` herdam os defaults de código do `ChannelConfig`. Canais que não sobrescrevem
uma chave específica herdam a da loja.

**Campo**: `Shop.defaults` (JSONField, `shopman/shop/models/shop.py`).
**Mergeado por**: `ChannelConfig.for_channel()` via `deep_merge`.

### Exemplo

```json
{
  "confirmation": {"mode": "auto_confirm", "timeout_minutes": 10},
  "stock": {"hold_ttl_minutes": 30, "safety_margin": 2},
  "notifications": {"backend": "manychat", "fallback_chain": ["sms"]},
  "rules": {"minimum_order_q": 0, "delivery_minimum_q": 2500, "free_delivery_above_q": 0}
}
```

### Políticas de pedido/entrega — `Shop.defaults["rules"]`

Valores em centavos (`_q`). **Semântica única: `0`/ausente = regra desligada** (sem
fallback mágico). Fonte única consumida pelo aviso ao vivo (projections) e pelo
gate de commit. Editáveis tipados em Reais no ShopAdmin (`shop/admin/shop.py`).

| Chave | Aplica a | Lido por | Descrição |
|-------|----------|----------|-----------|
| `rules.minimum_order_q` | todo pedido | `build_minimum_order_progress`, `can_checkout` | Mínimo geral para finalizar. Barra de progresso + bloqueio do checkout |
| `rules.delivery_minimum_q` | só entrega | `build_delivery_minimum_progress`, `DeliveryZoneRule` (commit), POS | Mínimo só para entrega (retirada nunca tem). Aviso no passo de entrega + bloqueio do commit |
| `rules.free_delivery_above_q` | só entrega | `build_free_delivery_progress`, `DeliveryFeeModifier` | Taxa de entrega zera no/above deste valor. Reusa a barra como upsell ("faltam X para frete grátis") |

> Convivem no mesmo sub-dict `rules` que o tri-state `validators`/`modifiers`/
> `checks` do `ChannelConfig` — o `_safe_init` filtra estas chaves de política, que
> são lidas direto de `shop.defaults["rules"]` por `shop_rule_q()`.

A taxa de entrega por região segue nas **Zonas de Entrega** (`DeliveryZone`, inline
no admin). O frete grátis global é avaliado por cima da taxa da zona.

### Fidelidade — `Shop.defaults["loyalty"]`

Política do programa de fidelidade, fora do schema do `ChannelConfig` (`_safe_init`
filtra). Source-of-truth tipado em `shopman/shop/loyalty_config.py` (`LoyaltyConfig`,
dataclass-driven), editável no ShopAdmin (fieldset "Fidelidade"). O Core (guestman)
não depende do shop: o orquestrador (`shop/apps.py`) registra resolvers em
`guestman.contrib.loyalty.conf` que injetam estes valores.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `loyalty.points_per_real` | `int` | `LoyaltyEarnHandler` (`shop/handlers/loyalty.py`) | Pontos por R$ 1,00 gasto. `0` desliga o acúmulo. Default `1` |
| `loyalty.stamps_target` | `int` | `LoyaltyService.enroll` (via resolver) | Meta de carimbos de novas contas. Default `10` |
| `loyalty.tiers` | `list[{name, threshold}]` | `LoyaltyService._update_tier` (via resolver) | Limiares de nível por pontos acumulados. `name` ∈ {bronze, silver, gold, platinum}; bronze é o piso (`0`) |

```json
{
  "loyalty": {
    "points_per_real": 1,
    "stamps_target": 10,
    "tiers": [
      {"name": "bronze", "threshold": 0},
      {"name": "silver", "threshold": 500},
      {"name": "gold", "threshold": 2000},
      {"name": "platinum", "threshold": 5000}
    ]
  }
}
```

> Chaves ausentes herdam os defaults do dataclass (idênticos ao comportamento
> hardcoded anterior — zero regressão). Sem `Shop` ou sem bloco `loyalty`, os
> resolvers caem nos defaults do guestman.

### Ponto de venda — `Shop.defaults["pos"]`

Políticas do balcão, fora do schema do `ChannelConfig`.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `pos.discount_approval_threshold_q` | `int` (centavos) | `discount_approval_threshold_q` (`shop/services/pos.py`) | Descontos manuais **acima** deste valor exigem PIN do gerente. `0` **desliga** o teto — nenhum desconto passa a exigir aprovação por valor (a exceção de preço alterado segue exigindo, sempre). **Ausente = herda `SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q`** (deploy). Editado em Reais no ShopAdmin. Dono único: o gate do orquestrador; a projection do backstage lê dele. |

### Alertas de estoque — `Shop.defaults["stock_alerts"]`

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `stock_alerts.cooldown_minutes` | `int` (minutos) | `get_alert_cooldown_minutes` (`stockman/contrib/alerts/conf.py`, via resolver) | Intervalo mínimo entre re-notificações do MESMO alerta de estoque baixo (anti-flood; o cooldown é por `StockAlert` = par sku+posição). **Ausente = herda `STOCKMAN_ALERT_COOLDOWN_MINUTES`** (deploy, default 60) — zero regressão. O Core não depende do shop: o orquestrador injeta um resolver em `stockman.contrib.alerts.conf`. O limiar de cada alerta (`min_quantity`) continua por-SKU no admin de Alertas. |

### Produção — `Shop.defaults["production"]`

Contrato único de configuração de produção, fora do schema do `ChannelConfig`
(produção é da loja, não do canal). Source-of-truth tipado em
`shopman/shop/production_config.py` (`ProductionConfig`, dataclass-driven, mesma
mecânica do `LoyaltyConfig`): defaults sensatos, `deep_merge` com
`Shop.defaults["production"]`, validação que acusa cedo no `load()`.

| Chave | Tipo | Lido por | Descrição |
|-------|------|----------|-----------|
| `production.suggestion.seasons` | `dict[str, list[int]]` | `production.suggest_for()` (`shop/services/production.py`) | Estações → meses (1-12). O mês da data-alvo resolve a estação; a lista filtra o histórico de demanda do `craft.suggest()`. Vazio = sem filtro sazonal. |
| `production.suggestion.high_demand_multiplier` | `string` (Decimal) | `production.suggest_for()` | Multiplicador aplicado em sexta/sábado (ex: `"1.2"`). Ausente = desligado. |
| `production.suggestion.safety_stock_percent` | `string` (Decimal) | `production.suggest_for()` | Margem sobre (demanda média + committed), ex: `"0.20"`. **Ausente = herda `CRAFTSMAN["SAFETY_STOCK_PERCENT"]`** (deploy, default 0.20). |
| `production.alerts.low_yield_threshold` | `string` (Decimal 0-1) | `maybe_create_low_yield_alert` (`shop/handlers/production_alerts.py`) | Yield (finished/started) abaixo disto → `OperatorAlert production_low_yield`. Default `"0.80"`. |
| `production.alerts.default_max_started_minutes` | `int` | `production_alerts`, projections de produção | Janela padrão de WO em andamento antes de "atrasada". `Recipe.meta["max_started_minutes"]` sobrescreve por receita. Default `240`. |
| `production.alerts.late_check_cadence_minutes` | `int` | `ProductionLateCheckHandler` | Cadência do heartbeat `production.late_check`. `0` = desligado. Default `15`. |
| `production.notifications.enabled` | `bool` | `production_alerts._notify_operator` | Liga o par alerta+notificação: além do `OperatorAlert` (sempre criado), o alerta enfileira `notification.send` de sistema (operador, email→console, retry). Default `false` — opt-in contra ruído. |
| `production.notifications.severities` | `list[string]` | `production_alerts._notify_operator` | Severidades que notificam quando `enabled`: subconjunto de `info\|warning\|error\|critical`. Default `["error"]` (só falta de insumo); ampliar para `["error", "warning"]` cobre atraso/yield/esquecimento. |
| `production.order_match` | `string` | `production_order_sync._match_strategy` | Estratégia de vínculo pedido confirmado → WorkOrder: `first_planned` (default) \| `earliest_target` \| `manual`. |

> Editáveis no ShopAdmin (estações, multiplicador e margem no fieldset de
> produção). CLI (`suggest_production`), projections do backstage e matriz do
> Produção resolvem a sugestão pelo MESMO caminho (`suggest_for`) — nunca chame
> `craft.suggest()`/`formula suggest()` direto de uma superfície.

---

## Shop.integrations

Seleção de adapters por tipo. Sobreescreve `settings.py` sem exigir redeploy.

**Campo**: `Shop.integrations` (JSONField, `shopman/shop/models/shop.py`).
**Lido por**: `shopman.shop.adapters.get_adapter()`.

### Schema

```json
{
  "payment": {
    "pix":  "<módulo Python>",
    "card": "<módulo Python>"
  },
  "notification": {
    "default": "<módulo Python>"
  },
  "fiscal": "<módulo Python>"
}
```

Adapters aceitos por tipo:

| Tipo | Chaves | Adapters disponíveis |
|------|--------|----------------------|
| `payment` | `pix`, `card`, `external` | `payment_efi`, `payment_stripe` |
| `notification` | `default`, por backend | `notification_manychat`, `notification_console` |
| `fiscal` | (string) | `fiscal_nfce` |

### Prioridade de resolução

`Shop.integrations` → `settings.SHOPMAN_*_ADAPTERS` → defaults de código.

---

## Customer.metadata

Extensao do cadastro de cliente para contexto operacional e demos. Dados que
alteram autorizacao, cobranca ou identidade devem viver em campos/modelos
proprios, nao aqui.

**Campo**: `Customer.metadata` (JSONField, `shopman/guestman/models/customer.py`).

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `preferences` | `string \| dict` | cadastro/importacao | atendimento, segmentacao | Preferencias gerais do cliente, ex: restricoes alimentares |
| `birthday` | `string` | cadastro/importacao legado | atendimento, segmentacao | Data de aniversario em registros legados. Preferir campo `Customer.birthday` |
| `seed_persona` | `string` | seed | QA/auditoria | Persona operacional deterministica. Ex: `"low_attention"` |
| `qa_notes` | `list[string]` | seed | QA/auditoria | Observacoes de teste para simular baixa atencao, recuperacao e suporte |
| `house_account` | `bool` | **Admin** (checkbox "Conta na casa" no form do cliente, `guestman/contrib/admin_unfold`) | `shop/services/house_account.is_eligible` (porteiro da venda "em conta" no PDV), projection do PDV (`customer lookup.house_account`) | O cliente pode comprar em conta e acertar por período (WP-10 do CASHMAN-PLAN). Desligado por padrão; não se divulga. Ausente = `false` |
| `fiscal_prefs` | `dict` | `shop/services/pos._remember_fiscal_prefs` (quando cliente identificado OPTA na venda) | POS lookup projection (`fiscal_prefs`) → pré-marca o checkout | `{cpf_na_nota: bool, email_receipt: bool}` — o cliente optou uma vez, a próxima venda vem pré-marcada (editável). Só grava opt-IN; desmarcar numa venda não apaga ("hoje não" ≠ "nunca mais"). Esquecer é gesto de cadastro (Admin) |

---

## Product.metadata (chaves do orquestrador)

Contexto de venda/operacao do produto fora do schema estrutural do Offerman
(o proprio Offerman documenta `fiscal`, `allergens`, `dietary_info` etc.).

**Campo**: `Product.metadata` (JSONField, `shopman/offerman/models/product.py`).

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `lead_time_hours` | `int` | seed/admin (Offerman) | `shop/services/lead_time.py` (checkout do storefront + gate de demanda em `shop/services/stock.hold`) | Antecedência mínima (horas) para registrar DEMANDA (encomenda para data sem fornada planejada). Sobrescreve `ChannelConfig.stock.default_lead_time_hours`. Não bloqueia encomenda com Quant planejado da data nem venda imediata do estoque físico de hoje. |

---

## Regras de Governança

1. **Toda nova chave** em qualquer JSONField deve ser adicionada a este documento antes do merge.
2. **CommitService** é o único caminho Session.data → Order.data. A lista de chaves é explícita em `_do_commit()`.
3. **Handlers** escrevem apenas nas chaves documentadas na sua seção.
4. **Nenhum handler lê chave de outro handler** sem contrato documentado aqui.
5. **Nome da chave**: snake_case, descritivo, sem prefixo redundante (ex: `origin_channel`, não `session_origin_channel`).
6. **Tipo**: consistente. Valores monetários sempre `_q` (int centavos). Datas sempre ISO string.
7. **CommitService propaga exatamente estas chaves**: `customer`, `fulfillment_type`, `delivery_address`, `delivery_address_structured`, `delivery_date`, `delivery_time_slot`, `order_notes`, `origin_channel`, `payment`, `delivery_fee_q`. Mais `is_preorder` (computado).
8. **Order.snapshot é imutável**. Nunca editar após o commit. Contém `items`, `data`, `pricing`, `rev`.
9. **Directive.payload varia por topic**. Cada handler documenta as chaves que lê e escreve na sua seção acima.
10. **Channel.config usa ChannelConfig dataclass**. Chaves fora do schema devem ser documentadas na seção "Chaves fora do ChannelConfig schema".

---

## WorkOrder.meta

Contexto operacional de produção mantido fora do core Craftsman.

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `committed_order_refs` | `list[string]` | `shop.handlers.production_order_sync` | Backstage produção/pedidos projections | Pedidos que comprometem quantidade do SKU produzido por esta WorkOrder. Espelho operacional de `Order.data.awaiting_wo_refs`; a métrica de produção é a soma de itens, não a contagem de pedidos. |
| `steps_progress` | `int` | Backstage produção (futuro botão manual) | `build_production_kds` | Override manual do passo atual no KDS de produção, 1-based. |
| ~~`quality`~~ | — | **REMOVIDA (ADR-017, 2026-08-13)** | — | A qualidade da fornada não é mais armazenada: é DERIVADA das linhas de OUTPUT (`WorkOrderItem.quality_grade_ref`, colunas reais, não meta). Consumidores usam `shop.services.quality.derived_quality/output_partition`. Hierarquia = `QualityGrade.rank` (catálogo). A migração `shop/0014` traduziu os dados antigos (pt→en). |
| ~~`batch_ref`/`batch_quantity`/`expiry_date`~~ | — | **REMOVIDAS (ADR-017 §5, 2026-08-13)** | — | O lote sai da LINHA de OUTPUT (`WorkOrderItem.batch_ref`), um `Batch` por linha — a fórmula no meta só admitia um lote por ordem. Validade vive em `Batch.expiry_date`; grupo com desconto congela `Batch.nonconformity_percent`/`_reason`. |
| `formula_basis` | `dict` | `set_planned_quantity` (`shop/services/production.py`) | matriz/auditoria de sugestão | Basis da sugestão aceita (demanda média, committed, margem, `accepted_quantity`). Só quando `source_ref="formula:suggestion"`. |
| `consolidated_work_order_refs` | `list[string]` | `set_planned_quantity` | auditoria | Refs de WOs planned duplicadas consolidadas nesta. |
| `_recipe_snapshot` | `dict` | Core (`CraftPlanning.plan`) | Core (`finish`) | BOM congelada no plan — **gerida pelo Core, nunca editar**. |
| `stock_consumed_at` | `string` (ISO 8601) | `craftsman/contrib/stockman/handlers` (`_handle_finished`), `config/.../seed.py` | `sweep_unrealized_production` | Instante em que a perna de INSUMO do ledger fechou. Ausente numa WO `finished` = o consumo não rodou. O `seed` grava `FINISHED` direto no banco (sem passar pelo handler) e por isso **carimba os dois na mão** — sem o carimbo o sweeper reconsumia a história inteira. |
| `stock_realized_at` | `string` (ISO 8601) | `craftsman/contrib/stockman/handlers` (`_handle_finished`), `config/.../seed.py` | `sweep_unrealized_production` | Instante em que a perna de OUTPUT do ledger fechou (realize + write-off de rendimento). Ausente numa WO `finished` = a fornada não entrou no estoque. |

> **Escrever a perna e carimbar o marcador acontecem sob a MESMA trava**
> (`_leg_lock`, `select_for_update` na WorkOrder), e o carimbo vem ANTES da
> escrita, na mesma transação. Ler o marcador fora da trava é atalho, nunca
> decisão: dois fechamentos simultâneos com a mesma chave de idempotência
> passavam pela janela entre o COMMIT da WorkOrder e o carimbo e creditavam a
> vitrine em dobro.
>
> **Os dois marcadores acima são o guarda do sweeper, não decoração.**
> `_handle_finished` **não é idempotente** — o `realize` credita o `actual`
> cheio, independente do saldo planejado, então re-executar sem consultar o
> marcador credita a vitrine **em dobro**. São dois (e não um) porque a falha
> típica é parcial: o insumo baixa antes do `try` do output, então re-rodar o
> handler inteiro consumiria o insumo duas vezes para consertar a vitrine uma.
> A migração `craftsman/0005` carimbou o histórico como já realizado, para o
> primeiro ciclo do sweeper não reprocessar tudo que existia antes deles.

## Recipe.meta

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `steps` | `list[dict]` | seed/admin de receitas | KDS de produção | Passos do KDS: `[{name: string, target_seconds: int}]`. Fallback: campo legado `Recipe.steps`. |
| `max_started_minutes` | `int` | seed/admin de receitas | alertas/KDS produção | Tempo alvo total para WO em produção antes de atraso. Ausente = `production.alerts.default_max_started_minutes`. |
| `capacity_per_day` | `int` | seed/admin de receitas | dashboard/relatórios | Capacidade diária nominal da receita. |
| `production_lifecycle` | `string` | admin de receitas (contrib Unfold, campo provider-driven) | `dispatch_production` (`shop/production_lifecycle.py`) | Variante de lifecycle do orquestrador: `standard` (default, chave omitida) \| `forecast` \| `subcontract` (ADR-007). O campo só existe porque `CRAFTSMAN["PRODUCTION_LIFECYCLE_PROVIDER"]` aponta para `production_lifecycle_choices()` do orquestrador — pacote standalone não o renderiza. |
| `requires_batch_tracking` | `bool` | admin de receitas (contrib Unfold) | `backstage.services.production` | Cria lote ao concluir a produção. |
| `shelf_life_days` | `int` | admin de receitas (contrib Unfold) | `backstage.services.production` | Validade do lote produzido, em dias. |

## DayClosing.data

Registros antigos podem ser uma lista simples de snapshots. Registros novos usam envelope:

```json
{
  "items": [
    {"sku": "SKU", "qty_reported": 1, "qty_applied": 1, "qty_discrepancy": 0, "qty_remaining": 0, "qty_d1": 0, "qty_loss": 0}
  ],
  "production_summary": {
    "recipe-ref": {"recipe_ref": "recipe-ref", "output_sku": "SKU", "planned": 10, "finished": 9, "loss": 1}
  },
  "reconciliation_errors": [
    {"sku": "SKU", "sold": 12, "available": 10, "deficit": 2}
  ]
}
```

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `items` | `list[dict]` | `services/closing.py::perform_day_closing` | template fechamento | Snapshot por SKU com qty reportada, aplicada, perda. |
| `production_summary` | `dict[str, dict]` | `services/closing.py::_production_summary` | template fechamento, projection | Agregado de WOs do dia por receita: `{recipe_ref: {recipe_ref, output_sku, planned, finished, loss}}`. |
| `pending_production` | `list[dict]` | `services/closing.py::_pending_production_snapshot` | auditoria | WOs ainda abertas (planned/started, `target_date <= data do fechamento`) no momento do fechamento: `{ref, output_sku, recipe_ref, status, quantity, target_date}`. O fechamento acusa, não bloqueia. |
| `cash_shift_summary` | `dict` | `services/closing.py::_cash_shift_summary` | template fechamento, projection, **B.I.** (`projections/bi_cash.py` lê `payment_method_totals` — ADR-021) | Turnos de caixa do dia (fechados/abertos/totais). |
| `reconciliation_errors` | `list[dict]` | `services/closing.py::_reconciliation_errors` | projection (`ReconciliationError.from_dict`) | Discrepâncias detectadas: SKUs vendidos além do que estoque + produção poderiam suprir. Schema: `{sku, sold, available, deficit}` (a projection converte para `ReconciliationError(sku, sold_qty, available_qty, deficit_qty)` na leitura). |
| `financial_reconciliation` | `dict` | `services/financial_reconciliation.py::persist_financial_reconciliation` (comando `reconcile_financial_day`) | auditoria, runbook de pagamento divergente | Resumo do dia (`FinancialReconciliationReport.as_dict()` sem `issues`): `date`, `generated_at`, `order_count`, `intent_count`, `transaction_count`, `order_gross_q`, `captured_q`, `refunded_q`, `chargeback_q`, `net_q`, `by_method`, `by_gateway`, `issue_counts`, **`cash_ledger`** (cruzamento Payman × livro-caixa, WP-7 do CASHMAN-PLAN: `{payman_captured_q, payman_refunded_q, payman_net_q, ledger_sale_q, ledger_cod_settled_q, ledger_refund_q, ledger_net_q, difference_q}`; `difference_q = payman_net_q − ledger_net_q`, zero quando o dinheiro em espécie bate nos dois livros), `day_closing_id`, `persisted`, `alert_created`. |
| `financial_reconciliation_errors` | `list[dict]` | idem | auditoria, runbook | Só as issues `error`/`critical` (`FinancialReconciliationIssue.as_dict()`): `{code, severity, message, order_ref?, intent_ref?, context?}`. Códigos: `day_closing_missing`, `digital_order_missing_intent`, `order_data_intent_not_found`, `intent_amount_mismatch` (soma dos intents liquidados do pedido × total; um intent por MÉTODO na venda mista), `multiple_captured_intents_for_order` (mesmo método duas vezes), `intent_without_order`, `intent_currency_mismatch`, `captured_intent_without_capture_transaction`, `open_intent_has_capture`, `refund_exceeds_capture`, `capture_exceeds_intent_amount`, `paid_order_not_confirmed`, `terminal_order_with_captured_balance`, `fulfilled_digital_order_underpaid`, `terminal_intent_has_capture`, `cash_ledger_mismatch` (`context`: `payman_cash_q`, `ledger_cash_q`, `difference_q`, `order_count`, `orders` — até 10 refs de pedido que divergem). |

---

## payman.PaymentIntent.gateway_data

Contexto do intent no gateway (`packages/payman`, `PaymentIntent.gateway_data`). É o
JSONField que evita coluna nova para dado contextual de pagamento. **O livro continua
sendo `PaymentTransaction`** — nada aqui é fonte de valor financeiro; o que este dict
guarda é o "de onde veio" e o "o que está em curso".

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `checkout_url`, `checkout_session_id` | `str` | `adapters/payment_stripe.py::create_intent` | storefront (redirect do cartão) | URL hospedada do Stripe Checkout e id da sessão. O `gateway_id` promove de `cs_…` para `pi_…` quando `checkout.session.completed` chega. |
| `location`, `client_secret` | `str` | `adapters/payment_efi.py::create_intent` | storefront (QR do Pix) | Endereço do QR e payload copia-e-cola da cobrança Efí. |
| `e2e_id` | `str` | `services/pix_confirmation.py::confirm_pix` | conciliação, suporte | Identificador ponta-a-ponta do Pix que pagou. |
| `efi_status` | `str` | `adapters/payment_efi.py::capture` | suporte | Último status bruto da cobrança na Efí (ex.: `CONCLUIDA`). |
| `collection` | `str` | `services/payment.py`, `services/operator_orders.py` | reconciliação financeira, livro-caixa | `terminal` (liquidado no balcão, ADR-022) ou `on_delivery` (COD, acertado na entrega). Ausente na loja online. |
| `terminal_ref` | `str` | idem | reconciliação, PDV | Terminal onde o dinheiro foi recebido. |
| `asserted_at_terminal` | `bool` | `PaymentService.settle` (via `services/payment.py::settle_terminal_tenders`) | reconciliação, estorno | `True` quando um método COM gateway (pix, cartão) foi **atestado por gente** no balcão — QR estático, maquininha avulsa numa venda mista. Distingue "capturado pelo gateway" de "afirmado pelo operador", e é o que faz o estorno saber que não há gateway para chamar. |
| `settled_with`, `settled_by`, `customer_ref` | `str` | `services/house_account.py` | acerto de conta, livro-caixa | Como e por quem a conta em aberto foi acertada, e de qual cliente ela é. |
| `smoke` | `bool` | `services/gateway_smoke.py` | smoke de gateway | Intent de teste de fumaça; nunca é venda. |
| **`disputes`** | `dict[str, dict]` | `adapters/payment_stripe.py::handle_dispute_event` | operador (alerta `payment_disputed`), suporte | **Disputas em curso e encerradas, por id do gateway** (`du_…`). Só o desfecho `lost` vira `PaymentTransaction(CHARGEBACK)`; o resto é risco, não livro. Cada valor: `{status, amount_q, currency, reason, charge_id, evidence_due_by, funds_withdrawn, funds_reinstated, last_event, updated_at}`. `status` é o do Stripe (`warning_*`, `needs_response`, `under_review`, `won`, `lost`, `prevented`) e é **grudento quando terminal** — evento fora de ordem não reabre disputa encerrada. Pix não popula: a Efí não publica evento de MED (ver docstring de `shopman/shop/webhooks/efi.py`). |

---

## cashman.Terminal.metadata

Configuração por terminal do PDV (`packages/cashman`, `Terminal.metadata`). Escrita pelo
Admin do backstage (`shopman/backstage/admin/terminal.py`, que registra por cima do contrib do
pacote porque hardware é da superfície) e pelo `seed`; lida por
`shopman/backstage/services/pos_terminal.py::runtime_profile`, que devolve o
`TerminalRuntimeProfile` consumido pela projection do POS e pelo badge de saúde no Admin, e por
`pos_hardware.py::CashDrawerConfig.from_terminal`.

| Chave | Tipo | Escrito por | Lido por | Descrição |
|-------|------|-------------|----------|-----------|
| `default_fulfillment_type` | `str` | Admin | projection POS | `pickup` (default) ou `delivery`. Qualquer outro valor cai em `pickup`. |
| `favorite_collection_refs` | `list[str]` | Admin | projection POS | Até 9 coleções fixadas na tela de venda. Aceita o alias legado `favorite_collections`. |
| `auto_lock_seconds` | `int` | Admin | projection POS | Inatividade até o cadeado do operador. Default 60. |
| `default_float_q` | `int` | Admin | projection POS (`cash_runtime.default_float_q`) | Fundo de troco sugerido na abertura guiada do caixa, em centavos. Escolha FIXA do gestor; 0/ausente = sem sugestão. ⚠️ Nunca derivado do contado/esperado de turnos (regime de contagem cega). |
| `hardware` | `dict` | Admin, `seed` | `runtime_profile` | Periféricos declarados. Ver abaixo. |
| `station` | `dict` | Admin | `backstage/station_trust.py` | Que ESPÉCIE de estação é este dispositivo. Ver abaixo. |

⚠️ **Nada disto é dado de seed, e o `seed --flush` não custa nenhum.** O flush precisa apagar
`Terminal` (o turno pendura ali por FK), então ele fotografa a config por `ref` e
`_restore_terminal_config` devolve depois que a fase dinâmica recria o terminal — o mesmo
idioma que `_relink_bi_aliases` usa para a curadoria de de-paras. A loja vence em tudo que
declarou; o `seed` só preenche lacuna, e no `hardware` isso é por periférico (a impressora
cadastrada não é sobrescrita, mas a gaveta do seed entra se não havia nenhuma). Terminal que
o seed não recria — qualquer `ref` fora do `pdv-main` do `Terminal.default()` — volta pela
mesma via.

### station — atendida ou autônoma

Lido por `shopman/backstage/station_trust.py` (`station_mode`, `station_operator`) e, através
dele, pelo gate de permissão do backstage. Ausente = **atendida**.

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `mode` | `str` | `attended` (default) ou `autonomous`. Qualquer outro valor cai em `attended`. |
| `operator` | `str` | Só para `autonomous`: o `username` da conta em cujo nome o dispositivo age. |

**Atendida** é o balcão: tem gente na frente, e não faz nada sem PIN ou crachá.
**Autônoma** é o totem: não há quem digite PIN, então ele age em nome próprio, com uma conta
que é dele. O que essa conta pode fazer são as permissões que a loja lhe conceder — não há
conjunto embutido no código, e o gate a trata como trata qualquer operador.

⚠️ **Tudo aqui falha fechado, e por motivo vivido.** Modo escrito errado, conta ausente,
conta inativa ou fora da casa → o dispositivo volta a ser uma estação atendida, pedindo PIN.
E conta **superusuária é recusada com log de erro**: `is_superuser` curto-circuita `has_perm`,
então um totem assim ignoraria qualquer conjunto mínimo — que é literalmente o buraco que a
D1 Parte B fechou, só que com um dispositivo no lugar do `admin`.

### hardware — periféricos declarados

Um dict por periférico: `printer`, `cash_drawer`, `scanner`, `payment_terminal`, `customer_display`.

**Ausência não é defeito.** Periférico não declarado vale `absent` ("não instalado"), não `warning` —
um balcão sem display do cliente está completo do jeito que a loja montou. Alerta que nunca apaga é
alerta que ninguém lê.

| Chave | Tipo | Aplica a | Descrição |
|-------|------|----------|-----------|
| `enabled` | `bool` | todos | `false` → `absent` ("desligado"). Ausente = ligado. |
| `adapter` | `str` | todos | Nome do adapter. Presente → `ready`; declarado sem adapter → `warning`. |
| `model` | `str` | todos | Informativo (ex.: `epson-tm-t20`). Não afeta saúde. |
| `roll_width_mm` | `int` | `printer` | Largura do rolo em mm (40–120). É o que a loja sabe: o papel que ela compra. Vira `--pos-roll-width` no print CSS do PDV via projection. Ausente → o default do CSS (80mm) manda. |
| `print_width_mm` | `int` | `printer` | Largura que o cabeçote alcança, em mm. **Só é necessária para rolo fora dos dois padrões** (80mm→72mm, 58mm→48mm), porque a área imprimível não é proporcional à largura do papel e chutar imprime fora do alcance. |

⚠️ **Declaração inválida não cai calada para o default.** Rolo fora da faixa, rolo não padrão sem
`print_width_mm`, ou `print_width_mm >= roll_width_mm` viram `warning` na saúde do terminal com o
motivo. Config ignorada em silêncio é pior que config ausente: a loja acha que configurou.

A margem é derivada, nunca declarada: `ceil((roll_width_mm - print_width_mm) / 2)`. Um rolo de 80mm
dá 4mm por lado; um de 58mm dá **5mm**, não 4 — daí ela não ser um segundo botão para alguém errar.

---

## cashman.Entry.payload

O livro-caixa do turno (`packages/cashman`, ADR-022) é **append-only**: uma
linha por acontecimento na gaveta, com `amount_q` **assinado** (efeito no
saldo; zero quando não mexe em dinheiro), `kind`, `operator`, `approved_by`
(segunda assinatura), `order_ref`, `payment_ref` (intent do `payman`),
`parent` (o lançamento que este responde/corrige), `reason`, e este `payload`
com o específico de cada tipo. Esperado, contado e diferença **não têm
coluna**: são `Σ` do livro (`services.expected_before_count/counted/difference`).

⚠️ O valor de venda, sangria e suprimento é o próprio `amount_q`; o payload
**não** repete valor. Guarda de imutabilidade igual à do `stockman.Move`
(`update()`/`delete()` levantam); imutabilidade real no banco não é prometida.

⚠️ **Um pedido entra uma vez por turno, por tipo.** `UniqueConstraint` parcial em
`(shift, order_ref)` para `sale` e para `cod_settled` (`order_ref` vazio fica de
fora: não há pedido a que amarrar). Dois submits do mesmo fechamento — retry de
rede do PDV — dobrariam o esperado do turno, e um `exists()` antes do insert é
TOCTOU. Quem chama recebe `CashError("DUPLICATE_ENTRY")`, não `IntegrityError`.

| `kind` | `amount_q` | `parent` | payload | Escrito por |
|--------|-----------|----------|---------|-------------|
| `float_in` | > 0 | — | — | `services.open_shift` |
| `sale` | ≥ 0 (efeito em dinheiro; 0 para pix/cartão/external e para entrega paga na porta) | — | `{method, collection, intents: {method: intent_ref}, received_q?, change_q?}` | `shop/services/pos.py::_settle_pos_sale` (uma linha por venda; `payment_ref` = intent do dinheiro, ou o único intent) |
| `cod_settled` | > 0 | — | `{settled_by}` | `shop/services/operator_orders.py::settle_delivery_cash` (turno de quem RECEBEU; `payment_ref` = intent cash com `gateway_data.collection = on_delivery`) |
| `account_settled` | > 0 | — | `{customer_ref, settled_by}` | `shop/services/house_account.py::settle_account` em DINHEIRO: uma linha por intent `account` capturado (`order_ref` + `payment_ref`), no turno de quem recebeu, na mesma transação da captura. Acerto por pix/cartão/external não mexe na gaveta (fica só no Payman, `gateway_data.settled_with`) |
| `courier_out` | < 0 | — | `{change_for_q, suggested_q, dispatched_by}` | `shop/services/operator_orders.py::advance_order` no despacho da entrega em dinheiro: o troco que o entregador leva da gaveta, no turno de quem despacha (sem segunda assinatura: é rotina do despacho). Obrigatório dizer o valor (zero vale) quando o pedido pede troco; sem turno aberto não leva. Não é pagamento: fica fora do cruzamento Payman × livro |
| `courier_in` | ≥ 0 | `courier_out` (só se do mesmo turno; senão `order_ref` + `payload.courier_out_id` ligam) | `{courier_out_id, settled_by}` | `settle_delivery_cash`: o troco que VOLTOU com o entregador, na mesma transação do `cod_settled`; obrigatório quando saiu troco (zero = usou tudo). `courier_out` sem `courier_in` é o alerta `courier_change_unsettled` da reconciliação |
| `refund` | < 0 | `sale` original (só se do mesmo turno; senão `order_ref` liga) | `{intents_refunded}` (motivo em `reason`) | `shop/services/payment.py::refund_cash`: o gesto físico de devolver, com turno aberto de quem devolve, gravando Payman (`REFUND` nos intents cash) e esta linha na MESMA transação. Chamado pelo cancel do PDV dentro da janela (cliente na frente) e por `POST pos/cash/refund/<order_ref>/` (PIN de gerente) para vendas canceladas pelo gestor. **Cancelar não é devolver**: o estorno automático do cancel (`payment.refund`) NÃO toca em dinheiro; a pendência é derivada (`payment.pending_cash_refunds`: pedido cancelado/devolvido × saldo capturado do intent cash), nunca tabela |
| `cash_in` | > 0 | — | — (motivo em `reason`) | suprimento: `backstage/services/pos.py::register_cash_movement` |
| `cash_out` | < 0 (exige `approved_by`) | — | — (motivo em `reason`) | sangria: idem (PIN de gerente, `cashman.adjust_shift`) |
| `count` | contado − esperado | — | `{counted_q, notes}` | `services.close_shift`. Quem contou é `Entry.operator`. ⚠️ `supervisory` foi ESCRITO até 21/08/2026 e ainda aparece em lançamentos antigos (o livro é imutável); parou de ser escrito quando a custódia passou a ser da gaveta — turno sem dono não tem substituto, e a gerente fechar o caixa que outra pessoa abriu virou o caso normal |
| `count_correction` | ± (exige `approved_by`) | `count` | — (motivo em `reason`) | `services.correct_count` |
| `drawer_open` | 0 | — | — (motivo em `reason`) | abertura sem venda: `backstage/services/pos.py::register_drawer_opening` |
| `drawer_unlock` | 0 (exige `approved_by`) | — | `{drawer_raw}` (o byte que o sensor devolveu, ex. `0x12`) | destrave da trava da gaveta: `backstage/services/pos.py::unlock_drawer` (`POST pos/cash/drawer-unlock/`, PIN de gerente). A trava é do PDV (`useDrawerLock`): recusa INICIAR a próxima venda quando o agente do balcão diz `known: true, open: true`; estado desconhecido nunca trava; sem carência; cada destrave vale UMA venda |
| `change_requested` | 0 | — | `{amount_q, denominations: [int], note}` | pedido de troco: `backstage/services/pos.py::request_change`. `amount_q` inteiro > 0 e `denominations` lista de centavos positivos são exigidos pelo próprio `record` (`CashError("INVALID_PAYLOAD")`); QUAIS valores valem é da superfície (ver abaixo) |
| `change_served` | 0 (exige `approved_by`) | `change_requested` | — | `serve_change_request` (PIN de gerente, `cashman.adjust_shift`) |
| `change_cancelled` | 0 | `change_requested` | — | `cancel_change_request` |
| `receipt_result` | 0 | `cash_out`/`cash_in` | `{status: printed\|failed\|skipped, detail}` | comprovante: `record_receipt_result` (só o navegador do balcão sabe se imprimiu; a conferência no Admin lê o ÚLTIMO filho). A lista de status é fonte única em `cashman.Entry.RECEIPT_STATUSES`, exigida pelo `record`; o backstage valida antes só para a mensagem |
| `note` | 0 | — | `{text}` | anotação gerencial em turno fechado |

**Linhas nascidas do backfill** (`backstage/0030_cashman_backfill_and_cut`, WP-5 do CASHMAN-PLAN;
o caixa legado `CashShift`/`CashMovement`/`POSTerminal` entrou no livro uma vez e sumiu): levam
`payload.legacy = true` (`sale`, `cod_settled`, `drawer_open`) ou chaves `legacy_*`:
`sale.payload.source` (`method`/`tenders`/`cash_received`; `intents` vazio, `payment_ref` vazio),
`cod_settled.payload.settled_by`, `cash_out`/`cash_in` com `{legacy_movement_id, created_by, approved_by}`
(nomes como o legado guardava; `approved_by` FK só quando o usuário ainda existe),
`change_requested` com `{legacy_ref, legacy_kind}` (denominações vazias: o legado não tinha),
`count.payload.legacy = {shift_id, expected_q, difference_q, reproduced_expected_q, booked_q, divergent}`
(o `count` é `contado − Σ do livro`; `divergent` quando o algoritmo copiado do `close()` não reproduz o
`expected_q` gravado, tipicamente pedido cancelado depois do fechamento) e
`note.payload = {legacy_shift_id, legacy_status: "open", balance_q}` para turno legado que ainda
estava aberto no corte (fechado sem contagem).

⚠️ As linhas do backfill nascem de `Entry.objects.create` dentro da migração, não do
`services.record`, e por isso não passam pela validação de payload acima (o
`change_requested` legado, por exemplo, não tem `amount_q`). É de propósito: a guarda
existe para o que se escreve de hoje em diante; o passado entrou como estava.

O estado do pedido de troco é **dobrado** do livro (`services.change_requests`):
`pending` → `served`/`cancelled` pela primeira resolução com `parent` apontando
para o pedido; só `pending` chega à tela do PDV (`cash_runtime.pending_change_requests`,
cujo `ref` é o `id` da linha `change_requested` — é por ele que a tela atende e cancela).

### `change_requested.denominations`

As cédulas e moedas pedidas, **em centavos, do maior para o menor**. Lista vazia
é um pedido completo — "me traz R$ 100" basta, e o gerente resolve com o que
houver no cofre; a lista só refina ("R$ 100 em notas de 5 e moedas de 0,50").

Os valores aceitos são a lista canônica em
`backstage/services/pos.py::CHANGE_DENOMINATIONS` — `2000, 1000, 500, 200`
(cédula) e `100, 50, 25, 10, 5` (moeda). Um valor fora dela é recusado no
service: um pedido de R$ 0,03 não é um pedido, é um dedo errado, e viajaria
calado até o balcão. R$ 50, R$ 100 e R$ 200 existem e **não** estão na lista —
ninguém pede troco em nota grande, é o oposto do problema.

⚠️ A tela recebe a lista pela projection (`capabilities.cash_management.change_denominations`)
em vez de repetir os números em TypeScript. Duas listas viram uma divergência no
dia em que uma moeda sair de circulação, e o pedido passaria a falar de um
dinheiro que não existe.

⚠️ **A troca é NET ZERO.** Saem R$ 50, entram 5×R$ 10 — o total da gaveta não muda.
Atender um pedido tem `amount_q = 0` por construção (CheckConstraint do pacote). Lançar
isso com valor faria o esperado cair por um dinheiro que nunca saiu, e o turno fecharia
com falta fantasma (foi o defeito desfeito no PR #178).

## HistoricalSale.metadata

O que o export externo traz e nenhuma coluna de `HistoricalSale` guarda
(BI-DATA-FOUNDATION-PLAN, P0). Escrito **só** pelo importador da fonte
(`shopman/backstage/bi/ingest/yooga.py::SaleRow.metadata`); a reimportação de um
export posterior **completa chaves ausentes e nunca sobrescreve** as presentes.
Chave ausente = o export não trouxe; nunca se grava vazio.

| Chave | Tipo | Fonte (coluna) | Lido por | Descrição |
|-------|------|----------------|----------|-----------|
| `nfce_id` | `int` | Yooga `nfce_id` | ninguém ainda (fonte NFC-e futura, P5) | Id da NFC-e autorizada no sistema antigo. Só quando ≠ 0. |
| `phone_hash` | `str` (sha256 hex) | Yooga `telefone` | join futuro com `guestman` (perfis) | Hash do E.164 obtido por `shopman.utils.phone.normalize_phone` — o mesmo normalizador do guestman, para o join bater. ⚠️ Pseudonimização, não anonimato: o espaço de números é pequeno; protege da leitura casual, não de força bruta. **Nunca o número em claro.** |
| `phone_last4` | `str` | Yooga `telefone` | conferência humana | Últimos 4 dígitos do E.164. |
| `neighborhood` | `str` | Yooga `bairro` | B.I. (entregas por bairro; futuro) | Texto cru. |
| `address` | `str` | Yooga `endereco` | B.I. (geocodificação; futuro) | Texto cru, até 500 caracteres. |
| `payment_fee_q` | `int` (centavos) | Yooga `taxa_pagamento` | B.I. ("taxa de cartão por mês", catálogo §4) | Só quando ≠ 0. |
| `note` | `str` | Yooga `observacao` | auditoria | Observação da venda, até 500 caracteres. |

A proveniência da linha (arquivo, hash, quando, quantas) não mora aqui: mora em
`HistoricalSale.batch` → `ImportBatch`.


## BIAlertRule.last_reading

O que a última avaliação de um alarme do B.I. viu (`shopman/backstage/bi/alerts.py::Reading`).
Sobrescrito a cada ciclo do `evaluate_bi_alerts`; o disparo propriamente dito é `BIAlertEvent`.

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `value` | `float \| null` | O medido (dias desde o último lote; faturamento de ontem em centavos). `null` = a regra não opinou. |
| `baseline` | `float \| null` | O esperado (cadência em dias; média do mesmo dia da semana em centavos). |
| `fired` | `bool` | Passou da régua nesta avaliação (independe do cooldown). |
| `message` | `str` | A frase que foi (ou seria) para o operador, em pt-BR. |


## BIScenarioReport.inputs / .scenarios

`inputs` é o que a IA viu numa rodada (`shopman/backstage/bi/scenarios.py::gather_inputs`): só
agregados da camada de leitura, com unidade no nome (`_q` = centavos), e o `inputs_hash` (sha256
do JSON ordenado) para reproduzir a pergunta. Chaves por foco: `sales` → `totals`,
`previous_period`, `days[]`, `by_channel[]`, `top_products[]`, `orders_by_weekday_mon_first`,
`orders_by_hour`, `next_week_forecast`; `production` → `days[]`, `oven_time_by_recipe[]`,
`soldout_days_by_sku`, `leftover_by_sku`, `unavailable_hours_by_sku`. **Nunca** pedido, cliente
ou apuração de caixa.

`scenarios` é a resposta validada (`ScenarioPayload`): `[{title, proposal, basis[], unknowns[]}]`.
Resposta fora do contrato não entra aqui: o relatório nasce `failed` com `error` e `raw_text`.
