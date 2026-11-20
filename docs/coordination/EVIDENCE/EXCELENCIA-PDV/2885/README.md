# #2885: o diálogo Cliente cabe no celular

Capturas do PDV de verdade (Django semeado em banco local próprio, PDV compilado), com a
Caixa (Fran) entrando com PIN no posto que a Gerente vinculou, em 375 px (celular) e
1366 px (balcão). A jornada é a da J12: encomenda nova, "Identificar cliente", o telefone
43991111111 na busca, e o cadastro da Maria Santos escolhido. `antes/` é a base deste PR
(o head do #2886, que é o `main` mais o foco no "Concluir"); `depois/` é este PR.

## O que acontecia, medido

A 375 px o diálogo tem 343 px (16 a 359), e o corpo (`data-slot=body`) tinha
`scrollWidth` 433 para `clientWidth` 343: 90 px de transbordo. A busca, o "Remover
cliente", o selo de aniversário, os campos e os padrões passavam da borda direita.

A causa: a linha do cabeçalho do cartão do cadastro (o selo "Cadastro existente · Maria
Santos", que não quebrava, e o "Remover cliente" ao lado) pedia 383 px. O cartão é item
de uma grade de uma coluna `auto`, e coluna `auto` não fica menor que o conteúdo mínimo
dos itens: o cartão, a busca e o diálogo inteiro cresceram para 417 px de conteúdo, num
corpo de 311.

A mesma causa aparece no balcão quando o cadastro tem contato longo. A trava de geometria
nova (`tests/geometry/customerModal.spec.ts`, mock com telefone, CPF e e-mail de 35
caracteres) mediu na base, a 1366 px, `scrollWidth` 636 para `clientWidth` 512: a linha de
contato corta com reticências (`truncate`), e texto que corta conta a frase inteira como
conteúdo mínimo da coluna `auto`. A Maria do banco semeado não tem CPF nem e-mail, por
isso a auditoria ao vivo de 1366 não pega esse caso.

## O que mudou

- As grades do corpo e do cartão ganham uma coluna `minmax(0, 1fr)` (`grid-cols-1`) no
  lugar da coluna `auto` implícita: a coluna fica na largura do diálogo e nenhum conteúdo
  a empurra para fora. Quando tudo cabe, as duas desenham igual.
- O cartão mede a si mesmo (`@container`). Estreito (menos de 24rem de cartão), o
  "Remover cliente" desce para baixo do selo e o selo quebra linha em vez de cortar o
  nome. Largo, a linha de sempre.
- A linha de contato (telefone, CPF, e-mail) quebra no estreito em vez de cortar o e-mail.
- O selo de aniversário, que no estreito ocupa duas linhas, troca o `rounded-full` por
  `rounded-2xl`: numa linha só os dois desenham igual (o raio é limitado pela metade da
  altura); em duas, a cápsula vira um cartão arredondado.
- O convite da busca vai pela largura do campo, como o da busca de produtos (PDV-16, beta de 05/11):
  abaixo de 360 px de campo, "Nome, telefone, CPF ou e-mail"; acima, a frase inteira de
  sempre. Com o transbordo resolvido o campo passou a ter 311 px, e a frase longa saía
  cortada nele.

| | antes 375 | depois 375 | antes 1366 | depois 1366 |
|---|---|---|---|---|
| corpo: `scrollWidth` / `clientWidth` | 433 / 343 | 343 / 343 | 512 / 512 | 512 / 512 |
| elementos passando da borda direita | 20 | 0 | 0 | 0 |
| selo "Cadastro existente · Maria Santos" | cortado (202 px) | inteiro (248 px) | inteiro | inteiro |
| convite da busca | passava da borda | cabe no campo | cabe | cabe (o mesmo) |
| alinhamento dos blocos do cartão | 49..432 | 49..326 | 468..898 | 468..898 |

## 1366 não mudou

As duas auditorias de 1366 (`antes/1366/auditoria.txt` e `depois/1366/auditoria.txt`)
são idênticas linha a linha: mesma posição, largura, altura e contraste de todos os
elementos. Na comparação por pixel das capturas, a região do diálogo é idêntica (diferença
zero em todos os pixels); o que difere é só a tela atrás do véu.

## As capturas

| Arquivo | O que mostra |
|---|---|
| `<antes ou depois>/<largura>/01-cadastro-escolhido.png` | o diálogo com o cadastro escolhido, do topo |
| `<antes ou depois>/<largura>/02-cadastro-escolhido-fim.png` | o mesmo, com o corpo rolado até o fim |
| `<antes ou depois>/<largura>/auditoria.txt` | a medida por script de cada elemento à vista |

## A auditoria

`auditoria.txt`, por script, nas duas larguras e nas duas posições de rolagem: o
transbordo do corpo; para cada texto, botão e campo, a esquerda, a direita, a largura, a
altura e o contraste (cor do texto contra o fundo efetivo, compondo as camadas
translúcidas), com as marcas `PASSA-DA-DIREITA`, `CORTADO`, `RETICENCIAS`,
`TEXTO-DO-CAMPO-CORTADO` (o valor ou o convite do campo, medido pela fonte do campo) e
`CONTRASTE<4.5`; no fim, o alinhamento dos blocos do cartão e da busca com o cartão.

Diálogo sem aviso de tela: não há aviso a conferir abaixo das barras nem botão que o
resolva.

Fora da régua deste PR, igual no antes e no depois e nas duas larguras: o selo
"🎂 Aniversário HOJE" tem contraste 4,09 (texto `text-primary` de 12 px sobre
`bg-primary/10`), abaixo de 4,5. Registrado na #2894.
