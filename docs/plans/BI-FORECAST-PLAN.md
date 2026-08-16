# BI-FORECAST-PLAN — "o que esperar"

> **Status:** 🟢 **RODADA 8 EXECUTADA (2026-08-15)** — a frente mínima
> (F1 dias parecidos + F2 projeção + F4 ramos de clima + F5 seed de dois anos)
> está no worktree, com suíte verde e a tela conferida no navegador. O que saiu
> do papel está no §12; o que ficou, no §12.5.
> Continuação de [BI-INSIGHTS-MAP.md](BI-INSIGHTS-MAP.md) (§1–§13), que fechou o eixo
> *medir → contextualizar*. Esta rodada ataca o pedido original que ficou por último:
> **projetar**.
>
> Pedido do dono, nas palavras dele: *"quero poder ter uma previsibilidade sobre demanda,
> baseada em inteligência de dados. Do tipo: 'o que esperar para a próxima quarta-feira?',
> 'o que esperar para a semana que vem ou mês que vem?', 'o que esperar neste dia das mães
> ou nessa véspera de feriado?', 'o que esperar da primavera este ano?' — projetando e
> comparando com períodos compatíveis anteriores."*
>
> Tudo aqui foi verificado contra o código no worktree (base: `f0e7eb5a`). Onde digo "não
> existe", eu procurei.

---

## 0. A reformulação que torna o pedido construível

O pedido soa como uma coisa só, mas são **duas**, e elas têm custo, risco e honestidade
completamente diferentes:

| | **Comparar** | **Projetar** |
|---|---|---|
| Pergunta | "como foram as quartas parecidas com essa?" | "quanto vou vender na quarta?" |
| Natureza | leitura de fatos | afirmação sobre o futuro |
| Erra? | não pode errar, é história | erra sempre, a questão é o quanto |
| Base hoje | **2 anos de Yooga, já carregados** | 28 dias de pedidos nativos |
| Custo | leitura nova | leitura nova + método declarado |

**Comparar é 80% do valor e 100% da honestidade.** Um gestor que vê "as 14 quartas
parecidas com essa venderam entre 96 e 134 pedidos, mediana 112" já sabe o que esperar,
sem que ninguém precise fingir que adivinha. E consegue discordar do número, porque vê de
onde ele veio.

Projetar é a camada fina por cima: pegar essas mesmas quartas e devolver **um número com
faixa e premissa escrita**. Nunca uma caixa-preta.

**Consequência de projeto:** o trabalho não é construir um modelo. É construir **uma
definição de "dia parecido"** e usá-la em todo lugar. É isso que o resto deste documento
detalha.

---

## 1. O que a casa já tem (verificado, com arquivo)

A descoberta boa desta rodada: **as rodadas 4 a 7 construíram, sem que esse fosse o
objetivo, exatamente os ingredientes da comparabilidade.** Nada disso precisa ser criado.

| Ingrediente | Onde está | O que responde |
|---|---|---|
| Feriado, véspera, volta | `DayContext.day_kind` ([day_context.py:117](../../shopman/backstage/models/day_context.py)) | esse dia era especial no calendário? |
| Temperatura e chuva do dia | `DayContext.temp_*`, `rain_mm` | fazia calor? choveu? |
| **Expediente congelado** | `DayContext.open_minutes/opens_at/closes_at` | a casa abriu, e por quanto tempo? |
| Dia em que a casa não abriu | `closed_days_within` ([production.py:82](../../shopman/shop/services/production.py)) | esse dia não conta |
| **Dia atrapalhado** | `disrupted_days` ([episodes.py:21](../../shopman/shop/adapters/episodes.py)) | faltou luz, não foi procura baixa |
| Dia em que o produto acabou | `StockQueries.shelf_history` ([queries.py:227](../../packages/stockman/shopman/stockman/services/queries.py)) | vendeu 20 porque acabou, não porque a procura era 20 |
| Dia em que não dava para oferecer | `ShelfOutage` + métricas do §11 do mapa | o cliente não encontrava |
| 2 anos de venda com hora, SKU e **categoria** | `HistoricalSale`/`HistoricalSaleItem` | a base longa |
| Eixos cíclicos | `month_of_year`, `week_of_year` no explorador | comparar todos os janeiros |
| Estações declaradas pela casa | `ProductionConfig.suggestion.seasons` ([production_config.py:53](../../shopman/shop/production_config.py)) | quente/ameno/frio, por mês |
| Fórmula explicável | `craft.suggest` + `basis` ([queries.py:120](../../packages/craftsman/shopman/craftsman/services/queries.py)) | quanto assar amanhã, e por quê |

**A lacuna é de composição, não de captura.** Cada peça responde à sua pergunta sozinha, e
**ninguém as junta na frase "estes dias são parecidos com o dia que você perguntou"**.

### 1.1 O que NÃO existe (confirmado procurando)

- **Comparação com período compatível.** O único `previous` que existe é o período de mesmo
  tamanho **imediatamente anterior** ([bi_production.py:172](../../shopman/backstage/projections/bi_production.py)).
  Ele não vê sazonalidade: comparar agosto com julho não responde nada sobre agosto.
  Ano anterior não existe (é a L5 do mapa, nunca feita).
- **Datas comerciais.** O calendário só conhece feriado, véspera e volta. Dia das mães,
  Páscoa, dia dos namorados, Black Friday não existem em lugar nenhum do código.
- **Estação como recorte de leitura.** `seasons` existe só como filtro dentro da fórmula de
  produção; o explorador não tem a dimensão.
- **Categoria como dimensão.** `HistoricalSaleItem.category` é gravado
  ([historical_sale.py:70](../../shopman/backstage/models/historical_sale.py)) e **nunca
  lido** — a métrica de quantidade só oferece SKU.
- **Qualquer previsão.** Está explicitamente fora da v1 ([BI-PLAN.md §8](BI-PLAN.md)).
  Reabrir é decisão do dono, e é o que este documento propõe.
- **Ligação entre SKU do Yooga e do catálogo atual.** Excluída da v1, também nunca feita.

---

## 2. O coração: o que torna dois dias comparáveis

Esta é a decisão de projeto. Tudo o mais decorre dela.

### 2.1 Os critérios, do mais forte ao mais fraco

Para uma padaria, na ordem em que realmente separam um dia de outro:

1. **Dia da semana.** Sábado não é terça. É o critério mais forte e o mais barato.
2. **Tipo de dia no calendário.** Uma sexta que é véspera de feriado não é uma sexta.
3. **Estação / mês do ano.** Julho em Londrina não é janeiro.
4. **Clima.** Um sábado de 32 °C não é um sábado de 16 °C com chuva.

E dois critérios de **exclusão**, que não tornam dias parecidos mas tornam dias
**inutilizáveis** — todos já implementados:

5. **A casa abriu?** Dia fechado não ensina nada.
6. **O dia foi atrapalhado?** Faltou luz não é procura baixa.

E um sétimo, que só vale quando a pergunta é por produto:

7. **O produto acabou naquele dia?** Aí o dia mede o estoque que havia, não a procura que
   houve. A fórmula já sabe extrapolar isso (`soldout_at`, ligado na rodada 3).

### 2.2 A escada de afrouxamento (é aqui que mora a honestidade)

Exigir os quatro critérios de uma vez costuma devolver dois ou três dias. Amostra de três
não sustenta afirmação nenhuma. A saída **não** é ignorar o problema: é afrouxar em ordem
declarada e **dizer o que foi afrouxado**.

```
1. dia da semana + tipo de dia + estação + faixa de temperatura
2. …sem a faixa de temperatura
3. …sem a estação
4. …sem o tipo de dia   (só o dia da semana, na janela inteira)
```

Sobe um degrau só quando a amostra é pequena demais, e a resposta carrega a frase: *"14
quartas-feiras comuns dos últimos 2 anos. Temperatura foi ignorada: só 2 dias batiam com a
faixa."*

Isso é o mesmo padrão do `basis` da fórmula de produção, que já traduz sua base em frases
na tela de plano. Não é invenção: é aplicar a convenção que a casa já tem.

⚠️ **Um degrau que NUNCA se afrouxa:** dia fechado e dia atrapalhado ficam fora em qualquer
nível. Eles não são "menos parecidos", são **inválidos**.

### 2.3 Uma pergunta, um dono

O gancho `untrustworthy_days` ([production.py:66](../../shopman/shop/services/production.py))
já responde "que dias não devem ensinar demanda". Ele é o **caso degenerado** da
comparabilidade: os critérios 5 e 6, sem os critérios 1 a 4.

Se o B.I. criar a própria noção de "dia que conta", as duas telas vão discordar sobre o que
foi a última quarta — e a regra da casa é explícita: mesma pergunta em dois lugares vira
divergência. Então:

> **`untrustworthy_days` passa a ser um método do seletor de dias comparáveis, e a fórmula
> de produção continua chamando o mesmo dono.** Sem duplicar, sem quebrar o que existe.

---

## 3. De dias comparáveis para um número

Escolher os dias é metade. A outra metade é o que se faz com eles, e há duas armadilhas.

### 3.1 Mediana com faixa, nunca média com ponto

Movimento de padaria tem cauda: um dia de encomenda grande puxa a média e não se repete. A
mediana ignora o outlier; a média o incorpora.

E "o que esperar" **é uma faixa por natureza**. A resposta honesta tem três números: o
provável (mediana), e o intervalo entre os quartis (p25–p75), que é onde ficam metade dos
dias parecidos. Um número só finge uma precisão que não existe.

### 3.2 A armadilha do nível: a casa de hoje não é a de 2024

Comparar com a quarta de agosto do ano passado supõe que a casa é a mesma. Ela não é:
mudou de sistema, mudou o cardápio (59 SKUs novos), e cresceu ou encolheu.

Duas saídas, e a escolha é do dono:

**(a) Forma do histórico, nível do presente** *(minha recomendação)*
O histórico longo dá o **peso relativo** — quarta vale 0,82 de um sábado; dezembro vale
1,3 de um agosto; véspera de feriado vale 1,4 de um dia comum. O nativo recente dá o
**patamar** em reais e pedidos. A projeção é `patamar_atual × peso_do_contexto`.
Resistente à troca de sistema e à mudança de cardápio, porque só usa do Yooga o que ele
sabe bem: a forma da curva.

**(b) Nível bruto do histórico, com fator de crescimento declarado**
Mais simples de explicar ("as quartas de agosto passado venderam R$ X, e a casa está 12%
acima"), mais frágil: o fator de crescimento é ele próprio uma estimativa, e ele carrega
junto qualquer distorção da migração.

A **(a)** exige que a tela diga qual é o patamar usado e de quantos dias ele veio. Isso é
uma frase, não um subsistema.

### 3.3 A regra que não se negocia

**Amostra pequena não vira número pequeno; vira ausência.** Abaixo de um mínimo declarado
(proponho 5 dias após o afrouxamento máximo), a resposta é *"não temos dias parecidos o
bastante para dizer"*. A fórmula de produção já faz exatamente isso — `_calc_confidence`
devolve `None` e a receita é pulada. Mesmo comportamento, mesma frase.

---

## 4. Clima: ramo condicional é a fundação, previsão é o enfeite

> **Decisão do dono (2026-08-15):** *"API de tempo (se gratuita), sempre com fallback para
> opção de resposta condicional."*

A ordem importa e é essa: **o ramo condicional é a base, a previsão é uma cortesia por
cima.** Não o contrário.

**A base — sempre calculada, sem depender de nada:** em vez de escolher um clima, mostrar
os dois ramos.

> Quarta-feira, 20 de agosto. 14 quartas parecidas.
> **Se fizer frio (abaixo de 20 °C):** 96 a 118 pedidos, mediana 104. *(8 dias)*
> **Se fizer calor:** 118 a 141, mediana 127. *(6 dias)*

Isso é mais informativo que um palpite já cozido: o padeiro vê **o quanto** o clima pesa, e
olha pela janela de manhã para escolher.

**A cortesia:** quando há previsão, ela **destaca** um dos ramos ("a previsão diz 31 °C") em
vez de substituí-los. Previsão indisponível, lenta ou fora do ar → a tela mostra os dois
ramos e não perde nada. Degradação sem buraco.

Três decisões de projeto que caem disso:

1. **Previsão nunca vira história.** Ela não é gravada no `DayContext`: aquele é o registro
   do que **aconteceu**, alimentado pela medição real via `import_weather` quando o dia
   passa. Um palpite escrito na linha do dia contaminaria toda leitura futura por
   temperatura, e ninguém saberia. A previsão é lida no momento da pergunta, com cache
   curto, e some.
2. **Não é adapter.** A regra da casa exige 2+ implementações reais para justificar um seam
   plugável, e aqui há um provedor só. Serviço simples, ligado por setting, inerte em DEBUG
   como as demais integrações externas. Criar seam sem consumidor é a cicatriz que a casa
   já tem.
3. **Falha rápido e em silêncio.** Timeout curto, erro engolido com log, ramo condicional
   intacto. O B.I. não pode ficar refém de um serviço de terceiro.

⚠️ **"Se gratuita" precisa de verificação, não de memória.** Serviços de clima costumam
separar uso não comercial de uso comercial nos termos, e a Nelson é um negócio. Antes de
escolher o provedor eu confirmo os termos e o limite de requisições, e trago a resposta —
não vou assumir que "tem plano grátis" significa "podemos usar". Se nenhum servir sem
custo, a base condicional entrega o valor sozinha e a decisão pode esperar.

---

## 5. Datas comerciais e estação

### 5.1 "O que esperar neste dia das mães"

Hoje impossível: o calendário só conhece feriado. Dia das mães **não é feriado** e é
provavelmente um dos maiores dias do ano de uma padaria.

**Caminho barato e coerente:** o arquivo de calendário que `import_holidays` já lê ganha uma
coluna de tipo (`feriado` | `comercial`). Duas consequências separadas, porque as perguntas
são diferentes:

- **feriado** pode fechar a loja e gera véspera/volta (já implementado);
- **data comercial** nunca fecha a loja e **não** gera véspera/volta, mas é um valor próprio
  do recorte "tipo de dia".

Móveis (Páscoa, dia das mães, dia dos pais) não precisam de regra de cálculo: entram no
arquivo anual, que já é a forma de carga escolhida. Uma linha por ano, uma vez por ano.

⚠️ **Pergunta para o dono:** quais datas comerciais movem a Nelson? Eu chutaria dia das
mães, Páscoa, Natal, ano novo, dia dos pais, dia dos namorados — mas isso é conhecimento
dele, e chutar aqui seria inventar.

### 5.2 "O que esperar da primavera este ano"

`ProductionConfig.suggestion.seasons` já declara as estações da casa (`hot`/`mild`/`cold`,
por lista de meses). O explorador não as conhece.

Virar dimensão é barato e segue a regra das dimensões de contexto: **se a casa não declarou
estações, a dimensão não aparece.** Reusar a config existente em vez de criar estações
meteorológicas próprias respeita "uma pergunta, um dono" — a casa já disse o que considera
estação, e não cabe ao B.I. discordar.

---

## 6. Por produto: o problema do mapeamento, e o meio-termo barato

Aqui há um degrau real de custo, e ele decide o escopo.

| Nível | Base disponível | Custo |
|---|---|---|
| **Casa** (faturamento, pedidos, ticket) | **2 anos, hoje** | zero |
| **Categoria** (pães, doces, bebidas…) | 2 anos, com mapa de ~10 linhas | **baixo** |
| **SKU** | 28 dias nativos; 2 anos exigem mapa de ~59 linhas | médio (curadoria) |

O nível da casa funciona **hoje**, sem nada: o explorador já funde Shopman e Yooga na mesma
série. É o que responde "o que esperar da semana que vem".

O nível de **categoria** é a descoberta boa: `HistoricalSaleItem.category` já está gravado e
nunca foi lido. Um mapa de categoria antiga → coleção do catálogo atual tem cerca de dez
linhas, é revisável numa sentada, e destrava dois anos de "o que esperar de pães no
inverno". **Melhor relação custo/benefício de todo este documento.**

O nível de **SKU** sobre a série longa exige casar 59 produtos do cardápio 2027 com os nomes
do Yooga, sabendo que ~7% das linhas históricas não têm SKU e que parte do cardápio
simplesmente não existia. É trabalho de curadoria do dono, não de código. **Recomendo
deixar para depois**, porque por SKU a pergunta que mais importa (quanto assar) já é
respondida pela fórmula com dado nativo, que é o dado certo: mede a casa de hoje.

---

## 7. A ponte com a fornada (o que fecha o ciclo)

O mapa (§7) estabeleceu que o eixo do B.I. é o ciclo da fornada: medir →
contextualizar → decidir. As rodadas 3 a 7 entregaram medir e contextualizar. **Decidir já
existe** (`craft.suggest`), e hoje ele decide com:

- 28 dias de janela, mesmo dia da semana → cerca de 4 amostras;
- estação, se configurada;
- multiplicador fixo de sexta/sábado;
- dias fechados e atrapalhados fora;
- extrapolação nos dias que esgotaram.

O que ele **não** sabe: que a quarta que vem é véspera de feriado, e que vai fazer 32 °C.

E existe um encaixe pronto para isso: `FORMULA_FACTOR_PROVIDERS`
([conf.py:49](../../packages/craftsman/shopman/craftsman/conf.py)) está **vazio** e aceita
multiplicador, soma, piso e teto. Foi desenhado exatamente para "está calor" e "é véspera de
feriado" entrarem.

⚠️ **Mas isto é um seam sem consumidor, e a casa tem cicatriz disso** (o `InventoryProtocol`
morto). Ele só deve ser preenchido quando houver um fator **medido** para colocar lá — e a
medição é justamente o que os pacotes deste documento produzem. Ou seja: o provider entra
**depois** que a comparação disser quanto pesa uma véspera de feriado, não antes.

O ganho final é a frase que aparece na tela de plano, ao lado do número sugerido:

> *"Quarta-feira, véspera de feriado. As 6 vésperas parecidas venderam 1,4× uma quarta
> comum."*

Aí o B.I. deixa de ser uma tela que se visita e vira **a explicação do número que o padeiro
já usa todo dia**.

---

## 8. Seed: o que falta para o dono ver isso funcionando

Verificado: `_seed_bi_history` cobre **42 dias**, e é bom no que faz (perfis de prateleira
reconhecíveis, faltas, forno, clima carimbado como `seed`).

Para previsibilidade, 42 dias **não mostram nada**: não há dois anos de quartas para
comparar, não há sazonalidade anual, e não há um único dia das mães.

Três lacunas concretas:

1. **Nenhum feriado é semeado.** `has_calendar` nunca fica verdadeiro, então a dimensão
   "tipo de dia" **não aparece** num banco semeado — a regra do §10.2 do mapa funcionando
   contra a demonstração. Quem roda o seed local não vê a funcionalidade existir.
2. **Nenhuma venda histórica é semeada.** `HistoricalSale` fica vazio; a série longa só
   existe no staging, onde o Yooga real foi carregado.
3. **O clima cobre só os mesmos 42 dias.**

**Proposta:** o seed passa a gerar **dois anos** de venda histórica com estrutura
reconhecível — perfil por dia da semana, sazonalidade por mês, salto em datas comerciais,
queda em dia de chuva, tendência de crescimento leve — mais o calendário de feriados e o
clima do mesmo período.

Duas exigências de honestidade, herdadas do que já se faz com o clima semeado:

- **carimbar a origem** (`source` distinto de `yooga`, `sources` dizendo `seed`), para que
  dado de demonstração jamais se passe por export real;
- **a UI não pode chamar isso de Yooga** — hoje o rótulo da fonte é literal
  ([bi_explore.py:353](../../shopman/backstage/projections/bi_explore.py)); precisa passar a
  derivar do campo.

Custo: usar `HistoricalSale` em vez de `Order` nativo torna dois anos baratos (uma linha por
venda, sem lifecycle, sem estoque) — que é exatamente o que o modelo existe para ser. O
nativo continua cobrindo os 42 dias recentes, com abastecimento. **É o espelho fiel da
realidade: passado longo sem estoque, presente curto com tudo.**

---

## 9. Pacotes, na ordem em que se sustentam

| # | Pacote | Conteúdo | Esforço | O que passa a existir |
|---|---|---|---|---|
| **F1** ⭐ | **Dias parecidos** | O seletor: critérios §2.1, escada §2.2, explicação declarada. `untrustworthy_days` vira caso dele. | dias | A definição que faltava. Nada aparece na tela ainda. |
| **F2** ⭐ | **"O que esperar" da casa** | Dia ou período alvo → mediana + faixa + os dias usados + o que foi afrouxado. Método §3. | dias | Responde "próxima quarta", "semana que vem", "mês que vem" **sobre 2 anos, hoje** |
| **F3** | **Calendário completo** | Datas comerciais no arquivo (§5.1) + estação como dimensão (§5.2) | dias | "Dia das mães", "primavera" |
| **F4** | **Ramos de clima** | A resposta condicional do §4 (fundação) | dias | "Se chover / se fizer calor" — sem dependência externa |
| **F4b** | **Previsão opcional** | Serviço de clima, inerte em DEBUG, destacando um ramo; termos de uso verificados antes | dias | A previsão escolhe o ramo; sem ela, nada quebra |
| **F5** ⭐ | **Seed de dois anos** | §8, com origem carimbada | dias | O dono **vê** F2–F4 localmente e no staging |
| **F6** | **Categoria** | Dimensão nova + mapa categoria↔coleção (~10 linhas) | dias | "O que esperar de pães no inverno", 2 anos de base |
| **F7** | **Ponte com a fornada** | A frase de contexto na tela de plano (§7) | dias | O B.I. explica o número que já é usado |
| **F8** | **Fator na fórmula** | `FORMULA_FACTOR_PROVIDERS` com fatores **medidos** por F2 | dias | A sugestão passa a saber que é véspera de feriado |
| **F9** | **Por SKU na série longa** | Mapa de 59 SKUs (curadoria do dono) | curadoria + dias | "O que esperar de croissant no dia das mães" |

**Ordem sugerida:** F1 → F2 → **F5 junto** (sem seed o dono não vê F2 rodando fora do
staging) → F3 → F4 → F6 → F7. F8 depois que F2 tiver medido os fatores; F9 só se o dono
quiser fazer a curadoria.

**F1+F2+F5 é a frente mínima que entrega o pedido.** O resto amplia.

### 9.1 Onde isso mora na tela

O explorador não expressa esta pergunta: a gramática dele é métrica × dimensão sobre uma
janela, e aqui a pergunta é sobre **um dia ou período futuro**, com dias comparáveis do
passado como resposta. Forçar na gramática existente distorceria as duas.

Recomendo **página própria** no bi-nuxt, com um seletor de data ou período e a resposta em
três blocos: o número com faixa, os dias que a sustentam, e o que foi afrouxado para chegar
lá. O §9.4 do mapa dizia para não criar tela nova sem ver o uso — a ressalva vale para
recortes que o explorador já faz, e não é o caso aqui.

---

## 10. Riscos que eu quero declarados desde já

1. **Previsão erra, e a tela precisa envelhecer bem.** Se o número aparecer sem a faixa e
   sem os dias que o sustentam, ele vira promessa. A casa tem regra explícita sobre nunca
   prometer o que não cumpre.
2. **Duas telas discordando sobre o passado.** É o risco de projeto mais real, e o §2.3 é a
   defesa: um dono só para "que dias contam".
3. **A base longa é de outra casa.** O Yooga é o cardápio antigo, no sistema antigo. Usá-lo
   para **forma** é defensável; para **nível**, é onde a projeção mente primeiro (§3.2).
4. **Sazonalidade com dois anos são duas amostras por mês do ano.** Dizer "o que esperar de
   dezembro" com dois dezembros é frágil, e a tela tem de mostrar que são dois. O afrouxamento
   do §2.2 ajuda, mas não cria dado.
5. **Desempenho.** F2 varre até 2 anos de `HistoricalSale` por pergunta. O gatilho medido da
   ADR-021 §3 (p95 > 2s) segue sendo a régua; materializar antes de medir é o que a ADR
   proíbe. Vale medir no staging, que já tem as 81.255 vendas.

---

## 11. Decisões do dono (2026-08-15)

**Respondidas:**

1. **Horizonte: dia, semana e mês.** Os três, e a **estação ficou de fora** — que é
   coerente com o §10.4: com dois anos de base, "o que esperar da primavera" tem duas
   amostras e seria a afirmação mais frágil da tela. A estação segue valendo como
   **recorte** (dimensão do §5.2), não como horizonte de projeção.
2. **Nível vs forma: forma do histórico, nível do presente** (§3.2, opção a).
3. **Clima: previsão por API se for gratuita, sempre com fallback condicional** (§4) — o
   ramo condicional é a fundação, a previsão destaca um ramo. Termos de uso comercial a
   verificar antes de escolher provedor.
4. **Página própria no B.I.** (§9.1).

5. **Datas comerciais:** Dia das Mães, Páscoa, Natal, Dia dos Pais, Dia dos
   Namorados. Implementadas — ver §12.5.

6. **A casa abre nos domingos de data comercial?** **Não** — o dinheiro acontece
   na véspera (§12.5.1). Nenhuma abertura excepcional a construir.

**Aberta:**

7. **A ocasião deve assumir o destaque** nos dias que têm uma, em vez de aparecer
   abaixo do número genérico? (§12.5.1)

**Encaminhada por recomendação, sem objeção:** paramos em **categoria** (F6); a curadoria
de 59 SKUs (F9) fica para se ele quiser fazê-la.

---

## 12. O que foi executado (2026-08-15)

**F1 + F2 + F4 (base) + F5 no ar.** Suíte inteira verde (4.496), ruff limpo, gate
canônico do Admin limpo, typecheck e vitest do bi-nuxt limpos, e a tela conferida
no navegador com banco semeado.

### 12.1 O motor de comparabilidade (F1)

`backstage/services/day_similarity.py` — a definição de "dia parecido", com a
escada do §2.2 e a distinção entre **afrouxado** e **indisponível** sob teste.
`untrustworthy_days` mudou de casa para cá: a tela de plano e o B.I. passam a ler
a mesma resposta para "que dias contam", que era o risco de projeto nº 2 do §10.

### 12.2 A projeção (F2) e os ramos de clima (F4)

`projections/bi_forecast.py` implementa o método do §3: forma do histórico, nível
do presente, mediana com faixa interquartil, e as três recusas (amostra curta,
sem patamar recente, dia sem venda descartado). Horizonte de dia, semana e mês —
período é a **soma dos dias**, e sem base para um dos dias o total não sai.

Os ramos condicionais já entraram (a fundação do §4). Falta só o F4b, a previsão
que destaca um ramo.

`GET /api/v1/backstage/bi/forecast/` e a página `/forecast` no bi-nuxt.

### 12.3 Dois defeitos que a construção revelou

1. **A regra de fusão "dia nativo vence" estava inline em dois lugares**, e a
   projeção seria o terceiro. Virou dono único (`projections/sales_series.py`),
   com teste que cobra que a projeção e o painel de vendas leem o mesmo dia com
   o mesmo número. Sem isso, duas telas discordariam sobre ontem.
2. **A prestação de contas assustava sem informar.** Perguntando por uma
   quarta, ela dizia "100 dias em que a casa não abriu ficaram fora" — os
   domingos do calendário, que nunca foram candidatos a se parecer com uma
   quarta. Os excluídos passaram a ser contados **só entre os que teriam se
   parecido**.

Junto veio uma correção menor de honestidade: o rótulo da fonte na série de
vendas era o literal `"yooga"` para qualquer histórico. Agora vem do campo, para
que dado semeado se anuncie como `seed` em vez de se passar por um export real.

### 12.4 O seed (F5)

Dois anos de venda em `HistoricalSale` (~11.700 linhas com itens), com perfil por
dia da semana, sazonalidade por mês, salto em véspera de feriado e em data
comercial, queda no calor e na chuva, e tendência de crescimento. Mais o
calendário de feriados (fixos + os móveis da Páscoa) e clima nos mesmos dois
anos.

Duas escalas de propósito, como na vida real: **abastecimento** (prateleira,
faltas, forno) segue nos 42 dias recentes, porque depende do ledger; **venda** vem
dos dois anos, que é o que sustenta sazonalidade. O calendário cobre um ano à
frente, senão não daria para perguntar sobre o feriado que vem.

### 12.5 Datas comerciais (F3, lista do dono: 2026-08-15)

> Dia das Mães, Páscoa, Natal, Dia dos Pais, Dia dos Namorados.

`DayContext.commercial_name`, carregável pelo `import_holidays` com a coluna
`kind` (`feriado` — o padrão — ou `comercial`). Feriado e data comercial coexistem
no mesmo dia porque respondem perguntas diferentes: **o feriado pode fechar a
loja, a data comercial nunca fecha** — ela enche. O Natal é os dois.

Três decisões que o código trava:

1. **Cada data tem identidade própria** (`day_kind = "commercial:dia das mães"`),
   não um balde genérico "data comercial". Perguntar pelo dia das mães tem de
   comparar com dias das mães, não com o dia dos namorados.
2. **Véspera e volta saem da união** de feriados e datas comerciais — o sábado
   antes do dia das mães enche tanto quanto a véspera de um feriado. Os campos
   viraram `is_special_eve`/`is_post_special`.
3. **Bloco "o que este dia fez antes"** na tela. Dois anos dão duas ocorrências,
   e a régua da amostra mínima corretamente se recusa a projetar com duas. Mas há
   resposta honesta disponível numa pergunta diferente: cada ocorrência passada
   medida contra o movimento típico da época dela ("1,4× e 1,5× um dia normal"),
   com o número de ocorrências à vista. Observação, não previsão.

### 12.5.1 A véspera é a ocasião (decisão do dono, 2026-08-15)

> *"O dinheiro acontece nas vésperas (sábado, no caso)!"*

Três das cinco datas caem em domingo (mães, pais, Páscoa) e a Nelson fecha aos
domingos. A resposta do dono resolve: **não há abertura excepcional a construir**
— o movimento dessas datas acontece na véspera.

E isso expôs que eu tinha deixado a véspera pela metade: ela era um booleano, então
o sábado do dia das mães entrava no mesmo balde do sábado antes de Tiradentes —
exatamente o erro que eu tinha evitado para as datas em si.

Corrigido: `DayContext.eve_of` guarda **de qual data** o dia é véspera, e a véspera
ganha identidade própria (`day_kind = "eve:dia das mães"`, rótulo "Dia das Mães
(véspera)"). O bloco "o que este dia fez antes" passa a valer para ela, e **véspera
compara com véspera** — as duas medem a mesma data, em posições que vendem de
formas diferentes.

A volta de data especial segue sendo só um booleano, de propósito: nela o movimento
apenas esvazia, e o motivo não muda decisão nenhuma.

⚠️ **E isso trouxe um problema de hierarquia na tela, que precisou de conserto.**
Com duas ocorrências, a régua da amostra afrouxa o tipo de dia e o número grande
passa a tratar a véspera do dia das mães como um sábado qualquer (R$ 1.267),
enquanto o bloco logo abaixo mostra que ela fez 3,2× e 3,3× um dia normal
(R$ 2.331 no patamar de hoje). Dois números certos, um contradizendo o outro em
silêncio. A tela agora **declara a contradição** quando ela existe: "o número
acima trata este dia como um sábado comum. Ele não é: Dia das Mães (véspera)".

**Resolvido pelo dono: a ocasião assume o destaque.** Nos dias com ocasião ela
lidera, e o número genérico vira o contraponto ao lado ("um sábado comum") —
sem ele, "2,4× um dia normal" não tem escala.

A aba passou a se chamar **Projeção** e foi para o fim da barra: as outras
olham o que aconteceu, e só esta projeta.

### 12.5.2 Os números não batiam, e o motivo eram dois (2026-08-15)

> *"acho que os números não estão nem de longe condizentes… aliás, você teve
> acesso aos dados mais recentes do próprio yooga?"*

**Não tive, e é importante que fique escrito:** o banco local nunca teve uma
linha real do Yooga. As 11.717 vendas eram `source='seed'`, inventadas por mim.
O Yooga real (81.255 pedidos) está carregado **no staging**. A pergunta do dono
achou dois defeitos, um em cada ponta.

**1. O seed errava a ordem de grandeza (~8×).** Eu tinha chutado os pesos:
16 vendas/dia contra ~111 reais, sábado a R$ 1.267 contra R$ 10.478 reais. Um
seed que erra de ordem de grandeza não demonstra a tela — ensina o dono a
desconfiar dela. Agora a **forma** vem do painel real da casa (nenhuma venda
real é copiada), e três coisas que eu tinha errado por intuição aparecem:

- **julho é o pico do ano**, não dezembro (dezembro é um mês comum);
- **janeiro despenca para 31%** do ano, que é quando a casa para;
- **o crescimento está no ticket** (R$ 42 → R$ 66 em dois anos), não no volume,
  que ficou estável. A versão anterior inventava crescimento de volume, e isso
  contradizia o próprio dado.

**2. O patamar do presente media o sistema, não a casa.** Este é o defeito de
código, e ele vale para o staging tanto quanto para o seed: 33 dos últimos 35
dias tinham pedidos nativos de QA (3 a 6 por dia), e a regra "dia nativo vence"
— correta, evita contar a mesma venda duas vezes — descartava as ~130 vendas
históricas **do mesmo dia** em favor de 4 pedidos de teste. O patamar caía para
12% do real, e **toda projeção saía oito vezes menor parecendo certa**.

Corrigido em duas frentes:

- **Guard** (`MIN_LEVEL_SHARE_OF_YEAR`): patamar recente abaixo de 15% do típico
  do ano não vira projeção baixa, vira ausência declarada
  (`patamar_nao_representativo`). A régua é frouxa de propósito para não
  confundir com sazonalidade: janeiro real, a 31%, continua projetando.
- **Seed**: os dias recentes passam a ter volume nativo de verdade, porque um
  seed com dois anos de operação e um presente de quatro pedidos descreve uma
  casa que não existe.

Depois disso o seed bate com o real mês a mês (jun/2026: R$ 205.866 contra
R$ 209.820; ticket R$ 66,84 contra R$ 64,52).

### 12.6 O que fica para a próxima rodada

- **F4b** — a previsão do tempo destacando um ramo, com os termos de uso
  verificados antes de escolher provedor.
- **F6** — categoria como dimensão (o campo já é gravado e o seed já preenche).
- **F7/F8** — a ponte com a tela de plano e o fator na fórmula.
- **Hierarquia da tela** nos dias com ocasião (§12.5.1), se o dono quiser
  invertê-la.

---

## 13. O que este documento deliberadamente NÃO propõe

- **Modelo estatístico ou aprendizado de máquina.** Mediana de dias parecidos, com faixa e
  premissa escrita, é explicável para o padeiro e auditável por quem discorda. Um modelo
  seria mais preciso na média e indefensável no dia em que errasse.
- **Tabela de agregado materializada.** Sem gatilho medido, é o que a ADR-021 §3 proíbe.
- **Previsão de estoque de insumo.** É Buyman, tem dono próprio.
- **Alerta automático ("amanhã vai faltar").** Só depois que a projeção tiver histórico de
  acerto — alertar com número que ninguém conferiu é ensinar a equipe a ignorar alerta.
