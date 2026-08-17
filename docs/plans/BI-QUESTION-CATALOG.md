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
> **Status:** 🟢 **F1, F3 e F4 EXECUTADOS (17/08/2026)** — o dono mandou fazer tudo
> autonomamente. O que saiu do papel está resumido no §8; o resto do catálogo (§4)
> segue como trabalho disponível.
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

3. **Mesa — o conceito não existe, mas cinco das seis perguntas não precisam dele.**
   O que existe é a comanda (`POSTab`): número reusável, sem lugar e sem lotação. O
   dono vetou o vínculo comanda↔mesa com razão (*"a pessoa nem sabe onde vai
   sentar"*), e o veto custa pouco: só "qual mesa rende mais" depende dele. Ocupação,
   ociosidade, giro e "quantas mesas eu deveria ter" saem do modo de consumo do §3.1
   mais um **cadastro de mesas** que ninguém no balcão toca. → §3.2, §5-F4.

**O fio que liga os três:** nenhum deles pede um gesto novo a quem está no balcão.
Pagamento já está gravado; modo de consumo se lê da cesta; ocupação se deriva do modo
de consumo mais um cadastro feito uma vez. O único toque pedido em todo este documento
é a resposta a "teve fila hoje?", **e só nos dias em que o sistema detectar casa
cheia** — que é o padrão de episódios que a casa já usa.

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

**A regra, como fica** — e ela lê **duas coisas** na cesta, não sete:

| Sinal na cesta | Classificação |
|---|---|
| Âncora (bebida preparada, bebida pronta, prato quente, lanche montado) | **local** |
| Âncora **+ item de levar** (pão, varejo) | **local + levar** |
| Sem âncora (pão, varejo, ou doce sozinho) | **levar** |
| `is_delivery` / `fulfillment_type=delivery` | **entrega** — precede tudo |
| Nenhum produto etiquetado | **não classificado** |

O retrato que o estudo produziu com a regra: **~56% levar, ~38% local, ~6%
delivery**, com ticket local (R$ 63) acima do ticket de levar (R$ 53).

### 3.1.1 O dado por SKU é uma escolha entre TRÊS, não um papel entre sete

> Desafio do dono (17/08): *"Só vejo um dado relevante, e seria booleano: é
> âncora local? Sim ou não. Me prove o contrário."*

Ele estava certo em quase tudo, e o desafio expôs um defeito real. O acerto de
contas:

- ❌ **O corte de "compra de estoque" (4+ do mesmo item) era código morto.** Os
  dois ramos finais da regra devolviam `TAKEAWAY`; a variável era calculada e
  nunca mudava um veredito. Pior, a docstring afirmava que "a âncora vence o
  corte" — a âncora não vencia nada, o corte não fazia nada. E o teste que
  provava essa precedência passava por acidente (café nem era item de levar, então
  a variável jamais era ligada). **Removido**, com nota: volta no dia em que
  existir um modo "compra de estoque" para ele decidir.
- ❌ **Sete papéis eram três comportamentos.** Bebida preparada, bebida pronta,
  prato quente e lanche montado eram quatro nomes para o mesmo bit. **Colapsados
  para três leituras.**
- ✅ **Mas o segundo bit sobrevive — e por causa da quarta pergunta do dono.**
  Com só o booleano de âncora, *café + pão francês* e *café + croissant* são a
  mesma cesta: âncora mais não-âncora. Aí só há dois caminhos, ambos errados —
  chamar as duas de "consumiu e levou" (e todo croissant que acompanha um café
  vira pão levado) ou abandonar o modo "consumir no local e levar", que foi
  pedido no mandato original.

### 3.1.2 A contraproposta do booleano — e por que ela vira medição, não debate

> Dono, na sequência: *"ainda acho que dá pra fazer só com o booleano. Se a cesta
> tem só SKU com âncora True, coluna 1; se só tem False, coluna 3; se tem os dois,
> coluna do meio (1 consumo local, 2 misto, 3 levar). Faz sentido ou não?"*

**Faz — e já está implementado.** O esquema dele é este, com a leitura
"acompanha" nunca usada. Etiquetando o croissant como "leva":

| Cesta | Coluna dele | O que a regra devolve |
|---|---|---|
| só café | 1 | `local` |
| café + pão | 2 | `local + levar` |
| só pão | 3 | `levar` |
| café + croissant | 2 | `local + levar` |
| só croissant | 3 | `levar` |

Idêntico. Adotar o booleano **não custa mudança nenhuma**: basta curar com dois
valores e nunca tocar no terceiro.

**Onde as duas divergem:** numa cesta só — âncora + item ambíguo. E o problema
não é o número de colunas (três saídas a partir de um bit está correto), é a
**pergunta da etiqueta**: *"este item é de consumo local?"* não tem resposta
honesta para croissant, pain au chocolat, salgado, doce individual — e numa
boulangerie essa classe é enorme. Ela quebra nos dois sentidos:

- **ambíguo = True** → croissant sozinho vira "consumo local", contrariando o
  próprio estudo (doce sozinho SEM bebida é pra levar);
- **ambíguo = False** → café + croissant vira "misto", enquanto o estudo o trata
  como consumo local — é disso que vêm os ~38%.

O item é ambíguo **sozinho**, e é a bebida que resolve. Esse é o terceiro estado.

**A consequência é medível, não teórica:** com o ambíguo em False, *café +
croissant* — provavelmente o pedido mais comum da casa — sai da coluna 1 e vai
para a 2. O salão esvazia e o misto incha.

**Decisão: não se resolve no debate, resolve-se no F2.** São duas leituras
plausíveis do mesmo dado, produzindo retratos diferentes — exatamente o tipo de
pergunta que a contagem sobre os dois anos responde. Virou a variante 2 do F2.

**As três leituras, cada uma fazendo algo distinto:**

| Leitura | O que faz |
|---|---|
| **Consome aqui** (bebida, prato, lanche) | diz que a pessoa consumiu aqui |
| **Leva** (pão, varejo) | junto de uma âncora, vira "consumiu e levou" |
| **Acompanha** (doce, viennoiserie) | não decide sozinha — mas tira a cesta do balde "sem etiqueta" |

O catálogo segue editável: a casa nomeia como quiser ("café", "salgado assado",
"geleia"), e cada nome escolhe **uma** das três leituras. Nome novo é cadastro;
comportamento novo é teste.

⚠️ **O refinamento "bebida pronta ancora sozinha" mexe no resultado e é mensurável.**
Na formulação original a bebida pronta só ancorava acompanhada de item de consumo
local; agora ancora sozinha. O efeito é deslocar parte do "levar" para o "local", e o
tamanho desse deslocamento sai de uma contagem — vale rodar as duas variantes sobre os
dois anos e ver a diferença antes de congelar (é barato: a regra é função pura).

**O trabalho real é curadoria, não código.** As etiquetas por SKU (bebida preparada,
bebida pronta, prato quente, pão-de-levar, fino individual, varejo/mercearia) são o
esforço; a regra em si é uma função testável.

✅ **Caso aberto do estudo, resolvido pelo dono (17/08): Baguete Lanche e Hambúrguer
100g são PÃES, não lanches.** Etiqueta `pão-de-levar`, **não** ancoram consumo local.
O nome enganava a classificação: "Hambúrguer 100g" é o pão de hambúrguer, não o
sanduíche montado. Sem essa correção a regra leria toda compra de pão de hambúrguer
como alguém almoçando na casa — e o retrato do salão sairia inflado exatamente nos
dias de churrasco, que é quando esse pão vende.

⚠️ **A lição, que vale como guarda:** o nome do SKU não classifica. A etiqueta é
curadoria humana, produto a produto, e a revisão precisa passar por quem conhece o
cardápio — não por quem lê a lista. ✅ O corte de "estoque" (4+ do mesmo item), que
era o outro caso aberto do estudo, **deixou de ser pergunta**: ele não decidia
nada (§3.1.1) e saiu.

**A honestidade que a tela precisa carregar:** a leitura é **inferida**, e diz isso —
com a regra vigente ao alcance de um clique, porque um número que muda quando alguém
reetiqueta um SKU precisa dizer de que regra veio. O que **não** é mais necessário:
separar série medida de série inferida. Não há série medida, e é isso que torna a
leitura coerente de ponta a ponta.

### 3.2 Mesa — valor, ocupação, ociosidade, quantidade ideal

**Estado: 🟡 o conceito não existe, mas a maior parte das perguntas não precisa dele.**

O que existe é a **comanda** (`POSTab`): `ref`, `label`, `is_active`
([`pos.py:9`](../../shopman/backstage/models/pos.py)). Um número reusável — o seed
cadastra 1007 a 1012. Não tem lugar, não tem lotação, não tem mesa.

#### 3.2.1 A objeção do dono, que está certa

> *"O vínculo comanda/mesa é difícil de fazer na hora, a pessoa nem sabe onde vai
> sentar! Por isso sempre evitamos usar em termos de mesa. Se dificultou, tô fora."*

A objeção derruba a proposta que eu tinha feito, e derruba com razão. Amarrar comanda
a mesa **no ato de abrir** exige uma informação que ninguém tem naquele instante. O
resultado previsível seria mesa errada, mesa em branco, ou o operador escolhendo
qualquer uma para o sistema parar de perguntar — e aí a métrica não fica só
incompleta, fica **mentirosa**, que é pior do que não existir.

**Então a recomendação muda: não crie o vínculo comanda↔mesa.**

#### 3.2.2 O que cada pergunta realmente exige

Separando o que você pediu, quase nada precisa saber *em qual* mesa a pessoa sentou:

| Pergunta | Precisa do vínculo? | O que precisa de verdade |
|---|---|---|
| O salão está ocioso? | **não** | quantos grupos sentados ao mesmo tempo, e a capacidade |
| Que dias e horários sobra mesa? | **não** | idem, por faixa |
| Quantas mesas eu deveria ter? | **não** | pico de simultaneidade + faturamento por mesa-hora |
| Quanto tempo o grupo fica? | **não** | duração, calibrada uma vez |
| Quanto rende o salão? | **não** | modo de consumo (§3.1) — já resolvido |
| **Qual mesa** rende mais (a da janela vale mais?) | **sim** | vínculo |

**Uma pergunta em seis.** E é a menos acionável das seis: saber que a mesa da janela
rende mais não muda a decisão de comprar ou tirar mesa, muda no máximo a arrumação —
que você já conhece melhor que qualquer relatório.

#### 3.2.3 O que dá para medir sem pedir nada a ninguém

Com o modo de consumo inferido (§3.1), toda venda de consumo local já é um **grupo que
sentou**. Falta só saber por quanto tempo. Três peças, nenhuma com atrito de operador:

1. **Cadastro de mesas** — uma tela de Admin, preenchida uma vez. É o denominador, e
   é de graça: ninguém no balcão toca nisso.
2. **Duração** — **medida**, não estimada. Ver abaixo.
3. **Simultaneidade** — contar intervalos que se sobrepõem, minuto a minuto.

✅ **Resposta do dono (17/08): "sempre abrimos comanda. Ponto."** Isso elimina a única
suposição que restava no plano inteiro. Toda venda passa por comanda, então a
permanência sai de `Session.opened_at` → `committed_at` — **colunas duráveis, medidas,
por venda**. Não há duração calibrada, não há três cenários de sensibilidade, não há
observação manual de sábado para conferir. O F4 passa a ser leitura pura de dado
existente.

Três consequências que valem registrar:

- **A janela é a comanda, não uma suposição.** Abre quando a pessoa pede, fecha quando
  paga. É mais larga que o tempo sentado (inclui o pedido em pé no balcão) e a tela
  deve chamá-la pelo nome — *"tempo de comanda aberta"* — em vez de vender como tempo
  de permanência. Nomear certo é mais barato que corrigir depois.
- **Comanda de quem leva também abre.** Ela dura um minuto e some sozinha da conta:
  quem filtra a ocupação é o modo de consumo (§3.1), não a existência da comanda.
- ⚠️ **O código tem um caminho de venda direta** (`direct_checkout` em
  `shopman/shop/services/pos.py:247`), que fecha sem comanda. A prática da casa é não
  usá-lo, mas a leitura deve **declarar a fração** que passou por ele em vez de supor
  zero — se um dia subir, o número avisa sozinho, em vez de a métrica emagrecer calada.

#### 3.2.4 O salão real (informado pelo dono, 17/08)

| Espaço | Quantidade | Lugares | Conta? |
|---|---|---|---|
| Mesas internas | 4 | ~2 cada | **sim** |
| Assentos de balcão | 6 | 6 | **sim** |
| Mesas externas | 4 | ~2 cada | **sim** |
| Mesinhas altas (bistrô, em pé) | 2 | ~2 cada | não |
| Bancão externo comprido | 1 | ~4 em dia cheio | não |

**Capacidade oficial: 8 mesas + 6 lugares de balcão.** Fora da conta ficam o bistrô e
o bancão externo — e, dentro das mesas internas, o fato de que o sofá permite apertar
mais gente com menos conforto.

⚠️ **Isso é o achado mais importante desta seção, e muda como a métrica deve ser
apresentada.** Se o próprio denominador é elástico — a casa comporta mais do que os
números oficiais dizem —, então **um numerador preciso é falsa precisão**. Publicar
"ocupação de 73,4%" sobre uma capacidade que na prática estica seria inventar exatidão
onde ela não existe.

A leitura correta, então, não é uma porcentagem fina, é:

- **"bateu no teto oficial"** como **evento contado**, não como taxa: quantas vezes,
  em que faixas, em que dias. Bater no teto é o sinal de que a capacidade elástica
  entrou em uso — e é exatamente o momento que interessa.
- **ociosidade em faixas grossas** (vazio / meio / cheio / no teto), não em decimais.
- **por mesa, não por lugar** (decisão do dono): mesa ocupada é mesa ocupada,
  independentemente de quantas pessoas sentaram.

#### 3.2.5 O que passa a ser mensurável

| Métrica | Como se calcula | Responde |
|---|---|---|
| **Grupos simultâneos** | intervalos sobrepostos de consumo local | "quão cheio esteve?" |
| **Ociosidade por faixa** | faixa grossa por hora × dia-da-semana | "que dias e horários sobra mesa?" |
| **Vezes no teto** | contagem de períodos com 8 mesas ocupadas | ⭐ "falta mesa?" |
| **Faturamento por mesa-hora** | faturamento local ÷ (8 × horas abertas) | ⭐ "quantas mesas?" |
| **Giro** | grupos locais ÷ mesas ÷ dia | "a mesa roda?" |
| **Tempo de comanda aberta** | `opened_at` → `committed_at`, medido | "quanto tempo ficam?" |

O denominador de tempo **já existe**: `DayContext.open_minutes`, carimbado na rodada 6
para que métricas de tempo não fossem lidas pelo horário de hoje. Ocupação herda a
mesma garantia — **dia sem carimbo não entra na conta**, em vez de inventar expediente.

**Sobre "a quantidade ideal de mesas":** o número não sai de uma conta, sai de duas
leituras. O **pico** diz se falta (teto raramente atingido = mesa a mais é espaço
morto; teto todo sábado às 10h = mesa a mais é dinheiro). O **faturamento por
mesa-hora** diz até onde compensa: acrescentar mesa vale enquanto ele não cair.

⚠️ **O que nenhuma delas vê: quem chegou, olhou, não achou lugar e foi embora.** É a
demanda reprimida do salão — o mesmo problema do pão que esgota (§7.1 do INSIGHTS-MAP:
"o sistema aprende a demanda truncada"). A saída é a que a casa já usa para episódios:
o sistema detecta **casa cheia sustentada**, e no fechamento oferece a pergunta com
opções — "teve fila? teve gente que desistiu?". Sinal automático, motivo em um toque,
só nos dias em que houve sinal.

#### 3.2.6 Se um dia o vínculo fizer sentido

Ele não fica impossível — fica **opcional e posterior**. E o momento natural para ele
nunca foi a abertura da comanda: é a **entrega na mesa**, quando quem leva o pedido já
sabe onde a pessoa sentou. Se algum dia essa pergunta importar, o gesto existe ali,
sem atrito. Nada neste plano depende disso.

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
| M1 | Quão cheio esteve o salão, por dia e faixa horária? | 🟡 | §3.2 — deriva de V2 + cadastro |
| M2 | Que dias e horários o salão fica **ocioso**? | 🟡 | §3.2 |
| M3 | Qual o **faturamento por mesa-hora**? | 🟡 | §3.2 — a métrica que responde "quantas mesas" |
| M4 | Qual mesa rende mais (a posição importa)? | ⛔ | **fora** — única que exigia o vínculo vetado (§3.2.1) |
| M5 | Quanto tempo a comanda fica aberta, e isso mudou? | 🟡 | **medido** — a casa sempre abre comanda |
| M6 | Quantas vezes o salão **bateu no teto**? | 🟡 | §3.2 — a leitura principal, no lugar da % |
| M7 | Teve gente que **desistiu por falta de mesa**? | 🔴 | episódio no fechamento — o único toque pedido |
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

✅ **Os dois comandos existem** (17/08). Rodam onde o histórico está carregado —
hoje, só o staging:

```bash
python manage.py propose_consumption_tags --dry-run   # e sem --dry-run para gravar
python manage.py bi_calibrate
```

O `bi_calibrate` **imprime e não grava nada** — é medição, não migração. Aceita
`--from`/`--to` e `--role REF=LEITURA` para variantes extras (ex.:
`--role bebida-pronta=neutral`).

1. Distribuição real de `HistoricalSale.payment` — dimensiona a whitelist de F1.
2. **As variantes da regra**, sobre os dois anos — quanto muda o retrato? É o que
   congela o F3 com número em vez de opinião. São duas, independentes:
   a. bebida pronta ancorando **sozinha** × só acompanhada;
   b. classe ambígua (croissant, doce, salgado) como **"acompanha"** × como
      **"leva"** — a contraproposta do booleano (§3.1.2). Se a diferença for
      pequena, o booleano vence por ser mais barato de curar; se o "misto" engolir
      o salão, a terceira leitura se pagou.
⚠️ **`table_label` saiu do F2** (17/08). Eu tinha proposto usá-lo como "teste de
aderência" da inferência, e isso contradiz a decisão que o próprio dono tomou: se
mesa/balcão do Yooga não eram preenchidos com disciplina, discordância entre o
campo e a regra **não diz quem errou**. É um número que não se pode interpretar,
e um número assim é pior que nenhum.

⚠️ **A ordem do F2 estava errada.** A contagem 2 (as variantes da regra)
**depende das etiquetas existirem** — sem elas tudo sai não classificado e não há
o que comparar. A contagem 1 roda a qualquer momento. Sequência real:
**curadoria → variantes → congelar o parâmetro**.

### F3 — Modo de consumo, inferido ⭐

- **Etiquetas por SKU** — o trabalho de verdade, e ele é uma escolha entre TRÊS
  por produto (§3.1.1): consome aqui · leva · acompanha. Cadastro editável no
  Admin, como os defeitos de qualidade já são.
- ✅ **`propose_consumption_tags`** troca *decidir do zero* por *conferir uma
  lista*: propõe a partir da coleção do catálogo (e, com
  `--include-historical`, da categoria do histórico). ⚠️ **Proposta não é
  curadoria** — tudo entra com `reviewed=False`, e o Admin filtra por
  "revisada = não". O que o mapa não alcança (coleção "Balcão", que agrupa por
  ONDE vende; produto em coleções que discordam) sai **listado**, nunca chutado.
- **A regra como função pura e testável**, aplicada igual ao `OrderItem` nativo e ao
  `HistoricalSaleItem`. Uma implementação, dois consumidores — nunca duas cópias que
  divergem.
- **Dimensão "Modo de consumo"**: `local`, `local + levar`, `levar`, `entrega`,
  aplicável às famílias de vendas e itens (e portanto cruzável com hora, dia,
  contexto do dia, forma de pagamento de F1).
- **Rotulada como inferida na tela**, com a regra vigente ao alcance de um clique.
- ✅ Casos abertos do estudo, decididos: Baguete Lanche e Hambúrguer 100g são
  pães; o corte de "estoque" saiu por não decidir nada.
- ⚠️ SKU sem etiqueta não pode virar "levar" por omissão — vira **não classificado**,
  declarado. Etiqueta faltando é ausência de dado, não um veredito.

**Independe de F4.** Não depende de mesa, de comanda, nem de ritual de equipe.

### F4 — Salão: ocupação, giro, valor *(sem vínculo comanda↔mesa)*

Revisto em 17/08 depois da objeção do dono (§3.2.1). **Não entra vínculo
comanda↔mesa** — nenhum gesto novo é pedido ao balcão.

- **Cadastro de mesas** no Admin, preenchido uma vez: 4 internas + 4 externas + 6
  lugares de balcão, com os espaços elásticos (bistrô, bancão) registrados como
  **fora da capacidade oficial**, porque é assim que a casa os trata.
- **Simultaneidade por intervalos medidos**: `Session.opened_at` → `committed_at`,
  filtrados pelas vendas que o F3 classificou como consumo local. Sem suposição de
  duração — a casa sempre abre comanda.
- **Cobertura declarada:** a fração de vendas que fechou por `direct_checkout` (sem
  comanda) aparece na tela. Hoje é ~zero por prática da casa; se subir, o número
  avisa.
- **Apresentação em faixas grossas + "vezes no teto"**, nunca porcentagem com
  decimal: a capacidade real estica, e numerador preciso sobre denominador elástico é
  falsa precisão (§3.2.4).
- **Ociosidade por mesa, não por lugar** (decisão do dono).
- Sinal de **casa cheia sustentada** → pergunta com opções no fechamento, no catálogo
  de episódios que já existe.

**Depende do F3** (é dele que vem "esta venda foi consumo local"). Não depende de mais
nada.

### F5 — Catálogo, conforme apetite

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
4. **A janela medida é a comanda, não o tempo sentado.** Ela abre no pedido e fecha no
   pagamento, então inclui o tempo em pé no balcão. A tela chama pelo nome — "tempo de
   comanda aberta" — em vez de prometer permanência. **Nada do core é tocado no F4**:
   o cadastro de mesas mora no backstage e a leitura é derivada.
5. **`table_label` do Yooga não vira verdade de canal** — nem depois de F2. Se a
   contagem mostrar boa cobertura, ele serve para **medir o erro** da inferência, e é
   assim que deve aparecer.
6. **Modo de consumo inferido não vale para decisão operacional.** É leitura de
   gestão: mix, ticket, cesta, tendência. Nada de fila, cozinha ou fiscal deve passar
   a depender dele — inferência é boa para entender o negócio e ruim para mandar em
   alguém.

---

## 7. Perguntas ao dono

1. ✅ **Respondidas em 17/08, as duas.** O vínculo comanda↔mesa sai do plano (não vale
   o atrito), e **a casa sempre abre comanda** — então a permanência é medida, não
   calibrada. O F4 não tem mais nenhuma suposição e nenhuma pergunta aberta.
2. ✅ **Respondida em 17/08** (§3.2.4): 4 mesas internas + 4 externas + 6 lugares de
   balcão como capacidade oficial; bistrô e bancão externo ficam fora da conta, e o
   sofá permite apertar. Fica só o detalhe de durabilidade: o cadastro guarda **desde
   quando** cada mesa existe, para que mesa acrescentada em março não reescreva a
   ocupação de janeiro.
3. ✅ **Respondida em 17/08: por mesa.** Mesa ocupada é mesa ocupada, sem perguntar
   quantas pessoas sentaram — o que também elimina o único tap que ainda restava.
4. **Entrega própria e iFood entram no mesmo balde "entregas"?** Custo e margem são
   muito diferentes; a leitura pode ser uma ou duas.
5. **F1 já?** É pequena, independente, e vale sobre dois anos desde o primeiro dia.
   Meu voto é sim, antes de qualquer coisa deste documento.
6. **Bebida pronta ancora sozinha — confirmar depois de ver o número.** A formulação
   original do estudo pedia bebida pronta *acompanhada*; a sua frase de 17/08 a torna
   âncora por si. Concordo com o raciocínio (levar bebida é desprezível aqui), e
   proponho só congelar depois do F2-2, que mostra de quanto é o deslocamento.


---

## 8. O que foi executado (17/08/2026)

Três frentes, na ordem do §5. Suíte do backstage verde, bi-nuxt com 29 testes e
typecheck limpo.

### 8.1 F1 — forma de pagamento

Três métricas novas (**recebido**, **pedidos** e **a receber na entrega**) e a
dimensão **forma de pagamento**, cruzáveis com hora, canal, fonte e contexto do
dia. A leitura passou a ser do **pedido**, não do fechamento: existe todo dia,
inclusive nos sem fechamento feito, que era o limite do painel de caixa.

A regra de repartição saiu de dentro de `services/closing.py` para
`services/payments.py`. Era o único lugar que sabia ler `order.data.payment`, e o
B.I. teria de reimplementá-la — duas implementações divergiriam no primeiro caso
de borda. Um teste cobra que as duas telas contam o mesmo dinheiro.

Duas honestidades sob teste: cobrança na entrega ainda não recebida **sai do
recebido** e tem métrica própria (dinheiro na rua não é caixa, mas também não
some); e a forma crua do histórico que o vocabulário não conhece **preserva o
texto original** em vez de cair num balde "(outros)" — uma forma que a casa usava
e eu não previ tem de aparecer.

### 8.2 F3 — modo de consumo inferido

Dimensão **modo de consumo** (`local`, `local + levar`, `levar`, `entrega`) nas
métricas de venda e de itens. A mesma função classifica o `OrderItem` nativo e o
`HistoricalSaleItem` — é isso que torna os dois anos comparáveis com o presente.

As etiquetas por produto são catálogo editável no Admin, com o comportamento em
campo (`anchors_dine_in`, `travels`) e não em código, como os defeitos de
qualidade. O seed traz o **vocabulário**; etiquetar produto a produto é curadoria
do gestor.

✅ **Baguete Lanche e Hambúrguer 100g entraram como `pão-de-levar`**, com teste
próprio: o nome engana, e sem isso o salão apareceria cheio nos dias de churrasco.

Três decisões travadas por teste: produto sem etiqueta **não vira "levar" por
omissão** (a venda se declara não classificada); **a âncora vence o corte de
estoque** (quatro cafés são uma mesa de quatro, não uma despensa — o corte de 4+
só olha item de levar); e **"consumiu e levou" sai da composição da cesta**.

⚠️ **Um parâmetro segue aberto** (§3.1): bebida pronta ancorando sozinha desloca
parte do "levar" para o "local". Está implementado assim, conforme a sua frase, e
o tamanho do deslocamento sai da contagem do F2.

### 8.3 F4 — o salão

Cadastro de lugares (`SeatingSpot`) e seis métricas, **sem vínculo comanda↔mesa**:
tempo por lotação, pico de grupos, tempo no teto, faturamento por lugar-hora,
giro e tempo de comanda aberta.

O seed traz o salão real: 4 mesas internas + 4 externas + 6 lugares de balcão na
capacidade oficial; bistrô e bancão externo cadastrados **fora da conta**, porque
contá-los esconderia o momento em que a casa bateu no teto.

A lotação sai em **faixa grossa** (vazio / até a metade / cheio / no teto), nunca
em porcentagem com decimal: a capacidade oficial não é limite duro, e numerador
preciso sobre denominador elástico é falsa precisão.

Quatro coisas que o código trava: só quem consumiu aqui ocupa lugar (comanda de
quem levou some sozinha da conta); **dia sem expediente carimbado não vira
linha**; tempo fora do expediente não custa mesa; e mesa cadastrada depois **não
reescreve o passado** (`active_from`).

### 8.4 O que NÃO foi feito, e por quê

- **Rodar o F2** — os comandos existem (§5-F2); falta executá-los no staging, que
  é onde o Yooga está carregado.
- **Curadoria das etiquetas produto a produto** — é decisão de negócio, não
  trabalho de código. O `propose_consumption_tags` reduz isso a conferir uma
  lista, mas quem confere é gente: o nome engana.
- **"Qual mesa rende mais"** — saiu do catálogo (⛔ M4): era a única pergunta que
  exigia o vínculo vetado.
- **M7/M8 (desistiu por falta de mesa; salão × fila do balcão)** — o sinal de
  casa cheia sustentada existe agora (`room_full_minutes`); ligá-lo ao episódio de
  fechamento é o passo seguinte natural.
