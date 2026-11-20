# #2824: a encomenda nova abre com o foco em "Identificar cliente"

Capturas do PDV de verdade (Django semeado e PDV compilado), com a Caixa (Fran) entrando
com PIN no posto que a Gerente vinculou, em 375 px (celular) e 1366 px (balcão). `antes/`
é o `main` (5b0664cdd); `depois/` é este PR. A jornada é a J12
(`surfaces/pos-nuxt/tests/e2e-live/j12-encomenda-pelo-teclado.live.spec.ts`).

## O roteiro

Encomendas, "Nova encomenda". No diálogo "Iniciar nova encomenda?" o foco nasce em
"Voltar sem iniciar"; um Tab vai a "Iniciar encomenda" e o Enter confirma. A encomenda
abre na etapa do cliente.

## O que acontecia, medido

O diálogo, ao fechar, devolve o foco a quem o tinha quando abriu. Na chegada pelas
Encomendas, era a busca do quadro de comandas ("Mesa, nome ou referência"). A encomenda
abria, o quadro saía da tela, e o foco morria no `body`. Ninguém levava o foco ao
assistente.

| | antes | depois |
|---|---|---|
| foco logo depois do diálogo | a busca do quadro, que sai da tela | ninguém (o diálogo não devolve) |
| foco com a encomenda aberta | `body` | "Identificar cliente" |
| Tabs até "Identificar cliente" | 2 (a trilha "1. Cliente", depois o gesto) | **0** |
| foco à vista, com anel (`:focus-visible`, contorno de 3 px) | não há foco | sim, nas duas larguras |
| altura do alvo | 32 px | 32 px |

A altura de 32 px é a dos controles da casa (`--spacing-control`, decisão do dono de
09/10/2026), não os 44 px do alvo de toque do rail. Este PR não muda tamanho de botão.

## As capturas

| Arquivo | O que mostra |
|---|---|
| `antes/<largura>/01-encomenda-aberta.png` | a encomenda aberta, nenhum anel de foco na tela |
| `depois/<largura>/01-encomenda-aberta.png` | a encomenda aberta, o anel em "Identificar cliente" |

## A auditoria

`auditoria.txt`, por script, nas duas larguras: o elemento ativo em cada passo, se ele
casa com `:focus-visible`, o contorno e a altura, e os Tabs até o alvo.
