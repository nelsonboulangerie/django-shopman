# BI-DATA-FOUNDATION-PLAN — a fundação de dados do B.I. em três camadas

> **Status: 🟢 ETAPA 1 APROVADA em 2026-08-18 ("acato as recomendações") — as três decisões do
> §6 ficaram como recomendado; ETAPA 2 em andamento: P0 ✅ (#209), P1 ✅ (`feat/bi-aliases`),
> próximo P2 (contrato canônico + fontes + leitura).** Frente B, v1. Irmão de
> [BI-PLAN.md](BI-PLAN.md), [BI-INSIGHTS-MAP.md](BI-INSIGHTS-MAP.md),
> [BI-FORECAST-PLAN.md](BI-FORECAST-PLAN.md) e [BI-QUESTION-CATALOG.md](BI-QUESTION-CATALOG.md).
> Não depende da consulta de perfis (frente separada); se ela existir quando isto rodar, é só
> mais um cliente da camada de leitura.
>
> Base do levantamento: `origin/main @ b1fd8a844` (cashman WP-0/1/2 mergeados; WP-3 = #205 e
> WP-4 = #206 abertos). Tudo abaixo foi lido no código; onde cito número, cito a linha.

## 0. Resumo executivo

O B.I. de hoje é **bom na camada de leitura e inexistente nas outras duas**. Há oito
projections (3.042 linhas), um explorador de 24 métricas × 20 dimensões com gramática estrita,
previsão por dias parecidos, contrato TypeScript gerado e um app Nuxt próprio. Tudo calculado na
hora, zero materialização, por política (ADR-021 §3). Isso não é dívida: com ~150 vendas/dia o
cálculo na hora é a resposta certa, e a política tem gatilho medido.

O que **falta** é exatamente o que a missão pede:

1. **Ingestão sem disciplina de lote.** O Yooga aterrissa em `HistoricalSale`/`HistoricalSaleItem`
   (81.255 vendas, 353.009 linhas), idempotente por chave natural, mas **sem lote, sem hash do
   arquivo, sem registro de importação, sem transação nas vendas, sem validação de payload**. Nove
   colunas do export são descartadas na entrada (telefone, bairro, endereço, taxa de cartão,
   observação…) — 4.769 clientes identificados no histórico são inalcançáveis.
2. **Camada canônica que existe como REGRA em código, não como dado.** A fusão nativo × Yooga
   ("o dia nativo vence") vive em `sales_series.py` mas está **replicada** em `bi_sales.py` (3×) e
   `bi_explore.py` (2×). Os de-paras que a missão quer editáveis no Admin hoje são **tabelas em
   Python**: `CATEGORY_READING` (26 regras de substring), `_HISTORICAL_VOCABULARY` (15 regras de
   forma de pagamento), `product_map` (nome→SKU, em memória, só durante o ingest). **Não existe
   de-para produto Yooga → `offerman.Product`**: o join é string com string, e o SKU do catálogo é
   inventado enquanto o do Yooga é o real ([SKU-REAL-PLAN](SKU-REAL-PLAN.md), branch `plano/sku-real`).
   A única exceção — e o molde a seguir — é `ProductConsumptionTag` (SKU→papel de consumo,
   `reviewed`, editável no Admin, curadoria humana).
3. **Log do PDV = `cashman.Entry`, e ele já é a fonte certa.** O PR #198 (`POSEvent`) foi
   superado; o livro-caixa imutável nasceu como pacote do Core (#202). Ele **não precisa de tabela
   de aterrissagem** — é ledger nativo, append-only, com guarda igual à do `stockman.Move`. O que
   ele precisa é de um **adaptador** para a camada canônica, e de que `bi_cash.py` (hoje lendo
   `CashShift.difference_q` + `CashMovement` + `DayClosing.data`) migre **uma vez só**, pela camada
   de leitura, junto com o WP-4/WP-8 do [CASHMAN-PLAN](CASHMAN-PLAN.md).

**Veredito:** a arquitetura-alvo cabe no que existe **sem redesenhar leitura nenhuma**. A primeira
fonte a atravessar as três camadas é o **Yooga** — já aterrissou, tem o maior volume, e todos os
seus leitores já passam por um funil (`sales_series`, `_consumption_modes`, `iter_order_payments`).
Depois o pedido nativo, depois o `cashman.Entry`, e a NFC-e entra pelo padrão provado quando houver
emissão real.

**Duas decisões que só o dono toma** (§6): (a) canônica **persistida** (tabelas `Sale`/`SaleLine`
copiadas de todas as fontes) ou canônica como **contrato + de-paras como dado, com materialização
só na camada de leitura** — recomendo a segunda, pelo Core sagrado e pela ADR-021; (b) o **sentido
do de-para de produto**: alias apontando para `offerman.Product` (identidade do catálogo) ou para um
"produto canônico do B.I." separado — recomendo `Product`, e isso encosta no SKU-REAL.

---

## 1. Estrutura atual do B.I. (lida pelas três camadas)

### 1.1 O que hoje faz o papel de "ingestão"

| Fonte | Onde aterrissa | Como entra | Idempotência | Metadados de lote |
|---|---|---|---|---|
| Yooga (export xlsx, 3 abas) | `backstage.HistoricalSale` + `HistoricalSaleItem` (`models/historical_sale.py:19,60`) | `ingest_yooga --file` (`management/commands/ingest_yooga.py`, 231 linhas, `openpyxl`) | chave natural `pedido` → `external_id`; `UniqueConstraint(source, external_id)`; itens dedup **por venda**, não por linha (`:182-200`) | `source="yooga"`, `ingested_at`. **Nenhum** lote/hash/log. `metadata` só guarda `nfce_id` (`:144-147`) |
| Yooga sintético (local/CI) | mesmas tabelas, `source="seed"` | `seed._seed_bi_history` (`config/.../seed.py:6328-6400`) | apaga só `source=seed`; **pula se houver fonte real** (`:6343-6350`) | idem |
| Feriados / datas comerciais | `backstage.DayContext` (bloco calendário) | `import_holidays` (JSON/CSV) | reescreve o ano inteiro | `DayContext.sources` (proveniência por bloco) |
| Clima | `DayContext` (bloco clima) | `import_weather` (CSV/JSON, aliases Open-Meteo) | por data; vazio = NULL, nunca 0 | idem |
| Expediente congelado | `DayContext` (bloco expediente) | `stamp_business_days` (maintenance_worker) | por data | idem |
| Nativo (venda, produção, forno, caixa, estoque, falta) | ledgers e modelos de operação: `orderman.Order/OrderItem`, `craftsman.WorkOrder/Item`, `backstage.OvenRun`, `CashShift/CashMovement/DayClosing`, `stockman.Move`, `backstage.ShelfOutage`, `guestman.CustomerInsight` | operação | n/a | n/a |

Só existe **um** importador de venda externa e ele não segue contrato nenhum: formato, colunas
e validação são dele. Fonte nova hoje = copiar o `ingest_yooga` e adaptar.

### 1.2 O que hoje faz o papel de "canônica"

Não há modelo unificado. Há **regras em código** que unificam na leitura:

| Pergunta | Dono único hoje | Replicado em | Natureza |
|---|---|---|---|
| Quanto vendeu no dia (nativo × histórico, "o dia nativo vence") | `projections/sales_series.py:43` | `bi_sales.py:120-138, 208-217, 266-272`; `bi_explore.py:381-392, 490-498, 741-755` | fusão de fontes |
| Modo de consumo (cesta) | `services/consumption.py:108 classify_basket` | — (um só; `bi_explore._consumption_modes:518` e `services/room.py:154` chamam) | regra + de-para |
| SKU → papel de consumo | **`ProductConsumptionTag`** (tabela, `reviewed`, Admin) | — | **de-para como dado ✅ (o molde)** |
| Categoria Yooga → papel de consumo | `CATEGORY_READING` (`consumption.py:40-72`, 26 regras) | — | **de-para em código ❌** |
| Forma de pagamento Yooga → chave | `_HISTORICAL_VOCABULARY` (`bi_payments.py:26-42`, 15 regras) | — | **de-para em código ❌** |
| Nome Yooga → SKU Yooga (7% sem SKU) | `product_map` (em memória no ingest, `ingest_yooga.py:114-127`) | leitores dobram por `nome:<name>` (`bi_sales.py:246`, `bi_explore.py:460`) | **de-para descartável ❌** |
| SKU Yooga → `offerman.Product` | **não existe** | — | **buraco** (BI-PLAN §8 deixou fora do v1) |
| Repartição de pagamento no pedido | `services/payments.py:42 iter_order_payments` | — (fechamento e B.I. usam) | regra |
| Dia parecido | `services/day_similarity.py` | — | regra |
| Canal do histórico | sintético `f"{source} · {loja|delivery}"` | `bi_sales.py:134`, `bi_explore.py:390` | fusão |

### 1.3 Camada de leitura (a única que existe de fato)

- **8 projections** em `shopman/backstage/projections/bi_*.py`, 3.042 linhas; 6 com `build_bi_*`
  (`production`, `sales`, `cash`, `customers`, `forecast`, `change`) + `bi_explore` (gramática) +
  `bi_payments` (vocabulário). Dataclasses congeladas → `projection_data` → contrato TS gerado
  (`export_bi_schema`, drift test).
- **9 URLs / 8 views / 11 handlers** em `api/bi.py`, todos atrás de `backstage.view_bi`
  (`api/urls.py:199-208`, montado em `/api/v1/backstage/`).
- **Explorador:** 24 métricas em 9 famílias (`sales`, `sales_items`, `production`, `oven`,
  `cash`, `shelf`, `outage`, `payment`, `room`) × 20 dimensões, gramática estrita, ranking com
  `MAX_ROWS=60` e corte declarado; dimensões de contexto (`day_kind`, `temperature`, `rain`) só
  aparecem se `DayContext` tiver dado.
- **`BIView`** (`models/bi_view.py`): cenário salvo do explorador — config, não dado.
- **Materialização: zero.** Sem `django.core.cache` em nenhum `bi_*`, sem tabela agregada, sem view
  SQL, sem comando `refresh_*`. Política: ADR-021 §3 — só com gatilho medido (p95 > 2 s ou
  varredura > 12 meses por request); `bi_production.py:22-26` e BI-FORECAST-PLAN §13 repetem. As
  três coisas armazenadas são **entradas**, não agregados: `HistoricalSale*`, `DayContext`,
  `guestman.CustomerInsight` (agregado que o guestman mantém; o B.I. só lê).
- **Calculado na hora, sempre:** todas as leituras varrem `Order`+`HistoricalSale` (e
  `OrderItem`+`HistoricalSaleItem` quando pedem SKU/consumo — 353k linhas) a cada request. Ainda
  dentro do orçamento; `OrderItem.sku` **não tem índice** (`orderman/models/order.py:341`) e
  BI-INSIGHTS-MAP §9 já aponta como risco de escala.

### 1.4 Onde a superfície fica

- `surfaces/bi-nuxt` (:3007), 6 páginas, um único BFF catch-all (`server/api/v1/[...path].ts` →
  `proxyDjangoApi`), fetch sem poll e sem SSE, sem export CSV/XLSX/impressão. Tile na Central via
  `projections/hub.py:85` + `SHOPMAN_BI_BASE_URL`.
- ⚠️ **Drift de deploy:** o spec vivo do staging (`doctl apps spec get 40b86e35…`) **tem** o
  componente `bi-nuxt` e o domínio `bi.boulangerie.com.br`; o spec versionado no repo
  (`.do/app.staging-subdomains.yaml`) **não tem**. Um `apps update --spec` a partir do arquivo do
  repo derruba o B.I. do staging (mesma família do gotcha "spec do repo apaga segredos"). Fora do
  escopo desta frente; registrado para não morder.

---

## 2. Fontes hoje: onde vivem, onde terminam, silos e buracos

### 2.1 Yooga (histórico externo, jul/2024 → 20/jul/2026)

- **Origem:** API interna do painel Yooga, consolidada em `yooga-consolidado.xlsx` (Drive) —
  81.255 vendas autorizadas (NFC-e cstat=100; **canceladas não vêm**), ~380k itens no export,
  **353.009 linhas medidas no banco** do staging, 220 produtos, 4.769 clientes identificados.
- **Onde vive:** `HistoricalSale` (`source`, `external_id`, `occurred_at`, `total_q`, `discount_q`,
  `surcharge_q`, `payment` cru, `operator`, `modality` cru, `origin` cru, `table_label` cru,
  `is_delivery` derivado, `customer_external_id`, `customer_name`, `metadata`, `ingested_at`) e
  `HistoricalSaleItem` (`sale`, `seq`, `product_name`, `sku` texto indexado, `category`, `qty`,
  `unit_price_q`, `discount_q`, `line_total_q`). **Nada entra em `Order`, `Move`, `DayClosing`**
  (BI-PLAN §7; `historical_sale.py:1-6`).
- **Como foi importado:** `ingest_yooga --file var/…xlsx` no console do staging. Lê 14 das 23
  colunas de `Vendas`, 8 das 14 de `Itens`, 3 das 6 de `Produtos`. Dinheiro vira centavos por
  `Decimal`; data+hora viram tz-aware.
- **Onde termina:** 20/07/2026 (último dia do export). O nativo começa em 11/07/2026 — mas ver
  §2.2: o nativo até hoje **é seed/QA**, então na prática o passado real termina em 20/07 e o
  presente real ainda não começou.
- **Buracos na entrada (baratos de corrigir agora, caros depois):**
  - Descartadas: `ano, mes, dia_semana, hora_cheia` (deriváveis, ok) e `taxa_pagamento, telefone,
    endereco, bairro, observacao` (**perda real**: C3 "bons clientes do Yooga que nunca voltaram" e
    "$5 taxa de cartão por mês" estão 🔴 no catálogo por isso — BI-QUESTION-CATALOG §4).
  - **Sem lote:** reimportar o mesmo arquivo não duplica (chave natural), mas ninguém sabe *qual*
    arquivo entrou, *quando*, com *quantas* linhas, nem se o export mudou de forma entre versões.
  - **Sem transação nas vendas** (`_ingest_sales` faz `bulk_create` fora de `atomic`; só os itens
    são atômicos, `:195`). Falha no meio deixa cabeçalhos sem itens — e a regra "itens só de
    vendas que ainda não têm" completa depois, o que mascara o problema em vez de declará-lo.
  - **Sem validação de payload:** cabeçalho lido por posição; coluna renomeada no export vira
    `KeyError` no meio do lote, não erro na fronteira.
  - **`nfce_id` guardado e nunca lido.**
- **Silos:**
  - `sku` do Yooga é texto livre; ~7% das linhas do export **não têm SKU** e dobram por
    `nome:<produto>` (`bi_sales.py:246`); 27.177 linhas sem SKU só se classificam por categoria
    (`consumption.py:77-82`). Nenhuma delas jamais fará join com o nativo.
  - `modality`/`origin`/`table_label` cru são **inconfiáveis por decreto** (o balcão não preenchia
    com disciplina); só `is_delivery` é rótulo. `table_label` está guardado e não serve para nada.
  - Yooga não tem produção, forno, caixa, estoque, falta: `bi_production`, `bi_cash`, `bi_change`
    (hábito de troco) são nativo-only. **O passado do Yooga ensina demanda, só.**
  - `bi_customers` lê só `CustomerInsight` — o RFM tem **zero profundidade histórica** apesar de
    `customer_external_id`/`customer_name` estarem gravados.
- **Fragilidade documentada e não corrigida** (BI-INSIGHTS-MAP §9 item 3): **1 pedido de teste num
  dia apaga ~110 vendas Yooga daquele dia, sem alerta** — a regra "dia nativo vence" pula em
  silêncio (`sales_series.py:88-98`). Item 4: `orders_by_hour`/`orders_by_weekday` misturam as
  fontes sem rótulo (`bi_sales.py:117-118, 137-138`).

### 2.2 Nativo (Shopman)

- **Onde começa:** `orderman.Order` (`created_at`, `total_q`, `channel_ref`, `status`, `data` JSON,
  `snapshot` selado) + `OrderItem` (`sku` texto sem índice, `name`, `qty`, `line_total_q`) +
  `OrderEvent` (append-only, **ainda não lido pelo B.I.** — BI-INSIGHTS-MAP §0 aponta como o maior
  dado não lido: funil temporal do pedido).
- **O que o B.I. lê do `Order.data`:** `fulfillment_type` (só `pickup|delivery`; **o PDV abre toda
  comanda como `pickup`**, então "comeu na mesa" e "levou" saem iguais), `payment.method`,
  `payment.cash_received_q`, `payment.change_q` (única fonte de troco do sistema). Canal é coluna.
  Mesa/salão **não existem** (vínculo comanda↔mesa vetado pelo dono; salão é medido por
  `Session.opened_at→committed_at` + cesta + `DayContext.open_minutes`).
- ⚠️ **Estado real (medido em produção 18/08, SKU-REAL-PLAN §1.4):** 216 pedidos nativos (11/07 a
  18/08), **todos de seed, QA e piloto automático**; 322 movimentos de estoque, nenhuma venda real
  no ledger. E **o local nunca teve Yooga real** — só `source=seed`. Consequência para esta frente:
  não há passado nativo a proteger, e a janela para acertar identidade de produto (SKU) é agora.
- Produção/forno/falta/caixa: `WorkOrder`, `OvenRun`, `ShelfOutage`, `CashShift`… são ledgers ou
  quase; entram no B.I. direto. `soldout_at` **não é campo**: é preenchido pelo adapter
  `shop/adapters/demand.py:53-57` a partir de `ShelfOutage`.

### 2.3 NFC-e / fiscalman

- **O B.I. não lê nada do fiscal.** `fiscalman` **não tem models nem migrations** — só
  `classification.py`, `contracts.py` (dataclasses `FiscalDocumentResult` etc.) e o Protocol.
- O estado da emissão vive em **`Order.data`**: `nfce_access_key`, `nfce_number`, `nfce_series`,
  `nfce_protocol`, `nfce_status`, `nfce_danfe_url`, `nfce_qrcode_url`, `nfce_xml_url`,
  `nfce_cancelled`, `nfce_cancellation_protocol` (data-schemas.md:145-154), escritos por
  `shop/handlers/fiscal.py` e pelo adapter FocusNFe.
- Como **fonte futura** de B.I., a NFC-e tem valor próprio: (a) é a **verdade fiscal** para
  reconciliar venda declarada × venda registrada; (b) traz **canceladas** que o export do Yooga não
  trouxe; (c) o histórico Yooga já carrega `nfce_id` (81.255 vendas autorizadas = 81.255 chaves).
  Ela entra como tabela de aterrissagem própria (documento por chave de acesso), não como coluna do
  pedido — mas **só quando houver emissão real** (pós-alpha; NFC-e/DANFE é obrigação legal já
  registrada).

### 2.4 Contexto e referência (já são "dado, não código")

`DayContext` (feriado/comercial/véspera/volta, expediente congelado, clima; proveniência por bloco),
`ConsumptionRole` (3 leituras: `anchor|takeaway|hybrid`), `ProductConsumptionTag` (59 SKUs
curados, `reviewed=True` no seed), `SeatingSpot` (capacidade oficial: 8 mesas + 6 lugares de
balcão), `OutageReason`, `OperationEpisode`. Instalados por `setup_bi_reference` (⏳ pendente no
staging junto com `apply_catalog_taxonomy`). `HistoricalSale*` e `DayContext` **não têm Admin**;
`ConsumptionRole`/`ProductConsumptionTag`/`SeatingSpot` têm.

### 2.5 Dependências

`pyproject.toml` não declara **pandas, rapidfuzz nem pydantic** (zero import no repo; só menções
aspiracionais em planos arquivados). A única lib tabular é `openpyxl` (só o `ingest_yooga`). Toda
agregação é `defaultdict` + `Decimal` sobre `values_list`.

---

## 3. Log do PDV: o que existe e o encaixe

### 3.1 O que já existe (no `main`)

O "log do PDV em desenvolvimento" da missão **é o `cashman.Entry`** —
`packages/cashman/shopman/cashman/models/entry.py` (220 linhas), no `main` desde o PR #202
(WP-1 do CASHMAN-PLAN). O PR #198 (`backstage.POSEvent`) foi diagnosticado como terceiro remendo e
vai fechar sem merge; só a trava da gaveta sobrevive por cherry-pick (WP-8).

| Aspecto | `cashman.Entry` |
|---|---|
| Natureza | livro-caixa **append-only** por turno; guarda igual ao `stockman.Move` (`QuerySet.update/delete` levantam; `save` com pk levanta; `delete` levanta) |
| Campos | `shift` FK PROTECT, `operator` FK User, `approved_by` FK User null, `at` (default `timezone.now`, **carimbo do servidor**), `kind` (15 tipos), `amount_q` **assinado** (0 para evento sem dinheiro), `order_ref` texto indexado, `payment_ref` (intent do payman), `parent` FK self (correção/resposta), `reason`, `payload` JSON (schema por tipo em data-schemas.md) |
| Tipos | dinheiro entra: `float_in`, `sale` (≥0: pix/cartão passam pelo turno sem tocar a gaveta), `cod_settled`, `cash_in` · sai: `refund`, `cash_out` · contagem: `count`, `count_correction` · sem dinheiro: `drawer_open`, `drawer_unlock`, `change_requested/served/cancelled`, `receipt_result`, `note` |
| Invariantes no banco | `CheckConstraint` sinal-por-tipo; índices `(shift,id)`, `(operator,at)`, `(kind,at)`, `(at)`; `ordering=["at","id"]` |
| Escritores | só `cashman.services` (`open_shift`, `record`, `close_shift`, `correct_count`); WP-3 (#205) faz o `shop` gravar `sale/refund/cod_settled` na venda; WP-4 (#206) faz o backstage operar o turno pelo cashman |
| Volume esperado | ~100–150 vendas/dia + eventos de gaveta/troco/sangria/contagem → **~200–400 linhas/dia, ~100k/ano**. Trivial. |
| Granularidade | **um lançamento por acontecimento**, com autor, hora e o que responde a quê. É exatamente o formato que responde "quem abre a gaveta 3× mais", "destraves por operador", "em que horário" |

Hoje `bi_cash.py` lê `CashShift.difference_q` (por dia/operador), `CashMovement`
(sangria/suprimento) e `DayClosing.data.cash_shift_summary.payment_method_totals`. Pelo
CASHMAN-PLAN, o WP-4 troca isso por `count`+correções e `cash_out`/`cash_in` do livro, e o WP-8
acrescenta `drawer_openings`/`drawer_unlocks`/`change_requests` por operador e `drawer_by_hour`.

### 3.2 O encaixe nas três camadas

- **Camada 1 (ingestão):** o `Entry` **não precisa de tabela de aterrissagem** — ele *é* a fonte
  imutável, com carimbo do servidor e guarda de append-only. Criar uma cópia "crua" dele no B.I.
  seria o mesmo erro do #198 (segundo lugar para o mesmo fato). O critério: **fonte externa
  aterrissa; ledger nativo é lido no lugar.** Isso vale para `Order`, `Move`, `WorkOrder`,
  `ShelfOutage` também — o B.I. nunca copia o que a operação já grava de forma imutável.
- **Camada 2 (canônica):** um adaptador `cashman → eventos canônicos de caixa` (turno, operador,
  tipo, efeito, hora, pedido). Não há de-para: os tipos são fechados e do próprio sistema.
- **Camada 3 (leitura):** `bi_cash.py` e a família `cash` do explorador migram para o adaptador.

### 3.3 Incompatibilidades para apontar agora (barato) — nenhuma bloqueia

1. **Duplo trabalho iminente em `bi_cash.py`.** O WP-4 (#206, aberto) reescreve `bi_cash` para
   ler `Shift`/`Entry` diretamente; esta frente quer que ele leia pela camada canônica. Se os dois
   andarem separados, `bi_cash` é reescrito duas vezes em uma semana. **Proposta:** o WP-4 mergeia
   como está (não segurar o caixa por causa do B.I.); esta frente faz a passagem para o adaptador
   no seu passo P4 (§5), e o **WP-8 (B.I. sobre o livro) é executado dentro desta frente**, não à
   parte — uma passagem só. Pede alinhamento com quem toca o WP-8.
2. **`payload` sem schema publicado por tipo.** O model diz "schema em data-schemas.md"; o WP-1
   prometeu a seção. Antes de o B.I. ler `payload.drawer_raw` etc., a seção precisa existir e ter
   teste de contrato (o B.I. só lê chave documentada). Verificar no #205/#206.
3. **`note` é válvula de escape.** Um tipo livre com `amount_q=0` convida a contrabandear evento
   novo como anotação. Guarda barata: teste que falha se `Entry.Kind` ganhar valor sem métrica/rótulo
   correspondente no B.I., e revisão do uso de `note` na projection (aparece como "anotação",
   nunca é contado como outra coisa).
4. **`operator` é `User`, não `Operator`/crachá.** O B.I. por operador hoje já usa User (via
   `CashShift.operator`); consistente. Só registrar que "operador" no caixa = conta autenticada,
   e no forno = `operator_ref` texto do `OvenRun`. A dimensão `operator` do explorador cruza os
   dois por rótulo — bom o bastante enquanto o mesmo humano tiver o mesmo nome nos dois.
5. **Forma de pagamento não está no `Entry`** (`sale` guarda só o efeito em dinheiro; mix de
   meios é do `payman`, WP-2). Correto por desenho: a métrica `payment_received` continua lendo
   `iter_order_payments`/payman, não o caixa. Não misturar.
6. **Backfill (WP-5) roda o algoritmo de `close()` uma última vez** e cria `Entry` históricos com
   `at` = data do turno. O B.I. deve tratar lançamento de backfill como qualquer outro (o
   `payload` pode marcar `backfilled=True` para auditoria; leitura não distingue).

Nenhum destes exige mudança no `cashman`. Todos são combinações de ordem e contrato.

---

## 4. Inventário do que consome o B.I. hoje (a lista do que migra)

| # | Consumidor | Endpoint / projection | O que lê hoje | Migra para |
|---|---|---|---|---|
| 1 | `bi-nuxt` `pages/sales.vue` | `GET bi/sales/` → `bi_sales` | `Order`, `OrderItem`, `HistoricalSale`, `HistoricalSaleItem` (fusão inline 3×) | leitura via canônica (P2) |
| 2 | `bi-nuxt` `pages/explore.vue` | `GET bi/explore/` → `bi_explore` (24 métricas) | idem + `WorkOrder*`, `OvenRun`, `CashShift`, `Quant`/`Move`, `ShelfOutage`, `DayContext`, `SeatingSpot`, `Session` | famílias `sales`, `sales_items`, `payment` via canônica (P2); `cash` (P4); demais ficam |
| 3 | `bi-nuxt` `pages/forecast.vue` | `GET bi/forecast/` → `bi_forecast` → `sales_series` | `Order` + `HistoricalSale` via `daily_sales` | **já passa pelo funil**; ganha série materializada (P3) |
| 4 | idem (bloco troco) | `GET bi/change/` → `bi_change` | `Order.data.payment.*` (hábito, nativo-only) + `sales_series` | idem |
| 5 | `bi-nuxt` `pages/cash.vue` | `GET bi/cash/` → `bi_cash` | `CashShift`, `CashMovement`, `DayClosing.data` | `cashman.Entry` via adaptador (P4, com WP-4/8) |
| 6 | `bi-nuxt` `pages/index.vue` (produção) | `GET bi/production/` → `bi_production` | `WorkOrder*`, `OvenRun`, `QualityGrade` | **não muda** (ledger nativo, sem fonte externa) |
| 7 | `bi-nuxt` `pages/customers.vue` | `GET bi/customers/` → `bi_customers` | `guestman.CustomerInsight`, `Customer` | não muda em v1; ganha profundidade histórica quando o de-para de cliente existir (fora de escopo) |
| 8 | `bi-nuxt` cenários | `bi/views/` → `BIView` | config | não muda |
| 9 | `hub-nuxt` tile | `projections/hub.py:85` | permissão + URL | não muda |
| 10 | `services/room.py:154` | `bi_explore._consumption_modes` | cesta nativa+histórica | passa a consumir a canônica (P2) |
| 11 | `sales_series.py:56` | `bi_sales._local_datetime_window` | helper | vira utilitário da canônica |
| 12 | `bi_calibrate` (comando, só imprime) | `bi_payments.normalize_historical_payment` | vocabulário em código | lê `PaymentMethodAlias` (P1) |
| 13 | `export_bi_schema` + `test_bi_schema_export` | dataclasses `bi_*` | contrato TS | não muda (contratos das projections são preservados) |
| 14 | 11 suítes `test_bi_*` (~149 testes) + `test_day_context`, `test_shelf_outage`, `test_seed_forecast_history`, `test_day_similarity` | `build_bi_*` | — | **são o teste de equivalência da migração**: precisam continuar verdes sem edição em cada passo |
| 15 | `bi-nuxt/tests` (36 `it`) | `presentation/bi.ts` | — | não muda |
| — | Admin/Unfold | — | — | **não existe por política** (`check_unfold_canonical.py:352`, exceção "app dedicado bi-nuxt") — as telas de de-para (P1) nascem no Admin como CRUD de configuração, o que a regra da casa permite (Admin configura, não opera) |
| — | Export CSV/XLSX/impressão | — | — | não existe |
| — | Jobs periódicos | `maintenance_worker` | só **alimenta** o B.I. (`reconcile_shelf_outages`, `stamp_business_days`, `detect_operation_episodes`, `sweep_stale_oven_runs`) | ganha `refresh_bi_daily_series` (P3) |
| — | Sugestão de produção | `shop.services.production.suggest_for` | independente do B.I. (`craft.suggest` + `adapters/demand.py`) | não muda; questão aberta em BI-INSIGHTS-MAP §9 (fórmula deveria ver o Yooga?) fica para depois |

Nenhuma outra superfície Nuxt chama `bi/*`. Toda leitura entra por um único BFF catch-all.

---

## 5. Plano de migração incremental

### 5.0 Princípios (herdados, não inventados)

- **As leituras atuais nunca param.** Endpoints, dataclasses e contrato TS **não mudam** em nenhum
  passo. Cada passo troca o que está *debaixo* de um `build_bi_*` e prova equivalência: mesma
  janela, mesmo número antes e depois (as 11 suítes `test_bi_*` continuam verdes sem edição; onde
  a fixture não cobre, teste novo compara o resultado do caminho antigo com o novo na mesma janela
  antes de o antigo ser apagado).
- **Uma pergunta, um dono.** Cada regra de fusão/de-para sai de onde está replicada e passa a
  ter um módulo dono. Nada de "cópia para migrar depois".
- **Fonte externa aterrissa; ledger nativo é lido no lugar.** O B.I. não copia `Order`, `Move`,
  `Entry`, `WorkOrder`.
- **De-para é dado, sugestão é máquina, confirmação é humana.** Toda tabela de alias tem
  `status` (`proposed|confirmed|rejected`), quem confirmou e quando; leitura só usa `confirmed`.
  Nunca mescla em silêncio.
- **Materializar só com motivo declarado.** A ADR-021 §3 continua valendo; o único agregado
  materializado do v1 (série diária, P3) tem motivo arquitetural (alarmes e o guard da fusão
  precisam de um lugar persistido para declarar), não de performance.
- **Migrações append-only, nenhuma destrutiva.** Tabelas novas + FK nula em `HistoricalSale` com
  backfill de lote "importação legada".
- **Sem rename em massa** (hostil a merge). Nada se move; o novo nasce em
  `shopman/backstage/bi/` (`ingest/`, `sources/`, `canonical.py`, `mapping.py`) e as projections
  ficam onde estão — elas *são* a camada de leitura.
- **Libs:** `pydantic` entra no P0 (validação de linha na fronteira do xlsx/CSV); `rapidfuzz`
  entra no P1 (sugestão de alias). `pandas` **só quando uma transformação pedir** — no v1 nenhuma
  pede (agregações são ORM + dict); fica sancionada, não instalada por antecipação.

### 5.1 Ordem e conteúdo de cada passo

**P0 — Ingestão com lote (Yooga; 1 PR). ✅ ENTREGUE 2026-08-18 (branch `feat/bi-import-batch`).**
Prova a camada 1 na fonte que já existe. Como saiu: `backstage.ImportBatch` (migração `0022`,
lote legado por origem para o que já estava carregado), FK **obrigatória** `HistoricalSale.batch`,
importador em `shopman/backstage/bi/ingest/yooga.py` (pydantic por linha, uma transação, hash
recusado só entre lotes concluídos, falha registrada como `failed`), `metadata` com telefone
hash+últimos 4 / bairro / endereço / taxa / observação, Admin somente leitura no grupo novo
"B.I." (Importações, Vendas históricas com itens inline), `view_*` para o Gerente,
`pydantic` declarado no `pyproject`. Detalhe original do passo abaixo.
- `bi.ImportBatch`: `source`, `file_name`, `file_sha256` (**unique com source**), `imported_at`,
  `imported_by`, `rows_read`, `rows_created`, `rows_skipped`, `status` (`done|failed`),
  `error`, `notes`. Reimportar o mesmo arquivo = recusa declarada (não silêncio, não duplicação).
- `HistoricalSale.batch` FK nula → migração de dados cria um lote `legacy` por `source` para as
  linhas existentes (`file_sha256` vazio, `notes="anterior ao controle de lote"`).
- `ingest_yooga` passa a: validar cada linha por modelo `pydantic` (`YoogaSaleRow`, `YoogaItemRow`,
  `YoogaProductRow` — coluna faltando ou tipo errado é erro **na fronteira**, com número da linha);
  gravar em **uma transação por lote** (vendas + itens); guardar em `HistoricalSale.metadata`
  as colunas hoje descartadas (`telefone` **mascarado**, `bairro`, `endereco`, `taxa_pagamento`,
  `observacao`) — o export volta a ser completo, e a reimportação **completa** o que já está lá
  (BI-PLAN §7 já previa "ingest completável").
- `HistoricalSale`/`HistoricalSaleItem`/`ImportBatch` ganham **Admin read-only** (Unfold, gate).
- **Não muda leitura nenhuma.** Aceite: `ingest_yooga` sobre o mesmo arquivo 2× → 1 lote, 0
  linhas novas na segunda; `make test-backstage`, `make admin`.

**P1 — De-paras como dado (Yooga). ✅ ENTREGUE 2026-08-19 (branch `feat/bi-aliases`, sobre a do P0).**
Como saiu: `ProductAlias` (por fonte; SKU ou nome → `offerman.Product`, FK nula para extinto),
`CategoryAlias` e `PaymentMethodAlias` (vocabulários por trecho, em ordem, **independentes de
fonte**), migração `0023` só de schema; `CATEGORY_READING` e `_HISTORICAL_VOCABULARY` **apagados
do código** — a leitura carrega `category_readings()`/`payment_vocabulary()` (só `confirmed`); as
regras padrão moram no `seed._seed_bi_aliases` e no `setup_bi_reference` (convenção da casa:
referência não vai em migração); `suggest_aliases` (rapidfuzz; nunca confirma, nunca sobrescreve,
declara o que não achou); Admin de curadoria com ações confirmar/rejeitar que assinam; Gerente
cura. ⚠️ **O contrato canônico + `bi/sources/yooga.py` passaram para o P2** — nascem junto com o
primeiro leitor, não antes. Detalhe original do passo abaixo.
- Tabelas (base abstrata comum com `status`, `score`, `suggested_at`, `confirmed_by`,
  `confirmed_at`, `note`):
  - `ProductAlias(source, external_sku, external_name → product FK null)` — para os 7% sem SKU o
    alias é por nome. **Sentido: aponta para `offerman.Product`** (§6.b).
  - `CategoryAlias(source, external_category → collection_ref, reading)` — absorve
    `CATEGORY_READING` (a leitura de consumo por categoria vira coluna editável; o código some).
  - `PaymentMethodAlias(source, external_value → method_key)` — absorve `_HISTORICAL_VOCABULARY`.
  - `ProductConsumptionTag` **fica como está** (já é o molde).
- Comando `suggest_aliases --source yooga [--kind product|category|payment]`: `rapidfuzz`
  (`token_set_ratio` sobre nome normalizado, com SKU exato quando existir) → linhas
  `status=proposed` com `score`; nunca confirma. Admin (Unfold, `list_editable` de status, filtro
  por `status`/`score`) para a confirmação humana. Migração de dados carrega as 26 + 15 regras
  atuais como `confirmed` (são curadoria já feita) — a leitura não muda de resposta.
- `shopman/backstage/bi/canonical.py`: dataclasses `CanonicalSale` (`source`, `external_ref`,
  `occurred_at` local, `channel_key`, `is_delivery`, `total_q`, `discount_q`, `payment_key`,
  `customer_key`, `operator_key`) e `CanonicalSaleLine` (`sale`, `product_ref` **resolvido pelo
  alias**, `external_sku`, `name`, `category_key`, `qty`, `line_total_q`, `reading`); e
  `bi/sources/yooga.py` com `iter_sales(window)`/`iter_lines(window)` produzindo-as. É código de
  extração do que já existe em `sales_series`/`bi_sales`/`bi_explore`; sem cache, sem tabela.
- Aceite: `test_bi_*` verdes sem edição; teste novo prova que `bi_calibrate` e a leitura de
  consumo respondem igual com o de-para vindo da tabela.

**P2 — Leitura pela canônica (nativo entra; 2 PRs).** Prova o padrão de ponta a ponta.
- `bi/sources/orderman.py` (mesmo contrato, lendo `Order`/`OrderItem`, `product_ref = sku`
  nativo, `channel_key = channel_ref`, `payment_key` via `iter_order_payments`).
- `bi/canonical.py` ganha o **compositor**: `sales(window)` aplica **"o dia nativo vence" em UM
  lugar** e devolve a série já conciliada, com o **guard declarado** (dia com < N nativos e > M
  históricos vira `warning` na resposta, não silêncio — fecha BI-INSIGHTS-MAP §9 item 3).
- `sales_series.daily_sales`, `bi_sales`, `bi_explore._sales_rows/_sales_item_rows/_payment_rows/
  _consumption_modes` e `services/room.py` passam a consumir a canônica; **as 5 réplicas da
  fusão são apagadas.** `orders_by_hour/weekday` ganham rótulo de fonte (item 4).
- Aceite: equivalência numérica em fixture com os dois tipos de dia (só histórico, só nativo,
  misto); `test_bi_schema_export` sem drift; `bi-nuxt` `npm run test` + `typecheck`.

**P3 — Camada de leitura materializada (1 PR).** Só o que tem motivo.
- `bi.DailySalesFact` (`date`, `source`, `channel_key`, `revenue_q`, `orders`, `cash_orders`,
  `payments_known`, `refreshed_at`, `batch`/`warning`) — refeita por `refresh_bi_daily_series
  --days N` no `maintenance_worker` (ciclo de 300 s, ADR-003 intacto) e por sinal de lote novo
  (P0). `sales_series.daily_sales` lê a tabela; `forecast`/`change`/`sales` herdam. Recomputável
  do zero em segundos.
- É a única materialização do v1. Motivo: **alarmes (roadmap) e o guard da fusão precisam de um
  lugar persistido, e a projeção lê a mesma série 30–60 vezes por request.** O resto continua na
  hora até o gatilho da ADR-021 disparar — e quando disparar, o formato já existe.
- Aceite: `daily_sales` materializado == calculado (teste de igualdade); p95 medido antes/depois.

**P4 — Caixa: `cashman.Entry` entra pelo padrão provado (1 PR, após WP-4 mergeado).**
- `bi/sources/cashman.py` (`iter_cash_events(window)` → `CanonicalCashEvent`: `shift`,
  `operator_key`, `kind`, `amount_q`, `at`, `order_ref`, `parent`). `bi_cash` e a família `cash`
  do explorador migram; **o WP-8 do CASHMAN-PLAN (por operador: aberturas, destraves, troco;
  `drawer_by_hour`) é entregue aqui, uma vez.** Contrato TS regenerado.
- Aceite: `test_bi_business` (caixa) verde; `bi-nuxt/cash.vue` sem mudança de contrato além do
  WP-8; teste de que todo `Entry.Kind` tem leitura.

**P5 — Fonte nova pelo padrão: NFC-e (quando houver emissão real; fora do v1).** Tabela de
aterrissagem própria (`FiscalDocument`: chave de acesso, número/série, status, valor, xml/danfe,
`batch`), adaptador `bi/sources/nfce.py`, reconciliação venda × documento como métrica. Prova
que "fonte nova = importador + tabela + adaptador; nada mais muda". Não implementar agora.

### 5.2 Como as leituras continuam funcionando durante a transição

| Passo | O que o usuário do B.I. vê mudar | O que muda por baixo |
|---|---|---|
| P0 | nada (Admin ganha 3 telas read-only) | lote/hash/validação/transação |
| P1 | nada (Admin ganha 3 telas de de-para com sugestões) | regras em código viram linhas confirmadas; contrato canônico existe mas ninguém o lê ainda |
| P2 | `sales`/`explore` ganham `warning` de dia apagado e rótulo de fonte em hora/dia da semana | 5 réplicas da fusão somem; leitura passa pela canônica |
| P3 | previsão e painel de vendas ficam mais rápidos; nada mais | série diária vira tabela recomputável |
| P4 | `cash.vue` ganha o WP-8 | `bi_cash` sai de `CashShift`/`CashMovement`/`DayClosing.data` |

Cada passo é um PR com base `main`, gates da casa (`make test-backstage`, `make admin`, `ruff`,
`bi-nuxt` test+typecheck, `migrate` de banco zerado **e** de banco com dados), e pode parar sem
deixar meio-caminho: P0 sozinho já é melhor que hoje; P1 sozinho já é melhor que hoje.

### 5.3 Ordem com as outras frentes

- **CASHMAN WP-3/WP-4 (#205/#206) primeiro**, depois P4. P0–P3 não tocam caixa e podem andar em
  paralelo aos WPs do caixa. WP-8 é absorvido por P4 (combinar com quem o tocaria).
- **SKU-REAL** (`plano/sku-real`): se rodar **antes** do P1, `ProductAlias` nasce com muitos
  matches exatos (SKU Yooga == SKU do catálogo) e a sugestão fuzzy vira exceção; se rodar depois, o
  alias absorve a diferença até lá e o `cascade_rename` do `refs` atualiza `product FK`, não texto
  — o alias aponta para FK justamente para sobreviver ao rename. **Não bloqueia; melhora.**
- **`setup_bi_reference` + `apply_catalog_taxonomy` no staging** (⏳ pendência do dono) seguem
  independentes; P1 depende de `ConsumptionRole` existir (P1 roda o `setup_bi_reference` no seu
  próprio deploy se ainda não rodou).
- **Consulta de perfis** (frente separada): se existir, entra como cliente do P2 (`bi/sources/*` +
  canônica) — não desta lista.

---

## 6. Decisões do dono (tomadas em 2026-08-18 — as recomendações foram acatadas)

**a) Canônica persistida ou canônica como contrato?**
A missão fala em "modelos unificados para onde todas as fontes convergem". Duas leituras:
- **(i) Tabelas `Sale`/`SaleLine` materializadas**, alimentadas por sinal do `Order` + backfill
  do histórico. Custo: um segundo lugar para cada venda (Core sagrado; ADR-021 §3 sem gatilho),
  sincronização a manter (pedido editado/cancelado depois), e o mesmo padrão que o #198 repetiu no
  caixa. Ganho: SQL simples sobre uma tabela.
- **(ii) ⭐ Contrato canônico (dataclasses + iteradores por fonte) + de-paras como tabelas +
  materialização só na camada de leitura (P3).** Custo: leitura continua percorrendo as fontes
  (hoje já faz, dentro do orçamento). Ganho: nenhuma cópia de ledger; a regra tem um dono; se o
  gatilho de performance disparar, a materialização entra na camada 3 sem mexer na 2.
  **Decidido: (ii).**

**b) Para onde aponta o de-para de produto?**
`ProductAlias.product` → `offerman.Product` (identidade do catálogo, sobrevive ao SKU-REAL via
FK) **ou** um "produto do B.I." próprio (desacoplado do catálogo, com produtos extintos como
linhas). **Decidido: `offerman.Product`** com `product` **nulo permitido** para produto extinto
(o alias guarda `external_name` e o B.I. lê pelo nome quando não há FK) — não inventa um segundo
cadastro de produto. Isso encosta na pergunta 3 do SKU-REAL (Yooga adota código real ou numeração
nova) — o alias funciona nos dois cenários.

**c) Telefone do cliente no `metadata` do histórico (P0):** guardar mascarado (últimos 4) para
permitir join futuro com `guestman` por hash, ou não guardar? **Decidido: hash + últimos 4** —
o join C3 ("bons clientes que nunca voltaram") depende disso e é a pergunta 🔴 mais cara de
perder; dado pessoal fica fora do claro.

---

## 7. Roadmap (desenhado, NÃO implementar)

### 7.1 Cenários com IA (meia página)

**O que é.** O B.I. lê **só a camada de leitura** (série diária materializada, agregados do
explorador já calculados — nunca `Order`, nunca `HistoricalSale`), monta um contexto compacto
(últimos 28 dias vs. dias parecidos; sobra/falta por SKU; caixa por operador; alarmes disparados
na semana) e pede ao provedor **cenários** — "se a terça de véspera de feriado repetir a forma
do ano passado com o patamar de agora, a produção de X fica curta em ~N; três opções: assar +N às
6h, +N/2 e reforçar às 10h, não mexer e aceitar esgotar às 11h" — cada um com o dado que o
sustenta e o que ele **não** sabe.

**Infra existente.** `shop/services/copy_assist.py` já fala com o provedor (`AI_ASSIST_PROVIDER/
API_KEY/MODEL`, hoje `anthropic` + `claude-opus-5`), com `is_configured()` para a tela não
oferecer o que não pode cumprir. É service, não adapter (um provedor só, ADR-001). O B.I. reusa
o transporte e o padrão; **não** reusa a voz da marca (aqui é linguagem de gestor, sentence case,
sem travessão, em pt-BR).

**Contrato.** Entrada: `ScenarioRequest{window, focus: production|cash|sales, aggregates}` —
`aggregates` são dataclasses da camada 3 serializadas, com `unit` (a IA nunca vê centavo cru sem
unidade). Saída: `ScenarioReport{generated_at, model, inputs_hash, scenarios[]{title, basis[],
proposal, unknowns[]}}` **versionado** em tabela (`bi.ScenarioReport`, append-only, com o hash
das entradas para reproduzir "o que a IA viu"). Tela: seção "Cenários" no `bi-nuxt` (`/scenarios`),
lista de relatórios por data, botão "gerar" só se `is_configured()`.

**Regras.** Propositivo: nunca executa, nunca cria fornada, nunca muda RuleConfig — o gestor
lê e decide na tela de plano. Nada de dado pessoal no prompt (cliente, telefone). Custo/latência
declarados na tela ("gerado em 12 s, modelo X"). Falha do provedor é ausência, não silêncio.
Roda sob demanda; se um dia virar semanal, entra como comando no `maintenance_worker` com
cooldown, nunca por request de tela.

### 7.2 Alarmes configuráveis (meia página)

**Tabela `bi.AlertRule` (Admin, CRUD de configuração):** `ref`, `label`, `metric` (chave da
camada de leitura: `daily_revenue`, `daily_orders`, `cash_difference_by_operator`,
`import_batch_age`, `native_day_overrides_history`, `unaliased_lines_share`, `soldout_before`),
`condition` (`below|above|missing`), `threshold` (número + `unit`, ou `%` do baseline),
`window` (`day|7d|28d`), `severity` (`info|warning|critical`), `channel` (`operator_alert|email`
— reusa `OperatorAlert`, o bus cross-surface com ack que já existe, e `notification_email`),
`cooldown_minutes` (**obrigatório**, sem default zero), `is_active`, `last_fired_at`.
**Baseline:** média (ou mediana) do **mesmo dia da semana** nas últimas N semanas, lida da série
diária materializada (P3) — sem ML, sem modelo; a régua é a mesma que o dono já aprovou para a
projeção ("dias parecidos", forma do histórico).

**Job:** `evaluate_bi_alerts` no `maintenance_worker` (300 s), avalia cada regra ativa contra a
camada 3, respeita cooldown, grava `bi.AlertEvent` (append-only: regra, valor medido, baseline,
disparou/não) e notifica pelo canal. Silêncio do próprio job também é alarme (o `maintenance_worker`
já tem `last_run` por comando).

**Os 5 primeiros (sugeridos):**
1. **Silêncio de importação** — fonte com cadência esperada (`ImportBatch.expected_every_days`
   por fonte) sem lote novo há mais que o esperado. É o candidato forte da missão e o mais
   barato: sai direto do P0. (Hoje o Yooga é importação única; o alarme nasce para NFC-e e para
   qualquer export recorrente.)
2. **Dia abaixo do baseline** — `daily_revenue` do dia fechado < X% da média do mesmo dia da
   semana (4 semanas), excluindo dias fechados e episódios (`OperationEpisode` já marca "dia
   atrapalhado"). Severidade por faixa (70% warning, 50% critical).
3. **Dia nativo apagou histórico** — o guard do P2 como alarme: dia com < N pedidos nativos e
   > M vendas históricas na mesma data (o "pedido de teste apagou 110 vendas" documentado).
4. **Quebra de caixa acumulada** — `Σ count + count_correction` por operador em 7 dias fora da
   faixa; sai do P4 (`cashman.Entry`). Sem ranking público: alerta para o gerente, não mural.
5. **Linhas sem de-para** — após um lote novo, % de linhas com `ProductAlias`/`CategoryAlias`
   `proposed` ou ausente acima de X%: "há curadoria pendente antes de o número ser confiável".
   Fecha o ciclo humano da camada 2.

Candidatos seguintes: SKU que esgotou antes das 10h em 3 dias seguidos (`ShelfOutage`),
fornada planejada sem realização até a hora Y (já existe como episódio; virar alarme é ligar
o canal), `OrderItem` sem índice quando o p95 do explorador passar de 2 s (alarme técnico, gatilho
da ADR-021).

---

## 8. Fora de escopo (declarado)

- Warehouse/plataforma externa, Airflow, dbt, Kafka, data lake (vetados pela missão).
- Índice composto em `Order`/`OrderItem` (Core; só quando o gatilho da ADR-021 disparar).
- De-para de **cliente** (Yooga `customer_external_id` → `guestman.Customer`) — o P0 guarda o
  que permite fazê-lo depois; a regra de junção é frente própria (perfis).
- Deploy do `bi-nuxt` no spec do repo (drift do §1.4) — infra, não B.I.
- Reescrever a fórmula de sugestão de produção para enxergar o Yooga (BI-INSIGHTS-MAP §9, aberto).
- Mover projections/serviços de lugar (rename em massa é hostil a merge; feature primeiro).
