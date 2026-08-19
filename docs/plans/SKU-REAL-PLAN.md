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

### 2.2 O "do dia" — decidido (18/08): vira coleção

O cardápio 2027 colapsou famílias inteiras em produtos rotativos. **O dono
adotou a recomendação:** os quatro viram coleção, e o produto por baixo é o real.

| Saiu como produto | Virou a coleção | Sobre os produtos |
|---|---|---|
| `FD` Focaccia do dia | `focaccia-do-dia` | `FOA` · `CBT` · `FOC` + as três minis |
| `FL` Folhado do dia | `folhado-do-dia` | `CN` · `BH` · `PR` |
| `SD` Salgado do dia | `salgado-do-dia` | `DL` · `HO` · `MIHO` · `FF` · `MFF` |
| `THG` Chá gelado do dia | `cha-gelado-do-dia` | `HI` · `CTV` |

⚠️ **A membresia não é palpite meu — está na copy que a casa escreveu.** "O
folhado da fornada: chausson, bichon, pain aux raisins…" nomeia exatamente os
três; o texto de ingredientes do "Salgado do dia" diz "deli de milho e bacon ou
salsicha artesanal".

**O vínculo é secundário.** O produto continua morando na sua categoria:
Chausson é Finos *e* aparece em "Folhado do dia". Por isso o teste de coerência
fala em uma categoria por produto, não uma coleção.

`CV` (Cream Soda do dia) **fica como produto**: não há produto real por baixo
dele. Ali o sabor rotaciona dentro de um preparo só, que é diferente de um
folhado ser outro produto a cada dia.

As duas receitas que produziam "do dia" passam a produzir o real — `FD` → `FOA`,
`FL` → `CN`. Era o argumento nº 2 da recomendação, e virou código.

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

> ⚠️ A coluna **`aponta_para`** (antes `sku_2027`) não é "o SKU do cardápio
> 2027": ela aponta para a linha-destino, e o destino muda com a `situacao` —
> em `confirmado` é o produto do cardápio, em `preco` e `canal` é o **SKU-base
> do Yooga**. Uma sessão irmã tentou usá-la como medida de "identidade
> pré-rename" e o número nunca zeraria: 43 dos 73 valores são também
> `sku_yooga`. Coluna cujo sentido depende de outra coluna engana quem lê de
> fora.

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

**F5 — O iFood.** ✅ Feito, e era mais sério do que "ressincronizar".

⚠️ **O id do item no iFood sai do NOSSO SKU:** `uuid5(merchant_id, "item:" +
sku)` (ver `catalog_projection_ifood`). Trocar `CROISSANT` por `CT` muda o uuid —
o sync cria um item **novo**, e o antigo **continua no cardápio deles,
disponível para venda**, apontando para um SKU que não existe mais aqui. Pedido
nesse item chega e não resolve produto.

O `sync_catalog_ifood` incremental não alcança: ele reconcilia o que está na
listagem, e o nome antigo saiu dela. Quem sabe o nome antigo é o mapa do rename.

[`ifood_retract_renamed_skus`](../../shopman/shop/management/commands/ifood_retract_renamed_skus.py)
parte desse mapa e retira os órfãos. A **ordem importa, e o comando a protege**:
ele recusa retirar SKU que ainda existe no catálogo, porque antes do rename o
nome antigo é o produto que está vendendo. Só retira os pares cujo código novo
já está no catálogo — se o rename não rodou, não há órfão.

## 4. A ordem de execução

```bash
python manage.py ingest_yooga --delivery-flags-only   # 201 vendas mal marcadas
python manage.py rename_skus_to_real --dry-run        # confere
python manage.py rename_skus_to_real                  # aplica
python manage.py ifood_retract_renamed_skus --dry-run # confere
python manage.py ifood_retract_renamed_skus           # limpa o cardápio deles
python manage.py sync_catalog_ifood --full            # publica os códigos novos
```

### 4.1 A limpeza que só pode vir DEPOIS

⚠️ `measure_eat_in_weights` tem um mapa `TWINS` que liga SKU do cardápio 2027 ao
gêmeo no Yooga (`CROISSANT → CT`). Ele existe porque os dois lados usam códigos
diferentes para o mesmo pão, e **morre no dia em que o rename rodar** — a partir
dali cada SKU se mede sozinho, que é melhor.

**Não remova antes.** Medido no staging em 19/08, com o rename ainda por rodar,
o mapa está entregando peso às 11 chaves: `CROISSANT` 9% herdado do `CT`,
`FOLHADO-DIA` 29% herdado do `FF`, `CORNET` 10% da média de `CO`+`COC`. Tirá-lo
antes do rename derruba esses 11 para o piso, em silêncio.

⚠️ **E a lição de como eu errei isso:** removi o mapa depois de conferir contra
`seed.py` e ver zero ocorrência de `CROISSANT`. O seed é *fixture*; o catálogo
vivo do staging é outro — 59 produtos com os SKUs longos, editados à mão pelo
dono, com canonização pendente. Conferir identidade de catálogo contra o seed
responde a pergunta errada.

## 5. O que NÃO fazer

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
