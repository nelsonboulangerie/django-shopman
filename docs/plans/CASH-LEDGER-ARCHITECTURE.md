# O caixa do PDV: desconstrução e reconstrução

> Análise arquitetural, 2026-08-18. Escopo: tudo que envolve dinheiro e gaveta no
> PDV — terminal, turno, abertura, fechamento cego, venda em dinheiro, troco,
> sangria, suprimento, abertura sem venda, pedido de troco, trava, comprovante,
> fechamento do dia, reconciliação. Ponto de partida: o PR #198 (log de eventos +
> trava) e a pergunta "log e `CashMovement` não se sobrepõem?". Resposta curta:
> **sobrepõem, e o problema é maior que o #198.**

---

## 0. Veredito em um parágrafo

O domínio do caixa hoje é um Frankenstein porque **o dinheiro do turno mora em
três lugares e a pergunta "quanto entrou nesta gaveta" tem três donos**. Falta a
peça que todo domínio de quantidade do projeto tem: **um livro imutável de
lançamentos** (o `Move` do estoque, a `PaymentTransaction` do pagamento). O
`CashMovement` é um livro pela metade (só sangria e suprimento); a venda em
dinheiro nunca vira lançamento (fica em JSON no pedido, com etiquetas de turno
que um algoritmo de 80 linhas interpreta no fechamento, espelhado em mais dois
lugares); e o `POSEvent` que criei no #198 é um **terceiro** registro que aponta
para o segundo. A forma correta é **um único livro-caixa por turno**, append-only,
em que **todo evento da gaveta é um lançamento com valor assinado** (zero quando
não mexe em dinheiro), e o `CashShift` vira só **custódia** (quem, onde, quando)
sem nenhuma coluna de dinheiro. Com isso o algoritmo de fechamento, o espelho da
leitura X/Z, a adoção de órfãs, as etiquetas no `Order.data`, o `CashMovement` e
o `POSEvent` **deixam de existir**. E o livro precisa morar num pacote do Core,
porque hoje o `shop` importa `backstage` para falar de caixa, o que a regra de
dependência proíbe.

---

## 1. A religião (o que vale como lei aqui)

Enumero, com fonte, o que a análise usa como axioma. Se algum destes não for lei,
a conclusão muda; se forem, ela é quase forçada.

| # | Princípio | Fonte |
|---|-----------|-------|
| P1 | **Quantidade que muda vive num livro imutável; o estado é cache com um escritor só.** `Move` (ledger) + `Quant` (cache, guard `_allow_quantity_update`); `PaymentTransaction` (ledger, "segue o mesmo padrão de Stockman.Move") + `PaymentIntent` (estado). Sinal vive no **tipo**, valor sempre positivo, FK `PROTECT`, `update()`/`delete()` levantam. | `packages/stockman/.../models/move.py`, `quant.py`; `packages/payman/.../models/transaction.py:26-34` |
| P2 | **Uma pergunta, um dono.** Duas superfícies que decidem o mesmo fato separadamente divergem. | memória `feedback_one_question_one_owner` |
| P3 | **JSONField é para estado contextual, não para evento.** Foi a lição do handoff: `drawer_openings`/`change_requests` no `metadata` era a regra da casa aplicada fora de lugar. | `docs/plans/HANDOFF-POS-EVENT-LOG.md` §"Por que o log existe" |
| P4 | **Regra de dependência:** `storefront → shop ← backstage`, `shop` **nunca** importa `backstage`. Cores só se veem por `adapters/`/`contrib/` com import lazy. | `CLAUDE.md` §"Regra de Dependência"; ADR-001 |
| P5 | **Signal para anunciar sem retorno; adapter só com 2+ impls reais; Directive para comando async confiável.** Escrita em ledger de outro app é o handler que escreve direto (`craftsman/contrib/stockman` → `Move`, "único escritor"). | `CLAUDE.md` §"Integração entre apps"; ADR-001 |
| P6 | **Fechamento cego é obrigatório**: o terminal nunca vê esperado nem diferença. **`DayClosing` agrega, não é livro-caixa transacional.** **Turno fechado é imutável salvo ajuste gerencial auditado.** | ADR-011 §4, §5, "Invariantes" |
| P7 | **Core é sagrado, mas cabe ao Core resolver o que é do Core**: antes de inventar, ver como o Core já resolve; e não criar backend de escrita plugável onde um signal ou uma chamada direta basta. | `CLAUDE.md` §"Core é Sagrado" e §"Integração" |
| P8 | Centavos `_q`; identificador textual `ref`; identificadores e URLs em inglês, texto em pt-BR; **nenhum jargão inventado**; nomes de pacote são personas. | `CLAUDE.md`; memórias de nomenclatura |
| P9 | **Nunca por menor diff. Zero gambiarra.** A recomendação é a mais simples-correta-robusta pelo mérito. | memórias `feedback_never_recommend_smallest_diff`, `feedback_zero_gambiarras` |

---

## 2. Diagnóstico: a anatomia do que existe

### 2.1 Onde mora o dinheiro do turno hoje

| Fato | Onde mora | Quem escreve | Quem lê para responder "quanto tem na gaveta" |
|------|-----------|--------------|-----------------------------------------------|
| Fundo de troco (abertura) | `CashShift.opening_amount_q` | `services/pos.py::open_cash_shift` | `CashShift.close()`, `cash_session.py`, `closing.py::_cash_shift_summary`, `bi_cash.py` |
| Sangria / suprimento | `CashMovement` (linha) | `services/pos.py::register_cash_movement` | `close()` (aggregate), `cash_session.py`, `bi_cash.py`, comprovante, Admin |
| **Venda em dinheiro** | `Order.data.payment` (`method`, `tenders[]`, `cash_received_q`, `cash_shift_id`, `cod_cash_shift_id`, `collection`) e `Order.data.pos.cash_shift_id` | `shop/services/pos.py` (`close_sale`, tenders, COD, settle) | `CashShift.close()` (80 linhas), `cash_session.py` (**espelho declarado** de `close()`), `services/payments.py::iter_order_payments`, `order_queue.py`, `bi_change.py`, `sales_series.py`, `fiscal_focusnfe.py`, `operator_orders.py` |
| Contagem cega, esperado, diferença | `CashShift.blind_closing_amount_q / expected_amount_q / difference_q` | `CashShift.close()` | `cash_session.py` (Z), `closing.py` (snapshot), `bi_cash.py`, Admin |
| Devolução de venda em dinheiro | **não existe lançamento**: cancelar depois do fechamento é recusado por texto ("registre a devolução pelo gestor") | `shop/services/pos.py:1002-1005` | ninguém |
| Pagamento em dinheiro no `payman` | **nunca entra**: `payment.initiate` retorna cedo para `cash`/`external` | `shop/services/payment.py:46` | — |

Três casas para o mesmo dinheiro (colunas do turno, tabela de movimento, JSON do
pedido) e nenhuma delas é o livro. Isto viola **P1** na raiz.

### 2.2 A pergunta com três donos

"Quanto dinheiro esta gaveta recebeu de vendas?" é respondida por:

1. `CashShift.close()` — algoritmo de atribuição (tag durável decide; sem tag,
   janela temporal; COD conta para quem coletou; tender sem tag pertence a quem
   criou; **e adota a venda órfã reescrevendo `Order.data` no meio do
   fechamento** — [`cash_register.py:142-254`](../../shopman/backstage/models/cash_register.py)).
2. `cash_session.py` — a leitura X/Z, cujo docstring diz literalmente *"espelha
   `CashShift.close()` (read-only, sem adoção de órfãs)"*. Um espelho é a
   confissão de que a pergunta tem dois donos.
3. `services/payments.py::iter_order_payments` — a "regra de repartição" usada
   por `DayClosing` e B.I. para o mix de meios de pagamento.

Isto viola **P2** três vezes. E o item 1 viola **P6** ("turno fechado é
imutável salvo ajuste auditado") no sentido inverso: o fechamento do turno **muta
pedidos**.

Os dois primeiros **já divergem** hoje, não em tese: `close()` usa `now` como
teto da janela e adota órfãs; o espelho usa `closed_at or now`, não adota, e
conta tenders não-dinheiro por método. Duas respostas para "vendas deste
turno" que só coincidem enquanto ninguém fecha turno com venda em voo.

E o dinheiro em JSON não é só lido por vários: é **reescrito** por vários.
`_reconcile_order_payment_to_total` ([`shop/services/pos.py:1730-1764`](../../shopman/shop/services/pos.py))
regrava `payment.amount_q`, `tenders[].amount_q`, `cash_received_q`, `change_q`
depois do total selado; o acerto de COD regrava tenders e carimba
`cod_cash_shift_id`; `_adopt_orphan_sale` carimba `pos.cash_shift_id`. Três
escritores num campo mutável para o valor que o fechamento cego vai conferir.
A reconciliação financeira, por sua vez, é ancorada em `PaymentIntent`: **o
dinheiro físico é estruturalmente invisível** para todos os seus 17 checks.
E o inventário de ledgers da ADR-021 lista `Move` e `PaymentTransaction`; caixa
não aparece porque não há o que listar.

### 2.3 A seta ao contrário

`shopman/shop/adapters/pos.py` importa `shopman.backstage.models` (com import
lazy) para `cash_shift_is_closed()` e para `POSTab`. É a exceção à regra **P4**
travestida de adapter. E ela existe **porque** o `shop` (que fecha a venda) não
pode escrever num modelo do `backstage` (onde vive o turno) — então o `shop`
carimba `cash_shift_id` no JSON do pedido e o `backstage` reinterpreta depois.
**A dependência mal colocada gerou o algoritmo.** Não é acidente; é a forma que
a arquitetura assumiu para contornar o próprio limite.

### 2.4 O que o #198 acrescenta (e onde erra)

O handoff pediu um log e mandou seguir o `Move`. Eu segui a letra e errei a
essência:

- `cash_in`/`cash_out` no `POSEvent` **apontam** para o `CashMovement`. Mesma
  linha, duas identidades, duas tabelas. O `Move` não aponta para "a tabela do
  movimento"; ele **é** o movimento. Ao dizer "não duplique valor" o handoff
  descreveu o sintoma certo (dois números) e a solução errada (duas tabelas com
  FK); a solução era **uma** tabela.
- `day_closed` e `reconciliation_failed` não são eventos da gaveta. São do dia
  (`DayClosing`) e do pagamento (reconciliação orders × intents). Coloquei-os no
  log por ler "cinco rastros" como lista de coisas a engolir; o critério certo é
  "é lançamento desta gaveta?".
- `CashMovement.receipt_status/receipt_detail/receipt_at` são **estado mutável**
  numa linha que se pretende trilha, e o `CashMovement` **não tem guarda
  nenhuma** de imutabilidade (nem QuerySet, nem `save`). O resultado da
  impressão é um acontecimento, e cabe como lançamento próprio.
- Continuei a venda em dinheiro fora do log. O log responde "o que aconteceu no
  caixa em ordem" **menos as vendas**, que são a maior parte do que acontece.

### 2.5 Outros sinais

- Autorizações de gerente (desconto acima do teto, cancelamento) só vão para
  `logger.info("pos_manager_override …")` ([`shop/services/pos.py:1306`](../../shopman/shop/services/pos.py)). Trilha
  em log de processo é trilha que some.
- `DayClosing.data.cash_shift_summary` **copia** as colunas do turno para dentro
  do snapshot. Cache de cache.
- ADR-011 fixou `POSTerminal`/`CashShift`/`CashMovement`/`DayClosing` e disse
  explicitamente que `DayClosing` "não é livro-caixa transacional". Nunca disse
  quem é. Ninguém é.

---

## 3. Reconstrução: o desenho correto

### 3.1 O domínio em três palavras

O caixa de uma padaria tem exatamente três coisas:

1. **Aparelho** — o terminal onde a gaveta está (`POSTerminal`, já existe, é
   config/estado; ADR-011: "não guarda dinheiro").
2. **Custódia** — o turno: **quem** responde por **qual** gaveta **desde quando
   até quando**. Tem invariantes de unicidade (um aberto por operador, um por
   terminal) que só uma linha de estado com `UniqueConstraint` garante. É o
   `CashShift`, **enxugado**.
3. **Livro** — o que aconteceu com o dinheiro e com a gaveta, em ordem, imutável.
   **Não existe hoje.** É a peça nova, e a única.

Tudo o mais (leitura X/Z, esperado, diferença, mix de meios no dia, "quem abre a
gaveta 3× mais") é **leitura do livro**.

### 3.2 O livro: `cashman.Entry` (nome final; `Shift` e `Terminal` idem, ver §5)

Um lançamento por acontecimento na gaveta de um turno. Segue `Move` e
`PaymentTransaction` à risca:

```
Entry                                        "lançamento de caixa"   (cashman.Entry)
  shift        FK CashShift, PROTECT         em qual custódia aconteceu
  operator     FK user, PROTECT              quem agiu (o do turno, ou o gerente num fechamento supervisório)
  approved_by  FK user, PROTECT, null        a segunda assinatura (sangria, destrave, troco atendido)
  at           datetime                      quando
  kind         choices                       ver tabela abaixo
  amount_q     int, ASSINADO                 efeito no saldo da gaveta; 0 quando não mexe em dinheiro
  order_ref    str                           quando é venda / devolução / COD
  payment_ref  str                           ref do PaymentIntent no payman (sale/refund/cod_settled)
  parent       FK self, PROTECT, null        o lançamento que este responde ou corrige
  reason       str                           motivo humano (sangria, abertura sem venda, correção)
  payload      JSON                           o específico de cada tipo (schema em data-schemas.md)

  guarda: QuerySet.update()/delete() levantam; save() com pk levanta; instance.delete() levanta
  Meta: ordering ["at","id"]; índices (shift, id), (operator, at), (kind, at), (at)
  CheckConstraint por tipo: sinal obrigatório onde há dinheiro, zero onde não há
```

**Por que `amount_q` assinado e não "tipo dá o sinal"?** Porque aqui **o mesmo
livro carrega lançamentos sem dinheiro**, e o invariante que interessa é
`saldo = Σ amount_q`. O sinal no tipo (como no `CashMovement`) foi a escolha
certa quando havia só dois tipos; com uma dúzia, o CheckConstraint por tipo
(`sale ≥ 0`, `refund < 0`, `drawer_open = 0`) dá a mesma proteção sem
espalhar a aritmética por quem lê.

**Tipos** (identificadores em inglês; rótulo pt-BR na tela):

| `kind` | `amount_q` | quando nasce | `parent` | payload |
|--------|-----------|--------------|----------|---------|
| `float_in` | + | abertura do turno (fundo de troco) | — | — |
| `sale` | ≥ 0 | **toda** venda fechada no terminal, no turno aberto do operador: `amount_q` = efeito em dinheiro (recebido − troco; **0** para pix/cartão/external); `payment_ref` aponta o intent do `payman` (§5.2) | — | `{received_q, change_q}` |
| `cod_settled` | + | acerto do dinheiro de entrega no terminal (`OrderSettleDeliveryCashView`) | — | `{courier}` |
| `refund` | − | cancelamento/devolução de venda em dinheiro (dentro ou fora do turno de origem: o dinheiro sai **desta** gaveta) | `sale` original, se no mesmo livro | — |
| `cash_out` | − | sangria (exige `approved_by`) | — | — |
| `cash_in` | + | suprimento | — | — |
| `count` | ± | **fechamento cego**: `amount_q = contado − saldo`, isto é, o **ajuste** que faz o livro bater com a gaveta física | — | `{counted_q, notes}` |
| `count_correction` | ± | ajuste gerencial auditado depois do fechamento (ADR-011) | `count` | `{reason}` |
| `drawer_open` | 0 | abertura sem venda | — | — |
| `drawer_unlock` | 0 | gerente libera a próxima venda com a gaveta aberta (exige `approved_by`) | — | `{drawer_raw}` |
| `change_requested` | 0 | pedido de troco | — | `{kind, amount_q, note}` |
| `change_served` | 0 | troco atendido (exige `approved_by`) | `change_requested` | — |
| `change_cancelled` | 0 | pedido cancelado | `change_requested` | — |
| `receipt_result` | 0 | o que aconteceu com o papel do comprovante | `cash_out`/`cash_in` | `{status, detail}` |
| `note` | 0 | anotação gerencial num turno fechado (hoje `CashShift.notes` editável no Admin) | — | `{text}` |

O que **sai** de cena por consequência direta:

- **`CashMovement`** inteiro (é `cash_out`/`cash_in` + `receipt_result`).
- **`POSEvent`** do #198 (é o livro com os tipos sem dinheiro).
- **Colunas de dinheiro do `CashShift`**: `opening_amount_q` (= `float_in`),
  `blind_closing_amount_q` (= saldo após `count`), `expected_amount_q` (= saldo
  antes de `count`), `difference_q` (= `count.amount_q`), `notes`, `metadata`.
- **`Order.data.pos.cash_shift_id`, `payment.cod_cash_shift_id`, `tenders[].cash_shift_id`**:
  a atribuição passa a ser o próprio lançamento (`sale`/`cod_settled` no livro do
  turno que recebeu). O `Order.data.payment` continua sendo o registro do
  **pedido** (método, tenders, recebido, troco): é dado do pedido; o livro é dado
  da gaveta, e aponta para o pedido pelo `order_ref`. Duas perguntas, dois donos.
- **`CashShift.close()`** (80 linhas) e **`cash_session.py`** como espelho:
  esperado é `Σ amount_q` antes do `count`; X é o livro do turno aberto; Z é o
  livro do turno fechado; histórico do dia é a união. `_adopt_orphan_sale` morre
  sem substituto: não há órfã, porque a linha nasce **na venda**, na mesma
  transação, no turno aberto do operador que fechou a venda.
- **`shop/adapters/pos.py::cash_shift_is_closed`**: `shop` importa o pacote
  (§3.5) e pergunta ao turno.

### 3.3 O `Shift`, enxuto

```
Shift                                         "turno de caixa"   (cashman.Shift)
  terminal    FK POSTerminal, PROTECT
  operator    FK user, PROTECT
  opened_at, closed_at, status (open|closed|void)
  UniqueConstraint(operator, open) / UniqueConstraint(terminal, open)
```

Nenhuma coluna de dinheiro. **Nem cache de saldo.** O `Quant` cacheia
`_quantity` porque disponibilidade é leitura quente do checkout; o saldo da
gaveta é lido no fechamento e na auditoria, `Σ amount_q` com índice `(shift, id)`
é trivial, e **não ter a coluna é o que garante o fechamento cego por
construção**: não há número para a projection do terminal vazar. Este é o caso
em que o padrão do Core fica **mais simples** que o `Move`/`Quant`, não igual.

Se um dia a lista do Admin precisar de "diferença" por linha sem N+1, é um
`annotate(Sum(entries.amount_q) filter kind=count)` no `get_queryset`, não uma
coluna. E se a leitura ficar quente de verdade, aí sim entra o cache com guard,
exatamente como o `Quant`; hoje isso é especulação.

### 3.4 Como cada momento passa a funcionar

- **Abrir turno**: cria `CashShift` + `float_in`. Uma transação.
- **Venda em dinheiro** (`shop/services/pos.py::close_sale`): para o tender
  `cash` com `collection=terminal`, grava `sale` no turno aberto do operador,
  **na mesma transação do commit do pedido e depois do total selado** (hoje o
  `_reconcile_order_payment_to_total` regrava o JSON depois; com o livro, o
  valor que entra na gaveta é gravado uma vez, no momento em que é definitivo,
  e o JSON do pedido deixa de ser a fonte que alguém "reconcilia"). Sem turno
  aberto, a venda em dinheiro é recusada onde hoje já é
  (`requires_open_shift_for_sale`). Análogo exato de "pedido pago →
  `Move(kind=SELL)`".
- **COD**: quando o entregador acerta no terminal, `cod_settled` no turno de quem
  recebeu. É literalmente "o turno que coletou", que hoje é regra escondida no
  algoritmo.
- **Cancelar/devolver venda em dinheiro**: `refund` negativo no turno aberto de
  quem devolve. Fechou o turno de origem? Não importa mais: o dinheiro sai desta
  gaveta agora. A recusa "registre pelo gestor" deixa de existir; a devolução
  **é** um lançamento e o gestor a vê no livro.
- **Sangria/suprimento**: `cash_out` (com `approved_by`) / `cash_in`.
  Comprovante: `receipt_escpos` renderiza a partir da linha; `code_for(entry.pk)`;
  o resultado da impressão vira `receipt_result` com `parent`. A conferência do
  comprovante no Admin lê a linha + o último `receipt_result` filho.
- **Fechar turno (cego)**: o operador informa `counted_q`; o service grava
  `count` com `amount_q = counted_q − Σ(anteriores)` e fecha a custódia. Esperado,
  contado e diferença ficam **provados** pelo livro, não guardados. Correção
  gerencial depois: `count_correction` com `parent`, e a diferença "vigente" é a
  soma dos dois. Turno fechado imutável (P6), corrigível por lançamento (P1).
- **Trava da gaveta**: idêntica ao #198; `drawer_unlock` com `approved_by` e
  `drawer_raw`. Só muda a tabela.
- **Pedido de troco**: três tipos ligados por `parent`, estado dobrado do livro
  (já é assim no #198; `parent` substitui o `ref` no payload).
- **Fechamento do dia**: `DayClosing` continua sendo o snapshot do **dia**
  (sobras, produção, reconciliação); `cash_shift_summary` deixa de copiar
  colunas e passa a ser **calculado do livro** no momento do fechamento (é
  snapshot, pode congelar números; o que não pode é ter uma segunda fonte viva).
- **Mix de meios de pagamento**: dinheiro vem do livro; PIX/cartão vêm do
  `payman` (intents/transações capturadas). `iter_order_payments` deixa de ser a
  fonte de dinheiro; se continuar existindo, é para o que só o pedido sabe
  (repartição declarada de tenders para o fiscal), não para contar caixa.
- **Autorizações de gerente que não tocam na gaveta** (desconto acima do teto):
  **não** vão neste livro. São fato do pedido; o lugar honesto é
  `Order.data`/evento do pedido. Registro aqui como lacuna vizinha, fora do
  escopo.

### 3.5 Onde mora: um pacote do Core

O `shop` fecha a venda e precisa **escrever** o `sale`; o `backstage` opera o
turno e **lê e escreve** o resto. Pela regra P4, o único lugar que os dois
podem importar é `packages/`. Hoje isso é contornado com JSON no pedido e
import lazy do `backstage` dentro do `shop`.

As alternativas, pesadas por P4/P5/P7:

| Opção | Como o `shop` grava a venda | Veredito |
|-------|-----------------------------|----------|
| A. Pacote do Core (terminal + turno + livro + services `open/close/record`) | import direto do service do pacote, síncrono, na transação da venda | **Correta.** Espelha `craftsman/contrib/stockman → Move` e `payman`. Sem seta invertida, sem sinal implícito para dinheiro. |
| B. Fica no `backstage`; `shop` anuncia por signal e um handler do `backstage` grava | `order_changed` → handler | Consistente com P5, mas para **dinheiro** o handler não registrado falha em silêncio; "o silêncio era o bug" já custou uma sexta-feira nesta semana. E mantém `POSTerminal`/`CashShift` num app de superfície. |
| C. Fica no `backstage`; `shop` importa via `adapters/pos.py` | como hoje | É a seta invertida de sempre; a que produziu o algoritmo. |

**A.** Nome: persona, sem jargão inventado. `till` é a palavra inglesa corrente
para caixa registradora / gaveta de dinheiro; `tillman` é candidato natural ao
lado de `payman`/`stockman`. `cashman` é o outro. Decisão do dono (§5).

O pacote leva: `Terminal` (config do aparelho, hoje `POSTerminal`), `Shift`,
`Entry`, e os services (`open_shift`, `record`, `close_shift`, `correct_count`,
consultas `balance(shift)`, `timeline(shift)`). **Não leva** hardware do
terminal (`pos_hardware.py`, agente do balcão, comprovante ESC/POS): isso é
superfície de operador e fica no `backstage`, que passa a **usar** o pacote.
`POSTab` também fica (é sessão de venda, não caixa).

Zero adapter plugável: só há uma implementação real, e P7 proíbe seam "para o
futuro". Import direto.

### 3.6 O que NÃO entra no livro (fronteiras)

- `PaymentIntent`/`PaymentTransaction`: dinheiro **com gateway**. O dinheiro
  físico não passa por lá e não deve passar: `payman` responde "o cliente pagou
  e o gateway liquidou?"; o livro responde "quanto há nesta gaveta". Perguntas
  diferentes, donos diferentes, ligados por `order_ref`.
- `OperatorAlert`: aviso com reconhecimento, cross-superfície. Não é trilha.
- Reconciliação financeira: pedidos × pagamentos. Do `payman`/dia, não da gaveta.
- `DayClosing`: snapshot gerencial do dia. Lê o livro; não é o livro (ADR-011).
- Sessão de venda / comanda (`POSTab`, `Session`): não é caixa.

---

## 4. O que fazer com o PR #198

**Não mergear como está.** Ele acrescenta a terceira tabela e legitima a
sobreposição que motivou a pergunta. O que ele tem de bom migra 1:1 para o
desenho acima:

| No #198 | No livro |
|---------|----------|
| `POSEvent` + guarda `Move`-like | `cashman.Entry` (mesma guarda) |
| `cash_in`/`cash_out` → FK `CashMovement` | **são** as linhas; `CashMovement` some |
| `drawer_opened`, `drawer_unlocked`, `change_*` | tipos de `amount_q = 0`, `parent` em vez de `ref` no payload |
| `shift_opened`/`shift_closed` com `opening_amount_q`/`difference_q` no payload | `float_in` / `count` **com o valor como `amount_q`** |
| `day_closed`, `reconciliation_failed` | fora (não são da gaveta) |
| RunPython carregando `metadata` para o log | mesmo espírito, alvo o livro |
| Endpoint `drawer-unlock` + `validate_manager_override` | igual |
| `useCashDrawer.readState`, `useDrawerLock`, `PosDrawerLockDialog`, testes | **iguais** (a trava é do PDV; só o `POST` muda de destino se o path mudar) |
| Inline no Admin do turno | igual, sobre `entries` |
| B.I. `by_operator` + `drawer_by_hour` | igual, sobre `entries` |

**Migração (uma só, append-only, pré go-live de caixa):**

1. Criar as tabelas do pacote.
2. Backfill: para cada `CashShift`, `float_in` (de `opening_amount_q`), uma linha
   por `CashMovement` (`cash_out`/`cash_in` + `receipt_result` se houver
   resultado), `sale`/`cod_settled` por venda em dinheiro **rodando o algoritmo
   atual de `close()` uma última vez** (é a última vez que ele existe: vira o
   backfill), `count` com `amount_q = blind_closing − expected` para turnos
   fechados, `drawer_open`/`change_*` das listas do `metadata`.
3. Provar no teste de migração que `Σ` por turno reproduz `expected`, `contado` e
   `diferença` de todo turno fechado (é o critério da ADR-011: "dados históricos
   migram sem alteração financeira").
4. Remover `CashMovement`, as colunas do turno, as etiquetas do `Order.data`, o
   `adapters/pos.py`.

O `POSEvent` **não chega a existir em produção** se o #198 não entrar. Melhor
assim: uma tabela a menos para migrar.

---

## 5. Decisões (tomadas pelo dono em 2026-08-18)

1. **Nome do pacote: `cashman`** (`packages/cashman`, `shopman.cashman`).
2. **Venda: uma linha** `sale`, `amount_q` = efeito em dinheiro na gaveta
   (recebido − troco), payload `{received_q, change_q}`.
3. **`POSTerminal` vai junto** para o pacote (`cashman.Terminal`), com o turno.
4. **Mix de meios de pagamento: fonte única é o `payman`**, e para isso
   `cash` e `external` passam a criar `PaymentIntent` capturado atomicamente na
   venda do PDV (método sem gateway; **não** é adapter novo, é caminho do
   `PaymentService`). Ver §5.1.

### 5.1 `cashman` × `payman`: fronteira e o único fato compartilhado

Perguntas diferentes, donos diferentes, ligados por ref (ADR-004):

| Pergunta | Dono |
|---|---|
| Como este pedido foi pago (declaração: método, tenders, troco)? | `Order.data.payment` (dado do pedido; fiscal e recibo precisam dele) |
| Este pagamento liquidou? Quanto foi capturado/estornado, por método? | **`payman`** (intent + transactions), agora com `cash` e `external` |
| Quem responde por esta gaveta e o que entrou/saiu dela, em ordem? | **`cashman`** (turno + livro) |

O único fato que aparece nos dois é o **tender em dinheiro**: no `payman` é
uma captura; no `cashman` é uma linha `sale` com efeito no saldo e
`payment_ref` para o intent. Não são dois donos de uma pergunta; é cada
contexto guardando a sua projeção do fato, como pedido → `Move(SELL)`. A ligação
habilita um check cruzado hoje impossível: `Σ capturas cash do dia ==
Σ sale.amount_q do dia` (a reconciliação financeira, ancorada em intent, é
**estruturalmente cega para dinheiro** hoje).

Referências externas com a mesma forma: Square (`Payment` para todo tender +
`CashDrawerShift`/`CashDrawerShiftEvent` com `CASH_TENDER_PAYMENT`,
`OTHER_TENDER_PAYMENT`, `PAID_IN`, `PAID_OUT`, `NO_SALE`, refunds); Odoo POS
(`pos.payment` por método + sessão com controle de caixa e entradas/saídas).
Contabilmente: recebimentos é um livro, livro-caixa é outro.

O que **não** vai para o `cashman`: status de intent, gateway, chargeback,
reconciliação. O que **não** vai para o `payman`: turno, custódia, sangria,
suprimento, abertura sem venda, trava, troco.

### 5.2 Cartão, PIX e `external` no PDV

Não tocam na gaveta: **efeito zero no saldo**. Mas passam pelo turno, e a
leitura Z precisa de "vendas por método deste turno". Portanto **toda venda no
terminal escreve uma linha `sale` no livro do turno; `amount_q` é só o efeito
em dinheiro** (0 para pix/cartão/external), com `payment_ref`. Método e valor
do tender ficam no `payman` (um dono); a projection X/Z do `backstage` junta os
dois (o `backstage` pode importar ambos os pacotes). É o `OTHER_TENDER_PAYMENT`
do Square: a venda entrou na sessão, a gaveta não abriu. De graça: "quantas
vendas este turno fez" deixa de depender de algoritmo.

Consequência no modelo (§3.2): a linha `sale` ganha `payment_ref` (string, ref
do intent) e o CheckConstraint passa a ser `amount_q >= 0` para `sale`.

### 5.3 Por que pacote do Core, e não `shop`

A ADR-019 diagnosticou a mesma doença para promoção ("regra de preço mora numa
superfície; o orquestrador alcança por adapter com import lazy: legal pela
regra, invertido pela constituição") e a cura foi mover o modelo para onde a
dependência aponta. `shop/adapters/pos.py → backstage.models` é o mesmo
sintoma. Para onde mover:

- **`packages/cashman`** (decisão): "sessão de caixa + livro da gaveta" é um
  contexto delimitado clássico de POS, com invariantes próprios e ledger
  próprio, sem depender de catálogo/estoque/pedido além de refs string. É o
  critério da ADR-001 para um core, e é a forma que `payman` e `stockman` já
  têm. `shop` grava a venda e `backstage` opera o turno: `packages/` é o único
  lugar que os dois importam sem seta invertida.
- **`shopman/shop/`** (alternativa honesta, não escolhida): o `backstage`
  importa `shop`, então a dependência fecharia. O precedente da ADR-019 vale
  para promoção porque promoção é **política composta sobre cores** (preço ×
  canal × cliente) e o orquestrador é o dono da política. Custódia de dinheiro
  não é política; é domínio com ledger. Pôr uma biblioteca de domínio dentro do
  coordenador funcionaria, mas seria a exceção sem motivo.
- Contra-argumento considerado: 12º pacote, três modelos. Tamanho não é
  critério; independência e invariantes são. Nasce com o mesmo teste de
  fronteira dos outros (`Terminal.channel_ref` é string; zero import de
  `shop`/`backstage`).

---
## 6. O que não muda

- Fechamento cego: reforçado (não há coluna para vazar).
- Sangria exige PIN sem limiar; troco atendido exige PIN; destrave exige PIN.
- Regras da trava (iniciar; sem carência; só quando sabe; um destrave, uma venda).
- Comprovante de sangria, conferência por QR, agente do balcão, polaridade medida.
- `DayClosing` como snapshot do dia; `OperatorAlert` como aviso.
- Contratos das telas do PDV (a projection `cash_runtime` e X/Z mantêm forma;
  mudam de fonte).

---

## 7. Síntese

O Frankenstein não é o #198; o #198 é o terceiro remendo. A costura errada é
anterior: **um domínio de quantidade sem livro**, com o dinheiro repartido entre
colunas de estado, uma tabela parcial e JSON no pedido, e uma pergunta com três
donos porque a seta de dependência não deixava o `shop` gravar onde devia. A
correção é a mesma que o projeto já deu duas vezes (`Move`, `PaymentTransaction`):
**um livro imutável, um escritor por fato, estado só para custódia**, num pacote
que os dois lados podem importar. Tudo o resto some por consequência, não por
decisão.
