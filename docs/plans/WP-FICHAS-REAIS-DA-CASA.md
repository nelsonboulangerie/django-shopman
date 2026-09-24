# WP — As fichas reais da casa, e o fator de correção que elas exigem

> Decisão dele em 23/09/2026: *"as receitas da casa são estas da planilha.
> esqueça as que você tinha usado como rascunho, ok."*

A planilha é a **Ficha Técnica - Maysa** (Drive dele, `1xVzeJYB…U5paI`), com
datas de 2017 a 2023. As fichas que o `seed` carrega hoje são rascunho, e param
de valer.

⚠️ **A service account do cofre não a enxerga** — só as duas planilhas já
compartilhadas com ela. Quem a lê é o conector do Drive dele.

## Por que o fator de correção vem ANTES

Toda ficha dela traz três colunas por ingrediente, e não duas:

| | cebola | tomilho (só folhas) | suco de limão |
|---|---:|---:|---:|
| **Qtde Líquida** — o que entra no produto | 0,200 kg | 0,002 kg | 0,056 kg |
| **Rend. %** — o fator de correção | 84% | 60% | 40% |
| **Qtde Bruta** — o que sai do estoque | 0,238 kg | 0,003 kg | 0,140 kg |

O `RecipeItem` tem **uma** quantidade. Importar a ficha real obriga, hoje, a
escolher uma das duas colunas e jogar a outra fora — e **as duas respondem
perguntas diferentes que o sistema já faz**:

- **quanto sai do estoque** é a bruta: paga-se pela casca da cebola, e é ela que
  o `craftsman/contrib/stockman` consome ao fechar a fornada;
- **quanto vai no produto** é a líquida: é dela que saem o rótulo nutricional, a
  derivação de alérgeno e a massa da peça.

Gravar só a bruta faz o rótulo contar casca. Gravar só a líquida faz o estoque
descer menos do que a realidade e o custo nascer subestimado. **Por isso este WP
não começa importando: começa dando lugar ao terceiro número.**

## F1 — O fator de correção, e a forma que ele toma

**A decisão de desenho, e a razão dela.** `quantity` passa a ser explicitamente a
**líquida**, e o fator de correção entra como campo próprio; **a bruta é sempre
derivada**, nunca gravada.

A ordem inversa (gravar a bruta e derivar a líquida) parece equivalente e não é:

1. **Fator ausente = 100% torna a migração um no-op.** Com a líquida em
   `quantity`, toda ficha que existe hoje continua significando exatamente o que
   significa, sem tocar em nenhum número.
2. **O rótulo não se move.** A validação de rendimento (`Recipe.clean`, que já
   compara `batch_size` com a soma dos insumos), o cálculo nutricional e a
   derivação de alérgeno leem `quantity` e continuam certos sem uma linha de
   mudança. Se `quantity` virasse a bruta, o rótulo passaria a contar casca **no
   instante do import**, calado — e a casa tem trava explícita sobre afirmar o
   que não honra.
3. **Só dois caminhos passam a dividir pelo fator**: o consumo de estoque e o
   custo. Dois, não vinte.

**Campo, não `meta`.** O `RecipeItem.meta` já guarda `density_g_per_ml`, então há
precedente de dado estrutural no JSON — mas a densidade é lida num lugar só
(`_item_mass_in_kg`) e **falha graciosamente**, devolvendo `None` quando não dá
para saber. O fator de correção é lido no caminho que **consome estoque**: se
vier ausente ou corrompido, o saldo desce errado em silêncio, que é o defeito
mais caro deste repositório. Isso pede coluna com default e `CheckConstraint`
(`0 < fator <= 1`), e pede poder perguntar ao banco quais fichas declaram perda.
É a "necessidade comprovada" que o `CLAUDE.md` exige para tocar o Core.

**E ele carrega o `≈`.** Fator de correção é equivalência física com incerteza —
a cebola de hoje não rende igual à de ontem —, exatamente o tipo 3 da
[ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md), cuja R3 manda
o número carregar o carimbo até a tela. A lista de separação diz *"0,238 kg
(≈ 0,200 limpos)"*, não um número que parece exato.

**Fora do escopo do F1:** a massa de pão não tem fator de correção (farinha não
tem casca), então a lente de padaria e o `contrib/formula` não mudam.

## F2 — Importar as fichas reais

Só depois do F1. As divergências medidas em 23/09, comparando a planilha dela com
o que o `seed` carrega hoje:

| ficha | o que a real tem e a nossa não |
|---|---|
| **Jambon Beurre** | pão errado — a nossa usa `TRADI`, e ele confirmou em 23/09: **é a Baguete Lanche (`BGL`), massa ciabatta**. Faltam **manteiga de wassabi** e **pepino cornichon** |
| **Molho Bechamel** | vinho branco, tomilho, alecrim, louro, nata e parmesão — seis. O da casa é infusionado e finalizado com queijo |
| **Vinagrete da boulan** | é outra receita: cebola branca, vinagre de vinho tinto, óleo de girassol e pimenta. A nossa tem açúcar e limão, que não estão na dela |
| **Cebola Bacon Tomilho** | sal, queijo colonial, pimenta e louro. E o bacon é 11% do recheio na dela, 33% na nossa |
| **Recheio Citron** | leite, amido de milho, farinha; e o limão é **dois** (tahiti e siciliano) |
| **Recheio de frango** | caldo, tomate, colorau, farinha e milho |
| **Salada da casa** | alface crespa (a nossa usa americana), tomate pera (a nossa, cereja) e o vinagrete junto |
| **Queijo quente** | cebolas assadas; e o acabamento é queijo terreiro, não parmesão |
| **Croque / Tartine** | pão campagne fatiado fino (a nossa usa forma) e parmesão na cobertura. O gouda no lugar do gruyère, que ele já corrigiu na aba, **a ficha real confirma** |
| **Pain Perdu** | caramelo, chantilly e flor de sal |
| **Creme de chocolate** | **dois** chocolates: 40% cacau e ao leite |
| **Tapenade** | cranberry no vinho, pimenta e tomilho |
| **Presunto cozido** | **não existe ficha nenhuma** no sistema — `PRESUNTO-CASA` é só um insumo "produção própria". A real tem pernil, salmoura, 72 h de marinada e 6 h de forno |

E **dez preparos sem ficha nossa**: cebolas assadas, manteiga de mel, de bacon e
de alho, caramelo, creme de caramelo, cranberry no vinho, geleia de morango,
ratatouille e salmoura.

**24 insumos de compra** que essas fichas usam e a lista não tinha já entraram na
aba `Insumos` da planilha viva (pernil, sal de cura, amido, cravo, zimbro, louro,
mel, pólen, os quatro da ratatouille, …).

### Estado do F2 (24/09/2026)

**Importadas** (fatia A, molhos e recheios): bechamel, vinagrete, recheio cebola
bacon tomilho, recheio citron (`creme-limao`), recheio de frango, creme de
chocolate e salada. **Fatia B, montagens:** Jambon-Beurre, queijo quente, os três
croques e o pain perdu, com os pré-preparos que eles pedem (manteiga de wasabi,
cebolas assadas, caramelo salgado e o creme do pain perdu). O «Rend. %» entra
como aproveitamento da linha, e as validades da ficha dela substituem o exemplo
genérico. A revisão assinada no Admin continua obrigatória.

**Decisões de leitura** (cada uma está escrita no comentário da ficha):

- **A quantidade por peça fica com a balança dele, não com a ficha de 2017.** A
  focaccia grande recebe 80 g de recheio (`PESO_MASSA_CRUA_G`, 26/08). A ficha
  dela punha ~310 g. Da ficha entra a proporção.
- **A salada ganhou o vinagrete**, na proporção da guarnição dela (30 g em 80 g).
  Por isso o vinagrete saiu dos croques como linha própria.
- **Abaixo de 1 g fica fora**: a folha de louro do frango (0,34 g) e a baunilha em
  gotas do creme do pain perdu. A ficha grava em quilo com três casas.

**Ficam de fora, com o motivo:**

- **Presunto cozido.** A ficha é clara, mas a salmoura (3,65 kg, com 0,43 kg de
  sal) é **descartada** depois das 72 h. A derivação nutricional contaria todo esse
  sal no produto, e o rótulo do croque e do Jambon-Beurre passaria a mentir para
  cima em sódio. Falta um número que ninguém tem: quanto da salmoura fica na peça.
  Até ele existir, o `PRESUNTO-CASA` segue como insumo de produção própria, com o
  perfil de hoje. (A sessão de insumos já concordou que ele deixe de ser
  `Material` quando a ficha entrar.)
- **Tapenade (`TPND`) e cranberry no vinho.** A ficha do cranberry não diz quanto
  rende depois de reduzido, e sem isso a tapenade não fecha a conta de massa.
- **Ratatouille.** O catálogo vende um «Patê de Ratatouille» (`RTAT`). A ficha
  dela é de legumes em cubos, envasados inteiros. Falta ele dizer se é a mesma
  coisa.
- **Geleias de morango e de laranja, manteigas de mel, bacon e alho, creme de
  caramelo, creme de morango, dijonese e torradas.** Nenhum produto do catálogo
  as consome. Entram quando o produto entrar, e não antes: ficha sem
  consumidor não vira custo, rótulo nem fornada.

## O que a planilha dela respondeu sozinha

- **Wasabi é pasta.** Há o registro do teste com pó em 30/08/2023, reprovado por
  ele na própria célula.
- **`QUEIJO-COLONIAL` não saiu de uso** — está no recheio de cebola, 40 g na
  focaccia grande. Faltava a ficha, não o insumo.
- **Gouda no lugar de gruyère** está certo: a ficha do croque diz "queijo gouda
  president".

## O que ela levanta e ainda não tem resposta

- **`Qb` (quanto baste) e `Co` (consumo de óleo)** estão na legenda dela, e o
  sistema exige quantidade positiva em toda linha de ficha. Onde a casa usa
  `Qb`, ou entra um número, ou a linha vira nota de preparo.
- **O mesmo engano da tônica aparece lá**: *"baunilha essência: 14 gt"*, com a
  anotação dele ao lado — *"preciso verificar em peso (kg)!"* — e *"ovos: 0,075
  Unidade"*, que é peso rotulado como contagem. Ver
  [`WP-INSUMOS-DA-VIDA-REAL`](WP-INSUMOS-DA-VIDA-REAL.md).
- **Validades reais** que o `seed` hoje marca como exemplo pré-go-live: recheio
  de cebola 5 dias resfriado, recheio citron 3 dias, manteiga de wassabi 30 dias
  congelado e 15 resfriado.
- **Custos de 2017 a 2023** nas fichas. Velhos demais para virar preço; servem de
  ordem de grandeza ao conferir o custeio.

## Fora de escopo

- A curadoria da lista de insumos — é o [`WP-INSUMOS-DA-VIDA-REAL`](WP-INSUMOS-DA-VIDA-REAL.md).
- Custo por fornecedor e conversão de compra — [`WP-INSUMOS-SEM-FRICCAO`](WP-INSUMOS-SEM-FRICCAO.md).
- A baixa de insumo na venda — [`WP-BAIXA-DE-INSUMO-NA-VENDA`](WP-BAIXA-DE-INSUMO-NA-VENDA.md),
  que passa a depender deste: descontar pela ficha errada desconta do lugar errado.
