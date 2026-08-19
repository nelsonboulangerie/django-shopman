# BI-CONSUMPTION-PROFILES — quem são os clientes de balcão, em três perfis (Frente A, v1)

> Status: **IMPLEMENTADO em 18/08/2026** (branch `feat/bi-consumption-profiles`, a partir de `origin/main`).
> Decisões do dono (18/08): faixas por **ocasião** · **24 assentos** no RevPASH · combos do Yooga
> como **consome-aqui** · **três colunas** (piso · vigente · teto). Ver §6 para o que saiu e §7 para os números.
> Alvo: staging.
> Irmão de [BI-QUESTION-CATALOG](BI-QUESTION-CATALOG.md) (F3 = a regra que este plano reaproveita).
> Não antecipa nada do refactor do B.I. planejado em frente separada.

## 0. A pergunta

Pedidos de **balcão** (delivery e iFood fora), em três perfis:

- **A — Só pra levar** · **B — Consumo local + pra levar** · **C — Só consumo local**

Para cada perfil: nº de pedidos, % dos pedidos, receita, % da receita, ticket médio, itens médios
por pedido, distribuição por faixa de hora. Recortes: dia da semana × faixa de hora × período.
Mais quatro consultas sobre a mesma base: receita por categoria (bebidas prontas em destaque),
strike rate de bebida, bebidas por pedido nos pedidos com item local, RevPASH por faixa.

## 1. Verificação prévia — o que existe (medido no staging em 18/08/2026, leitura pura)

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Histórico Yooga tem **linha de item por pedido**? | **Sim.** `HistoricalSale` 81.255 vendas (16/01/2024 → 20/07/2026) · `HistoricalSaleItem` **380.199 linhas**. Só 1 venda sem item. ⚠️ `qty` é sempre 1 (o export abre uma linha por unidade) — "itens por pedido" sai como unidades **e** produtos distintos. |
| 2 | Campos | `occurred_at` (com hora, UTC → local ok), `is_delivery` (único rótulo de canal confiável), `sku` (vazio em 27.177 linhas), `product_name`, `category` (10 categorias do Yooga), `qty`, `unit_price_q`, `line_total_q`, `total_q` da venda. |
| 3 | Sinal direto de consumo local? | **Não.** `modality`/`origin`/`table_label` existem crus e estão **declarados não confiáveis** (decisão registrada, não reabrir). Não há outro sinal. |
| 4 | Trabalho anterior | **Existe e está no `main` (PR #183, F3).** `ConsumptionRole` (3 leituras: `anchor` "Consome aqui" · `takeaway` "Leva" · `hybrid` "Híbrido") + `ProductConsumptionTag` (SKU → papel, **editável no Admin**, 59 curadas pelo dono + 131 propostas no staging) + `classify_basket()` (função pura) + dimensão `consumption_mode` no explorador + `bi_calibrate` (variantes por remapeamento). |

**Vocabulário: o seu `local`/`viagem`/`ambíguo` = o `anchor`/`takeaway`/`hybrid` já curado.**
Não renomeio nada (rename em massa é hostil a merge; enum em inglês, rótulo em pt-BR já é a
regra). Os perfis A/B/C são exatamente os modos `takeaway`/`dine_in_takeaway`/`dine_in` que a
regra vigente já devolve — a sua tabela ("só viagem ± ambíguos → A", etc.) **é a regra que está no
código**, com o híbrido transparente. O que falta é o relatório, os recortes, as duas leituras
extremas e as quatro consultas.

### 1.1 Sanidade contra a sua amostra (2025, balcão, 37.833 pedidos)

| Referência da amostra | Medido no histórico | |
|---|---|---|
| 37% com bebida | **35,6%** com café/chá/bebida pronta | ✓ |
| 32% com café/chá preparado | **29,4%** | ✓ |
| café = 9% da receita | **9,04%** (categoria Cafés) | ✓ |
| bebida pronta 0,9–1,4% (estimada por diferença) | **1,85%** (categoria Bebidas; água mineral é ~0,7 pp disso) | acima da estimativa — vale a medida real |
| 3,1 itens distintos/pedido · 20% item único | 4,83 unidades/pedido; 12,3% com uma linha | ⚠️ unidades ≠ distintos; o relatório vai medir os dois |

Retrato do `bi_calibrate` (2025, sem a reserva por categoria): local 19,1% · local+levar 7,1% ·
levar 59,3% · entrega 6,0% · sem etiqueta 8,6%. Com a reserva por categoria (que o explorador já
usa) o local sobe para ~23,5%. **A classificação está no rumo da amostra; nada indica etiqueta
errada.**

### 1.2 Três achados que mudam a resposta (e cabem no plano)

1. **"Combo Cola + Hotdog" e irmãos: 9.255 linhas, R$ 233 mil, em 5.527 vendas (jul/24 → jul/25),
   sem SKU e sem categoria.** Hoje são invisíveis para a regra → essas vendas saem "sem etiqueta"
   (~7% do total). São recuperáveis **pelo nome**. Proposta: a etiqueta aceita chave `nome:<produto>`
   para linha sem SKU (a mesma convenção que o explorador já usa em `_sales_item_rows`), e as quatro
   entram como **proposta** (`reviewed=False`) para você confirmar no Admin — sugestão: `consome-aqui`
   (lanche montado + bebida). Se preferir "sem etiqueta", basta não confirmar.
2. **Não existe "faixa de hora"** no B.I. — só hora cheia. Proposta: faixas fixas de 2h alinhadas ao
   expediente (**9–11 · 11–13 · 13–15 · 15–17 · 17–19**; fora disso "outros", declarado). Pico real:
   15–17h = 31,6% dos pedidos de 2025. Constante numa tupla só, trocar é uma linha.
3. **Assentos: o cadastro do salão soma 22** (4 mesas int. ×2 + 4 ext. ×2 + 6 balcão) **e você disse
   24.** O RevPASH lê o cadastro (`SeatingSpot`, editável no Admin, "uma pergunta, um dono") e mostra
   o denominador na tela. Se 24 é o certo, é ajuste de cadastro, não de código — me diga qual mesa
   tem 4 lugares (ou eu uso 24 e aponto a divergência).

## 2. O que será construído (mínimo que a resposta exige)

### 2.1 Regra — `shopman/backstage/services/consumption.py` (funções puras, portáveis)

- **Três leituras da classe ambígua**, todas remapeando as etiquetas e chamando a **mesma**
  `classify_basket` (como o `bi_calibrate` já faz — nunca uma segunda regra):
  - `piso` — híbrido lido como `viagem` (piso de consumo local; A no máximo)
  - `vigente` — híbrido transparente (a regra do F3; é o que o explorador mostra)
  - `teto` — híbrido lido como `local` (C no máximo)
- Perfil = modo: A=`takeaway`, B=`dine_in_takeaway`, C=`dine_in`; `unclassified` e `delivery` seguem
  como baldes **declarados** (o primeiro é a cobertura; o segundo está fora da pergunta, mas entra
  na conciliação).
- Flags derivadas por pedido (`has_local_item`, `has_takeaway_item`, `has_beverage`,
  `beverage_count`) calculadas na coleta, nunca no template.
- `reading_for(sku, name, category, …)`: chave `nome:<produto>` como reserva antes da categoria.

### 2.2 Bebida vira **dado**, não string — 1 campo + 2 papéis (migração aditiva no backstage)

Três das quatro consultas extras precisam saber "esta linha é bebida? preparada ou pronta?". Nada
hardcoded por nome de categoria: `ConsumptionRole` ganha `beverage` (`""` · `prepared` · `ready`),
visível no Admin. O vocabulário do seed/`setup_bi_reference` ganha `bebida-preparada` e
`bebida-pronta` (ambos `reading=anchor`, portanto **zero mudança nos perfis** — teste garante) e as
~30 bebidas da curadoria migram para eles. A reserva por categoria do histórico passa a carregar o
tipo de bebida junto (`Cafés`/`Festival Chai` → preparada; `Bebidas` → pronta).

### 2.3 Projection — `shopman/backstage/projections/bi_profiles.py` (isolada, sem UI dentro)

`build_bi_consumption_profiles(date_from, date_to, weekday=None, hour_band=None)` → dataclass
`BIConsumptionProfilesReport`:

- **coleta única** por janela: vendas nativas (dia nativo vence, mesma fusão do `bi_sales`) +
  históricas, com linhas resolvidas; delivery separado; extraída para `services/consumption.py`
  (`collect_baskets`) e **reaproveitada** por `bi_explore._consumption_modes` (um dono, dois
  consumidores).
- por leitura (piso/vigente/teto) × perfil (A/B/C + sem etiqueta): pedidos, % pedidos, receita,
  % receita, ticket médio, unidades/pedido, produtos distintos/pedido, distribuição por faixa.
- **sensibilidade**: % de pedidos que muda de perfil entre piso e teto; a faixa por perfil.
- **conciliação declarada**: A+B+C+sem etiqueta+entrega = faturamento do período pela leitura atual
  do `bi_sales` — número mostrado e **testado**; se não bater, o teste quebra.
- **período anterior** (mesmo padrão F7 do `bi_sales`) para comparar anos/meses.
- **quatro consultas**: receita por categoria (histórico: `category`; nativo: coleção do produto;
  bebida pronta destacada; declara a diferença item×cabeçalho — desconto/acréscimo de venda,
  R$ 39 mil nos 2 anos); strike rate de bebida por dia da semana × faixa; bebidas/pedido nos pedidos
  com item local; RevPASH por faixa = receita dos pedidos com item local ÷ (assentos oficiais ×
  horas da faixa × dias com venda no recorte).

### 2.4 API + superfície

- `GET /api/v1/backstage/bi/consumption-profiles/?date_from&date_to&weekday&hour_band` (perm
  `backstage.view_bi`, mesma base `_BIBase`); contrato regenerado por `export_bi_schema`.
- `surfaces/bi-nuxt/app/pages/profiles.vue`: seletor de período (o existente), filtros dia da
  semana e faixa, **piso · vigente · teto lado a lado**, tile de sensibilidade, matriz faixa ×
  perfil, os quatro blocos extras, linha de conciliação e o aviso "perfil **presumido** pela cesta —
  regra e etiquetas em Configurações › Como vendemos". Monocromático, cor só funcional; entrada na
  home do B.I.

### 2.5 Testes

Regra (3 leituras, casos de borda, `nome:`), bebida (flag no papel; perfis inalterados), coleta
(fusão nativo/histórico igual ao explorador), **conciliação = faturamento do `bi_sales`**, filtros,
RevPASH (denominador do cadastro), contrato TS sem drift, presentation do bi-nuxt (vitest).

## 3. O que NÃO entra

Captura no PDV · vínculo comanda↔mesa · rename `anchor`→`eat_in` · qualquer refactor do B.I. ·
mudança em `packages/*` · leitura de `table_label` · materialização (o explorador já varre 380k
linhas por pedido; medir p95 no staging antes de otimizar).

## 4. Deploy no staging (depois do merge)

✅ Feito em 18/08: `migrate` (0022) → `setup_bi_reference` → combos e os 61 "Pães Finos"
revisados pelo dono no Admin/por script; a curadoria foi levada ao seed em seguida (PR próprio),
então `setup_bi_reference` num ambiente novo instala tudo já revisado. Nunca `seed` no staging.

## 5. Decisões (respondidas pelo dono em 18/08/2026)

1. **Faixas por ocasião**: Manhã 9–11 · Almoço 11–14 · Tarde 14–17 · Fim de dia 17–19 (+ "fora do
   expediente", declarado). Fronteiras onde a curva horária de 2025 muda de regime; moram numa tupla
   (`services/hour_bands.py`). ⚠️ A hora é a do REGISTRO da venda (NFC-e = pagamento): quem almoça às
   13h e paga às 14h05 cai em "Tarde" — a tela diz isso.
2. **24 assentos** no RevPASH. Deliberadamente **não** lê o cadastro do salão (`SeatingSpot`, 22): aquele
   número foi calibrado para "bateu no teto" (o sofá que aperta não conta lá, de propósito); aqui a
   pergunta é quantos assentos há para render, e o dono respondeu 24. Constante declarada com a fonte
   na tela (`REVPASH_SEATS`).
3. **Combos** Cola/Citrus + Hotdog/Donut → `consome-aqui`, pelo NOME (`nome:<produto>`), como
   **proposta** (`reviewed=False`) para confirmar no Admin. **Não** entram como bebida: a linha é o
   combo inteiro, e contá-la como refrigerante jogaria R$ 140 mil de hotdog na receita de bebida pronta.
4. **Três colunas** lado a lado.

## 6. O que foi construído

- `services/consumption.py`: leituras `floor`/`current`/`ceiling` por remapeamento na mesma
  `classify_basket`; chave `nome:` para linha sem SKU; bebida (`beverage_for`, reserva por categoria
  `Cafés`→preparada, `Bebidas`→pronta; papel sem tipo de bebida **não veta** a categoria — no staging
  os cafés do Yooga estão etiquetados "consome aqui" por proposta automática); **coleta única**
  `collect_baskets` + `fuse_baskets` (dia nativo vence), reaproveitada pelo explorador
  (`_consumption_modes`) e pelo salão.
- `services/hour_bands.py`: as faixas por ocasião.
- `ConsumptionRole.beverage` (`""`/`prepared`/`ready`, migração `backstage 0022`, aditiva) + papéis
  `bebida-preparada`/`bebida-pronta` (leitura `anchor` — perfis inalterados, testado) no seed e no
  `setup_bi_reference`; 13 bebidas curadas migram para eles (água → pronta).
- `projections/bi_profiles.py` → `GET /api/v1/backstage/bi/consumption-profiles/?date_from&date_to&weekday&hour_band`
  (perm `backstage.view_bi`); contrato TS regenerado.
- `surfaces/bi-nuxt/app/pages/profiles.vue` (aba **Perfis**): filtros dia da semana × faixa,
  3 leituras lado a lado, faixa piso–teto + período anterior, conciliação, perfil × faixa, receita por
  categoria (bebida pronta destacada), bebida no pedido (strike rate dia × faixa, café/chá,
  bebidas por pedido local), RevPASH por faixa com denominador à vista.
- `propose_consumption_tags`: para bebida do histórico propõe o papel que declara o tipo de bebida.
- Testes: `test_bi_profiles.py` (31) + ajustes em `test_bi_calibration.py`; vitest do bi-nuxt;
  `nuxi typecheck` limpo.

## 7. Medido (cópia local do staging, 2025, balcão = 37.833 pedidos, R$ 2.124.088,85)

| | Piso | **Vigente** | Teto |
|---|---|---|---|
| A · só pra levar | 56,5% · R$ 1.126 mil | **56,5%** · ticket R$ 52,67 | 13,8% |
| B · local + levar | 31,1% | **10,2%** · ticket R$ 82,62 | 32,9% |
| C · só local | 12,3% | **33,2%** · ticket R$ 53,88 | 53,3% |
| sem etiqueta | 0,0% (1 pedido) | | |

**Revisão dos 61 "Pães Finos" (SKUs do Yooga) feita pelo dono em 18/08 e gravada no seed
(`_seed_historical_consumption_tags`, instalada pelo `setup_bi_reference`):** 18 pães de
abastecimento → `leva` (forma, burger bun, pão de hot dog, pita, challah, nanterre, kuro pan);
salgados montados e viennoiserie → `hibrido` confirmado — **regra fixada: a bebida no pedido é
que define; salgado sozinho não ancora**. Efeito 2025: mudam piso→teto **63,6% → 54,4%**;
vigente A 56,5% · B 12,7% · C 30,8%. A largura que sobra é croissant, pain au chocolat e
madeleine, híbridos de propósito.

**Segunda rodada (19/08, 70 propostas restantes, também no seed):** cafés/chás do Yooga →
`bebida-preparada`; croques/queijo quente/jambon/pain perdu → `consome-aqui`; pães rústicos,
chás Kãnfa e SKUs iFood → `leva`; **ciabatta, tabatière, fendu e mini baguete → `hibrido`**
(como no cardápio 2027, embora só 14–18% das vendas levem bebida) e mini focaccias → `hibrido`.
Zero propostas restantes. Efeito 2025: mudam piso→teto **64,9%** (a ciabatta, R$ 171 mil, voltou
para a classe ambígua); vigente A 56,5% · B 9,8% · C 33,7%.

**Conciliação:** balcão R$ 2.124.088,85 + entrega R$ 178.064,20 = **R$ 2.302.153,05 = `bi_sales`** ✓
(testado e conferido na aba Vendas). **63,6% dos pedidos mudam de perfil entre piso e teto** — a
faixa é larga porque "Pães Finos" (55% da receita, 61 SKUs, todos etiquetados híbrido por proposta
automática) está em quase toda cesta. Revisar essas 61 propostas no Admin (ex.: "Forma Artesanal - 6
Fatias", R$ 82 mil, é claramente de levar) estreita a faixa sem tocar em código.

**Sanidade contra a amostra:** 35,6% com bebida (ref 37%) · 29,4% com café/chá preparado (ref 32%)
· café 9,7% da receita por linhas (ref 9%) · 3,1 produtos distintos/pedido no vigente (ref 3,1) ·
bebida pronta industrializada **2,0%** (ref 0,9–1,4% estimado — água mineral é ~0,7 pp).
Strike rate por faixa: manhã 48% · almoço 32% · tarde 31% · fim de dia 44%; sábado 39% (o maior).
RevPASH 2025: manhã R$ 17 · almoço R$ 12,5 · tarde R$ 18 · fim de dia R$ 10 por assento-hora
(24 assentos × 282 dias); sábado de manhã R$ 34.

## 8. Da vocação ao peso — a leitura em graus (pedido do dono, 19/08/2026)

> *"No momento estamos muito booleanos. Associar algum peso à vocação do SKU talvez mostre
> um número mais realista."* — concordo: a faixa piso–teto de ~65% é a regra sendo honesta
> sobre o que não sabe, não um retrato.

### 8.1 Passo 1 — pesos declarados ✅ (implementado 19/08)

- **Dado, não código:** `ConsumptionRole.eat_in_weight` (default por leitura: consome aqui /
  bebidas 95 · leva 5 · híbrido 50, editável) e `ProductConsumptionTag.eat_in_weight` (override
  por SKU, vazio = herda do papel). Migração `backstage 0023`, aditiva. Linha sem etiqueta usa
  a categoria do histórico → leitura → peso de partida (`DEFAULT_WEIGHT_BY_READING`).
- **A cesta vale o seu MAIOR peso** (`Basket.eat_in_probability`): P(alguém sentou) = max(peso).
  Não multiplica — multiplicar suporia independência entre os itens de uma mesma pessoa e "café
  + croissant" viraria quase certeza por contagem. Com o máximo, o café (95) já disse que alguém
  sentou; o croissant não muda isso. Entrega = 0; cesta sem peso = fora da conta, declarada.
- **Na tela:** bloco "Estimativa ponderada: quantos comeram aqui" — ≈ pedidos com alguém sentado
  (% e receita), ≈ só vieram buscar, pedidos com/sem peso, % que comeu aqui por faixa, delta vs
  período anterior. Rotulado como esperança sob os pesos vigentes; a faixa piso–teto continua
  logo abaixo como o que o dado garante.
- **No Admin:** peso por papel (lista editável) e por SKU; na tela do SKU, a **dica do histórico**
  (`sku_signal`): vendas de balcão, % com bebida, % sozinho, % em 4+ unidades — para ninguém
  decidir o peso no escuro.
- **Com os defaults** (híbrido 50), 2025 dava ≈ 63,8% de pedidos com alguém sentado — o prior
  neutro falando (quase toda cesta tem um híbrido a 50).
- **O dado inclina os híbridos — `measure_eat_in_weights` (19/08, pedido do dono: "faça uma
  média, para onde este SKU inclina").** Para cada SKU híbrido mede-se a % das vendas de
  balcão dele com bebida e compara-se com a média da casa (35%): peso = (P(bebida|SKU) −
  P(bebida)) / (1 − P(bebida)). Na média → piso 5; 100% → teto 95. ⚠️ A co-ocorrência crua
  (croissant 41% → peso 41) contaria o café duas vezes e daria 60% de pedidos com alguém
  sentado, contra os ~38% do estudo do dono; a lift dá **49%**. Âncoras (95) e leva (5) ficam;
  variante "M"+SKU e gêmeo do cardápio 2027 (CROISSANT ↔ CT) herdam; < 30 vendas fica no
  papel, declarado. Rodado no staging com `--apply`: 58 pesos (CPQ 37 · FF 29 · DL 26 · PC 23
  · CN 22 · CM 22 · BH 20 · MD 15 · CT 9 · CI/TB/FE 5…). **2025: ≈ 18,7 mil pedidos com
  alguém sentado (49,3%), R$ 1,14 mi (53,6% da receita); ≈ 19,2 mil só buscaram (50,7%)**;
  por faixa: manhã 61% · almoço 48% · tarde 44% · fim de dia 55%. Reproduzível em qualquer
  ambiente com o histórico carregado.

### 8.2 Passo 2 — pesos medidos pela comanda (desenhado; depende de dado nativo real)

A única coisa que aproxima o número da realidade sem pedir nada ao balcão é um peso **medido**.
E há um sinal automático que já existe: **a comanda** ("sempre abrimos comanda, ponto").
`Session.opened_at → committed_at` é o tempo que a venda ficou aberta; comanda de 25 min com
croissant é alguém sentado, comanda de 90 s com croissant é alguém que levou. É o mesmo sinal
que o salão (F4) já usa.

Desenho, para quando houver pedidos nativos de verdade (o staging tem ~200 de teste — nada
a medir):

1. **Limiar "sentou"** sai da própria distribuição das durações de comanda (esperada bimodal:
   balcão rápido × mesa), não de opinião; aparece na tela junto do número de comandas medidas.
2. **Peso medido por SKU** = P(comanda acima do limiar | SKU na cesta), calculado sobre o nativo
   e **proposto** como `eat_in_weight` (como o `propose_consumption_tags` propõe a leitura):
   campo `weight_source` (declared / measured), `measured_n` (tamanho da base) e data. O dono
   confirma ou não; peso medido com base pequena aparece como proposta, nunca como fato.
3. **Vale para trás:** o peso é por produto, e os produtos do Yooga são os mesmos de hoje —
   o histórico é reponderado sem tocar em nada.
4. **Onde mora:** um comando `measure_eat_in_weights` (imprime e propõe; não grava sem
   `--apply`) + a coluna de origem do peso no Admin e na tela ("peso medido em N comandas" vs
   "peso declarado"). Nenhuma captura nova no PDV; nenhum vínculo comanda↔mesa.
5. **Ressalva que fica na tela:** a janela é a comanda, não o tempo sentado — inclui o tempo em
   pé no balcão; é por isso que o limiar vem da distribuição e não de um minuto fixo.

Fora do escopo até lá: modelos com mais features (hora, dia, total), que sem verdade de campo
seriam só pesos disfarçados.
