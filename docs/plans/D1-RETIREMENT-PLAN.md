# D1-RETIREMENT-PLAN — a validade decide, a posição não

> **Status:** 🚧 ativo (2026-08-13). Continuação direta do
> [ADR-017](../decisions/adr-017-quality-as-production-outcome.md) (§1–8
> implementados, PR #143) e do [QC-FORNADA](QC-FORNADA.md).
>
> ⚠️ **Este plano existe no repo de propósito.** A decisão de aposentar o D-1
> foi tomada uma vez, viveu num plano nunca commitado (POS-ALPHA-REMEDIATION) e
> **se perdeu por meses** — a ponto de a frente FOMO construir um badge novo em
> cima do conceito morto. Plano fora do repo morre fora do repo
> (`feedback_plan_in_repo`).

## 1. O que o D-1 é hoje, no código (verificado)

O D-1 não é um conceito, é uma **mecânica de posição**:

| Peça | Onde | O que faz |
|---|---|---|
| Transferência | `backstage/services/closing.py:48-60` | Sobra classificada `d1` sai do saleável e entra na posição `"ontem"`, com `batch="D-1"` (string literal, **não** uma `Batch.ref` real) e `reason="d1:<data>"` |
| Desconto | `shop/rules/pricing.py` `D1Rule` + `shop/modifiers.py` `AvailabilityDiscountModifier` | 50% linear em qualquer linha cujo estoque venha de `"ontem"` |
| Cerca de canal | `seed.py` `_remote_stock = {"excluded_positions": ["ontem"]}` | Canal remoto não enxerga a posição |
| Limpeza | `shop/management/commands/cleanup_d1.py` | Remove D-1 vencido |
| Vitrine | `shop/services/fomo.py` `d1_qty()` + `storefront/presentation/fomo.py` `_d1()` | Badge "Último dia" |
| PDV | `backstage/projections/pos.py` | Bucket `d1` |

**O defeito de fundo:** a posição é um *proxy* de "está no último dia". Funciona
para pão do dia; **quebra para tudo que dura mais de um dia** — o caso do queijo,
que foi o que originou a superação. Um Camembert com 20 dias de validade não tem
"ontem"; tem uma curva de validade. E o desconto de 50% linear ignora *por que* o
item está barateando (idade? não conformidade?) e *quanto* isso deveria valer.

## 2. O que substitui

O modelo do ADR-017, já no `main`:

- **`Batch.expiry_date`** responde "até quando pode ser vendido" — por lote, não
  por posição. Vale para pão de 1 dia e para queijo de 20.
- **`Batch.nonconformity_percent`** responde "quanto desconta" — resolvido do
  grau no fechamento da fornada e **congelado** no lote.
- **`Batch.nonconformity_reason`** responde "por quê" (rótulo do defeito/grau).

### O fato arquitetural que torna isto possível (verificado)

**Cada `Hold` ancora em exatamente UM `Quant`** (`holds.py:97-102`, "1:1 hold:quant
by design"), e **`Quant.batch` guarda a `Batch.ref`** (CharField, ADR-004; a chave
única `unique_quant_coordinate` inclui `batch`). Logo:

> A linha vendida **sabe de qual lote saiu** — hold → quant → `batch` → `Batch`.

É isso que torna o preço por lote viável sem redesenhar o fulfillment. Sem esse
elo, `percent_for_lot` seria impossível e o D-1 por posição seria insubstituível.

## 3. Os consumidores (a frente)

Ordem obrigatória; cada um entrega valor sozinho e passa `make test`.

### C1 — Preço por lote na venda (`percent_for_lot`)

O desconto passa a vir do LOTE que a linha reservou, não da posição.

- `shop/services/lot_pricing.py`: `percent_for_lot(batch_ref) -> int`, lendo
  `Batch.nonconformity_percent`. Arbitragem `max(automatic, declared)` conforme
  ADR-017 §7 — o operador pode aprofundar o desconto, nunca reduzi-lo abaixo do
  que a inspeção determinou.
- Novo modifier `LotDiscountModifier` (ordem 15, onde hoje vive o D-1), lendo o
  lote da linha. **Best-wins** com promoção/D-1, nunca compõe
  (`_apply_flat_best_wins`, mesma lei da auditoria de descontos).
- ⚠️ **Fonte durável:** o percentual entra no snapshot da linha no commit — o
  lote pode ser reprecificado depois, e o pedido fechado não muda
  (`project_discount_stacking_guard_durable_source`).

### C2 — Validade decide a oferta, por canal

`ChannelConfig.stock` ganha dois aspectos, ambos config (sem campo novo no core):

- `sells_nonconforming: bool` (default `False`) — canal remoto não vende lote
  com desconto de não conformidade. **Substitui** `excluded_positions=["ontem"]`.
- `expiry_margin_days: int` (default `0`) — não oferecer lote a menos de N dias
  do vencimento (o gap B2 do VALIDITY-SHELFLIFE-REVIEW, "near-expiry").

Aplicados em `quants_eligible_for` via o adapter de disponibilidade do
orquestrador — o mesmo escopo que o hold usa, para badge e carrinho nunca
divergirem.

### C3 — FEFO: vende primeiro o que vence antes

`_find_quant_for_hold` ordena por `created_at` (FIFO). Com validade decidindo
preço, FIFO passa a ser **errado**: deixaria o lote que vence hoje encalhar
enquanto vende o de amanhã. Ordenar por `Batch.expiry_date` (nulos por último),
`created_at` como desempate. É o gap A2 do VALIDITY-SHELFLIFE-REVIEW.

### C4 — Fechamento: write-off, não mudança de posição

A sobra **não se move**. O que muda é a leitura:

- Lote que vence hoje → `Move` com `Kind.WASTE`, razão `perda_vencido:<data>`.
- Lote que vence depois → **fica onde está**; o desconto (se houver) e a cerca
  de canal já vêm do lote. A classificação `d1` do fechamento deixa de existir.
- Lote não conforme → `perda_nao_conformidade:<data>` quando o grau obriga
  (`forces_discard` já resolve no finish; aqui é o resíduo declarado).

### C5 — Quiosque de QC (ADR-017 §9)

Tela de fechamento de fornada em `production-nuxt`: partição por grau com os
botões de defeito (rótulo + `hint`), consumindo Projection frozen. Menos toques
possíveis, tela touch, 5h da manhã.

### C6 — Remoção do D-1 (só depois de C1–C5 no ar)

`D1Rule`, posição `"ontem"`, `cleanup_d1`, bucket `d1` do POS, `d1_qty()`,
badge F3 (vira "último dia" derivado de `Batch.expiry_date`), `reason="d1:"` do
fechamento, `excluded_positions` do seed. **Zero resíduo** — a janela pré-go-live
permite apagar em vez de depreciar (ADR-015 ainda não vigora).

## 4. Invariantes

- A posição nunca mais decide preço nem visibilidade comercial. Posição é
  **onde**, validade é **até quando**, grau é **quanto**.
- Preço de lote sai do `Batch`, congelado no commit do pedido.
- Desconto de lote **não compõe** com promoção/cupom — best-wins.
- Canal remoto não vende não conforme por default; afrouxar é decisão explícita.
- FEFO em produto com validade; FIFO só onde não há lote.
- Nenhum `Batch` novo em `stockman` além dos dois campos já criados.

## 5. Critérios de aceite

- Pão do dia e queijo de 20 dias passam pelo MESMO caminho de decisão.
- Lote com desconto não aparece em canal remoto sem `sells_nonconforming=True`.
- Pedido fechado não muda de preço quando o lote é reprecificado depois.
- `grep -rn "ontem\|d1_qty\|D1Rule\|cleanup_d1"` retorna vazio ao fim do C6.
- Fechamento não cria `Move` para posição `"ontem"` em ambiente nenhum.

## Referências

- [ADR-017](../decisions/adr-017-quality-as-production-outcome.md) — a fundação (§1–8 no main)
- [QC-FORNADA](QC-FORNADA.md) — desenho de produto do fechamento de fornada
- [VALIDITY-SHELFLIFE-REVIEW](VALIDITY-SHELFLIFE-REVIEW.md) — gaps A2 (FEFO) e B2 (near-expiry)
- [ADR-004](../decisions/adr-004-string-refs.md) — por que `Quant.batch` é string
