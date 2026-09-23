# WP — Os insumos da vida real

> Pedido do dono em 23/09/2026: *"CAFE-GRAO e outros insumos eram genéricos, de
> teste. Precisamos urgentemente listar e completar a lista básica dos insumos,
> como estamos fazendo com os produtos."*

## O que este WP é, e o que ele não é

**É a curadoria da LISTA.** Os 57 insumos do alpha nasceram do seed para a ficha
técnica fechar — `FARINHA-T45`, `MANTEIGA-FR`, `CAFE-GRAO`. São plausíveis e
foram úteis, mas **não são o que a casa compra**: não têm marca, não têm
embalagem, não têm fornecedor, e alguns são genéricos onde a casa usa uma coisa
específica. É o mesmo trabalho que o catálogo de produtos acabou de receber, do
outro lado da cozinha.

**Não é** a fricção do recebimento — essa é do
[`WP-INSUMOS-SEM-FRICCAO`](WP-INSUMOS-SEM-FRICCAO.md) — nem o enriquecimento por
GTIN, que é do [`WP-ENRIQUECIMENTO-INSUMOS-GTIN`](WP-ENRIQUECIMENTO-INSUMOS-GTIN.md).
Os dois assumem que a lista está certa. **Este vem antes deles**: enriquecer o
insumo errado é trabalho perdido duas vezes.

## O estado, medido no alpha em 23/09

| | |
|---|---:|
| Insumos cadastrados | **57** |
| Sem custo de fornecedor | **52** |
| Sem conversão de unidade | **51** |
| Sem nenhuma ficha que os use | **3** |
| Movimentos de compra no ledger (`Move.kind=BUY`) | **0** |

Os mais usados dão a medida do problema:

| insumo | em quantas fichas | o que ele não diz |
|---|---:|---|
| `ACUCAR` Açúcar | 17 | cristal? refinado? demerara? |
| `MANTEIGA-FR` Manteiga francesa | 16 | qual marca, e em que peça |
| `LEITE` Leite integral | 15 | marca, embalagem |
| `SAL` Sal marinho | 13 | grosso ou fino |
| `CAFE-GRAO` Café em grão da casa | 8 | **qual torra, de quem** |

## Por que agora, e não depois do go-live

1. **A ficha técnica aponta para eles.** 266 linhas de ficha usam esses 57 SKUs.
   Renomear ou trocar um insumo depois arrasta a ficha junto — e o SKU dele
   divide namespace com o produto vendável
   (`shop/services/sku_namespace.py`), então o mesmo cuidado do rename de
   catálogo vale aqui.
2. **O custo do produto não existe sem eles.** 52 sem custo é 52 fichas que não
   dizem quanto custa fazer.
3. **A baixa na venda depende da lista certa.** O
   [`WP-BAIXA-DE-INSUMO-NA-VENDA`](WP-BAIXA-DE-INSUMO-NA-VENDA.md) vai descontar
   automaticamente o que a ficha manda: insumo genérico faz o desconto sair do
   lugar errado, em silêncio.

## Como fazer, no molde que já funcionou

O catálogo de produtos foi curado assim em 22–23/09, e deu certo:

1. **Uma aba na planilha viva** ([Catálogo Nelson — consolidado](https://docs.google.com/spreadsheets/d/1wXoIxaYFiEn1hj2k2mEH0NrOP3b1-sTnbspakD_YhKA/edit)),
   com os 57 como estão hoje e **uma coluna amarela por decisão**. A aba
   `Insumos` já existe e tem 8 renomeações propostas — releia-a antes de criar
   outra.
2. **Comando idempotente** no molde do `apply_product_skus`: tabela versionada,
   ensaio por padrão, `--apply`, recusa fechada em colisão.
3. **Ensaio antes de gravar**, provando o que arrasta: quantas linhas de ficha,
   quantos quants, quantos custos de fornecedor.
4. **Gravar no alpha pede a palavra dele.**

## As armadilhas já conhecidas, que não se redescobrem

- **O SKU do insumo divide namespace com o do produto vendável.** Colisão é
  recusada em `pre_save` nos dois modelos; o ensaio tem de provar que não há.
- **`MT` é o caso vivo disso**: é o código de um produto (Mostarda da Casa) e a
  aba `Insumos` o quer para a Dijon da Beaufor. Uma coisa ou outra.
- **A `AGUA` órfã** (nenhuma ficha, saldo 5 l) está marcada para apagar.
- **Unidade-base**: líquidos pesados vão para kg, não litro
  ([ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md)).
- **`Material.unit` serve dois senhores** — a receita e o custo. A unidade de
  compra é outro eixo (`MaterialConversion`); não force a unidade-base para
  resolver custo.

## O que sai deste WP

- A lista real, com nome que o padeiro reconhece.
- O de-para do que existe hoje para o que passa a existir, aplicado com ensaio.
- A aba da planilha respondida, para as duas frentes seguintes (custo/conversão
  e GTIN) começarem em cima de dado certo.

## Fora de escopo

- Custo por fornecedor e conversão de unidade (`WP-INSUMOS-SEM-FRICCAO`).
- GTIN e enriquecimento (`WP-ENRIQUECIMENTO-INSUMOS-GTIN`).
- A baixa na venda (`WP-BAIXA-DE-INSUMO-NA-VENDA`).
