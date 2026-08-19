# ADR-024 — Conversão de unidade é cidadã de primeira classe: base única, conversões declaradas

**Status:** **Aceito na direção** (dono, 2026-08-19). Os XMLs de NF-e de entrada que o dono vai mandar **calibram os defaults, não mudam a decisão**.
**Data:** 2026-08-19
**Escopo:** `packages/buyman` (unidade-base do `Material`, tabela de conversões, unidade de compra no custo); `packages/craftsman` (a ficha fala na base; anotação de preparo derivada); `packages/stockman` (o ledger conta na base); `shopman/backstage` (a anotação na tela de mise-en-place/picking); `config/management/commands/seed.py`
**Execução:** [UNIT-CONVERSION-PLAN.md](../plans/UNIT-CONVERSION-PLAN.md) — em fases, **nada implementado ainda**
**Depende de:** [ADR-023](adr-023-cost-live-and-frozen.md) (Aceita, 19/08 — o custo congela); esta ADR decide **em que unidade** ele congela
**Origem:** auditoria do Buyman (2026-08-18), achado B2

> Palavras do dono (19/08/2026): *"o processo de conversão de unidades entre (a) o
> que se compra e o que se conta fácil, do ponto de vista do operador, e (b) o que
> se usa internamente no sistema, deve ser um cidadão de primeiríssima classe no
> Django Shopman. Super simples, super robusto, super elegante! Flexível, mas à
> prova de falhas, sem gambiarra."*

---

## Contexto

`Material.unit` (`packages/buyman/shopman/buyman/models/material.py:28`) servia dois
senhores com pressões opostas, e por isso servia mal aos dois.

**A receita exige igualdade estrita.** `RecipeItem.clean()`
(`packages/craftsman/shopman/craftsman/models/recipe.py:231`) recusa unidade diferente
da do SKU no catálogo — *"a unidade do ingrediente deve coincidir com a unidade do SKU
cadastrado"*. **Não há conversão, por design.**

**O custo é centavo inteiro por essa mesma unidade.** `SupplierMaterialCost.cost_q` é
"custo por unidade do insumo, em centavos" (ADR-002). Unidade fina torna custo
sub-centavo irrepresentável; unidade grossa torna a ficha técnica fracionária.

A saída não é escolher um dos dois senhores: é **parar de fingir que existe uma
unidade só**. A padaria já vive com três vocabulários simultâneos — o que ela
**compra** (saco, caixa, fardo, cartela), o que ela **conta fácil** (ovo, limão,
pacote) e o que ela **mede na verdade** (kg, l, un). O sistema tem de falar os três e
saber, sempre, qual é o que vale.

## Decisão

### 1. Três tipos de conversão — parecem um só e não são

Tratá-los como a mesma coisa é a origem de toda gambiarra de unidade. Cada um tem
natureza, dono e lugar diferentes:

| Tipo | Exemplos | Onde vive | Quem edita | Exata? |
|---|---|---|---|---|
| **1. Exata (definicional)** | kg↔g, l↔ml, dz↔un | **tabela fechada em código** | ninguém | sim, por definição |
| **2. Convencionada (do material)** | saco = 25 kg · caixa = 30 un · fardo = 12 pacotes | banco, por insumo (e, quando muda, por fornecedor) | **o dono, no Admin** | sim, por convenção declarada |
| **3. Aproximada (equivalência física)** | 1 ovo ≈ 50 g · 1 limão ≈ 100 g | banco, por insumo | **o dono, no Admin** | **não** |

- **A exata não é dado do usuário.** Constante de física não é configuração: se
  morasse no banco, alguém poderia salvar "1 kg = 900 g" e o sistema obedeceria em
  silêncio. Fica em código, sem tela, sem migração de dado, sem discussão.
- **A convencionada muda, então é editável.** Saco de farinha vira de 25 kg para
  20 kg quando o moinho quiser; cadastrar embalagem nova não pode exigir deploy.
- **A aproximada é a única que carrega incerteza**, e por isso não pode dividir a
  mesma caixinha com as outras duas. É ela que a regra 3 abaixo persegue.

Sim, a resposta à pergunta do dono é **tabela editável — mas só para os tipos 2 e 3**.

### 2. Quatro regras, e são elas que fazem isto ser robusto em vez de flexível-demais

**R1 · Uma unidade-base por insumo: aquela em que o livro conta.**
A unidade do *momento da verdade* — se o insumo é pesado, `kg`; se é contado, `un`; se
é medido em volume, `l`. **Estoque e dinheiro vivem sempre na base**, e só nela: um
`Quant`, um `Move`, um `cost_q`. Nunca duas unidades para o mesmo insumo no ledger.

**R2 · Todo o resto é conversão PARA a base, declarada por insumo.**
O operador digita o que está na nota ("1 saco, R$ 180,00") ou o que é fácil contar
("2 cartelas"); **a máquina divide**. Jamais o contrário. Conversão é sempre no sentido
*vocabulário humano → base*, calculada em `Decimal`, arredondada só na ponta em que
vira dinheiro guardado.

**R3 · Aproximada nunca vira número silencioso.**
O que atravessou uma equivalência aproximada **carrega o carimbo até a tela**: some o
`≈`, some a informação. Vale para anotação, planejamento, picking e conferência — não
para se dissolver num número que parece exato.

> **O caso real, e ele existe:** compra-se ovo por unidade (cartela de 30) e
> consome-se ovo por peso (300 g na massa). A ponte entre os dois lados é
> necessariamente aproximada. A regra **não** é proibir a ponte — é que ela seja
> **declarada e visível**:
> - se a casa **pesa** no recebimento (a balança está ali), o número exato entra no
>   ledger e a equivalência serve para **conferir** ("30 ovos ≈ 1,5 kg; pesou 1,47 kg");
> - se a casa **não pesa**, a entrada acontece pela ponte e o lançamento nasce
>   carimbado (`approximate=true` + o fator usado no `metadata` do `Move`), o saldo
>   aparece como `≈ 1,5 kg` na tela, e o custo derivado dali é **estimado**, nunca
>   custo congelado sem aviso (ADR-023: incerteza se registra, não se dissolve).
>
> O que fica proibido é a terceira via: converter por baixo do pano e devolver um
> número liso, do qual ninguém mais consegue perguntar "isso foi pesado ou chutado?".

**R4 · Sem fator declarado, o sistema RECUSA — não adivinha.**
Faltou a conversão de "cartela" para `un`? O lançamento **para**, com mensagem dizendo
exatamente o que cadastrar. Nunca "assume 1:1", nunca "chuta 50 g", nunca converte
"na melhor das hipóteses". É a mesma doutrina do NCM ausente no Fiscalman: o dado que
falta grita no gesto, não vira default silencioso três telas adiante.

### 3. Os "dois eixos" deixam de ser caso especial

A versão anterior desta ADR propunha `purchase_unit` + `purchase_factor` no custo. Com
o desenho acima, isso **deixa de ser estrutura especial**: unidade de compra é apenas
uma **linha da tabela de conversões convencionadas** do insumo, e a linha de custo
aponta para a conversão que usou em vez de redeclarar unidade. Um mecanismo, não dois.

Consequência prática: quando a Fase 2 do Buyman modelar `PurchaseOrder`, ela não
inventa eixo nenhum — lê a mesma tabela.

### 4. Requisito de projeto: a anotação de preparo (dono, 19/08)

> *"0.300 de OVOS seria idealmente 300 g de ovos"* … *"é útil, como anotação, qual a
> quantidade aproximada em unidades, para facilitar a vida do operador que vai fazer o
> mise-en-place/picking/pesagem"*.

Isto **é requisito, não detalhe**, e cai exatamente na regra 3:

- **A ficha fala na base:** `0,300 kg` de ovo. É o que entra no BOM, no consumo, no
  custo e no ledger.
- **A tela de preparo mostra a anotação derivada:** `300 g · ≈ 6 ovos`, calculada na
  hora a partir do fator aproximado do material (`MiseEnPlaceLineProjection`,
  `shopman/backstage/projections/production.py`).
- **A anotação nunca é gravada como verdade.** Corrigiu o fator porque o ovo do
  fornecedor novo é jumbo (60 g)? Toda lista de picking se atualiza sozinha, sem tocar
  em ficha nenhuma. Se a anotação fosse persistida, ela seria a quinta cópia de uma
  verdade que já tem dono — e envelheceria calada.

## Invariantes

- Um insumo, uma unidade-base. `Quant`, `Move` e `cost_q` só existem nela.
- Conversão exata não é editável; convencionada e aproximada são, e têm autor.
- Nenhuma conversão é implícita: ou está na tabela fechada, ou está declarada no
  insumo. Não existe conversão "deduzida".
- Número que passou por fator aproximado é rotulado até a tela, e não vira custo
  congelado sem o rótulo.
- Fator ausente **recusa o gesto**; não existe fallback silencioso.

---

## Evidência (medida no repositório em 2026-08-19)

É esta seção que sustenta o desenho acima — em particular, por que a unidade-base
**não pode** ser escolhida para agradar a ficha técnica nem para agradar o custo.

### 0. O que a casa já sabia de custo de compra: nada

- `SupplierMaterialCost` **não tem uma linha sequer** — o seed cria os 23 `Material` e
  **nenhum** `Supplier` nem custo.
- **Não existe ingestão de NF-e de entrada** em lugar nenhum do repositório.
  `uCom`/`qCom`/`vUnCom` aparecem num único arquivo, e é de **saída**:
  `shopman/shop/adapters/fiscal_focusnfe.py` (emissão da NFC-e).

O **denominador** do erro — o preço — não está no repositório. Dá para medir com rigor
a aritmética do arredondamento e as quantidades reais; o resto está em §4.

### 1. A lei do arredondamento (aritmética, não opinião)

Custo em centavo inteiro por unidade erra, no máximo, **meio centavo por unidade**:

> **erro máximo (%) = 50 ÷ (custo em centavos por unidade)**

| Custo por unidade | Erro máximo |
|---|---|
| ≥ R$ 0,50 | ≤ 1% |
| R$ 0,05 | 10% |
| < R$ 0,01 | **sem representação** — com a `CheckConstraint(cost_q > 0)`, não existe valor válido a lançar |

O erro cai a zero só quando o preço calha de dar centavo inteiro por unidade (canela a
R$ 30,00/kg = exatos 3 centavos/g). Sorte, não projeto: muda no próximo reajuste.

### 2. Insumo a insumo, com as receitas reais do seed

23 materiais e 18 receitas, 47 itens de ficha apontando para `Material`. Maior uso por
fornada e erro máximo em reais (quantidade × meio centavo), **se** a base fosse a
unidade fina:

| Insumo | Base fina hipotética | Maior uso por fornada | Erro máx. R$/fornada | Preço p/ erro ≤1% |
|---|---|---|---|---|
| CANELA | `g` | 60 g (recheio-maçã) | R$ 0,30 | **R$ 500,00/kg** |
| ALECRIM | `g` | 30 g (focaccia) | R$ 0,15 | **R$ 500,00/kg** |
| FARINHA-T65 | `kg` | 5,000 kg | R$ 0,025 | R$ 0,50/kg |
| AGUA-FILTRADA | `l` | 4,000 l | R$ 0,020 | R$ 0,50/l |
| MANTEIGA-FR | `kg` | 2,400 kg | R$ 0,012 | R$ 0,50/kg |
| … demais 15 em `kg` | `kg` | ≤ 4,800 kg | ≤ R$ 0,024 | R$ 0,50/kg |

**Os 11% da auditoria se confirmam:** canela a R$ 45,00/kg = 4,5 centavos/g → arredonda
para 4 → **11,1%**. Na faixa de atacado (R$ 30 a R$ 90/kg), o erro **máximo** vai de 17%
a 5,5%. Para cair a 1% com base em `g`, o quilo teria de custar **R$ 500,00**.

**Como o desenho responde:** a base da canela é `kg` — ela é **pesada**, e é isso que a
R1 pergunta. A ergonomia da ficha ("0,060 kg") não é resolvida mudando a base, e sim
pela anotação da §4 do desenho ("60 g"); a precisão do custo não é resolvida mudando a
base, e sim pelo eixo de compra (§3), que é uma linha da tabela de conversões. **A
tentação que produzia os 11% deixa de existir porque a base parou de ter dois donos.**

**A água é o caso extremo, e ele vem do lado grosso:** um litro de água filtrada custa
fração de centavo — nem a base grossa salva. Sob conversão declarada, compra-se o
filtro/m³ e o fator resolve.

### 3. Quais fichas técnicas quebram em cada caminho

- **Base grossa para tudo, sem conversão** (a alternativa descartada): dos 47 itens,
  **27 ficam abaixo de 1 kg** e **6 abaixo de 0,1 kg** — canela 0,060 · alecrim 0,030 ·
  malte 0,020 · sal 0,090 e 0,080 · limão 0,020 — e **13 ocorrências mudam de unidade**.
  A ficha fica ilegível para quem prepara, e é exatamente aí que nasce a gambiarra.
- **Desenho aceito:** a ficha continua na base **e ganha anotação legível na tela de
  preparo**. Nenhuma ficha precisa ser reescrita para caber no custo.

### 4. O que uma NF-e de compra responde (a intuição do dono, e ela é melhor do que parece)

O item de uma NF-e **já traz dois eixos, por obrigação legal**:

- `uCom` · `qCom` · `vUnCom` — unidade **comercial**: como o fornecedor vendeu (SC, CX, FD, PC);
- `uTrib` · `qTrib` · `vUnTrib` — unidade **tributável**: a unidade de referência (KG, L, UN).

Ou seja: o **fator convencionado** é `qTrib ÷ qCom` e o **custo por unidade-base** é o
próprio `vUnTrib`. Uma futura ingestão de XML **preenche a tabela de conversões
sozinha**, sem digitação — a NF-e é, literalmente, a fonte de dado que a regra R2 quer.

**Experimento barato (o dono providencia os arquivos):** 5 a 10 XMLs de NF-e de
**entrada** dos fornecedores reais da Nelson (moinho, laticínio, distribuidor de secos,
hortifrúti), entregues por **arquivo** — dado externo entra por arquivo, é a convenção
da casa. Extrair por item: `xProd`, `NCM`, `uCom`, `qCom`, `vUnCom`, `uTrib`, `qTrib`,
`vUnTrib`. Quatro perguntas que 10 notas fecham:

1. **`uCom` ≠ `uTrib` em que fração dos itens?** Alta → o fator vem de graça da nota.
2. **Quais unidades comerciais aparecem** (SC/CX/FD/PC/KG) → dimensiona o vocabulário
   inicial da tabela, em vez de adivinharmos a lista.
3. **Distribuição de `vUnTrib`** → quantos insumos custam menos de R$ 0,50 por
   unidade-base (onde o centavo inteiro erra > 1%).
4. **O mesmo insumo chega em mais de uma embalagem?** Se sim, a conversão
   convencionada precisa de escopo por fornecedor — e não só por material.

Nenhuma dessas respostas muda a decisão: elas **calibram os defaults** (que unidades
nascem cadastradas, quais fatores já vêm preenchidos, se o escopo é material ou par
material-fornecedor).

---

## Consequências

**Positivas**

- Um mecanismo em vez de três remendos: unidade de compra, embalagem e equivalência
  física passam a ser a mesma tabela, com o mesmo teste e a mesma tela.
- O operador nunca divide: ele copia da nota ou conta o que é fácil contar.
- A ficha técnica para de brigar com o custo — cada um lê a mesma base por um caminho
  declarado.
- O B.I. (ADR-021) e o custo congelado (ADR-023) recebem números com procedência:
  dá para perguntar de qualquer número se ele passou por aproximação.

**Negativas / custos**

- É estrutura nova no Core (tabela de conversões + carimbo de aproximação), não um
  campo. O plano de execução existe para que ela entre em fases, cada uma útil sozinha.
- Fator errado continua sendo erro caro (custo 25× menor); pede validação de
  positividade e alerta de ordem de grandeza na tela.
- Regra R4 (recusar sem fator) **vai** parar lançamentos no começo, enquanto a tabela
  está sendo povoada. É o preço de não ter número inventado no ledger — e a mensagem
  tem de dizer exatamente o que cadastrar.

## Alternativas descartadas

- **Uma tabela só, com tudo editável (inclusive kg↔g)**: mais "flexível" e frágil —
  permite declarar física errada, e o erro fica invisível porque parece configuração
  legítima. A separação em três tipos é justamente o que impede isso.
- **Regra de cadastro "insumo sempre na unidade grossa" (kg/l)**: zero código, e a
  §3 mediu o preço: 27 dos 47 itens abaixo de 1 kg, 13 ocorrências mudando de unidade,
  água ainda sem custo representável, e o operador dividindo no lançamento — o que o
  dono vetou.
- **Guardar custo em milésimos de centavo**: resolve a representação, não resolve
  embalagem nem picking, e rompe ADR-002 sem ganhar nada estrutural.
- **Conversão automática por heurística** ("se está em g e o insumo é kg, divide por
  mil na calada"): é a gambiarra que a R4 proíbe. Conversão sem autor é conversão sem
  responsável.
- **Duas unidades no estoque** (contar ovo em `un` *e* em `kg`): dois números que
  discordam e nenhum dono único — o oposto de ledger-first.

## Referências

- Auditoria do Buyman (2026-08-18), achado B2
- [ADR-023](adr-023-cost-live-and-frozen.md) — o custo congela; esta ADR diz em que unidade
- [ADR-002](adr-002-centavos.md) — dinheiro é inteiro em centavos
- [ADR-021](adr-021-bi-cross-suite-read-layer.md) — o fato tem dono; agregação é leitura
- [UNIT-CONVERSION-PLAN.md](../plans/UNIT-CONVERSION-PLAN.md) — execução em fases
- [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) — Fases 2–4 do Buyman
- `packages/craftsman/shopman/craftsman/models/recipe.py` (`RecipeItem.clean`), `packages/buyman/shopman/buyman/models/cost.py`, `shopman/backstage/projections/production.py`
