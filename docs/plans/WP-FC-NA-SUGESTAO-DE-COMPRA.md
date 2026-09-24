# WP — O fator de correção chega ao Compras, na hora de decidir quanto comprar

> Pedido dele em 24/09/2026, ao fechar a discussão do `usable_factor`:
> *"FC, derivado, pode ser útil para sugerir quantidade de compra, no app
> Compras."*

## O que existe hoje, e o que falta

`RecipeItem.usable_factor` guarda **quanto do insumo bruto sobra depois de
limpo**, em fração — cebola `0,84`, tomilho só folhas `0,60`, suco de limão
`0,40`. Ele entrou pela PR #1026 e virou fração na #1052.

`RecipeItem.correction_factor` já devolve o **inverso** (`1 ÷ 0,84 = 1,19`),
como property de leitura, para a tela falar a língua do chef sem ninguém
inverter de cabeça.

**O que falta é o gesto**: hoje o Compras sugere quanto comprar a partir do
consumo histórico e do mínimo cadastrado. Ele não sabe que, para a cozinha ter
10 kg de cebola **limpa**, a casa precisa comprar **11,9 kg**.

## Por que isto não é cosmético

A perda é declarada por ingrediente e **varia muito**: 16% na cebola, 40% no
tomilho desfolhado, **60% no suco de limão**. Uma sugestão de compra que ignora
o aproveitamento nasce curta na mesma proporção — e o sintoma aparece no meio do
preparo, quando já não há o que fazer.

⚠️ É o mesmo defeito que o `_validate_mass_balance` do Craftsman foi escrito
para pegar, um degrau acima: lá o sistema debitava menos insumo do que o padeiro
usava; aqui ele compraria menos do que a ficha pede.

## O desenho, e a regra que ele tem de respeitar

**A sugestão multiplica pelo FC; o estoque continua contando na base.** O número
que o Compras mostra é *quanto comprar*; o que desce do ledger na produção já é
a bruta, porque `gross_quantity` resolve isso desde a #1026. Os dois não se
somam — é o mesmo fator, lido em dois momentos.

**Onde o FC entra:** entre a necessidade líquida (o que as fichas do plano
pedem) e a quantidade a comprar. E só ali.

⚠️ **Um insumo pode ter aproveitamento diferente por ficha.** A cebola rende 84%
em pétala e outra coisa em brunoise; o `usable_factor` mora no `RecipeItem`, não
no `Material`, justamente por isso. A sugestão tem de **ponderar pelo consumo de
cada ficha**, não pegar o primeiro fator que achar.

⚠️ **A média de FCs é enviesada.** `média(1/r) ≠ 1/média(r)` — medido em
24/09 com rendimentos reais de 0,72 · 0,84 · 0,93: a média dos FCs dá 1,2182
contra 1,2048 do inverso da média, **1,11% a mais de compra**, sistematicamente.
Pondere e mediar **rendimentos**; inverta só no fim, uma vez.

## O que sai deste WP

- A sugestão de compra do `purchase-nuxt` passa a dizer **quanto comprar**, não
  quanto se consome, quando a ficha declara perda.
- A tela mostra o porquê: *"11,9 kg (10 kg limpos ÷ 84%)"* — a ADR-024 §R3 manda
  a aproximação carregar o `≈` até a tela, e aqui ela também explica a diferença.

## Fora de escopo

- Mudar `usable_factor` de lugar ou de formato. A decisão está fechada: o banco
  guarda o **rendimento**, com faixa `(0, 1]`, e o FC é derivado
  ([PR #1052](https://github.com/nelsonboulangerie/django-shopman/pull/1052)).
- O consumo na produção, que já usa a bruta.
- Calibrar os fatores — é o `calibrate_conversions`, da PR #1041.
