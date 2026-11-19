# #2806: o Recebimento do PDV sem o X sobre a frase, a escolha que se vê e um separador só

Três defeitos antigos do diálogo Recebimento, vistos na prévia do WP-E13 (#2774). Capturas
do PDV de verdade (Django semeado e PDV compilado), com a Caixa (Fran) entrando com PIN,
em 375 px (celular) e 1366 px (balcão). `antes/` é o branch do WP-E13 (a base deste PR);
`depois/` é este PR. A cliente é a Maria Santos, com o endereço de Casa já escolhido para
a entrega.

## O que mudou, na língua do balcão

1. **O X não fica mais em cima da frase.** No celular, o X do canto cobria a palavra
   "definem". Agora ele fica na linha do título, e a frase termina antes dele. Vale para
   todo diálogo e toda gaveta lateral dos apps de operador.
2. **A frase de abertura diz o que fazer**: "Escolha como o cliente recebe o pedido."
   Antes: "Escolha uma opção. Cliente e data não definem como o pedido será recebido."
3. **Retirada e Entrega mostram qual está escolhida**: a bolinha cheia, a borda e o fundo
   da cor da casa, igual à lista de endereços logo abaixo. Antes, o escolhido só mudava um
   tom de fundo. E o cartão Entrega diz o que acontece com o pedido, como o da Retirada:
   "O pedido vai até o endereço do cliente." (antes: "Entrega local com endereço informado
   pelo operador."). A mesma frase aparece no assistente da encomenda.
4. **O endereço escolhido usa o mesmo " · " da lista**, e diz o complemento como a lista:
   "Rua Belo Horizonte, 540, Apto 12 · Centro · Londrina/PR". Antes: "Rua Belo Horizonte,
   540 - Centro - Londrina/PR". O endereço da nota, do entregador e do pedido não muda.

## As capturas

Em `antes/375`, `antes/1366`, `depois/375` e `depois/1366`, os mesmos quatro passos:

| Arquivo | O que mostra |
|---|---|
| `01-abertura-do-recebimento` | o diálogo abrindo com a Entrega escolhida: o X e a frase |
| `02-retirada-escolhida` | um toque em Retirada |
| `03-entrega-escolhida` | de volta à Entrega, com o endereço de Casa marcado na lista |
| `04-resumo-do-endereco-escolhido` | o endereço escolhido, abaixo da busca |

As mais representativas: `antes/375/01-abertura-do-recebimento.png` (o X sobre "definem")
contra `depois/375/01-abertura-do-recebimento.png`; e `antes/375/02-retirada-escolhida.png`
contra `depois/375/02-retirada-escolhida.png`.

As capturas `01`, `02` e `03` do depois foram refeitas com a frase nova do cartão
Entrega; a `04` mostra o endereço, com os cartões fora da tela, e ficou como estava.

## A auditoria

`auditoria-depois.txt`, por script, nas oito telas do depois e do antes. No depois: o X
sobre 0 linhas do título e da frase (no antes, 1 linha da frase a 375 px); transbordo
lateral 0 em 375 e 1366; os dois cartões com o papel de rádio, a mesma altura (110 px a 375, 90 px a 1366) e o
mesmo topo; contraste mínimo 5,75:1 (a descrição do cartão escolhido, sobre o fundo tingido;
passa o AA de 4,5 e fica abaixo do AAA de 7, como a descrição da lista de endereços);
toda letra em 14 ou 16 px.
