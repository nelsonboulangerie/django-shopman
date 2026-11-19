# #2778 + #2815: o assistente da encomenda sem mouse, com o cartão de rádio do Recebimento

Capturas do PDV de verdade (Django semeado e PDV compilado), com a Caixa (Fran) entrando
com PIN, em 375 px (celular) e 1366 px (balcão). `antes/` é o branch do #2814 (a base
deste PR); `depois/` é este PR. A cliente é a Maria Santos, a encomenda é para amanhã, a
partir das 9h.

## O roteiro (o "pronto quando" do #2778), só com teclado

F6 abre o cliente; telefone, seta e Enter escolhem a Maria (o "Concluir" do diálogo do
cliente fica a 11 Tabs, #2825). Daí em diante, dentro do assistente:

1. **Para quando?** O foco está no dia (Hoje). Seta para a direita, Amanhã; Enter escolhe.
   Um Tab chega ao primeiro horário; Enter escolhe.
2. **O foco vai para o Continuar** (a etapa não anda sozinha, como no E13). Enter.
3. **Entrega ou retirada?** O foco está na Retirada. Enter escolhe.
4. **O foco vai para "Montar encomenda".** Enter monta.

A volta pela Entrega confere o E13: seta para a Entrega, o endereço padrão do cliente em
foco; Voltar (este toque é de mouse, só para a captura 04), a Entrega marcada em foco na
etapa; seta para a Retirada, o foco de novo em "Montar encomenda"; Enter monta.

No depois, as sete paradas de foco do roteiro passaram nas duas larguras. No antes, quatro
falhavam: o foco chegava no bloco da etapa e não no dia, ficava no horário escolhido e não
no Continuar, ficava na Retirada e não em "Montar encomenda", e na volta caía na Retirada
em vez da Entrega marcada. E a seta não andava no grupo de dias (o `ref` repetido do
`OperatorDayPicker`, consertado neste PR): pelo teclado só dava para escolher Hoje.

## As capturas

| Arquivo | O que mostra |
|---|---|
| `01-foco-no-continuar` | escolhido o horário: no depois, o foco (o anel) no Continuar |
| `02-recebimento-sem-escolha` | a etapa "Entrega ou retirada?" ao chegar, com o foco na Retirada |
| `03-retirada-escolhida` | Retirada escolhida: no depois, o rádio cheio e o foco em "Montar encomenda" |
| `04-entrega-escolhida` | de volta à etapa com a Entrega escolhida |

As mais representativas: `antes/375/03-retirada-escolhida.png` contra
`depois/375/03-retirada-escolhida.png` (o sinal da escolha e o foco no botão que segue), e
`depois/1366/01-foco-no-continuar.png`.

## A auditoria

`auditoria.txt`, por script, nas dezesseis telas. No depois: transbordo lateral 0 em 375 e
1366; nenhum texto com contraste abaixo de 4,5, cortado, fora da tela ou coberto; contraste
mínimo de texto ativo 4,62:1 (o "Voltar"); letras só em 12, 14, 16 e 20 px; o foco sempre à
vista e com anel; os dois cartões com papel de rádio, `aria-checked`, a mesma altura (130 px
a 375, 90 px a 1366) e o mesmo topo; no escolhido, borda e miolo do rádio na cor da casa
(`rgb(139, 107, 46)`), no outro, borda clara e rádio vazio. No antes, o nome do escolhido
("Retirada" ou "Entrega", na cor da casa sobre o fundo tingido) media 4,35:1, abaixo do AA;
no depois o nome fica na tinta forte e a escolha se diz pelo rádio e pela borda.

Fora da régua deste PR, igual no antes e no depois: o dia escolhido do grupo de dias do kit
(Amanhã, 4,35:1, #2826) e o rodapé a 375 px, que quebra "Etapa 3 de 3" em três linhas (#2827).
