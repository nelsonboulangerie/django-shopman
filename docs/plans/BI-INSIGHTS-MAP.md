# BI-INSIGHTS-MAP — mapa de perguntas de negócio e possibilidades de insight

> **Status:** 🟢 **RODADA 3 EXECUTADA (2026-08-14)** — o dono mandou executar sem
> interrupções ("quero o trabalho feito, até o fim"). O que saiu do papel está marcado
> ✅ ao longo do documento e resumido no §9. O restante segue como análise para iterar.
> Mandato original: "análise profunda das possibilidades de insight — com os dados que
> JÁ existem e com os que PODEMOS passar a capturar".
>
> **Base (verificada no main em 2026-08-14, após rebase):** o PR #151 (B.I. F0–F9:
> `OvenRun`, `HistoricalSale`, painéis, explorador, `BIView`) **e** a fila C1–C6
> (write-offs `perda_vencido`/`perda_nao_conformidade`, FEFO, preço por lote) **já
> estão mergeados**, e o `bi.boulangerie.com.br` está no ar em staging com o Yooga
> carregado. Nada aqui depende mais de fila. Citações apontam o arquivo real; os três
> achados críticos do §7 foram revalidados contra o main após o merge.

---

## 0. Sumário executivo

O levantamento varreu os models de pedidos, produção, estoque, caixa, clientes,
marketing e o histórico Yooga. Conclusões de uma linha:

0. ⭐ **O eixo que o dono nomeou (rodada 2, §7) é planejamento de produção**: sobra ou
   falta de pão, hora de chegada e de esgotamento por SKU, e quanto assar amanhã dado o
   dia, a estação, a temperatura e o feriado. A descoberta central: **a fórmula de
   sugestão que já existe tem o mecanismo de demanda reprimida pronto e desligado** —
   falta apenas a hora de esgotamento, que o ledger de estoque sabe dar. Enquanto isso,
   o sistema aprende a demanda truncada e **a falta se auto-perpetua**.
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

## 5. Destravado pela fila C1–C6 (já mergeada — pronto para ler)

A fila entrou no main; o que dependia dela deixou de ser espera e virou trabalho
disponível:

- **Perda por vencimento vs não conformidade, por SKU** — o fechamento já grava os
  write-offs com motivo carimbado (`perda_vencido:<data>` e
  `perda_nao_conformidade:<data>` em `shopman/backstage/services/closing.py`). Vira
  métrica de perda por motivo no explorador. ⚠️ Ver §6.1: esses write-offs seguem sem
  `kind` próprio, então um agrupamento por tipo de movimento os conta como ajuste de
  inventário — a leitura tem de ir pelo motivo, não pelo tipo.
- **Validade × desconto (o markdown do grau converte?)** — com o preço por lote no ar,
  a pergunta "o desconto do lote acelera o giro?" passa a ser mensurável cruzando
  validade, movimento de venda e preço praticado. Leitura nova de alto valor, e a que
  fecha o ciclo do C1–C6 mostrando se a política de lote deu resultado.

---

## 6. Dívidas de honestidade do dado (não são insights; contaminam leituras)

1. ⚠️ **A perda do C4 é registrada como ajuste de inventário, não como perda**
   (verificado no main pós-merge). `_write_off_lots` em
   `shopman/backstage/services/closing.py:190` chama `StockMovements.issue(...)` sem
   informar o tipo de movimento, e o padrão do método é `ADJUST` — apesar de a própria
   docstring da função dizer "WASTE dos quants". Ou seja: `perda_vencido` e
   `perda_nao_conformidade` chegam ao ledger com o motivo certo e o **tipo errado**.
   Quem agrupar perda por tipo de movimento não vê a perda de fim de dia; quem agrupar
   por motivo vê. É a métrica que o C4 existiu para habilitar, entrando torta. Correção
   de uma linha (passar o tipo), e vale antes de qualquer painel de perda.
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

## 7. O eixo do dono: planejar a produção (rodada 2, 2026-08-14)

> Perguntado "quais decisões você toma toda semana e gostaria de tomar com número",
> o dono respondeu com um bloco só: **sobra ou falta de pão** (por dia-da-semana,
> temperatura, estação, mês, semana do ano), **SKU que chega tarde na loja**, **SKU que
> acaba cedo demais**, **projeção** ("se estivesse mais cedo, qual o impacto? se tivesse
> mais unidades até tal hora?"), **quanto produzir amanhã** (dia-da-semana, semana do
> ano, mês, temperatura/previsão, véspera e volta de feriado), com **flexibilidade para
> dimensões que ele ainda não considerou**; e, em segundo plano, **comportamento
> quantitativo do cliente** (o que se compra em cada hora, o que se compra junto).
>
> Isso reposiciona o B.I.: não é uma galeria de painéis, é **o ciclo de decisão da
> fornada**. Medir (sobra/falta/hora) → contextualizar (dia, clima, calendário) →
> decidir (quanto assar amanhã). O que segue é o que a suite sustenta hoje, verificado
> no código.

### 7.1 A descoberta que muda o plano: a fórmula já espera esse dado

A suite **já tem** o cálculo de sugestão de produção, determinístico e explicável
(`craft.suggest` em `packages/craftsman/.../services/queries.py`, com `basis` traduzido
em frases pt-BR na tela de plano). E ele já contém, pronto e desligado, o mecanismo de
demanda reprimida:

- `DailyDemand.soldout_at` existe no protocolo (`protocols/demand.py`) e
  `_estimate_demand` sabe extrapolar: se o produto esgotou às 10h, estima a demanda do
  dia inteiro pela taxa de venda observada (com teto de 2× o vendido, para não delirar).
- **O backend nunca preenche `soldout_at`** (`contrib/demand/backend.py` monta
  `DailyDemand(date, sold, wasted)` e para aí). Logo o sistema hoje aprende a demanda
  **truncada**: um pão que esgota toda quinta às 10h ensina à fórmula que a quinta vende
  pouco, e ela sugere produzir pouco. **A falta se auto-perpetua.**

Ou seja: a pergunta nº 1 do dono ("está faltando pão?") não é só um painel a construir;
é um **campo morto a ligar** dentro de um mecanismo que a casa já desenhou. Isso é o
"Core é Sagrado" funcionando a favor: antes de criar, achar onde ele já resolve.

### 7.2 Três defeitos concretos na sugestão de hoje (achados nesta rodada)

1. ⚠️ **A sugestão olha o dia da semana errado.** `craft.suggest(date=...)` recebe a
   data-alvo, mas `DemandProtocol.history()` **não tem parâmetro de data** e o backend
   filtra o histórico por `today.weekday()` (`backend.py:64-66`). Planejando na sexta a
   fornada de sábado (o default do comando é *amanhã*), o histórico consultado é o das
   **sextas**. O multiplicador de fim de semana, no mesmo cálculo, usa a data-alvo
   correta (`date.weekday() in (4,5)`) — os dois eixos discordam dentro da mesma conta.
   Sábado de padaria não é sexta; isso é dinheiro. Correção exige um argumento novo no
   Protocol (mudança em core, justificada como correção, não feature).
2. **A amostra é de 4 dias.** `HISTORICAL_DAYS=28` com `SAME_WEEKDAY_ONLY=True` dá 4
   ocorrências do dia-da-semana. Pior: o backend lê só `OrderItem` **nativo** — os
   81.255 pedidos do Yooga, com 2 anos de sábados, são invisíveis para a decisão de
   produção. Um `DemandBackend` que enxergue nativo + histórico troca 4 amostras por
   ~50 do mesmo dia-da-semana. E o `DEMAND_BACKEND` já é adapter plugável: é o seam
   existente, com consumidor real (ADR-001 satisfeita, sem inventar arquitetura).
3. **Dia fechado entra na média como dia fraco.** O calendário de fechamento existe
   (`business_calendar`, feriados em `Shop.defaults`), mas `craft.suggest` não o
   consulta: domingo fechado e feriado viram dias sem venda no histórico em vez de
   dias excluídos.

### 7.3 O que o ledger sustenta — e onde ele quebra (verificado)

| Pergunta | Dá? | Fonte | Ressalva honesta |
|---|---|---|---|
| **A que horas o SKU chegou na loja** | **Sim** | `Move` de produção positivo no quant físico vendável (posição `vitrine`) — escrito na hora do finish da fornada | É a hora do **registro no kiosk**, não a hora física do forno. Registro tardio atrasa o dado junto. |
| **A que horas esgotou fisicamente** | **Sim** | Soma acumulada do ledger `Move` por SKU até cruzar zero; o saldo é invariante garantida | Enviesado por canal: o PDV baixa no ato, a loja online só quando o pagamento confirma, o iFood no aceite do operador. |
| **A que horas sumiu da vitrine para o cliente** | **Parcial** | O que o cliente vê é `saldo − reservado`, e o **reservado (`Hold`) não tem ledger**: é mutável e o prazo é reescrito por atividade de carrinho | É a lacuna real. Precisa de captura (§7.6, N11). |
| **Quanto sobrou no fim do dia** | **Sim, já pronto** | `DayClosing.data.items[]` traz `qty_remaining`, `qty_loss`, `qty_d1` por SKU | Só existe em dia com fechamento feito. |
| **Curva de demanda por hora, com 2 anos** | **Sim** | `HistoricalSale.occurred_at` tem hora; itens têm SKU, categoria e quantidade | O Yooga não tem produção nem estoque. |

**A distinção que organiza tudo:** o passado do Yooga ensina **demanda** (que horas as
pessoas compram o quê, em cada dia e estação); só o Shopman mede **abastecimento**
(quando chegou, quando faltou, quanto sobrou). Um não substitui o outro, e a tela deve
dizer qual está falando.

⚠️ **Consequência prática para testes:** nada disso é observável no banco semeado. O
`seed` cria pedidos e fornadas gravando direto no banco, sem passar pelo lifecycle —
não gera movimento de venda nem de produção. Toda validação real depende de dados de
produção acumulando após o go-live.

### 7.4 A peça que resolve metade das perguntas de uma vez: contexto do dia

O dono pediu recortes por **dia-da-semana, semana do ano, mês, estação, temperatura,
véspera e volta de feriado** — e pediu espaço para dimensões que ainda não pensou.
Construir isso como métricas separadas seria repetir a mesma lógica em cada uma. A
forma econômica é uma **linha por data** (`DayContext`), com:

- **Calendário** (derivável, zero captura): dia-da-semana, **semana do ano**, **mês do
  ano**, estação.
- **Feriado** (captura pequena): é feriado, véspera, volta, ponte, e a distinção entre
  feriado nacional/estadual/municipal. Hoje o sistema só sabe se a loja **fecha**, não
  se o dia é especial para a demanda.
- **Clima** (captura externa): temperatura mínima/máxima/média e chuva. O histórico de
  clima é obtível para os 2 anos do Yooga, o que dá base imediata em vez de esperar um
  ano coletando.
- **Marca de dia fechado**, para excluir do denominador em vez de contar como dia fraco.

Com isso, **qualquer** métrica que tenha um dia associado ganha todos esses recortes de
graça, e adicionar uma dimensão nova depois (evento na cidade, feira, greve, semana de
prova) é acrescentar uma coluna, não reescrever análise. É também o que alimenta o seam
de ajuste da fórmula (`FORMULA_FACTOR_PROVIDERS`, hoje vazio: aceita
multiplicador/soma/piso/teto e é exatamente onde "está calor" ou "é véspera de feriado"
deve entrar).

**Nota sobre o eixo cíclico:** o explorador hoje agrupa o tempo de forma **contínua**
(dia → semana → mês, conforme a janela). "Semana do ano" e "mês do ano" que o dono pediu
são **cíclicos**: comparar todos os janeiros entre si, ou a semana 33 de cada ano. Só
`dia-da-semana` é cíclico hoje; os outros dois precisam nascer como dimensões próprias.

### 7.5 O que passa a ser mensurável (blocos, na ordem em que se sustentam)

**B1 — Janela de disponibilidade por SKU e por dia** *(leitura nova; sem captura)*
Chegou às HH:MM, esgotou às HH:MM, ficou N horas sem produto dentro do expediente.
Responde diretamente "está indo tarde pra loja?" e "está acabando cedo?". Cruzada com o
contexto do dia, vira o retrato do abastecimento.

**B2 — Sobra e falta, lado a lado** *(leitura nova; sobra já está pronta no fechamento)*
As duas caras da mesma decisão: sobra em unidades e em dinheiro (do fechamento), falta
em horas sem produto. Por SKU × contexto do dia. É o painel que responde "sobrou ou
faltou?" sem que ninguém precise cruzar duas telas.

**B3 — `soldout_at` ligado na fórmula** *(liga campo morto; correção)*
Derivado de B1, alimenta o mecanismo que já existe. Efeito imediato: a demanda deixa de
ser aprendida truncada, e a sugestão para de perpetuar a falta. Junto disso vão as
correções de 7.2 (dia-da-semana certo, dias fechados fora, e a extrapolação usando o
horário real da loja em vez das 06:00–18:00 fixas que estão no código).

**B4 — Venda estimada perdida** *(leitura nova; premissa declarada na tela)*
Responde "se tivesse mais unidades até tal hora, qual o impacto?". Método honesto e
explicável, sem caixa-preta: pega a curva de venda por hora **do próprio SKU em dias de
contexto comparável em que não faltou**, aplica às horas em que faltou, e apresenta como
estimativa **com a premissa escrita ao lado** ("supõe que a procura seguiria como nos
dias parecidos em que houve produto"). O mesmo método, invertido, responde "se
estivesse mais cedo na loja": compara os dias em que o SKU chegou cedo com aqueles em
que chegou tarde, dentro do mesmo contexto.

**B5 — Demanda que se manifestou sem virar venda** *(sinal já capturado, nunca lido)*
`StockAlertSubscription` é a fila de "queria e não tinha": tem SKU, data, hora e canal,
e o botão só aparece quando o produto está honestamente esgotado. Conta **pessoas, não
unidades** — é indício, não medida, e a tela precisa dizer isso. Hoje alimenta o badge
de vitrine e audiência de campanha; ninguém lê como série temporal.

**B6 — Comportamento do cliente** *(leitura nova; 2 anos de base disponíveis)*
O que se vende em cada hora (falta só a dimensão hora na métrica de quantidade), o que
se compra junto, tudo recortável pelo contexto do dia. O histórico Yooga já tem hora,
SKU, categoria e quantidade: **esse bloco tem 2 anos de base no primeiro dia**, ao
contrário dos blocos de abastecimento.

**B7 — Proxy de esgotamento no passado** *(leitura nova; barata)*
O Yooga não sabe de estoque, mas sabe a **hora da última venda** de cada SKU em cada
dia. Um SKU cuja venda cessa às 9h30 na maioria dos sábados e segue até as 17h nos
outros dias estava esgotando. É inferência, não medição, e deve ser rotulada assim —
mas dá uma leitura de 2 anos de "o que faltava" que nenhum outro caminho oferece.

### 7.6 Captura nova que este eixo exige (além das já listadas no §4)

- **N11 — Marcar quando o produto sai do ar para o cliente.** A quebra do §7.3: o
  reservado não tem ledger. O caminho barato **não** é versionar reserva (caro e
  invasivo); é carimbar o **evento de indisponibilidade** por SKU (ficou indisponível
  às HH:MM, voltou às HH:MM), no mesmo ponto onde a disponibilidade já é calculada.
  Custo baixo, e é o que torna B1 exato do ponto de vista do cliente em vez de aproximado
  pelo físico.
- **N12 — Contexto do dia** (§7.4): tabela + carga de calendário/feriados + clima
  histórico e diário. Custo médio-baixo, valor transversal.
- **N13 — Demanda que o checkout descartou.** Hoje, quando o cliente pede mais do que
  há, o sistema calcula a diferença exata, mostra o erro e **joga fora**. Persistir essa
  linha (SKU, quantidade pedida, quantidade disponível, data/hora) transforma o sinal
  mais preciso de demanda reprimida — porque tem **quantidade**, não só pessoas — em
  dado. Custo baixo.
- **N14 — Busca sem resultado.** A busca do site é 100% no navegador: nenhum termo
  chega ao servidor. "O que as pessoas procuram e não encontram" é hoje invisível.
  Custo baixo, valor médio (entra também no cardápio, não só na produção).

---

## 8. Priorização proposta (para iterar com o dono)

Reordenada após a rodada 2 (§7): o eixo de produção sobe ao topo, porque é a decisão
que o dono toma toda semana.

| Pacote | Conteúdo | Esforço | Alavanca |
|---|---|---|---|
| **P1 — Curadoria** | C1–C8 e C10–C12 como exemplos do Explorar; dimensão `oven` fora dos selects | horas | Imediata: o B.I. mostra do que já é capaz |
| **P2 — Sobra e falta** ⭐ | B1 janela de disponibilidade + B2 sobra×falta por SKU | dias | Responde a pergunta nº 1 do dono com dado que já existe |
| **P3 — Contexto do dia** ⭐ | N12 (`DayContext`: calendário, feriado, clima) + dimensões cíclicas semana/mês do ano + hora na métrica de quantidade | dias | Uma peça destrava sazonalidade, clima e feriado em TODAS as métricas |
| **P4 — Fórmula honesta** ⭐ | B3 `soldout_at` ligado + as 3 correções do §7.2 (dia-da-semana, amostra com histórico Yooga, dias fechados) | dias | Para de perpetuar a falta; melhora a sugestão que já está na tela |
| **P5 — Projeção** | B4 venda estimada perdida + B7 proxy de esgotamento no passado | dias | "Se tivesse mais unidades / chegasse mais cedo": o contrafactual pedido |
| **P6 — Cliente quantitativo** | B6 (hora × SKU, cesta) + L6 attach + L7 Pareto | dias | 2 anos de base disponíveis desde o primeiro dia |
| **P7 — Sinais de demanda** | B5 fila de "me avise" como série + N13 checkout descartado + N14 busca sem resultado | dias | Demanda reprimida deixa de ser invisível; N13 traz quantidade |
| **P8 — Yooga completo** | N1 re-ingestão com telefone (**decidido: opção (a)**) + L5 comparação com ano anterior | dias | Resgate de clientes perdidos, geografia, sazonalidade anual |
| **P9 — Produção honesta** | N9 etapas (concepção original) + L9 tempo de forno × defeito | dias | Fecha o ciclo do forno; N9 é dívida contra a concepção |
| **P10 — Funil do pedido** | L1 lead time (+ L4 cancelamentos, L11 promessa) | dias | Grande dado inexplorado, mas de operação, não de produção |
| **P11 — Dinheiro invisível** | L3 descontos + L10 quebra×contexto + dívidas §6.1–6.5 | dias | Controle interno; números confiáveis |
| **P12 — Estruturais** | N6 atribuição de campanha; N7 margem (Buyman F2); N2 regra B; §6.7 snapshot de RFM (**decidido: começa já**) | semanas | Cada um pede decisão de escopo própria |

Sugestão de ordem: **P1 já** (horas, zero risco); **P2→P3→P4 como uma frente só**, na
ordem, porque cada um habilita o seguinte e juntos fecham o ciclo medir→contextualizar→
decidir; **P5 e P6 em seguida** (P6 pode andar em paralelo: não depende do ledger);
**P7–P12 conforme apetite.** N11 (marcar quando o produto sai do ar) entra junto do P2
se o recorte "o que o cliente via" for considerado essencial; sem ele o P2 mede o
físico, que já é muito melhor que nada.

⚠️ **Expectativa de dados:** P2, P4 e P5 medem abastecimento, que só existe em dados de
produção reais acumulando após o go-live (o banco de teste não gera esses movimentos).
P3 e P6, ao contrário, valem imediatamente sobre os 2 anos do Yooga.

### Perguntas ao dono — estado

**Respondidas (2026-08-14):**
- **Fornos:** um só, na prática → N3 arquivada, C9 fora dos exemplos, dimensão `oven`
  dormente.
- **Etapas de produção:** sem exigência de ledger; o requisito é **dado histórico
  verdadeiro** → N9 segue pelo append em `meta`, com as três garantias listadas lá.
- **Telefone do Yooga (N1):** opção **(a)** — guardar o telefone junto da venda
  histórica, aceitando o dever de proteger dois anos de dado pessoal, em troca de poder
  reconstruir quem comprava o quê e montar campanha de resgate de quem sumiu.
- **Snapshot de RFM (§6.7):** **começa já** — a foto mensal passa a ser guardada, para
  que a migração de segmento ao longo do tempo seja visível quando a análise de coortes
  chegar.
- **Decisões semanais:** respondidas no §7 (planejamento de produção + comportamento
  quantitativo do cliente) e refletidas na priorização acima.

**Abertas (rodada 3):**
1. **A correção do dia-da-semana da sugestão (§7.2-1) sai já, fora do B.I.?** É bug com
   dinheiro em jogo toda semana, e a correção mexe no core (assinatura do protocolo de
   demanda). Não depende de nada do B.I.
2. **A sugestão deve enxergar o histórico Yooga (§7.2-2)?** Troca 4 amostras por ~50 do
   mesmo dia-da-semana, mas mistura a demanda da casa antiga com a nova na decisão
   operacional — e o cardápio mudou. Alternativa conservadora: usar o Yooga só para o
   **formato** da curva (peso relativo entre dias e horas) e o nativo para o **nível**.
3. **De onde vêm os feriados?** Nacional é fácil; municipal e estadual de Londrina
   precisam de fonte (ou cadastro manual anual no Admin, que é honesto e barato).
4. **Clima: vale a dependência externa?** É a única captura do §7 que traz um serviço de
   fora para dentro. Meu voto: sim, porque o histórico de 2 anos é obtível e a
   temperatura é justamente a variável que o dono citou espontaneamente — mas é decisão
   dele, e a casa é parcimoniosa com dependência nova.
5. **N11 (marcar quando o produto sai do ar) entra no P2 ou fica para depois?** Sem ele,
   a janela de disponibilidade mede o esgotamento **físico**; com ele, mede o que o
   cliente de fato via.

---

## 9. O que foi executado (rodada 3, 2026-08-14)

Cinco commits, suíte inteira verde (~6.500 testes), ruff limpo, typecheck do
bi-nuxt limpo.

### 9.1 Correções (defeitos achados pela análise)

**A perda do C4 entrava no ledger como ajuste de inventário** (§6.1). O
write-off do fechamento chamava a saída de estoque sem informar o tipo, e o
padrão é "ajuste" — apesar de a própria função se chamar de WASTE na
documentação dela. `perda_vencido` e `perda_nao_conformidade` chegavam com o
motivo certo e o tipo errado, sumindo de qualquer leitura de perda agrupada por
tipo. Corrigido, com teste que cobra o tipo em ambas as famílias de motivo.
⚠️ **Vale daqui pra frente**: o ledger é imutável, então movimentos já gravados
seguem como ajuste. Leitura que cubra o período anterior precisa aceitar as duas
formas.

**A sugestão de produção amostrava o dia errado** (§7.2-1). O histórico era
filtrado pelo dia-da-semana de *hoje*, e o comando roda para *amanhã* por
padrão: planejar sábado numa sexta lia sextas. `target_date` passou a ser
obrigatório no protocolo de demanda — quem pergunta pelo histórico tem de dizer
para qual dia está planejando. Os testes existentes trocavam o método por um
mock e por isso nunca exercitaram o filtro; o teste novo cria pedidos reais em
dois dias-da-semana e cobra a amostra certa.

**Dia fechado contava como dia fraco** (§7.2-3). Domingo de portas fechadas
entrava na média e puxava a sugestão da semana para baixo. Quem conhece o
calendário é o orquestrador, então é ele que resolve os dias e o core só recebe
a lista; o `basis` declara quantos saíram.

### 9.2 O ciclo do esgotamento (a descoberta do §7.1)

`soldout_at` **ligado**: o campo que existia e ninguém preenchia. Agora a
fórmula sabe que um dia esgotado mostra o estoque que havia, não a procura que
houve, e para de perpetuar a falta.

- `StockQueries.shelf_history` reconstrói, por SKU e dia, quando o produto
  chegou à prateleira e quando acabou, a partir do ledger dos quants vendáveis.
  Duas distinções que os testes cobram: **reposição desfaz o esgotamento**
  anterior, e **descarte não é esgotamento** (zera a prateleira, mas é o oposto:
  sobrou). Por isso o esgotamento só se fecha em movimento de venda — o que
  torna o §9.1 pré-requisito, não coincidência.
- A composição mora em `shop/adapters/demand.py`: quem pode ler pedidos e
  estoque na mesma frase é o orquestrador. O core segue sem conhecer o outro
  lado. `OrderingDemandBackend` virou export público do craftsman (já era
  público de fato: é o valor default do setting).
- **A extrapolação assumia expediente de 06:00–18:00** e a loja abre às 09:00 —
  subestimava a demanda pela metade. A janela real viaja junto, vinda do horário
  declarado. **Sem horário configurado, não extrapola**: perder precisão é
  melhor que inventar procura. O `basis` declara `soldout_days`.
- O seed ancorava o histórico só no dia-da-semana de hoje, por construção, para
  casar com o filtro antigo; agora cobre também o dia planejado.

### 9.3 Sobra e falta no B.I. (B1/B2 do §7.5)

Três métricas novas no explorador, cruzáveis por SKU, dia, dia-da-semana e mês:
**dias que acabaram**, **horas sem produto** (do esgotamento até o fim do
expediente) e **sobra no fim do dia** (da contagem do fechamento). Falta vem do
ledger, sobra vem do operador.

Honestidade preservada em três pontos: dia sem produto não fala nem de sobra nem
de falta e fica fora; dia sem fechamento é ausência, não sobra zero; sem horário
declarado não há "resto do dia" a contar.

**Sazonalidade** (parte do §7.4): dimensões cíclicas **mês do ano** e **semana
do ano**, que juntam todos os anos no mesmo balde — diferentes da série do
tempo, que é cronológica e nunca repete um balde. Junto: dimensão ordinal passa
a sair em ordem natural em vez de ranking, porque curva ordenada por valor deixa
de ser curva.

**Curadoria** (P1): de 3 para 15 cenários de partida, na ordem em que a semana
acontece — quanto assar, o que o cliente procura, como a casa foi. Cruzamento
por forno fica de fora (um forno só). Um teste cobra que todo exemplo usa
dimensão que existe, para que nenhum chip quebre ao abrir a tela.

### 9.4 O que NÃO foi feito, e por quê

- ~~**Clima e feriados**~~ → **ENTREGUES na rodada 4** (§10). Decisão do dono:
  "se tivermos os dados, mais opções aparecem na tela; se não tivermos, jamais
  inventamos". O caminho escolhido evita a dependência de rede: os dados entram
  por **arquivo**, e a gramática cresce sozinha quando eles chegam.
- **N11 (marcar quando o produto sai do ar)** — sem ele, a janela mede o
  esgotamento **físico**, não o que o cliente via. É a pergunta aberta nº 5.
- **Venda estimada perdida (B4/§7.5)** — depende de curva por hora em dias
  comparáveis; a fórmula já faz a versão simples disso internamente (taxa de
  venda com teto de 2×). Virar tela é o passo seguinte natural.
- **Tela própria de abastecimento** — as métricas entraram no explorador, que já
  responde as perguntas com cruzamento. Uma página dedicada só se justifica
  depois de ver quais cruzamentos o dono usa de fato.

### 9.5 Expectativa de dados (importante)

As métricas de abastecimento e o `soldout_at` só ganham vida com **dados reais
de produção acumulando**: o banco de teste grava pedidos e fornadas direto, sem
passar pelo fluxo que gera os movimentos de estoque, então lá elas aparecem
vazias por construção. As de venda e sazonalidade, ao contrário, valem
imediatamente sobre os dois anos do Yooga.

---

## 10. Contexto do dia: feriado e clima por injeção (rodada 4, 2026-08-15)

> Decisão do dono: *"calendário anual de feriados é fácil de obter, uma única
> vez! Claro que é bom não depender pra funcionar… mas opcionalmente poder
> injetar esses dados é muito bem-vindo. Mesma coisa para o clima: se tivermos
> os dados, mais opções aparecem na tela. Se não tivermos, jamais inventamos."*

Isso desenha a solução inteira: o dado é **opcional**, entra por **injeção**, e
a tela **cresce quando ele chega**. Nada de dependência de rede para o B.I.
funcionar, e nada de balde inventado quando o dado falta.

### 10.1 Como entra

`DayContext` — uma linha por data, com dois blocos independentes e ambos
opcionais: **feriado** (nome, abrangência, e véspera/volta derivadas na carga) e
**clima** (mínima, máxima, média, chuva). O que a suite deriva sozinha da data
(dia da semana, mês, semana do ano) **não** mora lá: é função da data e sai
calculado na leitura.

Dois comandos, ambos por arquivo local e idempotentes:

```bash
python manage.py import_holidays --file calendario-2026.json   # ou .csv
python manage.py import_weather  --file londrina-2024-2026.csv # ou .json
```

O de feriados **reescreve o ano inteiro** a partir do arquivo (o arquivo é a
verdade daquele ano: feriado tirado de lá some do banco) e marca véspera e
volta, que é o que muda o movimento de uma padaria. O de clima aceita os
cabeçalhos que arquivos de série histórica já usam (`temperature_2m_max`,
`precipitation_sum`), para não obrigar ninguém a reescrever cabeçalho na mão —
convite a erro. Ambos têm `--dry-run`.

Consolidação do histórico: um CSV com dois anos de temperatura torna os dois
anos do Yooga cruzáveis por clima de uma vez só. É o mesmo princípio do
histórico externo (ADR-021 §3): dado que a suite não produz só pode existir
materializado, com a origem carimbada — `sources` guarda de qual arquivo veio
cada bloco.

### 10.2 A regra: sem dado, nenhuma afirmação

Três camadas honram isso, e as três estão sob teste:

1. **A dimensão não existe até o dado chegar.** `available_context_dimensions()`
   consulta o que há carregado; sem clima, "Temperatura" e "Chuva" **não
   aparecem no seletor** nem passam pela validação. Pedir mesmo assim devolve um
   erro que diz qual comando rodar. Verificado ao vivo: apagando o clima, as duas
   dimensões e os três cenários de clima somem da tela, e "Tipo de dia"
   permanece — cada bloco entra e sai por conta própria.
2. **Célula vazia é ausência, não zero.** Um dia sem medição fica nulo e **sai**
   da leitura por temperatura, em vez de entrar como um dia de 0 °C.
3. **Dia sem contexto não vira balde.** Se metade da janela tem clima e metade
   não, a leitura por temperatura usa a metade que sabe — e não empurra a outra
   para uma faixa qualquer.

### 10.3 O que apareceu na tela

Três dimensões novas (**Tipo de dia (feriado)**, **Temperatura do dia** em
faixas de 5 °C, **Chuva** com/sem) aplicáveis a vendas, itens vendidos e
abastecimento — não à produção: a fornada não é função do dia do cliente. E
cinco cenários que só aparecem quando o dado existe: faturamento por
temperatura, o que vende no calor, feriado/véspera/volta, falta em véspera de
feriado, movimento com e sem chuva.

Junto veio uma correção de leitura: **num ranking, o que não aconteceu não é
linha**. Produto que nunca faltou não pertence à lista de faltas, e sessenta
zeros escondiam os dois SKUs que importavam. Em série temporal o zero fica — ali
ele é ponto da curva.
