# WP — A baixa de insumo quando o item é feito na hora

> Pedido do dono em 23/09/2026: *"Acho que precisamos lançar WP dedicado essa
> fase 2 do Buyman, confere?"* — **confere**, e a primeira coisa que este WP faz
> é desfazer um nome que engana.

## O nome engana, e isso já custou

"Fase 2 do Buyman" quer dizer **duas coisas diferentes** no repositório:

1. No [`BUYMAN-PROCUREMENT-PLAN`](BUYMAN-PROCUREMENT-PLAN.md), Fase 2 é o
   **Pedido de Compra** (`PurchaseOrder`). Boa parte dela **já foi entregue por
   outro caminho**: o Compras do Gestor (`surfaces/purchase-nuxt` +
   `shopman/backstage/services/purchase.py`) já recebe mercadoria e escreve
   `Move(kind=BUY)` no ledger, sem o model formal de pedido.
2. No `seed.py`, "Fase 2 do Buyman" é o **consumo automático na VENDA de item
   feito na hora** — *"a ficha nasce pronta para ele"*.

**É a (2) que falta, e é esta que o WP trata.** A (1) segue no plano do Buyman.

## O buraco, medido no alpha em 23/09

**23 fichas estão inativas**, e não é erro: elas dão custo, insumo e rótulo, mas
não são fornada. São os croques, os sanduíches montados e as bebidas — o que se
faz **quando o cliente pede**, não em lote.

O que não acontece: **quando esses itens são vendidos, nada sai do estoque.**

| item | ficha | vendas no histórico |
|---|---:|---:|
| Espresso | `SP` | 62.331 |
| Cappuccino | `CAP` | 34.022 |
| Croque Monsieur | `CQMO` | 28.727 |
| Café Coado | `COAD` | 27.190 |
| Espresso Macchiato | `SPMC` | 4.899 |
| Caffè Latte | `CAFL` | 2.960 |

**22 insumos existem só dentro de ficha inativa** — ou seja, entram no estoque
pela compra e **nunca saem**. Entre eles:

- `CAFE-GRAO` (café em grão da casa), usado por **8** fichas
- `PRESUNTO-CASA`, `QUEIJO-GRUYERE`, `MOLHO-BECHAMEL`, `SALADA-DA-CASA`
- os **7 blends de chá da Kãnfa** (`CHA-BLEU`, `CHA-CHAI`, `CHA-ROUGE`…)

O saldo deles no alpha é o do seed (5 kg, 2 kg) e **não se move desde que
nasceu**. Quem olhar o estoque de café em grão vê o que comprou, nunca o que
usou.

## O que isso quebra hoje

- **Estoque de insumo mente para cima.** O café em grão nunca desce. Qualquer
  alerta de reposição em cima dele é ficção.
- **O custo do produto feito na hora não fecha.** A ficha existe e dá o custo
  unitário, mas nada o confronta com consumo real.
- **O `INVENTORY_BACKEND` (guardrail de disponibilidade de insumo) não protege
  esses itens**: ele valida contra um saldo que não reflete consumo.
- **O B.I. não sabe a margem** desses itens — é a pergunta P6 do
  [`BI-QUESTION-CATALOG`](BI-QUESTION-CATALOG.md), marcada 🔴 e apontando
  justamente para cá.

## O que já está pronto e não se refaz

- **A ficha.** As 23 existem, com gramatura por unidade, e o dono acabou de
  ganhar a aba `Fichas` na planilha para revisá-las.
- **O ledger.** `StockMovements.issue(kind=MAKE)` é o primitivo, e o
  `craftsman/contrib/stockman` já o usa no fim da produção — **escritor único**,
  por signal, como manda a [ADR-001](../decisions/adr-001-protocol-adapter.md).
- **A lição do `InventoryProtocol` morto** (ver o plano do Buyman): houve um
  segundo caminho de escrita que não escrevia nada por um typo, e o insumo
  nunca era deduzido. A cura foi **um caminho só**. Este WP não pode criar o
  segundo.

## As perguntas que decidem o desenho

**1. Qual é o gatilho?** Três candidatos, e eles não dão o mesmo resultado:

- a **venda** (`order` confirmado/completado) — simples, mas conta o que foi
  cancelado depois;
- o **preparo** (o KDS marcar pronto) — fiel ao que a cozinha fez, mas o balcão
  tira café sem passar pelo KDS;
- o **fechamento do dia** — em lote, tolerante a correção, e é como muita casa
  faz de verdade.

**2. Falta de insumo trava a venda?** Hoje o `INVENTORY_BACKEND` recusa
`adjust`/`finish` na produção. Recusar uma venda de balcão porque o sistema acha
que acabou o gruyère é pior que o erro que evita — mas deixar passar calado é
como chegamos aqui.

**3. O que fazer com o que já passou?** Dois anos de Yooga e o alpha inteiro
foram vendidos sem baixa. Retroagir é tentador e perigoso: o saldo de hoje foi
contado à mão, não derivado.

**4. Preparo intermediário conta duas vezes?** O `MOLHO-BECHAMEL` e a
`SALADA-DA-CASA` são fichas que produzem, e entram como insumo nos croques. Se a
baixa na venda descer até a folha, desconta o que a produção já descontou.

## Fatias sugeridas

- **F1 — o gatilho, decidido e escrito.** Uma linha no ADR, não um palpite no
  código. Depende da resposta 1.
- **F2 — o consumo por signal, escritor único.** `issue(kind=MAKE)` a partir dos
  itens da ficha inativa, com a mesma política greedy/present-stock-first que a
  produção usa; shortfall **não fatal**, mas **registrado** (foi o silêncio que
  criou o problema).
- **F3 — o que a tela mostra.** O Compras precisa dizer "isto desceu por venda",
  e não misturar com a fornada. O `Move.kind` já separa.
- **F4 — a margem.** Com consumo real, a P6 do B.I. deixa de ser 🔴.

## Fora de escopo

- O `PurchaseOrder` formal (Fase 2 do plano do Buyman) — outro caminho já
  entrega o recebimento.
- Retroagir consumo histórico, até a resposta 3.
- FEFO / near-expiry na escolha do lote (é o WP-B6 do Buyman).

## Pré-condição

**As 23 fichas revisadas pelo dono.** Duas massas estavam erradas e ele as
corrigiu em 22 e 23/09; uma baixa automática em cima de ficha errada desconta o
insumo errado, em silêncio, para sempre. A aba `Fichas` da planilha de curadoria
existe para isso.
