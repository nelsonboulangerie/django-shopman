# Modelagem de receitas de panificação no Shopman — briefing

> Documento de passagem para uma sessão de código que vai modelar o manejo de fichas
> técnicas de panificação. Escrito em 05/09/2026, a partir de uma entrevista com o dono
> (Pablo / Nelson Boulangerie). **Nada aqui está implementado ainda.**

## 1. O modelo do ofício (não invente outro)

Padaria profissional escreve ficha em três camadas — é o padrão da BBGA e do Hamelman, e
é como o dono já pensa:

| Camada | O que é | Quem escreve |
|---|---|---|
| **Receita base** | A fórmula total da massa. Farinha total = 100%. É o que se pesquisa, se publica e se compartilha. | O padeiro |
| **Partes** | Pedaços da base que recebem tratamento antes: levain, pasta autolisada, yudane, poolish, biga, massa velha, bassinage, manteiga de folhagem. | O padeiro, **só a %** |
| **Mistura final** | O que falta pôr na masseira no fim. | **Ninguém — é calculada** |

**Mistura final = receita base − soma das partes.** Nunca digitada. O dono chama isso de
"o pulo do gato", e é a razão de o modelo aguentar variação diária.

### A direção da verdade importa
A base é o **ponto de partida**, não o resultado. Somar as partes para chegar na base serve
**uma vez**, como inventário das fichas que já existem no seed. Depois disso, quem cria uma
receita escreve a base e aponta as partes.

## 2. Convenções fechadas com o dono

- **Todo lote é escrito sobre 1 kg da soma de TODAS as farinhas** (trigo, integral, centeio).
  Com a farinha total normalizada em 1000 g, **grama ÷ 10 = % do padeiro**. Um número, duas
  leituras. Não existem duas unidades para o usuário aprender.
- **Duas bases de % encaixadas**: dentro de uma parte, o 100% é a farinha *daquela parte*;
  o tamanho da parte se declara pela **% da farinha total que está nela** (farinha
  pré-fermentada). **PTM (peso total da massa) não entra na fórmula** — serve para dividir
  em peças.
- **`parte`, nunca `etapa`.** `Recipe.steps` já existe e significa etapa de *processo*
  (Mistura, Fermentação, Modelagem, Forno). Parte = pedaço da fórmula. Dois eixos, dois
  nomes; confundir os dois colide no código e na tela.
- **Fermento biológico (fresco ou seco) NÃO é parte** — é ingrediente, entra direto.
- **A ficha é massa CRUA; o `unit_weight_g` do catálogo é a peça ASSADA.** ~12% de perda de
  forno entre as duas. Ver `feedback_recipe_is_raw_dough_catalog_is_baked` no memory.
- Escalonagem pelo **coeficiente francês**, que já existe
  (`services/execution.py:133`, `coefficient = quantidade / batch_size`) mas é **invisível
  ao padeiro**. O dono pediu que fique transparente: com base de 1 kg de farinha, o fator
  É o lote em kg de farinha.

## 3. O que o código já tem (não reconstrua)

- `Recipe` / `RecipeItem` em `packages/craftsman/shopman/craftsman/models/recipe.py`.
- **BOM multinível já funciona**: `RecipeItem.input_sku` aponta para um SKU; se ele tem
  `Recipe` ativa, `_expand_bom` (`services/queries.py:432`) desce recursivamente até a
  matéria-prima, com trava de ciclo em profundidade 5 (`BOM_CYCLE`).
- `Recipe._validate_mass_balance` já recusa ficha onde a massa rende mais do que pesa.
- `RecipeItem.meta` é `JSONField` — é onde dado contextual mora neste projeto
  (CLAUDE.md: contextual → JSON; **não abrir campo novo no Core sem necessidade provada**).
- `Recipe.steps` é `JSONField(list)` de nomes de etapa.
- O consumo de insumo na conclusão é **derivado da ficha × coeficiente**
  (`execution.py:148`), a menos que venha `consumed` explícito.

## 4. O que FALTA (é isto que precisa ser modelado)

1. **Não existe receita base.** A ficha de hoje lista o que se joga na masseira; a fórmula
   total é implícita. Ninguém lê hidratação, farinha total nem % pré-fermentada.
2. **Não existe "declarar a parte por %".** Hoje se digita kg.
3. **A mistura final não é derivada** — é digitada.

### Onde a % mora
**No vínculo, não na parte.** "Levain 20%" é a relação *daquela massa* com o levain — outra
massa usa 13% do mesmo levain. Logo a % pertence à **linha** (`RecipeItem`), não à
sub-`Recipe`.

## 5. Armadilhas provadas nesta entrevista

### ⚠️ Dupla contagem da farinha
Base-first + parte-como-receita cria risco real: o levain tem ordem de produção própria e
**já dá baixa na farinha dele**. Se a fornada do pão consumir *a base inteira*, a mesma
farinha sai do estoque duas vezes, e a sugestão de compra nasce inflada todo dia,
silenciosamente. Da ficha base-first o sistema tem de derivar **duas coisas diferentes, e
nenhuma delas é a base**:

- **lista de pesagem** (o que o padeiro pesa) = mistura final;
- **BOM de consumo** = mistura final **+ as partes prontas**.

### ⚠️ Nem toda parte deve virar `Recipe`
Dois eixos independentes:

| | compartilhada entre massas? | tem estoque? |
|---|---|---|
| Levain, yudane, poolish, biga | sim | **sim** — existem entre fornadas |
| Pasta autolisada | **sim** | **não** — feita sob demanda, na quantidade exata, zera no dia |
| Bassinage | não | não |

⛔ **A pasta autolisada NÃO precisa de varredura de fim de dia, posição efêmera especial nem
regra de validade.** Eu propus uma e o dono cortou: *"Só vai ser preparada a quantidade que
vai ser consumida. Já zera. Ponto. É sob demanda."* Não construir isso.

### ⚠️ Massa velha é um TETO, não um parâmetro
É a que mais varia — depende do que sobrou. **Massa velha = a própria receita base da
véspera**, então ela substitui uma fatia da *fórmula inteira*: tudo o mais encolhe junto
por `(1 − mv%)`, levain incluído.

A solução acordada, sem nenhum campo novo e sem digitação no chão de fábrica:

> Na ficha: `massa velha: até 20% da farinha total`.
> O sistema usa `mínimo(sobra dentro da validade, teto)`. A pasta autolisada cobre a
> diferença — e como ela é feita sob demanda, isso não custa nada.

**A sobra o sistema já sabe calcular**: a fornada da massa grava `WorkOrderItem.Kind.OUTPUT`
com a quantidade confirmada no finish (lançamento que já trava o fluxo e já é feito), e a
fornada do pão grava `Kind.CONSUMPTION` derivada da ficha. Sobra = produzida − consumida.
⚠️ É **resíduo contábil, não medido** — perda real (massa na bacia, aparas) infla o número.
O que torna isso seguro é o teto + a autolisada ser conta: se o saldo erra, o padeiro usa o
que tem de fato e a autolisada absorve. O número do sistema é sugestão; a bancada é a
verdade; a fórmula fecha dos dois jeitos.

### ⚠️ Regra de método (o dono cortou três propostas minhas)
Antes de propor mecanismo novo, verificar se a operação real da casa já anula o problema.
Linhas de MEMO, coluna espelho e varredura de fim de dia foram todas cortadas com **KISS**.

## 6. Estado dos dados

- Fichas atuais: 90 em `config/management/commands/seed.py` (`recipes_data`, ~linha 2818).
  São **proposta minha de agosto**, nunca passaram pela balança do dono.
- Proposta nova, conferida (11 massas + 51 peças, levain nos rústicos e biológico fresco nos
  macios): artifact **Fichas dos Pães**
  https://claude.ai/code/artifact/b8cd4fc0-c136-47d0-aac2-0a4c912e0e59
- Destino acordado dos dados: **seed** (verdade do repo) **e** banco vivo pela planilha do
  cofre (`import_backup`, upsert, não apaga o QA dele). Nada de `seed --flush`.

## 7. Perguntas em aberto

1. A base vira a verdade guardada (e a mistura final é materializada), ou a base é uma
   **projection** calculada subindo a árvore com `_expand_bom`? A segunda é muito mais
   barata e não mexe em nada que funciona — mas não atende "o padeiro digita 20%".
2. Onde guardar o teto da massa velha: `RecipeItem.meta` da linha, ou `Recipe.meta`?
3. `MASSA-*` como `output_sku` de pré-preparo estocado continua certo para levain e yudane;
   e para a pasta autolisada, que não estoca?
4. Tempos e temperaturas por parte — o dono adiou ("discutiremos em seguida") e depois pediu
   proposta. Onde eles moram: `Recipe.steps` enriquecido, ou estrutura própria?
