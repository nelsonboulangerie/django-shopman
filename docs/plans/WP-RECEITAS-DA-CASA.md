# WP — As receitas da casa, conferidas por quem faz o pão

> Pedido do dono em 22/09/2026: *"quero que lance um WP exclusivo e dedicado
> para organizarmos as receitas. ver o que já tem sugerido, eu corrijo, ou
> envio imagens com as receitas originais"*.

## Por que agora, com nome e sobrenome

No mesmo dia, revisando SKU por família de massa, ele achou **seis fichas com
a massa errada** — e as seis vinham de inferência de agente, não do padeiro:

| Peça | A ficha dizia | É |
|---|---|---|
| Pain aux Raisins | croissant | **brioche** |
| Baguete Gergelim Pequena | tradição | **ciabatta** |
| Baguete Lanche | tradição | **ciabatta** |
| Coelhinho, Ursinho, Porquinho | brioche | **butter** |

Ficha errada não é rótulo errado. É o que a Produção consome, o que o custo
calcula e o que a etiqueta de alérgeno deriva. O pão sai igual na vitrine e a
conta sai errada no fim do mês — **erro silencioso, que é a pior espécie**.

E a amostra foi pequena: ele olhou as massas porque estávamos falando de SKU.
Ninguém olhou quantidade, rendimento, passo ou tempo.

## O que existe hoje, medido no alpha (22/09)

| | |
|---|---|
| Fichas cadastradas | **92**, sendo 69 ativas |
| Inventário versionado (`RecipeEntry` / `RecipeVersion`) | **70** registros |
| Produtos publicados **sem** ficha ativa | **32** |
| Porta "Anotação" e porta "Foto" (`recipe_capture`) | **já implementadas** — o padeiro cola texto ou fotografa o caderno e recebe rascunho estruturado |
| Tela de receitas | app de Produção, rotas `/recipes` (`RECIPE-INVENTORY-PLAN §8`) |

Ou seja: **a máquina existe**. O que falta é a passada humana — e um jeito de
saber, olhando, o que já foi conferido e o que ainda é chute.

## O buraco que este WP fecha

Hoje uma ficha não diz **de onde veio**. Uma receita digitada pelo padeiro e
uma inventada por um agente têm exatamente a mesma cara na tela. Por isso as
seis erradas passaram: ninguém tinha como saber que precisavam de conferência.

**F1 — procedência e estado de conferência.** Cada ficha carrega quem a
declarou (padeiro, foto do caderno, agente) e se foi conferida, por quem e
quando. A tela mostra, e a lista filtra por "ainda não conferida". Sem isso,
todo o resto é trabalho que se perde na próxima dúvida.

**F2 — a passada do padeiro, ficha por ficha.** Fila ordenada pelo que mais
sai (o B.I. já sabe), com a massa em destaque, porque foi ali que errou. Ele
confirma ou corrige; cada confirmação vira procedência "conferida por ele".

**F3 — as 32 sem ficha.** Cada produto publicado sem receita é um custo que
ninguém calcula e um alérgeno que ninguém deriva. A porta "Foto" existe para
isto: ele fotografa o caderno e revisa o rascunho.

**F4 — o que a ficha tem de responder além dos ingredientes.** Rendimento
real, perda de forno, tempo e ordem dos passos — o que a Produção precisa para
planejar, e o que hoje está preenchido por estimativa em boa parte das fichas.

## Travas que já existem e ficam

- `shopman/backstage/tests/test_massa_de_cada_peca.py` — trava a massa de cada
  peça conferida com ele; nasceu destas seis correções.
- Alérgeno derivado da ficha (WP anterior): ficha errada vira rótulo errado, e
  a casa só afirma o que honra.

## O que este WP **não** é

Não é reescrever o editor de receitas, que já funciona. Não é automatizar a
conferência: o objetivo é exatamente o contrário — deixar visível o que só uma
pessoa pode responder, e parar de tratar palpite de máquina como fato.
