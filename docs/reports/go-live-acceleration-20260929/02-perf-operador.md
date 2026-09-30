# 02 — Performance dos apps de OPERADOR (PDV, Gestor, KDS, Produção, Marketing, Hub, Compras)

> Árvore canônica: `.dsh-worktrees/go-live-acceleration` — `origin/main` = `f0ffd02fd` (2026-09-29).
> Escopo: superfícies de operador. Storefront fora.
> Legenda: **[FATO]** = verificado no código citado ou em saída de comando · **[INFERÊNCIA]** = dedução a partir dos fatos citados · **[NÃO VERIFICADO]** = procurei e não confirmei.

---

## 1. Resumo executivo

1. **[FATO] O KDS é o app mais caro por requisição, e o único que paga poll + SSE no mesmo dado.** `build_kds_board` custa **5 + N** queries (N = tickets ativos): medido **65 queries com 60 tickets** na estação de preparo e **125 com 40 tickets** na de separação. A tela refaz esse board **a cada 15 s, sem condição** (`useKdsBoard.ts:266`) **e** a cada evento SSE (`:228,:235`) — carga dobrada confirmada.
2. **[FATO] A causa raiz do KDS é uma resolução de fonte por ticket.** `build_kds_board` monta `sources` com `_resolve_ticket_source(ticket)` **dentro de um dict comprehension** (`kds.py:314`), e cada chamada faz `Order.objects.filter(session_key=…)` (`kds.py:848-852`). Foram **61 das 65 queries** medidas.
3. **[FATO] A Produção tem o pior N+1 do Django, e ele é multiplicado pelo número de fichas, não de pedidos.** `build_production_board` chama o motor de sugestão (`production.py:1189`), que itera **todas as fichas ativas** (`craftsman/services/queries.py:243`) e faz **2 queries por ficha** (`contrib/demand/backend.py:63 e :85`). Medido: **91 queries com 40 fichas (80 delas do motor de sugestão)**. A Produção é também a única superfície de operador **sem SSE** e com **9 pollers**.
4. **[FATO] A query de demanda filtra `OrderItem.sku`, que não tem índice** (`orderman/models/order.py:372`, `db_index=False`; `Meta` só tem constraints). Isso explica, mecanicamente, os *"13.055 seq scans/dia em `orderman_orderitem`"* do `WP-PERFORMANCE-2026-09.md:78`.
5. **[FATO] Índices ausentes no caminho de leitura do operador:** `Order.data` (JSON, sem GIN) é filtrado em 14 pontos, incluindo a query principal da fila do Gestor a cada 30 s (`order_queue.py:1233`); `KDSTicket.status`/`completed_at`/`cancelled_at` não têm índice nem `Meta.indexes` (`backstage/models/kds.py:141-148`).
6. **[FATO] O Gestor de Pedidos é o pior cliente do backstage.** A home monta **4 streams SSE + 5 timers de rede** sobre a mesma fila, e 4 dos 5 timers **não desligam quando o SSE está vivo**. O PDV é o único app que faz isso certo (`shouldPollTick`, `presentation/events.ts:14-16`).
7. **[FATO] O que já está bom e não deve ser mexido:** `build_two_zone_queue` (8–11 queries, constante de 5 a 60 pedidos), `build_order_queue` (8, constante), o board público de retirada (2 queries), `build_production_kds` (3) e `marketing_v2.build_board` (2).
8. **[FATO] Nenhum `select_for_update` em fluxo de leitura.** As 37 ocorrências em `shopman/backstage/` estão todas em serviços de escrita, comandos e `pos_concurrency` (guarda de mutação de comanda). `projections/` não contém nenhum.
9. **[INFERÊNCIA, alta] Não há desenho de offline nos apps de operador.** PWA com precache do casco (`operator-kit/pwa.config.ts:255-299`), navegação **NetworkOnly** com `offline.html`, e **zero outbox** — offline é degradação, não modo offline.
10. **[FATO] Dois canais SSE são publicados sem nenhum consumidor** (`stock-<ref>`, `fomo-*`) **e a Produção não tem rota SSE** — custo por evento pago, latência ganha zero.

---

## 2. Como foi medido

**Contagem de queries (medida própria, reprodutível).** Banco sqlite em memória criado por `connection.creation.create_test_db()`, queries capturadas por `django.test.utils.CaptureQueriesContext`. Sem `.venv` na worktree, o interpretador é o da raiz (`/Users/…/django-shopman/.venv/bin/python`) com `sys.meta_path` limpo dos finders `__editable__*` e as pastas `packages/*` da worktree à frente do `sys.path` — sem esse passo os pacotes resolvem para a árvore principal (outro branch) e a medição mede o código errado.

```
[kds_board] tickets=5 queries=10 / tickets=25 queries=30 / tickets=60 queries=65
[kds_index] 3 instâncias, 60 tickets → 76
[picking_board] tickets=10 queries=35 / tickets=40 queries=125
[expedition_board] ready=10 queries=13 / ready=40 queries=43
[pickup_board] n=10 e n=40 → 2 (constante)
[two_zone_queue] n=5/25/60 → 11/10/11   [order_queue] n=5/25/60 → 8/8/8
[build_pos] sem Shop no banco → 28 (14× shop_shop) | com Shop → 11
[build_pos_tabs] 3   [build_pos_shift_summary] 4
[build_production_board] 40 WOs → 91  (80 do motor de sugestão)
[build_production_dashboard] 40 WOs → 44 (40 de _started_qty)
[build_qc_kiosk] 7   [build_production_kds] 3   [marketing_v2.build_board] 2
```

**Onde veio o N+1.** Rastreado com `connection.execute_wrapper` capturando `traceback.extract_stack()` para cada SQL — os pares `arquivo:linha:função` do relatório são a saída desse rastreio, não leitura de olho.

**Inventário de front (polling, SSE, boot/PWA).** Duas investigações delegadas de leitura, na mesma árvore, com a mesma regra de evidência `path:line`. Re-verifiquei pessoalmente as linhas que sustentam os vereditos: `useKdsBoard.ts:266`, `useKdsCustomerBoard.ts:50`, `useOrdersBoard.ts:420`, `usePosEvents.ts:104-106` e `presentation/events.ts:14-16`.

**O que NÃO foi medido:** latência real (nenhum request foi servido), tempo de boot dos Nuxt, custo por conexão SSE, e o custo em produção dos builders que dependem de dados que não consegui semear (Marketing legacy, Compras, Alertas, Notificações). Ver §6.

---

## 3. Achados

### 3.1 KDS — 3 causas concretas, todas medidas

**A1. N+1 de resolução de fonte: 1 query por ticket, no caminho quente.**
- **O que é:** `build_kds_board` monta `sources = {ticket.pk: _resolve_ticket_source(ticket) for ticket in all_rows}` — [FATO] `shopman/backstage/projections/kds.py:314`. Cada `_resolve_ticket_source` faz `Order.objects.filter(session_key=…).order_by("-id").first()` e, se não achar, uma segunda query em `Session` — [FATO] `kds.py:848-859`.
- **Evidência medida:** 60 tickets → 65 queries; **61** delas são o mesmo `SELECT … FROM orderman_order WHERE session_key = …`. 5 tickets → 10; 25 → 30 (base 5 + N).
- **Impacto:** o board é buscado a cada 15 s por estação e a cada evento SSE. Com 3 estações e 40 tickets cada, são ~120 queries por rodada de poll, ~8 rodadas/min.
- **Confiança:** alta (medida + leitura).

**A2. Separação (`picking`): +2 queries de estoque por ticket.**
- **O que é:** `_build_ticket` chama `_add_stock_warnings(raw_items)` **dentro do laço de tickets** — [FATO] `kds.py:917-918`; a função agrega `Quant` e lê `StockAlert` **para os SKUs de um ticket só** — [FATO] `kds.py:1090-1100`.
- **Evidência medida:** 10 tickets → 35 queries; 40 → 125 (3 por ticket: 1 fonte + 2 estoque).
- **Impacto:** a estação de separação é a mais cara do KDS. Um `Quant.objects.filter(sku__in=…).annotate(Sum)` único para a união de SKUs da tela resolveria.
- **Confiança:** alta.

**A3. Saída (`expedition`): 1 query de itens por pedido pronto.**
- **O que é:** `_build_expedition_card` chama `order_composition.effective_items(order)` — [FATO] `kds.py:1030` — que cai em `original_items(order) → order.items.all()` quando não há ajuste — [FATO] `shopman/shop/services/order_composition.py:144-154`. O queryset do board **não** faz `prefetch_related("items")` — [FATO] `kds.py:627`.
- **Evidência medida:** 10 prontos → 13 queries (10× `orderman_orderitem`); 40 → 43.
- **Impacto:** a Saída é a tela que decide o despacho; cada pedido pronto na fila custa uma ida ao banco.
- **Confiança:** alta.

**A4. Seletor de estações: o índice soma os boards.**
- **O que é:** `build_kds_index` chama `build_kds_board(inst.ref)` **para cada instância ativa** — [FATO] `kds.py:249-253`.
- **Evidência medida:** 3 instâncias com 60 tickets em uma → 76 queries.
- **Impacto:** [FATO] o endpoint `GET /api/v1/backstage/kds/` só é chamado em `kds-nuxt/app/pages/index.vue:6` (a tela de escolha de estação), **não é pollado**. É custo de abertura de tela, não de regime — por isso o impacto é menor do que parecia.
- **Confiança:** alta.

**A5. Índices ausentes em `KDSTicket`.** [FATO] `backstage/models/kds.py:141-148`: `Meta` só tem `ordering` e `permissions` — sem `indexes`. `status` não tem `db_index` (só `session_key`, `:109`). As queries `status="done", completed_at__gte=…` (`kds.py:304-311`) e `status__in=ACTIVE, exclude(kds_instance__type="expedition")` (`kds.py:683-686`) não têm índice de apoio. [NÃO VERIFICADO] volume da tabela em produção e se existe rotina de expurgo — procurei `KDSTicket…delete` e `KDSTicket` em `data_retention.py` e **não encontrei nada**.

### 3.2 Produção — o N+1 mais caro do sistema

**B1. Motor de sugestão: 2 queries por ficha ativa, em TODA carga do board.**
- **O que é:** `build_production_board` → `_production_suggestions(selected_date)` — [FATO] `production.py:1189` e `:2975-2982` → `shop/services/production.py:32 suggest_for` → `craftsman` → **`for recipe in recipes:` sobre `Recipe.objects.filter(is_active=True)`** — [FATO] `packages/craftsman/shopman/craftsman/services/queries.py:242-249`. Cada iteração chama `backend.history()`, que roda **duas** queries: o agregado de `OrderItem` (`contrib/demand/backend.py:63-80`) e o agregado de `WorkOrderItem` de waste (`:85-110`); com `LedgerAwareDemandBackend` há ainda `_soldout_times` por SKU — [FATO] `shopman/shop/adapters/demand.py:43-48`.
- **Evidência medida:** 40 fichas ativas → **91 queries**, das quais **80** vêm do par `backend.py:98:history` ← `demand.py:43:history` (rastreio de pilha).
- **Impacto:** [FATO] a Produção polla o board a cada 60 s (`useProductionBoard.ts:64`). Com ~100 fichas ativas, são ~200 queries e ~100 varreduras completas por tela por minuto. **Não há cache em nenhum ponto do caminho** [FATO: `grep cache` em `craftsman/services/queries.py` só acha `_prefetched_objects_cache`].
- **Confiança:** alta no mecanismo; o número de fichas ativas em produção é [NÃO VERIFICADO].

**B2. A query de demanda não usa índice — e é a origem dos seq scans do `orderman_orderitem`.**
- **O que é:** `history()` filtra `OrderItem.objects.filter(sku=product_ref, order__status__in=…, order__created_at__date__gte=…)` — [FATO] `contrib/demand/backend.py:63-80`. `OrderItem.sku` é `RefField(..., db_index=False)` — [FATO] `packages/orderman/shopman/orderman/models/order.py:372` — e o `Meta` de `OrderItem` só declara constraints, **nenhum `indexes`** — [FATO] `order.py:384-405`. O `order__created_at__date` também impede uso do `ord_order_created_at_idx` (o próprio comentário admite: `order.py:126-129`).
- **Impacto:** varredura completa de `orderman_orderitem` **por ficha ativa, por carga de board**. É o mecanismo por trás de *"orderman_orderitem (12.406): seq scans 173.627 … 13.055/dia"* — [FATO] `docs/plans/WP-PERFORMANCE-2026-09.md:78`.
- **Confiança:** alta (leitura + correlação com a medição publicada).

**B3. `_started_qty` no dashboard: 1 query por ordem de produção.**
- **O que é:** `craft.summary()` itera as WOs e chama `_started_qty(order)` — [FATO] `packages/craftsman/shopman/craftsman/services/queries.py:420`; a função tenta o prefetch e, quando o cache de `events` está vazio, dispara `order.events.filter(kind="started")…first()` — [FATO] `queries.py:536-543`. O chamador `build_production_dashboard` carrega as WOs **sem `prefetch_related("events")`** — [FATO] `production.py:1785` (o board, esse sim, prefetcha em `:1164`).
- **Evidência medida:** 40 WOs → 44 queries, **41** de `crafting_work_order_event`; rastreio: `queries.py:538:_started_qty` ← `queries.py:420:summary`.
- **Confiança:** alta.

**B4. O board de produção lê o catálogo de fichas inteiro para decidir o que é produto vendável.**
- [FATO] `production.py:1175` carrega `Recipe.objects.filter(is_active=True)` com `prefetch_related("items")`, e `:1184-1186` roda `RecipeItem.objects.filter(recipe__is_active=True).exclude(input_sku="").values_list("input_sku")` — uma varredura de `crafting_recipe_item` por request para calcular `consumed_recipe_skus`. Medido: 4 queries de `crafting_recipe_item` (mas as linhas varridas crescem com o catálogo). [INFERÊNCIA] candidato natural a cache de processo com invalidação por signal.

### 3.3 Gestor de Pedidos (orders-nuxt)

**C1. Polling + SSE em cima do mesmo dado, sem gate.** [FATO] `orders-nuxt/app/composables/useOrdersBoard.ts:420` — `setInterval(() => refresh(), 30_000)` incondicional, com o `EventSource` de `/sse/orders` montado em `:385-391` refazendo o mesmo `refresh()`. Diferente do PDV, **não há `shouldPollTick`**. O comentário em `:163-164` reconhece que o poll é estado degradado; o código não o desliga.
**C2. Cinco timers de rede na mesma home.** [FATO] `useOrdersBoard` 30 s, `useBackstageEvents` 30 s (5 consumidores, `useBackstageEvents.ts:35`), `useAlerts` 60 s (`useAlerts.ts:46`), `useChannelAttention` 60 s (`useChannelAttention.ts:20`) **que ainda monta o `useBackstageEvents` (`:16`) — dois pollers sobre a mesma função** — e `useIFoodStore` 60 s (`useIFoodStore.ts:19`).
**C3. A fila do Gestor usa a melhor estrutura e ainda assim carrega tudo.** [FATO] `build_two_zone_queue` (`order_queue.py:1223`) é bem feito: uma query de pedidos, uma de itens em lote (`:1244`), leituras bateladas (`waitlist`, `payment`, `danfe`, `channel_configs`, `cash_settlement`, `fiscal_states`). **Medido: 11/10/11 queries para 5/25/60 pedidos — constante.** O problema não é N+1, é que `ACTIVE_STATUSES` inclui `"delivered"` (`order_queue.py:50`) e a query **não tem janela de data** (`:1230-1236`): ela varre e materializa todos os pedidos não-terminais desde sempre. [INFERÊNCIA, alta] mitigado por `_complete_after_handoff` (`shop/lifecycle.py:708-715`), que move DELIVERED → COMPLETED na fase `on_delivered`; se essa fase falhar, o pedido fica na fila para sempre.
**C4. JSON sem índice na query principal da fila.** [FATO] `order_queue.py:1233`: `Q(status__in=ACTIVE_STATUSES) | Q(channel_ref="ifood", data__ifood__handshake_pending=True)`. Não há GIN em `Order.data` — [FATO] o único `GinIndex` do repositório está em `guestman/contrib/insights` (migração `0004_customerinsight_audience_indexes.py`). O `OR` com JSON costuma derrubar o plano para seq scan em `orderman_order`.
**C5. Poll + SSE no detalhe do pedido.** [FATO] `useOrderEvents` (`useOrderEvents.ts:4`) monta o mesmo `useBackstageEvents` no detalhe, sobre o mesmo dado do board.

### 3.4 PDV (pos-nuxt) — o app que acerta o desenho, com um excesso

**D1. [FATO] Só o PDV suprime o poll quando o SSE está vivo.** `shouldPollTick(state) => state !== "live"` — `pos-nuxt/app/presentation/events.ts:14-16`, usado em `usePosEvents.ts:104-106` (`pollMs` default 60 s). É o padrão que o ADR-016 pede e que o KDS e o Gestor não seguem.
**D2. [FATO] `build_pos` custa 11 queries com Shop cadastrado.** Medido: 28 com a tabela `shop_shop` vazia (14× `shop_shop`), 11 com o Shop presente. A diferença **não é um gargalo**: `Shop.load()` cacheia por 60 s (`shop/models/shop.py:485-491`), mas **só cacheia quando encontra a linha** (`if shop is not None`), e cada um dos 12 helpers do PDV chama `load()` sem memoização de request (rastreio: `shop.py:488:load` ← `channel_policy.py:146`, `config.py:434`, `cart.py:638`, `weighed_sale.py:66`, `business_calendar.py:452`, `fulfillment_window.py:119`, `pos_hardware.py:294`, `integration_readiness.py:664`, `pos.py:3123`, `pos.py:2189`, `pos.py:2200`, `shop/models/shop.py:75`). [INFERÊNCIA, média] em produção isso é 1 query por request em vez de 1 por processo — barato, mas é o mesmo padrão que o `WP-PERFORMANCE` suspeita nos 100 mil scans/dia de `shop_channel` (`:80`, gargalo 8).
**D3. [FATO] `_load_products` carrega o catálogo inteiro do canal do PDV, sem paginação** — `pos.py:1051-1067` (com `Prefetch` da coleção primária, bem feito em `:1046`/`:1059-1065`). [INFERÊNCIA, alta] com 111 produtos (`WP-PERFORMANCE-2026-09.md:81`) é aceitável; o crescimento é linear e sem teto.
**D4. [FATO] Poll de PIX/entrega a 2,5 s, fora do gate de SSE.** `usePosSale.ts:425-443` (entrega) e `:457-459` (PIX), `setInterval` de 2 500 ms, sem checar `realtime`. Bounded (24 tentativas / 240 tentativas ≈ 10 min) e o `/pos/payment/<ref>/status/` é barato. **Carga dobrada parcial**: a Projection do terminal já carrega o estado do pagamento, e o poll sonda o mesmo dado. [INFERÊNCIA, alta].
**D5. [FATO] `useDrawerLock` polla a 400 ms** (`useDrawerLock.ts:154-165`, `CLOSE_POLL_MS` em `:23`) — só com o diálogo aberto e contra o agente local, não o Django. Sem impacto no backstage.

### 3.5 Marketing

**E1. [FATO] Dois fetches por tick.** `useCampaignBoard.ts:113-115`: `refresh()` roda `refreshLegacy()` **e** `refreshCanonical()` em paralelo, a cada 60 s (`POLL_MS` em `:17`, timer em `:119`), **sem SSE**. Medido: `marketing_v2.build_board` sozinho custa 2 queries (barato); o custo é o dobro de requisições + o do board legado (`backstage/projections/marketing.py`, 1 015 linhas) que não medi.
**E2. [FATO] Poll + SSE na caixa de notificações.** `useMarketingNotificationInbox.ts:70` (60 s) com `EventSource` em `:48` sobre `/api/v1/backstage/notifications/v2/?limit=100` (`:19-26`) — sem gate.
**E3. [FATO] Não há pausa em aba oculta** no board nem na inbox (`useCampaignBoard.ts` e `useMarketingNotificationInbox.ts` só reagem na volta).

### 3.6 Hub

**F1. [FATO] O Hub não faz polling nem SSE** — `grep setInterval|setTimeout` nos fontes do app: 0 resultados. É uma tela de tiles; o custo é 1 SSR bloqueante (`app.vue:26` → `useOperatorHub.ts:12-15`, `useFetch server: true`). `build_operator_hub` não foi medido (exige `user` com `has_perm`); o módulo tem 146 linhas e resolve URLs de superfície — [INFERÊNCIA, média] custo baixo.

### 3.7 Compras

**G1. [NÃO VERIFICADO] Não medi o board de Compras.** `shopman/backstage/projections/purchase.py` tem 912 linhas e não expõe um `build_purchase_board` (o nome que tentei não existe). O que encontrei por leitura: **[`purchase.py:375`] um laço com 7 chamadas ORM no corpo** e **`purchase.py:550` `metadata__converted_via__approximate=True`** — JSON sem índice. Fica como dívida de medição (§6).

### 3.8 Transversais

**H1. `Order.data` filtrado em 14 pontos da leitura de operador, sem GIN.** [FATO] `kds.py:318`, `kds.py:356`, `kds.py:538` (`delivery_date`); `pos.py:849` (`data__has_key="tab_ref"`); `closing.py:396`; `dashboard.py:164` (`data__customer_rating__rating__gte`); `order_queue.py:1233`; `preorders.py:390 e :402`; `customers.py:325, :457, :477`. `has_key` e `__gte` sobre JSON sem `GinIndex` = varredura completa de `orderman_order`.
**H2. [FATO] Carga dobrada de SSE + poll.** Canais que **não** suprimem o poll quando o stream está vivo: KDS board (15 s), KDS pickup (10 s), Gestor board (30 s), `useBackstageEvents` (30 s ×5), alertas do Gestor (60 s), `useChannelAttention` (60 s + 30 s), notificações (60 s, kit), inbox do Marketing (60 s). Só o PDV suprime.
**H3. [FATO] Bloqueios: nenhum `select_for_update` em leitura.** As ocorrências em `shopman/backstage/` estão em `services/`, `management/commands/` e `api/pos_concurrency.py:41` (guarda de mutação de comanda dentro de `transaction.atomic()`, que segura o lock durante o corpo da view — a view é um save/fire de comanda, curto). `projections/` e as views GET não travam linha. [NÃO VERIFICADO] duração real dessas transações sob carga; a única transação de leitura longa que apareceu é o `select_for_update` no contador do eventstream (`django_eventstream/models.py:37-58`), um por evento de canal reliable.
**H4. [FATO] Nenhum endpoint de projeção do backstage serve cache HTTP.** O único `ETag` está no Marketing v2 (`marketing_v2_http.py:159-165`); `operations.py:2014` usa `private, no-store`. Não há `cache_page` nem `never_cache` nos endpoints de projeção.
**H5. [FATO] PWA/offline não atrasa o boot, mas também não protege a operação.** `generateSW` com precache do casco e navegação `NetworkOnly` + `offline.html` (`operator-kit/pwa.config.ts:255-299`); atualização em `prompt` com sonda de 30 min (`usePwaAutoUpdate.ts:160`, `pwaRuntime.ts:11`). Não existe outbox/fila de escrita em nenhum app de operador. [INFERÊNCIA, alta] o que `offline.html` entrega é degradação explícita ("os dados da operação não são guardados neste dispositivo").
**H6. [FATO] O boot de conteúdo espera o Django em 4 apps.** `await` de `useFetch` com `server: true`: hub (`app.vue:26`), PDV (`PosOperatorShell.vue:17`), e a sessão do operador em todos (`useOperatorLock.ts:38-47`). Não há middleware global de rota com fetch (`defineNuxtRouteMiddleware` = 0 resultados nos 6 apps). [INFERÊNCIA, média] cada um é ~1 RTT ao Django no caminho crítico do SSR — e o BFF chama o Django **pela URL pública**, com hairpin pela Cloudflare (`WP-PERFORMANCE-2026-09.md:154-155`).

---

## 4. O que já existe e funciona (não reinventar)

| Item | Evidência | Por que importa |
|---|---|---|
| **Gate de poll pelo SSE no PDV** | `pos-nuxt/app/presentation/events.ts:14-16`, `usePosEvents.ts:104-106` | é o padrão pronto a copiar para KDS/Gestor/Marketing |
| **Política de poll adaptativo da Produção** | `production-nuxt/app/composables/useAdaptivePoll.ts:15-28` (backoff 2^n até 8×, jitter 0–20%, piso 5 s, não busca em aba oculta) | o melhor poller do monorepo; o KDS e o Gestor não o usam |
| **Fila do Gestor em lote** | `order_queue.py:1223-1343` | 11/10/11 queries de 5 a 60 pedidos — a referência de como fazer |
| **Board público de retirada** | `kds.py:509-592` | 2 queries constantes, mesmo com 40 pedidos |
| **KDS de produção e QC kiosk** | `production.py:1827`, `:1862` | 3 e 7 queries |
| **Priming explícito no board de produção** | `production.py:1190-1191` → `_prime_order_commitments` (`:2461`), `_prime_base_recipe_usages` (`:2494`) | o padrão correto já existe no arquivo; falta aplicar ao Laço A1 do KDS |
| **ETag + cache-control no Marketing v2** | `marketing_v2_http.py:159-165` | único endpoint de projeção com validação condicional |
| **PWA com precache do casco e `offline.html`** | `operator-kit/pwa.config.ts:255-299` | boot offline do shell funciona |
| **`Shop.load()` com cache de 60 s** | `shop/models/shop.py:485-491` | singleton já cacheado — só não é memoizado por request |
| **ADR-016** | `docs/decisions/adr-016-sse-first-realtime.md` | a regra "SSE é push sobre fetch canônico, poll só como fallback calmo" já está escrita — o que falta é *aplicá-la* |

---

## 5. Lacunas e riscos

1. **[FATO] Publicadores SSE sem consumidor:** `stock-<ref>`, `fomo-<sku>`/`fomo-catalog` e `backstage-production-*` são emitidos e nenhum BFF assina (a Produção não tem rota `/sse/*`). Custo por evento pago, latência ganha zero.
2. **[FATO] `ADR-016` desatualizada:** o canal `wa-verify-<token>` (`:43`, `:57`) foi removido (`docs/plans/ACCESS-LINK-UNIFICATION-PLAN.md:136`).
3. **[FATO] Sem limite de conexões SSE por usuário/canal** e sem rate limit no `eventstream_view` — não há contador de listeners em `shopman/shop/eventstream.py`, `backstage/urls.py` nem no pacote.
4. **[INFERÊNCIA, alta] Um único thread de execução síncrona por processo.** `views.stream` usa `sync_to_async(..., thread_sensitive=True)` (`django_eventstream/views.py:155`), que no asgiref roda em `ThreadPoolExecutor(max_workers=1)`; o `web` é **1 instância daphne** (`WP-PERFORMANCE-2026-09.md:103-104`). Toda leitura de banco de qualquer conexão SSE serializa com todas as outras requisições. O sintoma é latência somada, não worker esgotado — mas é o risco a acompanhar quando o número de telas crescer.
5. **[FATO] Nenhuma observabilidade de query.** `pg_stat_statements` não instalado e `log_min_duration_statement = -1` (`WP-PERFORMANCE-2026-09.md:83-84`). Sem isso, todo número deste relatório é contagem estática/medida em sqlite; a distribuição real continua invisível.
6. **[INFERÊNCIA, alta] A Produção é o app com maior risco de degradação silenciosa:** pior N+1, sem SSE, 9 pollers, e o custo escala com o catálogo de fichas — não com o movimento da loja.
7. **[NÃO VERIFICADO] Volume real das tabelas em produção** (`KDSTicket`, `Recipe` ativas, `OrderItem`), que é o multiplicador de tudo aqui.

---

## 6. Recomendações, por impacto ÷ esforço

| # | Ação | Onde | Impacto | Esforço |
|---|---|---|---|---|
| R1 | **Gate de SSE em `useKdsBoard` e `useKdsCustomerBoard`** — copiar `shouldPollTick` do PDV | `kds-nuxt/app/composables/useKdsBoard.ts:266`, `useKdsCustomerBoard.ts:50` | alto (corta ~metade das chamadas do KDS com stream vivo) | XS |
| R2 | **Gate de SSE em `useOrdersBoard`, `useBackstageEvents`, `useAlerts`, `useChannelAttention`, `useNotifications`, `useMarketingNotificationInbox`** | `orders-nuxt/`, `marketing-nuxt/`, `operator-kit/` | alto (a home do Gestor tem 5 timers + 4 streams) | S |
| R3 | **Resolver as fontes do KDS em lote** — uma query `Order.objects.filter(session_key__in=…)` + uma `Session.objects.filter(session_key__in=…, state="open")`, com `prefetch_related("items")` para a Saída | `projections/kds.py:314` e `:627` | alto (65 → ~6 queries no board de 60 tickets) | S |
| R4 | **Cachear o motor de sugestão da Produção** (chave = `target_date` + revisão do catálogo de fichas; invalidar por signal de `Recipe`/`WorkOrder`) | `shop/services/production.py:32`, `craftsman/services/queries.py:243` | alto (remove 2×N queries por poll de 60 s) | M |
| R5 | **Índice em `OrderItem.sku`** (e trocar `order__created_at__date` por `__range`) | `orderman/models/order.py:372` + migração do Core | alto (mata os ~13 mil seq scans/dia) | S |
| R6 | **`prefetch_related("events")` em `build_production_dashboard`** | `production.py:1785` | médio (44 → ~5) | XS |
| R7 | **`prefetch_related("items")` no board da Saída** | `kds.py:627` | médio (43 → ~5) | XS |
| R8 | **`prefetch_related("items")`/`values` no `_add_stock_warnings`** — agregar `Quant`/`StockAlert` uma vez para a união de SKUs da tela | `kds.py:918`, `:1090-1100` | médio (125 → ~8 na separação) | S |
| R9 | **GIN em `Order.data`** (ou promover `delivery_date`/`ifood.handshake_pending` a coluna) | `orderman/models/order.py` + migração do Core | médio-alto (14 pontos de leitura, um deles na fila a cada 30 s) | M |
| R10 | **Índices em `KDSTicket`** (`status`, `(kds_instance, status)`, `completed_at`) e um expurgo para tickets antigos | `backstage/models/kds.py:141-148` | médio | S |
| R11 | **Cadência calma + telemetria de poll por tela** (o `coalesceRefresh` do kit deduplica dentro de um composable, não entre composables) | `operator-kit/app/utils/coalesceRefresh.ts:2` | médio | M |
| R12 | **Ligar `pg_stat_statements` + `log_min_duration_statement=500`** | `WP-PERFORMANCE-2026-09.md` P0 | habilita tudo | XS |
| R13 | **Dar consumidor ao SSE da Produção** (ou parar de publicar `backstage-production-*`) | `_sse_emitters.py:408-424` | baixo-médio | S |
| R14 | **`Shop.load()` memoizado por request** e revisão dos lookups de `Channel` sem cache | `shop/models/shop.py:485` | baixo | S |

**Como medir cada uma.** Todas as contagens deste relatório saem do mesmo harness (sqlite in-memory + `CaptureQueriesContext` + `execute_wrapper` com `extract_stack`). Para as de front, instrumentar o `djangoProxy` do BFF com contador por rota e comparar antes/depois; para R12, `pg_stat_statements` por endpoint. Sem R12, nenhuma dessas ações tem *antes e depois* medido em produção — só em laboratório.

---

## 7. Perguntas abertas / o que não consegui verificar

1. **Volume real em produção** de `KDSTicket`, `Order` não-terminal, `OrderItem` e **quantas `Recipe` ativas** existem. É o multiplicador de todo N+1 acima; a medição foi feita com N sintético.
2. **Board de Compras não medido** — `projections/purchase.py` (912 linhas) não tem `build_purchase_board`; procurei o builder por nome e não achei. `purchase.py:375` (laço com 7 chamadas ORM) e `:550` (JSON `metadata`) ficam como suspeitos não confirmados.
3. **Board legado do Marketing** (`projections/marketing.py`, 1 015 linhas) não medido — é o segundo fetch de cada tick de 60 s (`useCampaignBoard.ts:113-115`).
4. **Alertas e Notificações** (`api/alerts.py`, `api/notifications.py`, poll de 60 s em todos os apps) — só leitura; não medi por exigirem usuário/permissão.
5. **Tempo de boot real** dos apps Nuxt (nenhum build/SSR foi executado). Todo "atrasa o boot" na §3.8-H6 é inferência de código.
6. **Custo por conexão SSE** (RSS/CPU) e o teto de conexões simultâneas — não há métrica no repositório e o `WP-PERFORMANCE-2026-09.md:341-345` já registra isso como pendente.
7. **Timeout de borda/Cloudflare** para conexões longas — não versionado, não medido.
8. **Duração real das transações de escrita do PDV** (`pos_concurrency.py:41` segura o lock durante o corpo da view).
9. **Latência externa dos endpoints de operador** — o `WP-PERFORMANCE-2026-09.md:42` mediu os shells de operador em 0,33–0,67 s, mas nenhum endpoint de projeção do backstage foi cronometrado de fora.
