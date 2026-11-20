# #2854: Retirada e Entrega no celular

Capturas do PDV de verdade (Django semeado e PDV compilado, banco local), com a Caixa
(Fran) operando depois de a Gerente vincular o posto, a 375 px (celular, toque) e 1280 px
(balcão). `antes/` é o `main`; `depois/` é este PR. A cliente é a Maria Santos, a
encomenda é para amanhã, e a Retirada está escolhida.

| Arquivo | O que mostra |
|---|---|
| `01-assistente-retirada-escolhida` | etapa "Entrega ou retirada?" do assistente da encomenda |
| `02-recebimento-retirada-escolhida` | o diálogo Recebimento, na venda montada |

A mais representativa: `antes/375/01-assistente-retirada-escolhida.png` contra
`depois/375/01-assistente-retirada-escolhida.png`.

## A auditoria (`auditoria.txt`)

| Tela | Largura | Contêiner | Disposição | Linhas da descrição (Retirada / Entrega) | Altura dos cartões |
|---|---|---|---|---|---|
| Assistente | 375, antes | 285 px | lado a lado | 3 / 4 | 130 / 130 |
| Assistente | 375, depois | 285 px | empilhados | 1 / 2 | 70 / 90 |
| Recebimento | 375, antes | 311 px | lado a lado | 2 / 3 | 110 / 110 |
| Recebimento | 375, depois | 311 px | empilhados | 1 / 1 | 70 / 70 |
| Assistente | 1280, antes e depois | 574 px | lado a lado | 1 / 2 | 90 / 90 |
| Recebimento | 1280, antes e depois | 464 px | lado a lado | 1 / 2 | 90 / 90 |

A 1280 px as caixas dos cartões têm as mesmas coordenadas no antes e no depois: o
contêiner mais estreito do balcão (o diálogo, 464 px) fica acima do limiar de 448 px
(`@md`), e os cartões seguem lado a lado.

Nos quatro casos do depois: empilhados com as mesmas bordas (diferença 0 px à esquerda e
à direita, 8 px entre um e outro), nada fora da tela, transbordo lateral 0, a ordem de
leitura Retirada e depois Entrega, cada cartão com pelo menos 44 px de alvo (o menor tem
70 px de altura). Contraste: rótulo de 11,29:1 a 13,67:1, descrição de 5,38:1 a 6,52:1.
Nenhum aviso na tela durante as capturas.
