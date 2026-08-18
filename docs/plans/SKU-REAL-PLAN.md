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

### 2.1 A pergunta que sobra é de granularidade, e é sua

Descontados preço e canal, ainda sobra produto de verdade colapsado. O caso mais
claro:

```
CROISSANT (cardápio 2027)  ←  CT   Croissant Tradicional      21.298 linhas
                           ←  CM   Croissant Mini             13.195 linhas
                           ←  CPQ  Croissant Presunto e Queijo 5.660 linhas
```

O Yooga tratava os três como produtos distintos. O cardápio 2027 tem **um**
`CROISSANT`. Mesma história em `CORNET` (`CO` × `COC` de chocolate), `ESPRESSO`
(`SS` × `SL` macchiato), `CAMPAGNE` (`CGO` oval × `CGR` redondo), `KURO-PAN`
(`KP` × `KBB` burger) — **13 dos 27 produtos** têm mais de um código real.

Duas leituras, e a escolha é sua:

1. **O cardápio 2027 aposentou variantes de propósito.** Aí o produto fica um só,
   herda o código do irmão de maior volume (`CT`), e o histórico dos outros
   continua legível pelo `HistoricalSaleItem` — que não muda.
2. **O seed colapsou o que a casa vende separado.** Aí não é rename, é
   desdobramento de produto: `CT`, `CM` e `CPQ` viram três `Product`.

⚠️ **A escolha muda o B.I., não só o nome.** Colapsado, "croissant" vende 40.439;
desdobrado, o tradicional vende 21.298 e o mini 13.195 — e a pergunta "o mini
puxa venda ou canibaliza?" só existe na segunda leitura.

### 2.2 Os 31 produtos sem código real

Dos 58 produtos do cardápio 2027, **27 têm código real e 31 não têm**. Os sem
código são, na maior parte, produto novo que o Yooga nunca viu: a linha de chás
(`CHA-BLEU`, `CHA-CAMILLE`, `CHA-ROUGE`, `CHA-SOPHIE`), `PURIN`, `TEA-JELLY`,
`MELON-ICED-SANDO`, `SHOKUPAN`, `COFFEE-FLOAT`. Esses precisam de código novo, e
aí a numeração é decisão de desenho — não há histórico a respeitar.

O mapa para conferência está em
[`sku-real-mapa.csv`](sku-real-mapa.csv) (143 linhas, coluna `SEU_SKU_CORRETO`
em branco para você preencher).

---

## 3. Execução

**F1 — O mapa.** ✅ 56 correspondências levantadas e conferidas por você (18/08).
Falta a decisão do §2.1 (granularidade) e os 31 do §2.2.

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
