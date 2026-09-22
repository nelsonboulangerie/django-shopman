# WP — Variação de produto e adicional de linha

> Pedido do dono em 22/09/2026, durante a consolidação do catálogo: *"Poderia
> deixar só como … Quente e … Gelado, mas aí teria que ter uma forma canônica
> de escolher o sabor, tipo a variação do produto. Mas receio que atualmente
> nem o PDV nem a Loja online tratam isso."* Ele leu certo: não tratam. Este
> documento é o plano, não a implementação.

## O problema, com os casos reais na mão

A casa vende a mesma coisa em duas formas que o catálogo de hoje não sabe
dizer, e a falta empurra os dois para o único lugar que existe — um SKU por
combinação:

**1. Variação: o sabor do dia.** O chá servido é um produto (*Chá Quente*,
R$ 13) que muda de sabor (Bleu, Camille, Rouge, Sophie). Hoje isso vive como
quatro SKUs, `THB`/`THC`/`THR`/`THS`, com o mesmo preço e a mesma promessa.
Mesmo formato em outras vagas: focaccia do dia, folhado do dia, cream soda do
dia, animalzinho — hoje resolvidos como "1 SKU fixo por vaga, o sabor é
operação" (Cardápio 2027), que é o contorno, não o conceito.

**2. Adicional: o que se soma à linha.** *Chantilly Extra* (R$ 6) vendeu 105
vezes em 12 meses no sistema antigo. Não é produto de prateleira: é um
acréscimo a uma bebida que já está na comanda. Hoje só caberia como SKU
solto, e aí ele aparece na loja e no feed do Google como se fosse um item
que alguém pode comprar sozinho.

⚠️ O que **não** é este WP: *Ciabatta*, *Ciabatta 170g* e *Ciabatta Quadrado*
são três pães diferentes (confirmado pelo dono em 22/09). Tamanho que muda o
pão não é variação; é outro produto.

## O que existe hoje, e por que não serve

| Peça | O que faz | Por que não resolve |
|---|---|---|
| `offerman.ProductComponent` | compõe um produto a partir de outros (kit/combo) | o combo é um produto novo, com preço próprio; não é escolha na hora da venda |
| `shop/modifiers.py` | D1, desconto, funcionário, happy hour | mexe no PREÇO da linha, não no que a linha é |
| Coleções + "1 SKU por vaga" | o sabor do dia é operação | o cliente não escolhe; e o histórico não sabe qual sabor saiu |
| `Session.data` / `Order.data` | guardam contexto livre | sem contrato, cada superfície inventaria o seu |

## A forma proposta

Dois conceitos distintos, que a conversa acima mistura de propósito porque a
tela é a mesma:

- **Variação** — o produto tem um eixo (`sabor`, `tamanho`) com opções. A
  venda escolhe **uma**, obrigatoriamente. Preço normalmente igual entre as
  opções; quando muda, é preço por opção, não SKU novo.
- **Adicional** — item que **acompanha** uma linha e soma ao preço dela.
  Opcional, pode repetir, e nunca é vendável sozinho.

Nenhum dos dois pede tabela nova no Core: ambos cabem em
`Product.metadata` (é o padrão da casa, ver `docs/reference/data-schemas.md`)
e no `meta` da linha da Session/Order, que já atravessa commit e nota.

Esboço a validar na implementação:

```json
// Product.metadata
{"variants": {"axis": "sabor", "label": "Sabor",
              "options": [{"ref": "bleu", "name": "Bleu"},
                          {"ref": "rouge", "name": "Rouge"}]},
 "addons": {"allowed": ["CHANTILLY"], "max": 2}}
```

A linha vendida carrega a escolha (`meta.variant = "bleu"`,
`meta.addons = ["CHANTILLY"]`), e é isso que o B.I. lê para responder "qual
sabor sai mais" — pergunta que hoje não tem resposta.

## Onde encosta (o custo real do WP)

1. **Catálogo (Gestor)**: declarar eixo, opções e adicionais permitidos.
2. **PDV**: escolher a variação ao lançar a linha; somar adicional. É a
   superfície mais sensível — o gesto não pode ganhar um passo.
3. **Loja (storefront)**: escolher o sabor antes de pôr no carrinho, e a
   disponibilidade por opção (sabor que acabou).
4. **KDS/Produção**: a ficha precisa dizer o sabor, senão a cozinha não sabe.
5. **Fiscal**: a NFC-e descreve o item vendido; adicional entra como item
   próprio ou compõe o valor da linha — **pergunta para o contador**.
6. **B.I.**: `HistoricalSaleItem` passa a ter o eixo; as séries antigas não
   têm, e isso precisa aparecer como "sem informação", nunca como zero.
7. **iFood/Meta/Google**: o feed exporta o produto-pai; variação e adicional
   têm contrato próprio em cada canal (complemento no iFood, `item_group_id`
   no Meta) — cada um é um passo, não um efeito colateral.

## Como entra (fatiado, e cada fatia útil sozinha)

- **F1 — adicional no PDV.** Resolve o Chantilly, que é o caso vivo e o de
  menor alcance: só PDV e comanda. Loja não muda.
- **F2 — variação no catálogo e no PDV.** Junta os quatro chás do bule num
  *Chá Quente* com sabor. Loja ainda mostra o produto-pai sem escolher.
- **F3 — variação na loja e na disponibilidade.** O cliente escolhe; sabor
  esgotado some.
- **F4 — canais e B.I.** Feed, iFood e as séries por sabor.

## Pendências que este WP herda

- Os SKUs `KFQ`, `KFG` e `KFC` (Chá Kãfa Quente/Gelado/Citrus do sistema
  antigo) estão na planilha do catálogo como **a decidir**, esperando F2.
- `CHX` (Chantilly Extra) está como **adicional**: não nasce produto.
- *Soft Chai Cítrico* e *Chá Tônica Frutas Vermelhas* **ficam separados** —
  são produtos diferentes, não variação (dono, 22/09).
