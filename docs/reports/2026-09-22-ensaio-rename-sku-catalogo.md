# Ensaio do rename de SKU do catálogo — 22/09/2026

> Frente: [`WP-CATALOGO-PUBLICAVEL.md`](../plans/WP-CATALOGO-PUBLICAVEL.md), fatia F1.
> Comando: `config/management/commands/apply_product_skus.py`.
> **Nada foi gravado no alpha.** O ensaio rodou contra uma **cópia** do banco
> vivo (`pg_dump` do pool do alpha para um Postgres local), e não contra ele:
> o ensaio executa e desfaz, e desfazer numa transação de 15 mil linhas
> seguraria trava no banco que serve a loja.

## O que o ensaio diz, em uma linha

**71 dos 86 códigos trocam, 36 itens de feed mudam de `g:id`, e 15 pares param**
— não por causa do rename, mas porque uma decisão de curadoria de 19/08
envelheceu quando o catálogo separou os produtos.

> Medido em 87 pares; o `GL` saiu depois, quando o dono disse que o pote mini
> não vai mais existir. Os números de linha abaixo são os da medição.

## Como rodar

```bash
python manage.py apply_product_skus              # ensaio: executa e desfaz
python manage.py apply_product_skus --apply      # grava
python manage.py apply_product_skus --sku CT     # um par só, pelo código de hoje
```

## A tabela

Vem da planilha
[Catálogo Nelson — consolidado](https://docs.google.com/spreadsheets/d/1wXoIxaYFiEn1hj2k2mEH0NrOP3b1-sTnbspakD_YhKA/edit),
abas `Proposta SKU da casa` e `Produtos`, na 2ª revisão do dono. Só entrou par
cujo código de hoje **existe** no catálogo vivo: os 33 produtos que a planilha
manda criar são outra fatia, e renomear o que não existe seria inventar.

| | |
|---|---|
| Pares na tabela | **87** — 72 da casa, 15 de revenda |
| Linhas da planilha que ficaram de fora | 33 (produto a criar) + 7 (código que fica como está) |
| Códigos do catálogo sem linha na planilha | **8**, com o motivo escrito no comando |

Os 8 sem linha: `BK` (bacon — a casa ainda não faz), `CV`, `CX`, `GR`, `LN`,
`QP`, `THL` (placeholders da despensa do Cardápio 2027) e `MT`, que é o código
da Mostarda e está numa ficha — esse é do
[`WP-INSUMOS-SEM-FRICCAO.md`](../plans/WP-INSUMOS-SEM-FRICCAO.md).

## As seis provas, medidas

### 1. Série do B.I. — **nenhum de-para a criar**

O `HistoricalSaleItem` guarda o SKU como o Yooga o escreveu, e isso não se
reescreve. Quem junta os dois anos de histórico ao presente é o `ProductAlias`,
pelo FK — então o rename passa despercebido pela série **desde que o de-para
exista**. Medido: os 67 produtos com série que seriam renomeados **já têm** o
seu. O comando cria o que faltar; aqui não faltou nenhum.

### 2. Endereço público — 36 itens de feed mudam de `g:id`

`/produto/<sku>` e o `id` do item no Merchant Center derivam do SKU. Dos 72
renomeados, **36 estão em coleção de feed** (`rusticos`, `finos`, `salgados`,
`doces`); os outros trocam só a URL da página de produto. Para o Google, id
novo é item novo: passa por revisão outra vez, e o antigo fica órfão até o feed
ser lido de novo. **Antes do go-live isso é barato; depois custa reindexação e
redirect.**

### 3. Tabelas de código — **NÃO são reescritas pelo comando**

| ocorrências | arquivo |
|---:|---|
| 671 | `config/management/commands/seed.py` |
| 72 | `config/management/commands/apply_product_brands.py` |
| 23 | `config/management/commands/rename_skus_to_real.py` |
| 10 | `shopman/backstage/management/commands/measure_eat_in_weights.py` |
| 8 | `shopman/shop/management/commands/apply_product_measurements.py` |
| 0 | `docs/plans/sku-real-mapa.csv` |

A contagem é de literal entre aspas, então inclui falso positivo de código
curto. **Isto é trabalho de commit, não de gravação de banco**, e está de fora
de propósito: reescrever 671 literais contra uma tabela que o dono ainda pode
editar é a definição de retrabalho. Quem cobra a travessia de verdade é a suíte.

### 4. Fichas do Craftsman — 468 linhas arrastadas

| linhas | campo |
|---:|---|
| 56 | `crafting.Recipe.output_sku` |
| 7 | `crafting.RecipeItem.input_sku` |
| 405 | `crafting.WorkOrder.output_sku` |

Entram no cascade por serem `RefField(ref_type="SKU")`. Ficha órfã não acontece.

### 5. Namespace compartilhado com o insumo — **zero colisão**

Nenhum código curado é hoje um `buyman.Material`, e nenhum é hoje um produto
diferente. A tabela também não disputa consigo mesma: nenhum alvo repetido e
nenhum alvo que seja o código de hoje de outra linha (isso obrigaria a renomear
em cadeia, e a ordem da tabela passaria a importar).

### 6. JSON fora do cascade — o que o rename não alcança

| linhas | onde | o que é |
|---:|---|---|
| 4.073 | `orderman.Directive.payload` | história |
| 323 | `orderman.SessionEvent.payload` | história |
| 214 | `orderman.Order.snapshot` | história |
| 41 | `orderman.IdempotencyKey.response_body` | história |
| 87 | `orderman.Order.data` | **vivo** |
| 14 | `orderman.Session.data` | **vivo** |
| 96 | `backstage.KDSTicket.items` | **vivo** |
| 253 | `stockman.Hold.metadata` | **vivo** |
| 9 | `shop.Announcement.content` | **vivo** |
| 22 | `customer_insights.CustomerInsight.favorite_products` | derivado |

História fica como está: payload de evento e snapshot são a foto do que
aconteceu, e reescrevê-los seria falsificar o registro. **Estado vivo pede
janela**: renomear com o balcão sem pedido aberto (no momento da medição o
alpha tinha 12 `preparing` e 3 `ready`), e conferir anúncio por publicar — há
**dois anúncios em `pending_review` com link para `/produto/BE`**, que vira
`BGGG`; publicados depois do rename, publicam um 404.

`shop.ProductAffinity` guarda SKU em coluna própria, fora do cascade
(2.867 pares). É derivada: `compute_product_affinity` a refaz.

## O que o ensaio achou e não estava no WP

### a) `ProductConsumptionTag.sku` é ÚNICO, e os dois códigos coexistem

O alpha guarda etiqueta de consumo tanto de `FE` quanto de `FENDU` — que é
justamente o alvo do rename, sobra do `propose_consumption_tags
--include-historical`, que etiquetou também os códigos do cardápio 2027. O
`update` do cascade estourava a constraint **no meio da travessia**. Só aparece
em banco com operação: teste unitário cria um lado de cada vez.

Resolvido reaproveitando a política por model do `rename_skus_to_real`: fundir a
anotação (a curada vence; no empate sobrevive a do produto renomeado), recusar a
entidade, e **parar o comando** se um campo de SKU único nascer sem política.
Uma fusão no alpha: `FE + FENDU`, e os dois dizem "Híbrido".

### b) 15 pares param: a série daquele código está creditada a outro produto ⚠️

Esta é a descoberta que **precisa da sua palavra**, e não é sobre o rename.

| código | o de-para credita a | a nota diz |
|---|---|---|
| `CHEGO_L50` `CHEGO_P50` `INTIMI_L50` `INTIMI_P50` `INTU_L70` `INTU_P50` `MAMA_L60` `MAMA_P50` `NAMAS_L60` `NAMAS_P50` `SOFIA_P50` `VITAL_P50` | `THL` — Chá da Casa (lata) | *"curadoria 19/08 (Pablo): chás Kãnfa lata/pouch = Chá da Casa (lata)"* |
| `BBB` — Brioche Burger Bun | `BBB2` — o pacote de 2 | *"curadoria 19/08 (sessão B.I.): mesmo produto"* |
| `PHO` — Pão para Hot Dog | `PHO4` — o pacote de 4 | *"curadoria 19/08 (sessão B.I.): mesmo produto"* |
| `CHAI_A` — Soft Chai Cítrico | produto nenhum | *"produto de outra época, sem equivalente no cardápio atual"* |

**A curadoria valia quando foi feita.** Em 19/08 o catálogo tinha um chá
genérico, e os 12 Kãnfa eram linha do Yooga sem produto. Hoje os 12 existem como
produto no alpha — e a venda deles continua sendo creditada ao placeholder.
`BBB` e `PHO` são o mesmo mecanismo ao contrário: o `rename_skus_to_real`
resolveu que o pacote é **bundle** sobre a unidade, e a unidade virou produto
próprio; o de-para ficou apontando para o pacote. São **10.849 linhas de venda
de `BBB` e 6.360 de `PHO`** creditadas ao pacote.

Renomear não pioraria nada — o de-para olha o FK, não o SKU. O que se perde é a
última chance barata de notar: depois do rename, o laço entre "o código antigo"
e "este produto" existe só na tabela do comando. Por isso cada par **para
sozinho**, com a nota de origem citada, e os outros 72 seguem.

**✅ Resolvido em 22/09, com a palavra dele ("faz").** Virou comando:
`config/management/commands/repoint_product_aliases.py`, ensaio por padrão e
`--apply`. Medido na cópia do alpha: **15 de-paras reapontados, 17.320 linhas de
venda voltando ao produto certo** — e, com eles corrigidos, o rename passa a
aceitar **os 86 pares**, não 71.

### c) O iFood: um mapa só, e uma cadeia que volta

`ifood_retract_renamed_skus` lia **só** o `rename_skus_to_real`. O id do item lá
é `uuid5(merchant, "item:" + sku)`, então esta leva deixa exatamente o mesmo
órfão — item vendável no cardápio deles apontando para um SKU que não existe
mais aqui — e **sem erro nenhum**, que é o pior formato de falha. Passou a ler
os dois mapas (neste PR).

Ao juntá-los apareceram duas coisas que o par cru esconde:

- **As levas se encadeiam.** `BAGUETE` virou `BF`, que vira `TRADI`. Quem
  olhasse o par cru não acharia `BAGUETE`, porque `BF` já não está no catálogo —
  e o item de agosto ficaria lá para sempre.
- **E uma delas volta.** `FENDU` virou `FE` em agosto; a curadoria de setembro
  devolve `FE` a `FENDU`. Resolver a cadeia no papel daria um **ciclo**, e
  qualquer desempate seria chute. Quem decide é o catálogo: a caminhada para no
  código que **existe hoje**. Assim `FE` sai e `FENDU` fica, sem ninguém
  escolher nada. É o único par nessa situação.

## Um terceiro código encurtou, e a razão está na própria tabela

`BE → BGGG` virou **`BE → BGG`** (dúvida dele em 23/09: *"e se BE virar somente
BG ou BGG?"*). O argumento não é de gosto: em toda a tabela **a base não carrega
letra de tamanho, só a variante** — `BRBB`/`BRBB2`, `FOB`/`FOBM`, `HOD`/`HODM`,
`FFGO`/`FFGOM`, `PIT`/`PIT4`. O `G` final de `BGGG` era "grande", um tamanho que
o resto da casa deixa implícito; com ele, a baguete padrão parecia a variante.

`BGG` e `BGGP` (a pequena) passam a dividir o começo, que é o que faz a família
aparecer junta na busca por teclado.

## As perguntas, respondidas em 22/09

1. ~~**Dois códigos da casa passam de 5 caracteres**~~ — **encurtados, aprovado
   por ele:** `MBBBG → BRBBM` (irmão de `BRBB` e `BRBB2`; o `BUBGMI` que a
   planilha propunha começava com `BU`, prefixo do *Butter* Burger Bun, e
   arquivava o brioche na família errada) e `MS → MELSA` (o pão dele é o
   melonpan, que virou `MELON`). *(`CROPQM` e `HOBBMI` têm o mesmo problema, mas
   são produtos a criar, fora desta fatia.)*
2. ~~**`GL → GELEIA-DAMASCO-STDALFOUR-28`**~~ — **respondido em 22/09.** O `GL`
   é placeholder de sabor indefinido, e existem **dois** minis St. Dalfour reais:
   damasco e frutas vermelhas, com GTINs distintos. **Rename não divide produto**
   — renomeá-lo para um dos dois declararia um sabor que ele nunca teve e
   esconderia o outro. O `GL` sai como exclusão, os dois minis entram como
   produto novo (fatia de criação, não de rename), e o par saiu da tabela com o
   motivo escrito em `FORA_DA_TABELA`.

## Quatro pares renomeiam algo que a planilha manda tirar

`ANP → PORQ` e `MS → MELICE` são "despublicar"; `CD → COAD` e `TI → TABUA` são
"excluir". Renomear antes de tirar não faz mal (e mantém a tabela completa), mas
se a ordem for outra — tirar primeiro — eles saem sozinhos do caminho.

## F2 e F3, medidos no mesmo banco

**F2 — fotos: o dono é o [`WP-FOTOS-DA-CASA.md`](../plans/WP-FOTOS-DA-CASA.md)**
(PR #975, do mesmo dia, já no `main`). Este ensaio só acrescenta dois fatos:
o acervo `pablondrina/nb-catalog` **não tem foto real de nenhum dos 59** — as 51
que servem já estão wiradas, e o que sobra lá é de outro produto, então não há
nada a "ligar"; e dos 13 em coleção de feed, **5 saem por curadoria** (`PG`,
`PU`, `TJ`, `TI` excluir, `MS` despublicar), sobrando **8**: `CCOM`, `CMA`,
`CMO`, `JB`, `PPU`, `PI`, `PI4`, `QQ`.

**F3 — descrições.** O WP dizia "42 publicados sem descrição longa". Medido:
**`long_description` está vazia nos 111** — o campo nunca foi usado. E a PDP já
mostra a curta, os ingredientes com alérgenos, a conservação e a tabela
nutricional. A longa só rende um segundo parágrafo, e só vale se disser o que os
outros campos não dizem. Isso é conhecimento da casa: a pergunta foi para a
planilha em vez de virar prosa minha.

**A planilha foi atualizada** (mesma URL): aba `Pendências 22-09` com as
decisões — uma coluna amarela por linha, já com o valor de hoje dentro — e 8
linhas novas no fim de `Produtos` para os produtos do alpha que nunca tiveram
uma.

## Ordem de execução, quando você der a palavra

```bash
python manage.py apply_product_skus --apply      # 1. troca os códigos
python manage.py ifood_retract_renamed_skus      # 2. o item antigo segue vendável no iFood
python manage.py sync_catalog_ifood --full       # 3. publica os códigos novos
python manage.py compute_product_affinity        # 4. a afinidade guarda SKU e é derivada
```

E **antes de gravar num banco que já roda**, as tabelas de código (seção 3)
precisam ter virado commit, senão o próximo `seed` nasce discordando do alpha.
