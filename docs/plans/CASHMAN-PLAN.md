# CASHMAN-PLAN: o livro-caixa do PDV como pacote do Core

> Plano de execução da arquitetura decidida em
> [CASH-LEDGER-ARCHITECTURE.md](CASH-LEDGER-ARCHITECTURE.md) (§3 desenho, §5
> decisões do dono, 2026-08-18). Este documento diz **o que fazer, em que ordem,
> e como provar**. O porquê mora no outro; não repita aqui.

## Objetivo

Substituir os três lugares onde o dinheiro do turno mora hoje (colunas do
`CashShift`, `CashMovement`, JSON do `Order.data.payment` com etiquetas de
turno) por **um pacote do Core, `cashman`**, com três modelos: `Terminal`
(aparelho), `Shift` (custódia, sem coluna de dinheiro) e `Entry` (livro
imutável, `amount_q` assinado, zero para evento sem dinheiro). O `payman` passa
a ser o livro de pagamentos **de todos os métodos** (`cash` e `external` viram
intents capturados na venda). O algoritmo de fechamento, o espelho da leitura
X/Z, a adoção de órfãs, as etiquetas no pedido, o `CashMovement` e o `POSEvent`
do PR #198 deixam de existir.

## Princípios que o plano obedece

- **Nunca por menor diff; zero gambiarra.** Cada WP entrega a forma final da
  sua peça, não um degrau.
- **Um dono por pergunta.** "Quanto há na gaveta" = `cashman`; "liquidou?" =
  `payman`; "como o pedido declarou o pagamento" = `Order.data.payment`.
- **Renames zeram tudo** (pré go-live): nada de alias `CashShift = Shift`,
  nada de `# formerly`. Permissões mudam de content type de verdade.
- **Migrações append-only**: nada de reset. O backfill é uma migração, e o
  algoritmo antigo roda **uma última vez** dentro dela.
- **Check verde não prova o merge**: todo WP com migração exige `migrate` de
  banco zerado **e** de banco com dados (fixture do backfill).
- **Fechamento cego** continua invariante: nenhuma projection de terminal soma
  o livro.

## Fora de escopo

- Autorizações de gerente que não tocam na gaveta (desconto acima do teto):
  são fato do pedido; lacuna registrada, tratada em outro plano.
- Trigger/permissão no Postgres para imutabilidade real: a guarda é no app,
  como no `Move`; documentado, não prometido.
- Reconciliação financeira além do check cruzado dinheiro (WP-7).
- Impressão fiscal, agente do balcão, hardware: não mudam de lugar.

## Mapa de dependências

```
WP-0 (decisões/ADR) ─┬─► WP-1 (cashman nasce) ─┬─► WP-3 (shop grava a venda) ─┐
                     │                         └─► WP-4 (backstage migra) ────┼─► WP-5 (backfill) ─► WP-6 (remoções) ─► WP-7 (reconciliação) 
                     └─► WP-2 (payman: cash/external) ─► WP-3                 └─► WP-8 (trava + B.I. sobre o livro)
```

WP-1 e WP-2 são paralelizáveis (worktrees separados). WP-3 e WP-4 também, depois
de WP-1/2. WP-5 é o ponto de junção e o mais delicado. WP-8 pode andar em
paralelo com WP-5 (só depende de WP-4).

Cada WP é **um PR** com base `main`, título/corpo em português explicando o
porquê, e a bateria de gates do fim deste documento. Nenhum merge sem o dono.

---

## WP-0: Fechar o #198 e escrever a lei

**Entrega**

1. **PR #198 fechado sem merge**, com comentário apontando para
   `CASH-LEDGER-ARCHITECTURE.md` §4 e para este plano. A branch fica: a trava
   do PDV (`useCashDrawer.readState`, `useDrawerLock`, `PosDrawerLockDialog`,
   endpoint de destrave, testes) é reaproveitada no WP-8 por cherry-pick.
2. **ADR-022** (`docs/decisions/adr-022-cashman-ledger.md`): decisão, invariantes,
   fronteira `cashman`×`payman`, o que supersede na ADR-011 (§3 e §5 daquela
   passam a apontar para cá; ADR-011 ganha "Superada parcialmente por ADR-022").
3. `docs/reference/data-schemas.md`: seção `POSEvent.payload` removida (nunca
   chega a existir); `CashShift.metadata` marcada "vai morrer no WP-6".

**Aceite**: ADR revisada pelo dono; #198 fechado; branch preservada.

---

## WP-1: `packages/cashman` nasce

**Entrega**

- `packages/cashman/` no molde do `payman` (`pyproject.toml` `shopman-cashman`,
  `shopman/cashman/{models,services,contrib/admin_unfold,tests,migrations}`,
  `apps.py`, `exceptions.py`). Registro em `pyproject.toml` raiz, `Makefile`
  (`test-cashman` **na cadeia de `make test`**; ver memória "teste fora do
  runner não existe"), `INSTALLED_APPS` (`shopman.cashman`,
  `shopman.cashman.contrib.admin_unfold`), `.venv` editable install, CI matrix.
- **Modelos** (§3.2/§3.3 do desenho, com §5.2):
  - `Terminal`: `ref`, `label`, `channel_ref`, `location_ref`, `is_active`,
    `metadata` (hardware continua aqui; `pos_hardware.py` do backstage lê),
    `created_at`, `updated_at`. Sem dinheiro (ADR-011).
  - `Shift`: `terminal` FK PROTECT, `operator` FK PROTECT, `opened_at`,
    `closed_at`, `status` (`open|closed|void`), **sem coluna de dinheiro, sem
    metadata**. `UniqueConstraint(operator, status=open)`,
    `UniqueConstraint(terminal, status=open)`. `Meta.permissions`:
    `operate_pos`, `audit_shift`, `adjust_shift`, `manage_operators`
    (codenames sem o `cash`: o app já é o caixa).
  - `Entry`: `shift` PROTECT, `operator` PROTECT, `approved_by` PROTECT null,
    `at`, `kind`, `amount_q` assinado, `order_ref`, `payment_ref`, `parent`
    FK self PROTECT null, `reason`, `payload`. Guarda `Move`-like (QuerySet
    `update`/`delete` levantam; `save` com pk levanta; `delete` levanta).
    `CheckConstraint` por tipo: `float_in`, `cod_settled`, `cash_in` > 0;
    `cash_out`, `refund` < 0; `sale` ≥ 0; `count`, `count_correction` livres;
    os demais = 0. Índices `(shift, id)`, `(operator, at)`, `(kind, at)`,
    `(at)`. `ordering = ["at", "id"]`.
- **Services** (`shopman/cashman/services/`), únicos escritores:
  - `open_shift(operator, terminal, float_q) -> Shift` (cria `Shift` +
    `float_in`, atômico; recusa se já há aberto por operador/terminal).
  - `record(kind, *, shift, operator, amount_q=0, ...) -> Entry` (valida sinal
    por tipo antes do banco, mensagem em pt-BR).
  - `close_shift(shift, *, counted_q, actor, notes) -> Entry` (grava `count`
    com `amount_q = counted_q − balance(shift)`, fecha; atômico; `select_for_update`
    no turno).
  - `correct_count(shift, *, delta_q, actor, reason) -> Entry` (`count_correction`
    com `parent`; exige turno fechado).
  - Consultas: `balance(shift, until=None)`, `expected_before_count(shift)`,
    `counted(shift)`, `difference(shift)` (soma de `count` + correções),
    `timeline(shift)`, `open_shift_for(operator)`, `open_shift_for_terminal(terminal)`,
    `change_requests(shift)` (dobra `change_*` por `parent`), `is_closed(shift_id)`.
- **Signals**: `shift_opened`, `shift_closed`, `entry_recorded` (para o
  backstage anunciar por SSE sem o pacote saber de SSE).
- **Admin contrib** (`contrib/admin_unfold`): `Terminal` (edição de config),
  `Shift` (readonly, inline `Entry` cronológica com "detalhe" por tipo),
  `Entry` **não** registrado sozinho (fica reachable pelo turno; o guard do
  menu do Admin não muda).
- **Testes** (`packages/cashman/shopman/cashman/tests/`): imutabilidade
  (QuerySet, instância), sinal por tipo, unicidade de turno aberto, `close_shift`
  reproduz esperado/contado/diferença, correção soma, `change_requests` dobra,
  fronteira (`test_import_boundaries`: nada de `shop`/`backstage`/outros cores
  fora de `contrib/`).
- Migração `cashman/0001_initial`.

**Aceite**: `make test-cashman` verde; `make test` inclui; pacote instala isolado
(`pip install -e packages/cashman` num venv limpo importa `shopman.cashman`).

---

## WP-2: `payman` recebe dinheiro e `external`

**Entrega**

- `PaymentService`: caminho **sem gateway** para `Method.CASH` e `Method.EXTERNAL`
  (o enum já tem os dois): `create_intent` + `capture` atômicos, `gateway=""`,
  `gateway_id=""`. Não é adapter novo (P7 do desenho: adapter só com 2+ impls
  reais); é um ramo do service. Refund de dinheiro = `PaymentTransaction(REFUND)`
  normal.
- `shop/services/payment.py::initiate` deixa de retornar cedo para
  `cash`/`external` **quando a coleta é no terminal**; para `collection=on_delivery`
  o intent nasce no acerto (WP-3). `intent_ref` volta em `Order.data.payment`
  como já acontece para pix/card (data-schemas.md).
- `payment_service.refund` deixa de ser "smart no-op" para dinheiro.
- Reconciliação financeira: só o necessário para não gritar falso positivo
  com intents `cash` (checks ancorados em gateway ignoram gateway vazio). O
  check cruzado com o `cashman` é WP-7.
- Testes em `payman` (service) e em `shop/tests` (initiate para cash cria intent
  capturado; storefront **não** muda: `cash`/`counter` do delivery continua sem
  intent até o acerto).

**Aceite**: `make test-payman`, `make test-shop`, `make test-storefront` verdes;
`docs/guides/payments.md` atualizado (tabela de métodos).

---

## WP-3: o `shop` grava a venda no livro

**Entrega**

- `shopman/shop/services/pos.py`:
  - `close_sale`: depois de o total selar (hoje `_reconcile_order_payment_to_total`),
    para cada tender com `collection=terminal`: intent no `payman` (WP-2) e
    `cashman.record("sale", shift=turno aberto do operador, amount_q=efeito em
    dinheiro, order_ref, payment_ref, payload={received_q, change_q, method})`.
    Tudo na mesma transação do commit. Sem turno aberto → recusa onde já recusa.
  - `cancel_recent_sale`/`reopen_recent_order_for_correction`: `refund`
    negativo no turno aberto de quem devolve, `parent` = `sale` original quando
    for o mesmo livro; a recusa "registre a devolução pelo gestor" morre.
  - Acerto de COD (`operator_orders.py`): `cod_settled` no turno de quem
    recebeu, com intent `cash` capturado no acerto.
  - **Param de entrada**: o `shift_id` continua vindo do servidor
    (`_open_cash_shift_for_request`), nunca do browser; passa a ser resolvido
    por `cashman.open_shift_for(operator)`.
- **Etiquetas morrem na escrita**: `pos.cash_shift_id`, `tenders[].cash_shift_id`,
  `payment.cod_cash_shift_id`/`cod_terminal_ref` deixam de ser gravadas.
  `pos.terminal_ref` fica (é dado do pedido). `data-schemas.md` atualizado
  (chaves marcadas removidas; leitura legada só no backfill do WP-5).
- `shopman/shop/adapters/pos.py`: `cash_shift_is_closed` some (o `shop`
  importa `cashman` direto). `upsert_tab`/`ensure_tab` (POSTab, backstage)
  ficam **por ora**; são outra seta invertida, fora deste plano (ver
  CORE-BOUNDARIES-AUDIT).
- Testes: `shop/tests` (venda cash grava `sale` com efeito certo; pix/card
  gravam `sale` com 0; troco; COD; cancel gera `refund`; sem turno recusa).

**Aceite**: `make test-shop` verde; nenhum teste do `shop` cria `backstage.CashShift`.

---

## WP-4: o `backstage` opera o turno pelo `cashman`

**Entrega**

- `shopman/backstage/services/pos.py` reescrito sobre `cashman.services`:
  `open_cash_shift` → `open_shift`; `register_cash_movement` → `record(cash_out|cash_in)`
  com `approved_by`; `register_drawer_opening` → `drawer_open`; `unlock_drawer`
  → `drawer_unlock`; `request/serve/cancel_change` → `change_*` com `parent`;
  `record_receipt_result` → `receipt_result` com `parent`; `close_cash_shift`/
  `close_blocking_shift` → `close_shift` (fechamento supervisório = `actor` ≠
  dono do turno, no payload do `count`).
- API (`api/operations.py`, `api/urls.py`): rotas de turno, sangria/suprimento,
  gaveta, troco e destrave **mantêm URL e corpo**. O que muda de nome muda
  inteiro (renames zeram tudo): `movement_id` → `entry_id` na resposta de
  `pos/cash/movement/`, e a rota do comprovante
  `pos/cash/movement/<movement_id>/receipt/` → `pos/cash/entry/<entry_id>/receipt/`,
  com o `pos-nuxt` acompanhando no mesmo PR (`usePosCashSession.lastMovementId`
  → `lastEntryId`, `actionHref` do comprovante), BE+FE atômico como no PR #67.
  Comprovante: `code_for(entry.pk)`; `cash_receipt.py` lê a linha + último
  `receipt_result` filho.
- Projections: `pos.py` (`cash_runtime`, `pending_change_requests`),
  `cash_session.py` **reescrita**: X = livro do turno aberto; Z = turnos
  fechados do dia; vendas por método = `payment_ref` das linhas `sale` →
  intents do `payman` (o `backstage` importa os dois). Blind count: a
  projection **não** expõe `balance`; teste existente continua.
- `closing.py::_cash_shift_summary`: calculado do livro no fechamento do dia
  (snapshot pode congelar; não é fonte viva). `payment_method_totals` vem do
  `payman` (WP-2), não de `iter_order_payments`; `iter_order_payments` fica
  só para o que é do pedido (fiscal), com docstring dizendo isso.
- Admin: `shopman/backstage/admin/cash_register.py` some; menu
  (`admin/navigation.py`) aponta para `admin:cashman_shift_changelist` e
  `admin:cashman_terminal_changelist`; "Movimentações de caixa" sai do menu
  (a movimentação é linha do turno; o grupo Auditoria **encurta**). Guards do
  Admin (`make admin`, `test_admin_navigation`, `test_admin_renders_with_rows`)
  verdes.
- Permissões: strings `backstage.operate_pos|audit_cashshift|adjust_cashshift|manage_operators`
  → `cashman.operate_pos|audit_shift|adjust_shift|manage_operators` em **todo**
  o código (61 ocorrências fora de testes), `permissions.py`, `setup_groups`
  (`shop_cash` passa a `("cashman", "shift", ...)`), RBAC docs.
- `pos_hardware.py`, `pos_terminal.py`, `pos_agent.py`: leem `cashman.Terminal`.
- `seed.py`: cria `Terminal`/`Shift`/`Entry`; flush usa `hard_delete(Entry)`
  antes de `Shift`/`Terminal`.
- B.I. `bi_cash.py`: quebra por operador = `count` + correções por operador;
  sangria/suprimento = `cash_out`/`cash_in`.
- Superfícies: `pos-nuxt`/`bi-nuxt` **não mudam contrato**; `npm run test` e
  `typecheck` como prova.

**Aceite**: `make test-backstage`, `make admin`, `ruff` verdes; `pos-nuxt`
test+typecheck verdes; nenhum import de `backstage.models.CashShift|CashMovement|POSTerminal`
fora de migrações.

---

## WP-5: backfill e corte

**Status: ENTREGUE (PR aberto em 2026-08-19; deploy em janela, ver abaixo).**

**Entrega (como ficou)**

- **Uma** migração, `backstage/0030_cashman_backfill_and_cut` (depende de
  `cashman/0001`, `backstage/0029`, `orderman`, `auth`, `contenttypes`): backfill
  + permissões + `DeleteModel` ×3 na mesma transação. Um corte, uma migração.
- `POSTerminal` → `Terminal` pelo `ref` (cria o que falta; se o do pacote já
  existe sem `metadata`, herda a configuração do aparelho). `CashShift` → `Shift`
  com **pk novo** (o pacote já tem turnos em staging desde o WP-3/4; o pk legado
  vai para o payload do `count`/`note`, e `Order.data.pos.cash_shift_id` é
  etiqueta morta que ninguém lê). Turno legado **aberto** no corte fecha sem
  contagem e ganha uma linha `note` dizendo isso.
- Por turno, em ordem cronológica (`at`): `float_in`; `sale`/`cod_settled` uma
  linha por pedido em dinheiro pelo **algoritmo do `close()` copiado** (adoção de
  órfãs em memória, sem escrever no pedido; pedido que já tem `sale` no livro
  novo não entra de novo); `cash_out`/`cash_in` por `CashMovement` com
  `receipt_result` filho; `drawer_open` e `change_requested`(+`served`/
  `cancelled` com `parent`) das listas do `metadata`; `count` com
  `amount_q = contagem cega − Σ do que entrou no livro`. O payload do `count`
  guarda `expected_q`/`difference_q` legados, o `reproduced_expected_q` do
  algoritmo e `divergent` (difere quando um pedido foi cancelado DEPOIS do
  fechamento: o livro é a verdade de hoje, não a foto de ontem).
- Permissões: `backstage.cashshift.{operate_pos, audit_cashshift,
  adjust_cashshift, manage_operators}` → `cashman.shift.{operate_pos,
  audit_shift, adjust_shift, manage_operators}` em grupos e usuários; o content
  type legado e as permissões dele somem.
- Código: `shopman/backstage/models/cash_register.py` apagado; `seed` sem o flush
  legado; docstrings sem `CashShift`.
- **Teste de migração** (`test_migration_cashman_backfill.py`, `MigrationExecutor`,
  SQLite e Postgres): `Σ` de cada turno == contagem cega ao centavo; uma linha por
  pedido em cada forma que o `close()` sabia somar (etiquetado, `tenders`,
  `cash_received_q`, COD, método); cancelado/depois do fechamento/cartão de fora;
  já-no-livro não duplica; `parent` de comprovante e troco; permissões movidas;
  tabelas sumidas. Reverso: `RunPython.noop` (as tabelas voltam vazias; o livro
  fica). `migrate` de banco zerado e `make test-migrations` verdes.

**Deploy (janela ~1h, caixa fechado)**: snapshot do banco; `migrate` no release;
`setup_groups` (idempotente, cinto e suspensório); conferir no Admin um turno
antigo com a linha do tempo populada. Se houver turno legado aberto, a `note`
grita e o dono decide o que fazer com a contagem que não houve.

---

## WP-6: remoções e docs

**Status: ENTREGUE (2026-08-19).** Resíduo de código já tinha saído nos WP-4/5 (o grep do aceite
só acha migrações, docs de decisão/histórico e nomes legítimos como `POSTerminalComponentProjection`
e `CashMovementRow`); este corte entrega `docs/guides/cashman.md`, glossário (seção Cashman),
ADR-021 (inventário com `cashman.Entry`), ADR-022 → Aceito, `CLAUDE.md` (12 apps),
`POS-CASH-DRAWER-PLAN` → `completed/` (superado no registro). O `HANDOFF-POS-EVENT-LOG.md` já não
existia no repo (o #198 fechou sem merge). Memória do projeto atualizada.

**Entrega**

- Zero resíduo: `CashShift`, `CashMovement`, `POSTerminal`, `_adopt_orphan_sale`,
  o algoritmo de `close()` (só vive na migração 0022), o espelho em
  `cash_session.py`, `shop/adapters/pos.py::cash_shift_is_closed`, chaves de
  etiqueta em `data-schemas.md`, `iter_order_payments` como fonte de caixa,
  `docs/plans/POS-CASH-DRAWER-PLAN.md` e `HANDOFF-POS-EVENT-LOG.md` (marcar
  concluídos/superados, mover para `completed/`).
- Docs: `docs/guides/cashman.md` (novo, molde do `payments.md`), `CLAUDE.md`
  (12 pacotes; linha do `cashman`), `docs/reference/glossary.md` (turno, livro,
  lançamento), ADR-021 (inventário de ledgers ganha `cashman.Entry`),
  `docs/reference/commands.md` se houver comando novo.
- Memória do projeto atualizada (arquivo `project_pos_event_log_and_drawer_lock`
  vira histórico; novo `project_cashman_ledger`).

**Aceite**: `grep -rn "CashShift\|CashMovement\|POSTerminal\|POSEvent"` só acha
migrações e docs de decisão/histórico.

---

## WP-7: reconciliação cruzada

**Entrega**

- `financial_reconciliation.py`: check `cash_ledger_mismatch`: por dia,
  `Σ PaymentTransaction(capture, method=cash) − Σ refund(cash)` ==
  `Σ Entry(sale|cod_settled|refund).amount_q` do dia (janela por `at`).
  Divergência = issue `error` com os dois números. Cash deixa de ser invisível.
- `terminal_intent_has_capture`/checks que hoje assumem "terminal = sem intent"
  revisados para o novo mundo.
- Testes de reconciliação com dinheiro.

**Aceite**: `make test-backstage` verde; `reconcile_financial_day` num dia com
vendas cash não gera falso positivo.

---

## WP-8: a trava da gaveta e o B.I. sobre o livro

> ✅ **A metade "B.I. sobre o livro" foi entregue pela fundação de dados do B.I.**
> ([BI-DATA-FOUNDATION-PLAN](BI-DATA-FOUNDATION-PLAN.md), P4, branch
> `feat/bi-cash-canonical`, 2026-08-19): `by_operator` com aberturas/destraves/troco,
> `drawer_by_hour`, contrato regenerado, `cash.vue`. Com o gate novo do dono: o painel de
> caixa exige `cashman.audit_shift` além de `view_bi`. A metade "trava da gaveta" (cherry-pick
> do #198 no PDV) segue neste WP.

**Entrega**

- Cherry-pick da branch do #198: `useCashDrawer.readState`, `useDrawerLock`,
  `PosDrawerLockDialog`, fiação em `index.vue`, testes do PDV — **sem alteração**.
- Servidor: `POST pos/cash/drawer-unlock/` (WP-4 já expõe `unlock_drawer` →
  `drawer_unlock` com `approved_by`, `payload.drawer_raw`); action `drawer_unlock`
  na projection.
- B.I. `bi_cash.py`: `by_operator` ganha `drawer_openings`, `drawer_unlocks`,
  `change_requests` (contagem de `Entry` por tipo); `drawer_by_hour`; contrato
  regenerado (`export_bi_schema`); `bi-nuxt/cash.vue` como no #198.
- Regras da trava **inalteradas** (iniciar; sem carência; só quando sabe; um
  destrave, uma venda).

**Aceite**: `pos-nuxt` e `bi-nuxt` test+typecheck; `test_bi_schema_export`.

---

## WP-9: o troco da entrega sai e volta pelo livro

**Status: ENTREGUE (PR aberto em 2026-08-19).** Como ficou: `courier_in` é ≥ 0 (voltou zero
também fecha o ciclo), `parent` só quando o acerto é no mesmo turno (senão `order_ref` +
`payload.courier_out_id`), o valor é exigido pelo SERVIDOR no despacho (409 `change_out_required`
com a sugestão) e no acerto (400), e o gestor pergunta antes (diálogo no despacho e campo no
acerto); despacho que pede troco fica fora do lote de avançar. Reconciliação: `courier_*` fora
do `cash_ledger_mismatch` por construção + `warning` `courier_change_unsettled`. A custódia da
maquininha (`Order.data.courier.equipment`) NÃO entrou neste corte.

**O problema (medido no código, 2026-08-19):** a loja coleta o pedido de troco
no checkout do delivery (`change_for_q`, em `Order.data.payment`, escrito por
`storefront/api/views.py` e `intents/checkout.py`) e **ninguém lê depois**: não
está no card da expedição (`projections/order_queue.py`), não chega ao
entregador (orders-nuxt), não entra no caixa. O entregador descobre na porta.
E o troco que ele leva da gaveta ao sair não tem linha: a gaveta fica
fisicamente desfalcada enquanto ele está na rua (contagem cega nesse intervalo
acusa falta falsa) e, quando volta, o `cod_settled` lança só o total da venda;
o troco que voltou "aparece" sem explicação.

**Entrega**

- `cashman.Entry.Kind` ganha dois tipos, espelho um do outro, com `order_ref`
  (ou lista de pedidos no payload quando um entregador sai com vários):
  - `courier_out` (< 0): troco que SAIU da gaveta com o entregador, na hora do
    despacho. Não exige segunda assinatura (é rotina do despacho, não exceção),
    mas exige turno aberto de quem despacha e `order_ref`.
  - `courier_in` (> 0): o que VOLTOU de troco não usado, no acerto do
    entregador. `parent` = o `courier_out` correspondente.
  - `cod_settled` continua sendo a venda (+total), como hoje. Saldo do turno
    verdadeiro em todo instante: `float − troco levado + venda + troco de volta`.
- `CheckConstraint` do sinal por tipo, `sign_allows`, `services.record` e os
  testes do pacote acompanham. Migração `cashman/0002` (só choices/constraint).
- `shop/services/operator_orders.py`: `dispatch_delivery` (ou o ponto em que o
  pedido vai para `dispatched`) aceita `change_out_q` e grava `courier_out` no
  turno aberto de quem despacha; `settle_delivery_cash` aceita `change_back_q`
  e grava `courier_in` com `parent` no mesmo `atomic` do `cod_settled`.
  Sugestão de troco = `max(0, change_for_q − total_q)`; o operador confirma ou
  corrige (levou menos porque tinha nota quebrada).
- `projections/order_queue.py` + orders-nuxt: o card de entrega mostra
  "Cliente paga com R$ 50,00 (levar R$ 20,00 de troco)" e o despacho pede
  confirmação do valor levado; o acerto mostra "voltou R$ X de troco".
- **Equipamento que sai com o entregador (maquininha):** é custódia de
  aparelho, não de dinheiro, então NÃO mora no `cashman`. Mora no mesmo gesto:
  o despacho registra o que saiu (`Order.data.courier.equipment`, lista de refs
  de uma catálogo curto configurado no canal de entrega, ex.
  `["maquininha-01"]`; documentar em `data-schemas.md`) e o acerto marca o que
  voltou. "Onde está a maquininha agora" é derivado: pedido despachado e não
  acertado que a levou; aparece no card da expedição e no acerto. Sem tabela
  nova; se um dia houver frota, aí se discute `Fulfillment` (ver
  CORE-BOUNDARIES-AUDIT §3, item 5).
- `data-schemas.md`: `change_for_q` deixa de ser dado morto (leitores
  declarados); tipos novos na tabela do `Entry.payload`.
- WP-7: o check `cash_ledger_mismatch` exclui `courier_out`/`courier_in` (não
  são pagamento; são custódia temporária do entregador), e ganha o espelho
  `Σ courier_out + Σ courier_in` por pedido/dia como alerta `warning` quando
  o troco saiu e não voltou nem foi acertado.

**Aceite**: pacote, shop, backstage, orders-nuxt verdes; fixture "entregador
sai com R$ 20 de troco de dois pedidos, volta com R$ 5" prova o saldo da gaveta
em cada passo; `migrate` de banco zerado.

---

## WP-10: conta do cliente (acerto semanal/mensal)

**Status: ENTREGUE (PR aberto em 2026-08-19).** Como ficou: Payman `Method.ACCOUNT` +
`charge_to_account` (authorized = deve) + `capture(gateway_data=)` + `account_balance_q`/`account_balances`
(derivado); `cashman.account_settled` (0004); `shop/services/house_account.py` (elegibilidade lida de
`Customer.metadata.house_account`, acerto FIFO por venda inteira, dinheiro grava Payman+livro juntos;
cancel da venda em conta cancela o intent); Admin do cliente com checkbox "Conta na casa"; PDV: o lookup
diz `house_account`/`account_balance_q`, "Em conta" só aparece para esse cliente, a antesala lista
saldos e recebe o acerto (`GET pos/accounts/`, `POST pos/accounts/<ref>/settle/`, sem PIN: entrada);
reconciliação inclui captura de `account` com `settled_with=cash` × `account_settled`; B.I. do caixa ganha
`accounts` (vendido em conta, acertado, em aberto hoje, maiores saldos) e `by_operator.account_settled_q`.
Fora, como previsto: juros, limite, cobrança automática, extrato por WhatsApp.

**O problema:** não existe. O Payman não tem método que expresse "deve"; a
fidelidade do guestman é ponto, não crédito. Hoje a única forma de registrar
uma venda "em conta" seria `external` ("recebido fora"), que é mentira. O
fenômeno existe (alguns clientes antigos acertam por período) e não se
divulga: é por cliente, desligado por padrão.

**Desenho (cabe no que já existe, sem tabela de saldo):**

- **Payman**: método `account` ("Em conta"). O intent nasce `authorized`
  ("deve"; a venda aconteceu, a obrigação está reconhecida) e só vira
  `captured` no acerto ("pagou"). É a máquina de estados que o Payman já tem,
  sem gateway (`gateway=""`), no mesmo ramo do `settle` mas parando em
  `authorized`. Saldo devedor do cliente = Σ dos intents `account` autorizados
  e não capturados, por `customer_ref` (via `Order`). **Derivado, não tabela.**
- **Guestman**: elegibilidade no cliente (`CustomerGroup` "Conta" ou flag em
  `Customer.metadata.house_account`, documentada em `data-schemas.md`),
  desligada por padrão; só o Admin dá.
- **Shop**: tender `account` no `close_sale` só quando o cliente identificado
  é elegível (recusa com `PosIntentError` senão); grava linha `sale` com efeito
  zero (nada entrou na gaveta) e `payload.method = account`; `payment.timing`
  do PDV é `external`, então o pedido segue normalmente; fiscal na venda, como
  hoje.
- **Acerto** (`shop/services/payment.py::settle_account(customer, amount_q,
  method, shift, actor)`): captura os intents `account` mais antigos do
  cliente até o valor (FIFO), na mesma transação em que, se for dinheiro,
  grava `account_settled` (+valor) no turno de quem recebeu (tipo novo no
  `cashman`, irmão do `cod_settled`); pix/cartão via gateway ou atestado.
  Acerto parcial permitido (captura parcial = intents inteiros até o valor; o
  resto fica autorizado).
- **Backstage/PDV**: tender "Em conta" visível só para cliente elegível;
  tela de acerto no gestor (lista de clientes com saldo, histórico, botão
  "acertar" com método); na antesala, o acerto em dinheiro passa pela gaveta
  aberta, sem PIN: entrada de dinheiro não exige segunda assinatura (o
  suprimento também não); só saída exige.
- **B.I.**: `by_operator`/dia ganham `account_sales_q` e `account_settled_q`;
  relatório de saldos em aberto por cliente (`audit_shift`).
- **Reconciliação (WP-7)**: `account` autorizado não entra em `cash_ledger`
  (não é dinheiro); no acerto em dinheiro, `account_settled` entra no `Σ` do
  livro e a captura do intent no `Σ` do Payman, e batem.
- **Fora**: juros, limite de crédito, cobrança automática, extrato ao cliente
  pelo WhatsApp (ideias; só com gatilho).

**Aceite**: venda em conta recusada para cliente não elegível; venda em conta
não mexe na gaveta; acerto em dinheiro grava os dois livros juntos; acerto
parcial deixa o resto autorizado; B.I. e reconciliação quietos; migrações
`payman/000N` (choices) e `cashman/000N` (tipo), `migrate` de banco zerado.

**Ordem**: depois do WP-5 e do WP-9 (o WP-9 é menor e destrava a dor que já
existe no delivery; o WP-10 é feature nova).

---

## Gates de todo WP

```bash
make test                # cadeia completa (inclui test-cashman a partir do WP-1)
make admin
ruff check packages/ shopman/ config/ scripts/
.venv/bin/python manage.py makemigrations --check --dry-run
rm db.sqlite3 && .venv/bin/python manage.py migrate --noinput     # banco zerado
```

Superfícies tocadas: `npm run test` **e** `npm run typecheck` no app. Em
worktree: `PYTHON=` e `PYTHONPATH=` explícitos (ver
`reference_worktree_gate_recipe`), uma suíte por chamada.

⚠️ Desde 2026-08-18 o repositório é `nelsonboulangerie/django-shopman`, com
**fila de merge** e `strict` desligado, e `Testes (test-backstage)` **não
bloqueia mais** o merge. Consequências para este plano: (1) o `migrate` de
banco zerado depois do rebase é o **único** check que prova colisão de
migração, e é obrigatório antes de entrar na fila; (2) quem toca `backstage`
(WP-4, WP-5, WP-7, WP-8) **olha o resultado do `test-backstage` no CI à mão**
antes de pedir merge, porque ninguém mais vai ser barrado por ele.

## Riscos e como cada um é tratado

| Risco | Tratamento |
|---|---|
| Backfill divergir do que o `close()` calculou | teste de `Σ` ao centavo sobre fixture realista (WP-5); o algoritmo copiado para a migração é o **mesmo** código, congelado |
| Permissões: grupos perderem `operate_pos` no deploy | migração move as `Permission` rows por content type **antes** do `post_migrate`; `setup_groups` depois; smoke de login+venda no staging |
| Duas migrações `backstage/0022` (aconteceu 3× nesta semana) | WP-5 é o único WP com migração de `backstage`; WP-1 só cria `cashman/0001`; rebase antes de merge |
| Venda em voo no instante da virada | migração roda no `release` (PRE_DEPLOY) com o app parado; sem etiqueta nova gravada depois do WP-3 |
| Fechamento cego vazar `balance` na projection | teste existente de blind count mantido; `cash_session.py` reescrita sem campo de esperado |
| `payman` com intent `cash` confundir reconciliação | WP-2 ajusta os checks ancorados em gateway; WP-7 adiciona o cruzado |
| Perf: `Σ` por turno em listas do Admin | `annotate` no `get_queryset`; sem cache até medir |

## Ordem sugerida de execução (sessões paralelas)

1. WP-0 (dono + uma sessão): meio dia.
2. WP-1 ‖ WP-2 (dois worktrees).
3. WP-3 ‖ WP-4 (dois worktrees), rebase sobre WP-1/2 mergeados.
4. WP-5 (uma sessão, com o dono por perto no deploy).
5. WP-6 ‖ WP-7 ‖ WP-8.
6. WP-9 (troco da entrega), depois WP-10 (conta do cliente): descobertos em
   2026-08-19 ao revisar os fenômenos cotidianos; o WP-9 fecha uma lacuna
   (dado coletado e jogado fora), o WP-10 é feature nova e desligada por
   padrão. Lição da fila de merge: **sem PR empilhado**, cada WP nasce do `main`.

Cada sessão nova lê **este arquivo** e o desenho antes de qualquer linha
(memória `feedback_plan_in_repo`: planos moram no repo; ninguém inventa WP).
