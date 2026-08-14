# BI-INSIGHTS-MAP — mapa de perguntas de negócio e possibilidades de insight

> **Status:** 🔍 ANÁLISE para iteração com o dono (2026-08-14). Não é plano de execução:
> nada aqui vira código sem OK explícito. Mandato: "análise profunda das possibilidades
> de insight — com os dados que JÁ existem e com os que PODEMOS passar a capturar".
>
> **Base assumida:** mundo pós-merge do PR #151 (B.I. F0–F9: `OvenRun`, `HistoricalSale`,
> painéis, explorador, `BIView`) e da fila C1–C6 (#144/#146/#148/#149/#152 — write-offs
> `perda_vencido`/`perda_nao_conformidade`, FEFO, preço por lote). O que depende de cada
> um está marcado. Inventário de dados verificado no código em 2026-08-14 (main +
> branch do PR #151); citações apontam o arquivo real.

---

## 0. Sumário executivo

O levantamento varreu os models de pedidos, produção, estoque, caixa, clientes,
marketing e o histórico Yooga. Conclusões de uma linha:

1. **O explorador já responde mais do que os 3 exemplos curados mostram** — há ~12
   cenários de valor imediato dentro da gramática atual (§2). Custo: só curadoria.
2. **A maior mina inexplorada com dado já existente é o funil temporal do pedido**:
   todos os status têm timestamp de coluna e o `OrderEvent` guarda cada transição —
   ninguém lê isso ainda (§3, L1).
3. **A segunda maior é o próprio ledger de estoque**: a hora de esgotamento de cada SKU
   (sold-out) é derivável dos `Move`s sem capturar nada novo (§3, L2).
4. **A captura nova de melhor custo/benefício é re-ingerir o Yooga com as colunas hoje
   descartadas** (telefone, bairro, taxa de pagamento): destrava RFM histórico, resgate
   de clientes perdidos e geografia de delivery por ~zero risco (§4, N1).
5. **Uma pergunta que parece respondível NÃO é:** "a campanha X vendeu?" — não existe
   atribuição campanha→venda (§4 N6). E uma segunda, "o forno 2 queima mais?", foi
   **arquivada pelo dono**: a casa tem um forno só (§4 N3).
6. **Etapas de produção: a concepção sempre foi ter timestamps por etapa — o código
   não honra** (`apply_advance_step` sobrescreve o carimbo a cada avanço). É correção
   de alta prioridade, barata e fora do core (§4, N9).
7. O levantamento também expôs dívidas de honestidade do dado que não são insights,
   mas contaminam qualquer leitura se ficarem mudas (§6).

---

## 1. O que já existe (fatos verificados)

**Painéis (PR #151):** vendas (série diária fundida Shopman+Yooga com "dia nativo
vence", mix por canal, top SKUs, pedidos por hora e por dia-da-semana, comparação com
período anterior), produção (rendimento, perda, mix de qualidade, tempo de forno com
cobertura declarada), caixa (quebra por dia/operador, sangrias, mix de meios de
pagamento via `DayClosing`), clientes (foto RFM, novos por semana).

**Explorador (`bi_explore.py`):** 9 métricas × dimensões compatíveis, até 2 eixos,
janela até 5 anos, ranking com corte declarado, cenários salvos (`BIView`). Gramática:

| Métrica | Dimensões |
|---|---|
| Faturamento, Pedidos, Ticket médio | tempo, canal, hora, dia-da-semana, fonte |
| Qtd vendida | tempo, SKU, fonte |
| Qtd produzida | tempo, receita, forno, operador, dia-da-semana, grau |
| Perda de produção | tempo, receita, forno, operador, dia-da-semana, defeito |
| Rendimento | tempo, receita, forno, operador, dia-da-semana |
| Tempo de forno | tempo, receita, forno, operador |
| Quebra de caixa | tempo, operador |

**Dados vivos e ainda não lidos por ninguém:** timestamps por status do `Order`
(`accepted_at`…`returned_at`) + ledger `OrderEvent` com cada transição carimbada;
`Move` (ledger imutável, 7 kinds, indexado por tempo); blocos de desconto em
`Order.snapshot.pricing` e `OrderItem.meta._disc`; `cancellation_reason`/`cancelled_by`;
`SessionEvent` (linha a linha do carrinho/comanda); 81.255 vendas × ~380k itens Yooga
com categoria e desconto por linha; `CustomerInsight` com `preferred_hour`,
`favorite_products`, `predicted_ltv_q` (os painéis só leem segmento e ticket).

---

## 2. Já dá — cenários curados do explorador (custo: só curadoria)

Hoje há 3 exemplos (`EXPLORE_EXAMPLES` em `surfaces/bi-nuxt/app/presentation/bi.ts`).
Todos os cenários abaixo cabem na gramática atual, sem uma linha de backend:

| # | Cenário (config) | Pergunta de negócio | Decisão que muda |
|---|---|---|---|
| C1 | Faturamento · hora × dia-da-semana | Qual o mapa de calor da semana, com 2 anos de história? | Escala de equipe, horário de fornada, horário de funcionamento |
| C2 | Pedidos · dia-da-semana × canal | Que dia cada canal pesa? | Alocação de produção por dia; promoções por canal |
| C3 | Ticket médio · canal | Delivery paga o custo que carrega? | Preço/frete por canal |
| C4 | Faturamento · tempo × fonte | A casa nova já vende como a antiga? (série longa rotulada) | Meta de rampa pós-cutover |
| C5 | Qtd vendida · SKU × fonte | O que vendia no Yooga e sumiu no Shopman (e vice-versa)? | Resgatar SKU esquecido no cardápio 2027 |
| C6 | Perda · defeito × receita *(exemplo atual)* | Onde a perda se concentra? | Ajuste de processo por receita |
| C7 | Perda · operador | Perda é de processo ou de pessoa? | Treinamento dirigido (nunca punitivo — ver §6.8) |
| C8 | Perda · dia-da-semana | O domingo perde mais? | Reforço/escala no dia crítico |
| ~~C9~~ | ~~Rendimento · receita × forno~~ | ❌ **fora** — a casa tem um forno só (decisão do dono, §4-N3) | — |
| C10 | Tempo de forno · receita *(exemplo atual)* | Tempo real vs planejado por receita | Recalibrar `planned_seconds` das receitas |
| C11 | Qtd produzida · grau × receita | Mix de qualidade por receita ao longo do tempo | Onde investir em consistência |
| C12 | Quebra de caixa · operador | Quebra é sistêmica ou concentrada? | Auditoria/treinamento de caixa |

**Ressalva de honestidade:** C10–C11 e tudo que depende de `OvenRun` começa a valer
quando o bi-nuxt + F2 estiverem em produção e a equipe adotar o timer — o dado nasce
zerado; a cobertura declarada nos painéis é o KPI de adoção (já existe:
`oven_coverage_percent`).

**Proposta:** promover C1–C8 e C10–C12 a exemplos curados na página Explorar (mexe só
no array do cliente, decisão de F9: exemplos são chips de partida, sem tocar seed).

---

## 3. Leitura nova — dado existe, ninguém lê (sem captura nova)

Formato: **Pergunta · Fonte · Esforço · Valor (decisão que muda)**.

### L1 ⭐ Funil temporal do pedido (lead time por etapa)
- **Pergunta:** quanto tempo um pedido leva de criado→aceito→pronto→entregue, por
  canal, hora e dia? Onde está o gargalo — cozinha, balcão ou entrega? A confirmação
  otimista está funcionando (tempo de aceite ~0)?
- **Fonte:** colunas `accepted_at`/`preparing_at`/`ready_at`/`dispatched_at`/
  `delivered_at`/`completed_at` do `Order` (todas existem, gravadas no `save()`;
  `packages/orderman/.../models/order.py`). Precisão fina no `OrderEvent`
  (`status_changed` com payload old/new + `created_at`).
- **Esforço:** leitura nova média — projection `bi_orders` ou 1–2 métricas novas no
  explorador ("minutos até pronto", "minutos até entregue") com dimensões canal/hora/
  dia-da-semana. ⚠️ Armadilha conhecida: os `*_at` são first-write-wins — o recall
  `ready→preparing` não atualiza nada; para percentis honestos, ler do `OrderEvent`
  (ou declarar a limitação). Sem índice nos `*_at` — no volume atual não dói (ADR-021
  §3 é o gatilho).
- **Valor:** é O dado operacional que nenhuma superfície responde hoje. Alimenta a
  promessa ao cliente (memória da casa: acompanhamento nunca promete o que não
  cumpre), o SLA por canal e o dimensionamento da cozinha por faixa horária.

### L2 ⭐ Hora de esgotamento por SKU (sold-out — sinal de subprodução)
- **Pergunta:** a que horas cada SKU esgota, em que dias? O que esgota antes das 15h
  sistematicamente (= dinheiro deixado na mesa)?
- **Fonte:** ledger `Move` (imutável, indexado `(quant, timestamp)`): o instante em que
  o saldo acumulado do dia chega a zero é derivável por SKU/posição. Nada a capturar.
- **Esforço:** leitura nova média (reconstrução do saldo intradia por SKU; janela
  limitada).
- **Valor:** converte direto em quantidade planejada da fornada seguinte — o elo entre
  B.I. e o `suggest_production` existente. Provavelmente o insight com efeito mais
  imediato no caixa da Nelson.

### L3 Descontos concedidos por tipo
- **Pergunta:** quanto a casa dá de desconto por mês, quebrado por cupom, desconto
  manual, funcionário, happy hour, fidelidade? Quem autoriza os manuais?
- **Fonte:** `Order.snapshot.pricing` (blocos `discount`/`coupon`/`manual_discount`/
  `employee_discount`/…) + `OrderItem.meta._disc`. Durável, mas JSON — agregação em
  Python, não SQL (ok no volume).
- **Esforço:** leitura nova pequena-média (métrica "descontos concedidos" no
  explorador, dimensão tipo × tempo × canal).
- **Valor:** hoje o custo das políticas de preço é invisível. Auditoria do desconto
  manual (quem, quanto, com que razão) é controle interno básico de caixa.

### L4 Cancelamentos por motivo
- **Pergunta:** onde se perde venda — PIX expirado, confirmação estourada, estoque,
  cliente desistiu? Por canal e horário?
- **Fonte:** `data.cancellation_reason` (códigos de máquina conhecidos: `pix_timeout`,
  `card_timeout`, `confirmation_timeout`, `customer_requested` + texto livre),
  `cancelled_by`, actors semânticos do lifecycle (`auto_reject_oos`, …).
- **Esforço:** leitura nova pequena — normalizar por whitelist de códigos conhecidos +
  balde "(outros)" declarado (o padrão "(sem motivo)" do explorador já existe).
  Estruturar o código na escrita é a N5 (§4).
- **Valor:** cada `pix_timeout` é uma venda quase fechada; se dominar o ranking, a
  ação é prazo/UX de pagamento, não produção.

### L5 Comparação com o mesmo período do ano anterior (YoY)
- **Pergunta:** este agosto está melhor que o agosto passado? (Páscoa, festas, inverno —
  sazonalidade de padaria é anual, e a janela "imediatamente anterior" do F7 não a vê.)
- **Fonte:** as mesmas dos painéis; o Yooga dá 2 anos de base.
- **Esforço:** leitura nova pequena — segundo modo de `previous` ("ano anterior") no
  contrato; a UI já sabe desenhar comparação.
- **Valor:** planejamento de compras (Buyman) e de produção por estação; meta honesta
  de crescimento.

### L6 Cesta — o que vende junto (attach rate)
- **Pergunta:** o que acompanha o croissant? Café puxa doce? Qual attach rate de
  bebida por período? (É também a fundação da regra B, ver N2.)
- **Fonte:** co-ocorrência de itens por venda — `OrderItem` por `order` e
  `HistoricalSaleItem` por `sale` (380k linhas históricas: base estatística real).
- **Esforço:** leitura nova média (pares/combos mais frequentes; janela limitada).
- **Valor:** combos, sugestão no storefront, posição de vitrine, precificação de
  bundle (Offerman já tem bundles).

### L7 Pareto e cauda de SKUs
- **Pergunta:** quantos SKUs fazem 80% do faturamento? O que a cauda longa custa em
  produção/perda para o que devolve?
- **Fonte:** `OrderItem`/`HistoricalSaleItem` (já agregados no top-10; falta a curva
  completa com % acumulado), cruzado com perda por SKU (`WorkOrderItem`).
- **Esforço:** leitura nova pequena.
- **Valor:** decisão de cardápio (o cardápio 2027 tem 59 SKUs — quantos se pagam?).

### L8 Retenção por coorte (nativo)
- **Pergunta:** dos clientes novos de cada mês, quantos voltam em 30/60/90 dias? A
  retenção está melhorando desde o go-live?
- **Fonte:** `Order.data.customer_ref` + `Customer.created_at` (nativo apenas; o RFM
  atual é foto, não filme — lacuna 20 do inventário).
- **Esforço:** leitura nova média.
- **Valor:** a métrica de saúde do negócio que o ticket médio não conta; mede o efeito
  real de campanha/fidelização ao longo do tempo.

### L9 Rendimento × tempo de forno (o forno queima?)
- **Pergunta:** fornadas com tempo acima do planejado têm mais `overbaked`? Assar N
  minutos a menos reduz defeito?
- **Fonte:** `OvenRun.elapsed` (pós-#151) × `WorkOrderItem.quality_defect_ref` via
  `work_order_ref`. Já dá pós-deploy — precisa de semanas de cobertura de timer.
- **Esforço:** leitura nova pequena (cruzamento novo na família oven).
- **Valor:** transforma o timer em instrumento de qualidade, não só de lembrete — é a
  pergunta-âncora do plano de B.I. respondida com dado, não com opinião.

### L10 Quebra de caixa × contexto
- **Pergunta:** a quebra correlaciona com terminal, volume do turno, mix
  dinheiro-vs-cartão, dia da semana?
- **Fonte:** `CashShift` (tem FK de terminal e operador, `difference_q`,
  `expected_amount_q`) + vendas do turno.
- **Esforço:** leitura nova pequena (dimensões terminal/dia-da-semana na métrica
  existente + tile de correlação com volume).
- **Valor:** separa quebra sistêmica (processo, troco) de concentrada (pessoa,
  terminal); direciona a auditoria de retaguarda que o blind count já suporta.

### L11 Promessa vs realizado (on-time de delivery/retirada)
- **Pergunta:** entregamos/aprontamos na janela prometida? Qual % estoura, por dia e
  faixa?
- **Fonte:** `data.delivery_date` + `delivery_time_slot` (resolver a ref do slot em
  `Shop.defaults["pickup_slots"]` → instante) vs `ready_at`/`delivered_at`.
- **Esforço:** leitura nova média (resolução de slot + cobertura declarada — pedidos
  sem slot ficam fora do denominador, dito na tela).
- **Valor:** a casa tem regra explícita de nunca prometer o que não cumpre — esta é a
  métrica que fiscaliza a promessa.

### L12 Funil de sessão (carrinho → pedido)
- **Pergunta:** de cada 100 sessões abertas, quantas viram pedido? Onde o storefront
  perde gente?
- **Fonte:** `Session.state` (open/committed/abandoned) + `SessionEvent`.
  ⚠️ Lacuna real: o sweep de abandono usa `.update()` — não há `abandoned_at`; o
  TEMPO até abandonar é irrecuperável hoje (captura N4 conserta barato).
- **Esforço:** leitura nova pequena (taxa de conversão); tempo-até-abandono depende
  de N4.
- **Valor:** primeira visão de topo de funil do canal próprio.

### L13 Lift ingênuo de campanha (com honestidade declarada)
- **Pergunta:** vendeu mais na janela após a publicação do anúncio do que na média dos
  dias equivalentes?
- **Fonte:** `Announcement.published_at` + série de vendas. **Sem atribuição real**
  (não há UTM/cupom por campanha/lista de destinatários — ver N6): é correlação, e a
  tela precisa dizer isso.
- **Esforço:** leitura nova pequena.
- **Valor:** melhor que nada enquanto N6 não existe; dá ao marketing um retrovisor
  honesto ("não distingue campanha de chuva").

### L14 Extensões da gramática do explorador (habilitam vários acima)
Dimensões que faltam em métricas existentes, todas com dado disponível:
- `qty_sold` + **hora, dia-da-semana, canal** (o `created_at` do pedido já viaja) e
  **categoria** (existe no item histórico; no nativo via coleção do catálogo —
  esforço médio).
- `cash_difference` + **terminal, dia-da-semana**.
- Métricas novas candidatas: **cancelamentos** (L4), **descontos** (L3), **lead time**
  (L1), **clientes distintos** (contagem por período — mede recorrência sem RFM).
- **Esforço:** pequeno por dimensão (a gramática é whitelist: cada adição nasce com
  teste, regra da casa "roda como configurada ou não roda").

---

## 4. Captura nova — o dado não existe; custo/benefício explícito

### N1 ⭐ Re-ingestão Yooga enriquecida (telefone, bairro, taxa, observação)
- **Pergunta destravada:** quem eram os bons clientes do Yooga que NUNCA apareceram no
  Shopman? (resgate dirigido); de que bairros vinha o delivery? (zonas); quanto se
  perdia em taxa por meio de pagamento?
- **O que falta:** o export já tem `telefone`, `bairro`, `endereco`, `taxa_pagamento`,
  `observacao` — a ingestão descarta (verificado em `ingest_yooga.py`). São 4.769
  clientes identificados no histórico.
- **Custo:** BAIXO — ampliar o command idempotente (ingestão completável por
  construção, BI-PLAN §7: a segunda carga enriquece sem duplicar) + colunas novas no
  model histórico. Telefone é PII: guardar normalizado E casar com
  `guestman.Customer.phone` (a chave de identidade da casa) — decidir com o dono se o
  telefone cru persiste ou só o vínculo resolvido.
- **Valor:** ALTO — RFM ganha 2 anos de passado; a campanha de resgate ("sentimos sua
  falta") vira executável no marketing-nuxt com audiência real; delivery ganha
  geografia histórica para desenhar zonas.

### N2 Dimensão comer-aqui vs levar (regra B — decidida, não aplicada)
- **Pergunta destravada:** ticket e mix do salão vs balcão-para-levar; dimensionamento
  de mesas; produto que "senta" vs produto que "viaja".
- **O que falta:** aplicar a regra B (âncora de bebida, decidida na memória do
  projeto: ~56% levar / ~38% local / ~6% delivery) como coluna inferida na ingestão
  (`dine_in_inferred`) + tabela de etiquetas de SKU (bebida preparada/pronta, prato
  quente, pão-de-levar, …). No nativo: POS não distingue hoje — a mesma etiqueta
  classifica a cesta nativa por inferência, com o mesmo rótulo "inferido" na UI.
- **Custo:** MÉDIO — as etiquetas são o trabalho (curadoria por SKU); a regra é código
  puro e testável. Pendências já anotadas na memória: reclassificar Baguete
  Lanche/Hambúrguer; corte de "estoque" (4+ itens).
- **Valor:** MÉDIO-ALTO — é a dimensão de negócio que o dono pediu explicitamente no
  levantamento do Yooga; sem ela, salão e balcão são um borrão só.

### N3 Fornos distintos — ❌ ARQUIVADA (decisão do dono, 2026-08-14)
- **Decisão: a Nelson tem UM forno na prática.** A pergunta "o forno 2 queima mais que
  o 1?" (motivadora do QC-FORNADA §1) **não existe nesta casa** e sai do escopo — não
  é lacuna a corrigir, é pergunta sem dono.
- **Consequências imediatas:**
  - C9 (rendimento · receita × forno) sai dos cenários curados — cruzamento que sempre
    devolve uma linha só é ruído, não análise.
  - A dimensão `oven` do explorador fica **dormente**: o campo `OvenRun.oven_ref`
    continua sendo gravado (custo zero, e o dia que houver um segundo forno o passado
    já está carimbado), mas a dimensão não deve aparecer nos selects enquanto houver
    uma posição de forno só — oferecer um recorte que não recorta nada mente por
    omissão.
  - L9 (rendimento × tempo de forno) **segue de pé** e ganha importância: sem a
    variável "qual forno", a pergunta vira "assar mais tempo queima mais?" — que é
    justamente a acionável para um forno único.

### N4 `abandoned_at` na Session
- **O que falta:** o sweep de sessões estale usa `queryset.update()` — nem `updated_at`
  marca o instante. Carimbar `abandoned_at` (ou gravar `SessionEvent` de abandono) no
  sweep.
- **Custo:** MUITO BAIXO. **Valor:** habilita tempo-até-abandono (L12) e limpeza de
  funil honesta.

### N5 Código estruturado de cancelamento
- **O que falta:** `cancellation_reason` mistura código de máquina e texto livre numa
  string. Os presets de cancelamento já existem (`Shop.defaults["cancellation_presets"]`)
  — falta carimbar junto uma chave estável (`cancellation_code`) quando o operador
  escolhe o preset.
- **Custo:** BAIXO (uma chave nova em `Order.data`, registrada em data-schemas).
- **Valor:** L4 sem normalização frágil; taxonomia estável para sempre.

### N6 Atribuição real de campanha → venda
- **Pergunta destravada:** a campanha X gerou quantos pedidos e quanto de receita?
- **O que falta (verificado):** nada liga `Announcement`/`Campaign` a `Order` — sem
  UTM, sem lista de destinatários (por design, PII), sem model de resgate de cupom
  (`Coupon.uses_count` é contador reversível e zerável pelo Admin — não é histórico).
  Caminho mínimo: **cupom exclusivo por campanha** + model `CouponRedemption`
  (cupom, order_ref, redeemed_at) — o elo já aparece em
  `order.snapshot.pricing.coupon.code`, só não é consultável. Caminho complementar:
  parâmetro de campanha no `content.link` do anúncio, capturado como `origin_campaign`
  na Session (propagação via commit — a lista explícita do `CommitService`).
- **Custo:** MÉDIO (model novo no shop/backstage + toque no fluxo de cupom + chave
  nova na propagação). **Valor:** ALTO — marketing deixa de ser fé; RFM × campanha
  (a pergunta original) passa a ser mensurável de verdade.

### N7 Custo e margem por SKU (cadeia rompida em 2 pontos)
- **Pergunta destravada:** qual a margem de cada SKU? A perda de produção custa quanto
  em reais (hoje só sabemos em unidades)?
- **O que falta (verificado):** o dado bruto existe (`SupplierMaterialCost.cost_q` com
  `is_preferred`), mas (a) nenhum adapter implementa `CostBackend.get_cost`
  (`COST_BACKEND=None` no settings) e (b) não existe agregador
  `RecipeItem.quantity × custo → custo de receita`. Sem histórico de custo (o model
  sobrescreve).
- **Custo:** MÉDIO-ALTO — é essencialmente o Buyman Fase 2 + implementação do seam já
  desenhado. Histórico de preço de insumo é captura adicional.
- **Valor:** ALTO mas não urgente — muda decisão de preço e mix; sequenciar com o
  roadmap do Buyman, não como frente do B.I.

### N8 Clima × vendas
- **O que falta:** captura externa (API de clima, 1 leitura/dia armazenada; adapter
  inerte em DEBUG como manda a casa).
- **Custo:** BAIXO-MÉDIO (dependência externa nova — precisa passar no filtro de
  parcimônia da casa). **Valor:** MÉDIO — explica variância ("caiu porque choveu") e
  refina o planejamento de fornada; ganha força combinado com L5/L2. Sugestão: só
  depois do B.I. estar em uso real.

### N9 ⭐ Timestamps por etapa de produção (concepção original não honrada)
- **Correção do dono (2026-08-14): etapas de produção foram concebidas DESDE O INÍCIO
  para ter timestamps.** Verificação atenta (main, PR #151 e todos os branches da
  fila): `apply_advance_step` guarda um ponteiro escalar
  (`WorkOrder.meta["steps_progress"]`) e SOBRESCREVE `steps_progress_updated_at` a
  cada avanço — avançar para a etapa 3 apaga o carimbo da etapa 2. Não gera
  `WorkOrderEvent`. A trilha por etapa se perde; mise-en-place vive em localStorage.
- **Decisão do dono (2026-08-14):** *"não sei se precisa de ledger, só preciso ter
  dados históricos verdadeiros para BI."* → **caminho escolhido: o mínimo que seja
  verdadeiro.** Acumular `steps_progress_history: [{step, at, actor}]` por append no
  próprio `WorkOrder.meta`, no serviço do backstage que já é o único escritor — sem
  tocar craftsman (Core é Sagrado; kind novo em `WorkOrderEvent` poria vocabulário de
  padaria no core genérico e exigiria ADR própria).
- **O que "verdadeiro" exige, concretamente** (senão o dado mente e não serve ao B.I.):
  append que nunca sobrescreve; avanço lido-e-escrito na mesma transação (dois toques
  simultâneos no kiosk não podem perder um passo — risco baixo com um kiosk, mas o
  código precisa não depender disso); e o retrocesso/correção de etapa, se existir,
  entra como linha nova, jamais editando a anterior.
- **Custo:** BAIXO (append no mesmo serviço + registro em data-schemas).
- **Valor:** tempo por etapa (onde a manhã emperra: massa? modelagem? forno?),
  duração real de fornada vs "OP aberta" (hoje `started_at→finished_at` inclui
  fermentação e espera — e o start implícito zera a duração), e o gargalo de
  capacidade que o `capacity_per_day` sozinho não mostra.

### N10 `started_at` no KDSTicket
- **O que falta:** o ticket tem `created_at`/`completed_at`/`acknowledged_at`, mas não
  o instante de início do preparo — fila e execução ficam indistinguíveis.
- **Custo:** BAIXO. **Valor:** MÉDIO — separa "demorou porque a fila estava cheia" de
  "demorou preparando"; complementa L1 no trecho cozinha.

---

## 5. Dependentes da fila C1–C6 (não fazer antes do merge)

- **Perda por vencimento vs não conformidade, por SKU** — as chaves
  `perda_vencido`/`perda_nao_conformidade`/`nonconformity_writeoffs` chegam com o C4
  (#149). Vira painel/métrica de write-off no explorador.
- **Validade × desconto (o markdown do grau converte?)** — hoje
  `Batch.nonconformity_percent` é gravado mas nunca aplicado a preço (os consumidores
  previstos no ADR-017 não existem no main); a fila C traz preço por lote. Só depois
  dela a pergunta "o desconto do grau acelera o giro do lote?" é mensurável — e aí é
  leitura nova de alto valor (FEFO + `Move` + preço praticado).

---

## 6. Dívidas de honestidade do dado (não são insights; contaminam leituras)

1. **Write-offs de fechamento caem em `kind=ADJUST`** (`closing.py` não passa kind) —
   um GROUP BY por kind conta perda de fim de dia como ajuste de inventário. Corrigir
   na fila C ou em seguida.
2. **`Move.reason` tem 5 formatos coexistindo** (`perda:`, `perda_d1_vencido:`,
   `Perda de rendimento: WO-…`, …) e ligar Move→WO exige regex. Convenção a congelar
   antes de qualquer leitura de perdas por SKU.
3. **Fusão "dia nativo vence" é frágil no limite:** 1 pedido de teste num dia apaga
   ~110 vendas Yooga daquele dia, sem alerta. Vale um guard (ex.: alertar se o dia
   nativo tem <N pedidos e o histórico tem >M).
4. **`orders_by_hour`/`orders_by_weekday` misturam fontes sem rótulo** no painel de
   vendas (diferente da série diária, que rotula). Pequeno ajuste de contrato.
5. **Ticket médio dos painéis exclui frete** (`delivery_fee_q` vive fora de
   `total_q`) — declarar na UI ou somar explicitamente.
6. **`CustomerInsight` pode estar velho sem ninguém saber**: `recalculate_all()` não
   tem invocador agendado e as projections não expõem `calculated_at`. Expor a idade
   do dado (padrão "health não alcança tudo") e/ou agendar no maintenance_worker.
7. **RFM é foto, não filme** — sem snapshot histórico, migração de segmento
   (champion→at_risk) é invisível. Se L8 mostrar apetite, um snapshot mensal barato
   resolve (tabela derivada recomputável? não — aqui é série temporal genuína, captura
   nova de baixo custo).
8. **Perda por operador (C7) é ferramenta de treinamento, não de punição** — recomendo
   a tela carregar o denominador (volume produzido) junto, para não criar ranking
   injusto de quem mais produz.
9. **Divergências doc↔código encontradas** em `docs/reference/data-schemas.md`: tupla
   de propagação do commit desatualizada (faltam `customer_ref`, `loyalty`,
   `delivery_distance_km`); exemplo de `snapshot.pricing` com formato que nenhum
   modifier grava; fase `on_confirmed` vs `on_accepted` do código.
10. **`OrderItem.sku` sem índice** com 380k+ linhas históricas no mesmo explorador —
    manter o gatilho medido da ADR-021 §3 no radar (medir p95 do explorador em
    staging com o Yooga carregado).

---

## 7. Priorização proposta (para iterar com o dono)

| Pacote | Conteúdo | Esforço | Alavanca |
|---|---|---|---|
| **P1 — Curadoria** | C1–C8 e C10–C12 como exemplos do Explorar; dimensão `oven` sai dos selects (um forno só) | horas | Imediata: o B.I. novo mostra do que é capaz |
| **P2 — Funil do pedido** | L1 (+ L4 cancelamentos, L11 promessa) | dias | O maior dado inexplorado; melhora operação E promessa ao cliente |
| **P3 — Yooga completo** | N1 re-ingestão (+ L5 YoY, C4/C5 curados) | dias | 2 anos de história viram clientes, zonas e sazonalidade acionáveis |
| **P4 — Produção honesta** | N9 etapas (concepção original) + L9 tempo de forno × defeito + L2 sold-out | dias | Fecha o ciclo âncora do B.I.: produzir a quantidade certa, assar certo |
| **P5 — Dinheiro invisível** | L3 descontos + L10 quebra×contexto + dívidas §6.1–6.5 | dias | Controle interno; números confiáveis |
| **P6 — Estruturais** | N6 atribuição de campanha; N7 margem (com Buyman F2); N2 regra B | semanas | Alto valor, cada um pede decisão de escopo própria |

Sugestão de ordem: **P1 já; P2 e P3 em paralelo; P4 quando o bi-nuxt estiver
deployado e o timer rodando; P5 encaixado; P6 são decisões separadas.**

### Perguntas ao dono — estado

**Respondidas (2026-08-14):**
- **Fornos:** um só, na prática → N3 arquivada, C9 fora dos exemplos, dimensão `oven`
  dormente.
- **Etapas de produção:** sem exigência de ledger; o requisito é **dado histórico
  verdadeiro** → N9 segue pelo append em `meta`, com as três garantias listadas lá.

**Abertas:**
1. **Telefone do Yooga (N1)** — o export histórico tem a coluna `telefone` e a
   ingestão atual a joga fora. Duas formas de aproveitá-la:
   (a) **guardar o telefone junto da venda histórica** — o B.I. passa a poder
   reconstruir sozinho quem comprava o quê, inclusive de quem nunca virou cliente no
   Shopman; custo: dado pessoal de 2 anos passa a viver numa segunda tabela, com o
   dever de protegê-lo;
   (b) **usar o telefone só na hora da ingestão para achar o `Customer` correspondente
   e guardar apenas esse vínculo** — o histórico fica sem PII nova, e quem nunca se
   cadastrou no Shopman continua anônimo (perde-se a lista de resgate desses).
   A diferença prática é essa: (a) permite campanha de resgate para quem sumiu; (b) é
   mais conservador com dado pessoal.
2. **Decisões semanais** — quais decisões você toma toda semana e gostaria de tomar
   com número na frente? A priorização do §7 é minha leitura; a sua manda.
3. **Snapshot de RFM (§6.7)** — hoje o RFM é foto: quando um cliente passa de
   `champion` para `at_risk`, ninguém vê a mudança acontecer. Interessa começar a
   guardar uma foto mensal já, ou espera L8 (coortes) mostrar apetite?
