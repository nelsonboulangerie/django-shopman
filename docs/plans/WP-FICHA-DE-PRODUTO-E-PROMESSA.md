# WP-FICHA-DE-PRODUTO-E-PROMESSA — a ficha por unidade, e nada que o cliente lê fica velho

> Aberto em 2026-09-05, do dono, na conversa do inventário de receitas.
> Aprovação para executar: *"pode seguir! autonomamente, até concluir!"*
>
> ⛔ **Fora deste WP, por ordem dele:** a linguagem de passos e a notação de panificação.
> Ele tem uma notação própria e pediu para **discutir antes**. Ver
> `project_linguagem_de_passos_da_receita` na memória.

## O fio que costura tudo

> *"nutricional e tudo o mais que apareça no catálogo mas seja relativo ou derivado da
> receita do produto deve ter uma relação estabelecida, para manter tudo sempre atualizado
> e sem falsa promessa para o cliente."*

Hoje o catálogo deriva três coisas da receita (nutrição, alérgenos, ingredientes) e **não
guarda de qual versão elas vieram**. Publicou uma versão nova, os números do PDP
continuam lá, com cara de atuais. O peso da peça nem derivado é: é digitado à mão, com uma
perda de forno de ~12% que o próprio código admite nunca ter passado pela balança
(`apply_product_measurements.py`: *"a conferir na balança com a peça pronta"*).

## A · A ficha de produto passa a ser por unidade

Achado do dono: a ficha da baguete diz "7 kg de Massa Tradição rende 25 un". O 25 não é
propriedade da baguete, é a decisão de quanto se fez naquele dia. **A ficha do produto
mostra o que entra em UMA peça.**

A régua é o que a ficha rende, medido no seed: **42 fichas rendem unidade** (produto) e
**25 rendem massa** (fórmula). Por unidade, os números saem redondos: baguete 280 g,
bâtard 320 g, animalzinho 60 g de brioche mais 40 g de creme.

- `batch_size` das 42 vira `1 un`; as quantidades dos itens são divididas pelo rendimento
  antigo. É **reexpressão**, a razão não muda, então o consumo por fornada é idêntico.
- O bootstrap **para de fabricar fórmula para peça**: parte é fração, e a 100% não é
  parte, é o insumo. A baguete deixa de exibir a composição da massa como se fosse dela.
- A lente de padaria some das peças: elas não têm farinha própria, têm processo.
- Ganho de graça: **o peso cru da peça passa a existir** (280 g), que é o insumo do bloco B.

## B · Capacidade deixa de ser `3 × rendimento`

`capacity_per_day = int(batch_size * 3)` no seed é conta arbitrária, e **quebra agora**:
com `batch_size = 1` viraria 3, e o painel passaria a achar que a casa faz três baguetes
por dia.

⚠️ **Não inventar política nova aqui.** São dois números que hoje estão conflados, e a
decisão de ambos é do dono:
- **teto físico** — o que o forno permite. Fato de equipamento (a casa tem UM forno), e
  não existe cadastro disso hoje;
- **capacidade praticada** — o que a casa entrega. O B.I. mede, mas só enxerga o que foi
  TENTADO: se nunca se fez 200 baguetes, ele não sabe se cabem.

**Nesta rodada:** preservar o número absoluto de hoje, escrito explicitamente por ficha,
com comentário dizendo que é provisório e qual é a política que falta. O número não muda;
o que muda é ele parar de ser uma multiplicação fingindo ser política.

## C · A relação derivada: nada do catálogo fica velho em silêncio

Tudo que o catálogo mostra e vem da receita passa a carregar **de qual versão veio**.

- Ao derivar, carimbar a versão de origem (`Recipe.meta["version_ref"]`, que já existe).
- **Vencido é comparação exata, não heurística:** versão atual diferente da versão de
  origem. Sem limiar inventado.
- Override manual continua sagrado (a casa já tem `nutrition_facts["auto_filled"]` e
  `metadata["dietary_auto_filled"]`): não se recalcula, **mas passa a ser marcado como
  vencido** quando a receita anda, com autor e data, para alguém reconferir.
- Vale para nutrição, alérgenos e ingredientes, que já são derivados, e para o **peso**,
  que passa a ser.

## D · O peso anunciado é PISO, nunca média

> *"o cliente se importa mais se está pagando o preço por menos do que o mostrado, nunca
> por mais... esse pão nunca sai menor que 90 g... calcularíamos para que o pão assado mire
> uns 96 g."*

`Product.unit_weight_g` deixa de ser estimativa e vira **compromisso pelo lado de baixo**:
```
assado esperado = cru por unidade × (1 − perda de forno)
anunciado       = arredonda PARA BAIXO (assado esperado × (1 − folga))
```
A perda de forno passa a ser declarada por ficha (`Recipe.meta`), com o padrão de 12% da
casa **marcado como estimativa não auditada**. Peso posto à mão não é sobrescrito; ele
ganha o aviso de divergência.

⚠️ **Amarra com o bloco E:** se o anunciado é piso, a régua da bancada tem de ser "nunca
abaixo do alvo". É a mesma decisão, vista dos dois lados.

## E · Margem de rendimento: meia divisão por peça

Balança da casa: **2 g**, e tem de ser configurável.

Com a régua "nunca abaixo do alvo", cada peça cai em `[W, W+d)` e o excesso esperado é
**`d/2`, não `d`**. Pâton de 60 g em balança de 2 g consome 61 g em média. Em 100 pâtons,
supor `d` joga fora 100 g de massa por fornada.

**Duas perdas, duas formas** (é por isso que uma porcentagem única erra as duas):
```
massa a fazer = N × peso da peça
              + N × d/2                arredondamento: escala com o NÚMERO de peças
              + perda da masseira      filme na bacia: ~fixa por fornada
              + colchão ≈ 3·d·√(N/12)  variância, que encolhe em proporção quando N cresce
```
A soma de N arredondamentos tem desvio `d·√(N/12)`: em 25 peças, ~2,9 g. **A peça isolada
é incerta, a fornada não é** — então a margem se orça na fornada, nunca por peça.

A perda da masseira **não se chuta**: o ledger já sabe produzido menos consumido, então o
sistema pode aprender a perda real por ficha. Nesta rodada ela é declarada com padrão
conservador e o aprendizado fica anotado como próximo passo.

E o que sobrar **não é perda, é massa velha de amanhã**, que já é modelada como teto. O
alvo não é sobra zero: é sobra que caiba no teto do dia seguinte.

## F · Auditar pesos (a função que ele pediu)

> *"poderia acusar se aquele número foi auditado por um operador humano (poderia até
> mostrar por quem, quando, etc.)"*

Tela no app de **Produção**, e o momento natural é o fechamento da fornada, quando o
operador já está com a peça pronta na mão. Registra o peso medido, quem mediu, quando, e
**sobre qual versão da receita** — é isso que torna a defasagem exata.

## Ordem

`A` e `B` juntos (a capacidade quebra com a ficha por unidade). `C`, `D` e `E` em paralelo
com eles. `F` depois de `C`, porque consome o que ele expõe.
