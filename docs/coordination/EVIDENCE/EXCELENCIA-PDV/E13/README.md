# WP-E13: na encomenda, "pra quando" vem em segundo e o endereço cabe na linha

Pedido do dono de 19/11/2026 (#2754). Capturas do PDV de verdade (Django semeado e PDV
compilado), com a Caixa (Fran) entrando com PIN, em 375 px (celular) e 1366 px (balcão).
`antes/` é o `main` de 19/11/2026; `depois/` é este PR. A cliente é a Maria Santos, que
tem três endereços: Casa (o padrão), um salvo de pedido de entrega (etiqueta "Entrega",
como o de quem vem do iFood) e Trabalho.

## ⚠️ F7 e F8 trocaram de lugar

A barra da venda passou a seguir a ordem da encomenda, e a tecla é da posição do botão:

| Tecla | Antes | Depois |
|---|---|---|
| F6 | Cliente | Cliente |
| **F7** | Recebimento | **Quando** |
| **F8** | Quando | **Recebimento** |

Vale no balcão também: "Agora" é F7 e "Consumir aqui" é F8. No celular, onde não há
tecla, o "Mais ações" lista Quando antes de Recebimento. A ajuda de atalhos (tecla `?`)
já diz a ordem nova. As teclas aparecem nos botões da barra em
`depois/1366/05-entrega-padrao-ja-marcado.png` (F6 Maria Santos, F7 Amanhã, F8 Entrega);
o antes está em `antes/1366/03-entrega-sem-endereco-marcado.png` (F7 Entrega, F8 Sem
agendamento).

## O que mudou, na língua do balcão

1. **A encomenda pergunta nesta ordem: cliente, para quando, entrega ou retirada.**
   Antes o "para quando" vinha por último. Escolhido o dia, a tela espera o horário: quem
   segue é o "Continuar".
2. **Cada endereço do cliente é uma linha inteira**, com a rua, o número, o complemento,
   o bairro e a cidade. Antes eram botõezinhos: "Casa", "Entrega", "Trabalho". A etiqueta
   só aparece quando diz alguma coisa (Casa, Trabalho, o nome que o cliente deu); a que só
   repete "Entrega" não aparece, e quem fala é o endereço.
3. **Ao tocar em Entrega, o endereço padrão já vem marcado.** No balcão, Enter aceita e
   segue; a seta para baixo passa para outro endereço, e Enter aceita. No celular, o toque
   na linha escolhe.
4. **"Tirar o endereço desta entrega"** deixa a entrega sem endereço. O endereço continua
   no cadastro do cliente, a tela diz isso ("Endereço tirado desta entrega. O cadastro do
   cliente não mudou.") e o "Desfazer" fica ao lado.

## As capturas

`depois/1366` (balcão, com teclado):

| Arquivo | O que mostra |
|---|---|
| `01-encomenda-pede-o-cliente` | etapa 1: cliente |
| `02-depois-pra-quando` | etapa 2: "Para quando?" |
| `03-dia-e-horario-no-cartao` | dia e horário escolhidos no próprio cartão |
| `04-depois-o-recebimento` | etapa 3: "Entrega ou retirada?" |
| `05-entrega-padrao-ja-marcado` | etapa 4: a lista, com a Casa já marcada e com o foco; F6, F7 e F8 na barra |
| `06-seta-escolhe-outro` | seta para baixo: o endereço sem etiqueta marcado |
| `07-barra-da-venda-na-ordem-nova` | a barra da venda: Cliente, Quando, Recebimento |
| `08-f7-abre-o-quando` | F7 abre o "Quando" |
| `09-recebimento-lista-de-linha-inteira` | F8 abre o Recebimento, com a mesma lista |
| `10-endereco-tirado-da-entrega` | a entrega sem endereço, a frase e o Desfazer |
| `11-outro-endereco-escolhido-no-recebimento` | outro endereço escolhido pelo toque |

`depois/375` (celular): os mesmos passos de 01 a 05, e depois
`06-toque-escolhe-outro`, `07-mais-acoes-quando-antes-do-recebimento`,
`08-recebimento-lista-de-linha-inteira`, `09-endereco-tirado-da-entrega` e
`10-outro-endereco-escolhido-no-recebimento`.

`antes/1366` e `antes/375` (o `main`):

| Arquivo | O que mostra |
|---|---|
| `01-encomenda-pede-o-cliente` | etapa 1: cliente |
| `02-depois-o-recebimento` | o recebimento vinha em segundo |
| `03-entrega-sem-endereco-marcado` | ao tocar em Entrega, nenhum endereço vinha marcado; a barra com F7 Entrega e F8 Sem agendamento |
| `04-enderecos-em-botoezinhos` | o diálogo com os botõezinhos "Casa", "Entrega" e "Trabalho" |
| `05-casa-escolhida-no-botaozinho` | a Casa escolhida pelo botãozinho |
| `06-pra-quando-por-ultimo` | o "para quando" vinha por último |
| `07-barra-cliente-recebimento-quando` (1366) | a barra na ordem antiga: Cliente, Recebimento, Quando |
| `07-mais-acoes-recebimento-antes-do-quando` (375) | o "Mais ações" com Recebimento antes de Quando |

## Auditoria

`auditoria-depois.txt` é a saída da jornada J11
(`surfaces/pos-nuxt/tests/e2e-live/j11-encomenda-endereco-do-cadastro.live.spec.ts`),
que mede a tela antes de capturar e reprova se qualquer medida sair da régua. Resultado:
`2 passed` (375 e 1366 px). O que ela mediu:

- **Contraste**: o menor é 4,62:1, nos dois botões da barra da venda em 1366 px
  ("Amanhã, a partir das 9h" e "Entrega · Centro", dourado `rgb(139, 107, 46)` sobre o
  creme). Na lista de endereços, o menor é 5,38:1, na segunda linha em tom suave
  ("Centro · Londrina/PR"); a rua e a etiqueta ficam entre 11,29:1 e 13,67:1. Tudo acima
  de 4,5:1.
- **Letra**: 14 px em todo texto medido.
- **Linhas de endereço**: de borda a borda do bloco (mesma esquerda e direita do
  conteúdo), 70 px de altura (90 px quando a linha quebra em três, em 375 px).
- **Botões dos gestos** ("Informar outro endereço", "Tirar o endereço desta entrega",
  "Desfazer"): 32 px de altura. É a altura `md` do kit (`--spacing-control: 2rem`), decisão
  do dono de 09/10/2026 para todos os apps, PDV e Cozinha inclusive; a trava
  `surfaces/operator-kit/tests/catalog.guardrails.test.ts` ("mantém campos e botões na
  altura md em todos os apps, sem opt-in de toque") recusa a volta dos 44 px.
- **Sem transbordo para o lado**: `overflowX` 0 em 375 e em 1366 px.
- **Nada coberto, cortado ou espremido**: `covered`, `clipped` e `crushed` falsos e
  `inside` verdadeiro em todos os textos medidos.

Visto à mão nas capturas, e anterior a este PR (está igual no `antes/`): em 375 px o X
do diálogo Recebimento encosta na palavra "definem" da frase de abertura, e o cartão
"Entrega" escolhido quase não se distingue do "Retirada" (muda só um tom do fundo).
