# Auditoria de fronteiras do Core: que outros domínios estão sem casa?

> Análise arquitetural, 2026-08-18. Pergunta: além do caixa (já diagnosticado em
> [CASH-LEDGER-ARCHITECTURE.md](CASH-LEDGER-ARCHITECTURE.md), caso de referência,
> não reanalisado aqui), existe outro domínio hoje contornado ou mal alojado que
> mereça um pacote do Core, ou que seja política do orquestrador vivendo numa
> superfície? Leitura só; nenhum código foi alterado. Fatos citados como `path:linha`.

---

## 0. Veredito

**Nenhum outro pacote novo do Core se justifica hoje.** A varredura de 34 models de
superfície e orquestrador, 33 adapters e 10 famílias de JSON encontra **sete
candidatos**, mas nenhum passa no teste que o caixa passou (invariante próprio +
ledger próprio + dois escritores em lados opostos da seta). O que existe é uma
família de **política do orquestrador alojada em superfície e alcançada por bridge
lazy** (o mesmo sintoma da promoção na ADR-019, com a mesma cura: subir para
`shop`, matar o adapter), e uma **agregado que já existe no Core sem ser usado**
(fiscal em `fiscalman`, corrida em `orderman.Fulfillment`). Ranking: (1) **KDS**
(`KDSInstance`/`KDSTicket` no backstage; toda a escrita mora em `shop/services/kds.py`
e passa por um adapter de 13 funções; o próprio backstage delega para cima e o
shop desce de volta), (2) **OperatorAlert** (13 pontos de escrita no shop via
adapter; `UserNotification`, o irmão, já mora no shop), (3) **fechamento do dia**
(único service de superfície que escreve no ledger do Stockman direto), (4)
**documento fiscal** (dez chaves planas em `Order.data` para uma máquina de estado
que `fiscalman` deveria possuir), (5) **corrida de entrega** (`Order.data.courier`
ao lado de um `orderman.Fulfillment` com `tracking_url`/`carrier` vazios), (6)
**"me avise" e favoritos** (a superfície do cliente orquestra notificação e o shop
lê por adapter), (7) **POSTab** (registro de comanda que a `Session.handle_ref` já
resolve). Só 1, 2 e 3 valem mexer antes de doer; 4 a 7 esperam gatilho.

---

## 1. Método e critérios

Cinco marcas, na linha da análise do caixa. Um candidato só sobe quando **(a)-(d)
coincidem e (e) não se aplica**:

| # | Marca | O que conta como prova |
|---|-------|------------------------|
| (a) | Model de domínio vivendo em superfície (`backstage`/`storefront`) ou no orquestrador | o model tem invariante/lifecycle próprio e é escrito por quem não é a superfície |
| (b) | Orquestrador ou outro core alcança esse model por `adapters/*` com import lazy | bridge para **uma** implementação (não é Protocol com 2+ impls selecionadas por settings). "Legal pela regra (`test_shop_imports_surfaces_only_through_adapters`, `shopman/shop/tests/test_import_boundaries.py:136-149`), invertido pela constituição" |
| (c) | Estado de domínio guardado como JSON noutro agregado (`Order.data`, `Session.data`, `Shop.defaults`, `*.metadata`) por falta de casa | família de chaves com máquina de estado, lida por 3+ consumidores, ou reescrita por vários |
| (d) | Mesma pergunta com vários donos / lógica de atribuição duplicada | espelho declarado, `_sync_*`, algoritmo que reinterpreta o JSON |
| (e) | É política transversal e pertence ao orquestrador por direito (precedente ADR-019 promoção; ADR-005 §3 "o framework é o único lugar onde domínios se encontram") | **não** flagrar como pacote; no máximo mover de superfície para `shop` |

Regra de decisão: **default = "fica"**. Pacote do Core exige domínio com invariante
próprio, sem depender de outro core além de refs string, escrito por dois lados
que só se encontram em `packages/` (o caso do caixa). Política composta sobre
cores vai para `shop`. Fato operacional que só a superfície escreve e o B.I. lê é
estado de superfície (ADR-021 §2/§4). O que a auditoria **não** faz: propor
feature nova, redesenhar o que a ADR já fixou (019, 020, 021), ou tratar
tamanho de arquivo como evidência.

Fontes lidas: `CLAUDE.md`, ADR-001/-005/-011/-019/-020/-021, `data-schemas.md`,
todos os `models/*.py` das três apps, todos os `shop/adapters/*.py`, o teste de
fronteira, `config/settings.py` (fiação), e os services que os adapters
alcançam dos dois lados.

---

## 2. Inventário

Vereditos: **DSC** = domínio sem casa · **POL** = política do orquestrador (fica em
`shop`, ou deveria subir para lá) · **SUP** = estado de superfície, ok · **BI** =
leitura/B.I., ok (ADR-021) · **REF** = caso de referência (caixa), fora do escopo.

### 2.1 `shopman/backstage/models/`

| Model (arquivo) | O que é | Escreve | Lê | Veredito |
|---|---|---|---|---|
| `POSTerminal`, `CashShift`, `CashMovement` (`cash_register.py:12,45,266`) | aparelho, custódia, movimento de gaveta | `shop/services/pos.py`, backstage cash | shop, backstage, B.I., closing | **REF** (vira `cashman`) |
| `POSEvent` (`pos_event.py:45`) | log de eventos do PDV (#198) | backstage `pos_events` | closing, cash | **REF** (absorvido pelo livro) |
| `POSTab` (`pos.py:9`) | registro de comanda física (ref+label) | **só** `shop/services/pos.py:159-164` via `adapters/pos.py:7,20` | shop, `omotenashi_qa` | **POL** (candidato 7) |
| `KDSInstance`, `KDSTicket` (`kds.py:8,46`) | estação e ticket de montagem por `session_key`; `KDSInstance.collections` é M2M para `offerman.Collection` (`kds.py:20`) | **shop** (`services/kds.py`, `lifecycle.py:710`, `services/pos.py:578`) via `adapters/kds.py` (13 funções); backstage só delega (`backstage/services/kds.py:6`) | backstage projections/API, `_sse_emitters.py:186-197` | **POL** mal alojada (candidato 1) |
| `OperatorAlert` (`alerts.py:8`) | aviso operacional (21 tipos, 15 deles nascidos no lifecycle/pagamento/produção) | **shop** em 13 pontos (`lifecycle.py:995`, `services/payment.py:774,808`, `courier.py:401`, `pix_confirmation.py:198,255`, `handlers/*`) via `adapters/alert.py` | backstage API/projections/SSE | **POL** mal alojada (candidato 2) |
| `DayClosing` (`closing.py:8`) | snapshot de fechamento do dia (ADR-011 §5) | `backstage/services/closing.py`, que **escreve WASTE no Stockman** (`closing.py:17-19,202`) | closing, B.I. (`bi_cash.py`) | **POL** mal alojada (candidato 3) |
| `OperationTaskTemplate`, `OperationChecklistTemplate/Task/Run`, `OperationTaskRun` (`operation.py:46-217`) | checklists de abertura/rotina/fechamento | backstage `services/operations.py` | backstage API | **SUP** (autocontido; ninguém de fora escreve ou lê) |
| `OperationEpisodeKind`, `OperationEpisode` (`operation_episode.py:36,67`) | episódio que atrapalhou o dia (sinal automático + motivo humano) | backstage | backstage; shop **lê** por `adapters/episodes.py:24` (degrada a vazio) | **BI** (ver §3.8) |
| `OvenRun` (`oven_run.py:17`) | fato temporal do forno, `work_order_ref` string | kiosk de produção (backstage) | B.I. | **BI** (ADR-021 §4 fixou aqui) |
| `ShelfOutage` (`shelf_outage.py:36`) | período sem oferta por canal (observação, recomputável) | receivers do backstage (`handlers.py:12-25`) | B.I. | **BI** |
| `SeatingSpot` (`seating.py:33`) | lugares do salão (denominador de lotação; vínculo comanda↔mesa vetado) | Admin | B.I. | **BI** |
| `ConsumptionRole`, `ProductConsumptionTag` (`consumption.py:44,82`) | etiquetas de leitura de cesta (consumo local × levar) | Admin/seed | B.I. | **BI** |
| `DayContext` (`day_context.py:35`) | feriado + clima + expediente congelado (contexto externo materializado) | `import_holidays`/`import_weather`/`business_day` | B.I., previsão | **BI** |
| `HistoricalSale`, `HistoricalSaleItem` (`historical_sale.py:19,60`) | histórico externo (Yooga) | `ingest_yooga` | só B.I. | **BI** (ADR-021 §3) |
| `BIView` (`bi_view.py:13`) | cenário salvo do explorador | usuário | B.I. | **SUP** |
| `BlindPrepCode` (`blind_prep.py:18`) | código diário de pesagem cega por receita | produção | produção | **SUP** |

### 2.2 `shopman/storefront/models/`

| Model | O que é | Escreve | Lê | Veredito |
|---|---|---|---|---|
| `CustomerFavorite` (`favorites.py:13`) | coração do cliente por SKU (`customer_ref` string) | storefront | storefront; shop via `adapters/audience_sources.py:16` (audiência) | **SUP** com ressalva (candidato 6, parte fraca) |
| `StockAlertSubscription` (`stock_alerts.py:18`) | "me avise" (voltou ao estoque / saiu do forno) | storefront API; **storefront ouve `Move`/`production_changed` e dispara notificação** (`storefront/handlers.py:20-54`, `services/stock_alerts.py:97-140`) | shop via `audience_sources.py:37,53` (fomo, audiência) | **POL** leve (candidato 6) |

### 2.3 `shopman/shop/models/`

| Model | O que é | Veredito |
|---|---|---|
| `Shop` + proxies (`shop.py:89`, `settings_proxies.py`) | tenant: identidade, marca, `opening_hours`, `defaults`, `integrations` | config do orquestrador, ok |
| `Channel` (`channel.py:16`) | canal + `ChannelConfig` (8 aspectos) | config, ok |
| `RuleConfig` (`rules.py:24`) | regras ativas por contexto | config, ok |
| `NotificationTemplate` (`shop.py:515`), `OmotenashiCopy` (`omotenashi_copy.py:18`) | copy/templates | config, ok |
| `Promotion`, `Coupon` (`promotion.py:23,144`), `DeliveryZone`, `DeliveryDistanceBand` (`delivery.py:8,131`) | preço contextual e geografia de entrega | **POL** por decisão (ADR-019); não flagrar |
| `Campaign`, `Announcement`, `AnnouncementTemplate` (`campaign.py:65-267`) | marketing que anuncia | **POL** (ADR-020); não flagrar |
| `QualityGrade`, `QualityDefect` (`quality.py:21,76`) | catálogos que dão sentido aos refs opacos do craftsman | **POL** (ADR-017); não flagrar |
| `CatalogSyncState` (`catalog_sync.py:25`) | resultado da última projeção SKU×canal externo | estado de integração do orquestrador, ok |
| `UserNotification` (`user_notification.py:26`) | notificação por pessoa, entregue por SSE `user-{id}` | **POL**, ok; é o irmão que `OperatorAlert` deveria ter ao lado (candidato 2) |

### 2.4 `shopman/shop/adapters/`

| Adapter | Alcança | Natureza | Veredito |
|---|---|---|---|
| `payment_efi`, `payment_stripe`, `payment_mock` (`SHOPMAN_PAYMENT_ADAPTERS`, `config/settings.py:971`) | gateways | Protocol real, 3 impls por método | ok |
| `notification_console/email/manychat/sms/whatsapp` (`settings.py:1025`) | provedores | Protocol real, routing por canal | ok |
| `otp_manychat`, `otp_sms_comtele`, `otp_sms_twilio` | provedores OTP | Protocol real | ok |
| `courier_machine`, `courier_mock` (`SHOPMAN_COURIER_ADAPTER`, `settings.py:599`) | Machine | Protocol real, 2 impls | ok (o problema da corrida é o **estado**, §3.5, não o adapter) |
| `fiscal_focusnfe` (`SHOPMAN_FISCAL_ADAPTER`, `settings.py:1034`) | Focus NFe | Protocol do `fiscalman.contracts` (`packages/fiscalman/shopman/fiscalman/contracts.py:1-10`), 1 impl + mock | ok (o problema fiscal é o **estado**, §3.4) |
| `catalog_projection_ifood`, `catalog_projection_meta` | iFood/Meta | Protocol do offerman (`PROJECTION_BACKENDS`, `settings.py:610-621,871`) | ok |
| `catalog`, `stock`, `production`, `customer` (`_DEFAULTS`, `adapters/__init__.py:39-51`) | offerman/stockman/craftsman/guestman | delegação interna a cores (ADR-001 §2 diz que não precisaria de adapter) | ok, indireção legada |
| `pricing` (`OFFERMAN.PRICING_BACKEND`, `settings.py:869`), `catalog_backend`, `inventory`, `demand`, `sku_validator` | preenchem seams que os cores declaram | implementam Protocol de core (buraco declarado pelo core) | ok, forma correta |
| `audience_sources` (`:16,37,53`) | **storefront** | bridge lazy, 1 impl, leitura | ressalva (§3.6); ADR-019 §2 declarou legítimo (`adr-019:102`) |
| `alert` (`:12,34,48,60`) | **backstage** | bridge lazy, 1 impl, **escrita** (create/ack) + `connect_saved` | **smell forte** (§3.2) |
| `kds` (`:10-145`, 13 funções) | **backstage** | bridge lazy, 1 impl, **escrita** (create/cancel/unfire/shift) | **smell forte** (§3.1) |
| `pos` (`:7,20,28`) | **backstage** | bridge lazy, 1 impl, escrita (`upsert_tab`) + leitura de caixa | **REF** (`cash_shift_is_closed`) + §3.7 (`POSTab`) |
| `episodes` (`:24`) | **backstage** | bridge lazy, 1 impl, leitura que degrada a vazio | ressalva leve (§3.8) |
| `_dotted`, `_external`, `_notification_templates`, `_sms`, `payment_types` | helpers | não são adapters | ok |

Fato estrutural: dos 33 módulos, **cinco** apontam para superfície (`alert`, `kds`,
`pos`, `episodes`, `audience_sources`) e **nenhum deles é Protocol**: são
repositórios de uma implementação com import atrasado. Três escrevem.

### 2.5 Famílias de JSON (`docs/reference/data-schemas.md`)

| Família | Onde | Natureza | Veredito |
|---|---|---|---|
| `Order.data.payment.{tenders, cash_received_q, tendered_q, change_q, collection, cash_shift_id}` + `Order.data.pos` (`data-schemas.md:260-268`) | pedido | dinheiro do turno em JSON | **REF** |
| `Order.data.nfce_*` (10 chaves, `data-schemas.md:145-154`) | pedido | máquina de estado de documento fiscal (pending/authorized/denied/cancelled) | **DSC leve** (§3.4) |
| `Order.data.courier` (`data-schemas.md:170-199`; `attempts[]`, `driver`, `estimate`, `status` letra crua) | pedido | estado da corrida com provedor externo | **DSC leve**, casa existe (§3.5) |
| `Order.data.returns[]` (`:270-286`) | pedido | trilha de devolução; o estorno é ledger no `payman` (`handlers/returns.py:113-121`) | contextual, ok |
| `Order.data.{assignment, kitchen_note, cancellation_*, availability_decision, lifecycle, hold_ids, awaiting_wo_refs, loyalty}` | pedido | contexto do pedido; `lifecycle` é marcador durável de fase | contextual, ok |
| `Session.data.{tab_ref, tab_display, pos_operator, last_touched_at, fired_lines}` (`:35-39`) | comanda | estado da comanda no PDV; `fired_lines` é espelho declarado do ledger `KDSTicket` | contextual; ver §3.1 e §3.7 |
| `Session.data.customer_rating` (`:44`) | pedido | avaliação 1:1; Admin calcula média sobre JSON | contextual, ok ("só quando doer": média em SQL) |
| `Shop.defaults.{rules, loyalty, pos, stock_alerts, production, pickup_slots}` (`:753-870`) | tenant | política injetada nos cores por resolvers (`guestman.contrib.loyalty.conf`, `stockman.contrib.alerts.conf`) | política, ok |
| `Channel.config` (8 aspectos) | canal | dataclass `ChannelConfig` | política, ok |
| `Customer.metadata`, `Product.metadata.{fiscal, lead_time_hours}`, `Recipe.meta`, `WorkOrder.meta` (`:908-976`) | cores | extensão sem migração; `WorkOrder.meta.quality`/`batch_*` já **removidas** (ADR-017) porque viraram coluna | ok; o precedente ADR-017 é o teste: quando o meta vira máquina de estado, vira coluna |
| `DayClosing.data.{items, production_summary, cash_shift_summary, reconciliation_errors}` (`:978-1004`) | fechamento | snapshot; `cash_shift_summary` é cache de cache (REF) | ok como snapshot; o **escritor** é o problema (§3.3) |
| `POSTerminal.metadata.hardware`, `POSEvent.payload`, `CashShift.metadata` (`:1006-1114`) | caixa | | **REF** |

---

## 3. Candidatos, ranqueados

### 3.1 KDS: `KDSInstance` + `KDSTicket` (política do orquestrador alojada no backstage)

**Evidência.**
- (a) Os models moram em `shopman/backstage/models/kds.py:8,46`; a ADR-021 §4 os cita como
  "fato operacional de superfície que o backstage já possui" (`adr-021:102-104`).
- (b) Mas **quem escreve é o shop**: `shop/services/kds.py` (573 linhas: `dispatch`,
  `fire_lines`, `unfire_lines`, `cancel_tickets`, `on_all_tickets_done`, `complete_ticket`,
  `reopen_ticket`, `expedition_action`, `:55-523`), chamado do lifecycle
  (`lifecycle.py:710`), do PDV (`services/pos.py:578`), do `refresh_oven` (`:114`) e do
  autopilot (`:170`), tudo por `adapters/kds.py` (13 funções, `:10-145`, incluindo
  `create_ticket`, `cancel_open_tickets`, `unfire_session_lines`, `shift_ticket_completed_at`
  e `get_ticket_model` para o SSE conectar `post_save` no model da superfície,
  `handlers/_sse_emitters.py:195-197`). Onze pontos do shop importam esse adapter.
- **Circularidade em espírito**: `backstage/services/kds.py:6` importa
  `shop.services.kds as kds_core` e delega **tudo** (76 linhas de fachada); o shop então desce
  de volta pelo adapter até o model do backstage. A superfície não é dona de nada além da tabela.
- (d) `Session.data.fired_lines` é "mirror do ledger autoritativo (tickets KDS por
  `session_key`)" (`data-schemas.md:39`): espelho declarado, o mesmo sinal do caixa.
- Roteamento é **cross-domain**: `KDSInstance.collections` é M2M para `offerman.Collection`
  (`kds.py:20`), `_build_routable_items` lê `offerman.ProductComponent`
  (`shop/services/kds.py:292`), o ticket ancora em `orderman` (`session_key`), e a
  liberação depende de pagamento (`shop/services/kds.py:544-558`).

**Forma ideal: `shopman/shop` (models + service), adapter apagado.** Não é pacote:
KDS compõe orderman × offerman × payman × craftsman, e ADR-005 §3 diz onde domínios se
encontram. Um pacote não poderia ter o M2M para `Collection` (teria de virar
`collection_refs` JSON), e o `session_key` já é ref string. É a cura da ADR-019:
"mover o modelo para onde a dependência aponta". Nome fica (`KDSInstance`, `KDSTicket`);
migração `DeleteModel`+`CreateModel` como no precedente da promoção
(`adr-019:88-92`).

**O que move**: os dois models, `adapters/kds.py` (morre; suas 13 funções viram
chamadas diretas de `shop/services/kds.py`), o `connect` do SSE, o `admin` do backstage
para KDS. **O que não move**: `backstage/projections/kds.py` (592 linhas de leitura),
`backstage/api/kds.py`, `backstage/services/kds.py` (a fachada HTTP continua onde a
superfície está), permissão `operate_kds`.

**Risco**: baixo em código (é rename de app_label + migração), médio em ADR: a
ADR-021 §4 usa `KDSTicket` como precedente para `OvenRun` ficar no backstage. O
precedente sobrevive: `OvenRun` **é** escrito só pela superfície; `KDSTicket` nunca foi.
Vale registrar a correção na ADR-021 quando mover.

**Contra-argumento honesto**: funciona há meses; o adapter é feio mas estável, e o teste de
fronteira o permite. Mover é dívida arquitetural, não bug. A razão para pagar agora é
o efeito cumulativo: cada função nova de KDS (unfire, shift de timestamp) nasceu como
mais uma linha no adapter, e o SSE já precisou de `get_ticket_model()` para contornar.
Sem mover, o próximo passo é `POSEvent` para KDS.

### 3.2 `OperatorAlert`: aviso ao operador com dois modelos e a seta ao contrário

**Evidência.**
- (a)+(b) Model em `backstage/models/alerts.py:8`; **13** pontos do shop criam/consultam por
  `adapters/alert.py` (`lifecycle.py:995`, `services/payment.py:774,808`,
  `services/courier.py:401`, `services/pix_confirmation.py:198,255`,
  `services/observability.py:44`, `handlers/confirmation.py:143`,
  `handlers/notification.py:81`, `handlers/stock_alerts.py:35`,
  `handlers/courier_dispatch.py:103`, `handlers/production_alerts.py:10`,
  `handlers/_sse_emitters.py:186`). Dos 21 `TYPE_CHOICES` (`alerts.py:11-33`), 15 nascem
  no lifecycle, pagamento, courier, produção ou directives, todos do orquestrador. O
  adapter até expõe `connect_saved` (`alert.py:53-66`) para o shop ligar `post_save` no
  model da superfície.
- (d) `shop/models/user_notification.py:26` é o modelo irmão ("uma notificação
  endereçada a uma pessoa, não a uma tela", entregue por SSE `user-{id}`), **no shop**.
  "Avisar quem opera" tem dois donos: um por tela (backstage) e um por pessoa (shop).

**Forma ideal: `shopman/shop/models/operator_alert.py`**, ao lado de `UserNotification`;
`adapters/alert.py` morre; `backstage/services/alerts.py` (ack, contagem) importa do
shop, que é a direção legal. Não é pacote: alerta é efeito colateral transversal do
orquestrador. Unificar os dois models numa só notificação com `audience` (tela | pessoa)
é tentador e **fora do escopo** desta auditoria (seria feature); mover é suficiente.

**O que move**: o model, o adapter (morre), admin. **Não move**: API/projections/SSE de
alertas do backstage, permissões. **Risco**: baixíssimo; 21 tipos são strings.
**Contra-argumento**: é o menor dos três; poderia ir de carona no 3.1 num único PR de
"backstage → shop", com uma migração de cada lado.

### 3.3 Fechamento do dia: procedimento do orquestrador escrevendo ledger a partir da superfície

**Evidência.**
- `backstage/services/closing.py:17-19` importa `Quant`, `Move`, `StockMovements` do
  Stockman no topo do módulo e `perform_day_closing` faz `StockMovements.issue(...,
  kind=Move.Kind.WASTE)` (`closing.py:202`) dentro de `select_for_update`. É o **único**
  service de superfície que escreve num ledger do Core (varredura de
  `backstage/services/*` e `backstage/api/*`: `catalog.py` escreve catálogo via
  `CatalogService`, que é edição de cadastro; `production.py:20-21` delega para
  `shop.services.production`; nada mais toca stockman/craftsman/orderman em escrita).
- O procedimento é cross-domain por definição (ADR-011 §5: "consolidar sobras, D-1,
  produção, vendas e `CashShift`s"): lê `WorkOrder` (`closing.py:212,252`), `Order`
  (`:302`), `CashShift` (`:346`), `iter_order_payments` (`:395`), escreve `Move`.
  ADR-005 §3 diz que isso é o framework.
- O gate não vê: `test_backstage_views_do_not_drive_order_lifecycle_directly`
  (`test_import_boundaries.py:199-226`) varre `backstage/views/`, que hoje contém só
  `two_factor.py`; a API vive em `backstage/api/` e os services em
  `backstage/services/`, fora da varredura. `test_framework_does_not_import_protected_kernel_internals`
  (`:152-173`) só barra `models.<sub>`; `from shopman.stockman.models import Move` passa.
- (c) Consequência já sentida: a perda do C4 entrou como `ADJUST` (memória
  `project_c4_writeoff_lands_as_adjust`, corrigida) porque a escrita nasceu longe do
  service que sabe o `kind` certo.

**Forma ideal: `shop/services/closing.py`** com o procedimento (write-off, snapshot,
sumários) e **`DayClosing` em `shop/models/`**; o backstage guarda API, projection
`closing.py` e a tela. Não é pacote: é orquestração, e o snapshot é resultado dela.
Alternativa menor (fica em backstage, mas o write-off passa por
`shop.services.stock.write_off_lots`) resolve a escrita e deixa o resto do
procedimento onde está; é o "menor diff" e não é a forma correta, mas fecha a ferida
enquanto o caixa não vira `cashman` (o `_cash_shift_summary` de `closing.py:343` importa
`CashShift`, e mover para o shop **antes** do cashman recriaria a seta invertida por
`adapters/pos.py`). Portanto: **ordem importa**, cashman primeiro.

**Risco**: médio (o fechamento é o ritual de todo dia; testes de backstage `closing`
existem). **Contra-argumento**: ADR-011 fixou `DayClosing` no backstage e ADR-021 lista
`backstage.DayClosing.data` como fonte do B.I. (`adr-021:35`); mover exige emenda nas
duas. E o backstage já é "leitor cross-suite" declarado (`adr-021:66-68`); o que a
ADR não autoriza é **escrever**.

### 3.4 Documento fiscal: `fiscalman` existe, mas o documento mora em dez chaves de `Order.data`

**Evidência.**
- (c) `handlers/fiscal.py:117-124` grava `nfce_access_key`, `nfce_number`, `nfce_series`,
  `nfce_protocol`, `nfce_xml_url`, `nfce_danfe_url`, `nfce_qrcode_url`, `nfce_status`;
  `:154-155` grava `nfce_cancelled`, `nfce_cancellation_protocol`. O contrato do
  pacote já descreve o agregado inteiro: `FiscalDocumentResult` com `status`
  `pending|authorized|denied|cancelled` (`fiscalman/contracts.py:19-34`).
- Leitores espalhados, cada um reinterpretando o JSON: `shop/services/fiscal.py:68,104,107`
  (idempotência e "pode cancelar"), `backstage/projections/order_queue.py:794-822`
  (status + links), `backstage/services/orders.py:117`, `fiscal_emit.py:86`
  (`data__nfce_access_key__isnull=True` como fila de pendentes), seed (`seed.py:3703-3710`).
- `packages/fiscalman/shopman/fiscalman/` **não tem `models/`** (só `classification.py`,
  `contracts.py`, `contrib/offerman/`): a persona é dona da classificação e do
  contrato, mas não do documento que o contrato produz.
- Gatilhos previstos: DANFE no PDV é obrigação legal (memória
  `project_nfce_printing_required`), S5 = NF-e mod. 55 (`FISCALMAN-PLAN.md:116`),
  contingência/reemissão (`_is_transient`, `handlers/fiscal.py:36`), documento de
  devolução. Cada um adiciona chaves ao pedido ou quebra o 1:1 pedido↔documento.

**Forma ideal: `fiscalman.FiscalDocument`** (`order_ref` string, `kind` 65|55, `status`,
`number/series/access_key/protocol`, URLs, `cancelled_at/cancellation_protocol`,
`provider_ref`), escrito só pelo handler do shop, lido por todos. Não é pacote novo:
é dar ao pacote existente o agregado que o contrato dele já descreve. Precedente:
ADR-017 tirou `WorkOrder.meta.quality` do JSON quando virou coluna com máquina de
estado (`data-schemas.md:960-961`).

**O que move**: as dez chaves (com migração de dados). **Não move**: adapter FocusNFe,
handlers, `Session.data.fiscal` (`{issue_document, tax_id}` é preferência de checkout,
contextual). **Risco**: baixo. **Contra-argumento honesto**: 1:1 hoje, dez chaves,
funciona; e a persona foi desenhada "sem model" de propósito (schema em
`Product.metadata`). Por isso é **"só quando doer"**: o primeiro dos gatilhos acima
(DANFE no PDV é o mais próximo) é a hora. Até lá, o mínimo decente é aninhar em
`Order.data.fiscal_document = {...}` para parar de espalhar prefixo.

### 3.5 Corrida de entrega: `Order.data.courier` ao lado de um `Fulfillment` vazio

**Evidência.**
- (c) `services/courier.py:47-58` grava a corrida inteira em `Order.data["courier"]`
  (`id_mch`, `status` letra crua, `driver`, `tracking_url`, `estimate`, `attempts[]`,
  `error`; `data-schemas.md:170-199`), e o webhook da Machine faz lookup por
  `data__courier__id_mch`.
- (d) `orderman.Fulfillment` já tem `tracking_code`, `tracking_url`, `carrier`, `meta`
  ("metadados de entrega", `packages/orderman/.../models/fulfillment.py:45-52`) e
  lifecycle `pending → in_progress → dispatched → delivered`. O courier **não o toca**
  (nenhum `Fulfillment` em `services/courier.py`); o status é sincronizado por fora em
  `operator_orders._sync_delivery_fulfillment` (`operator_orders.py:444`, chamado em
  `:194,260`). "Onde está a entrega" tem três representações: `Order.status`,
  `Fulfillment.status`, `courier.status`.

**Forma ideal: usar o agregado que existe.** `Fulfillment.carrier="machine"`,
`tracking_url`, `tracking_code=id_mch`, e o resto (`driver`, `estimate`, `attempts`,
`error`) em `Fulfillment.meta`; o lookup do webhook passa a ser por
`Fulfillment.tracking_code`. Não é pacote nem `shop`: é orderman. **Não move**: adapters
`courier_machine`/`courier_mock` (Protocol legítimo, 2 impls), o funil `apply_status`.
**Risco**: baixo-médio (webhook lookup, projection `_courier_block`). **Contra-argumento**:
uma corrida pode ser re-despachada (attempts) e o `Fulfillment` é 1:N por pedido, então
cabe até melhor; mas o ganho hoje é higiene, não bug. **"Só quando doer"**: segundo
provedor de logística, ou relatório de custo de entrega que precise indexar
`estimate.value_q`.

### 3.6 "Me avise" e favoritos: a superfície do cliente orquestra, o shop lê por adapter

**Evidência.**
- (b) `shop/services/fomo.py:141-152` e `services/audience.py:383,400` leem
  `StockAlertSubscription`/`CustomerFavorite` por `adapters/audience_sources.py:16,37,53`,
  com a justificativa escrita "model do storefront e shop não importa superfície".
- O storefront **ouve `stockman.Move` e `production_changed` e envia notificação**
  (`storefront/handlers.py:20-54`, `services/stock_alerts.py:97-140`): é um handler de
  lifecycle cross-core (stockman × craftsman × notificações) vivendo na superfície,
  o papel que `shop/handlers/*` cumprem para tudo o mais.
- (e) ADR-019 §2 declarou explicitamente `audience_sources` legítimo, "dados de superfície
  de cliente, não regra de preço" (`adr-019:102`).

**Forma ideal**: a **assinatura** ("me avise") é intenção do cliente que dispara
notificação: `shop/models` + `shop/handlers/stock_alerts` (que já existe para o lado
do operador, `handlers/stock_alerts.py:1-5`); favoritos ficam no storefront (é
preferência de UI e só é lida para audiência). Não é pacote: nem guestman (o guestman
não sabe de SKU/estoque) nem stockman (o `StockAlert` do stockman é limiar de estoque
por posição, outra coisa, `packages/stockman/.../models/alert.py:18`). **Risco**: baixo.
**Contra-argumento**: ADR-019 já julgou; a leitura por adapter é leitura; e a
notificação sai por `shop.notifications` de qualquer forma. Rank baixo, **"quando doer"**:
segundo canal assinando (PDV "avise o cliente X"), ou quando o `audience` precisar de
mais uma fonte da superfície.

### 3.7 `POSTab`: registro de comanda que a `Session` já resolve

**Evidência.** `POSTab` (`backstage/models/pos.py:9`: `ref`, `label`, `is_active`) é
escrito **só** pelo shop (`services/pos.py:159-164` via `adapters/pos.py:7,20`; o único
leitor de backstage é `omotenashi_qa.py:293`). A comanda de verdade é a
`orderman.Session` com `handle_type/handle_ref` e `UniqueConstraint` para uma aberta por
canal (`session.py:96,147-148`); `Session.data.tab_ref/tab_display/pos_operator`
duplicam o rótulo (`data-schemas.md:35-37`). (d) "Qual é o rótulo desta comanda" mora em
dois lugares.

**Forma ideal**: morrer, ou virar `shop/models` (registro de etiquetas físicas de
comanda é config do PDV, como `Shop.kitchen_note_tags`). Vai de carona no 3.1 ou no
cashman (o `adapters/pos.py` some inteiro quando `cash_shift_is_closed` for
`cashman` e `upsert_tab` for shop). **Risco**: mínimo. Não merece PR próprio.

### 3.8 Ressalva sem candidatura: `adapters/episodes.py`

`shop/services/production.py:74` lê `disrupted_days` do backstage por
`adapters/episodes.py:24`, com try/except que degrada a vazio. É leitura de B.I. para
a fórmula (ADR-021 territory), o docstring do adapter é honesto sobre a exceção
(`episodes.py:1-11`), e o episódio é escrito só pela superfície. **Fica.** Se um dia a
fórmula precisar de mais três leituras do backstage (clima de `DayContext`, outage
de `ShelfOutage`), aí a forma certa é o craftsman declarar um seam
(`DEMAND_BACKEND` já é o lugar: `adapters/demand.py:8-11` mostra a composição correta,
no shop, sem tocar superfície) e não mais adapters de leitura.

### 3.9 NÃO candidatos (parecem domínio, estão no lugar)

| O quê | Por que fica |
|---|---|
| Modelos de B.I. (`OvenRun`, `ShelfOutage`, `SeatingSpot`, `ConsumptionRole/Tag`, `DayContext`, `HistoricalSale*`, `BIView`) | ADR-021 §2/§4: leitura cross-suite mora no backstage, "não existe pacote shopman-bi" (`adr-021:157`); todos escritos pela superfície ou por import de arquivo, lidos só pelo B.I. |
| Checklists de operação (`Operation*`) | autocontido no backstage: model, service, API, sem leitor/escritor externo; é rotina da casa, não domínio da suite |
| `Promotion`, `Coupon`, `DeliveryZone`, `DeliveryDistanceBand` | ADR-019: política composta sobre cores, dono é o orquestrador |
| `Campaign`, `Announcement*` | ADR-020 |
| `QualityGrade`, `QualityDefect` | ADR-017: catálogo que dá sentido a refs opacos do craftsman |
| `CatalogSyncState` | estado de integração de projeção externa; saiu de JSON (`Listing.projection_metadata`) para tabela no lugar certo (orquestrador integra) |
| Fidelidade | `guestman.contrib.loyalty` + resolvers injetados por `shop/apps.py`; `Shop.defaults.loyalty` é política (`data-schemas.md:798-806`); `Order.data.loyalty` é contextual |
| Devoluções (`Order.data.returns[]`) | o dinheiro é `PaymentTransaction` no payman (`handlers/returns.py:113-121`); o JSON é trilha; sem segundo leitor |
| Operador/PIN/badge | credencial é `doorman.PinCredential`; `backstage/services/operator.py:1-12` é política fina de superfície |
| `Shop`, `Channel`, `RuleConfig`, `NotificationTemplate`, `OmotenashiCopy`, `UserNotification` | config/política do orquestrador por concepção |
| Horário/calendário (`Shop.opening_hours`, `business_calendar.py`, `BusinessHoursRule`) | um dono (shop); `backstage/services/business_day.py` só congela o expediente praticado no `DayContext` (B.I.) |
| `Fulfillment` | já é core (orderman); o problema é não ser usado (§3.5) |
| `AccountingBackend` (`orderman/protocols.py:92`, `SHOPMAN_ACCOUNTING_BACKEND=None`) | seam dormente sem implementação; não é domínio escondido, é código morto de contrato; fora do escopo |
| Adapters internos `catalog`/`stock`/`production`/`customer` | indireção sem Protocol real (ADR-001 §2 já diz que o framework importa cores direto); dívida cosmética, não fronteira |

---

## 4. Recomendação

**Ordem** (dependências reais, não gosto):

1. **`cashman` primeiro** (referência). Ele apaga `adapters/pos.py::cash_shift_is_closed`
   e destrava o 3.3 (o `_cash_shift_summary` do fechamento passa a importar pacote).
2. **PR "backstage → shop" (3.1 KDS + 3.2 OperatorAlert + 3.7 POSTab)**: dois models
   grandes e um pequeno mudam de app_label, três adapters morrem (`kds`, `alert`, `pos`),
   o backstage passa a importar do shop (direção legal), zero mudança de contrato de API.
   É o mesmo movimento da ADR-019 e cabe numa ADR curta ("fato escrito pelo orquestrador
   mora no orquestrador"), com emenda de uma linha na ADR-021 §4 (o precedente para
   `OvenRun` continua válido pelo critério do escritor). **Urgente? Não é bug; é a
   próxima linha do adapter que vai doer.** Fazer antes de qualquer feature nova de KDS
   (troca de estação, prioridade, tempo por ticket): cada uma hoje nasce como função
   nova no adapter.
3. **3.3 fechamento**: `perform_day_closing` (write-off + snapshot) para
   `shop/services/closing.py`, `DayClosing` para `shop/models`, backstage guarda API,
   projection e tela. Depois do cashman. **Ao mesmo tempo, fechar o buraco do gate**:
   `test_backstage_views_do_not_drive_order_lifecycle_directly` deve varrer
   `backstage/api/` e `backstage/services/` (hoje varre um diretório com um arquivo), e
   uma regra nova deve barrar `stockman.services.*`/`StockMovements` em qualquer
   superfície. Sem o teste, o próximo write-off nasce no mesmo lugar.
4. **Só quando doer**: 3.4 fiscal (gatilho: DANFE no PDV, S5, contingência), 3.5
   corrida (gatilho: segundo provedor ou custo de entrega indexado), 3.6 "me avise"
   (gatilho: assinatura vinda de outra superfície). Nenhum dos três é pacote novo: são
   "use o agregado que existe" (fiscalman, orderman) ou "suba para o shop".
5. **Nunca**: pacote de B.I., pacote de KDS, pacote de alerta, pacote de fechamento.
   Nenhum tem invariante próprio que os cores não tenham, e todos são composição.

**Critério para o futuro** (para não repetir a auditoria): um `shop/adapters/<x>.py`
que aponta para `shopman.backstage`/`shopman.storefront` e não é Protocol com
2+ implementações em settings **é candidato automático**; e um `backstage/services/*`
que importe `*.services.*` de escrita de um core é violação, mesmo passando no gate.
Vale acrescentar os dois como testes de invariante junto do 3.3, para que o gate
falhe em vez de a auditoria descobrir.
