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

**F1 — O mapa.** ✅ Fechado (18/08). As 143 linhas de
[`sku-real-mapa.csv`](sku-real-mapa.csv) trazem preço praticado e destino:

| `situacao` | Linhas | O que acontece |
|---|---:|---|
| `preco` | 41 | `M*` era desconto do sistema antigo — qualidade mínima **ou** pão de ontem, sem distinção. Vira modifier sobre o produto-base. |
| `restaurar` | 32 | produto volta ao catálogo com o código real |
| `confirmado` | 27 | produto do 2027 recebe o código real |
| `canal` | 16 | `IFOOD_*` associa ao produto-base e ao canal |
| `revenda?` | 13 | ⚠️ linha Chai Kãnfa — **única decisão aberta** |
| `desdobrar` | 10 | vira produto próprio, irmão de um do 2027 |
| `juntar` | 2 | variante que não vingou, some no irmão |
| `bundle` | 1 | `COMBO` vira bundle na coleção Combos, não SKU |
| `nao-vem` | 1 | `TX` é taxa de entrega: modalidade, não item de cardápio |

Três achados que só apareceram ao fechar o mapa:

1. **`MOCHACCINO` recebia dois códigos** — `MC` Mocaccino e `MH` Mocha. São
   bebidas diferentes; o par por nome é o `MC`, e o Mocha entra como restauração.
   Achei porque meu primeiro teste de colisão olhava só o lado do destino.
2. **⚠️ Dois códigos mudam de unidade, e o B.I. não pode comparar os dois lados.**
   `PHO` era "Pão para Hot Dog — **Unidade**" a R$ 6; no cardápio 2027 é
   "**pc. 4un.**" a R$ 28. `BBB` era unidade a R$ 8; hoje é "pc. 2un." a R$ 16.
   Manter o código faz 6.360 vendas históricas de *unidade* virarem base de
   comparação para vendas de *pacote* — erro de 4×. **Recomendo código próprio
   para o pacote** (`PHO4`, `BBB2`), preservando `PHO`/`BBB` como a unidade: é a
   mesma regra que separou o mini do tradicional.
3. **Três dos 16 `IFOOD_*` são revenda e não podem casar por nome:** mostarda
   Maille ≠ Mostarda da Casa, geleia St. Dalfour 284g ≠ a mini, refri Wewi ≠ a
   Soda de Laranja da casa. Casar por nome aqui fundiria produto comprado com
   produto da casa.

**F2 — O mecanismo.** ✅ Feito. SKU no registro de refs, 17 campos no cascade,
defeito do `db_index` corrigido, cobertura testada.

**F3 — Renomear.** ✅ Feito.
[`rename_skus_to_real`](../../config/management/commands/rename_skus_to_real.py)
roda sobre o `RefBulk.cascade_rename`, com `--dry-run` que executa e desfaz e
`--only SKU` para conferir um a um. 25 pares; `PAO-HOTDOG` e `BRIOCHE-BURGER`
ficam retidos até a decisão do §F1.2.

⚠️ **Colisão em campo único foi o que quase passou.** Um ensaio sobre banco
semeado derrubou o comando com `IntegrityError`: `ProductConsumptionTag.sku` é
único, e o `propose_consumption_tags --include-historical` já tinha etiquetado
os códigos do Yooga. Seis pares afetados. Os testes unitários passavam porque
criavam um produto por vez — foi o ensaio de ponta a ponta que achou.

A política é explícita por model, porque depende do que a linha significa:
etiqueta de consumo é **anotação** e funde (a curada vence a proposta; no
empate sobrevive a do catálogo); produto e insumo são **entidade** e o comando
recusa, devolvendo a decisão. Campo de SKU único sem política faz o comando
parar — e um teste garante que nenhum exista.

Verificado em banco semeado: 25 SKUs, 12.834 linhas, 6 anotações fundidas,
ensaio desfazendo tudo e execução repetida sem efeito.

**F4 — O seed.** ✅ Feito. `seed.py` nasce com os códigos reais: 56 SKUs
trocados (531 literais, reescritos por `tokenize` — `re.sub` levaria junto o
`MASSA-CAMPAGNE`, que é insumo), mais os 10 desdobramentos e 31 restaurações.
O catálogo vai de 59 para 100 produtos.

⚠️ **Os 41 novos nascem despublicados, e é o próprio seed que exige isso.** O
portão de completude cobra alergênicos, informação nutricional, dieta, porção e
ingredientes — dado da casa, do tipo que ninguém inventa. Eles existem no
catálogo com código e preço reais (o mais praticado nos 12 meses até 20/07) e
entram na vitrine quando a ficha for preenchida: tire o SKU de `sem_ficha` e o
portão passa a validá-los como todos os outros. `ANP` (porquinho) também nasce
fora de venda — não está sendo feito.

Coleção, descrição, validade, peso e conservação dos 41 são **proposta**, pelo
padrão da coleção. Imagem fica vazia de propósito: foto errada é pior que sem
foto.

Dois efeitos que só apareceram ao rodar:

1. **A curadoria de consumo perdeu 7 etiquetas, e está certo.** `CT`, `PC`,
   `MD`, `ME`, `CO`, `ANC` e `KP` eram etiquetados duas vezes — uma pelo
   cardápio, outra pelo histórico do Yooga. Com o código real são o mesmo
   produto, e uma etiqueta basta. As duas curadorias **concordam** na leitura, e
   agora um teste garante isso: se divergirem, quem roda por último venceria em
   silêncio.
2. **Os rotativos e os reais convivem.** "Folhado do dia" (`FL`) e "Folhado de
   Frango" (`FF`) existem os dois, assim como as focaccias. Se a recomendação do
   §2.2 for adotada, os quatro "do dia" (`FD`, `SD`, `FL`, `THG`) saem e viram
   coleção.

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
