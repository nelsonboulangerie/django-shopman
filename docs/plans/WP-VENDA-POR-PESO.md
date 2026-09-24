# WP — Venda por peso (etiqueta de balança no PDV)

> Pergunta do dono em 22/09/2026, sobre o Queijo Vale do Testo, que chega da
> Pomerode em peças de peso diferente: *"vou tentar providenciar a balança,
> mas… como fica o preço do produto na hora da venda, vira um cód. barras, é
> isso? já funcionaria hoje se tivesse a etiqueta de pesagem assim? o item do
> PDV traria o preço por quilo, confere?"*
>
> **Resposta medida no código: não funcionaria hoje.** Este documento é o
> plano, não a implementação.

## Como a etiqueta de balança funciona

A balança etiquetadora imprime um **EAN-13 de uso interno**, que começa com
`2`. O resto dos 12 dígitos é convenção da loja, e as balanças oferecem dois
formatos:

| Formato | O que os dígitos carregam | O que o PDV faz |
|---|---|---|
| **Por preço** | código do item + **valor em reais** | usa o valor impresso; não precisa saber preço/kg |
| **Por peso** | código do item + **peso em gramas** | multiplica pelo preço por quilo do cadastro |

O código de dentro da etiqueta é o **código da balança**, não o SKU do
Shopman: a balança tem cadastro próprio, com 4 a 6 dígitos. Alguém precisa
ligar um ao outro.

## O que existe hoje, medido

| Peça | Estado | Onde |
|---|---|---|
| Quantidade fracionária no pedido | **existe** — `Decimal(12,3)` | `orderman/models/session.py:436`, `order.py:375` |
| NFC-e com quantidade fracionária | **existe** — 3 casas, e `vUnCom` derivado para não ser rejeitado | `shop/adapters/fiscal_focusnfe.py:445` |
| Leitor de código de barras apontado para o carrinho | **não existe** | a captura HID é exclusiva do crachá do operador (`operator-kit/app/composables/useIdentityCapture.ts`) |
| Busca por código de barras | **não existe** — a busca do PDV filtra nome e SKU do que já está na tela | `pos-nuxt/app/presentation/catalog.ts:58` |
| Unidade de venda com semântica | **não existe** — `Product.unit` é texto livre ("un, kg, lt, etc."), nunca entra em cálculo | `offerman/models/product.py:70` |
| Preço por quilo | **não existe** — só `base_price_q`, por unidade de venda | `offerman/models/product.py:117` |
| Vírgula no teclado de quantidade | **não existe** — o numpad faz `parseInt` | `pos-nuxt/app/presentation/numpad.ts:27` |
| Caminho do PDV no servidor | **trunca** — `int(item["qty"])` em quatro pontos | `shop/services/pos.py:784,1774,2330,2371` |

⚠️ O último item é o mais perigoso: hoje uma linha de 0,350 kg não daria erro,
daria **zero**. Truncar em silêncio é pior que recusar.

O roadmap do PDV já declarava "venda por peso" como fora de escopo
(`docs/plans/POS-FIRST-CLASS-PLAN.md:6`). Este WP é o que falta para tirá-la
de lá.

## O caminho mais curto: etiqueta por PREÇO

Para **um** produto de peso variável, a etiqueta por preço resolve com menos
peças: o valor já vem fechado da balança, então o PDV não precisa de preço por
quilo nem de multiplicação. O que ele precisa é ler, reconhecer e lançar.

- **F1 — ler a etiqueta.** Captura de leitor no PDV (fora do modal do crachá),
  parser de EAN-13 prefixo `2`, mapa `código da balança → SKU` (cabe em
  `Product.metadata`, como o resto), e a linha nasce com o valor impresso.
  Destrava o queijo sozinho.
- **F2 — quantidade fracionária de ponta a ponta.** Tirar os `int(qty)` de
  `shop/services/pos.py`, vírgula no numpad, e a linha mostrar "0,350 kg ×
  R$ 89,00/kg". O fiscal já aceita.
- **F3 — preço por quilo no catálogo.** `Product` ganha unidade de venda com
  semântica e preço por quilo; a etiqueta por peso passa a funcionar, e a loja
  online pode mostrar "R$/kg".
- **F4 — estoque em quilo.** O ledger já move decimal; falta o recebimento de
  revenda pesável conversar com a venda pesável.

## A decisão que vem antes do código

Comprar a balança não é a única saída, e a mais barata não tem código nenhum:
**pedir à Pomerode peças padronizadas**, como já acontece com o Camembert
125 g e o Mini Brie 25 g que a casa compra dela. Aí o produto vira peso fixo e
nada disto é preciso.

O WP só se paga quando houver **mais de um** produto pesável, ou quando o
queijo em peça inteira for decisão de merchandising que a casa quer manter.

⚠️ Fora do sistema, mas parte da mesma decisão: balança etiquetadora é
instrumento de medição — precisa ser **aferida pelo Inmetro**, com verificação
periódica. Quem pesa e etiqueta assume essa obrigação; quando o fornecedor
pesa, ela é dele.
