# WP-DATA-E-PROMESSA: data, horário, reserva e promessa, canal por canal

> Documento de mapa, não de conserto. Nenhuma linha de código de produção mudou.
> Levantado em 01/10/2026 sobre `origin/main` (`bf415ad98`). Toda afirmação traz
> `caminho:linha` lido nesta data; o que não foi conferido diz **NÃO VERIFICADO**.
> Configuração de canal citada é a do `seed` (`config/management/commands/seed.py`);
> o que está gravado no banco vivo do alpha **NÃO VERIFICADO**.
> Decisões já tomadas e não reabertas aqui: D16 (#1329, "1 pedido = 1 data" na loja),
> D17 e D18 em `docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md`.

## 1. Resumo em dez linhas

1. **Veredito sobre a premissa "uma data alvo por pedido, ponto": CONFIRMADA COM RESSALVA.**
2. Prova a favor: o pedido tem UM campo de data, `data["delivery_date"]`, lido por um único leitor (`shopman/shop/services/order_helpers.py:236-246`); item de pedido não tem data (a linha do PDV só copia `sku, name, qty, unit_price_q, notes, line_id, list_price_q, discount, weighed`, `shopman/shop/services/pos_intent.py:345-385`; nenhum `DateField` de negócio em `packages/orderman/shopman/orderman/models/order.py`).
3. Prova a favor: a loja recusa o item de outra data desde o #1329 (`shopman/shop/services/cart.py:81-101`), e a comanda do PDV tem uma data por sessão (`shopman/shop/services/pos.py:3866-3878`, D17).
4. **A ressalva:** a data mora em DOIS lugares, `order.data.delivery_date` e `Hold.target_date` de cada reserva, e nada obriga os dois a concordarem. Na loja, o cliente pode montar a sacola na fornada de amanhã e escolher "Hoje" no checkout: o commit adota as reservas de amanhã num pedido de hoje (`shopman/shop/services/stock.py:115-116`, `:872-884` sem filtro de data). O acompanhamento então diz "fornada prevista para hoje" no texto principal e "Fornada prevista para amanhã" no painel (seção 6, L1).
5. Fora isso, há três frestas menores por onde uma segunda data entra na sacola da loja (primeira linha sem data, reserva vencida, iFood pelo webhook antigo), todas na seção 6.
6. "Fermata", no código, é SÓ a reserva da fila de espera esperando a fornada (`shopman/shop/services/waitlist.py:294-305`, `:383-390`). O pedido "aguardando confirmação da loja" é outra coisa: status `new` com `confirmation.mode` do canal.
7. Nenhum canal cria ordem de produção a partir de pedido. A encomenda entra no plano só como reserva (`Hold`) somada pela sugestão de produção (`packages/craftsman/shopman/craftsman/contrib/demand/backend.py:127-148`), e quem decide produzir é o operador (`shopman/backstage/api/operations.py:3631-3648`).
8. Encomenda para data sem fornada planejada vira "demanda" (reserva sem lote, `quant=None`) e o pedido nasce mesmo assim, em todos os canais com `stock.preorder=True` (default, `shopman/shop/config.py:184`).
9. A reserva de encomenda (lote planejado ou demanda) nunca expira enquanto o pedido espera (`shopman/shop/adapters/stock.py:177-185`).
10. A fase 2 (conserto da loja: `add_item` passar a data da sacola para a resolução) depende de P1, P2 e P3 da seção 7.

## 2. Glossário: os termos como o CÓDIGO os usa

| Termo | O que é no código | Onde |
|---|---|---|
| **Data alvo / data combinada** | `delivery_date` (ISO) em `Session.data` e depois em `Order.data`. Única leitura canônica: `get_commitment_date` | `shopman/shop/services/order_helpers.py:236-246`; `docs/reference/data-schemas.md:22` |
| **Encomenda** (`is_preorder`) | `delivery_date` maior que hoje | `docs/reference/data-schemas.md:203` |
| **Slot / janela** | `delivery_time_slot`. Dois vocabulários: encomenda usa turno (`slot-09`, `slot-12`, `slot-15`, "a partir das"); venda de hoje no PDV usa janela de meia hora (`"14:00-14:30"`) | `docs/reference/data-schemas.md:23`; seed `config/management/commands/seed.py:1416-1420` |
| **Fornada / lote planejado** | `Quant` com `target_date` preenchido (null = físico). Nasce quando a ordem de produção é planejada | `packages/stockman/shopman/stockman/models/quant.py:103-109`; `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:255-293` |
| **Hold (reserva)** | Reserva do Stockman: `sku`, `quant` (nulo = demanda), `quantity`, `target_date` obrigatório, `expires_at` (nulo = sem prazo), `metadata.reference` (`<session_key>` na sacola, `order:<ref>` no pedido) | `packages/stockman/shopman/stockman/models/hold.py:85-113` |
| **Reserva de demanda** | Hold com `quant=None`: produto feito na hora (`demand_ok`) ou encomenda para data sem fornada. Marca `metadata.on_demand` | `shopman/shop/adapters/stock.py:155-185`; `packages/stockman/shopman/stockman/services/holds.py:272-293` |
| **Fila de espera** (`waitlist`) | Aspecto de canal que deixa o cliente reservar fornada ainda não assada até `horizon_days` | `shopman/shop/config.py:218-240` |
| **Fermata** | Estado DERIVADO de uma reserva de fila: `metadata.planned`, aponta para quant planejado, `expires_at=None`. Não cobra, não corre relógio | `shopman/shop/services/waitlist.py:294-305`, `:383-390`, `:439-455` |
| **Materialização** (`realize`) | Fim da fornada: o quant planejado vira físico, as reservas migram e ganham prazo (30 min, depois 48 h se forem de pedido) | `packages/stockman/shopman/stockman/services/planning.py:86-304`; `shopman/shop/handlers/_stock_receivers.py:121-215` |
| **Janela de confirmação da fila** (`confirming`) | Depois da materialização, o cliente tem `waitlist.confirmation_minutes` (15) para confirmar; senão a vaga vai para o próximo | `shopman/shop/services/waitlist.py:655-721`, `:1026-1050` |
| **Aguardando confirmação da loja** | Pedido em status `new` sob `confirmation.mode` (`immediate`, `auto_confirm`, `auto_cancel`, `manual`) | `shopman/shop/config.py:72-89`; `shopman/shop/lifecycle.py:721-779` |
| **Despertador da encomenda** (`preorder.activate`) | Directive agendada para 00:05 da data (ou para o início de preparo do iFood) que libera KDS e baixa | `shopman/shop/lifecycle.py:927-982`, `:985-1034`; `docs/reference/data-schemas.md:582-593` |
| **Lead time** | Antecedência mínima para registrar DEMANDA (`Product.metadata.lead_time_hours` ou `stock.default_lead_time_hours`). Não vale para data com fornada planejada | `shopman/shop/config.py:55-61`; `shopman/shop/services/stock.py:215-226` |
| **Margem de segurança** | Unidades que o canal remoto não mostra nem reserva (2 no seed); não vale no hold de commit | `config/management/commands/seed.py:6122-6133` |

## 3. Tabela canal × pergunta

| Pergunta | PDV balcão | PDV encomenda | Loja online | iFood agendado |
|---|---|---|---|---|
| Fonte da data | Nenhuma: vazio = hoje (`pos_sales_mode.py:79-85`) | Operador escolhe no modal, obrigatória (`pos_sales_mode.py:98-106`) | Cliente escolhe no CHECKOUT (`storefront/api/views.py:421-424`); a sacola tem data derivada das reservas (`cart.py:81-101`) | `schedule.deliveryDateTimeStart` do iFood (`ifood_ingest.py:164-169`) |
| Horário / slot | Proibido (`pos_sales_mode.py:79-85`) | Opcional, validado por prontidão do produto (`pos.py:1003-1063`) | Obrigatório na retirada, validado no checkout (`views.py:287-308`; `pickup_slots.py:304-338`) | Janela do iFood, validada só por coerência (`ifood_schedule.py:44-55`) |
| Resolução de disponibilidade | Nenhuma ao adicionar; aviso não bloqueante na revisão (`pos.py:838-858`) | Igual, com a data da comanda (`pos.py:944-959`) | Ao adicionar, SEM a data da sacola (`cart.py:184-190`; `availability.py:748-752`) | Desligada no commit (`check_on_commit=False`, `seed.py:6191`) |
| O que reserva e quando | Só no commit (`lifecycle.py:321-322`), prazo 48 h | Só no commit; lote planejado ou demanda, sem prazo (`adapters/stock.py:177-185`) | A cada toque na sacola (30 min); no commit adota ou refaz (`stock.py:115-126`) | No commit, na data do agendamento; sem janela válida, só na hora do preparo (`ifood_schedule.py:70-75`) |
| Aguardando confirmação | Não: auto-aceita (`lifecycle.py:746-758`) | Sim: forçado a `manual`, sem prazo e sem alerta (`lifecycle.py:737-744`) | Sim: `manual` com alerta de 10 min (`seed.py:6165`) | Sim: `manual`, alerta 5 min, SLA do iFood 8 min (`seed.py:6181-6185`) |
| Encomenda sobre lote planejado | n/a | Entra se UM lote tem livre suficiente; senão demanda inteira (`planning.py:207-236`; `holds.py:42-101`) | Igual, no commit para data futura | Igual |
| Encomenda que define o plano | n/a | Só via soma de reservas na sugestão; operador decide | Igual | Igual (se a reserva foi feita) |
| Sem estoque e sem fornada | Venda vale, alerta `stock_hold_gap` (`stock.py:289-317`) | Pedido nasce com demanda; lead time vira alerta, não recusa (`stock.py:219-226`, `:300-317`) | Commit registra demanda; lead time recusa no commit (`stock.py:258-264`) | Pedido nasce; demanda ou alerta (`stock.py:122-126`, `:310-317`) |
| Promessa escrita ao cliente | Nenhuma de data | Ficha impressa com data; `order_accepted` sem data | Sacola, checkout, acompanhamento (seção 4.3) | Nenhuma (iFood fala com o cliente) |

## 4. Canal por canal

### 4.1 PDV balcão (venda imediata)

O PDV é UM canal (`pdv`, `config/management/commands/seed.py:6212`) com dois modos em `session.data.pos.sales_mode`: `counter` ou `order` (`shopman/shop/services/pos.py:2260`; leitura em `shopman/shop/services/pos_sales_mode.py:12-19`). `POSTab` guarda só ref e rótulo, sem data (`shopman/backstage/models/pos.py:9-38`).

- **Data.** Não existe. `validate_sales_mode` recusa `delivery_date`, `delivery_time_slot` ou entrega no balcão com `counter_requires_immediate_pickup` (`pos_sales_mode.py:79-85`). A revisão assume hoje (`pos.py:944-959`). Ressalva: payload sem `sales_mode` pula essa checagem (`pos_sales_mode.py:74-75`).
- **Slot.** Proibido pelo mesmo gate.
- **Disponibilidade.** Adicionar produto não consulta estoque (`surfaces/pos-nuxt/app/composables/usePosSale.ts:1259-1266`). O selo "Esgotado" da grade lê o estoque de hoje sem data (`shopman/backstage/projections/pos.py:2336-2377`). A revisão chama `availability.decide(..., target_date=hoje)` e devolve só aviso não bloqueante (`pos.py:838-858`).
- **Reserva.** Nenhuma enquanto a comanda é montada (`availability.reserve` só é chamado de `cart.py`, que o PDV não usa). No commit, `secure_stock` é pulado porque `payment.timing == "external"` (`shopman/shop/lifecycle.py:214-215`; `seed.py:6060`), e `_on_commit` chama `stock.hold(order)` no caminho brando (`lifecycle.py:321-322`; `stock.py:55`). Reserva com `reference="order:<ref>"`, prazo de 48 h, prioridade 0 (`stock.py:239-246`, `:934-940`). Se falta, a venda toma reservas de sacola de clientes remotos (`stock.py:135-139`, `:289-298`) e o resto vira alerta.
- **Confirmação.** `confirmation.mode="immediate"` (`seed.py:6053`): aceita na hora (`lifecycle.py:746-758`), baixa e fecha (`lifecycle.py:483-505`).
- **Produção.** Não alimenta.
- **Sem estoque.** A venda vale; o resto vira `stock_hold_gap`: "Pedido {ref} ficou SEM reserva de estoque para {qty}× {sku} … O item pode faltar na separação." (`stock.py:310-317`, `:844-857`).
- **Texto.** Operador, na revisão: "só N em estoque. A venda de balcão vale; confira o estoque depois." (`pos.py:989-1000`). Cliente: nenhuma promessa de data.
- **Testes.** `shopman/shop/tests/test_pos_sales_mode.py:47` (`test_counter_refuses_delivery_or_schedule`); `shopman/shop/tests/test_counter_handoff.py:277`; `shopman/shop/tests/test_counter_sale_cedes_cart_holds.py:77`.

### 4.2 PDV encomenda (comanda com data)

- **Data.** Obrigatória, hoje ou depois (`pos_sales_mode.py:98-106`), exigida antes dos itens (`pos_intent.py:178-180`; `pos.py:1729`, `:1842`). Gravada em `session.data["delivery_date"]` por `_append_schedule_ops` (`pos.py:3866-3878`, chamado em `pos.py:2271`). Uma por comanda, nunca por linha (D17). O modal não tem data padrão; "Hoje" grava o dia da loja (`surfaces/pos-nuxt/app/components/PosScheduleModal.vue:78-81`, `:189`). As datas oferecidas vêm de `business_calendar.available_dates` até `max_preorder_days` (`shopman/backstage/projections/pos.py:2896-2946`).
- **Slot.** Opcional ("A combinar"). `_validate_schedule` (`pos.py:1003-1063`) confere data válida, não passada, dentro de `max_preorder_days` (30 no seed, `seed.py:1426`), dia aberto (`shopman/shop/services/preorder_dates.py:67-88`) e slot só contra a prontidão do produto (`shopman/shop/services/fulfillment_window.py:354-449`). Slot não tem capacidade.
- **Lead time.** Não conferido antes do commit no PDV; só aparece no hold (abaixo).
- **Disponibilidade.** Igual ao balcão, mas a revisão passa a data da comanda (`pos.py:838-858`, `:944-959`). O "Esgotado" da grade continua lendo HOJE, mesmo no modo encomenda (`backstage/projections/pos.py:2336-2377`; `PosProductGrid.vue:163`).
- **Reserva.** Só no commit. Data futura: não adota reservas de sessão, `allow_demand` vem de `stock.preorder` (True por default e deliberado para o PDV, `shopman/shop/config.py:184-190`) (`stock.py:115-126`). O Stockman ancora num lote planejado que caiba inteiro, ou cria demanda (`packages/stockman/shopman/stockman/services/holds.py:42-101`, `:272-293`). As duas ficam sem prazo (`adapters/stock.py:177-185`). Encomenda para HOJE reserva como balcão.
- **Aguardando confirmação.** O canal é `immediate`, mas encomenda do PDV é forçada a `manual` (`lifecycle.py:737-744`). Consequências: fica `new` sem prazo; sem alerta de pedido esquecido (o `pdv` não tem `stale_new_alert_minutes`, `lifecycle.py:768-779`); o aviso `order_received` não sai, porque o teste da linha `lifecycle.py:364` lê o modo do canal (`immediate`). Ao aceitar uma encomenda futura: despertador + `order_accepted` (`lifecycle.py:468-471`). Mandar à cozinha antes do dia é recusado (`pos.py:1854-1877`). Qual tela faz o aceite: **NÃO VERIFICADO**.
- **Produção.** Só pela soma das reservas na sugestão (seção 5).
- **Sem estoque e sem fornada.** Nasce demanda. Produto pausado é recusado pelo Stockman (`holds.py:216-218`); data dentro do lead time desliga a demanda (`stock.py:219-226`, lead time do seed em `seed.py:3034-3044`), mas como o PDV usa o caminho brando o pedido NÃO é recusado: vira reserva parcial + `stock_hold_gap` (`stock.py:300-317`). Sem teste para o PDV (**NÃO VERIFICADO** por teste; `test_untracked_gate_and_lead_time.py` usa canal web).
- **Texto ao operador.** "Informe a data da encomenda antes de adicionar produtos." (`pos_sales_mode.py:104`); "Esta encomenda está marcada para dd/mm/aaaa. Envie à cozinha somente no dia combinado." (`pos.py:1866-1872`); na revisão, "ainda não está pronto: sai do lote planejado para a data." (`pos.py:989-1000`).
- **Texto ao cliente.** `order_accepted`: "Seu pedido *{order_ref_short}* está confirmado. O total é *{order_total_display}*. Vamos preparar com todo carinho. ✨" (`shopman/shop/notification_copy.py:50-52`), sem a data. Lembrete na véspera: "…está agendado para amanhã…" (`notification_copy.py:112-116`). Recibo impresso: sem a data (`shopman/backstage/services/receipt_escpos.py:280-397`). Ficha do pedido: "HOJE" / "AMANHÃ" / "QUA, 08/07" calculado na impressão (`receipt_escpos.py:425-455`).
- **Testes.** `shopman/shop/tests/test_pos_scheduled_order.py:285` (`test_data_de_HOJE_nao_adia_a_venda_de_balcao`), `:313`, `:340`, `:359`, `:370`, `:389`; `shopman/shop/tests/test_counter_handoff.py:257` (`test_pos_order_mode_waits_for_human_acceptance_even_on_immediate_channel`); `shopman/backstage/tests/test_pos_fire.py:173`.

### 4.3 Loja online

Mesma sacola serve concierge do WhatsApp, recompra e oferta (`cart.py:91-92`; chamadores em `shopman/storefront/concierge/tools.py:688`, `customer_orders.py:611`, `offers.py:171`).

- **Fonte da data.** Duas, e separadas:
  - **Data da sacola**, derivada: as datas das reservas vivas que apontam para lote (`shopman/shop/services/availability.py:265-308`). Reserva de demanda e SKU não rastreado não fixam data (`availability.py:273-277`).
  - **Data do checkout**, escolhida pelo cliente: `delivery_date` gravada só no checkout (`shopman/storefront/api/views.py:421-424`). O padrão no Nuxt é o primeiro dia de operação (`surfaces/storefront-nuxt/app/pages/finalizar.vue:776-777`), com opções "Hoje" e "Amanhã"/"Próxima fornada" vindas do calendário da casa, NÃO das reservas (`finalizar.vue:497-520`; `shopman/shop/projections/checkout.py:136-151`).
  - **Ninguém compara as duas.** Não há código que confronte `delivery_date` com as datas das reservas no caminho do checkout (`views.py:203-308`). O único confronto de estoque por data (`cart_stock_shortfalls`, `shopman/storefront/intents/checkout.py:151-160`) mora em `interpret_checkout`, que não tem chamador fora de teste (busca por `interpret_checkout` em `shopman/`).
- **Slot.** Turnos "A partir das 9h/12h/15h" sem fim e sem capacidade (`shopman/storefront/services/pickup_slots.py:65-69`, `:185-195`). O mais cedo permitido é o maior `ready_from` entre os itens; hoje também respeita o relógio e o fechamento (`pickup_slots.py:239-301`, `:148-179`). Nada é validado ao adicionar; no checkout: data obrigatória com entrega ou slot (`views.py:203-207`), passada, além do máximo, dia fechado, hoje depois de fechar (`views.py:228-271`), slot de retirada (`views.py:287-308`). Lead time só no commit (`stock.py:215-226`, `:258-264`).
- **Resolução de disponibilidade (o defeito da fase 2).** Sequência real de `add_item`:
  1. trava a sessão (`cart.py:182`);
  2. reserva SEM data: `_reserve_or_raise(sku, qty, session_key, channel_ref)` (`cart.py:184-189`, `:628-639`);
  3. `availability.reserve` escolhe a data sozinho: `waitlist.reserve_target_date` devolve `None` (= hoje) se o pronto de hoje cobre, senão a próxima fornada (`availability.py:748-752`; `waitlist.py:249-288`);
  4. cria o hold (`availability.py:779-787`);
  5. só então `_refuse_a_second_date` compara com as datas que a sacola já tinha (`cart.py:190`, `:94-101`) e levanta `CartDateMismatchError`; o `transaction.atomic` desfaz a reserva (`cart.py:164`, `:87-88`).
  Efeitos: sacola de amanhã + item que tem pronto hoje é recusado mesmo que a fornada de amanhã o cobrisse (teste `shopman/storefront/tests/web/test_cart_one_date_per_order.py:124-139` consagra isso); sacola de hoje + pronto de hoje que não cobre a quantidade pula para a fornada de amanhã e vira "outro pedido", em vez de oferecer o parcial de hoje. O AJUSTE de quantidade (`update_qty`) já ancora na data da reserva existente (`availability.py:1225-1235`).
- **Reserva.** A cada adicionar, ajustar e remover, com `reference=session_key` (`availability.py:779-787`). Prazo do canal, 30 min (`seed.py:6122`; `availability.py:696-711`); a renovação usa 30 fixos, não o do canal (`availability.py:59`, `:83-91`). Reserva de fila e de demanda: sem prazo (`adapters/stock.py:177-185`). No commit: data hoje ou vazia adota as reservas por SKU, sem olhar a data delas (`stock.py:115-116`, `:184-191`, `:872-884`), e as passa a 48 h, menos a fermata, que segue sem prazo (`stock.py:943-975`); data futura não adota, reserva de novo na data e solta as da sacola (`stock.py:122-126`, `:328-332`).
- **Aguardando confirmação.** `manual` com alerta aos 10 min (`seed.py:6165`). O cliente recebe `order_received` (`lifecycle.py:364-365`): "…Estamos conferindo a disponibilidade e avisamos em seguida." (`notification_copy.py:35`). Reservas ficam; cozinha não é avisada; pedido `new` não entra no vínculo com produção (`shopman/shop/handlers/production_order_sync.py:23`).
- **Fila de espera (fermata).** Ligada no seed para loja e WhatsApp, horizonte de 2 dias, 15 min para confirmar, `serve_next` (`seed.py:6142-6159`). Pedido aceito em fermata não avança: "Reserva na fila de espera. O preparo abre quando o lote sair." (`shopman/shop/services/operator_orders.py:102-104`, `:292-293`). No fim da fornada, `open_window` chama FCFS quem cabe inteiro (`shopman/shop/services/production.py:129-154`; `waitlist.py:655-721`); `confirm` cobra (`waitlist.py:724-760`); prazo vencido libera e serve o próximo (`waitlist.py:1026-1050`).
- **Produção.** Só pela soma de reservas (seção 5).
- **Sem estoque e sem fornada.** Ao adicionar: 409 com substitutos. No commit para data futura: demanda, ou recusa limpa por lead time (`stock.py:258-264`).
- **Promessa escrita (literal).**
  - Sacola, recusa de outra data: "Isso fica para outro pedido" e "{name} é para {item_day}, e sua sacola é para {cart_day}. Cada pedido tem uma data só: envie este e monte outro pedido para {item_day}." (`shopman/storefront/presentation/cart.py:442-446`); botão "Ver minha sacola" (`shopman/storefront/api/surface.py:138`).
  - Sacola, linha na fila: "Envie o pedido para garantir a sua prioridade." e "Previsto para {date}" (`shopman/shop/omotenashi/copy.py:196-202`).
  - Checkout: "Escolha a data." (`views.py:205`); "Não é possível encomendar para uma data passada." (`preorder_dates.py:71`); "Já encerramos o atendimento de hoje. Escolha outra data." (`views.py:262`); rodapé da revisão "Itens em lista de espera: avisamos quando ficarem prontos." (`finalizar.vue:2211`).
  - Acompanhamento: "Pedido garantido para {when}. Preparamos tudo fresco no dia." (`shopman/storefront/presentation/order_tracking.py:780`); "Sua reserva está na fila de espera da fornada prevista para {when}. Avisamos quando sair." (`order_tracking.py:1124`); "Estamos conferindo a disponibilidade. Avisamos em seguida." (`order_tracking.py:960`); painel da fila "Fornada prevista para {{ tracking.waitlist_planned_for_display }}." (`surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue:577-580`).
  - Notificação de fila: "Oba! 💛✨ Acabou de sair do forno{customer_name_greeting}! Confirme o pedido *{order_ref_short}* para garantir: {tracking_url}" (`notification_copy.py:205-207`), sem o prazo, embora o prazo seja passado (`waitlist.py:712`).
- **Testes.** `shopman/storefront/tests/web/test_cart_one_date_per_order.py:98-182`; `shopman/storefront/tests/web/test_cart_adjustment_keeps_reservation.py:313` (`TestOneLineOneDate`); `shopman/storefront/tests/test_pickup_slots.py:281`, `:293`; `shopman/shop/tests/test_preorder_closed_store_commit.py:123-166`. Não há teste para: `add_item` recebendo a data da sacola; checkout com data diferente da das reservas.

### 4.4 iFood (pedido agendado)

- **Fonte da data.** Lida em dois caminhos de entrada, e só um deles a traz:
  - Eventos (`/ifood/events/` e polling): busca o pedido completo e mapeia `orderTiming` e `schedule` (`shopman/shop/services/ifood_events.py:281-283`; `shopman/shop/services/ifood_orders.py:94-95`). `map_schedule` lê `preparationStartDateTime`, `schedule.deliveryDateTimeStart` e `deliveryDateTimeEnd` (`shopman/shop/services/ifood_schedule.py:19-36`). Com `order_timing == "SCHEDULED"`, a ingestão grava `order.data["delivery_date"]` = data local do início da janela (`shopman/shop/services/ifood_ingest.py:164-169`; `ifood_schedule.py:58-63`), o mesmo campo de todos os canais.
  - Webhook antigo `/ifood/` (`shopman/shop/webhooks/urls.py:16`): `_to_ingest_payload` repassa só ref, loja, criação, cliente, entrega, itens e observação (`shopman/shop/webhooks/ifood.py:235-253`). O agendamento se perde e o pedido vira imediato. Qual dos dois o iFood chama no alpha: **NÃO VERIFICADO**.
- **Slot.** Só coerência da janela (início de preparo antes do início da janela, início antes do fim) (`ifood_schedule.py:44-55`). Sem horário de funcionamento, capacidade ou lead time. Reagendar é recusado: "A data do pedido do iFood é combinada no iFood." (`shopman/shop/services/reschedule.py:222-225`).
- **Disponibilidade.** `check_on_commit=False` para o iFood (`seed.py:6191`), então nada recusa.
- **Reserva.** Com janela válida, no commit, na data do agendamento (`ifood_schedule.py:70-75`; `stock.py:115`). Sem janela válida e antes da hora, adiada até o preparo (`lifecycle.py:316-326`, `:473-474`, `:1013-1014`). O iFood herda `stock.preorder=True` (sem chave no seed), embora o comentário do config diga que marketplace declara False (`shopman/shop/config.py:184-190`). Pedido de teste não reserva (`stock.py:103-105`).
- **Aguardando confirmação.** `manual`, alerta aos 5 min, SLA externo de 8 min contado do `createdAt` do iFood (`seed.py:6181-6185`; `ifood_ingest.py:171-175`). O mesmo prazo vale para agendado; o que o iFood exige de fato para agendado: **NÃO VERIFICADO**. Confirmar cedo é permitido (`ifood_schedule.py:84`). O trabalho físico espera o `preparationStartDateTime`: despertador nessa hora (`lifecycle.py:942-946`, `:973-982`), avanço manual bloqueado com "O horário de preparo do iFood ainda não permite avançar. Confira o agendamento deste pedido." (`operator_orders.py:87`, `:272-276`). Janela inválida gera alerta crítico (`lifecycle.py:963-971`).
- **Produção.** Só se a reserva foi feita com a data (janela válida); pedido sem janela é invisível para o plano até a hora do preparo.
- **Sem estoque.** Pedido nunca é cancelado: demanda para data futura (`stock.py:122-126`) ou reserva parcial + `stock_hold_gap` (`stock.py:300-317`).
- **Texto.** Ao operador: "Pedido agendado no iFood: aguarde o início do preparo em {dd/mm/YYYY às HH:MM}." (`ifood_schedule.py:95`); "Aguardando horário do iFood…" (`shopman/backstage/projections/order_queue.py:1892`). Ao cliente: nada sai daqui; o telefone é relé da central (`seed.py:6233`; `shopman/shop/services/notification.py:1164-1211`).
- **Testes.** `shopman/shop/tests/test_ifood_schedule.py:93-112`, `:146-197`, `:227-246`, `:271-299`; `shopman/shop/tests/test_ifood_operational_gates.py:49-100`. Nenhum cobre o webhook antigo perdendo o agendamento.

## 5. Fluxos de produção

### 5.1 Encomenda sobre produção JÁ planejada

1. Planejar uma ordem de produção cria (ou soma em) um quant planejado por (sku, data, posição) (`packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:255-300`).
2. No commit da encomenda, o Stockman procura UM quant elegível que cubra a quantidade inteira, FEFO (`packages/stockman/shopman/stockman/services/holds.py:42-101`, `:128-133`). Elegível inclui quant planejado com data menor ou igual à data pedida e estoque físico válido na data (`packages/stockman/shopman/stockman/services/scope.py:57-59`). Se a validade de um quant PLANEJADO é medida corretamente para data posterior: **NÃO VERIFICADO**.
3. Cabe: a reserva ancora no lote ("entra no lote existente"). Não cabe inteira: a quantidade TODA vira demanda (`quant=None`), sem dividir (`holds.py:272-293`).
4. No fim da fornada, `realize` puxa as reservas ancoradas e as demandas da mesma data, por prioridade (pedido antes de sacola) e ordem de chegada; a que não cabe inteira fica de fora (`packages/stockman/shopman/stockman/services/planning.py:207-272`; prioridade em `stock.py:936-940`).
5. Separado disso, um vínculo VISUAL pedido↔ordem de produção (`awaiting_wo_refs`, `committed_order_refs`) liga pedidos aceitos a ordens com data menor ou igual à do pedido (`shopman/shop/handlers/production_order_sync.py:1-6`, `:23`, `:508-580`, `:771-799`). Não reserva nada e ignora pedido `new`.
6. Reduzir uma ordem de produção abaixo do reservado falha com `COMMITTED_HOLDS` (`packages/craftsman/shopman/craftsman/services/scheduling.py:477-500`).

### 5.2 Encomenda que DEFINE o planejamento

1. Nada cria ordem de produção a partir de pedido (busca sem resultado; `accept_suggestion` em `packages/craftsman/shopman/craftsman/contrib/formula/service.py:64` não tem chamador fora do pacote).
2. A sugestão calcula `(média histórica + comprometido) × (1 + segurança)`, com multiplicador sexta e sábado (`packages/craftsman/shopman/craftsman/services/queries.py:282-290`). "Comprometido" é a soma de TODAS as reservas ativas do SKU na data: sacola, pedido, lote planejado e demanda (`packages/craftsman/shopman/craftsman/contrib/demand/backend.py:127-148`).
3. Receita sem histórico suficiente é pulada mesmo com encomenda (`queries.py:255-256`, `:267-269`): a encomenda não aparece na sugestão.
4. O histórico conta pedido concluído pela data de CRIAÇÃO, não pela data da encomenda (`backend.py:63-80`).
5. Quem decide é o operador, no quadro de produção (`shopman/backstage/projections/production.py:2975-2982`) via `apply_planned` (`shopman/backstage/api/operations.py:3631-3648`); o comando `suggest_production` só imprime (`shopman/shop/management/commands/suggest_production.py:51`).
6. Quando: sempre que o operador planejar. Nenhum gatilho avisa a produção de que chegou encomenda sem fornada.

## 6. Divergências e lacunas (registradas, não consertadas)

**L1. Duas datas no mesmo pedido da loja (a ressalva da premissa).** Sacola com reserva da fornada de amanhã + checkout "Hoje" → commit adota as reservas de amanhã (`stock.py:115-116`, `:184-191`, sem filtro em `:872-884`). O acompanhamento usa `delivery_date` no texto principal (`order_tracking.py:773`) e a data da reserva no painel (`index.vue:580`; `waitlist.py:490-499`). A revisão do checkout esconde o selo de fila quando as datas diferem (`surfaces/storefront-nuxt/app/presentation/cart.ts:95-110`), então o cliente não é avisado. Comportamento de execução: **NÃO VERIFICADO** por teste ou ensaio.

**L2. A resolução ao adicionar não recebe a data da sacola** (`cart.py:184-190`; `availability.py:748-752`). Reserva, trava o quant e só depois recusa. É o objeto da fase 2 e de D18(c).

**L3. Frestas por onde uma segunda data entra na sacola.** (a) Primeira linha é produto feito na hora ou não rastreado: não fixa data (`availability.py:273-277`). (b) Reserva de 30 min vencida sai do conjunto "de antes" (`availability.py:302`) e a próxima data é aceita (inferido, **NÃO VERIFICADO** por teste). (c) iFood pelo webhook antigo perde a data (`webhooks/ifood.py:235-253`).

**L4. Docstrings que contradizem D17.** `shopman/storefront/tests/web/test_cart_one_date_per_order.py:5-6` diz "No balcão a régua é outra: a comanda pode ter linhas de datas diferentes, uma data por linha", o que o código não faz (`pos_intent.py:345-385`; D17).

**L5. Encomenda esperando confirmação não tem prazo nem rede.** Reservas de lote planejado e de demanda de pedido não expiram (`adapters/stock.py:177-185`) e o varredor ignora `order:` (`shopman/shop/management/commands/sweep_orphan_holds.py:15-26`). Encomenda do PDV forçada a `manual` fica sem alerta e sem `order_received` (`lifecycle.py:737-744`, `:364-365`, `:768-779`). Se a fornada nunca acontecer, nada cancela nem avisa.

**L6. O "ENCOMENDA-ROUTING-PLAN" descreve uma fermata de pedido em dois portões (produção, depois pagamento) que não existe para pedido;** existe só para a fila da sacola (`docs/plans/ENCOMENDA-ROUTING-PLAN.md` versus `waitlist.py`). O `AVAILABILITY-SALE-PRODUCTION-PLAN.md:179`, `:214` diz que o PDV declara `preorder=False`; o código mantém True de propósito (`config.py:184-190`).

**L7. Configuração morta ou documentada errado.** `stock.planned_hold_ttl_hours` (`config.py:176`) não é lido por lógica nenhuma (só validado em `:492` e projetado em `shopman/shop/projections/channel_policy.py:96`). `MATERIALIZED_HOLD_TTL_MINUTES` não é campo de `StockmanSettings` e não pode ser sobrescrito (`packages/stockman/shopman/stockman/services/planning.py:36`, `:222-226`; `conf.py:19-47`). `data-schemas.md:1041` diz que `hold_ttl_minutes=None` é "sem expiração"; o código usa 30 min. `docs/guides/lifecycle.md:83`, `:88`, `:114` ainda falam de `_on_confirmed`/CONFIRMED.

**L8. iFood.** `preorder` herdado True contra o comentário do config (`config.py:190`; `seed.py:6187-6191`). O SLA de 8 min vale igual para agendado. A prévia do KDS lê chaves de horário que a ingestão não grava e cai em "Horário não informado" (`shopman/backstage/projections/kds.py:1000-1007`; inferido, **NÃO VERIFICADO** em execução).

**L9. Promessa escrita que pode mentir.** `order_accepted` não diz a data, nem em encomenda (`notification_copy.py:50-52`). O lembrete diz "amanhã" fixo e a guarda só olha o status (`notification_copy.py:112-116`; `shopman/shop/handlers/notification.py:125`). `waitlist_available` não diz o prazo. `stock_arrived` diz hora sem dia (`_stock_receivers.py:300-302`). `_planned_for_display` mostra data passada como "hoje" (`shopman/storefront/presentation/cart.py:423-424`). O "Esgotado" do PDV no modo encomenda lê hoje (`backstage/projections/pos.py:2336-2377`).

**L10. Texto com travessão visível ao cliente** (regra "copy sem travessão"): "Fechado{suffix} — escolha outra data." e "A casa não abre em {dd/mm/aaaa} — escolha outra data." (`shopman/shop/services/preorder_dates.py:79`, `:87`), usados pela loja, pelo PDV e pelo reagendar.

**L11. Sugestão de produção soma o que já está no lote.** "Comprometido" inclui reservas já ancoradas em lote planejado (`backend.py:127-148`) e a sugestão é um total-alvo, não um incremento (`queries.py:282-284`). Se isso infla a sugestão quando já existe ordem planejada para a data: **NÃO VERIFICADO**.

**L12. `interpret_checkout` sem chamador.** A checagem de estoque por data e de lead time do checkout mora num caminho que só os testes usam (`shopman/storefront/intents/checkout.py:23`, `:151-205`, `:428-522`); a API usa `views.py` e deixa o lead time para o commit. O texto dele também tem travessão (`intents/checkout.py:516-517`).

## 7. Perguntas fechadas para o dono

> No formato de PENDING-DECISIONS. Para a fase 2 sair bastam **P1, P2 e P3**; as demais
> podem esperar sem bloquear.

### P1. A lei "uma data por pedido" vale para os quatro canais?

**Contexto.** O código já tem uma data por pedido em todos os canais (seção 1). D16 fixou isso para a
loja; D17 recomendou manter a comanda do PDV com uma data só até o go-live. O iFood tem uma data por
construção (o agendamento dele).
**Opções.** 1) Sim, nos quatro canais, e a data do pedido é `delivery_date` (as reservas obedecem a
ela). 2) Sim na loja e no iFood; PDV com data por linha depois do go-live (D17 opção 2).
**Recomendação:** 1. Confirma D17 opção 1 e dá à fase 2 uma regra única.

### P2. Quando a data escolhida no checkout difere da data da sacola, qual vale?

**Contexto.** A sacola tem data pelas reservas; o checkout oferece "Hoje" e "Próxima fornada" pelo
calendário, sem olhar a sacola. Escolher "Hoje" com reserva de amanhã gera um pedido com duas
promessas (L1); escolher uma data futura descarta as reservas e reserva de novo.
**Opções.** 1) A data da sacola manda: o checkout já abre nela e só oferece outra data se o cliente
trocar de propósito, e aí o commit refaz as reservas na data nova (recusa limpa se não houver).
2) A data do checkout manda sempre: o commit refaz qualquer reserva de data diferente. 3) Manter.
**Recomendação:** 1. É o que o cliente montou, e evita a promessa dupla sem tirar a escolha dele.

### P3. Plano da fase 2: a sacola resolve o item na data dela (confirma D18(c))?

**Contexto.** Hoje `add_item` reserva sem a data, escolhe "pronto de hoje primeiro" e só depois
recusa (L2). Sacola de amanhã recusa item que a fornada de amanhã cobriria; sacola de hoje empurra
para amanhã o que tem parcial hoje.
**Opções.** 1) Sim: sacola COM data passa essa data para a resolução (`availability.reserve` já
aceita `target_date`); sacola vazia segue a regra atual (hoje primeiro, depois a fornada); item que
não existe na data da sacola recusa com "Isso fica para outro pedido", sem reservar antes. 2) Além
de 1, o cliente escolhe a data antes de montar a sacola (data no topo do cardápio). 3) Não mexer.
**Recomendação:** 1 agora; 2 é desenho de cardápio, depois do go-live.

### P4. Sacola de HOJE quando o pronto de hoje não cobre a quantidade pedida

**Contexto.** Hoje a resolução pula para a fornada de amanhã e, com a sacola já em hoje, a resposta
é "outro pedido". O cliente não fica sabendo que havia algumas unidades hoje.
**Opções.** 1) Oferecer o parcial de hoje ("Levar N"), como já é feito para falta sem fila.
2) Oferecer as duas saídas: parcial hoje ou tudo amanhã em outro pedido. 3) Manter.
**Recomendação:** 1, junto com P3 (é a mesma mudança de resolução).

### P5. Encomenda esperando o aceite da loja: que prazo e que aviso?

**Contexto.** Encomenda fica `new` com reserva sem prazo (L5). Na loja há alerta aos 10 min. No PDV
a encomenda é forçada a aceite manual sem alerta e sem o aviso "estamos conferindo" ao cliente.
**Opções.** 1) PDV ganha o mesmo alerta de pedido esquecido da loja; o cliente não recebe
"estamos conferindo", porque estava no balcão. 2) Igual a 1 e o cliente recebe o aviso.
3) Cancelamento automático depois de X horas sem aceite. 4) Manter.
**Recomendação:** 1.

### P6. Encomenda para data sem fornada planejada: quem garante que alguém vai produzir?

**Contexto.** O pedido nasce com reserva de demanda; só a sugestão de produção a soma, e a sugestão
pula receita sem histórico (5.2). Nada avisa a produção; se ninguém planejar, nada cancela.
**Opções.** 1) A encomenda sem fornada aparece no quadro de produção da data como "encomendado sem
fornada", e o operador decide. 2) Criar ordem de produção automaticamente. 3) Manter.
**Recomendação:** 1 (decisão continua humana, mas visível).

### P7. Encomenda sobre lote planejado que não cabe inteira

**Contexto.** Se nenhum lote tem livre para a quantidade toda, a quantidade inteira vira demanda,
mesmo havendo lote com parte livre (5.1, item 3). Uma encomenda de sábado também pode ancorar num
lote planejado de dia anterior, se a validade permitir.
**Opções.** 1) Manter: a demanda entra na fornada no `realize`, por prioridade. 2) Dividir: o que
cabe ancora no lote, o resto vira demanda. 3) Ancorar só no lote da própria data.
**Recomendação:** 1 até o go-live; 3 merece conversa com a produção (frescor).

### P8. iFood agendado sem estoque para a data

**Contexto.** O iFood herda `preorder=True` e registra demanda; o comentário do config diz que
marketplace declara False (L8). O pedido já está pago no iFood e nunca é recusado aqui.
**Opções.** 1) Manter demanda (conta na sugestão e aparece no plano) e corrigir o comentário.
2) Declarar `preorder=False`: a falta vira só alerta de buraco de estoque.
**Recomendação:** 1.

### P9. Turno de retirada sem capacidade

**Contexto.** "A partir das 9h/12h/15h" não tem limite de pedidos; a promessa é de prontidão do
produto, não de fila no balcão.
**Opções.** 1) Manter. 2) Capacidade por turno.
**Recomendação:** 1 até haver fila real no balcão.

## 8. O que ficou NÃO VERIFICADO

- Configuração gravada no banco vivo do alpha (canais, fila, `preorder`): só o seed foi lido.
- Qual entrada do iFood o portal chama no alpha (`/ifood/` ou `/ifood/events/`).
- O que o iFood exige para confirmar pedido agendado (prazo diferente de 8 min?).
- L1 em execução (checkout "Hoje" com reserva de amanhã): deduzido do código, sem ensaio nem teste.
- L3(b), reserva vencida abrindo a segunda data: deduzido, sem teste.
- Validade de quant planejado servindo data posterior (5.1, item 2).
- Se a sugestão infla com ordem já planejada (L11).
- Qual tela aceita a encomenda do PDV.
- PDV com lead time violado: sem teste para o canal `pdv`.
- Prévia do KDS para iFood caindo em "Horário não informado".
