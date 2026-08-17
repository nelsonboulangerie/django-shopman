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

2. **Modo de consumo — decidido: é inferido pela cesta, não capturado.** O nativo não
   registra (`fulfillment_type` só conhece `pickup`/`delivery`, e o PDV grava
   `pickup` sempre), e **não vai passar a registrar**: a regra da âncora de bebida já
   foi estudada e definida, e a decisão do dono (17/08) é aplicá-la como leitura
   derivada. Consequência boa: a mesma regra vale para o nativo e para os dois anos
   do Yooga, **sem depender de ritual de ninguém**, e vale no primeiro dia.
   → §3.1, §5-F3.

3. **Mesa — o conceito não existe no sistema.** O que existe é a **comanda**
   (`POSTab`): um número reusável, sem lugar, sem lotação, sem vínculo com mesa. Sem
   um cadastro de mesas e um vínculo comanda↔mesa, "valor por mesa", "ocupação" e
   "quantas mesas eu deveria ter" não têm denominador — não são perguntas difíceis,
   são perguntas **sem dado**. → §3.2, §5-F4.

**O que a decisão do item 2 muda:** os itens 2 e 3 **deixam de ser a mesma frente**.
Modo de consumo vira leitura pura, sem captura, sem cobertura declarada, sem
dependência do que a equipe lembra de fazer — e retroativa. A mesa continua exigindo
captura, mas agora **só pelas perguntas dela** (ocupação, giro, ociosidade): não é
mais pré-requisito de nada. As duas frentes andam em qualquer ordem, ou uma sem a
outra.

O denominador da ocupação (quanto tempo a casa esteve aberta naquele dia) **já foi
construído** na rodada 6 (`DayContext.open_minutes`), sem que esse fosse o objetivo.

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

**Estado: 🟡 nenhuma fonte registra o modo — e a decisão é não passar a registrar:
ele se infere da cesta, que já existe em toda venda, nativa e histórica.**

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

**Decisão do dono (17/08/2026): o modo de consumo é INFERIDO pela cesta.** Não haverá
captura no PDV. O estudo que definiu a regra já foi feito, e a razão pela qual ela
funciona nesta casa foi dita na mesma frase: *"quem pede bebida pra levar é uma
quantidade quase desprezível atualmente"*. A âncora é a **presença de item de
preparo** — bebida preparada, lanche montado — **mais a bebida pronta**, que aqui
também ancora, justamente porque quase ninguém a leva.

Isso é melhor do que a captura que eu tinha proposto, por três motivos que valem
registrar:

- **Vale para trás.** A mesma regra classifica os dois anos do Yooga e o nativo. Não
  há "antes e depois da captura".
- **Não depende de ritual.** Nenhuma cobertura declarada, nenhuma disciplina de
  equipe, nenhum campo em branco esperando alguém lembrar. A cesta sempre existe.
- **Uma pergunta, um dono.** A classificação mora num lugar só e vale igual no
  histórico e no nativo — em vez de duas verdades (uma medida, uma inferida) que a
  tela teria de manter separadas para sempre.

**A regra, como fica:**

| Sinal na cesta | Classificação |
|---|---|
| Item de preparo (bebida preparada, lanche montado) | **local** |
| Bebida pronta | **local** (refinamento do dono: levar bebida é desprezível) |
| Doce / viennoiserie / pão sozinho, sem bebida | **levar** |
| 4+ unidades do mesmo item | **levar** (compra de estoque) |
| `is_delivery` (Yooga) / `fulfillment_type=delivery` (nativo) | **entrega** — precede tudo |
| Cesta local **com** pão-de-levar junto | **local + levar** |

O retrato que o estudo produziu com a regra: **~56% levar, ~38% local, ~6% delivery**,
com ticket local (R$ 63) acima do ticket de levar (R$ 53).

⚠️ **O refinamento "bebida pronta ancora sozinha" mexe no resultado e é mensurável.**
Na formulação original a bebida pronta só ancorava acompanhada de item de consumo
local; agora ancora sozinha. O efeito é deslocar parte do "levar" para o "local", e o
tamanho desse deslocamento sai de uma contagem — vale rodar as duas variantes sobre os
dois anos e ver a diferença antes de congelar (é barato: a regra é função pura).

**O trabalho real é curadoria, não código.** As etiquetas por SKU (bebida preparada,
bebida pronta, prato quente, pão-de-levar, fino individual, varejo/mercearia) são o
esforço; a regra em si é uma função testável. Seguem abertos os dois casos do estudo:
Baguete Lanche e Hambúrguer 100g (são lanche montado, e portanto âncora?) e o corte de
"estoque" (hoje 4+ do mesmo item).

**A honestidade que a tela precisa carregar:** a leitura é **inferida**, e diz isso —
com a regra vigente ao alcance de um clique, porque um número que muda quando alguém
reetiqueta um SKU precisa dizer de que regra veio. O que **não** é mais necessário:
separar série medida de série inferida. Não há série medida, e é isso que torna a
leitura coerente de ponta a ponta.

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
| V2 | Quanto vende cada **modo de consumo** (levar, local, local+levar, entrega)? | 🟡 | §3.1 — inferido da cesta; falta etiquetar SKUs |
| V3 | Qual o **ticket** de cada modo de consumo? Quem senta gasta mais? | 🟡 | §3.1 |
| V4 | Qual a **cesta típica** de cada modo (o que o salão come, o que o balcão leva)? | 🟡 | §3.1 + itens |
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
| C6 | Quem senta é o mesmo que leva, ou são dois públicos? | 🟡 | §3.1 × `customer_ref` |
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

Três contagens no staging (que tem o Yooga carregado), cada uma decide um parâmetro:

1. Distribuição real de `HistoricalSale.payment` — dimensiona a whitelist de F1.
2. As **duas variantes da âncora** (bebida pronta ancorando sozinha × só acompanhada)
   sobre os dois anos: quanto muda o retrato? É o que congela a regra de F3 com
   número, não com opinião.
3. Que fração das vendas do Yooga tem `table_label` preenchido — não vira verdade de
   canal (a decisão de que mesa/balcão do Yooga não são confiáveis continua de pé),
   mas se a cobertura for alta serve de **teste de aderência** da inferência: mede o
   erro do método sem custar nada.

### F3 — Modo de consumo, inferido ⭐

- **Etiquetas por SKU** — o trabalho de verdade. Bebida preparada, bebida pronta,
  lanche montado, prato quente, pão-de-levar, fino individual, varejo. Cadastro
  editável no Admin, como os defeitos de qualidade já são.
- **A regra como função pura e testável**, aplicada igual ao `OrderItem` nativo e ao
  `HistoricalSaleItem`. Uma implementação, dois consumidores — nunca duas cópias que
  divergem.
- **Dimensão "Modo de consumo"**: `local`, `local + levar`, `levar`, `entrega`,
  aplicável às famílias de vendas e itens (e portanto cruzável com hora, dia,
  contexto do dia, forma de pagamento de F1).
- **Rotulada como inferida na tela**, com a regra vigente ao alcance de um clique.
- Decidir os dois casos abertos: Baguete Lanche / Hambúrguer 100g e o corte de
  "estoque" (4+).
- ⚠️ SKU sem etiqueta não pode virar "levar" por omissão — vira **não classificado**,
  declarado. Etiqueta faltando é ausência de dado, não um veredito.

**Independe de F4.** Não depende de mesa, de comanda, nem de ritual de equipe.

### F4 — Mesa: ocupação, giro, valor ⭐

Frente própria agora, movida **só pelas perguntas de mesa** (M1–M8) — deixou de ser
pré-requisito do modo de consumo.

- Cadastro de mesas (ref, rótulo, lugares, ativa desde quando) + vínculo
  comanda↔mesa: `table_ref` na `Session.data`, propagado a `Order.data` pela lista
  explícita do `CommitService`, registrado antes em `data-schemas.md`.
- Métricas do quadro do §3.2, todas sobre `DayContext.open_minutes` como
  denominador, herdando "dia sem carimbo não entra na conta".
- Sinal de **casa cheia sustentada** → pergunta com opções no fechamento, no catálogo
  de episódios que já existe.
- Cenários curados: ocupação por hora × dia-da-semana; faturamento por mesa-hora ao
  longo dos meses; permanência por faixa.
- ⚠️ Aqui a cobertura **continua importando**: se o salão não abrir comanda por mesa,
  a ocupação mede uma fatia. É a pergunta nº 1 do §7.

### F6 — Catálogo, conforme apetite

Da tabela do §4, os 🟡 em ordem de custo crescente: C4 (clientes distintos), P2
(Pareto), L3 (descontos), L4 (cancelamentos), O1 (lead time), P3 (attach rate), C2
(coortes).

---

## 6. Riscos e dívidas que este trabalho toca

1. **A etiqueta de SKU vira parâmetro de negócio.** Com o modo de consumo inferido,
   reetiquetar um produto **muda números publicados** — inclusive de meses passados.
   Duas travas: a regra vigente fica visível na tela, e mudança de etiqueta é evento
   com data, não edição silenciosa. É o preço justo da inferência, e é menor que o
   preço da captura que ela substitui.
2. **`OrderItem.sku` segue sem índice** com 380k+ linhas históricas. F1 e F3 aumentam
   a carga do explorador sobre a tabela de itens, e F3 mais que todas: classificar por
   cesta obriga a varrer os itens de cada venda. O gatilho medido da ADR-021 §3 (p95 do
   explorador no staging com o Yooga carregado) vale a pena **antes** de F3.
3. **Ticket médio dos painéis exclui frete** (`delivery_fee_q` fora de `total_q`).
   Comparar ticket de entrega com ticket de salão sem resolver isso compara coisas
   diferentes. Vale resolver junto de V6.
4. **Mesa é dado de operação, não do core.** O cadastro e o vínculo moram no
   backstage; `Order.data` recebe a chave pela lista explícita do `CommitService`,
   registrada em `docs/reference/data-schemas.md` antes do uso. Nenhum campo novo em
   modelo do core.
5. **`table_label` do Yooga não vira verdade de canal** — nem depois de F2. Se a
   contagem mostrar boa cobertura, ele serve para **medir o erro** da inferência, e é
   assim que deve aparecer.
6. **Modo de consumo inferido não vale para decisão operacional.** É leitura de
   gestão: mix, ticket, cesta, tendência. Nada de fila, cozinha ou fiscal deve passar
   a depender dele — inferência é boa para entender o negócio e ruim para mandar em
   alguém.

---

## 7. Perguntas ao dono

1. **O salão vai passar a abrir comanda por mesa?** Agora essa pergunta decide **só o
   F4** — com o modo de consumo inferido, F3 anda sem ela. Se sim, a ocupação mede a
   casa; se não, mede uma fatia com cobertura declarada, e talvez F4 não se pague.
   *(Pergunta reformulada em 17/08: antes ela decidia as duas frentes.)*
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
6. **Bebida pronta ancora sozinha — confirmar depois de ver o número.** A formulação
   original do estudo pedia bebida pronta *acompanhada*; a sua frase de 17/08 a torna
   âncora por si. Concordo com o raciocínio (levar bebida é desprezível aqui), e
   proponho só congelar depois do F2-2, que mostra de quanto é o deslocamento.
