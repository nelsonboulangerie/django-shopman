# ENCOMENDAS-PDV-PLAN — a seção "Encomendas" do PDV

> **Origem:** pedido do dono, 26/09/2026, na conversa sobre a área de Sessões do PDV
> ("deveria se chamar Encomendas, para ficar como a opção de modalidade do pedido no
> PDV […] precisa ser muito bem pensada/projetada"). Desenho aprovado na mesma
> conversa, com a grade semanal e com reagendar e editar **dentro** do escopo.
>
> **Princípio (Core é sagrado):** quase tudo o que a seção precisa já existe, espalhado
> entre Gestor, lifecycle e Payman. O trabalho é **compor e expor no balcão**, não criar
> fluxo paralelo. Onde o sistema não tem a peça (reagendar, editar pedido de canal
> próprio), ela nasce como **serviço do orquestrador** (`shopman/shop/services/`),
> reaproveitando os primitivos listados abaixo — nunca como atalho na superfície.

## As decisões que já estão tomadas (não reabrir)

1. **O nome é "Encomendas"**, o mesmo do seletor de modalidade do PDV
   (`PosTabHeader`: *Balcão | Encomendas*).
2. **Encomenda = todo pedido com recebimento** — retirada ou entrega — **de qualquer
   canal** (PDV, loja online, iFood), **hoje ou depois**. É o corte do PDV (Encomendas
   aceita "Hoje") e é o que o painel de parede quer ver.
   ⚠️ Diverge de "encomenda" no lifecycle e no Gestor (*Agendados*), onde é só data
   futura. A seção diz o seu corte na tela; o lifecycle não muda.
3. **O PDV recebe o saldo na retirada** — o cliente e a gaveta estão no balcão. O dinheiro
   entra no turno do terminal.
4. **Reagendar e editar entram.**
5. **Grade semanal** é parte da seção.
6. A tela "Fichas de pedido" **deixa de existir como item da barra lateral** e vira o card
   **Via Pedido** da seção (a palavra do dono para o papel — ver
   `backstage/services/order_documents.py`).

## A seção, card a card (antesala do PDV, `pages/session/index.vue`)

| Card | Pergunta do balcão | Abre |
|---|---|---|
| **Cliente veio buscar** | "Vim buscar a encomenda da Ana" | busca por nome, telefone ou número → a encomenda → **receber o saldo e entregar** num gesto |
| **Hoje** · selo com a contagem | "O que sai hoje?" | lista do dia por janela, com situação (a pagar · pago · pronto) |
| **Semana** · selo com a contagem | "Quanto temos para sábado?" | **grade semanal** (7 colunas, uma por dia, encomendas por janela) com totais do dia |
| **Via Pedido – painel** | "Imprimir a semana para o painel" | a tela de lote atual, renomeada e corrigida |

O detalhe de uma encomenda (aberto de qualquer card) oferece, conforme o estado e a
permissão: **Receber e entregar**, **Reagendar**, **Editar**, **Cancelar**, **Imprimir Via
Pedido**.

## O que existe, e onde (levantamento de 26/09/2026)

| Capacidade | Existe? | Onde | O que falta |
|---|---|---|---|
| Listar/buscar | parcial | `backstage/projections/order_queue.build_two_zone_queue` (grupo *Agendados*, cards ricos, itens efetivos sem N+1) · `order_ticket.orders_for_period` | projeção do PDV com busca, hoje+futuro e **saldo** (`payment.captured_balance_q` × `order_composition.effective_total_q`) |
| Receber na retirada (dinheiro/cartão) | sim | `operator_orders.settle_delivery_cash` · `backstage/services/orders.py` | endpoint do PDV com o turno do terminal; ⚠️ o serviço compara com `order.total_q` (selado) — trocar por `effective_total_q` |
| Receber Pix/link pendente no balcão | não | — | converter a cobrança pendente em pagamento do terminal (Payman `settle`), sem fluxo paralelo |
| Entregar | sim | `advance_order` READY→COMPLETED + `payment_gate` | expor |
| Cancelar fora da janela de 5 min | sim | `operator_orders.cancel_order` + `operator_cancel_policy` + PIN | expor; Caixa não cancela pronto/concluído (é do Gerente) |
| Devolver dinheiro | sim | `payment.pending_cash_refunds` · `refund_cash` | já está na antesala (*Precisa de você*) |
| **Reagendar** | **não** | peças: `lifecycle._schedule_preorder_activation`, `stock.hold/release`, `production_order_sync`, validadores de data | serviço `reschedule` (WP-E5) |
| **Editar itens** | parcial (só iFood) | `order_composition.record` + `stock.reconcile_to_items` + `kds.reconcile_to_lines` (`ifood_events._apply_patch`) | generalizar para fonte `pos:edit` (WP-E6) |
| Editar observação do cliente / recebimento | não | `save_kitchen_note` só cobre a nota do operador | WP-E6 |

## Work packages

Uma frente = um branch = uma PR. A ordem é de dependência.

### WP-E1 — Leitura: a projeção das encomendas + API  *(sem decisão pendente)*
- Projeção em `backstage/projections/` sobre a base do `order_queue` (não duplicar a
  montagem do card): intervalo por **data combinada**, busca (ref, nome, telefone,
  `display_id` do iFood), saldo, situação, canal, recebimento, janela.
- Exclui venda de Balcão (a regra de `build_two_zone_queue`), cancelados e devolvidos.
- API `GET /api/v1/backstage/pos/preorders/` (`cashman.operate_pos` + `shop.manage_orders`).
- **Corrige o lote da Via Pedido**: `order_ticket.orders_for_period` passa a excluir venda
  de Balcão (hoje entra, por não ter `delivery_date`).
- `closing._upcoming_preorders` passa a ler `effective_total_q` e a dizer o que conta
  ("Vendidas hoje" não confere com a consulta).

### WP-E2 — PDV: a seção e as telas  *(sem decisão pendente; depende de E1)*
- Seção **Encomendas** na antesala com os quatro cards (`PosSessionTile`), visível com ou
  sem caixa aberto, só para quem tem `shop.manage_orders`.
- Páginas `pages/preorders/` (URL em inglês — convenção das superfícies de operador):
  busca, dia, **grade semanal**, detalhe. A tela de lote vira `pages/preorders/panel.vue`
  (Via Pedido – painel); `/tickets` responde 301 (bookmark de kiosk).
- "Fichas de pedido" sai da barra lateral (`PosFunctionRail`).
- Vocabulário: "Via Pedido", nunca "ficha"/"filipeta" na tela.

### WP-E3 — Receber e entregar no balcão  *(depende de E1/E2)*
- Endpoint do PDV que reusa `settle_delivery_cash` com o turno do terminal (dinheiro/cartão)
  e depois `advance_order` → COMPLETED, numa transação.
- `settle_delivery_cash`, `has_sufficient_captured_payment` e o `closing` passam a ler o
  total **efetivo** (pré-requisito de E6; corrige desde já pedido do iFood ajustado).
- Pix/link pendente recebido no balcão: converter a cobrança em pagamento do terminal pelo
  Payman — **sem** segunda cobrança viva (cancelar o link/intent pendente antes).

### WP-E4 — Cancelar pelo PDV  *(depende de E2)*
- Expor `operator_orders.cancel_order` com a política e o PIN que já existem; devolução em
  dinheiro cai no *Precisa de você* como hoje.

### WP-E5 — Reagendar  *(serviço novo no orquestrador)*
Serviço `shopman/shop/services/reschedule.py` — `reschedule(order, *, date, slot, actor)`,
sob lock do pedido, transacional:
1. validar com as regras que já existem (`pos_sales_mode.validate_sales_mode`,
   `pos._validate_schedule`, `_max_preorder_days`, loja fechada/antecedência de
   `storefront/intents/checkout.py`);
2. reescrever `delivery_date`/`delivery_time_slot` e registrar a mudança (chave nova em
   `docs/reference/data-schemas.md` **antes** de usar);
3. **mover** a Directive `preorder.activate:{ref}` viva (editar `available_at`, padrão de
   `lifecycle.py` ~1057) — nunca criar outra; data nova = hoje ⇒ ativar agora;
4. achar o `preorder_reminder` pendente pelo `payload.order_ref` e cancelar/recriar (o
   `context` guarda a data congelada);
5. soltar e refazer os holds (`stock.release` + `stock.hold` com a data nova) — sem saldo na
   data nova ⇒ recusa com o motivo, nada muda;
6. religar a produção (`production_order_sync`: desfazer o vínculo da data antiga,
   `reconcile_production_order_links`);
7. avisar o cliente (conferir se há template; senão, WP de template);
8. de passagem: `activate_preorder` antecipado só loga e o comentário promete reagendar
   (`lifecycle.py` ~970) — a promessa vira código ou sai.

### WP-E6 — Editar  *(decisões do dono pendentes — ver abaixo)*
- Generalizar o `_apply_patch` do iFood para uma fonte `pos:edit`: lista final de itens
  (nunca delta) em `order_composition.record`, `stock.reconcile_to_items`,
  `kds.reconcile_to_lines`, preço do catálogo, aprovação conforme a política.
- Observação do cliente (`order_notes`) e forma de recebimento (retirada ↔ entrega,
  recalculando a taxa como ajuste).

## Perguntas abertas ao dono (bloqueiam só o WP-E6)

1. **Encomenda paga cuja NFC-e já foi autorizada** (o PDV emite no fechamento quando pago):
   editar itens exige cancelar a nota e emitir outra. Permitir com esse custo, ou bloquear a
   edição e oferecer "cancelar e refazer a encomenda"?
2. **Diferença de valor numa encomenda já paga:** a mais, recebe no balcão na retirada
   (vira saldo); a menos, devolve como? (dinheiro na gaveta · estorno no meio original)

## Fora de escopo, registrado

- Capacidade por janela de retirada (`pickup_slots` não tem) — só se o negócio pedir.
- Sinal / pagamento parcial — não existe no Payman; decisão de produto própria.
- Edição de pedido no Gestor.
