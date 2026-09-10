# ADR-022 — O caixa é um pacote do Core: `cashman`, livro imutável por turno

**Status:** Aceito e implementado (2026-08-19; WP-0..9 do CASHMAN-PLAN no `main`: pacote, Payman sem gateway, venda no livro, backstage sobre o pacote, backfill e corte dos models legados, reconciliação cruzada, trava da gaveta, cancelar não é devolver, troco da entrega; resta WP-10)
**Data:** 2026-08-18
**Escopo:** novo pacote `packages/cashman` (`Terminal`, `Shift`, `Entry`, services); `packages/payman` (métodos sem gateway: `cash`, `external`); `shopman/shop` (grava a venda no livro; deixa de etiquetar turno no `Order.data`); `shopman/backstage` (opera o turno pelo pacote; perde `POSTerminal`, `CashShift`, `CashMovement`); `docs/reference/data-schemas.md`
**Supersede parcialmente:** ADR-011 §3 ("Caixa passa a usar `POSTerminal`, `CashShift` e `CashMovement`") e §5 (`DayClosing` continua não sendo livro-caixa; agora existe um)
**Mantém:** ADR-011 §4 (fechamento cego obrigatório) e os invariantes "terminal não guarda dinheiro", "turno fechado é imutável salvo ajuste gerencial auditado"
**Análise completa:** [docs/plans/CASH-LEDGER-ARCHITECTURE.md](../plans/CASH-LEDGER-ARCHITECTURE.md); execução: [docs/plans/CASHMAN-PLAN.md](../plans/CASHMAN-PLAN.md)

---

## Contexto

O dinheiro de um turno de caixa mora hoje em três lugares: colunas do
`CashShift` (abertura, contagem, esperado, diferença), a tabela `CashMovement`
(só sangria e suprimento) e o JSON `Order.data.payment` (venda em dinheiro, com
etiquetas `cash_shift_id`/`cod_cash_shift_id` interpretadas no fechamento por um
algoritmo de atribuição de 80 linhas em `CashShift.close()`, espelhado em
`cash_session.py` e em `iter_order_payments`). Nenhum dos três é um livro. O
`payman` nunca recebe dinheiro (`initiate` retorna cedo para `cash`/`external`),
o que deixa a reconciliação financeira estruturalmente cega para o físico.

A causa é a seta de dependência: o `shop` fecha a venda e não pode escrever no
`backstage`, onde vive o turno; então carimba o pedido e o `backstage`
reinterpreta depois (`shop/adapters/pos.py` importa `backstage.models` com
import lazy, a mesma doença que a ADR-019 diagnosticou para promoção).

O projeto já resolveu esse tipo de problema duas vezes com a mesma forma:
`stockman.Move` (ledger imutável) + `Quant` (estado, um escritor) e
`payman.PaymentTransaction` (ledger imutável) + `PaymentIntent` (estado). O
caixa é o terceiro domínio de quantidade e o único sem livro.

## Decisão

1. **Nasce o pacote `cashman`** (`packages/cashman`, `shopman.cashman`), no
   molde do `payman`, com três modelos:
   - `Terminal`: o aparelho (config; não guarda dinheiro).
   - `Shift`: a custódia: terminal, operador, aberto/fechado em, status.
     **Nenhuma coluna de dinheiro, nem cache de saldo.** Constraints: um turno
     aberto por operador e um por terminal.
   - `Entry`: o livro. Uma linha por acontecimento na gaveta do turno, com
     `amount_q` **assinado** (efeito no saldo; **zero** quando o evento não
     mexe em dinheiro), `kind`, `operator`, `approved_by` (segunda assinatura),
     `order_ref`, `payment_ref`, `parent` (a linha que esta responde ou
     corrige), `reason`, `payload`. Guarda de imutabilidade igual à do `Move`:
     `update()`/`delete()` levantam; correção é lançamento novo.
2. **Todo evento da gaveta é lançamento**, inclusive os sem dinheiro:
   `float_in`, `sale` (efeito em dinheiro; 0 para pix/cartão/external),
   `cod_settled`, `refund`, `cash_out`, `cash_in`, `count` (o fechamento cego é
   um ajuste: `amount_q = contado − saldo`), `count_correction`,
   `drawer_open`, `drawer_unlock`, `change_requested/served/cancelled`,
   `receipt_result`, `note`. Esperado, contado e diferença são **provados pelo
   livro**, não guardados.
3. **A venda grava o livro na própria transação**: `shop/services/pos.py`
   importa `cashman` e registra `sale` no turno aberto do operador quando o
   pedido fecha, com `payment_ref`. Cancelamento/devolução grava `refund`;
   acerto de COD grava `cod_settled` no turno de quem recebeu. As etiquetas de
   turno em `Order.data` deixam de existir.
4. **`payman` é o livro de pagamentos de todos os métodos**: `cash` e
   `external` no terminal criam `PaymentIntent` capturado atomicamente na venda
   (ramo do `PaymentService` para método sem gateway; não é adapter). O mix de
   meios de pagamento tem um dono: o `payman`.
5. **Fronteira `cashman` × `payman`:** `payman` responde "liquidou? quanto,
   por método?"; `cashman` responde "quem responde por esta gaveta e o que
   entrou/saiu dela, em ordem". O único fato compartilhado é o tender em
   dinheiro (captura lá, `sale` aqui), ligado por `payment_ref`; a ligação
   habilita o check cruzado `Σ capturas cash == Σ sale/refund/cod_settled`.
6. **`backstage` opera o turno pelo pacote** (services, API com URLs
   preservadas, projections X/Z lendo livro + `payman`, Admin via
   `cashman.contrib.admin_unfold`). Permissões passam a `cashman.operate_pos`,
   `cashman.audit_shift`, `cashman.adjust_shift`, `cashman.manage_operators`.
7. **Migração única de backfill**: `Terminal`/`Shift` preservam pk; o
   algoritmo atual de `CashShift.close()` roda **uma última vez** dentro da
   migração para gerar as linhas `sale`; teste de migração prova, ao centavo,
   que `Σ` reproduz esperado/contado/diferença de todo turno fechado. Depois,
   `CashMovement`, `CashShift`, `POSTerminal` são removidos.

## Consequências

**Positivas**

- Uma pergunta, um dono: `CashShift.close()`, o espelho em `cash_session.py`,
  a adoção de órfãs, as etiquetas no pedido e `shop/adapters/pos.py::cash_shift_is_closed`
  deixam de existir.
- Fechamento cego garantido por construção: não há coluna de saldo para a
  projection do terminal vazar.
- Devolução de venda em dinheiro passa a existir como lançamento (`refund`),
  em vez de recusa por texto.
- Reconciliação financeira enxerga dinheiro.
- O log de eventos do PDV (PR #198) deixa de ser necessário: seus tipos são
  linhas de `amount_q = 0` no mesmo livro; a trava da gaveta (PDV) é
  reaproveitada tal e qual.

**Negativas / custos**

- 12º pacote do Core; renomear permissões (61 ocorrências) e o vocabulário
  `CashShift`/`CashMovement` em código, docs, seed e RBAC.
- `payman` passa a ter intents sem gateway; checks de reconciliação ancorados
  em gateway precisam ignorar gateway vazio.
- A migração de backfill é o passo delicado do go-live do caixa: exige
  fixture realista e janela de deploy com o app parado.

## Invariantes

- `Terminal` não guarda dinheiro; `Shift` não guarda dinheiro; só `Entry`.
- `Entry` é imutável no app (guarda igual ao `Move`); a imutabilidade real
  (trigger no Postgres) **não é prometida**.
- `saldo(turno) = Σ Entry.amount_q`; `esperado = saldo antes do count`;
  `diferença = Σ count + Σ count_correction`.
- Toda venda no terminal tem uma linha `sale` no turno aberto de quem fechou;
  `amount_q` é só o efeito em dinheiro.
- Nenhuma projection servida ao terminal expõe `saldo`, esperado ou diferença.
- `payman` é a única fonte de "receita por método"; `cashman` a única de
  "dinheiro na gaveta"; `Order.data.payment` a única de "como o pedido declarou".
- Cada destrave da trava é uma linha `drawer_unlock` com `approved_by`.

> ⚠️ **Revisto em 29/08 — a trava mudou de natureza.** Quando esta ADR foi
> aceita, a trava era um pedágio: barrava a próxima venda e o gerente liberava
> UMA venda com a gaveta ainda aberta. O dono trocou por **trava dura, liberada
> pelo mundo físico**: o PDV não anda enquanto a gaveta estiver aberta, e o
> bloqueio cai sozinho quando o sensor diz que ela fechou.
>
> O que muda no livro:
>
> - `drawer_unlock` deixa de ser o destrave e passa a ser a **exceção** (gaveta
>   emperrada aberta, sensor morto). O payload ganha `outcome`
>   (`manager_override` | `sensor_lost`) e `duration_ms`, porque emergência
>   indistinguível de rotina some na média — e a anomalia que interessa é o
>   gerente que libera 20× por dia.
> - Nasce a linha `note` com `payload.event = "drawer_blocked"`
>   (`outcome`, `duration_ms`): o fechamento normal, que antes não existia como
>   registro. É ela que torna a **duração real** da gaveta aberta mensurável —
>   o PIN cortava a medição no meio.
> - Nasce a linha `note` com `payload.event = "drawer_left_open"` (`minutes`): a
>   gaveta esquecida aberta na hora morta, que a trava não vê porque ninguém
>   tenta vender.
> - Nasce a linha `note` com `payload.event = "drawer_sensor_blind"`: a trava
>   caiu numa estação que TINHA medição. Ela falha aberta de propósito, e por
>   isso precisa gritar — sem isso, puxar o cabo da gaveta desligava a proteção
>   para sempre, em silêncio.
>
> - Nasce a linha `note` com `payload.event = "drawer_unlock_attempt"`
>   (`outcome`): alguém abriu a tela de PIN, **inclusive quem desistiu**. A
>   saída de emergência é escondida (Esc, sem botão na tela) porque um botão
>   ensina o bypass; e é por ser escondida que PROCURÁ-LA é informação.
>
> ⚠️ **Correção de 29/08, achada olhando a TELA e não pelos testes.** O botão de
> fechar do diálogo encerrava o bloqueio sem gerar linha nenhuma. Não era brecha
> de venda — largar a venda que esperava não libera nada, e a tentativa seguinte
> trava de novo —, mas era brecha de RASTRO: dava para esbarrar na trava e
> desistir a manhã inteira sem deixar registro. Nasceu o desfecho `dismissed`, e
> **todo** fim de episódio passou a ter um dono só no código (`takeEpisode`),
> incluindo sair da tela e recarregar a página. Desistência repetida no mesmo
> turno virou a anomalia `gave_up_repeatedly`.
>
> O `bi_cash` lê tudo isso: `drawer_by_operator` (bloqueios, tempo somado de
> gaveta aberta, pior episódio, destraves, buscas pelo PIN, sensor mudo,
> esquecimentos) e `drawer_anomalies`, que aponta o turno quando o padrão não
> fecha.
>
> ⚠️ **O limite honesto.** O agente do balcão roda NA máquina do caixa: quem tem
> a máquina tem o canal. Derrubar o agente, puxar o cabo da gaveta ou pôr um
> impostor na loopback respondendo `open: false` desliga a trava, e o navegador
> não tem como distinguir — o token que autentica o agente é entregue a ele.
> Isso é **indefensável no PDV, e a defesa é o reconhecimento**: cada manobra
> dessas deixa assinatura no livro, quase sempre como AUSÊNCIA. Um turno com
> dinheiro andando e zero `drawer_blocked` não é um balcão caprichoso; é um
> sensor que não estava falando, e é a anomalia `drawer_never_blocked`.

## Alternativas consideradas

- **Manter em `backstage` e o `shop` anunciar por signal**: consistente com a
  regra "signal para anunciar", mas para dinheiro o handler não registrado
  falha em silêncio; e mantém `Terminal`/`Shift` num app de superfície.
- **Levar para `shopman/shop`** (precedente ADR-019): fecharia a dependência,
  mas promoção foi para o orquestrador por ser política composta sobre cores;
  custódia de dinheiro é domínio com ledger, não política.
- **Absorver `Shift` no livro (event sourcing pleno)**: as constraints de
  unicidade de turno aberto exigem linha de estado; o turno é custódia, o livro
  é história.
- **Duas tabelas (dinheiro e eventos)**: é o desenho do PR #198; a mesma linha
  ganha duas identidades e "o que aconteceu, em ordem" vira união de tabelas.

## Referências

- [CASH-LEDGER-ARCHITECTURE.md](../plans/CASH-LEDGER-ARCHITECTURE.md), [CASHMAN-PLAN.md](../plans/CASHMAN-PLAN.md), [CORE-BOUNDARIES-AUDIT.md](../plans/CORE-BOUNDARIES-AUDIT.md)
- ADR-001 (cores e bridges), ADR-004 (refs string), ADR-011 (caixa; superada em parte), ADR-019 (precedente da seta invertida), ADR-021 (inventário de ledgers)
- `packages/stockman/shopman/stockman/models/move.py`, `packages/payman/shopman/payman/models/transaction.py`
