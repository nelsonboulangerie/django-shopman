# SKU-REAL-PLAN — o catálogo passa a usar os códigos que a casa usa

> **Mandato (18/08/2026):** *"quem esteve errado esse tempo todo foram os SKUs
> do nosso seed. Yooga estava certo. Ponto. O que divergir, resolvemos."*
>
> Os identificadores do cardápio 2027 (`CROISSANT`, `ESPRESSO`, `PAO-FRANCES`)
> nasceram de geração automática. Os códigos da casa são os do Yooga — `CT`,
> `MD`, `PC`, `CI` —, usados por dois anos em 353.009 linhas de venda.
>
> **Estamos em pré-alpha: muda no banco, atualiza o seed, pronto.** Sem apelido,
> sem `legacy_sku`, sem tabela de tradução — a casa ainda não vendeu nada pelo
> Shopman, e a regra pré-go-live é zerar o nome antigo (CLAUDE.md). As duas
> versões anteriores deste plano propuseram alias e tradução; ambas estão mortas.

---

## 1. O mecanismo já existia — e estava com um furo

**SKU já é uma ref.** `offerman/apps.py` registra o `RefType(slug="SKU")` desde
sempre, `Product.sku` já é `RefField(ref_type="SKU")`, e `RefBulk.cascade_rename`
já traz transação, `select_for_update` e auditoria. Não havia decisão de
mecanismo a tomar; havia um registro pela metade.

**O furo:** 10 dos 18 campos que guardam SKU eram `models.CharField` comum.
O `RefSourceRegistry` só enxerga `RefField`, então o cascade passava por eles sem
tocar — silenciosamente. O rename "funcionava", devolvia um número, e deixava
linha órfã apontando para produto que não existe mais.

**Feito (18/08):** os 10 viraram `RefField(ref_type="SKU")`. O cascade agora
alcança **17 campos** — catálogo, estoque, lote, alerta, hold, receita, fornada,
pedido, comanda, favorito, etiqueta de consumo, falta de prateleira, espelho de
canal. Conversão de `CharField` para `RefField` **não gera migração**: o
`deconstruct` se disfarça de `CharField` de propósito.

Fica **um** campo de fora, de propósito: `backstage.HistoricalSaleItem.sku`. É o
export do Yooga, registro de terceiro — e, no sentido desta troca, ele já está do
lado certo desde sempre. A decisão está escrita e testada
([test_sku_cascade_coverage.py](../../shopman/shop/tests/test_sku_cascade_coverage.py)),
nos dois sentidos: nem campo novo nasce órfão, nem alguém "conserta" a omissão do
histórico.

### 1.1 O defeito que apareceu no caminho

`RefField` tinha default `db_index=True`, e ele **não sobrevivia ao round-trip**.
`deconstruct()` se disfarça de `CharField`, que omite `db_index` quando é `False`
(o default do Django); `Field.clone()` — que o `makemigrations` usa para montar o
estado — reconstrói pelo `__init__`, onde o `setdefault` reaplicava `True`.
Resultado: campo declarado `db_index=False` voltava `True`, e o `makemigrations`
escrevia índice que ninguém pediu.

Não era teórico. Nove campos afetados, cinco anteriores a este plano —
`Product.sku`, `SessionItem.sku`, `Customer.ref`, `Channel.ref`,
`RecipeItem.input_sku` —, e quatro deles são `unique=True`, ou seja, ganharam
índice **duplicado** sobre uma coluna que o Postgres já indexava.

O default saiu. Seis migrações **removem** os índices espúrios. O teste que
fixava o default virou teste que fixa a propriedade real: o campo tem de
round-tripar.

---

## 2. O que falta: o mapa — e ele não é um-para-um

Aqui está a divergência a resolver, e ela é maior do que "trocar o código".

Dos 143 SKUs reais do Yooga, 56 têm correspondência com o cardápio 2027 —
mas apontam para apenas **27 produtos**. **Os códigos do Yooga não são um por
produto: são um por linha de venda.** Três coisas diferentes moram no mesmo
espaço de nomes:

| Natureza | Exemplo | Onde isso mora no Shopman |
|---|---|---|
| **Produto** | `CT` Croissant Tradicional | `Product.sku` — é isto que queremos |
| **Preço** | `MCT` Croissant Tradicional *METADE DO PREÇO* | modifier/promoção, **nunca** um SKU |
| **Canal** | `IFOOD_7a2d…` Croissant Tradicional | `CatalogSyncState`, **nunca** um SKU |

Então "adotar os códigos do Yooga" não é possível ao pé da letra: cerca de um
terço deles não é produto. O que dá para adotar é o **código-base** de cada
produto real (`CT`, `MD`, `PC`, `CI`, `TB`, `FE`…) — e isso o Shopman já modela
melhor do que o sistema antigo modelava.

### 2.1 Granularidade — decidido (18/08)

O dono confirmou: **variante com recheio ou preparo próprio é produto**, e volume
baixo não desqualifica.

| Produto 2027 | Vira | Códigos |
|---|---|---|
| `CROISSANT` | **3** | `CT` tradicional · `CM` mini · `CPQ` presunto e queijo |
| `ANIMALZINHO` | **3** | `ANC` coelhinho *de chocolate* · `ANU` ursinho *de creme* · `ANP` porquinho *de creme* |
| `CORNET` | **2** | `CO` · `COC` de chocolate |
| `ESPRESSO` | **2** | `SS` · `SL` macchiato |
| `CAMPAGNE` | **2** | `CGO` oval · `CGR` redondo |
| `KURO-PAN` | **2** | `KP` · `KBB` burger |
| `BAGUETE-GERGELIM` | **2** | `BE` · `BEP` mini, **usada em caixas presente** |
| `PAO-HOTDOG` | 1 | `MIPHO` (mini) não vinga |
| `CIABATTA` | 1 | `CIQ` (quadrado) não vinga |

⚠️ **`ANP` nasce inativo** — porquinho de creme não está sendo feito no momento.
O produto existe, guarda a história e volta com uma flag, não com um SKU novo.
É o que `is_sellable=False` serve para dizer.

⚠️ **`BEP` é a lição.** Eu tinha lido "14 linhas em dois anos" como produto morto.
É produto de **caixa presente** — vende pouco no balcão por não ser vendido no
balcão. Volume mede o canal, não a existência. Mesma armadilha do §4.

### 2.2 O "do dia" — recomendação

O cardápio 2027 colapsou famílias inteiras em produtos rotativos: "Folhado do
dia", "Salgado do dia", "Focaccia do dia", "Chá Gelado do dia", "Cream Soda do
dia". É por isso que 29 produtos de alto volume do Yooga não têm par —
`BCH` Brioche Chocolat (11.983 linhas), `CN` Chausson (10.711), `PR` Pain aux
Raisins (8.866), `FF` Folhado de Frango (5.387).

**Recomendação: restaurar os SKUs originais e deixar o "do dia" ser uma coleção,
não um produto.** Quatro razões, e nenhuma é de gosto:

1. **O eixo do B.I. é planejar a produção.** "Folhado do dia" como SKU não
   responde *qual* folhado assar amanhã — que é a pergunta.
2. **Fornada precisa de `output_sku` real.** Não existe ficha técnica de "do dia":
   a `Recipe` produz um pão específico.
3. **Estoque não distingue.** Um quant de "Folhado do dia" não separa "sobrou
   frango" de "faltou queijo" — e sobra/falta é medição que já está no ar.
4. **Preço.** Focaccia Alecrim saía a R$ 28 e a de Cebola/Bacon/Tomilho a R$ 36.
   Um SKU só não guarda dois preços.

O sistema já tem o mecanismo certo do outro lado: **coleção e listing**. O
cardápio mostra "Folhado do dia — hoje, de frango"; por baixo, o produto é o
`FF`. A vitrine fica curta sem que a identidade se perca, e disponibilidade já é
função do quando ([availability](../guides/lifecycle.md)).

### 2.3 Os 30 códigos novos

Produto que o Yooga nunca viu ganha código pela mesma convenção — 2 letras
(iniciais, ou 1ª + consoante marcante), 3 quando é família:

`THB` `THC` `THR` `THS` `THG` `THL` (chás — família própria, porque `C*` já
carrega croissant, cornet, campagne, croque, challah, chausson, ciabatta,
chocolate quente e caffè latte) · `CD` coado · `CE` coffee float · `AG` água ·
`SO` soda de laranja · `CV` cream soda · `LN` lata Nelson · `PU` purin ·
`TJ` tea jelly · `SK` shokupan · `PG` pain grillé · `FD` focaccia do dia ·
`MS` melon iced sando · `SD` salgado do dia · `FL` folhado do dia ·
`TI` tábua de iguarias · `GR` café em grão · `GL` geleia · `QP` queijo pomerode ·
`BK` bacon · `MT` mostarda · `CX` cornichons · `TP` tapenade · `PT` patê.

Zero colisão com os 143 do Yooga e entre si. ⚠️ Vários destes deixam de ser
necessários se o §2.2 for adotado — `FD`, `SD`, `FL` e `THG` são justamente os
"do dia".

## 3. Execução

**F1 — O mapa.** 🟡 [`sku-real-mapa.csv`](sku-real-mapa.csv) traz as 143 linhas
com preço praticado (últimos 12 meses, histórico até 20/07) e cada uma
classificada:

| `situacao` | Quantas | O que significa |
|---|---:|---|
| `confirmado` | 26 | par conferido pelo dono |
| `desdobrar` | 10 | vira produto próprio (§2.1) |
| `juntar` | 2 | variante que não vingou, entra no irmão |
| `CANDIDATO` | 27 | **decisão sua**: par que meu casador perdeu, ou aposentado? |
| `aposentado?` | 20 | baixo volume, provavelmente fora |
| `preco` | 41 | `M*` metade do preço — vira modifier, nunca SKU |
| `canal` | 16 | `IFOOD_*` — vira espelho de canal, nunca SKU |

⚠️ Dois candidatos com cara de família perdida: `JO` Caranguejo (4.211 linhas) e
`MA` Maçã (4.433) parecem ser moldados como os animalzinhos, só que sem o
prefixo `AN`.

**F2 — O mecanismo.** ✅ Feito. SKU no registro de refs, 17 campos no cascade,
defeito do `db_index` corrigido, cobertura testada.

**F3 — Renomear.** Um comando idempotente sobre `RefBulk.cascade_rename`, com
`--dry-run` que **executa e desfaz** (o padrão que o `apply_catalog_taxonomy` já
usa). Um SKU por vez, conferindo entre eles.

**F4 — O seed.** `config/management/commands/seed.py` passa a nascer com os
códigos reais. Sem isto, o próximo `seed --flush` traz os inventados de volta —
é aqui que a troca vira permanente.

**F5 — O iFood.** Ressincronizar o catálogo e conferir `CatalogSyncState`. É o
único ponto fora do nosso banco: renomear aqui não renomeia lá.

## 4. O que NÃO fazer

- **Não criar apelido, `legacy_sku` nem tabela de tradução.** Pré-go-live não há
  legado: o nome antigo se apaga (CLAUDE.md). As duas versões anteriores deste
  plano propuseram isso e estavam erradas.
- **Não tratar dado de seed como se fosse história.** Os 216 pedidos nativos e os
  322 movimentos de estoque são seed, QA e piloto automático — a casa ainda não
  vendeu pelo Shopman. Antes de proteger um registro, pergunte de onde ele veio.
- **Não transformar código de preço ou de canal em SKU.** `M*` é modifier,
  `IFOOD_*` é espelho de canal. Adotá-los como SKU seria importar para o Shopman
  a limitação do sistema antigo.
- **Não confiar no palpite de nome.** Foi assim que o "Hambúrguer 100g" quase
  virou lanche quando é o pão. O CSV é para conferir, não para aplicar.
- **Não fazer junto com outra mudança de catálogo.** Se algo quebrar, tem de
  ficar óbvio o que foi.
