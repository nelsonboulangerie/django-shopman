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
- API (`api/operations.py`, `api/urls.py`): **URLs iguais**, contratos JSON
  iguais (`movement_id` passa a ser `entry_id`; a superfície só relaia).
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

**Entrega**

- Migração `backstage/0022_cashman_backfill` (depende de `cashman/0001` e do
  último `backstage`): `RunPython` que, para cada `POSTerminal` → `Terminal`
  (mesmo `ref`), cada `CashShift` → `Shift` (**mesmo pk**, para preservar
  `Order.data.pos.cash_shift_id` histórico como leitura), e por turno:
  `float_in` (`opening_amount_q`), `sale`/`cod_settled` rodando **o algoritmo de
  `close()` uma última vez** (copiado para dentro da migração; é o único lugar
  em que ele sobrevive), uma linha por `CashMovement` (`cash_out`/`cash_in`, com
  `receipt_result` filho quando houver resultado), `count` com
  `amount_q = blind_closing − expected` para turnos fechados, `drawer_open`/
  `change_*` das listas do `metadata`. Sem reverse (voltar apagaria a trilha).
- Migração de **permissões**: `Permission` rows de `backstage.cashshift`
  (`operate_pos`, `audit_cashshift`, `adjust_cashshift`, `manage_operators`)
  movidas para o content type `cashman.shift` com os codenames novos, **antes**
  do `post_migrate` criar duplicatas; grupos mantêm as FKs. Depois do deploy:
  `setup_groups` (idempotente) como cinto e suspensório.
- Migração `backstage/0023_drop_cash_models`: `DeleteModel` `CashMovement`,
  `CashShift`, `POSTerminal`; `POSEvent` **não existe** (o #198 não entrou).
- **Teste de migração** com fixture realista (turnos fechados com vendas cash
  tagueadas e não tagueadas, COD, sangria com comprovante, pedidos de troco,
  aberturas): para todo turno fechado, `Σ` reproduz `expected_amount_q`,
  `blind_closing_amount_q` e `difference_q` originais **ao centavo** (critério
  da ADR-011: "dados históricos migram sem alteração financeira"). É o teste
  que autoriza o deploy.
- `migrate --noinput` de banco zerado **e** de banco com a fixture; `makemigrations --check`.

**Aceite**: os dois `migrate` verdes; teste de `Σ` verde; `showmigrations` mostra
`cashman 0001` antes de `backstage 0022`.

**Deploy**: uma janela; migrações rodam no `release`; depois `setup_groups`;
conferir no Admin um turno antigo com a linha do tempo populada.

---

## WP-6: remoções e docs

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

Cada sessão nova lê **este arquivo** e o desenho antes de qualquer linha
(memória `feedback_plan_in_repo`: planos moram no repo; ninguém inventa WP).
