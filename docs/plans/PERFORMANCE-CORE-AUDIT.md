# Auditoria Adversarial de Performance — Core/Kernel Shopman

> **Frente:** claude/perf-core-audit · worktree perf-core-audit-20261014 · base origin/main @ 82021ed04.
> **Natureza:** análise pura. **Zero** mudança em packages/, shopman/ e config/. Sem migração, sem credencial,
> sem escrita no vivo, sem tocar em .github/, .do/, surfaces/registry.json, operator-router/groups.json nem
> em docs/plans/WP-WATCHMAN*.
> **Escopo do Core:** os 12 pacotes de packages/ (utils, refs, offerman, stockman, craftsman, orderman,
> guestman, doorman, payman, buyman, fiscalman, cashman) e os caminhos quentes que os chamam em shopman/
> (shop, storefront, backstage). O pacote watchman (13o) ficou fora por ser de outra frente.
> **Método:** leitura estática com evidência arquivo:linha + medição de contagem de consultas num Postgres
> **local** isolado. Tudo o que tem número abaixo foi executado; o que é projeção está marcado como tal.

## TL;DR

Os 5 piores ofensores do Core, com número:

1. **orderman · CommitService grava OrderItem um a um** (N+1 de escrita). commit.py:463, dentro do laço
   em :457. Pedido de 10 itens = 1 INSERT do Order + 10 INSERTs de item + 1 evento. Projeção: 11 -> 2
   INSERTs; encurta a transação mais quente do sistema (o commit cria locks em Session e Customer).
2. **stockman · check_alerts é 1 + 2N consultas, medido.** alerts.py:44-73. Medido em Postgres local:
   2 alertas = **5 consultas**; 12 alertas = **25 consultas**. A projeção irmã do dashboard faz 10 alertas
   em **2 consultas** (teste já existente). Ganho: 1+2N -> 2.
3. **offerman · prefetch ignorado por .filter() dentro do laço.** service.py:408 faz
   prefetch_related(product__collection_items__collection), e :419 chama
   product.collection_items.filter(is_primary=True).first() — o .filter descarta o prefetch e volta ao banco
   por produto. 111 produtos no alpha -> ~112 consultas onde cabem 2.
4. **craftsman · mesmo padrão no planejamento de fornada.** queries.py:140 prefetcha recipe__items e :152
   chama recipe.items.filter(is_optional=False) por work order; scheduling.py:562 repete para as outras WOs
   do dia. 1+N em cada caminho de planejamento.
5. **shop (orquestrador) · sinal order_changed em cascata + I/O externo inline no on_commit.** apps.py:302-337,
   lifecycle.py:341-397. Um pedido criado dispara ~8 receivers de order_changed e, no on_commit, roda
   customer.ensure, stock.hold, loyalty.redeem, payment.initiate, fulfillment.create e notification.send —
   este último fala HTTP com o gateway de mensagem na mesma thread da resposta (dispatch.py:220-241).

Nenhuma dessas correções muda semântica de negócio. Todas têm teste de contagem de consultas proposto.

## 1. Como mediu (FATO, não opinião)

### 1.1 Inventário de modelos e índices (introspecção do ORM real)

Script descartável que faz django.setup() e despeja, para cada model dos 12 pacotes: db_table, ordering,
campos (tipo, null, db_index, unique, FK), Meta.indexes (campos, condição, INCLUDE) e constraints.
Comando (Postgres local, sem abrir conexão para escrita):

    PYTHONPATH=WORKTREE:WORKTREE/packages/CADA .venv/bin/python /tmp/introspect_models.py

Saída: 125 KB de metadados. Fato relevante: os únicos Meta.indexes explícitos existentes estão em Refs (2),
OfferMan Product (1), StockMan (Batch/Quant/Hold/Move/StockAlert), CraftsMan (Recipe/WorkOrder/WorkOrderItem/
RecipeEntry), Orderman Order (created_at), GuestMan (ContactPoint/Customer/ExternalIdentity/ProcessedEvent),
Doorman (AccessLink/TrustedDevice/Passkey/VerificationCode), CashMan Entry/Shift. **Orderman
Session/SessionItem/SessionEvent/Directive/Fulfillment/OrderItem/OrderEvent, OfferMan Collection/CollectionItem/
Listing/ListingItem/ProductComponent, PayMan PaymentIntent/PaymentTransaction, Buyman Material/Supplier/Cost/
Conversion, StockMan Position e CashMan Terminal não têm índice explícito nenhum** — o que só importa onde
houver filtro/ordenação sobre coluna não-FK.

### 1.2 Varredura AST de ORM dentro de laço

Scanner Python (ast) que percorre packages/ e shopman/ (sem tests/, sem migrations/), acha cada For/While e
reporta chamadas ORM no corpo (nome contendo .objects ou métodos filter/get/all/count/save/delete/etc).
Saída: 1584 linhas em 369 arquivos. É a fonte dos achados de N+1 por construção (o corpo do laço emite uma
consulta por iteração). Muitos falsos positivos de dict.get foram descartados por leitura.

### 1.3 Matriz de adoção da caixa de ferramentas

Contagem por pacote (só código, sem testes/migrations) de select_related, prefetch_related, values,
only/defer, iterator, bulk_create/update, Subquery/OuterRef, select_for_update, .count(), cache, I/O externo,
signals e paginação. Resultado que mais importa: **orderman tem 20 usos de select_for_update e ZERO de
select_related**; payman, fiscalman e buyman praticamente não usam a caixa.

Contagem global (git grep -F, sem testes):

    ArrayAgg=0  JSONBAgg=0  StringAgg=0  DistinctOn=0  SearchVector=0  GeneratedField=0
    update_conflicts=0  GinIndex=2  db_default=7  Subquery=16  OuterRef=37  Exists(=17
    select_for_update=544  iterator(=36  bulk_update=20  bulk_create=27

### 1.4 Medição de consultas (pytest + CaptureQueriesContext)

Postgres LOCAL (Homebrew 16.14 em 127.0.0.1:5432), banco de teste criado e destruído pelo pytest-django.
**Nunca usei o alpha/vivo.** Detalhe de ambiente: o .venv tem psycopg 3.3.6 com psycopg-binary 3.3.5 e o
connect quebra com wait_c() got an unexpected keyword; resolvi com PSYCOPG_IMPL=python (implementação pura),
sem tocar no venv compartilhado.

Teste descartável que projetei (não vai para o PR), com o modelo real de StockAlert/Quant:

    def _count(fn):
        with CaptureQueriesContext(connection) as ctx:
            fn()
        return len(ctx.captured_queries)

    seed(2);  small = _count(check_alerts)
    seed(10); big   = _count(check_alerts)

Resultado impresso:

    MEASURE stockman.check_alerts: 2 alertas=5 queries; 12 alertas=25 queries

Ou seja, exatamente 1 + 2N (1 consulta de alertas + 2 agregados por alerta). FATO.

No mesmo run, a suíte existente do projeto deu números de controle:

    GET pos/: 43 consultas (3 produtos, 1 comanda) e 43 (33 produtos, 7 comandas, 4 estações)

Isto é o test_pos_projecao_consultas.py, que trava custo constante (teto 45) — prova de que a projeção do
PDV **já foi corrigida** (era 171 consultas, 119 delas 1-por-produto, segundo o próprio docstring em
test_pos_projecao_consultas.py:1-11). E o dashboard batches os mesmos alertas em 2 consultas
(test_dashboard_projection_performance.py:33-34) — a correção de check_alerts é copiar um padrão que já
existe no repo.

Ressalva honesta do run: 2 testes passaram (meu medidor e o do POS) e 2 falharam, mas a falha é de
**formatação de valor** (global_row.current == 5 recebeu 5.000), não do orçamento de consultas (o
django_assert_num_queries(2) passou). Não é achado de performance desta frente; ficou registrado como
anomalia de teste, provavelmente pré-existente.

### 1.5 O que NÃO medi, e por quê

- **EXPLAIN do alpha**: não tenho credencial nem devo tocar no vivo. EXPLAIN no banco local vazio não
  representa o planner do alpha (o WP-PERFORMANCE-2026-09 mostra n_live_tup errado no alpha).
- **pg_stat_statements**: não instalado no alpha (é o P0 do WP-PERFORMANCE-2026-09). Sem ele, tempo de
  consulta por endpoint é inferência, não medição.
- **Throughput/ms de latência do Core isolado**: precisaria do seed completo e de carga; o número certo
  viria do locustfile (shopman/shop/tests/load/locustfile.py) contra um ambiente de ensaio. Não rodei.

## 2. Tabela por app — nota de risco

| App | Risco | O pior de cada um (evidência) | Ganho projetado |
|---|---|---|---|
| utils | Baixo | Sem ORM de banco no caminho quente; helpers puros | — |
| refs | Baixo-Médio | iendswith sem índice (services.py:222); rename em lote | baixo |
| offerman | **Alto** | N+1 de collection_items por produto (service.py:419) | ~1+N -> 2 |
| stockman | **Alto** | check_alerts 1+2N medido (alerts.py:44-73) | 25 -> 2 em 12 alertas |
| craftsman | **Médio-Alto** | recipe.items.filter no laço (queries.py:152; scheduling.py:562) | 1+N -> 2 |
| orderman | **Alto** | OrderItem.create por item (commit.py:463); JSON scan de histórico (history.py:92) | N+1 -> 2; scan -> índice |
| guestman | **Médio-Alto** | recalculate_all por cliente (insights/service.py:183) | O(C*O) -> set-based |
| doorman | Baixo-Médio | OTP/lookup indexados; custo mora no I/O síncrono de envio | depende do adapter |
| payman | **Médio** | filtro JSON gateway_data__customer_ref sem GIN (service.py:420-424) | seq scan -> índice |
| buyman | Baixo | volume baixo; FKs auto-indexadas | — |
| fiscalman | Baixo | funções puras sobre metadata; sem banco | — |
| cashman | Baixo-Médio | 3-4 agregados separados por turno (ledger.py:244-269) | 4 -> 1-2 |
| shop (orq.) | **Alto** | cascata de sinais + I/O externo no on_commit (apps.py:302-337) | tira HTTP do request |

## 3. Análise app a app

### 3.1 utils — risco Baixo

Sem ofensores de banco: o pacote é monetary/phone/names/formatting/units/spreadsheet e helpers de admin.
A matriz confirma 0 select_related/filter no caminho de dados. O único ponto de atenção é utils/spreadsheet.py
se for usado em request, mas não encontrei chamada em caminho quente.

O que NÃO vale a pena: micro-otimizar formatting/units. Custo de CPU irrelevante frente a banco.

### 3.2 refs — risco Baixo-Médio

Modelos e índices estão bons: Ref tem ref_type_val_active_idx e ref_target_active_idx, que cobrem as
consultas canônicas (resolve/reverse em services.py:194,293,367).

3 piores:

1. **services.py:222 — value__iendswith=suffix sem índice que sirva.** Busca por sufixo não usa btree; é
   varredura dentro do ref_type. Tipo: filtro não-indexável. Ganho: baixo hoje (cadastro é pequeno), mas
   cresce com o catálogo. Esforço P; risco baixo. Teste: EXPLAIN com ref_type fixo; ou trocar por pg_trgm
   (GinIndex) se virar busca de operador.
2. **bulk.py:134-145 — rename percorre as fontes registradas fazendo um UPDATE por modelo.** Bounded pelo
   número de models de cada ref_type (não por linha); bulk_update não ajudaria porque são tabelas
   diferentes. Tipo: N de tabelas, não N de linhas. Só monitorar.
3. **bulk.py:288-311 — auditoria de órfãos faz distinct(target_type) e uma query por tipo.** Também bounded
   por tipo. OK.

O que NÃO vale a pena: reescrever o registry; o design de refs é para volume pequeno.

### 3.3 offerman — risco Alto

Catálogo é lido em massa (home, menu, projeção iFood, admin). Índices: Product só tem
(is_published, is_sellable); Listing/ListingItem/Collection/CollectionItem/ProductComponent não têm índice
explícito (FKs auto-indexadas).

3 piores:

1. **service.py:419 — .filter() dentro do laço ignora o prefetch_related de :408.** Tipo: N+1. O prefetch
   traz product__collection_items__collection, mas .filter(is_primary=True).first() descarta o cache e emite
   1 query por produto. Ganho: 1+N -> 2. Com 111 produtos publicados no alpha (WP-PERFORMANCE-2026-09
   §2.3), ~112 -> 2 consultas por sync de listing. Esforço P; risco baixo. Correção segura:
   Prefetch(product__collection_items, queryset=CollectionItem.objects.filter(is_primary=True)
   .select_related(collection), to_attr=primary_collection_items) e ler a lista em Python. Teste que
   provaria: django_assert_num_queries constante ao crescer de 2 para 30 produtos.
2. **service.py:437 — list(product.keywords.names()) por produto.** keywords é TaggableManager; o
   prefetch_related(product__keywords) de :408 ajuda o .all(), mas .names() tende a emitir query própria.
   Tipo: suspeita de N+1 (confirmar com assertNumQueries). Ganho: 1+N -> 2. Esforço P. Correção: iterar
   product.keywords.all() quando prefetchado. Mesmo teste do item 1.
3. **adapters/sku_validator.py:134 e product_info.py:98/136 — mesmo padrão
   product.collection_items.filter/.all em laço, com prefetch em :122/:89.** Tipo: N+1 repetido em dois
   adapters de leitura do catálogo. Ganho 1+N -> 2. Esforço P; risco baixo. Teste idêntico.

O que NÃO vale a pena: cache global de produto (invalidação complexa) antes de consertar o N+1; índice em
Product.name para search antes de haver busca por trigram real.

### 3.4 stockman — risco Alto

O availability_for_skus_on_dates é o melhor código do repo para volume: lê lotes, quants e holds em
consultas em bloco (availability.py:449-521) e monta tudo em memória. Não mexer nisso.

3 piores:

1. **services/alerts.py:44-73 — check_alerts 1 + 2N, MEDIDO (5 e 25 consultas).** Por alerta ativo, um
   aggregate de Quant e um de Hold, mais um save quando dispara. Tipo: N+1 de leitura (agregado por item).
   Ganho: 1+2N -> 2 para qualquer número de alertas; o dashboard já faz isso em 2 consultas. Esforço P-M;
   risco baixo. Correção: 1 query agregando Quants por (sku, position) + 1 de Holds, e comparar em Python
   (copiando shopman/backstage/projections/dashboard.py). Teste: django_assert_num_queries(2) com 1 e com
   10 alertas — o mesmo formato de test_dashboard_projection_performance.py.
2. **models/position.py — Position sem índice e ordering por ref.** Se a tela lista posições, é sort em
   memória; com poucas posições não importa. Baixa prioridade.
3. **services/holds.py:394-451 e planning.py:261-273 — laços com get/save por item.** Bounded pelo número
   de SKUs/holds da operação; a leitura mostra volume pequeno. Monitorar, não atacar.

O que NÃO vale a pena: reescrever availability (já é boa); índice em Quant.sku já existe (e o composto
(sku, position, target_date) da constraint cobre).

### 3.5 craftsman — risco Médio-Alto

Produção mexe em BOM/receitas, que são leitura em árvore. Os índices de WorkOrder/WorkOrderItem estão
razoáveis; WorkOrderEvent só tem FK order (auto-indexada) e unique (order, seq).

3 piores:

1. **services/queries.py:140-152 — recipe.items.filter(is_optional=False).order_by(...) dentro do laço,
   apesar do prefetch_related(recipe__items) em :140.** Tipo: N+1. Ganho: 1+N -> 2. Um dia com 20 WOs =
   21 consultas onde cabem 2. Esforço P; risco baixo. Correção: Prefetch com to_attr já filtrado, ou
   filtrar a lista prefetchada em Python. Teste: assertNumQueries constante com 1 vs 20 WOs.
2. **services/scheduling.py:556-565 — other.recipe.items.filter(...) por work order do dia.** Mesmo padrão;
   agrava porque roda no guardrail de disponibilidade de insumos (a cada planejamento). Ganho 1+N -> 2.
   Teste idêntico.
3. **services/recipe_book.py:677 / models/recipe.py:163 — recipe.items.filter dentro de laço em montagem
   de ficha técnica.** Tipo: N+1. Ganho 1+N -> 2. Esforço P.

O que NÃO vale a pena: denormalizar BOM em coluna; a explosão multi-nível é uma caminhada de grafo, não
SQL. Índice em WorkOrderEvent(recorded_at) antes de haver consulta de auditoria pesada.

### 3.6 orderman — risco Alto

O app mais quente (sessão, commit, pedido) e o que menos usa select_related (0 na matriz). O
deferred_item_writes de session.py:254-287 já é uma otimização fina e correta; não desfazer.

3 piores:

1. **services/commit.py:457-472 — OrderItem.objects.create(item a item).** Tipo: N+1 de escrita, dentro da
   transação que segura lock de Session e Customer. Ganho: N INSERTs -> 1 bulk_create; pedido de 10 itens,
   11 -> 2 inserts, e menos tempo de lock. Esforço P; risco baixo (OrderItem não tem signal nem save
   customizado). Teste: CaptureQueriesContext no CommitService com 1 e com 10 itens, orçamento constante.
2. **services/history.py:77-80 e :92 — histórico do cliente filtra Order.data__customer_ref (JSONField, sem
   índice) e soma snapshot JSON em Python, iterando TODOS os pedidos do cliente.** Tipo: varredura de
   JSONField + agregação em Python. Ganho: por cliente, de 1 scan + parse de N snapshots para 1 agregado
   sobre campo indexado. No batch (guestman RFM) o efeito multiplica por cliente. Esforço M; risco médio
   (a semântica de total usa snapshot.pricing.total_q com fallback para total_q — precisa de teste de
   equivalência). Correção possível: GeneratedField/expression index sobre data->customer_ref, e/ou usar
   Order.total_q quando o snapshot não divergir. Teste: comparar atual vs novo para 50 pedidos com desconto.
3. **api/serializers.py:15-33 + api/views.py:142-156 — SessionSerializer serializa items (session.py:366) e
   o ViewSet não faz prefetch_related(session_items).** Tipo: N+1 de leitura em lista de sessões. O próprio
   _load_items_from_lines (session.py:370) já reconhece o prefetch, então é só ligar. Ganho: 1+N -> 2 numa
   página de comandas. Esforço P; risco baixo. Teste: listar 25 sessões com assertNumQueries.

Menção: Directive tem índices individuais (topic, status, available_at, dedupe_key) e a constraint única de
dedupe; a query do worker (process_directives.py:156-159) combina status+topic e available_at — um composto
(status, available_at) ou (topic, status, available_at) reduziria bitmap-and, mas o ganho é menor que os
itens acima. O reaper (process_directives.py:41) filtra started_at, que não tem índice, mas status=running é
raro e usa o índice de status. Não priorizar.

O que NÃO vale a pena: trocar select_for_update por lock otimista (muda semântica de concorrência); async
sobre o ORM do commit (o gargalo é escrita, não espera de rede).

### 3.7 guestman — risco Médio-Alto

Cadastro bem indexado (ref/document/phone/email; ContactPoint por customer+type+is_primary; ExternalIdentity
por provider+uid). O problema está no batch de CRM.

3 piores:

1. **contrib/insights/service.py:183 — recalculate_all itera todo cliente ativo e chama recalculate(ref),
   que por sua vez varre os pedidos do cliente (orderman history).** Tipo: laço por cliente com trabalho
   O(pedidos) dentro. Para C clientes e O pedidos: C consultas de stats + C varreduras completas do
   histórico (com parsing de JSON). Ganho: de O(C * pedidos) em Python para agregação set-based no banco.
   Esforço G; risco médio (RFM muda de valor se a fórmula sair do Python). Teste: congelar os insights
   atuais, rodar o novo, comparar campo a campo.
2. **contrib/insights/service.py:206-208 — favorite_products__contains=[{sku: ...}] sem GIN.** Tipo:
   varredura de JSONField (contains em lista de dicts). Ganho: seq scan -> GinIndex. Esforço P; risco baixo.
   Teste: EXPLAIN antes/depois; GinIndex em favorite_products.
3. **contrib/merge/service.py:663-689/768-781/815-846 — merge move ContactPoint/ExternalIdentity/
   CustomerIdentifier com exists+save+delete em laços.** Tipo: N+1 de escrita no merge (operação rara e de
   operador). Ganho moderado; esforço M; risco alto (merge mexe em identidade). Só fazer com teste de
   idempotência dedicado. Baixa prioridade.

O que NÃO vale a pena: cachear Customer (invalidação de PII/erasure é sensível); mexer no merge agora.

### 3.8 doorman — risco Baixo-Médio

Os lookups estão indexados e as mutações usam select_for_update (verification.py:258,328,452,612). Não há
varredura na base.

3 piores:

1. **Senders externos (senders.py) e verification emitem SMS/WhatsApp de forma síncrona no request de
   login.** Tipo: I/O externo síncrono em caminho quente. Não é bug de ORM, mas é latência de request que
   o usuário sente. Ganho: se o envio virar Directive/fila, o request devolve sem esperar o provedor.
   Esforço M; risco médio-alto (mudança de fluxo de OTP; precisa de fallback e teste de entrega).
2. **VerificationCode.acquire/consume fazem select_for_update + update.** Correto para concorrência;
   nenhuma otimização sem risco de corrida. Não mexer.
3. **models/customer_user.py e pin_credential.py — sem índice explícito, mas lookups são por FK/unique.**
   Sem ofensor.

O que NÃO vale a pena: trocar select_for_update por update condicional sem prova de ganho; volume baixo.

### 3.9 payman — risco Médio

Estado granular (PaymentTransaction) e idempotência correta. O custo real (gateway HTTP) mora nos adapters
do shop, não no pacote.

3 piores:

1. **service.py:420-424 e 434-441 — filtro/agrupamento por gateway_data__customer_ref (JSONField).** Tipo:
   varredura de JSONField; não há GIN em gateway_data. Ganho: seq scan -> índice GIN/expression. Esforço M;
   risco baixo (só acelera leitura). Teste: EXPLAIN de account_open_intents antes/depois.
2. **PaymentIntent sem índice em created_at, com ordering = [-created_at] e sem paginação por cursor na
   listagem do admin.** Tipo: ordenação sem índice; com volume cresce. Ganho: índice (ou composto
   (method, status, created_at)) se a tela listar. Esforço P; risco baixo. Teste: EXPLAIN da listagem.
3. **models/transaction.py — PaymentTransaction sem índice explícito em (intent, created_at/type).** Se a
   tela de reconciliação lista transações por intent e ordena, é sort/scan. Baixa-média prioridade; medir
   antes.

O que NÃO vale a pena: mexer no state machine; ele está correto e testado.

### 3.10 buyman — risco Baixo

Fase 1, volume baixo. Material/Supplier/MaterialConversion/SupplierMaterialCost não têm Meta.indexes, mas as
consultas caem em FK (auto-indexada) e nas UniqueConstraints. O ordering (material, supplier) não é coberto
pela unique (supplier, material) — ordem de colunas difere; se a tela ordenar por (material, supplier), um
índice composto ajudaria. Prioridade baixa. O que NÃO vale: índice preventivo.

### 3.11 fiscalman — risco Baixo

Não faz banco: from_metadata/errors/warnings/resolve_fiscal_item são funções puras sobre dict
(classification.py:164-238). O risco é o CHAMADOR percorrer o catálogo inteiro chamando
validate_for_emission por produto — isso é custo do admin/projeção (superfície), não do pacote. Nada a
fazer no Core.

### 3.12 cashman — risco Baixo-Médio

Livro-caixa append-only com Entry bem indexado ((shift,id), (operator,at), (kind,at), (at)). O saldo é
derivado, nunca coluna — correto.

3 piores:

1. **services/ledger.py:244-269 — balance/expected_before_count/difference/counted rodam agregados
   separados; counted chama difference (que faz exists + aggregate) e expected_before_count.** Tipo:
   múltiplos agregados na mesma linha do turno. Ganho: 3-4 -> 1-2 consultas com um CASE WHEN. Esforço P-M;
   risco baixo (mesma matemática). Teste: assertNumQueries no fechamento.
2. **services/ledger.py:279-312 — change_requests lê as entradas e dobra em Python.** É 1 consulta em
   bloco, não N+1. OK; só não quebrar.
3. **Shift sem índice em (terminal, opened_at) se a tela lista turnos por terminal.** Baixa prioridade.

O que NÃO vale a pena: materializar saldo em coluna (perde a garantia de derivado do livro).

### 3.13 shop (orquestrador) — risco Alto

É a cola que os 12 pacotes chamam; o custo está em coordenação, não em ORM próprio.

3 piores:

1. **Cascata de sinais.** order_changed tem ~8 receivers em produção (apps.py:333, :353,
   handlers/__init__.py:446, _sse_emitters.py:255, alert_resolution.py:99, cancellation_requests.py:32,
   production_order_sync.py:35, backstage/apps.py:126); production_changed tem outros ~8
   (craftsman/contrib/stockman/handlers.py:56, apps.py:369, handlers/__init__.py:379, _sse_emitters.py:260,
   campaign.py:29, production_alerts.py:48, production_order_sync.py:40, storefront/apps.py:92). Todo send()
   roda todos, em série, na thread do request/worker. Tipo: sinal em cascata. Ganho: não é apagar receiver
   (muda comportamento); é medir e coalescer reações idempotentes (o run_at_request_end de
   request_memo.py:201-227 já faz isso para observação de falta). Esforço M-G; risco alto. Teste: contar
   receptores e assertNumQueries num order_changed completo; medir antes/depois sem mudar efeito observável.
2. **lifecycle._on_commit (lifecycle.py:341-397) roda serviços pesados no on_commit de todo pedido:**
   customer.ensure, _check_availability, stock.hold, _verify_holds, loyalty.redeem, payment.initiate,
   fulfillment.create, notification.send. Cada um abre queries e alguns abrem transação. Tipo: I/O e
   escrita em caminho quente. Ganho depende do canal: num balcão, muito disso é no-op, mas o custo de
   decidir ainda existe. Esforço M; risco alto (é o coração do lifecycle). Teste: trace de consultas por
   fase com um pedido de PDV e um remoto.
3. **dispatch.py:220-241 + notification.send — handler de Directive roda inline no on_commit do post_save,
   então o HTTP para ManyChat/email acontece na mesma thread que fechou o pedido.** Tipo: I/O externo
   síncrono em caminho quente, depois do commit. Ganho: request responde sem esperar o provedor se o
   despacho ficar só para o worker (process_directives) ou para um executor fora do request. Esforço M;
   risco alto (muda a latência de entrega e a ordem; há testes de duplicidade). Teste: medir tempo de
   request de commit com e sem o dispatch inline; garantir que o worker pega a fila sem perder nada.
   Observação: o próprio dispatch.py:1-9 documenta que o worker é fallback e que o normal é inline — a
   proposta é o inverso (inline só quando o handler for barato).

Menção: ChannelConfig.for_channel (config.py:474-510) continua montando a cascata (deep_merge, from_dict,
validate) a cada dispatch; request_memo.channel_config (request_memo.py:108-130) guarda o resultado no
request, mas lifecycle.dispatch chama for_channel direto (lifecycle.py:327). Fora de request (worker) não há
memo. É CPU, não banco; baixa prioridade, mas é uma linha fácil (usar channel_config() quando houver request).

O que NÃO vale a pena: async/await no lifecycle inteiro (o ORM síncrono domina e a mudança é enorme);
remover receivers de sinal (quebra efeitos).


## 4. Implicações acima do Core (superfícies) — achados encaminhados, não tarefas

Conforme o complemento do dono (14/10), estes são **material para um WP dedicado de qualidade de
implementação**; não são tarefas desta frente e não executei nada fora do Core.

1. **shopman/backstage/projections/production.py:3053 — _qty_required_for_order percorre order.items.all()
   por par (pedido, WO) dentro de laço** (chamada em :3045). Tipo: N+1 de leitura. Ganho: pré-computar um
   mapa order_id -> {sku: qty} numa consulta. Risco baixo. WP candidato: projeções de produção.
2. **shopman/backstage/projections/production.py:2275 — wo.events.all() por work order** (e :2820
   RecipeItem.objects.filter, :3511 recipe.items.all). Tipo: N+1. Ganho: prefetch com filtro + to_attr.
   Risco baixo-médio. Mesmo WP.
3. **shopman/backstage/projections/kds.py:308-319 — build_kds_index recalcula o board inteiro por instância
   de expedição e varre Order.objects.filter(status=READY) por instância.** Tipo: N+1/trabalho repetido.
   Ganho: computar uma vez e reusar. Risco baixo. WP de projeções de KDS.
4. **shopman/storefront/api/surface.py:470-476 — laço sobre RetiredProduct.objects.all() chamando
   primeira_viva, que pode emitir exists() por coleção.** Tipo: N+1 no endpoint de redirect 301. Ganho:
   pré-carregar o conjunto de coleções vivas. Risco baixo. WP de storefront.
5. **shopman/storefront/services/stock_alerts.py:808-809 — para cada subscription, um get_or_create de
   StockAlertDelivery.** Tipo: N+1 de escrita num job. Ganho: bulk_create/upsert por lote. Risco médio
   (idempotência de entrega). WP de alertas.
6. **shopman/storefront/services/account_privacy.py:620-628 — update por assinatura em laço.** Tipo: N+1
   de escrita. Ganho: um UPDATE com filtro. Risco baixo. Mesmo WP de privacidade.
7. **shopman/backstage/services/production.py:3083/3098 — work_order.save()/order.save() por item em laço.**
   Tipo: N+1 de escrita. Ganho: bulk_update. Risco médio (ordem e timestamps). WP de execução de produção.
8. **shopman/backstage/services/sign_in_audit.py:507 — sessao.delete() por linha em laço.** Tipo: N+1 de
   escrita. Ganho: delete em bloco. Risco baixo. WP de higiene/auditoria.
9. **shopman/backstage/projections/bi_over_short.py:364/764/777 — WorkOrder/Product/CollectionItem
   filtrados dentro de laço.** Tipo: N+1 de leitura em relatório. Ganho: carregar em bloco. Risco baixo.
   WP de B.I.
10. **BFF Nuxt -> Django pela URL pública (hairpin)** — já mapeado como P4 do WP-PERFORMANCE-2026-09;
    NÃO é Core e não reproponho aqui.

Contraexemplos que NÃO precisam de WP (já estão bons): order_queue.py:1666 lê OrderItem em bloco;
kds.py:636-641 resolve fontes em duas consultas; storefront/presentation/catalog.py monta mapas a partir de
conjuntos já carregados.

## 5. O que já foi feito — não refazer

- **WP-PERFORMANCE-2026-09** (docs/plans/WP-PERFORMANCE-2026-09.md) já cobre: health check renderizando a
  home, /ready/ montando grafo de migrations, B.I. varrendo 380k linhas, BFF hairpin, cache da leitura
  pública, deployments em rajada. E o item índice em orderman_order.created_at **já foi implementado** (o
  modelo tem ord_order_created_at_idx:created_at, order.py:124-130).
- **request_memo** (shopman/shop/request_memo.py) já resolve o scan de Channel por request e o Redis do
  Shop.load; é um dos melhores códigos do repo. A memória de estoque só vale em GET/HEAD e desliga após
  qualquer escrita — desenho correto.
- **POS** (test_pos_projecao_consultas.py) já está em custo constante (43 consultas; era 171).
- **check_alerts do dashboard** já é batched em 2 consultas — é o padrão a copiar para o do stockman.

## 6. Roadmap priorizado (maior ganho por risco)

| # | Ação | Onde | Ganho | Esforço | Risco | Teste |
|---|---|---|---|---|---|---|
| 1 | bulk_create dos OrderItem | orderman commit.py:463 | N+1 -> 2 inserts; menos lock | P | Baixo | assertNumQueries constante 1 vs 10 itens |
| 2 | prefetch com to_attr no catálogo | offerman service.py:419 (+adapters) | 1+N -> 2 | P | Baixo | assertNumQueries 2 vs 30 produtos |
| 3 | batching do check_alerts | stockman alerts.py:44 | 1+2N -> 2 | P-M | Baixo | assertNumQueries(2) com 1 e 10 alertas |
| 4 | Prefetch filtrado no planejamento | craftsman queries.py:152, scheduling.py:562 | 1+N -> 2 | P | Baixo | assertNumQueries 1 vs 20 WOs |
| 5 | prefetch de session_items na lista | orderman api/views.py:142 | 1+N -> 2 | P | Baixo | assertNumQueries com 25 comandas |
| 6 | índice/GIN em Order.data->customer_ref e gateway_data->customer_ref | orderman history.py:92; payman service.py:420 | varredura -> índice | M | Baixo | EXPLAIN antes/depois |
| 7 | agregados de caixa em menos idas | cashman ledger.py:244-269 | 3-4 -> 1-2 | P-M | Baixo | assertNumQueries no fechamento |
| 8 | medir e coalescer a cascata de order_changed | shop apps.py:302 / lifecycle.py:341 | depende do canal | M-G | Alto | trace de consultas + tempo por fase |
| 9 | tirar o dispatch inline de Directive do request | orderman dispatch.py:220 | request sem HTTP externo | M | Alto | tempo de commit antes/depois + fila sem perda |
| 10 | RFM set-based | guestman insights/service.py:183 | O(C*pedidos) -> set-based | G | Médio | diff campo a campo dos insights |
| 11 | GIN em favorite_products | guestman insights/service.py:207 | seq scan -> índice | P | Baixo | EXPLAIN |
| 12 | índice em WorkOrderEvent(recorded_at) e Position(ref) | craftsman/stockman | sort/scan -> índice | P | Baixo | EXPLAIN (medir antes) |

Ordem de ataque sugerida: 1-5 num PR de Core sem N+1 (todos P, risco baixo, mesmo padrão de teste); depois
6-7 (índices/agregados); 8-9 exigem frente própria com instrumentação (pg_stat_statements do P0); 10-12
ficam para depois do go-live ou quando houver volume.

## 7. O que NÃO vale a pena

- **async/await sobre o ORM do commit/lifecycle** para esperar o banco: o gargalo é escrita e lock, não
  espera de rede. O pool psycopg3 já resolve o reuso de conexão (config/settings.py:520-546).
- **select_for_update a mais** em qualquer lugar: 544 usos já é muito; adicionar travas piora throughput.
- **cache global de catálogo/disponibilidade sem invalidação** (a disponibilidade fecha a promessa, como o
  próprio WP-PERFORMANCE-2026-09 argumenta). O request_memo é o limite seguro.
- **denormalizar BOM/saldo em coluna** para evitar joins: muda invariantes (Quant._quantity já é cache
  guardado por Move; não criar um segundo).
- **índices preventivos** em tabelas pequenas (Buyman, Fiscalman, utils): criam custo de escrita sem leitura
  que justifique. Medir com EXPLAIN antes.
- **trocar os loops Python de availability/cashman/change_requests por SQL** só pela estética: eles já fazem
  1 consulta em bloco e o Python não é o gargalo.

## 8. Anexo — caixa de ferramentas: o que o repo real já permite e não usamos

Versões reais do repo (pyproject.toml): **Django >=6.1,<6.2** (instalado 6.1.1), djangorestframework 3.18,
django-filter, drf-spectacular, **psycopg[binary,pool] >=3.2 (instalado 3.3.6)**, redis 7.4,
django-eventstream, django-unfold. Python >=3.12 (instalado 3.12.5). Postgres 16. Consequência: **tudo o
que é Django 5+ já está disponível** — e o código roda em 6.1.

| Ferramenta | Estado no repo | Onde se aplica |
|---|---|---|
| select_related/prefetch_related | usados, mas 0 em orderman | orderman api/views.py:142; craftsman/offerman já tentam mas quebram no .filter() |
| Prefetch(queryset=..., to_attr=...) | **0 usos de to_attr** | offerman service.py:408; craftsman queries.py:140 |
| only/defer | quase nada | listagens (Session, Order) para não trazer JSONField data/snapshot inteiro |
| values/values_list | usados | manter; order_queue.py:1666 é o exemplo certo |
| iterator(chunk_size) | 36 usos | relatórios/B.I.; não usar em listas pequenas |
| bulk_create / bulk_update | 27 / 20 usos | orderman commit.py:463; guestman merge; cashman; production.py |
| bulk_create(update_conflicts=True) | **0 usos** | upsert de custos/conversões (Buyman), projeções iFood |
| Subquery/OuterRef/Exists | 16/37/17 usos | já bem usado; aplicar em RFM no lugar de laço |
| Window functions | não vi uso | B.I. (rank de vendas por dia), fechamento |
| ArrayAgg/JSONBAgg/StringAgg/DistinctOn | **0 usos** (django.contrib.postgres está em INSTALLED_APPS, settings.py:305) | RFM/insights, order_queue, B.I. |
| GinIndex / pg_trgm | 2 usos de GinIndex; **0 pg_trgm** | guestman favorite_products (contains), busca de catálogo |
| SearchVector | 0 | busca textual de catálogo, se sair do icontains |
| GeneratedField / db_default | GeneratedField 0, db_default 7 | Order.data->customer_ref indexável sem poluir JSON |
| Índice composto/parcial/covering (INCLUDE) | parcial existe; INCLUDE **0** | order created_at+status; Entry(shift,kind); Directive(status,available_at) |
| ORM async / sync_to_async | presente em ASGI, mas não no Core | NÃO no Core; só onde há I/O externo (senders) |
| Pool psycopg3 + CONN_MAX_AGE/CONN_HEALTH_CHECKS | **já ligado** | config/settings.py:520-546; não repropor |
| Cache com invalidação por sinal | request_memo faz para request; Redis disponível | catálogo público (P6 do WP de setembro); NUNCA disponibilidade |
| Tirar trabalho do request (Directive/fila/SSE) | existe (Directive, django-eventstream) | dispatch inline (dispatch.py:220); SSE para telas |

## 9. Limitações e o que ficou

- Não rodei a suíte inteira nem toquei no alpha; os números são de Postgres local com fixtures pequenas
  (contagem de consultas é independente de volume, mas tempo em ms não).
- Não medi EXPLAIN no alpha (sem credencial e por regra). O instrumento certo é o P0 do
  WP-PERFORMANCE-2026-09 (pg_stat_statements); recomendo anexar os EXPLAINs a cada PR de correção.
- O run isolado teve 2 falhas de teste alheias ao escopo (formatação 5 vs 5.000 no
  test_dashboard_projection_performance.py), com o orçamento de consultas passando.
- Não cobri watchman (13o pacote, de outra frente) nem o código de preço/catálogo em voo
  (claude/catalogo-turbo), conforme a regra.
- Próximo passo natural: PR 1-5 do roadmap (Core sem N+1), cada um com o teste de contagem proposto.
