# #2825: escolhido o cadastro pelo teclado, o foco vai ao "Concluir"

Capturas do PDV de verdade (Django semeado e PDV compilado), com a Caixa (Fran) entrando
com PIN no posto que a Gerente vinculou, em 375 px (celular) e 1366 px (balcão). `antes/`
é o `main` (5b0664cdd); `depois/` é este PR. A jornada é a J12
(`surfaces/pos-nuxt/tests/e2e-live/j12-encomenda-pelo-teclado.live.spec.ts`).

## O roteiro, só com teclado

Na encomenda nova, o foco já está em "Identificar cliente" (#2824); Enter abre o diálogo
Cliente com o foco na busca. O telefone da Maria Santos, seta para baixo, Enter.

## O que acontecia, medido

O cadastro escolhido chegava (o selo "Cadastro existente", o formulário, os alertas) e o
foco ficava na busca. Até o "Concluir" eram 11 Tabs, pelo formulário inteiro: Remover
cliente, Favorito, Nome, WhatsApp, CPF/CNPJ, E-mail, CPF na nota, Nota por e-mail,
Restrições, Observações e, enfim, Concluir.

| | antes | depois |
|---|---|---|
| foco com o cadastro escolhido | a busca | "Concluir" |
| Tabs até o "Concluir" | **11** | **0** |
| foco à vista, `:focus-visible`, anel | (na busca) | sim, nas duas larguras |
| altura do alvo | 40 px | 40 px |
| o diálogo fecha sozinho | não | não: o operador confere e o Enter conclui |

Depois do Enter no "Concluir", o assistente segue para "Para quando?" com o foco no dia
(o comportamento do #2778, conferido na mesma jornada).

## As capturas

| Arquivo | O que mostra |
|---|---|
| `antes/<largura>/01-cadastro-escolhido.png` | o cadastro escolhido, o anel na busca |
| `depois/<largura>/01-cadastro-escolhido.png` | o cadastro escolhido, o anel no "Concluir" |

Fora da régua deste PR, igual no antes e no depois: a 375 px o corpo do diálogo Cliente
transborda 90 px à direita (a busca, o "Remover cliente", o selo de aniversário e os
campos aparecem cortados nas capturas de 375), #2885.

## A auditoria

`auditoria.txt`, por script, nas duas larguras: o elemento ativo, `:focus-visible`, o anel,
a altura e os Tabs até o "Concluir", com o caminho de cada Tab no antes. No fim, a sonda
do transbordo a 375 px.
