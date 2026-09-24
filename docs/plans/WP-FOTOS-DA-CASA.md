# WP — As fotos da casa

> Pedido do dono em 22/09/2026: *"Vamos ter que resolver a questão das fotos.
> Merece uma WP separada? Pensei de gerar/usar ilustrações genéricas por
> coleção, para itens ainda sem foto, mas sem comprometer a experiência
> visual… Depois quero que me cobre diariamente sobre quais fotos faltam, pra
> eu providenciar, uma a uma."*

## O tamanho do problema, medido no alpha (22/09)

**Produtos com foto de banco de imagem (Unsplash): 59.** Um sem foto nenhuma.

| Coleção | Com foto de banco | Destes, publicados |
|---|---|---|
| Mercearia | 23 | 6 |
| Bebidas quentes | 12 | 8 |
| Bebidas geladas | 9 | 2 |
| Salgados | 7 | 6 |
| Doces | 4 | 1 |
| Macios | 2 | 1 |
| Rústicos | 2 | 0 |

**Treze desses estão no feed do Google.** Lá a imagem não é decoração: é
declaração sobre o produto à venda.

**Na home, 5 imagens de banco em 7 lugares:** as quatro variações do herói
(`HomeHeroThing.vue`: saudação, pedido, recompra, feito à mão), a foto do
bloco de WhatsApp e duas repetições em `pages/index.vue`.

## A pergunta da ilustração genérica — sim, com uma fronteira

A ideia é boa e tem precedente na casa: o PDV já veste o tile sem foto com a
**cor e o ícone da coleção**, e ninguém sente falta de uma foto ali. O mesmo
raciocínio serve à loja.

A fronteira é esta, e não é de gosto:

- **Nas nossas superfícies** (loja, PDV, KDS), ilustração por coleção é
  legítima. Ela não finge ser o produto: é um cartão bonito que diz "pão
  rústico" enquanto a foto real não chega. Melhor que um vazio, e muito melhor
  que a foto de outra padaria.
- **No feed do Google/Meta, não.** A política do Merchant Center espera que a
  imagem mostre **aquele** produto; imagem genérica é motivo de reprovação e,
  pior que isso, é a vitrine prometendo o que a loja não tem. **Item com
  ilustração genérica fica fora do feed enquanto estiver assim** — e isso
  precisa ser automático, não lembrado.

Ou seja: a ilustração resolve a experiência visual **sem** virar promessa. O
que ela não pode fazer é entrar no lugar onde o cliente decide pela foto.

## As fatias

**F1 — ilustração por coleção, declarada como tal.** O produto sem foto real
ganha um cartão com a cor e o ícone da coleção (o mesmo par que o PDV já usa,
vindo de `Collection.metadata`). O produto fica marcado como "sem foto real", e
é essa marca — não uma lista à mão — que tira o item do feed.

**F2 — a fila de fotos que faltam, ordenada pelo que mais sai.** O B.I. já sabe
o que vende; tirar a foto do que aparece mais é o que muda a loja mais rápido.
A fila é a mesma que alimenta a cobrança diária (F4).

**F3 — as fotos da home, uma a uma, com prévia local.** O dono tem candidatas.
O fluxo: ele põe o arquivo numa pasta, a sessão troca a imagem no ambiente
local, abre a home e devolve a captura — ele aprova ou pede a próxima. Sem
adivinhação e sem subir nada antes de ele ver. São 7 trocas, 5 imagens.

**F4 — a cobrança diária.** Uma rotina diária lista o que falta, na ordem da
F2, e diz quantos estão no feed com foto de banco. Não é relatório: é uma
lista curta do que ele pode resolver hoje, uma a uma.

## Onde as fotos reais moram

`img.nelsonboulangerie.com.br` (host dedicado desde 17/09) — ver
[[project_fotos_de_produto_moram_na_loja]]. O arquivo entra pela loja; o
catálogo guarda a URL.

## Fora de escopo

Gerar imagem de produto por IA. Foto de produto é promessa: se a peça não é
aquela, a foto mente — e a casa só afirma o que honra. Ilustração de coleção é
outra coisa, e está na F1 justamente porque não finge ser o produto.
