# WP: Receitas do dono (inventário das três planilhas)

> Pedido do dono em 02/10/2026: *"Prefiro que lance uma WP dedicada, onde você vai ter
> que vasculhar e tentar extrair receitas"*.

**Estado:** inventário feito (seções A e B). O dono respondeu às perguntas 1 a 4 em
02/10/2026, e a **proposta de estrutura** para Tradição, Campagne, Ciabatta e Levain,
a partir da Fx, está na seção C. **Parado esperando o aval escrito do dono** para
executar. Nada entrou em banco, seed ou fixture.

## Fontes (só estas, indicadas pelo dono em 02/10/2026)

| # | Planilha (título no Drive) | Link | Abas autorizadas |
|---|---|---|---|
| 1 | RECEITAS 2.4 | <https://docs.google.com/spreadsheets/d/1UY0F0JiY3jxA_E0tcGwFMoj4j12elpgS7NsyoXQFVNA> | **CIAB, CAMP, TRAD** (só estas) |
| 2 | Ficha Técnica - Maysa | <https://docs.google.com/spreadsheets/d/1xVzeJYBEB12ed9dkntfPIzi6nUuD3Sjo1Zp1o4U5paI> | a planilha inteira (começando por gid=0) |
| 3 | ANÁLISE_CUSTOS_CVL_2021 - ficha técnica | <https://docs.google.com/spreadsheets/d/191t8nZdMCHynrksr0ZMihuSDwmDsiOyJ1ThwsufYWuw> | **Fx, MP** (só estas) |

## Regras duras do dono

- Ler só o que foi indicado.
- **Nunca inventar** quantidade, tempo, temperatura, etapa, rendimento ou insumo que não
  esteja na planilha. Onde a planilha não diz, escreve-se "a planilha não diz".
- Preservar os números exatamente como estão.
- **Não copiar a planilha para dentro do repositório**: nada de CSV, nada de tabela com as
  quantidades das receitas. Este documento diz *o que existe*, nunca *quanto*.
- Nada entra no sistema (banco, seed, fixtures) sem o aval escrito do dono.
- **Primeiro o inventário, e parar.** Sem propor estrutura, sem mapear para o modelo.
- A proposta das 92 etapas de 05/09
  ([`processo-das-massas-proposta-2026-09-05.md`](../reference/processo-das-massas-proposta-2026-09-05.md))
  deixa de ser fonte: serve só de **lista de conferência**, para apontar o que as planilhas
  cobrem ou não cobrem. Nunca para preencher lacuna.

## Como foi lido

- O conector do Google Drive (`read_file_content`) devolve só a **estrutura** de uma
  planilha (nome das abas, intervalo, amostra da primeira linha), não o conteúdo das
  células. Não há parâmetro para escolher aba. Na fonte 1, essa chamada listou os nomes
  de todas as abas; o conteúdo das abas não autorizadas não foi lido.
- O conteúdo veio do Chrome do dono, já logado no Drive: exportação CSV **por aba**
  (`export?format=csv&gid=…`), uma aba por vez, só as autorizadas. Sai o **valor exibido**
  de cada célula, não a fórmula. Por isso "fórmula quebrada" aqui quer dizer erro visível
  (`#DIV/0!`) ou valor implausível; a fórmula em si não foi lida. Comentários de célula e
  formatação (cor, mesclagem) também não.
- Nada do conteúdo foi gravado em disco nem no repositório.

---

## A) Inventário, por fonte e por aba

Legenda das tabelas: **sim** = a planilha traz; **não** = a planilha não diz;
**qualit.** = só em palavras ("fogo baixo", "aquecimento brando"), sem número.

### Fonte 1: RECEITAS 2.4 (abas CIAB, CAMP, TRAD)

**O que as três abas são.** Não são receita com modo de fazer: são **calculadoras de
fornada** de uma família de massa cada. As três têm o mesmo desenho:

1. **Lista de peças** da família: nome com código entre colchetes, código, peso da peça,
   quantidade encomendada, quantidade a produzir por fornada (colunas 1ª, 2ª, 3ª), total
   e subtotal em massa.
2. Linhas de **massa velha**, **margem de segurança** e **PTM** (peso total de massa).
3. A **fórmula da massa** em porcentagem de padeiro (`F100`, `% Plan.`), repartida em
   colunas **PA**, **LV** (levain), **MV** (massa velha) e **MF** (massa final), com a
   soma em grama e a participação de cada insumo.
4. Um gabarito fixo de linhas de insumo (farinha orgânica especial, farinha orgânica
   integral, farinha de centeio integral, água, leite integral, ovos, manteiga, azeite,
   açúcar, sal com a nota "3% relativo aos líquidos!", fermento fresco); só algumas linhas
   têm valor em cada aba.
5. Um bloco de **composição nutricional** por 100 g e a **perda aproximada pós-forno**.

| Aba | Massa | Peças listadas | Insumos | Quantidade | Unidade | Rendimento | Etapas / modo de fazer | Tempo | Temperatura | Custo |
|---|---|---|---|---|---|---|---|---|---|---|
| CIAB | ciabatta | 15 | sim | sim (% e grama) | grama e % | indireto (PTM e perda pós-forno) | não | não | não | não |
| CAMP | campagne | 10 | sim | sim (% e grama) | grama e % | indireto (PTM e perda pós-forno) | não | não | não | não (há R$ soltos fora do bloco, sem rótulo) |
| TRAD | tradição | 11 | sim | sim (% e grama) | grama e % | indireto (PTM e perda pós-forno) | não | não | não | não |

O **levain** aparece como coluna (LV) nas três, mas a composição dele não está nessas
abas: a planilha tem uma aba LEVAIN, que não está entre as autorizadas.

**Peças, como a planilha escreve** (código e nome; o peso que a planilha escreve junto
ao nome foi omitido aqui de propósito):

- **CIAB:** [CI] Ciabatta · [CI] Ciabatta Peq (código CIP) · [CIQ] Ciabatta Quadrada ·
  [CIM] Mini Ciabatta · [BE] Baguete Gergelim · [BEP] Baguete Gergelim Peq · [BAP]
  Baguetinha Peq · [FOA] Focaccia Alecrim · [FOC] Focaccia de Cebola Roxa · [CBT] Focaccia
  de Bacon,C&T · [FOL] Fougasse aux Olives e Lardons · Mini Focaccia (código MIF) · [VQ]
  Vulcão de Alho (código VQA) · [EP] Pain d'Êpi · [MEP] Mini Êpi.
- **CAMP:** [CGO] Pain de Campagne Oval · [CGR] Pain de Campagne Redondo · [CF] Baguette
  Campagne · [CFP] Baguette Campagne Peq · [CP] Petit Campagne · Campagne Passas & Cast
  (Peq) (código CPXP) · [CPX] Campagne Passas & Castanha (Grande) · Campagne Figos &
  Amêndoas (código CFA) · Mega Campagne · Pão do Croque CW.
- **TRAD:** [PH] Pão de Hambúrguer Rústico · [TB] Tabatière · [FE] Fendu · [MIB] Mini
  Baguete · [DBP] Baguette Pequena · [DB] Demi Baguete · [BF] Baguete Francesa · [BA]
  Bâtard · [BL] Boule · [BAX] Batard Grande · [BAXG] Batard XG.

**Ambiguidades na fonte 1**

- **Peso no nome diferente da coluna Peso** em FOL, EP, MEP (CIAB), CGR, CPX (CAMP) e
  BAXG (TRAD). Em parte delas há nota ao lado do tipo "era …"; em CGR a coluna Peso tem um
  valor que não pode ser peso de pão.
- **Código no nome diferente da coluna Código:** "[CI] Ciabatta Peq" tem código CIP;
  "[VQ] Vulcão de Alho" tem código VQA. Mega Campagne e Pão do Croque CW têm um número na
  coluna Código, não um código.
- No painel lateral da CAMP aparece "[CGRM] Campagne Grande Redondo Maior" com um peso que
  não é de pão; essa peça não está na lista principal.
- **CAMP** tem, ao lado da fórmula, sequências numéricas longas sem rótulo (parecem código
  de barras ou linha digitável), valores em R$ sem rótulo junto das linhas de sal e
  fermento, e um cálculo de volume de forminha para o "campagne fatiado (Croque)".
- **CAMP**: CPX traz massa e recheio separados no painel lateral e a nota "Versão moldada
  era … massa + … recheio"; a **composição do recheio** (passas, castanha) não está na aba.
  "Campagne Figos & Amêndoas" também não tem recheio descrito.
- **TRAD, composição nutricional:** valores implausíveis (água negativa, farinha com
  milhares de gramas em 100 g). Fórmula quebrada ou referência deslocada.
- **CIAB:** `#DIV/0!` numa célula ao lado da linha de água; a linha do azeite tem a nota
  "OBSERVAR!".
- Notas datadas soltas nas células (ex.: o peso do Pão do Croque CW "Era … até 09/04/2026.
  Era … até 27/12/2025"), mostrando que a aba é viva e editada.
- A **margem de segurança** é diferente em cada aba.

### Fonte 2: Ficha Técnica - Maysa (todas as abas)

A planilha tem **3 abas**: `Página1` (gid=0), `Página2` e `Ingredientes`.

**Página1: fichas técnicas de preparo** (cozinha e confeitaria, não massa de pão). Cada
ficha segue o mesmo molde: "Produção" + nome, data, tabela de ingredientes (unidade,
quantidade líquida, rendimento % / fator de correção, quantidade bruta, custo unitário,
custo bruto), custo total, rendimento, validade e "PREPARO". As datas vão de 2017 a 2022.
**33 fichas**:

| # | Nome na planilha | Insumos | Qtd + unidade | Fator de correção | Custo | Rendimento | Validade | Modo de fazer | Tempo | Temperatura |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Cebola Bacon Tomilho - Focaccia Grande | sim | sim | sim | parcial (vários R$ 0,00) | sim | sim | sim | não | qualit. |
| 2 | Cebola Bacon Tomilho - Focaccia Mini | sim | sim | sim | parcial | sim | sim | sim | não | qualit. |
| 3 | Recheio Citron | sim | sim | sim | zerado | sim | sim | sim (+ utensílios) | não | sim |
| 4 | Jambon Beurre | sim | sim | sim | sim | sim | não | sim | não | não |
| 5 | Manteiga de Wassabi ("PARAMOS AQUI") | sim | sim | sim | sim | sim | sim | sim | sim | não |
| 6 | Geléia de Morango (com nota "PARA A BASE DE MORANGO") | sim | sim | sim | sim | sim | sim | sim | não | sim |
| 7 | Geléia de Laranja | sim | sim | sim | zerado | sim | sim (duas, divergentes) | sim | não | não |
| 8 | Cebolas Assadas | sim | sim | sim | sim | sim | sim | sim | sim | não (só "forno 3 (pedra)") |
| 9 | Ratatouille | sim | sim | sim | sim | sim (+ porção) | sim | sim | não | sim |
| 10 | Creme de Chocolate! | sim | sim | sim | zerado | sim | sim | sim | não | não |
| 11 | Manteiga de Mel | sim | sim | sim | zerado | sim | sim | sim | não | não |
| 12 | Manteiga de Bacon | sim | sim | sim | zerado | sim | sim | sim | não | não |
| 13 | Manteiga de alho e salsa | sim | sim | sim | parcial | sim (+ porção) | sim | sim | sim | qualit. |
| 14 | Caramelo Salgado | sim | sim | sim | sim | sim (+ porções) | sim (+ "validade loja") | sim | sim | sim |
| 15 | Creme de Caramelo | sim | sim | sim | zerado | sim | sim | sim | sim | não |
| 16 | Torradas pão de sal (receita para 1 assadeira) | sim | sim | sim | sim | sim | sim | sim (em partes, duas versões) | sim | sim |
| 17 | Queijo quente | sim | sim | sim | sim | não | sim | sim | não | não |
| 18 | "O" presunto cozido da Nelson Boulangerie <3 | sim | sim | sim | sim | sim (+ porções) | sim | sim | sim | sim |
| 19 | salmoura presunto | sim | sim | sim | sim | não ("para cada quilo de carne") | não | não | não | não |
| 20 | Creme de Morango | sim | sim | sim | zerado | sim | sim | não | não | não |
| 21 | Croque-monsieur | sim | sim | sim | sim | não | sim | sim | sim | não |
| 22 | Cramberry no vinho | sim | sim | sim | zerado | não | sim | sim (2 linhas) | não | qualit. |
| 23 | Tapenade versão Malageña | sim | sim | sim | sim | sim | sim | sim | sim | não |
| 24 | Tapenade (azeitonas Vale Fértil, ao lado da 23) | sim | sim | sim | parcial | sim | sim | sim | sim | não |
| 25 | Creme Pain Perdu | sim | sim | sim | sim | sim | sim | sim | não | qualit. |
| 26 | Pain Perdu | sim | sim | sim | sim | não | sim | sim | sim | não |
| 27 | Molho bechamel | sim | sim | sim | sim | sim | sim | sim | sim | qualit. |
| 28 | Vinagrete da Boulan | sim | sim | sim | sim | sim (dois valores) | sim | sim | sim | não |
| 29 | Recheio de Frango | sim | sim | sim | sim | sim | sim | sim | sim | não |
| 30 | Super Hot Dog ("STAND BY") | sim | sim | sim | parcial | não | sim | sim | sim | não |
| 31 | Guarnição de salada verde e tomatinhos | sim | sim | sim | sim | não | qualit. | não | não | não |
| 32 | Milk Shake de Morango ("STAND BY") | sim | sim | sim | zerado | não | não | sim (1 linha) | não | não |
| 33 | Dijonese | sim | sim | sim | sim | sim | não | sim (1 linha) | não | não |

Fora das fichas, a Página1 traz ainda: um procedimento "COMO HIGIENIZAR VIDROS DE
CONSERVAS" (com tempo), textos de vitrine de quatro pães (Pão Campagne, Brioche, Tradição,
Ciabatta, sem receita) e uma seção "Ideias" (pratos, com uma temperatura e um tempo).

**Página2:** não é receita. É um **checklist de preparos** (lista de nomes) e uma tabela de
**estoque mínimo no freezer da loja** por dia da semana (croque, queijo quente, pain
perdu).

**Ingredientes:** não é cadastro de matéria-prima. É uma **cópia mais antiga da Página1**,
com os mesmos blocos, só os **nomes** dos ingredientes (sem quantidade, sem unidade) e,
em parte deles, o preparo. Em alguns pontos o preparo **diverge** da Página1 (ver abaixo).

**Ambiguidades na fonte 2**

- **Página1 × Ingredientes divergem** no modo de fazer: Torradas (temperatura de forno
  diferente nas duas abas, e a própria Página1 traz dois números, lastro e turbo), Molho
  bechamel (tempos de cozimento diferentes), Queijo quente (passo a mais na aba
  Ingredientes), Creme de Caramelo (a aba Ingredientes lista sal, a Página1 não).
- **Sub-preparos citados sem ficha própria:** creme de baunilha (usado em Creme de
  Chocolate, Creme de Caramelo, Creme de Morango), base de morango (só uma nota dentro da
  Geléia de Morango), gordura de bacon, caldo (Recheio de Frango), hot dog pronto,
  sorvete de baunilha, caramelo (no Creme de Caramelo; não fica claro se é o Caramelo
  Salgado).
- **Unidades estranhas:** manteiga em "Unidade" com valor fracionário (fichas 5, 11, 12);
  baunilha em gotas ("gt") com nota "preciso verificar em peso"; salsa em maço com nota
  "verificar peso em kg"; leite em colher de sopa; milho em litro; sal "qb" com número.
- **Ingrediente no preparo que não está na lista:** Recheio de Frango ("SÓ FALTOU O
  LOURO"); Caramelo Salgado lista "sal do moinho" e o preparo fala em "flor de sal".
- **Rendimento em dois valores:** Vinagrete da Boulan (com a nota "dona rosa vai confirmar
  o rendimento!"); Creme de Caramelo e Torradas com o rendimento em célula deslocada.
- Uma célula "322g" se repete, sem rótulo, em cinco fichas (Creme de Caramelo, Torradas,
  Creme de Morango, Croque-monsieur, Cramberry no vinho). Parece resto de cópia.
- **Ratatouille:** a tabela lateral repete os ingredientes com os rótulos deslocados uma
  linha em relação aos valores.
- **Geléia de Laranja:** duas validades diferentes no mesmo bloco.
- **salmoura presunto × presunto cozido:** o preparo do presunto descreve a salmoura com
  volume de água diferente do da ficha da salmoura.
- **Torradas:** o cabeçalho da ficha não diz "Produção" (a célula tem "´´").
- Marcas de estado: "PARAMOS AQUI" (Manteiga de Wassabi, com anotações de teste "não
  gostei"), "STAND BY" (Super Hot Dog, Milk Shake).

### Fonte 3: ANÁLISE_CUSTOS_CVL_2021 - ficha técnica (abas Fx e MP)

**Fx: fórmula com custo.** Cada bloco é uma receita: ingrediente (com marca), preço por
kg, quantidade em kg, subtotal, total e custo por kg. Alguns blocos repetem a fórmula em
porcentagem de padeiro (`PP %`). **21 receitas**:

| Nome na planilha | Insumos | Qtd (kg) | Custo | Rendimento | Etapas | Tempo | Temperatura |
|---|---|---|---|---|---|---|---|
| MASSA TRADIÇÃO | sim | sim | sim | só a massa total | não | não | não |
| LEVAIN | sim | sim | sim | só a massa total | não | não | não |
| MASSA CAMPAGNE | sim | sim | sim | só a massa total | não | não | não |
| MASSA CIABATTA | sim | sim | sim | só a massa total | não | não | não |
| MASSA BUTTER ("Preços de 27/mar/25") | sim | sim | sim | só a massa total | não | não | não |
| MASSA BRIOCHE (três blocos, ver ambiguidades) | sim | sim | sim | só a massa total | não | não | não |
| MASSA FORMA (+ bloco "FORMA" em PP %) | sim | sim | sim | só a massa total | não | não | não |
| MASSA CROISSANT (confirmar) | sim | sim | sim | só a massa total | não | não | não |
| MASSA FOLHADO | sim | sim | sim | só a massa total | não | não | não |
| MASSA PITA | sim | sim | sim | só a massa total | não | não | não |
| MASSA MADELEINE | sim | sim | sim | só a massa total | não | não | não |
| KURO (só em PP %) | sim | sim | não | só a massa total | não | não | não |
| RECHEIO DE CREME DE BAUNILHA | sim | sim | sim | só a massa total | não | não | não |
| RECHEIO DE CREME DE CHOCOLATE | sim | sim | não (preços vazios) | só a massa total | não | não | não |
| COBERTURA DE BISCOITO | sim | sim | sim | só a massa total | não | não | não |
| RECHEIO CARANGUEJO | sim | sim | sim | só a massa total | não | não | não |
| COBERTURA DELI | sim | sim | sim | só a massa total | não | não | não |
| RECHEIO DE MAÇÃ & CANELA | sim | sim | sim | só a massa total | não | não | não |
| RECHEIO DE FRANGO | sim | sim | sim | só a massa total | não | não | não |
| CALDA DOCE | sim | sim | sim | só a massa total | não | não | não |
| PASSAS E NOZES | sim | sim | sim | só a massa total | não | não | não |

Nenhum bloco da Fx traz validade, modo de fazer, tempo ou temperatura.

**MP: lista de matérias-primas com preço.** Não é receita. Cerca de 110 materiais
(farinhas por marca, açúcares, sais, fermentos, laticínios, carnes, castanhas, chocolates,
temperos), com preço por kg em colunas por ano (o cabeçalho vai de 2021 a 2017, mas quase
só 2021 e 2020 têm valor) e um quadro de cálculo do preço do ovo por kg.

**Ambiguidades na fonte 3**

- **MASSA BRIOCHE aparece três vezes lado a lado:** o bloco de custo, um segundo bloco
  com a mesma quantidade mas outra farinha no rótulo (Anaconda) e outros preços, e um
  terceiro em PP %.
- **FORMA:** o bloco em PP % tem o sal com valor diferente do bloco MASSA FORMA.
- **KURO:** o insumo é "Farinhas", sem dizer quais.
- **Datas de preço misturadas:** Butter diz "Preços de 27/mar/25"; o título da planilha é
  2021; a MP tem colunas por ano. O mesmo insumo tem preços diferentes entre a Fx e a MP
  (ex.: farinha Rio Azul T45 na Butter e na Brioche).
- **MASSA CROISSANT** traz "(confirmar)" no título.
- "Azeito de Oliva EA" (grafia da planilha).
- Na MP, valores em "R$" e em "$" misturados, e notas soltas ("consigo por R$20/kg",
  "<<<<<").

### Ambiguidades entre fontes (o mesmo nome, conteúdo diferente)

- **Tradição, Campagne e Ciabatta** existem na fonte 1 (RECEITAS 2.4) e na fonte 3 (Fx),
  e **não batem**: a mistura de farinhas e a hidratação são diferentes (ex.: a Fx não tem
  farinha integral na Tradição nem na Ciabatta; a RECEITAS 2.4 tem; a proporção entre as
  três farinhas da Campagne difere). Não há data nas abas da fonte 1 que diga qual é a
  mais nova, exceto as notas de 2025 e 2026 dentro da CAMP.
- **Recheio de Frango** existe na fonte 2 (Maysa) e na fonte 3 (Fx) com listas de
  insumos diferentes.
- **Creme de Chocolate** existe nas duas (Maysa e Fx) com os mesmos insumos; a Fx não
  tem preço.
- **Creme de baunilha**: a Maysa usa, mas não tem ficha; só a Fx tem a composição
  ("RECHEIO DE CREME DE BAUNILHA"), sem modo de fazer.
- **Levain**: a Fx tem um bloco LEVAIN; nas abas autorizadas da RECEITAS 2.4 o levain
  só aparece como coluna.

---

## B) Cruzamento com o sistema, só por nome

Comparação por **nome**, contra as 91 receitas de `_seed_recipes` em
`config/management/commands/seed.py` (`origin/main` de 02/10/2026). Não foi comparado
conteúdo. "Provável" quer dizer que o nome não é idêntico e a correspondência pede o
olho do dono.

**Massas**

| Planilha | No seed |
|---|---|
| CIAB (fonte 1), MASSA CIABATTA (fonte 3) | `massa-ciabatta` |
| CAMP (fonte 1), MASSA CAMPAGNE (fonte 3) | `massa-campagne` |
| TRAD (fonte 1), MASSA TRADIÇÃO (fonte 3) | `massa-tradicao` |
| LEVAIN (fonte 3) | `creme-levain` |
| MASSA BUTTER, BRIOCHE, FORMA, CROISSANT, FOLHADO, PITA, MADELEINE (fonte 3) | `massa-butter`, `massa-brioche`, `massa-forma`, `massa-croissant`, `massa-folhado`, `massa-pita`, `massa-madeleine` |
| KURO (fonte 3) | `massa-kuropan` (provável) |
| nenhuma das três fontes | `massa-pasta-autolizada`, `massa-yudane` |

**Peças da fonte 1 com receita de mesmo nome no seed:** CI → `ciabatta`; BEP →
`baguete-gergelim-pequena`; BAP → `baguete-lanche` (provável); FOC →
`focaccia-cebola-roxa`; CBT → `focaccia-cebola-bacon-tomilho`; Mini Focaccia →
`mini-focaccia-alecrim` (provável); CGO → `campagne`; CGR → `campagne-redondo`; CF →
`baguette-campagne`; BF → `baguete`; BA → `batard`; BAX → `italiano-rustico` (provável).

**Peças da fonte 1 sem receita no seed:** CIP, CIQ, CIM, BE, FOA (há só
`focaccia-dia`), FOL, VQ, EP, MEP, CFP, CP, CPXP, CPX, CFA, Mega Campagne, Pão do Croque
CW, PH, TB, FE, MIB, DBP, DB, BL, BAXG.

**Fichas da fonte 2 (Maysa)**

| Na planilha | No seed |
|---|---|
| Cebola Bacon Tomilho (Grande e Mini) | `recheio-cebola-bacon-tomilho` (uma só) |
| Recheio Citron | `creme-limao` (provável) |
| Jambon Beurre | `jambon-beurre` |
| Manteiga de Wassabi | `manteiga-wasabi` |
| Cebolas Assadas | `recheio-cebolas-assadas` |
| Creme de Chocolate! | `creme-chocolate` |
| Caramelo Salgado | `molho-caramelo` |
| Queijo quente | `queijo-quente` |
| Croque-monsieur | `croque-monsieur` |
| Creme Pain Perdu | `creme-leite-ovos` (provável) |
| Pain Perdu | `pain-perdu` |
| Molho bechamel | `molho-bechamel` |
| Vinagrete da Boulan | `vinagrete-frances` (provável) |
| Recheio de Frango | `recheio-frango` |
| Guarnição de salada verde e tomatinhos | `salada-da-casa` (provável) |
| **sem receita no seed** | Geléia de Morango, Geléia de Laranja, Ratatouille, Manteiga de Mel, Manteiga de Bacon, Manteiga de alho e salsa, Creme de Caramelo, Torradas pão de sal, "O" presunto cozido, salmoura presunto, Creme de Morango, Cramberry no vinho, Tapenade (as duas), Super Hot Dog, Milk Shake de Morango, Dijonese |

**Receitas da fonte 3 (Fx) além das massas:** RECHEIO DE CREME DE BAUNILHA →
`creme-baunilha`; RECHEIO DE CREME DE CHOCOLATE → `creme-chocolate`; RECHEIO DE MAÇÃ &
CANELA → `recheio-maca`; RECHEIO DE FRANGO → `recheio-frango`. **Sem receita no seed:**
COBERTURA DE BISCOITO, RECHEIO CARANGUEJO, COBERTURA DELI, CALDA DOCE, PASSAS E NOZES.

**No seed e em nenhuma das três fontes** (por nome): `massa-pasta-autolizada`,
`massa-yudane`, `recheio-cebola-azapas`, `focaccia-dia`, `croque-madame`,
`croque-complet`, as peças de brioche e butter (coelhinho, ursinho, porquinho, challah,
hot dog, deli, cornet, buns, nanterre, chocolat), as de croissant e folhado (mini, pain
au chocolat, aux raisins, presunto e queijo, maçã, folhado de frango, bichon), shokupan,
caranguejo, kuro pan e kuro pan burger, pita, madeleine, e as 15 bebidas.

### Cobertura em relação à lista de conferência (proposta das 92 etapas, 11 massas)

| Massa da proposta | Composição em alguma fonte | Etapas, tempo, temperatura |
|---|---|---|
| Tradição | sim (fontes 1 e 3, divergentes) | a planilha não diz |
| Campagne | sim (fontes 1 e 3, divergentes) | a planilha não diz |
| Ciabatta | sim (fontes 1 e 3, divergentes) | a planilha não diz |
| Focaccia | só como peças dentro da aba CIAB; sem fórmula própria | a planilha não diz |
| Forma | sim (fonte 3) | a planilha não diz |
| Kuropan | sim (fonte 3, "KURO", farinhas sem nome) | a planilha não diz |
| Butter | sim (fonte 3) | a planilha não diz |
| Brioche | sim (fonte 3, três blocos) | a planilha não diz |
| Pita | sim (fonte 3) | a planilha não diz |
| Croissant | sim (fonte 3, "confirmar") | a planilha não diz |
| Folhado | sim (fonte 3) | a planilha não diz |

**Das 92 etapas, as três fontes cobrem zero** em tempo, temperatura e ordem. O que há de
mais perto de processo nas massas é: perda pós-forno, massa velha e margem de segurança
(fonte 1). A etapa "Refrescar o levain" tem composição na fonte 3, sem tempo nem
temperatura.

**Onde a lista de conferência e a fonte 1 discordam sobre a família da peça:**

- **PH** (Pão de Hambúrguer Rústico) está na aba **TRAD**; a proposta põe "PH hambúrguer"
  na massa **Butter**.
- **BE, BEP, BAP** estão na aba **CIAB**; a proposta põe "BEP/BE gergelim" e "BAP lanche"
  na **Tradição** (a WP-RECEITAS-DA-CASA, de 22/09, já registrava que o dono corrigiu
  Baguete Gergelim Pequena e Baguete Lanche para ciabatta).
- **Focaccias** (FOA, FOC, CBT, MIF) estão na aba **CIAB**; a proposta cria uma massa
  Focaccia separada.

---

## C) Proposta de estrutura (a partir da Fx)

> Autorizada pelo dono em 02/10/2026 (HANDOFF §0.1b, PR #1352): **(1)** a Fx (fonte 3) é a
> fonte para Tradição, Campagne e Ciabatta; **(2)** etapas, tempos e temperaturas não
> existem, ele edita depois; **(3)** para o levain vale a Fx; **(4)** PH é massa de Tradição
> e Focaccia é massa de ciabatta. As perguntas 5 a 12 seguem abertas e **não** foram
> decididas aqui.
>
> Esta seção é **proposta**. Nada foi executado, nada entrou em banco, seed ou fixture.
> Como as seções A e B, ela diz *o que existe* e *onde cada coisa entraria*, nunca *quanto*:
> nenhuma quantidade, porcentagem, preço ou custo da planilha foi escrito aqui.

### C.1 Como a Fx foi lida desta vez

- O conector do Google Drive (`download_file_content`, exportação xlsx) devolveu a
  planilha inteira; foram abertas **só** as abas Fx e MP, pelo valor exibido da célula.
  O arquivo baixado foi apagado ao final; nada ficou em disco nem no repositório.
- Os quatro blocos usados: **MASSA TRADIÇÃO**, **LEVAIN**, **MASSA CAMPAGNE** e **MASSA
  CIABATTA**. Cada bloco tem as colunas Ingrediente, Preço/kg, Quant (kg) e Subtotal, e as
  linhas Total e Custo/kg. Nenhum dos quatro tem bloco em porcentagem de padeiro (PP %).
- A MP foi lida só para conferir a grafia e a marca de cada farinha.

### C.2 O modelo do sistema que recebe a receita

Lido em `origin/main` (02/10/2026):

- **`RecipeEntry`** (`packages/craftsman/shopman/craftsman/models/recipe_book.py`) é a
  receita do inventário, com a linhagem de versões. As quatro já existem por bootstrap do
  seed, com o mesmo ref da ficha: `massa-tradicao`, `massa-campagne`, `massa-ciabatta`,
  `creme-levain` (`bootstrap_entry_from_recipe`, `services/recipe_book.py`).
- **`RecipeVersion`** é a fórmula congelada: `formula` (schema no
  `docs/plans/RECIPE-INVENTORY-PLAN.md` §3), `origin` ("a receita como chegou",
  imutável), `source`, `yield_quantity` + `yield_unit` (padrão **grama**, ADR-024, emenda
  de 24/09/2026), `steps`, `notes`, `label`.
- **`Recipe`** + **`RecipeItem`** (`models/recipe.py`) é a ficha de execução (o BOM da
  fornada): `batch_size` (rendimento base), itens por `input_sku` em grama. Só a
  **publicação** de uma versão escreve a ficha (`publish_version`).
- **Sub-receita:** na `formula`, o levain entra em `parts` como
  `{"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment"}`; os `items` são a
  fórmula base com **toda** a farinha (a do levain inclusive), e a mistura final é
  calculada (`analyze` → `final_mix`), nunca digitada. Ao publicar, o BOM vira "mistura
  final + LEVAIN como item", que é exatamente como o seed já liga a massa ao levain hoje
  (`RecipeItem` com `input_sku="LEVAIN"`, saída da ficha `creme-levain`).
- **Publicar exige todo `sku` preenchido** (`ITEM_WITHOUT_SKU`). Rascunho aceita
  ingrediente com `sku=""`.

### C.3 Como cada bloco da Fx vira receita

**Regra de unidade, igual para os quatro.** A Fx escreve tudo em **kg** (coluna "Quant
(kg)"), inclusive a água e o azeite. O sistema guarda em **grama**: cada quantidade da Fx
entra multiplicada por 1000, sem arredondar. Nenhum líquido da Fx está em litro, então
não há densidade a declarar. O `origin` da versão guarda a Fx **como está** (em kg, com a
grafia da planilha, inclusive "Azeito de Oliva EA"); a conversão para grama mora só na
`formula`.

**Rendimento.** A Fx dá só a linha **Total** do bloco, que é a soma das quantidades dos
insumos (a massa total da fórmula). Mapeia para `RecipeVersion.yield_quantity` (em grama)
e, ao publicar, para `Recipe.batch_size`. O sistema aceita rendimento igual à soma dos
insumos (`_validate_mass_balance` só recusa rendimento **maior**). **A planilha não diz**:
perda de mistura, perda no forno, quantas peças a massa rende, nem massa velha. A Fx não
tem margem de segurança nem massa velha; essas linhas existem só na fonte 1, que não é a
fonte desta proposta.

**Etapas, tempo, temperatura: a planilha não diz; o dono edita depois** (resposta 2). As
versões nascem com `steps` vazio. A proposta das 92 etapas de 05/09 não preenche nada.

#### LEVAIN → `creme-levain` (saída `LEVAIN`)

| Insumo, como a Fx escreve | SKU no sistema |
|---|---|
| Farinha de Trigo Especial Biorgânica | **sem SKU correspondente** (ver C.4) |
| Farinha de Trigo Integral Biorgânica | **sem SKU correspondente**: o único integral do sistema é `FARINHA-INTEGRAL-ORGANICA`, de marca Paullinia, não Biorgânica |
| Água | `AGUA-FILTRADA` (provável: a Fx diz só "Água") |
| Levain (a cultura que se alimenta) | `LEVAIN-LIQUIDO` (provável: é a cultura, "Fermento natural (levain)" no cadastro) |

O levain é a raiz: não tem sub-receita. A Fx escreve a cultura como um ingrediente comum
do bloco; no sistema ela é o insumo `LEVAIN-LIQUIDO`, e a saída da receita é `LEVAIN`.

#### MASSA TRADIÇÃO → `massa-tradicao` (saída `MASSA-TRADICAO`)

| Insumo, como a Fx escreve | SKU no sistema |
|---|---|
| Farinha de Trigo Especial Biorgânica | **sem SKU correspondente** |
| Água | `AGUA-FILTRADA` (provável) |
| Sal Refinado | `SAL-REFINADO` |
| LEVAIN | `LEVAIN` = parte (pré-fermento) com `entry_ref: creme-levain` |

**Como a Fx expressa o levain:** como **uma linha de ingrediente pronto** ("LEVAIN", em
kg, com preço próprio), igual às outras. Ela não diz quanto da farinha da massa passou
pelo levain. No sistema, essa linha vira a parte `LEVAIN` em `parts`, com a quantidade
que a Fx escreve; a farinha e a água que o levain carrega entram na fórmula base pela
composição da versão atual do `creme-levain` (é o que `_dissolve` faz no bootstrap). Por
isso **o levain tem de entrar primeiro**: a composição que a massa herda é a do
`creme-levain` publicado na hora. O `origin` guarda a linha da Fx do jeito que está.

Ambiguidade do bloco: há uma linha só com **subtotal de custo**, sem nome de ingrediente
e sem quantidade, que entra no custo total e não entra na massa total. Ela **não vira
insumo** (não se sabe o que é); fica registrada na nota da versão como "linha de custo
sem ingrediente na Fx".

#### MASSA CAMPAGNE → `massa-campagne` (saída `MASSA-CAMPAGNE`)

| Insumo, como a Fx escreve | SKU no sistema |
|---|---|
| Farinha de Trigo Especial Biorgânica | **sem SKU correspondente** |
| Farinha de Trigo Integral Orgânico Paullinia | `FARINHA-INTEGRAL-ORGANICA` (marca Paullinia no cadastro) |
| Farinha de Centeio Integral Paullinia | `FARINHA-CENTEIO-INTEGRAL-ORGANICA` (marca Paullinia no cadastro) |
| Sal Refinado | `SAL-REFINADO` |
| Água | `AGUA-FILTRADA` (provável) |
| LEVAIN | `LEVAIN` = parte (pré-fermento), `entry_ref: creme-levain` |

#### MASSA CIABATTA → `massa-ciabatta` (saída `MASSA-CIABATTA`)

| Insumo, como a Fx escreve | SKU no sistema |
|---|---|
| Farinha de Trigo Especial Biorgânica | **sem SKU correspondente** |
| Água | `AGUA-FILTRADA` (provável) |
| Sal Refinado | `SAL-REFINADO` |
| Azeito de Oliva EA | `AZEITE-EXTRAVIRGEM` (provável: a Fx e a MP não dizem a marca; o cadastro diz Luglio; "EA" não está explicado) |
| LEVAIN | `LEVAIN` = parte (pré-fermento), `entry_ref: creme-levain` |

### C.4 A farinha que não tem SKU

As quatro receitas usam **Farinha de Trigo Especial Biorgânica**, e o levain usa também a
**Farinha de Trigo Integral Biorgânica**. Nenhum dos cinco cadastros de farinha do
sistema é Biorgânica (`config/management/commands/seed.py`, `SUPPLIER_BY_MATERIAL`):

- `FARINHA-NOVARA-T55` (Novara/Pasini) e `FARINHA-ANACONDA-PREMIUM` (Novara/Pasini,
  alternativa Anaconda);
- `FARINHA-BAGATELLE-T45` (Foricher);
- `FARINHA-INTEGRAL-ORGANICA` e `FARINHA-CENTEIO-INTEGRAL-ORGANICA` (Paullinia).

A MP lista "Farinha de Trigo Especial Biorgânica" e "Farinha de Trigo Integral
Biorgânica" como matérias-primas próprias, separadas das Paullinia, da Anaconda e da Rio
Azul. Nenhum SKU foi criado. Enquanto o dono não disser, as versões das quatro receitas
**ficam em rascunho** (`sku=""` nessas linhas), porque publicar exige todo SKU.

### C.5 Peças por família (só nomes e o vínculo massa → peça)

Pesos fora: a pergunta 5 segue aberta. A ficha de cada peça diz "N g de Massa X" e não
leva fórmula própria (`bootstrap_entry_from_recipe`, "peça não tem fórmula fabricada");
o vínculo é o `RecipeItem` da peça com `input_sku` = a saída da massa.

| Massa | Peças (fonte 1, abas TRAD/CIAB/CAMP) | Ficha de peça que já existe no seed |
|---|---|---|
| **Tradição** (`MASSA-TRADICAO`) | [PH] Pão de Hambúrguer Rústico (resposta 4) · [TB] Tabatière · [FE] Fendu · [MIB] Mini Baguete · [DBP] Baguette Pequena · [DB] Demi Baguete · [BF] Baguete Francesa · [BA] Bâtard · [BL] Boule · [BAX] Batard Grande · [BAXG] Batard XG | BF → `baguete` · BA → `batard` · BAX → `italiano-rustico` (provável) |
| **Ciabatta** (`MASSA-CIABATTA`) | [CI] Ciabatta · Ciabatta Peq (CIP) · [CIQ] Ciabatta Quadrada · [CIM] Mini Ciabatta · [BE] Baguete Gergelim · [BEP] Baguete Gergelim Peq · [BAP] Baguetinha Peq · [FOA] Focaccia Alecrim · [FOC] Focaccia de Cebola Roxa · [CBT] Focaccia de Bacon,C&T · [FOL] Fougasse aux Olives e Lardons · Mini Focaccia (MIF) · Vulcão de Alho (VQA) · [EP] Pain d'Êpi · [MEP] Mini Êpi | CI → `ciabatta` · BEP → `baguete-gergelim-pequena` · BAP → `baguete-lanche` (provável) · FOA → `focaccia-dia` · FOC → `focaccia-cebola-roxa` · CBT → `focaccia-cebola-bacon-tomilho` · MIF → `mini-focaccia-alecrim` (provável) |
| **Campagne** (`MASSA-CAMPAGNE`) | [CGO] Pain de Campagne Oval · [CGR] Pain de Campagne Redondo · [CF] Baguette Campagne · [CFP] Baguette Campagne Peq · [CP] Petit Campagne · Campagne Passas & Cast Peq (CPXP) · [CPX] Campagne Passas & Castanha Grande · Campagne Figos & Amêndoas (CFA) · Mega Campagne · Pão do Croque CW | CGO → `campagne` · CGR → `campagne-redondo` · CF → `baguette-campagne` |

Observações, sem decidir:

- O seed tem duas minis que a fonte 1 não separa: `mini-focaccia-cebola-bacon-tomilho` e
  `mini-focaccia-cebola-roxa`, ambas sobre `MASSA-CIABATTA`. A fonte 1 traz uma linha só,
  "Mini Focaccia".
- As peças com recheio (CPXP, CPX, CFA) levam um recheio cuja composição não está na fonte
  1 nem foi confirmada na Fx (pergunta 6, aberta). O vínculo massa → peça vale; o recheio
  fica de fora.
- Peça da fonte 1 sem ficha no seed continua sem ficha: criar ficha de peça precisa do
  peso (pergunta 5) e, para virar produto, de decisão de catálogo.

### C.6 Divergências entre a Fx e o seed de hoje (só o tipo, sem números)

Comparado com `_seed_recipes` em `config/management/commands/seed.py` (`origin/main`).

**Levain (`creme-levain`)**
- Farinha diferente: o seed usa `FARINHA-NOVARA-T55`; a Fx usa a Especial Biorgânica.
- Insumo a mais na Fx: farinha integral (Integral Biorgânica). O seed não tem integral no
  levain.
- A proporção entre cultura, farinha (somada) e água é a mesma nas duas.
- O rendimento do seed é menor que a soma dos insumos (o seed desconta perda); a Fx
  rende exatamente a soma.

**Massa Tradição (`massa-tradicao`)**
- Estrutura diferente: o seed monta a massa sobre a sub-receita `PASTA-AUTOLIZADA`
  (farinha + água autolisadas, `massa-pasta-autolizada`); a Fx lista farinha e água
  direto, e não diz se há autólise.
- Farinha diferente: no seed, `FARINHA-NOVARA-T55` (dentro da autolizada); na Fx, a
  Especial Biorgânica.
- Insumo a menos na Fx: **malte** (`MALTE-EXTRATO` está no seed, não está na Fx).
- Proporção de água e de levain diferente.

**Massa Campagne (`massa-campagne`)**
- Mesmos tipos de insumo nos dois (três farinhas, água, sal, levain).
- Farinha branca diferente: `FARINHA-NOVARA-T55` no seed; Especial Biorgânica na Fx. As
  duas outras farinhas (integral e centeio Paullinia) batem.
- Proporção entre as três farinhas diferente; proporção de água, de sal e de levain
  diferente.

**Massa Ciabatta (`massa-ciabatta`)**
- Mesmos tipos de insumo nos dois (farinha, água, sal, azeite, levain).
- Farinha diferente: `FARINHA-ANACONDA-PREMIUM` no seed; Especial Biorgânica na Fx.
- Proporção de azeite e de levain diferente; água e sal batem.

**As três massas:** no seed o rendimento é um número redondo, menor que a soma dos
insumos; na Fx o rendimento é a soma exata.

**O que a Fx não toca e continua no seed:** `massa-pasta-autolizada` deixa de ser usada
pela Tradição se a Fx valer como está, mas a ficha continua existindo (decisão de
apagar ou manter é do dono). O seed também ainda usa `FARINHA-NOVARA-T55` em outras
fichas, então nenhum insumo sai do cadastro por causa desta proposta.

### C.7 Plano de entrada no sistema

> ⛔ **Pede o aval escrito do dono antes de executar.** Nada abaixo foi feito.

1. **Resolver a farinha Biorgânica** (C.4): o dono diz se é um insumo novo (aí o cadastro
   de compra nasce pelo caminho normal do Compras, com o SKU que ele aprovar) ou se a
   casa hoje usa outra farinha no lugar. Sem isso, os passos 3 e 4 param em rascunho.
2. **Confirmar as correspondências "provável"**: Água → `AGUA-FILTRADA`; Levain da Fx →
   `LEVAIN-LIQUIDO`; Azeito de Oliva EA → `AZEITE-EXTRAVIRGEM`.
3. **Um comando de importação** (management command, idempotente, com `--apply`; sem
   `--apply` só mostra o que faria), que lê os valores **digitados pelo dono ou exportados
   por ele na hora**, nunca de um arquivo versionado no repositório, e para cada receita:
   - cria uma versão nova (`create_version`) na `RecipeEntry` existente, com
     `source = {"kind": "import", "text": "ANÁLISE_CUSTOS_CVL_2021, aba Fx"}`,
     `origin` = o bloco da Fx como está (kg, grafia da planilha), `formula` em grama,
     `yield_quantity` = a linha Total convertida para grama, `steps` vazio,
     `label` = "Fórmula da Fx";
   - na ordem: **`creme-levain` primeiro**, depois as três massas (que herdam a
     composição do levain pela parte `LEVAIN`);
   - deixa a versão em **rascunho**.
4. **Publicar** (`publish_version`) só depois do aval, receita por receita, na mesma
   ordem. A publicação reescreve a ficha de execução (`Recipe`/`RecipeItem`), e daí em
   diante a fornada, a sugestão de compra e o rótulo de ingredientes passam a ler a Fx.
   A versão anterior fica como "Substituída", consultável e comparável (`diff_versions`).
5. **Seed**: alinhar `_seed_recipes` às versões publicadas é um passo separado, também
   com aval, porque o seed é o que reconstrói o alpha num reseed (e reseed pede a palavra
   do dono).
6. **Etapas**: o dono escreve na tela da receita quando quiser (resposta 2). Nenhuma
   etapa é pré-preenchida.

### C.8 O que a planilha não diz (para estas quatro receitas)

- Etapas, ordem, tempos e temperaturas (resposta 2: o dono edita depois).
- Se a Tradição tem autólise.
- Perda de mistura e perda no forno; quantas peças cada massa rende.
- Massa velha e margem de segurança (só existem na fonte 1).
- Marca do azeite e o que quer dizer "EA".
- O que é a linha de custo sem ingrediente no bloco da Tradição.
- Validade da massa e do levain.

### C.9 Perguntas novas desta seção

13. **Farinha Biorgânica** (Especial e Integral): é insumo que a casa compra hoje? Se
    sim, nasce cadastro de compra próprio; se não, qual farinha a substitui nas quatro
    receitas?
14. As três correspondências "provável" (Água, Levain da Fx, Azeito de Oliva EA) estão
    certas?
15. Com a Fx valendo, a Tradição deixa de usar a Pasta Autolizada e o malte. É isso?

As perguntas 5 a 12 continuam abertas, como estavam.

---

## Perguntas abertas para o dono

1. **Qual versão vale** para Tradição, Campagne e Ciabatta: a da RECEITAS 2.4 ou a da Fx?
   As duas têm farinhas e hidratação diferentes.
2. **Etapas, tempos e temperaturas das massas** não estão em nenhuma das três fontes.
   Existe outro lugar (caderno, foto, outra aba)? Até lá, cada etapa fica "a planilha
   não diz".
3. **Levain:** a RECEITAS 2.4 tem uma aba LEVAIN, fora das autorizadas. Posso lê-la, ou
   vale o bloco LEVAIN da Fx?
4. **Família de massa:** o PH (Pão de Hambúrguer Rústico) é Tradição (como na aba TRAD)
   ou Butter? A Focaccia é a massa da ciabatta (como na aba CIAB) ou uma massa própria?
5. **Peso divergente** entre o nome e a coluna Peso em FOL, EP, MEP, CGR, CPX e BAXG:
   qual é o atual?
6. **Recheios das campagnes** (Passas & Castanha, Figos & Amêndoas): onde está a
   composição? A Fx tem "PASSAS E NOZES"; é o mesmo recheio?
7. **Maysa, Página1 × Ingredientes:** a Página1 é a versão que vale (Torradas,
   Bechamel, Queijo quente divergem)?
8. Fichas marcadas **STAND BY** (Super Hot Dog, Milk Shake) e **PARAMOS AQUI** (Manteiga
   de Wassabi): entram no inventário ou ficam de fora?
9. **Sub-preparos sem ficha** (creme de baunilha com modo de fazer, base de morango,
   gordura de bacon, caldo do frango): existem por escrito?
10. A **composição nutricional** das abas (quebrada na TRAD, com `#DIV/0!` na CIAB) deve
    ser ignorada?
11. Os dois **Recheio de Frango** (Maysa e Fx): qual vale?
12. A RECEITAS 2.4 tem outras abas de massa (KURO, BUTTER, BRIOCHE, FORMA, CROISSANT,
    MASSAS, VIENNOIS e versões antigas). Ficam de fora de propósito, ou posso lê-las numa
    segunda passada?

## Próximo passo

**Espera o aval escrito do dono sobre a seção C** e as respostas às perguntas 13 a 15
(C.9). As perguntas 1 a 4 foram respondidas em 02/10/2026 (HANDOFF §0.1b, PR #1352);
5 a 12 seguem abertas. Nada é executado (comando, versão, publicação, seed) antes
disso.
