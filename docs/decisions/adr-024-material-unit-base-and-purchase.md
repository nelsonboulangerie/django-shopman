# ADR-024 — Unidade do insumo: base para receita e estoque, unidade de compra para custo

**Status:** Proposto (rascunho para decisão do dono, 2026-08-19)
**Data:** 2026-08-19
**Escopo (se aceito):** `packages/buyman` (`Material.unit`, `SupplierMaterialCost` ganha unidade de compra + fator); `shopman/shop` (custo por unidade-base derivado); `config/management/commands/seed.py` (tabela de unidades); Fase 2 do [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) (`PurchaseOrder`)
**Não muda nada hoje:** esta ADR **não** vem com implementação nem com migração. O campo só muda **depois** que o dono responder a pergunta do fim.
**Origem:** auditoria do Buyman (2026-08-18), achado B2
**19/08/2026:** o dono não bateu o martelo e pediu recomendação fundamentada, com uma restrição dura — *"obrigar o operador a fazer contas no lançamento seria terrível"* — e uma intuição: *"será que analisando algumas NFs de compra descobriríamos?"*. As duas viraram as seções **Evidência** e **Recomendação** abaixo. Status segue **Proposto**.
**Depende de:** [ADR-023](adr-023-cost-live-and-frozen.md) (Aceito, 19/08) — o custo congela; falta decidir em que unidade ele é expresso antes de escrever o backend.

---

## Contexto

`Material.unit` (`packages/buyman/shopman/buyman/models/material.py:28`) alimenta
duas mecânicas com pressões opostas, e por isso serve mal às duas.

**1. A receita exige igualdade estrita.** `RecipeItem.clean()`
(`packages/craftsman/shopman/craftsman/models/recipe.py:231`) recusa unidade
diferente da do SKU no catálogo — *"a unidade do ingrediente deve coincidir com a
unidade do SKU cadastrado"*. **Não há conversão, por design.** Insumo em `kg`
obriga toda ficha técnica a falar em kg (0,5 kg, nunca 500 g).

**2. O custo é centavo inteiro por essa mesma unidade.** `SupplierMaterialCost.cost_q`
é "custo por unidade do insumo, em centavos" (ADR-002). Insumo em `g` torna
custos sub-centavo **irrepresentáveis**: canela a R$ 45,00/kg são 4,5
centavos/g — arredonda para 4 ou 5, erro de ~11% multiplicado por cada grama
custeado.

Escolher a unidade fina quebra o custo; escolher a grossa quebra a ergonomia da
ficha técnica. O seed já vive o dilema em silêncio
(`config/management/commands/seed.py`): farinhas, sal e açúcar em `kg` (custo
representável, receita fracionária); **CANELA e ALECRIM em `g`** (receita
ergonômica, custo condenado ao arredondamento).

E o silêncio é literal: o seed cria os `RecipeItem` por `objects.create()`, que
**não chama `clean()`**. Resultado hoje, no banco de desenvolvimento: o `Material`
CANELA está em `g` e o `RecipeItem` de canela está em `kg` com quantidade
`0.060` — as duas unidades já discordam, e nada gritou. O guarda existe; ele só
não é chamado no caminho que popula os dados.

Falta o eixo que o item master clássico tem exatamente para isso: **unidade de
compra + fator de conversão**. Ninguém compra grama de farinha: compra-se saco de
25 kg, e é *nesse* nível que o custo do fornecedor existe no mundo real. A Fase 2
(`PurchaseOrder`/recebimento) vai precisar da unidade de compra de qualquer
forma — a linha do pedido é "3 sacos", não "75 kg". Decidir agora evita migrar
dados de custo duas vezes.

## Decisão proposta

1. **`Material.unit` é a unidade-base**, e só isso: a unidade em que a receita
   escreve e o estoque conta. Uma por insumo, sem conversão, exatamente como
   `RecipeItem.clean()` já exige.
2. **O custo ganha o eixo de compra.** `SupplierMaterialCost` passa a guardar:
   - `purchase_unit` — a unidade em que o fornecedor vende (saco, caixa, kg, l);
   - `purchase_factor` — quantas unidades-base cabem em uma unidade de compra
     (decimal; 1 saco = 25 kg);
   - `cost_q` — centavos **por unidade de compra** (ADR-002 intacto: o que se
     guarda em dinheiro continua inteiro em centavos, e agora é o número que
     está na nota do fornecedor).
3. **Custo por unidade-base é derivado, não guardado**: `cost_q / purchase_factor`
   calculado em `Decimal`, arredondado **só na ponta**, quando vira dinheiro de
   verdade (custo de uma fornada, custo de um produto). Assim a canela a
   R$ 45,00/kg é exata, e o erro de 11% desaparece com o arredondamento
   intermediário que o causava.
4. **A unidade-base do insumo passa a ser escolhida pela receita**, não pelo
   custo — porque o custo deixou de depender dela. Na prática: CANELA e ALECRIM
   podem seguir em `g`, com custo lançado por kg comprado.
5. **A Fase 2 herda o eixo pronto**: a linha do `PurchaseOrder` fala em unidade
   de compra e o recebimento converte para base ao emitir o `Move` de entrada.

## Consequências

**Positivas**

- Os dois senhores param de brigar: receita manda na unidade-base, fornecedor
  manda na unidade de compra.
- O custo passa a ser lançado como está na nota fiscal — menos conta de cabeça
  no cadastro, menos erro de digitação.
- Fase 2 nasce sem migração de custo.

**Negativas / custos**

- Duas colunas novas em `SupplierMaterialCost` e uma migração no Buyman (barato
  hoje: a tabela é master data pequena, pré-go-live).
- O cadastro de custo ganha dois campos — mais fricção na tela de quem digita.
- Fator errado é erro silencioso e caro (custo 25× menor). Pede validação
  (`purchase_factor > 0`) e um alerta de ordem de grandeza na tela.

## Alternativas consideradas

- **Guardar custo em milésimos de centavo** (mudar a granularidade de `cost_q`):
  resolve a representação e não resolve a Fase 2 — continua faltando "saco de
  25 kg" para a linha do pedido de compra. E rompe ADR-002 sem ganhar o eixo.
- **Regra de cadastro "insumo sempre na unidade grossa" (kg/l)**: zero código, e
  era a segunda opção oferecida ao dono. A evidência abaixo mediu o preço dela:
  27 dos 47 itens de receita ficam abaixo de 1 kg (6 deles abaixo de 0,1 kg,
  incluindo canela 0,060 e alecrim 0,030), 13 ocorrências mudam de unidade, a
  água continua sem custo representável, e o operador passa a dividir no
  lançamento — o que o dono vetou. Segue registrada como a alternativa que a
  recomendação descarta.
- **Conversão automática de unidade na receita** (g↔kg): rejeitada por design
  no Craftsman, e não é o problema — o problema é o custo, não a ficha.

## Evidência (medida no repositório em 2026-08-19)

### 0. O que a casa já sabe de custo de compra: nada

Antes de qualquer conta, o inventário honesto do que existe:

- `SupplierMaterialCost` **não tem uma linha sequer** — o seed cria os 23 `Material`
  e **nenhum** `Supplier` nem custo (`grep` em `config/management/commands/seed.py`).
- **Não existe ingestão de NF-e de entrada** em lugar nenhum do repositório.
  `uCom`/`qCom`/`vUnCom` aparecem em um único arquivo, e é de **saída**:
  `shopman/shop/adapters/fiscal_focusnfe.py` (emissão da NFC-e).

Ou seja: o **denominador** do erro — o preço — não está no repositório. O que dá
para medir com rigor é a aritmética do arredondamento e as quantidades reais das
receitas. É o que segue; a parte que só uma nota fiscal responde está em §4.

### 1. A lei do arredondamento (aritmética, não opinião)

Custo em centavo inteiro por unidade erra, no máximo, **meio centavo por unidade**:

> **erro máximo (%) = 50 ÷ (custo em centavos por unidade)**

Daí saem dois limiares duros, que independem de insumo, de fornecedor e de preço:

| Custo por unidade | Erro máximo |
|---|---|
| ≥ R$ 0,50 | ≤ 1% |
| R$ 0,05 | 10% |
| < R$ 0,01 | **sem representação** — com a `CheckConstraint(cost_q > 0)` recém-criada, não existe valor válido a lançar |

O erro cai a zero só quando o preço calha de dar centavo inteiro por unidade
(canela a R$ 30,00/kg = exatos 3 centavos/g). Isso é sorte, não projeto: muda no
próximo reajuste.

### 2. Insumo a insumo, com as receitas reais do seed

23 materiais: **16 em `kg`, 3 em `l`, 2 em `g`, 2 em `un`**. 18 receitas, 47 itens
de receita apontando para `Material`. Maior uso por fornada e erro máximo em reais
(quantidade × meio centavo):

| Insumo | Unidade | Maior uso por fornada | Erro máx. R$/fornada | Custo/unidade p/ erro ≤1% |
|---|---|---|---|---|
| CANELA | `g` | 60 g (recheio-maçã) | R$ 0,30 | **R$ 500,00/kg** |
| ALECRIM | `g` | 30 g (focaccia) | R$ 0,15 | **R$ 500,00/kg** |
| FARINHA-T65 | `kg` | 5,000 kg | R$ 0,025 | R$ 0,50/kg |
| FARINHA-T55 | `kg` | 5,000 kg | R$ 0,025 | R$ 0,50/kg |
| FARINHA-T45 | `kg` | 4,800 kg | R$ 0,024 | R$ 0,50/kg |
| AGUA-FILTRADA | `l` | 4,000 l | R$ 0,020 | R$ 0,50/l |
| MANTEIGA-FR | `kg` | 2,400 kg | R$ 0,012 | R$ 0,50/kg |
| OVOS | `un` | 1,200 | R$ 0,006 | R$ 0,50/un |
| … demais 12 em `kg` | `kg` | ≤ 3,800 kg | ≤ R$ 0,019 | R$ 0,50/kg |
| MALTE | `kg` | 0,020 kg | R$ 0,0001 | R$ 0,50/kg |

Leitura: **em `kg` e `l` o erro é ruído** (farinha a R$ 3,50/kg → 0,14%; nenhum
insumo de padaria custa menos de R$ 0,50 o quilo, então o limiar nunca é cruzado).
**Em `g` o erro é estrutural**, porque para ficar em 1% a canela precisaria custar
**R$ 500,00 o quilo**.

**A estimativa da auditoria se confirma.** Canela a R$ 45,00/kg = 4,5 centavos/g →
arredonda para 4 → **erro de 11,1%**, exatamente o que a auditoria estimou. Na faixa
de atacado (R$ 30 a R$ 90/kg) o erro **máximo** vai de 17% a 5,5%. Em reais é pouco
(até R$ 0,30 por fornada de recheio), mas é 11% do custo *daquele* ingrediente —
e esse percentual entra inteiro na margem do produto que o usa e no B.I. que a
[ADR-023](adr-023-cost-live-and-frozen.md) acabou de mandar congelar.

**A água é o caso extremo, e é do eixo grosso.** Um litro de água filtrada custa
fração de centavo: mesmo com `unit = l` não existe `cost_q` válido (o mínimo é 1
centavo/l, mais que o dobro do real). Sob dois eixos, compra-se o filtro/m³ e o
fator resolve.

### 3. Quais fichas técnicas quebram em cada opção

**Opção B (eixo único, tudo na unidade grossa `kg`/`l`):** dos 47 itens, **6 já
estão abaixo de 0,1 kg** e passariam a ser escritos assim — MALTE 0,020 · SAL 0,090
· SAL 0,080 · **CANELA 0,060** · **ALECRIM 0,030** · LIMÃO 0,020 — mais 21 itens
entre 0,1 e 1 kg. E **13 ocorrências mudariam de unidade** (os itens cujo material
não está em `kg` hoje: água, leite, azeite, ovos, limão, canela, alecrim).

**Opção A (dois eixos):** **nenhuma ficha muda.** A unidade-base continua sendo a
que a receita já usa; o que ganha eixo é a linha de custo.

**De quebra, um erro que já existe:** os `RecipeItem` do seed nascem com o default
`kg` (o seed usa `objects.create()`, que não chama `clean()`), então OVOS `1.200` e
LIMÃO `0.120` — materiais cadastrados em `un` — significam 1,2 **kg** de ovo e 120 **g**
de limão, não 1,2 ovos. Qualquer das duas opções obriga a arrumar isso; a opção A
arruma só o cadastro do material, a B arruma cadastro **e** as 13 linhas de receita.

### 4. Onde o operador faz conta (o critério do dono)

Chegou um saco de farinha de 25 kg por R$ 180,00:

| | O que o operador digita | Quem divide |
|---|---|---|
| **A — dois eixos** | `saco` · `25` · `R$ 180,00` | o sistema (R$ 7,20/kg, em decimal) |
| **B — eixo único (kg)** | `R$ 7,20` | **o operador** (180 ÷ 25, de cabeça) |

Canela, caixa de 1 kg por R$ 45,00, insumo em `g`:

| | O que o operador digita | Resultado |
|---|---|---|
| **A** | `caixa` · `1000` · `R$ 45,00` | sistema deriva 4,5 centavos/g, exato |
| **B com `unit=g`** | precisa de centavos **por grama**: 45,00 ÷ 1000 | não cabe em centavo inteiro; ele digita 4 ou 5 e erra 11% |
| **B com `unit=kg`** | `R$ 45,00` (sem conta) | mas a ficha passa a dizer 0,060 kg de canela |

Os três números da opção A — embalagem, quantidade por embalagem e valor — **estão
todos impressos na nota e na caixa**. Nenhum exige divisão. O fator, além disso, é
propriedade da embalagem: digita-se uma vez por (fornecedor, insumo), não a cada
compra. Pelo critério do dono, **a opção B é a única que obriga o humano a dividir.**

### 5. O que uma NF-e de compra responderia (a intuição do dono, e ela é melhor do que parece)

O item de uma NF-e **já traz os dois eixos, por obrigação legal**:

- `uCom` · `qCom` · `vUnCom` — unidade **comercial**: como o fornecedor vendeu (SC, CX, FD, PC);
- `uTrib` · `qTrib` · `vUnTrib` — unidade **tributável**: a unidade de referência (KG, L, UN).

Isto é, o **fator** é `qTrib ÷ qCom` e o **custo por unidade-base** é o próprio
`vUnTrib`. Sob dois eixos, uma futura ingestão de XML preenche os três campos
**sozinha, sem digitação nenhuma** — o oposto do que o dono teme.

**Experimento barato (o dono providencia os arquivos):** 5 a 10 XMLs de NF-e de
**entrada** dos fornecedores reais da Nelson (moinho, laticínio, distribuidor de
secos, hortifrúti), entregues por **arquivo** — dado externo entra por arquivo, é a
convenção da casa. Extrair por item: `xProd`, `NCM`, `uCom`, `qCom`, `vUnCom`,
`uTrib`, `qTrib`, `vUnTrib`. Quatro perguntas que 10 notas fecham:

1. **`uCom` ≠ `uTrib` em que fração dos itens?** Alta → o eixo de compra é fato da
   nota, não invenção nossa, e o fator vem de graça.
2. **Quais unidades comerciais realmente aparecem** (SC/CX/FD/PC/KG) → dimensiona o
   vocabulário do campo, em vez de adivinharmos a lista.
3. **Distribuição de `vUnTrib`**: quantos itens custam menos de R$ 0,50 por unidade-base
   (erro > 1% no centavo inteiro) e quantos abaixo de R$ 0,05 (> 10%).
4. **O mesmo insumo chega em mais de uma embalagem?** Se sim, o fator pertence à
   linha de custo (por fornecedor) e não ao `Material` — que é o que esta proposta
   já assume.

**O experimento pode derrubar esta ADR**, e é por isso que vale: se (1) der baixo e
(3) mostrar todo mundo acima de R$ 0,50 por unidade-base, o eixo único basta e a
recomendação abaixo muda.

## Recomendação

**Opção A (dois eixos), pelos três motivos que a evidência sustenta:** é a única
que nunca pede divisão ao operador (§4, o critério do dono); é a única em que
nenhuma ficha técnica muda (§3); e é a única que representa canela, alecrim e água
sem erro (§1–2). O custo de adoção é dois campos a mais na tela de custo — campos
que são **cópia** da nota, não conta.

Com a [ADR-023](adr-023-cost-live-and-frozen.md) aceita, a ordem fica: decidir a
unidade → escrever o backend de custo → congelar o custo no `finish`. Nenhuma
linha de custo existe ainda, então **agora é o momento mais barato que vai existir**.

O experimento das notas (§5) não precisa preceder a decisão: ele **confirma** a
opção A ou a derruba, e se derrubar, derruba antes de a primeira linha de custo
ser digitada — nada a migrar de qualquer forma.

## Pergunta ao dono (responda "sim")

> **Seguimos com os dois eixos** — a receita continua na unidade que já usa, e o
> custo passa a ser lançado copiando os três números da nota (embalagem,
> quantidade por embalagem, valor), com o sistema fazendo toda divisão —
> **e você nos manda 5 a 10 XMLs de NF-e de entrada dos seus fornecedores para
> confirmar antes de escrevermos o código?**

## Referências

- Auditoria do Buyman (2026-08-18), achado B2
- [ADR-002](adr-002-centavos.md) — dinheiro é inteiro em centavos
- [ADR-023](adr-023-cost-live-and-frozen.md) — que custo é esse que a unidade expressa
- [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) — Fases 2–4
- `packages/craftsman/shopman/craftsman/models/recipe.py` (`RecipeItem.clean`), `packages/buyman/shopman/buyman/models/cost.py`
