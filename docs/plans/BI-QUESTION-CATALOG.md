# BI-QUESTION-CATALOG — o catálogo de perguntas, e o caminho para as três que faltam

> **Mandato (2026-08-17):** *"o que representa mais vendas: quem vem só buscar pão,
> quem vem só consumir no local, quem consome e leva, entregas? Qual o valor por
> mesa, a quantidade ideal de mesas, ocupação, ociosidade, dias, horários? Vendas por
> forma de pagamento? E: vou ter que formular TODAS as perguntas?"*
>
> **Resposta curta à última:** não. O catálogo do §4 é meu, não seu — cada pergunta
> nasce de um dado que a suite tem ou pode ter, com o estado dela verificado no
> código. Seu papel é riscar o que não interessa e apontar a ordem.
>
> **Base verificada:** `origin/main` @ `708491f92` (17/08/2026). Este documento é
> irmão de [BI-INSIGHTS-MAP.md](BI-INSIGHTS-MAP.md) (rodadas 1–7, o que já foi
> entregue) e [BI-FORECAST-PLAN.md](BI-FORECAST-PLAN.md) (a frente de projeção).
> O que está aqui **não** repete aqueles: é o que eles deixaram de fora.

---

## 0. Sumário executivo

Das três coisas que você trouxe, o diagnóstico honesto é:

1. **Forma de pagamento — o dado existe, durável, e ninguém lê direito.** Cada pedido
   guarda os pagamentos linha a linha (`order.data.payment.tenders[]`), e o histórico
   do Yooga traz a forma de pagamento crua em **dois anos** de venda. Hoje isso só
   aparece como um total do dia no painel de caixa, e **só em dia com fechamento
   feito**. Virar métrica e dimensão do explorador é o item mais barato e mais
   imediato deste documento. → §3.3, §5-F1.

2. **Modo de consumo (levar / local / local+levar / entrega) — a casa não registra.**
   `fulfillment_type` só conhece `pickup` e `delivery`, e o PDV grava `pickup`
   sempre. Salão e balcão são um borrão só. Existem dois caminhos, e eles se
   somam: capturar daqui pra frente (§3.1) e inferir o passado do Yooga pela cesta
   (regra B, já decidida). → §3.1, §5-F3/F6.

3. **Mesa — o conceito não existe no sistema.** O que existe é a **comanda**
   (`POSTab`): um número reusável, sem lugar, sem lotação, sem vínculo com mesa. Sem
   um cadastro de mesas e um vínculo comanda↔mesa, "valor por mesa", "ocupação" e
   "quantas mesas eu deveria ter" não têm denominador — não são perguntas difíceis,
   são perguntas **sem dado**. → §3.2, §5-F4.

**A descoberta que organiza o plano:** os itens 2 e 3 são a **mesma captura**. Se a
comanda for aberta *numa mesa*, o sistema sabe sozinho que aquilo é consumo local —
sem perguntar nada a ninguém, sem tap novo no PDV, usando um gesto que o operador já
faz. Uma captura, duas perguntas respondidas. E o denominador da ocupação (quanto
tempo a casa esteve aberta naquele dia) **já foi construído** na rodada 6
(`DayContext.open_minutes`), sem que esse fosse o objetivo.

---

## 1. O que o B.I. já responde hoje (para não reconstruir)

Painéis: vendas, produção, caixa, clientes, projeção. Explorador com 14 métricas ×
dimensões compatíveis, até 2 eixos, 5 anos de janela, cenários salvos
([`bi_explore.py:49`](../../shopman/backstage/projections/bi_explore.py)).

| Família | Métricas | Dimensões disponíveis |
|---|---|---|
| Vendas | Faturamento, Pedidos, Ticket médio | tempo, canal, hora, dia-da-semana, mês do ano, semana do ano, fonte |
| Itens | Quantidade vendida | tempo, SKU, hora, dia-da-semana, mês/semana do ano, fonte |
| Produção | Qtd produzida, Perda, Rendimento | tempo, receita, operador, dia-da-semana, grau, defeito |
| Forno | Tempo de forno | tempo, receita, operador |
| Caixa | Quebra de caixa | tempo, operador |
| Abastecimento | Dias que acabaram, Horas sem produto, Sobra no fim do dia | SKU, tempo, dia-da-semana, mês do ano |
| Oferta | Horas sem poder vender, Horas pausado, % do expediente sem vender | SKU, tempo, dia-da-semana, mês do ano, canal, motivo |

Mais as **dimensões de contexto** que só aparecem quando o dado foi injetado: tipo de
dia (feriado/véspera/volta/data comercial), temperatura, chuva.

**O que isso já cobre da sua pergunta:** "que dias, que horários, quanto" — para
faturamento, pedidos e ticket. O mapa de calor hora × dia-da-semana com dois anos de
história é um cenário curado hoje. **O que não cobre:** absolutamente nenhum recorte
por forma de pagamento, modo de consumo ou mesa.

---

## 2. Como leio "o conjunto de dados ao qual temos acesso"

Quatro fontes, com caráter diferente — e a tela precisa saber de qual está falando:

| Fonte | O que ensina | Alcance |
|---|---|---|
| `Order` + `OrderItem` + `Session` (nativo) | Venda, cesta, pagamento, canal, comanda, tempo de sessão | Desde o go-live |
| `Move` / `Hold` / `ShelfOutage` (estoque) | Abastecimento: quando chegou, quando faltou, o que sobrou | Desde o go-live |
| `HistoricalSale` (Yooga) | Demanda: 81.255 vendas × ~380k itens, com hora, SKU, categoria, **forma de pagamento**, operador, delivery | jul/2024 → jul/2026 |
| `DayContext` (injeção) | Contexto do dia: feriado, clima, expediente congelado, episódios | Conforme arquivo carregado |

A regra que já governa o B.I. e continua valendo aqui: **sem dado, nenhuma
afirmação**. Dimensão que não tem dado carregado não aparece no seletor; célula vazia
é ausência, nunca zero; leitura inferida sai rotulada como inferida.

---

## 3. As três perguntas que você trouxe

### 3.1 Modo de consumo — levar, local, local+levar, entrega

**Estado: 🔴 o dado não existe no nativo.**

Verificado: `fulfillment_type` aceita exatamente dois valores, `pickup` e `delivery`
([`surface.py:659`](../../shopman/storefront/api/surface.py)), e o PDV abre toda
comanda com `fulfillment_type: "pickup"`
([`pos.py:473`](../../shopman/shop/services/pos.py)). Não há tela, campo ou toggle
que distinga quem sentou de quem levou. A dimensão `channel` do explorador separa
`pdv` / `web` / `ifood` — isso separa **por onde o pedido entrou**, não **como foi
consumido**. Um croissant comido na mesa e um croissant levado saem os dois como
`pdv · pickup`.

No histórico do Yooga há `modality`, `origin` e `table_label` **crus**, e a decisão
já registrada é que **mesa/balcão do Yooga não são confiáveis** — a distinção não era
feita no dia a dia ([`historical_sale.py:9`](../../shopman/backstage/models/historical_sale.py)).
O único rótulo confiável de lá é `is_delivery`.

**Caminho — dois, e eles se somam:**

**(a) Daqui pra frente: a mesa é a captura.** Se abrir comanda numa mesa, a venda é
consumo local por construção. Venda direta no balcão, sem comanda de mesa, é levar. E
"consumiu e levou" deixa de precisar de um terceiro botão: é a **composição da cesta
de uma comanda de mesa** (tem pão-de-levar junto do café?), que se lê dos itens sem
capturar nada. Nenhum tap novo no PDV, nenhuma pergunta ao operador, nenhum campo em
branco esperando disciplina — o sinal nasce do gesto que já existe. É o mesmo
princípio dos episódios de operação (§13 do INSIGHTS-MAP): o sistema nota, a pessoa
não preenche.

⚠️ **A ressalva honesta:** isso só é verdade se o ritual do salão for abrir comanda de
mesa. Se metade das mesas for atendida por venda direta no balcão, a medida vira meia
verdade — e é melhor a tela declarar a cobertura ("N% das vendas do período têm modo
de consumo conhecido") do que fingir que 100% é levar. A cobertura declarada é o mesmo
padrão do `oven_coverage_percent` que já está no ar.

**(b) Para trás: inferência por cesta (regra B), rotulada como inferida.** A decisão
já foi tomada e o método já existe: âncora de bebida — consumo local exige bebida
junto; doce sozinho sem bebida é pra levar; 4+ do mesmo item é estoque/levar. O
retrato que ela produziu no levantamento foi ~56% levar, ~38% local, ~6% delivery,
com ticket local (R$ 63) acima do ticket de levar (R$ 53). O trabalho é a **curadoria
de etiquetas por SKU** (bebida preparada, bebida pronta, prato quente, pão-de-levar,
fino individual, varejo), não o código — a regra é código puro e testável. Ficaram
abertos dois casos: Baguete Lanche e Hambúrguer 100g (são lanche montado?) e o corte
de "estoque" (hoje 4+ do mesmo item).

**A honestidade que a tela precisa carregar:** nativo é **medido**, Yooga é
**inferido**. Misturar os dois num gráfico só, sem rótulo, é exatamente o defeito que
o §6.4 do INSIGHTS-MAP aponta em `orders_by_hour`. Duas séries rotuladas, sempre.

### 3.2 Mesa — valor, ocupação, ociosidade, quantidade ideal

**Estado: 🔴 o conceito não existe.**

O que existe é a **comanda** (`POSTab`): `ref`, `label`, `is_active`
([`pos.py:9`](../../shopman/backstage/models/pos.py)). Um número reusável — o seed
cadastra 1007 a 1012. Não tem lugar, não tem lotação, não tem mesa. Nada no sistema
sabe quantas mesas a Nelson tem.

**O que já dá para derivar hoje, sem capturar nada:**

- **Duração da comanda**: `Session.opened_at` → `Session.committed_at` são colunas
  duráveis ([`session.py:136`](../../packages/orderman/shopman/orderman/models/session.py)).
- **Valor por comanda**: o `Order` carrega `handle_type="pos_tab"` e
  `handle_ref=<número da comanda>` como colunas indexáveis
  ([`order.py:81`](../../packages/orderman/shopman/orderman/models/order.py)).
- **Simultaneidade**: quantas comandas estavam abertas ao mesmo tempo, por faixa
  horária, é uma varredura dos intervalos acima.

**O que NÃO dá, e por quê:** ocupação e ociosidade são frações — precisam de
denominador. "3 comandas abertas" só vira "60% de ocupação" se o sistema souber que
existem 5 mesas. E "quantidade ideal de mesas" precisa, além disso, saber quantos
lugares cada uma tem.

**Caminho mínimo — três peças pequenas:**

1. **Cadastro de mesas** (`ref`, rótulo, lugares, ativa). Uma tela de Admin, um
   punhado de linhas. É o denominador.
2. **Vínculo comanda↔mesa** no ato de abrir a comanda: `table_ref` na
   `Session.data`, propagado a `Order.data` pela lista explícita do `CommitService`
   (o contrato Session→Order, regra 5 do CLAUDE.md; a chave entra em
   `docs/reference/data-schemas.md` antes de ser usada).
3. **Leitura**: as métricas abaixo, todas derivadas, nenhuma capturada.

**O denominador de tempo já existe.** `DayContext.open_minutes`, `opens_at`,
`closes_at` e `closed_reason` foram carimbados na rodada 6 justamente para que
métricas de tempo não fossem lidas pelo horário de hoje. Ocupação de mesa usa o mesmo
carimbo — e herda a mesma garantia: **dia sem carimbo não entra na conta**, em vez de
inventar um expediente.

**O que passa a ser mensurável:**

| Métrica | Como se calcula | Responde |
|---|---|---|
| **Ocupação (%)** | Σ minutos de mesa ocupada ÷ (mesas ativas × `open_minutes`) | "o salão está ocioso?" |
| **Ociosidade por faixa** | 1 − ocupação, por hora × dia-da-semana | "que dias e horários sobram mesa?" |
| **Giro** | comandas fechadas ÷ mesa ÷ dia | "a mesa roda ou fica parada?" |
| **Valor por mesa** | faturamento ÷ mesa | "qual mesa rende mais?" (posição importa) |
| **Faturamento por mesa-hora** | faturamento ÷ (mesas × horas) | ⭐ a métrica que responde "quantas mesas?" |
| **Permanência média** | duração da comanda | "quanto tempo cada grupo fica?" |
| **Pico de simultaneidade** | máximo de mesas ocupadas por faixa | "quantas vezes bateu no teto?" |

**Sobre "a quantidade ideal de mesas", com honestidade:** o número ideal não sai de
uma conta, sai de duas leituras. A primeira é o **pico de simultaneidade por faixa
horária**: se o teto é atingido raramente, mesa a mais é espaço morto; se é atingido
todo sábado das 9h às 11h, mesa a mais é dinheiro. A segunda é o **faturamento por
mesa-hora**: acrescentar mesa só compensa enquanto ele não cair — o ponto em que
começa a cair é o ponto em que a casa tem mesas demais.

⚠️ **E o que nenhuma delas vê: quem chegou, olhou, não achou mesa e foi embora.** É a
demanda reprimida do salão, e é exatamente o mesmo problema do pão que esgota (§7.1
do INSIGHTS-MAP: "o sistema aprende a demanda truncada"). O ledger não registra
desistência. A saída barata é a mesma que a casa já usa para episódios: quando o
sistema detectar **casa cheia sustentada** (todas as mesas ocupadas por mais de X
minutos), oferecer no fechamento a pergunta com opções — "teve gente esperando? teve
gente que desistiu?". O sinal é automático; só o motivo depende de alguém dizer.

### 3.3 Forma de pagamento

**Estado: 🟡 o dado existe, durável, e a leitura é muito menor do que ele.**

O que existe hoje: o painel de caixa mostra o mix de meios de pagamento agregado do
dia, lido de `DayClosing.data.cash_shift_summary.payment_method_totals`
([`bi_cash.py:115`](../../shopman/backstage/projections/bi_cash.py)). Duas limitações
sérias: **só existe em dia com fechamento feito** (dias sem fechamento entram em
`closings_missing`), e é **um total do dia** — não cruza com nada.

O que o dado realmente permite, e ninguém lê:

- **Nativo, por pedido:** `order.data.payment.tenders[]` guarda cada pagamento com
  `method`, `collection`, `status` e `amount_q`
  ([`closing.py:384`](../../shopman/backstage/services/closing.py)). Pagamento
  dividido já é registrado corretamente (o PDV suporta múltiplos tenders), e
  pagamento na entrega ainda não recebido é distinguido de pagamento recebido. Isso
  significa que forma de pagamento pode ser métrica **e** dimensão, cruzável com
  hora, dia-da-semana, canal, SKU, contexto do dia — tudo o que a gramática já sabe
  cruzar.
- **Yooga, dois anos:** `HistoricalSale.payment` guarda a forma de pagamento crua de
  cada uma das 81.255 vendas ([`historical_sale.py:28`](../../shopman/backstage/models/historical_sale.py)).
  Precisa de uma normalização por whitelist (as strings do sistema antigo não são o
  vocabulário da casa) com balde "(outros)" declarado — o mesmo padrão que o
  explorador já usa para "(sem motivo)".

**Perguntas que isso destrava de imediato:** o dinheiro está encolhendo mês a mês
(quanto de troco a casa ainda precisa ter em caixa)? O PIX cresce em que horário? O
ticket do cartão é maior que o do dinheiro? Que forma de pagamento domina o sábado de
manhã? A taxa de cartão custa quanto por mês (com o `taxa_pagamento` do Yooga
re-ingerido, o custo histórico é calculável)? Vale a pena a maquininha nova?

**Custo:** baixo. É a leitura de melhor relação custo/benefício deste documento.

---

## 4. O catálogo — as perguntas que eu formulo por você

Legenda: ✅ o B.I. já responde · 🟡 o dado existe, falta leitura · 🔴 falta capturar.

### 4.1 Composição da venda (o que representa mais vendas)

| # | Pergunta | Estado | Fonte / o que falta |
|---|---|---|---|
| V1 | Quanto vende cada canal (balcão, loja online, iFood)? | ✅ | dimensão `channel` |
| V2 | Quanto vende cada **modo de consumo** (levar, local, local+levar, entrega)? | 🔴 | §3.1 |
| V3 | Qual o **ticket** de cada modo de consumo? Quem senta gasta mais? | 🔴 | §3.1 |
| V4 | Qual a **cesta típica** de cada modo (o que o salão come, o que o balcão leva)? | 🔴 | §3.1 + itens |
| V5 | Quanto vende cada **forma de pagamento**, e como isso muda por hora e dia? | 🟡 | §3.3 |
| V6 | Entrega paga o custo que carrega (ticket × taxa × distância)? | 🟡 | ticket por canal existe; `delivery_fee_q` está fora de `total_q` (§6.5 INSIGHTS-MAP) |
| V7 | Que dias e horários concentram faturamento? | ✅ | hora × dia-da-semana |
| V8 | Quanto pesa a **retirada agendada** (encomenda) contra a venda de balcão? | 🟡 | `is_preorder` está em `Order.data`, não é dimensão |
| V9 | Como está este mês contra o **mesmo mês do ano passado**? | ✅ | dimensão mês do ano (cíclica) |
| V10 | Quanto a casa perde em **pedido cancelado**, por motivo? | 🟡 | L4 do INSIGHTS-MAP |

### 4.2 Salão e mesas

| # | Pergunta | Estado | Fonte / o que falta |
|---|---|---|---|
| M1 | Qual a **ocupação** do salão, por dia e faixa horária? | 🔴 | §3.2 |
| M2 | Que dias e horários o salão fica **ocioso**? | 🔴 | §3.2 |
| M3 | Qual o **faturamento por mesa-hora**? | 🔴 | §3.2 — a métrica que responde "quantas mesas" |
| M4 | Qual mesa rende mais (a posição importa)? | 🔴 | §3.2 |
| M5 | Quanto tempo um grupo fica na mesa, e isso mudou? | 🔴 | §3.2 (`opened_at`→`committed_at`) |
| M6 | Quantas vezes o salão **bateu no teto**? | 🔴 | §3.2 |
| M7 | Teve gente que **desistiu por falta de mesa**? | 🔴 | episódio no fechamento, §3.2 |
| M8 | O salão tira gente da fila do balcão ou soma? | 🔴 | M1 × filas do balcão |

### 4.3 Cliente

| # | Pergunta | Estado | Fonte / o que falta |
|---|---|---|---|
| C1 | Como está a distribuição RFM? Quantos em risco? | ✅ | painel de clientes |
| C2 | Dos clientes novos de cada mês, quantos **voltam** em 30/60/90 dias? | 🟡 | L8 (coortes) |
| C3 | Quem eram os **bons clientes do Yooga que nunca voltaram**? | 🔴 | N1 — re-ingestão com telefone (decidida, não feita) |
| C4 | Quantos clientes **distintos** por período (recorrência sem RFM)? | 🟡 | métrica nova, dado existe |
| C5 | Que fração da venda é de **cliente identificado**? | 🟡 | `customer_ref` no pedido |
| C6 | Quem senta é o mesmo que leva, ou são dois públicos? | 🔴 | §3.1 × `customer_ref` |
| C7 | Que horário cada segmento prefere? | 🟡 | `CustomerInsight.preferred_hour` existe, ninguém lê |

### 4.4 Produto e cardápio

| # | Pergunta | Estado | Fonte / o que falta |
|---|---|---|---|
| P1 | O que mais vende, em quantidade e em dinheiro? | ✅ | top SKUs + explorador |
| P2 | Quantos SKUs fazem **80% do faturamento** (Pareto)? | 🟡 | L7 |
| P3 | O que **vende junto** (attach rate)? Café puxa doce? | 🟡 | L6 — 380k linhas de base |
| P4 | O que vendia no Yooga e **sumiu** no cardápio novo? | ✅ | cenário curado (SKU × fonte) |
| P5 | O que se vende **em cada hora**? | ✅ | qty × hora |
| P6 | Qual a **margem** de cada SKU? | 🔴 | N7 — Buyman Fase 2 |
| P7 | O que as pessoas **procuram e não encontram** no site? | 🔴 | N14 — busca é 100% no navegador |
| P8 | Que categoria pesa mais, e isso muda por modo de consumo? | 🟡 | categoria existe no histórico; no nativo via coleção |

### 4.5 Abastecimento e produção

Coberto pelas rodadas 3–7 e pelo BI-FORECAST-PLAN. Aqui só o que continua aberto:

| # | Pergunta | Estado |
|---|---|---|
| A1 | Sobrou ou faltou pão, por SKU e por dia? | ✅ |
| A2 | Quanto tempo a casa ficou sem ter o produto para oferecer? | ✅ |
| A3 | Quanto assar amanhã? | ✅ (com contexto do dia) |
| A4 | Quanto se **deixou de vender** por ter faltado? | 🟡 | B4 — método honesto desenhado, não construído |
| A5 | Assar mais tempo **queima mais**? | 🟡 | L9 — depende de cobertura do timer |
| A6 | Onde a manhã emperra (massa, modelagem, forno)? | 🔴 | N9 — timestamps por etapa |

### 4.6 Caixa e dinheiro

| # | Pergunta | Estado | Fonte / o que falta |
|---|---|---|---|
| $1 | A quebra de caixa é sistêmica ou concentrada? | ✅ | por operador |
| $2 | A quebra correlaciona com terminal, volume, mix de pagamento? | 🟡 | L10 |
| $3 | Quanto a casa **dá de desconto** por mês, por tipo? | 🟡 | L3 — `snapshot.pricing` |
| $4 | Quem autoriza os descontos manuais, e quanto? | 🟡 | L3 |
| $5 | Quanto custa a **taxa de cartão** por mês? | 🔴 | N1 (`taxa_pagamento` do Yooga) + custo nativo |
| $6 | Quanto de dinheiro vivo a casa precisa ter em caixa? | 🟡 | §3.3 (mix por hora) |

### 4.7 Operação

| # | Pergunta | Estado | Fonte / o que falta |
|---|---|---|---|
| O1 | Quanto tempo do pedido até pronto, por canal e hora? | 🟡 | L1 — os `*_at` existem, ninguém lê |
| O2 | A casa **entrega na janela prometida**? | 🟡 | L11 |
| O3 | De cada 100 sessões abertas, quantas viram pedido? | 🟡 | L12 |
| O4 | O que houve **naquele dia estranho**? | ✅ | episódios de operação |
| O5 | Onde está o gargalo do sábado de manhã: forno, balcão ou salão? | 🔴 | O1 + M1 juntos |

### 4.8 Marketing

| # | Pergunta | Estado |
|---|---|---|
| K1 | A campanha X **vendeu**? | 🔴 | N6 — não existe atribuição campanha→venda |
| K2 | Vendeu mais na janela depois do anúncio (correlação declarada)? | 🟡 | L13 |
| K3 | Quem responde a campanha, por segmento? | 🔴 | N6 |

---

## 5. Plano de execução

Cada fase é entregável sozinha e não bloqueia a seguinte.

### F1 — Forma de pagamento no explorador ⭐ *(a mais barata, a mais imediata)*

- Métrica **"Faturamento por forma de pagamento"** e dimensão **"Forma de
  pagamento"**, lidas de `order.data.payment.tenders[]` com fallback para
  `payment.method` quando não houver tenders (o mesmo caminho que
  `_payment_method_totals` já percorre — uma pergunta, um dono: extrair a
  normalização para um lugar só, em vez de duplicar a regra no B.I.).
- Normalização do `HistoricalSale.payment` por whitelist + balde "(outros)"
  declarado, para os dois anos entrarem no mesmo eixo com a fonte rotulada.
- Pagamento na entrega ainda não recebido **não** entra como recebido — a distinção
  já existe no fechamento e precisa sobreviver à leitura.
- Cenários curados novos: mix de pagamento por hora; dinheiro ao longo dos meses;
  ticket por forma de pagamento.

**Esforço:** pequeno. **Valor:** alto e imediato, sobre dois anos de base.

### F2 — Medir antes de construir *(meio dia, evita construir no vazio)*

Antes de F3/F4, rodar no staging (que tem o Yooga carregado) três contagens que
mudam a decisão:

1. Que fração das vendas do Yooga tem `table_label` preenchido — se for alta, a
   inferência da regra B ganha um **teste de aderência** grátis (não vira verdade,
   mas mede o erro do método).
2. Qual a distribuição real de `HistoricalSale.payment` — dimensiona a whitelist de
   F1.
3. Que fração das vendas do PDV hoje passa por comanda contra venda direta — é o
   número que diz se o caminho (a) do §3.1 mede a casa ou uma fatia dela.

### F3 — Modo de consumo, capturado ⭐

- Cadastro de mesas + vínculo comanda↔mesa (§3.2, peças 1 e 2). **Uma captura, duas
  perguntas.**
- Dimensão **"Modo de consumo"** com os valores que o dado sustenta: `salão`,
  `balcão-levar`, `retirada agendada`, `entrega`, `iFood` — derivados, não digitados.
- **Cobertura declarada na tela**: que fração do período tem modo conhecido.
- ⚠️ Sem inventar o terceiro estado: "consumiu e levou" sai da composição da cesta da
  comanda de mesa, não de um botão.

### F4 — Mesa: ocupação, giro, valor ⭐

- Métricas do quadro do §3.2, todas sobre `DayContext.open_minutes` como
  denominador, herdando "dia sem carimbo não entra na conta".
- Sinal de **casa cheia sustentada** → pergunta com opções no fechamento, no catálogo
  de episódios que já existe.
- Cenários curados: ocupação por hora × dia-da-semana; faturamento por mesa-hora ao
  longo dos meses; permanência por faixa.

### F5 — Modo de consumo, inferido (os dois anos)

- Etiquetas de SKU (o trabalho é curadoria, não código) + regra B como função pura e
  testável, aplicada ao `HistoricalSaleItem`.
- **Sempre rotulado "inferido"**, sempre em série separada do medido.
- Resolver os dois casos abertos: Baguete Lanche / Hambúrguer 100g, e o corte de
  "estoque" (hoje 4+ do mesmo item).

### F6 — Catálogo, conforme apetite

Da tabela do §4, os 🟡 em ordem de custo crescente: C4 (clientes distintos), P2
(Pareto), L3 (descontos), L4 (cancelamentos), O1 (lead time), P3 (attach rate), C2
(coortes).

---

## 6. Riscos e dívidas que este trabalho toca

1. **A cobertura da comanda decide a honestidade do §3.1.** Se o salão não abrir
   comanda, a métrica mede uma fatia e chama de tudo. Por isso F2 vem antes de F3, e
   por isso a tela carrega cobertura declarada.
2. **`OrderItem.sku` segue sem índice** com 380k+ linhas históricas. F1 e F5 aumentam
   a carga do explorador sobre a tabela de itens — o gatilho medido da ADR-021 §3
   (p95 do explorador no staging com o Yooga carregado) vale a pena antes de F5.
3. **Ticket médio dos painéis exclui frete** (`delivery_fee_q` fora de `total_q`).
   Comparar ticket de entrega com ticket de salão sem resolver isso compara coisas
   diferentes. Vale resolver junto de V6.
4. **Mesa é dado de operação, não do core.** O cadastro e o vínculo moram no
   backstage; `Order.data` recebe a chave pela lista explícita do `CommitService`,
   registrada em `docs/reference/data-schemas.md` antes do uso. Nenhum campo novo em
   modelo do core.
5. **`table_label` do Yooga não vira verdade de canal** — nem depois de F2. Se a
   contagem mostrar boa cobertura, ele serve para **medir o erro** da regra B, e é
   assim que deve aparecer.

---

## 7. Perguntas ao dono

1. **O salão vai passar a abrir comanda por mesa?** É a única pergunta que muda o
   plano inteiro. Se sim, F3/F4 medem a casa. Se não, medem uma fatia — ainda útil,
   mas com cobertura declarada, e talvez não valha F4.
2. **Quantas mesas e quantos lugares a Nelson tem hoje?** É o denominador; sem ele
   não há ocupação. (E se mudar ao longo do tempo, o cadastro precisa saber desde
   quando — mesa acrescentada em março não pode reescrever a ocupação de janeiro.)
3. **Ociosidade interessa por mesa ou por lugar?** Uma mesa de 4 ocupada por 1 pessoa
   está ocupada ou 25% ocupada? A primeira leitura é grátis; a segunda exige perguntar
   quantas pessoas — um tap a mais, na abertura da comanda.
4. **Entrega própria e iFood entram no mesmo balde "entregas"?** Custo e margem são
   muito diferentes; a leitura pode ser uma ou duas.
5. **F1 já?** É pequena, independente, e vale sobre dois anos desde o primeiro dia.
   Meu voto é sim, antes de qualquer coisa deste documento.
