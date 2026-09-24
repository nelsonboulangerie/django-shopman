# WP — A ficha precisa enxergar abaixo do grama

> Pedido dele em 24/09/2026: *"acho que vamos ter que ajustar a precisão das fichas
> técnicas/produção para g em vez de kg. Vão ter vários casos de fração de gramas…
> por exemplo nas bebidas."*

## O defeito, medido

Toda quantidade da ficha e da produção é gravada em **kg com três casas**. A menor
quantidade que cabe numa linha é, portanto, **1 g**. O F2 das fichas reais
(`WP-FICHAS-REAIS-DA-CASA`) esbarrou nisso três vezes no mesmo dia:

| insumo | quanto vai | o que a ficha fez |
|---|---|---|
| alecrim na finalização da focaccia | 0,1 g (0,05 g na pequena) | ficou **fora** da ficha |
| louro no recheio de frango | 1 folha = 0,34 g | ficou **fora** |
| baunilha no creme do pain perdu | 2 gotas = 0,125 g | a receita foi **escalada ×8** só para caber |

Arredondar para 1 g não serve. A baixa de estoque não converte unidade, e 0,1 g
gravado como 1 g **desconta dez vezes** o que vai na peça. Nas bebidas, que são por
unidade, o problema aparece em toda especiaria, gota e pitada.

## A decisão de desenho: mais casas, não outra unidade

Gravar em **grama** no lugar de quilo parece a correção natural, e não é. Mudar a
unidade de gravação é mudar a **unidade-base** do insumo. A
[ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md) (R1) fixou o kg
porque é nele que a casa pesa e o livro conta, e a nota fiscal, a conversão de
compra, o custo, o estoque e o B.I. conversam nessa base. A própria ADR já
respondeu esta tentação: *"a ergonomia da ficha ('0,060 kg') não é resolvida
mudando a base"*.

O que falta é **resolução**, não unidade. **Proposta:** a quantidade continua em
kg e passa de **3 para 6 casas decimais**, com resolução de 1 mg (0,1 g =
`0.000100`). A tela continua mostrando em grama, como a mise en place já faz. Em
números: um campo muda de largura em cada tabela, nenhum dado muda de
significado, e o que existe hoje continua exato (`0.280` = `0.280000`).

## Onde as três casas estão travadas

| camada | campos | por que precisa |
|---|---|---|
| **Ficha** (craftsman) | `RecipeItem.quantity`, a `formula` da `RecipeVersion`, o arredondamento de `gross_quantity`, `contrib/formula` | é onde a quantidade nasce |
| **Fornada** (craftsman) | `WorkOrderItem.quantity` | consumo de uma fornada pequena de peça com insumo fracionado |
| **Estoque** (stockman) | `Move.quantity`, `Quant`, `Hold` | a baixa por VENDA (`WP-BAIXA-DE-INSUMO-NA-VENDA`) desconta uma bebida por vez: 0,5 g de canela vira zero com três casas |
| **API/serializers** | `min_value=0.001`, `decimal_places=3` | recusariam a ficha nova na borda |

**Fica como está:** as quantidades de pedido e venda (`orderman`, `offerman`),
que contam unidade ou peso de balcão e não têm esse problema. Também não mudam as
telas, que já formatam em grama.

## Fatias

1. **F1 — ficha e fornada** (craftsman): migração dos campos, arredondamentos e
   serializers, e o `seed` passa a gravar o alecrim, o louro do frango e a
   baunilha na escala real. Isso desfaz o ×8.
2. **F2 — estoque** (stockman): `Move`/`Quant`/`Hold`. Vem antes da baixa por
   venda, que é quem a exige.

Pré-go-live, as migrações são livres (ADR-015). A partir do go-live, ampliar casas
continua sendo migração segura: só alarga o campo.

## A pergunta que é dele

**Mais casas em kg (a proposta) ou unidade-base em grama?** A segunda também
resolve, mas reabre a ADR-024 e toca todo insumo, toda conversão de compra e todo
saldo de estoque. A primeira muda largura de campo e nada mais.
