# #2894: o selo de aniversário do diálogo Cliente, legível e sem "HOJE"

Capturas do PDV de verdade (Django semeado em banco local próprio, `shopman_pdv_2885`, e
PDV compilado), com a Caixa (Fran) entrando com PIN no posto que a Gerente vinculou, em
375 px (celular) e 1366 px (balcão). Encomenda nova, "Identificar cliente", o telefone
43991111111 e o cadastro da Maria Santos, aniversariante hoje, com a promoção
"Parabéns! Desconto de aniversário". `antes/` é a base deste PR (o head do #2896,
`c64c306d7`); `depois/` é este PR.

## O que mudou

| | antes | depois |
|---|---|---|
| token do texto | `--primary` (`text-primary`, latão puro) | `--primary-ink` (`text-(--primary-ink)`, a tinta do latão) |
| cor do texto, medida | `#8b6b2e` | `#7f612c` |
| fundo efetivo, medido | `#eee9e0` | `#eee9e0` (não muda) |
| contraste, 375 | **4,09:1** (reprova) | **4,75:1** |
| contraste, 1366 | **4,09:1** (reprova) | **4,75:1** |
| texto | 🎂 Aniversário HOJE · Parabéns! Desconto de aniversário | 🎂 Aniversário hoje · Parabéns! Desconto de aniversário |
| caixa a 375 | 277 x 38 px, 2 linhas | 277 x 38 px, 2 linhas |
| caixa a 1366 | 330 x 22 px, 1 linha | 324 x 22 px, 1 linha ("hoje" é mais estreito que "HOJE") |

A tinta `--primary-ink` é a que o operator-kit já declara para latão como texto sobre o
próprio latão a 10% (`operator-theme.css`: 85% de latão e 15% do texto no claro; no
escuro, o próprio latão claro). Nenhum token do kit mudou. Fundo e borda do selo ficam.

O fundo do selo é latão a 10% sobre o cartão do cadastro, que já é latão a 5%: por isso o
latão puro media 4,09, e não os 4,35 do Badge `soft` num fundo branco.

## A auditoria

`auditoria.txt`, por script, nas duas larguras: a linha `SELO` traz a cor do texto, o fundo
efetivo (compondo as camadas translúcidas), a razão de contraste, a borda, a caixa, as
linhas, se passa da borda direita do diálogo e se está cortado; depois, cada texto, botão e
campo do diálogo com posição e contraste; no fim, o alinhamento do selo com os blocos do
cartão. Antes: 1 problema (o contraste do selo) nas duas larguras. Depois: nenhum.

Nada passa da borda direita, nada cortado, o selo começa na mesma coluna dos blocos do
cartão (49 px a 375, 468 px a 1366), o corpo sem transbordo (343/343 e 512/512).

Diálogo sem aviso de tela: não há aviso a conferir abaixo das barras nem botão que o
resolva.

## As capturas

| Arquivo | O que mostra |
|---|---|
| `<antes ou depois>/<largura>/01-cadastro-escolhido.png` | o diálogo com o cadastro escolhido |
| `<antes ou depois>/<largura>/02-selo-aniversario.png` | o recorte do selo |
| `<antes ou depois>/<largura>/auditoria.txt` | a medida por script |
