# Backstage ↔ operator-surfaces contract audit

> ⚠️ **SEVERIDADE REVISADA — leia [`verify-03-backstage.md`](verify-03-backstage.md) antes de agir por este laudo.**
> 
> Um passe de refutação em 01/09 atacou cada P0 deste arquivo com uma régua única
> (P0 = perde dinheiro, corrompe dado, viola segurança, ou impede tarefa central sem
> contorno). **11 P0 alegados → 2 sobreviveram.** Nove foram rebaixados por severidade (o fato costuma estar certo; a consequência, não). Nenhum foi refutado por inteiro.
> 
> As contagens NO CORPO deste arquivo são as originais e estão infladas. O fato de
> cada achado quase sempre se sustenta; a **severidade** não.

Scope: `shopman/backstage/` (Django, `/api/v1/backstage/` + SSE `/events/`) against
`surfaces/{pos,kds,orders,production,hub,marketing,bi,purchase}-nuxt` and `surfaces/operator-kit`.

Method: every route in `shopman/backstage/api/urls.py` enumerated with method/permission/request/response/
error branches; every projection key enumerated and marked for conditional emission; every frontend
consumer (`app/composables`, `app/presentation`, `app/pages`, `app/components`, `server/`) diffed against it.
Read-only — no tests were executed. Everything below was confirmed by reading code; nothing is inferred.

**Headline correction to `docs/plans/fallbacks-perigosos-go-live.md` item 18.** The claim that
`Action.idempotency` is "purely declarative and nothing reads it" is now **half-stale**:

- **Backend, cash: TRUE protection exists.** `shopman/backstage/api/operations.py:2170` `_cash_idempotent`
  wraps 8 cash mutations in `run_idempotent_mutation` keyed on `client_request_id`. Verified at
  `operations.py:2281, 2324, 2366, 2691, 2734, 2772, 2812, 2874`.
- **Backend, everywhere else: still purely declarative.** No order, KDS, production, purchase-request,
  campaign, closing or tab endpoint reads it. `shopman/shop/tests/test_action_idempotency_contract.py`
  enforces only that the *declaration* exists — it scans source with AST and never exercises a request.
- **Frontend: purely declarative, in all seven apps.** `surfaces/pos-nuxt/app/presentation/actions.ts:68`
  copies `idempotency` into the affordance and **nothing branches on it**. The only real branch in the
  repo is on the *customer* side (`surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue:234,263`).
  Idempotency keys in the operator apps are hardcoded per composable
  (`usePosCashSession.ts:104`, `usePosSale.ts:1094`) and absent everywhere else.
- **Consequence:** an action that declares `idempotency="required"` but whose composable forgets the key
  fails silently and permanently. Per-mutation double-submit consequences are tabulated in
  "Idempotency reality table" below.

Counts: **11 P0 · 32 P1 · 36 P2.**

---

## P0

### P0-1 — POS comanda save is last-writer-wins with no version check: items silently vanish
`shopman/backstage/api/operations.py:3003-3024` (`POSTabSaveView`) → `shopman/shop/services/pos.py:971-1018`
(`save_pos_tab`) → `shopman/shop/services/pos.py:1994-1998` (`_replace_session_ops`).
Frontend: `surfaces/pos-nuxt/app/composables/usePosSale.ts:1345`.

`_replace_session_ops` emits a `remove_line` for **every** existing line and re-adds whatever the client
sent. There is no `version`, no `If-Match`, no `updated_at` guard, no `select_for_update` on the session,
and the request body carries no revision token. Grep for `claimed_by|locked_by|lease|If-Match|etag|version`
across `operations.py`, `shop/services/pos.py` and `backstage/models/pos.py` returns nothing relevant.

Repro (two tills; the code and `resolve_terminal`'s docstring both assume Nelson will have two):
operator A opens "Mesa 5" on till 1 at 10:00 and adds 3 items; operator B has "Mesa 5" open on till 2
from 09:58, adds 1 item at 10:01, taps "Guardar". Mesa 5 now contains only B's snapshot. A's three items
are gone from the customer's bill and nothing on either screen says so. The only trace is
`_audit_line_diff` (`shop/services/pos.py:1016`), an audit event no operator ever sees.
The same window exists single-till whenever the comanda is open in two tabs, or on the POS and the
`/display` window.

Fix: carry a monotonic revision in `build_open_tab` (the session already has `last_touched_at`), require it
in the save payload, and 409 with `{"detail": …, "error": {"code": "tab_stale"}}` on mismatch. The POS
already knows how to reopen a dialog on an `error.code` (`usePosCashSession.ts:113`).

### P0-2 — The cash shift cannot be closed the day a second drawer is registered
`shopman/backstage/api/operations.py:2309` (`POSCashCloseView`) reads `request.data.get("terminal_ref")`
**only** — unlike the other nine cash views, which use `_terminal_do_pedido(request)`
(`operations.py:2639-2649`) and fall back to the station cookie.
Frontend: `surfaces/pos-nuxt/app/composables/usePosCashSession.ts:132-138` sends
`{closing_amount, notes}` and **no `terminal_ref`**.
Resolver: `shopman/backstage/services/pos.py:773-777` — `strict=True` + 2 active terminals →
`POSTerminalAmbiguous` → `_falha_do_caixa` → 409 `{"detail": "Mais de um caixa ativo…", "field": "terminal_ref"}`
(`operations.py:2165-2166`).

Repro: the manager registers `balcao-2` in Admin → Equipamentos. Opening the shift still works
(`openCashShift` sends `terminal_ref: pos.value?.terminal_ref`, `usePosCashSession.ts:127`). Closing it
409s forever, and the POS has no terminal picker and no field named `terminal_ref` on the closing panel.
This is precisely the "não havia saída pela UI" trap `resolve_terminal`'s own docstring
(`backstage/services/pos.py:729-742`) says was fixed — it was fixed for open and left open for close.

Fix: `POSCashCloseView` must use `_terminal_do_pedido(request)`, and `closeCashShift` should send
`terminal_ref: pos.value?.terminal_ref` for symmetry with open.

### P0-3 — `/api/v1/backstage/closing/` serves the cash *apuração* to the role the house explicitly denies it
`shopman/backstage/projections/closing.py:143,167,429-436` → `shopman/backstage/services/closing.py:391-446`.
Gate: `shopman/backstage/api/operations.py:1070` — `backstage.perform_closing`.

`cash_shift_summary` emits `expected_amount_q` (`services/closing.py:426`), `difference_q` (`:427`),
`blind_closing_amount_q` (`:425`) and `payment_method_totals` (`:445,449-493`).
`shopman/shop/management/commands/setup_groups.py:165` gives *Gerente* `perform_closing`;
`setup_groups.py:239-241` explicitly withholds `audit_shift` — "Quem sabe o esperado não conta às cegas".
`POSCashReportView` gates the identical numbers behind `cashman.audit_shift`
(`operations.py:2906`) and its docstring (`:2895-2899`) says revenue-by-method is not visible
"nem para o gerente". `shopman/backstage/tests/test_cash_audit_policy.py:150-166` calls the same leak
through Admin "o P0". This route is the door that was left open.

Frontend exposure: `surfaces/pos-nuxt/app/pages/session/index.vue:62-65` fetches the full closing
projection **on the cash-session page whose "Fechar caixa" panel is the blind count**
(`session/index.vue:911-978`); `session/closing.vue:46` fetches it again. Neither renders it
(`app/types/closing.ts:48-62` doesn't declare the key) — but it is in the browser payload and
SSR-serialised into `__NUXT_DATA__` on `/session/closing`.

Repro: user in group *Gerente* only. `curl -b session /api/v1/backstage/pos/cash/report/` → 403.
`curl -b session /api/v1/backstage/closing/` → 200 with `closing.cash_shift_summary.totals.expected_amount_q`.

Fix: strip `cash_shift_summary` at the view, or gate it on `("backstage.perform_closing","cashman.audit_shift")`.
The persisted `DayClosing.data` snapshot can keep everything — its only reader
(`projections/bi_cash.py:243`) is already behind `view_bi` + `audit_shift`. Add the counterpart of
`test_cash_audit_policy.py` for this route.

### P0-4 — On a sold-out day the day cannot be closed at all
`shopman/backstage/projections/closing.py:246-252` builds items only from `Quant` with `_quantity__gt=0`,
so a fully sold-out day yields `items=()`, `has_items=False` (`:190-191`). The service is fine with it
(`shopman/backstage/services/closing.py:39-97` just skips the loop).
`surfaces/pos-nuxt/app/pages/session/closing.vue:338` wraps the whole submit block in
`v-if="closing.has_items && !closing.already_closed"`, and
`surfaces/pos-nuxt/app/presentation/closing.ts:60` (`if (!items.length) return false`) disarms the CTA
independently. The page shows "Nada em estoque vendável para contar" (`closing.vue:307`) and no button.

There is no other surface: the Admin/Unfold closing screen was removed in WP-ADM-3
(`shopman/backstage/tests/test_day_closing_blind_count.py:36-39`) and `perform_day_closing` has exactly
one caller (`operations.py:1090`). For a bakery whose model is selling out, the day it sells out is the
day `production_summary`, `cash_shift_summary`, `reconciliation_errors` and the reconciliation's
`day_closing_missing` check (`services/financial_reconciliation.py:234-243`) silently never happen.

Fix: drop `has_items` from `closing.vue:338`'s condition and return `true` for an empty list in
`presentation/closing.ts:60`. The confirm dialog's copy already covers it.

### P0-5 — Any failed poll blanks the entire kitchen board and the customer TV
`surfaces/kds-nuxt/app/composables/useKdsBoard.ts:16-24` and `useKdsCustomerBoard.ts:12-15`.
Neither `useFetch` passes `default`, and Nuxt's error branch
(`surfaces/kds-nuxt/node_modules/nuxt/dist/app/composables/asyncData.js:376`) sets
`data.value = unref(options.default())` → `undefined` on **every** failed refresh.
Chain: `data` → `undefined` → `board` (`useKdsBoard.ts:24`) → `null` → `view` (`:25`) → `null` →
`pages/[ref].vue:339` `v-if="view"` fails → every ticket disappears.

The code believes the opposite: `[ref].vue:325-326` states *"Erro com dados em cache NUNCA apaga o
board"*, and the amber branch at `[ref].vue:333-338` (`v-else-if="error && view"`) is **dead code** —
`error` and `view` can never both be truthy.

Repro: kitchen Wi-Fi drops for one 15s cycle → all cards vanish → 15s later they return. On the public
TV (`pickup.vue`) there is no banner at all: a customer whose order is READY watches their number
silently disappear.

Fix: keep the last good projection in a `shallowRef` and feed it back through `default`; then
`[ref].vue:333-338` becomes live and keeps the promise its comment makes.

### P0-6 — Unknown or deactivated KDS station → HTTP 500 outside the error dialect, unrecoverable
`shopman/backstage/projections/kds.py:183` — `KDSInstance.objects.get(ref=…, is_active=True)`.
`DoesNotExist` is not an `APIException`/`Http404`, so `shopman/shop/api_errors.py:55-57` returns `None`
and Django emits a 500 with no `{detail, field, errors}`. Caller `shopman/backstage/api/kds.py:68-70`
has no `try`, unlike every ticket route below it.

Repro: the manager unticks `KDSInstance.is_active` while a tablet has that board open. Every 15s poll
now 500s; combined with P0-5 the tablet blanks and shows "Falha ao carregar o board. Reconectando…"
**forever**, blaming the network for a configuration change.
`surfaces/kds-nuxt/tests/e2e/guards.spec.ts:36-38` documents that any path resolves as a station ref, so
a URL-bar typo reaches the same 500. No backend test covers it.

Fix: `except KDSInstance.DoesNotExist: return Response({"detail": "Estação não encontrada ou desativada."}, status=404)`
and a distinct 404 branch on the frontend.

### P0-7 — "Cancelar (gerente)" is a dead end on every paid order
Backend gate: `shopman/backstage/api/operations.py:1322-1333` — when `policy.requires_approval`,
`OrderCancelView` calls `validate_manager_override(request.data.get("manager_approval"), …)`.
Policy: `shopman/shop/services/cancellation.py:160-165` — `requires_approval=True` for **any** order with
sufficient captured payment **or** payment status `unknown` (also the fail-closed default at `:157-158`).
Projection: `shopman/backstage/projections/order_queue.py:395-399` returns
`can_cancel=True, cancel_requires_approval=True`. UI renders the button:
`surfaces/orders-nuxt/app/pages/[ref].vue:243-246`.
The write: `surfaces/orders-nuxt/app/composables/useOrderDetail.ts:54` —
`cancel(reason, cancellation_code) => act("cancel", { reason, cancellation_code })`.
**`manager_approval` is never in the body**; grep confirms zero occurrences of `manager_approval` in
`surfaces/orders-nuxt`.

Repro: a pix-paid order in `accepted`/`preparing` → `/WEB-…` → "Cancelar (gerente)" → type reason →
Cancelar → 422 → red toast "Esta operação exige aprovação gerencial.", dialog stays open, no PIN field.
**Cancelling a paid order from the Gestor is impossible.**

Fix: add the manager PIN/badge challenge to `OrderReasonDialog` gated on
`order.cancel_requires_approval`, thread it into the body, and react to
`httpErrorCode(err) === "manager_approval_required"|"manager_approval_invalid"`.
`surfaces/pos-nuxt/app/composables/usePosCashSession.ts:113` is the working reference.

### P0-8 — Purchase money parser diverges from the server by 100× on thousands-dot input
FE: `surfaces/purchase-nuxt/app/presentation/purchase.ts:55-62` —
`text.includes(",") ? strip dots, comma→dot : text`, then `Math.round(Number(x)*100)`.
BE: `shopman/backstage/services/purchase.py:793-801` — three branches: comma present → dots are
thousands; exactly one dot with ≤2 decimals → decimal; **otherwise dots are thousands**.

Repro: "Receber" → "Valor total (R$)" (`purchase-nuxt/app/pages/index.vue:999`, free text) type `1.250`.
Screen shows **R$ 1,25** (and feeds `receiptTotalCostQ` at `usePurchaseDesk.ts:532` and the confirm
summary); the server writes **125000 centavos = R$ 1.250,00** to `Move`/`SupplierMaterialCost`
(`purchase.py:872-875`, `:378`). `1.234.567` is worse: FE → `NaN` → `0` → renders `—`; BE → `123456700`.
`surfaces/purchase-nuxt/tests/purchase.test.ts:791-824` covers `12.50`, `12.5`, `360.00`, `1.250,00`,
`1250.50` — never the diverging case.

Fix: port the server's three-branch rule verbatim and add `"1.250"`, `"12.345"`, `"1.234.567"` to both
suites as a shared table.

### P0-9 — Every broad backstage failure is invisible in production logs and returns 400
`shopman/backstage/api/operations.py` has **24** `except Exception as exc:` blocks, **25** of which log
via `logger.debug(..., exc_info=True)` and return `Response({"detail": str(exc) or "…"}, status=400)`.
`config/settings.py:1443,1448` set the production log level to `INFO`, so **none of them appear in the
logs**. Verified sites include `POSTabCreateView` (`:2962`), `POSTabOpenView` (`:2987`),
`POSTabSaveView` (`:3017`), `POSTabMoveLinesView` (`:3080`), `POSTabRenameView` (`:3107`),
`POSTabFireView` (`:3130`), `POSTabUnfireView` (`:3157`), `POSCashOpenView` (`:2277`),
`POSCashCloseView` (`:2320`).

Consequence: a DB integrity error, a null deref inside a service, an unhandled `POSError` — all reach the
operator as a 400 carrying a raw Python exception string ("your request is wrong") and leave zero trace
for whoever debugs it. Go-live day, on a tablet nobody can attach a debugger to, the only evidence of an
internal failure will be the operator's memory of a Portuguese-less toast.

Fix: `logger.exception(...)` (ERROR) in every one of these blocks, and return 500 (not 400) when the
exception is not a domain error. `_falha_do_caixa` (`operations.py:2156-2167`) already models the
distinction correctly for one case.

### P0-10 — `quick-finish` has no idempotency on its plan leg: duplicate fornada, double stock consumption, double `MAKE`
`shopman/backstage/services/production.py:154` — `apply_quick_finish` calls `production_core.quick_plan(...)`,
which unconditionally `CraftPlanning.plan()`s a **new** WorkOrder
(`shopman/shop/services/production.py:190-213`), then hands its fresh `pk` to `apply_finish`
(`backstage/services/production.py:160`). The finish leg *is* protected — `_finish_idempotency_key`
(`backstage/services/production.py:462-490`) hashes `{work_order.pk, finished, wasted}` — but the pk is
new on every call, so the key is new on every call. **The guard is structurally unreachable on this path.**
Frontend: `surfaces/production-nuxt/app/composables/useQcKiosk.ts:62-73` posts
`{recipe_id, quantity, partition, force}` — no client key, no `expected_rev`. The only protection is an
in-process `submitting` ref (`useQcKiosk.ts:38`), which a reload discards.

Repro: Expedição → ⋯ → "Fornada avulsa" → pick a recipe → Confirmar. The POST commits; the response is
lost (kiosk wifi, BFF restart, tab reload). The baker taps Confirmar again. Two `WorkOrder`s, two
`finish` events, two `production_changed(action="finished")` fan-outs → `craftsman/contrib/stockman`
writes the `kind=MAKE` ledger **twice** and consumes the recipe's insumos twice. Nothing in the UI or
the ledger says it was one bake.

Fix: derive the idempotency key **before** planning, from `(recipe_id, quantity, partition, target_date,
actor)`, and look for an existing `WorkOrderEvent` with that key before calling `quick_plan`; or accept a
client key on `WorkOrderQuickFinishView` (`api/operations.py:2043`) and scope `quick_plan` under the same
`orderman.IdempotencyKey` table the cash endpoints already use.

### P0-11 — Four production write endpoints return HTTP 500 (Django HTML) where the contract requires 400/404
Two distinct leaks, both confirmed.

*(a) `ValueError` uncaught on quick-finish / void / advance-step / oven.* `WorkOrderPlanView`
(`api/operations.py:1930`), `WorkOrderStartView` (`:1969`) and `WorkOrderFinishView` (`:2012`) all have
`except ValueError → 400`. `WorkOrderQuickFinishView` (`:2046-2085`), `WorkOrderVoidView` (`:2090`),
`WorkOrderAdvanceStepView` (`:2025`) and both oven views (`:2115`, `:2136`) have **only**
`except ProductionError`. `_get_active_recipe` raises `ValueError("Receita inválida.")`
(`shopman/shop/services/production.py:503-509`) and `_operator_error` deliberately re-raises non-`CraftError`
unchanged (`backstage/services/production.py:49-50`).
Repro: the QC kiosk's "Fornada avulsa" sheet lists `kiosk.recipes` (`expedite.vue:443`), a snapshot up to
30 s old. A manager deactivates that recipe in Admin. The baker taps it → Confirmar → 500.
`httpErrorMessage` cannot parse the HTML body, so the toast reads the generic
"Não deu para fechar a fornada. Tente de novo." (`useQcKiosk.ts:47`). Retrying never works.

*(b) `WorkOrder.DoesNotExist` uncaught on start / finish / void / advance-step.*
`void_work_order` / `start_work_order` / `finish_work_order` all open with a bare
`WorkOrder.objects.get(pk=…)` (`shopman/shop/services/production.py:182,334,378`), and
`apply_finish`/`apply_advance_step` call `_get_work_order` outside their `try`
(`backstage/services/production.py:427,503`). `DoesNotExist` is not `Http404`, so DRF's handler returns
`None` and Django emits a 500. The two oven views are the only ones that translate it
(`backstage/services/production.py:267,299`), and even they answer 400 rather than 404.

Fix: add `except ValueError → 400` to the four views, and translate `WorkOrder.DoesNotExist` to
`exceptions.NotFound` once in `_ProductionActionBase.handle_exception`, so no production route can emit a
non-dialect body.

---

## P1

### P1-1 — The printed customer receipt recomputes line totals and disagrees with its own printed total
`surfaces/pos-nuxt/app/presentation/receipt.ts:45-50` (`receiptLineTotalQ`) computes
`price_q*qty − round(price_q*discountPct/100)*qty`, ignoring `charged_price_q` entirely.
`surfaces/pos-nuxt/app/composables/usePosSale.ts:1512-1517` builds the snapshot with only
`{name, qty, price_q, discountPct}` — `charged_price_q` never enters it, so the receipt *cannot* use the
server's number. Rendered at `surfaces/pos-nuxt/app/components/PosReceipt.vue:46`; the printed **total**
at `PosReceipt.vue:52` comes from `review.total_display`, i.e. the server.

Two divergences, in opposite directions:
- Automatic discounts (Happy Hour, lote/liquidação, funcionário) are invisible: `discountPct` is only the
  *manual* discount (`item.discount?.value`), so a Batard with "Liquidação −15%" prints at full
  `price_q` and the lines sum to **more** than the printed total.
- When a manual discount was overridden by a larger automatic one
  (`presentation/lineDiscounts.ts:51-53` `manualDiscountWasOverridden`), the receipt applies the
  *discarded* percentage and the lines sum to **less** than the total.

This is the exact bug `receipt.ts:57-63`'s own docstring says was fixed for `cartNetTotalQ` — the fix
never reached the paper the customer takes home.

Fix: carry `charged_price_q` (and `list_price_q`) into `PosReceiptItem` and make `receiptLineTotalQ`
delegate to `lineTotalQ`. Delete the local discount arithmetic.

### P1-2 — A killed request pins the cash idempotency key `in_progress` for 24 h and 409s every retry
`shopman/shop/services/remote_mutations.py:93-110` — `_acquire` writes `status="in_progress"` with
`expires_at = now + 24h` (`:94`), and `:105` raises `RemoteMutationInProgress` for any later attempt
while that window holds. `run_idempotent_mutation` only clears it on a Python exception (`:72-75`);
a gunicorn worker timeout, a SIGKILL or a dropped upstream connection never runs that handler.
No sweeper exists — grep for `IdempotencyKey` across `shopman/` finds no delete/cleanup anywhere, and
`shopman/shop/management/commands/` has no purge command for it.

Repro: operator lands a R$200 sangria on flaky 4G; the request commits the ledger row and the worker is
recycled before `idem.save(status="done")`. She retries. `chaveDoGesto`
(`surfaces/pos-nuxt/app/composables/usePosCashSession.ts:94-99`) reuses the same key because the body is
unchanged → `operations.py:2217-2229` → 409 "Este lançamento já está sendo registrado. Aguarde um
instante." She waits, taps again, same 409 — **for 24 hours**. Her escape is to change the reason text,
which mints a new key and creates the second R$200 entry the whole mechanism exists to prevent.

Fix: give `in_progress` a short TTL (60–120 s) separate from the `done` TTL —
`shopman/shop/services/webhook_idempotency.py:65-66` already models exactly this with
`in_progress_expires_at`. Reuse it.

### P1-3 — Board SSE never connects after any first-load error (`{ once: true }` self-cancels)
`surfaces/orders-nuxt/app/composables/useOrdersBoard.ts:138-142`:
`watch([pending, error], ([p,e]) => { if (!p && !e) connectSse(); }, { once: true })`.
Vue 3.5 `once` disposes the watcher after the **first callback run**, regardless of the condition's
outcome. The file's own comment (`:17-22`) says a first-load error is the state at *every* shift open
(locked station → 403 `station_locked`), so the callback fires on the first change with the condition
false and the watcher is gone. `source` stays `null` for the session.

Consequence: after PIN unlock, the board runs on the 30 s poll all shift, the indicator honestly says
"Atualização automática" and nobody knows why. A new iFood order can sit unseen for 30 s and
`announceNewOrder` (`:104`), which is driven only by the SSE push, never fires.

Fix: `const stop = watch(...)`; call `stop()` from inside the callback after `connectSse()` actually runs.

### P1-4 — Bulk "Avançar" skips the maquininha question the single-card path asks; custody is lost
`surfaces/orders-nuxt/app/presentation/board.ts:496` filters bulk candidates with
`c.can_advance && !dispatchAsksChange(c)`; `dispatchAsksChange` (`:506-508`) tests **change only**,
while `dispatchAsks` (`:512-516`) — the predicate the single-card path uses
(`pages/index.vue:243`) — tests change **or** `equipment_options.length > 0`.

Repro: a `ready` delivery order on a channel with `fulfillment.equipment` configured, paid by card
(so `change_out_suggested_q === 0`) passes the bulk filter. Select + "Avançar N" → `advanceMany` POSTs an
empty body (`useOrdersBoard.ts:273`) → `advance_order(..., equipment=[])` (`operations.py:1201-1211`)
→ dispatched with **no equipment recorded**. The card machine leaves with the courier and the
"onde está a maquininha" strip (`order_queue.py:878-891`, `index.vue:288-300`) never shows it.

Fix: `bulkableRefs` must use `dispatchAsks`.

### P1-5 — The expedition KDS board receives no SSE at all
Subscribe: `surfaces/kds-nuxt/app/composables/useKdsBoard.ts:44` →
`surfaces/kds-nuxt/server/routes/sse/kds/[ref].ts:11` → `/events/kds/<ref>/` →
`shopman/backstage/urls.py:37-42` → channel `backstage-kds-<ref>`.
The only publisher to `backstage-kds-*` is `emit_kds_change`
(`shopman/shop/handlers/_sse_emitters.py:381`, scope = `ticket.kds_instance.ref` at `:401`), driven by
`KDSTicket` post_save (`:433-450`). **Expedition instances never get tickets**:
`shopman/shop/services/kds.py:159` uses `get_active_prep_instances()`, which excludes expedition, and
`_build_expedition_board` (`shopman/backstage/projections/kds.py:354`) reads
`Order.objects.filter(status="ready")` instead. Order transitions publish to `backstage-orders-*`
(`_sse_emitters.py:269-274`), which the expedition board does not subscribe to.

Repro: a cook bumps the last prep ticket → order goes READY → the expedition screen shows nothing for up
to 15 s, and the SSE connection it holds open is decorative. All four event names registered at
`useKdsBoard.ts:49` are `backstage-kds-*`, so none can ever arrive there.

Fix: route expedition stations to `/events/orders/` in `server/routes/sse/kds/[ref].ts`, or have
`_on_order_changed` also emit `backstage-kds-update` scoped to each active expedition ref. The channel
gate already permits it (`shopman/shop/eventstream.py:130`).

### P1-6 — Unguarded `data["customer"]` — one malformed order 500s a whole KDS board
`shopman/backstage/projections/kds.py:448` and `:505`:
`source_data.get("customer", {}).get("name", "")`. These are the only two sites in the repo using this
form for `customer`; ~25 others use `data.get("customer") or {}` or an `isinstance` guard
(`pos.py:2002,2299,2531`, `checkout.py:47,295`, `customer_orders.py:135`, `modifiers.py:750`, …).
`dict.get(k, {})` returns the stored value when the key exists, so `null` or any non-dict reaches
`.get(...)` → `AttributeError` → 500. Ingest does not type-check:
`shopman/shop/webhooks/ifood.py:249` and `shopman/shop/services/ifood_ingest.py:109` both do
`payload.get("customer") or {}`, passing a string or list straight into `Order.data`.
Blast radius is the whole board: `_build_ticket` is called inside a comprehension
(`projections/kds.py:214-216`). Combined with P0-5 the screen goes blank.
`order_queue.py:416` and `:771` carry the same pattern.

Fix: `isinstance(customer, dict)` guard at both sites.

### P1-7 — A disconnected KDS station loses the cancellation notice permanently
`shopman/backstage/projections/kds.py:196-204` ANDs `acknowledged_at__isnull=True` with
`cancelled_at__gte=now - RECENT_CANCELLED_WINDOW` (10 min, `kds.py:32`). The model already carries the
right concept — `acknowledged_at` "Operador deu baixa no card cancelado — sai do board"
(`shopman/backstage/models/kds.py:83-86`) — and the UI has the button (`[ref].vue:369-377`).
The clock overrules it.

Repro: order cancelled at 10:00; the tablet is offline until 10:12. On reconnect the ticket is gone from
`tickets` (status `cancelled`) and gone from `cancelled_tickets` (outside the window). The cook finishes
food nobody ordered and no screen ever said "cancelado".

Fix: drop `cancelled_at__gte` and let `acknowledged_at__isnull=True` + the row limit do the work
(optionally a 12 h safety bound).

### P1-8 — Acking a cancelled KDS ticket twice returns an error that says the opposite
`shopman/shop/services/kds.py:583-584` returns `False` when `acknowledged_at is not None`, despite the
docstring at `:571` promising "Idempotente". Translated at `shopman/backstage/services/kds.py:67-68` to
`KDSError("Ticket não está cancelado.")` → 400 (`shopman/backstage/api/kds.py:169`) → toasted verbatim
(`surfaces/kds-nuxt/app/composables/useKdsBoard.ts:135,148-149`).

Repro: two tablets on the same bench (the documented normal setup,
`shop/services/kds.py:266`) both tap "Ciente" on the same red card. The loser sees **"Ticket não está
cancelado."** about a ticket that plainly is, and the card is re-inserted by `:134` before the reconcile
removes it again. `mark_ticket_done` got this right (`backstage/services/kds.py:41-44`); ack was left behind.

Fix: mirror `mark_ticket_done` — return the ticket unchanged when already acknowledged.

### P1-9 — Order detail never recovers from a lost session or a 409
`surfaces/orders-nuxt/app/composables/useOrderDetail.ts:14-17` — the detail `useFetch` has no
`onResponseError: operatorSessionOnError`, unlike the board (`useOrdersBoard.ts:31`).
Because backstage never returns 401 (`shopman/shop/api_errors.py:73-81`), a mid-shift session expiry
comes back as 403 `not_authenticated`, `flagIfStationLocked` only matches `station_locked`, and
`[ref].vue:151` renders **"Pedido não encontrado ou falha ao carregar."** The operator is told the order
vanished when their session died; only a manual reload fixes it.
Second gap: `act()`'s catch (`:35-40`) toasts and returns `false` without `await refresh()`. The board
does refresh, and its comment (`useOrdersBoard.ts:212-214`) explains why — "é justamente o caso do 409".
On the detail page a 409 leaves the panel on the pre-conflict projection: "Aceitar" stays lit on an order
someone else already accepted, and every further click 409s again.

Fix: pass `onResponseError: operatorSessionOnError` on the detail fetch and on both `act()` calls;
`await refresh()` in the catch.

### P1-10 — A failed iFood reason fetch fails **open** into free-text cancellation
`shopman/backstage/services/orders.py:132-135` swallows `IFoodCallbackError` and returns `[]`;
`surfaces/orders-nuxt/app/composables/useOrderDetail.ts:70-73` and `useOrdersBoard.ts:255-257` swallow
403/500/timeout too; `OrderReasonDialog.vue:35` / `index.vue:159` decide
`isMarketplace = reasons.length > 0`.
So when iFood's reasons endpoint is down, an iFood order silently renders the **free-text** dialog and
`cancellation_code=""` goes to `reject_order`/`cancel_order` (`operations.py:1264,1339`). The marketplace
relay then has no valid `cancelCodeId`. This inverts the house rule: the missing datum fails open.

Fix: distinguish `{"reasons": []}` from a 502 with `error.code = "reasons_unavailable"`, and block the
marketplace path explicitly instead of degrading to free text.

### P1-11 — `assign`/`unassign` emit no SSE and silently steal the claim
`shopman/shop/handlers/_sse_emitters.py:261-274` emits `backstage-orders-update` only for `created` and
`status_changed`. `shopman/shop/services/operator_orders.py:711-731` — `assign_order` is unconditionally
last-writer-wins with no check on an existing assignment. `OrderAssignView`
(`shopman/backstage/api/operations.py:1792-1801`) has no conflict branch at all.

Repro: A claims → B's board doesn't update for up to 30 s (`useOrdersBoard.ts:150`) → B clicks "Atender"
→ B's name replaces A's, no 409, no warning on either screen. The claim feature exists to prevent exactly
the double-work it fails to prevent.

Fix: emit an orders push on assign/unassign; 409 when a *different* operator holds the claim, with an
explicit "roubar atendimento" flag for the deliberate case.

### P1-12 — `/api/v1/backstage/orders/` is unbounded and O(N) queries per card
`shopman/backstage/projections/order_queue.py:609-613` — `Order.objects.filter(status__in=ACTIVE_STATUSES)`
with **no date bound and no limit**; `ACTIVE_STATUSES` (`:41`) includes `ready`, `dispatched`, `delivered`,
so uncollected pickups accumulate forever. Per card `_build_card` (`:747`) fires: `_payment_status` →
`PaymentService.get` (`shop/services/payment.py:910-913`); a *second* Payman read via
`_requires_captured_payment_for_work` (`operator_orders.py:757-764`); `waitlist.state_for` **twice**
(`:791`), each walking `_order_holds`; a per-card `Directive` query (`:1148-1161`); a per-card `WorkOrder`
query (`:947`); `ChannelConfig.for_channel` per card (`:858-875`). Only `courier_change_by_order` is
batched (`:618`). ~200 queries every 30 s at 30 orders; >1000 at 200, plus a full rebuild on every push.
Client side there is no virtualization and `triaged(zone)` is a **method call in the template**
(`index.vue:470,474,480` + `:61,65`) — ~7 full filter+sort passes on every re-render, including every
keystroke in the search box.

Fix: bound the queue query; batch the fiscal/Payman/waitlist reads the way `courier_change_by_order`
already is; memoize `triaged` into a computed map.

### P1-13 — `existing_closing_display` prints the closing time in UTC
`shopman/backstage/projections/closing.py:171` — `existing.closed_at.strftime("%H:%M")`.
`closed_at` is `auto_now_add` (`shopman/backstage/models/closing.py:17`) and `USE_TZ = True`
(`config/settings.py:693-695`), so a closing at 18:03 BRT displays **"Fechado por marina às 21:03"**.
Every sibling in the same file uses `timezone.localtime` (`closing.py:220-221`).
Rendered at `surfaces/pos-nuxt/app/pages/session/closing.vue:127` and `session/index.vue:1007`.
Fix: `timezone.localtime(existing.closed_at)`.

### P1-14 — The closing POST accepts a stale `quantities` map; new SKUs are counted as zero and never written off
`shopman/backstage/api/operations.py:1085` rebuilds the projection **fresh** at POST time and passes
those items (`:1092`) with the browser's map from page-load time (`:1093`).
`shopman/backstage/services/closing.py:42` does `quantities_by_sku.get(sku, "0")` and `:44-48` takes the
"nothing left" branch: snapshot with `qty_reported=0`, **no `_write_off_lots` call**,
`qty_remaining = item.qty_available` (`:169-179`).

Repro: open `/session/closing` at 18:00 (items A, B); a work order finishes SKU C
(`shelf_life_days == 0`) into a saleable position at 18:05; submit at 18:10. C's batchless quants are
**not** written off — expired day-product rolls into tomorrow as fresh — and `DayClosing.data["items"]`
records a count nobody made. The client-side "every item filled" guard
(`surfaces/pos-nuxt/app/presentation/closing.ts:56-62`) validated a different list.

Fix: compare `{i.sku for i in closing.items}` against `set(quantities)` in `DayClosingView.post` and
return 409 `{"detail": …, "error": {"code": "stale_closing"}}` on mismatch.

### P1-15 — Operation episodes are asked by nobody, and every episode day is permanently excluded from demand learning
`shopman/backstage/projections/closing.py:149-151,184,201-203` emit `pending_episodes`, `episode_options`,
`has_pending_episodes`; `shopman/backstage/api/operations.py:1038-1065` + `api/urls.py:294-298` expose
`POST /closing/episodes/<id>/`. **Zero consumers** across `surfaces/` —
`surfaces/pos-nuxt/app/types/closing.ts:48-62` omits all three keys and `closing.vue` never renders them.
The only readers are `shopman/backstage/tests/test_operation_episodes.py`.
Consequence beyond the missing UI: `shopman/backstage/services/episodes.py:205-223` treats an unanswered
episode as `affects_demand = True` (`shopman/backstage/models/operation_episode.py:128-130`). Since
nothing can ever answer one, **every day a detector fires is excluded from demand learning forever** —
the forecast quietly loses days.

Fix: render the question in `closing.vue` and add the three keys to `types/closing.ts`. Until then, do
not ship the detector's demand side-effect.

### P1-16 — Both closing screens render a blank page on any non-403 failure
`surfaces/pos-nuxt/app/pages/session/closing.vue:112,123,366` — the only branches are `accessDenied`,
`closing`, `pending`; `useDayClosing.ts:25-28` sets `accessDenied` only for 401/403. A 500, a 404 or a
dropped connection leaves `closing = null` and `pending = false` → everything under the header is empty,
no message, no retry. Identical shape in `session/report.vue:70,82,172` over `useCashReport.ts:29-32`.
Given backstage never returns 401, the realistic trigger is a 500 or the store's 4G — at exactly the
moment the day is being closed.
Fix: add a terminal `v-else-if="error"` branch with `httpErrorMessage` and a `refresh()` button.

### P1-17 — A permission-less operator gets a broken app, not a closed door (marketing, bi, purchase)
`surfaces/operator-kit/app/composables/useOperatorLock.ts:46,48` — `canIdentify = session !== null`;
the `perm` argument is used **only** for the eligible-operator list (`:63-75`) and never gates the shell.
`shopman/backstage/api/operations.py:393-416` (`OperatorSessionView`, `IsTrustedStation`) returns 200
with `locked: false` for any authenticated staff regardless of app permission.
Result: `surfaces/marketing-nuxt/app/pages/index.vue:129-138` shows "Não conseguimos carregar o painel.
Tentar de novo" on a 403 retry can never fix; every bi-nuxt page shows "Não deu para carregar os números"
(`pages/cash.vue:84-89`, `index.vue:92`, `sales.vue:74`, `customers.vue:39`, `forecast.vue:103`,
`profiles.vue:122`, `scenarios.vue:29`).
The correct pattern already exists: `surfaces/hub-nuxt/app/presentation/hub.ts:47-92`
(`hubFailure`/`hubFailureCopy`) classifies station-locked / login / forbidden / unavailable and offers
retry only where retry helps.
Fix: lift `hubFailure`/`hubFailureCopy` into `operator-kit` and render the `forbidden` screen when the
primary fetch 403s without `error.code === "station_locked"`.

### P1-18 — Compras renders fabricated demo data whenever the read fails, 403 included
Demo constants are the `useState` **defaults**:
`surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts:37` (MATERIALS — "Farinha T65",
`stockOnHand: 78`), `:166` (SUPPLIERS), `:235` (CONVERSIONS), `:248` (COSTS), `:264,307` (receipt lines),
wired at `:382,393-396`, replaced only when `data.value?.purchase` exists (`:704-710`).
On 403 the banner (`pages/index.vue:561-573`, `usePurchaseDesk.ts:419-432`) says "Operador sem acesso a
Compras" and **does not** say the numbers below are invented; only the non-403 message mentions
"dados de exemplo".
Repro: sign in without `backstage.operate_purchase` → the Painel/Comprar/Base tabs show a full board of
invented stock, suppliers and costs. Mutations are correctly disabled, so nothing is written — the damage
is a purchasing decision taken off invented numbers.
Fix: render an empty/blocked board when `readonlyFallback`; keep the fixtures for tests only.

### P1-19 — `CampaignFireView` has no server-side idempotency
`shopman/backstage/api/marketing.py:461-501` → `shopman/shop/services/campaign.py:85-145`: `fire_now`
filters the rule then calls `_create_announcement` unconditionally — no `IdempotencyKey`, no dedupe key,
no "already fired" guard, unlike `confirm_receipt` (`shopman/backstage/services/purchase.py:195-214`).
The client double-click guard is correct (`FireCampaignPanel.vue:378`), so the exposure is the timeout:
`useCampaigns.ts:93-96` toasts "Não foi possível disparar a campanha." while the server may have
published; the operator reopens and fires again → two Announcements, two WhatsApp broadcasts to the full
audience, no undo.
Fix: wrap in `run_idempotent_mutation` (scope `campaign.fire`) and reply with the
"já disparado em X por Y" shape `_receipt_already_received_message` (`purchase.py:219-227`) already uses.

### P1-20 — Marketing "Plataformas" and "Modelos" present a failed read as an empty fact
`surfaces/marketing-nuxt/app/composables/usePlatforms.ts:22-27` and `useAnnouncementTemplates.ts:13-18`
never return `error`. `pages/platforms.vue:72-77` has no error branch and no empty state — on 403/500
"por onde a padaria consegue falar" answers *nowhere*. `pages/templates.vue:71,81` asserts
**"Nenhum modelo ainda"** about data it could not read. The sibling pages get it right
(`pages/history.vue:42-48`, `pages/campaigns.vue:97-103`).

### P1-21 — BI offers the "Caixa" tab to every `view_bi` holder, but the endpoint needs a second permission
`shopman/backstage/api/bi.py:100` — `BICashView.required_permission = ("backstage.view_bi", "cashman.audit_shift")`
(`shopman/backstage/permissions.py:67`). `surfaces/bi-nuxt/app/components/BiTopBar.vue:30` puts `/cash`
in a static array with no permission awareness; the shell knows only `backstage.view_bi` (`app.vue:7`).
A manager with `view_bi` and not `audit_shift` clicks "Caixa" → 403 → "Não deu para carregar os números",
indistinguishable from an outage. `BIExploreView` (`bi.py:133-163`) handles the same split correctly by
stripping audit-only metrics from the grammar — the tab should follow that precedent.

### P1-22 — A locked-out PIN is indistinguishable from a wrong PIN
`packages/doorman/shopman/doorman/models/pin_credential.py:154-183` — `verify()` returns `False` both for
a wrong PIN and for `is_locked`. `shopman/backstage/api/operations.py:558-578` (`OperatorUnlockView`)
collapses both into 403 `{"detail": "Identificação inválida.", "error": {"code": "operator_unlock_invalid"}}`.
`surfaces/operator-kit/app/composables/useOperatorLock.ts:94` toasts that verbatim.
A baker locked out at 4 a.m. cannot tell "I mistyped" from "wait `PIN_LOCKOUT_MINUTES`", and there is no
manager on site. Note `OperatorUnlockView` also carries **no rate limit** — only `OperatorLoginView`
does (`operations.py:435-439`); the model-level lockout is the sole brake.
Fix: emit a distinct `error.code = "operator_pin_locked"` with `locked_until` and render the wait.

### P1-23 — Production board and KDS never resolve column access: every column permission is decorative
`ProductionBoardView.get` (`shopman/backstage/api/operations.py:835-838`) and `ProductionKDSView.get`
(`:873-876`) call the builders **without** `access=`. Both then fall back to `access or _full_access()`
(`shopman/backstage/projections/production.py:625,1287`).
Consequences: `_can_view_card` (`projections/production.py:2465-2472`) filters nothing;
`planned_queue`/`started_queue`/`suggestions` are never gated; `ProductionKDSCardProjection.can_finish`
(`:1578`) is always `true`; and `ProductionBoardProjection.access` is a constant of eleven `true`s.
Frontend: `ProductionStageGrid.vue:60` reads `board.value?.access` and `:88-117` derives
`lens.read.visible` / `lens.action.editable` from it — so the entire column gate on the surface evaluates
against a constant. The docstring at `api/operations.py:1861` asserting "o resolvedor … só governava a
LEITURA" is no longer true on either side; `resolve_production_access` is now reachable only from the
write gate.
Repro: grant a staff user `backstage.operate_production` + `shop.view_production_planned` only.
`GET /api/v1/backstage/production/` returns every started/finished card and `access.can_edit_started: true`;
`/plan` renders the Planejar button; tapping it 403s at `_ProductionActionBase.initial`
(`api/operations.py:1886-1891`).
Fix: pass `access=resolve_production_access(request.user)` at `api/operations.py:836` and `:874`. No test
covers this (`shopman/backstage/tests/test_api_production_surface.py:140-165` only asserts 200/403 on the
coarse gate).

### P1-24 — A stale-revision 409 on the planning board never refreshes the board
`useQcKiosk.post` handles it (`surfaces/production-nuxt/app/composables/useQcKiosk.ts:50`:
`if (httpErrorCode(err) === "state_conflict") await refresh()`). `useProductionBoard.post`
(`useProductionBoard.ts:44-61`) and `useProductionKds.post` (`useProductionKds.ts:35-52`) do **not** —
they toast and stop.
Repro: two bancadas on `/plan`. A adjusts CIABATTA to 40. B, on a board up to 60 s old, opens the same
row (`planQty` prefilled from the stale `planned_qty`) and saves with the stale `rev`
(`ProductionStageGrid.vue:256`) → `CraftPlanning.adjust` → `_check_rev` → `STALE_REVISION` →
`ProductionConflict` (`backstage/services/production.py:58-61`) → 409. B sees "A fornada mudou em outra
tela. Atualize o painel e tente de novo." — but the panel still shows the old number and the dialog still
holds the old `rev`, so Salvar produces the identical 409, forever.
Fix: mirror the QC handling at `useProductionBoard.ts:52` and `useProductionKds.ts:43`.

### P1-25 — A retried oven-arm creates a second `OvenRun` and silently shortens the measured bake
`useOvenFacts.declare` retries up to 4 attempts (`surfaces/production-nuxt/app/composables/useOvenFacts.ts:13-15`)
and `isTransientError` treats a network failure (`status === 0`) as retryable
(`surfaces/operator-kit/app/utils/httpError.ts:33-36`). `apply_oven_arm` has no idempotency: it marks any
open run `abandoned` and creates a new one with a fresh `armed_at`
(`backstage/services/production.py:274-282`; `OvenRun.armed_at` defaults to `timezone.now()`,
`shopman/backstage/models/oven_run.py:38`; `elapsed_seconds = concluded_at - armed_at`, `:71-74`).
Repro: baker arms a 40 min timer; the request commits but the response is lost. `retryWithBackoff` fires
again 0.3–4 s later. Run #1 → `abandoned`, run #2 opens. The ADR-021 measurement is short by the retry
delay, and `metadata.superseded_open_runs` reads `1` as if the baker had re-enfornado. Under a longer
outage the drift is the full backoff window.
Fix: return the existing open run when `work_order_ref` + `planned_seconds` match and `armed_at` is
within ~60 s, or dedupe on a client-generated `arm_id`.

### P1-26 — After any page reload mid-bake, every restored oven timer is permanently silent
`chime()` bails on `if (!audio) return` (`surfaces/production-nuxt/app/composables/useOvenTimers.ts:89`),
and `audio` is only ever created by `unlockAudio()`, called from `arm()` (`:119`) and nowhere else.
`load()` restores timers from `localStorage` on mount (`:33-50`) and `ensureTicker()` starts the loop, so
`isRinging` flips and the card animates — with `audio` still `null`.
Repro: baker arms a 40 min timer at 04:50; a deploy or a kiosk-browser reload happens at 05:00; at 05:30
the card pulses in `qc-ringing` red and nothing is heard. On a kiosk across the fournil, the visual chip
is exactly what the audible alarm exists to replace.
Fix: call `unlockAudio()` on the first user gesture after `load()`, the way `board.vue:70,144` already
does with `sound.unlock()`.

### P1-27 — The production board endpoint rebuilds every planned/started card via an N+1 loop the surface never reads
`build_production_board` builds `planned_queue` and `started_queue` with one
`WorkOrder.objects…get(ref=item.ref)` **per queue item**, then a full `_build_wo_card` on each
(`shopman/backstage/projections/production.py:660-673`). `_build_wo_card` costs, per card:
`_wo_started_qty` → `wo.events.filter(...)` (`:2482`, and `events` is never prefetched here),
`_base_recipe_usages` → a `Recipe.objects.filter(...)` (`:2249`), and `_order_commitments_for_work_order`
→ an `Order.objects.filter(...)` (`:1614`).
The frontend reads **none** of `work_orders`, `planned_queue`, `started_queue`, `finished_queue`,
`recipes`, `positions`, `suggestions`, `matrix_groups`, `default_position_pk`, `selected_operator_ref` —
each name appears only in `app/generated/productionContract.ts`. The grid consumes `matrix_rows`,
`counts`, `base_recipes`, `access` and `selected_date*` (`ProductionStageGrid.vue:60,85,121-132,374-393`).
A busy Saturday with ~120 planned+started WOs costs ~120 extra `get()`s plus 3–4 queries each for the two
dead queues, on a 60 s poll from every kiosk on the floor.
Fix: drop the four dead queues (derivable from `matrix_rows`) and add `prefetch_related("events")` plus a
batched recipe lookup to the remaining card build.

### P1-28 — One base prep referenced in two units produces two weighing tickets sharing one blind code
`add_ticket` keys the accumulator on `(recipe.pk, unit)`
(`shopman/backstage/projections/production.py:790`), and `unit` comes from the parent `RecipeItem`
(`:833-838`) — so two output recipes calling the same base prep, one in `kg` and one in `g`, produce
**two** ticket entries for one prep. `blind_prep_code(recipe.ref, selected_date)` is keyed on
`(date, recipe_ref)` only (`:2335`; `BlindPrepCode` unique on `(date, recipe_ref)`,
`shopman/backstage/models/blind_prep.py:31`), so both tickets carry the **same** code with **different**
ingredient weights.
Frontend: `mise-en-place.vue:483` keys ticket cards on `ticket.recipe_ref` → duplicate Vue key, DOM reuse;
`mise-en-place.vue:100` keys printed blind labels on `` `${blind_code}-${ing.sku}` `` → the two label sets
collide outright; `reports.vue:538` keys the manager's blind map on `row.code` → duplicate
indistinguishable rows.
Repro: ficha A lists `1,2 kg` of MASSA-MADRE, ficha B lists `800 g` of the same. Printing pesagem labels
yields two labels reading "B7 · Farinha · 720 g" and "B7 · Farinha · 480 g". The baker at the scale, who
by design cannot see the recipe name, weighs one batch instead of two.
Fix: normalize `unit` to the base recipe's own unit before keying; failing that, include the unit in the
blind-code allocation key and in every Vue key.

### P1-29 — Comma-decimal production quantities pass client validation and are rejected by the server
`ProductionStageGrid.vue:355-361` validates with `parseFloat(planQty.value.replace(",", "."))` but
`confirmPlan` sends the **raw** string (`:246`); `confirmStart` sends `startQty.value.trim()` with no
validation at all (`:277`). Both inputs are free text with `inputmode="decimal"` (`:720-726,784-790`) — on
a pt-BR touch keyboard the decimal key *is* the comma. Backend `_non_negative_decimal`/`_positive_decimal`
do `Decimal("1,5")` → `InvalidOperation` → `ValueError` (`shopman/shop/services/production.py:512-531`)
→ 400 "Quantidade planejada inválida.", with no indication of what is wrong.
Fix: normalize at the send site and apply `planQtyValid` to `startQty` too.

### P1-30 — `apply_advance_step` read-modify-writes the whole `WorkOrder.meta` JSON without a lock and can erase `committed_order_refs`
`backstage/services/production.py:503,518-524` — reads the WO, builds `meta = dict(work_order.meta or {})`,
mutates and saves with `update_fields=["meta", "updated_at"]`. No `select_for_update`, no `expected_rev`,
no `F()`. The order-sync handler writes the same column the same way
(`shopman/shop/handlers/production_order_sync.py:151-153`), as does `set_planned_quantity`
(`shopman/shop/services/production.py:249-253`).
Consequence: a customer order that links to the fornada between the read and the save has its link
silently dropped. `linked_order_refs` then returns `()`, so the board shows zero committed units,
`_check_linked_order_coverage` passes on any reduction, and `_ensure_order_links_closed` at finish never
releases the order. The window is milliseconds; the loss is a paying customer's bread, silently.
Fix: `transaction.atomic()` + `select_for_update()`, the way `CraftExecution.finish`/`void` already do
(`packages/craftsman/shopman/craftsman/services/execution.py:80,346`). Same for
`_append_order_work_order_link`.

### P1-31 — production-nuxt has no SSE at all, though the backend already publishes the channel
`_on_production_changed` emits `backstage-production-update` on `backstage-production-main` for every
plan/start/finish/void (`shopman/shop/handlers/_sse_emitters.py:327-341,477-479`); the route exists
(`shopman/backstage/urls.py:31-35`) and the permission predicate already grants the cozinha group
(`shopman/shop/tests/test_eventstream_permissions.py:88`). `surfaces/production-nuxt` contains **zero**
`EventSource` / `proxyEventStream` references. The justification at `useAdaptivePoll.ts:6-8` ("Polling
over SSE is deliberate for production … revisit post-alpha, decision WP-PE4") predates ADR-016's
site-wide SSE-first rule.
Consequence, worst on the QC kiosk: `useQcKiosk` polls every 30 s (`useQcKiosk.ts:33`), so a fornada
closed on another device stays tappable and "open" for up to 30 s and the second close 409s. The planning
board's 60 s (`useProductionBoard.ts:38`) is exactly the stale-`rev` window of P1-24. A kiosk whose tab is
hidden skips fetches entirely and catches up only on `visibilitychange` (`useAdaptivePoll.ts:14,26`).
Fix: subscribe via `proxyEventStream` and call the existing canonical `refresh()` on each event, keeping
the poll as the calm fallback.

### P1-32 — The production reports "Operador" filter is an exact match against a value the UI never shows
`_report_queryset` filters `qs.filter(operator_ref=filters.operator_ref)` — exact
(`shopman/backstage/projections/production.py:1783-1784`). Stored values are `production:<username>`
(`shopman/backstage/api/operations.py:142-145`), but the Produtividade table displays `operator_name`,
which is that value with `production:` stripped (`projections/production.py:1848`), and the placeholder
invites "Nome ou usuário" (`surfaces/production-nuxt/app/pages/reports.vue:322`). Typing `joao` returns
"Nada produzido nesse período."; only the literal `production:joao` works.
Fix: `operator_ref__icontains`, or drive the field from a `<select>` of distinct `operator_ref`s the way
Ficha/Posto already are.

---

## P2

1. **`accepted` has no status tone.** `surfaces/orders-nuxt/app/presentation/board.ts:16-26` maps
   `confirmed`, which is not an `Order.Status` (`packages/orderman/shopman/orderman/models/order.py:35-44`).
   Every `accepted` card falls to `?? "neutral"` (`board.ts:29`) — grey where the design intends blue.
2. **The orders board timer is a frozen server snapshot.** `order_queue.py:805` emits `elapsed_seconds`
   and `server_now_iso`; `OrderCard.vue:112` renders it verbatim, so the elapsed clock and the urgency
   colour (`timer_class`) jump only every 30 s despite `useNowTick` already existing in the same file.
3. **`OrderAdvanceView`'s 409 speaks a third dialect.** `operations.py:1213-1216` returns
   `{"detail", "code", "suggested_q"}` with a bare top-level `code` — neither `{detail, field, errors}`
   nor either sanctioned superset. `httpErrorCode` (`operator-kit/app/utils/httpError.ts:85`) reads
   `data.error.code` and cannot see it; nothing reads `suggested_q`.
4. **Catalog social errors break the dialect.** `shopman/backstage/api/catalog.py:360` returns
   `{"detail": …, "errors": [str, …]}` — a **list**, where `shopman/shop/api_errors.py:9` defines
   `errors` as `{campo: [mensagens]}`.
5. **Telemetry 429 has no body.** `shopman/backstage/api/telemetry.py:90` — `Response(status=429)` with
   no `detail`. The only route in scope returning an error without it.
6. **KDS `limit` 400 omits `field`.** `shopman/backstage/api/kds.py:220-223`.
7. **`PosRecentSales.vue:211` bypasses the command transport.** It calls `$fetch(apiPath(...))` directly
   instead of `usePosAction.call`, so the 401 re-gate (`useOperatorSession.flagIfUnauthenticated`) and
   the 403 `station_locked` re-gate (`useStationLock.flagIfStationLocked`) never run for cancelling a
   sale from that sheet. CSRF still works because the BFF derives the token from the forwarded cookie
   (`surfaces/operator-kit/server/utils/djangoProxy.ts:103-104`).
8. **`supports_push_updates: False` is a lie.** `shopman/backstage/projections/pos.py:1723` declares the
   POS does not support push, while `usePosEvents.ts:33-38` subscribes to two SSE channels. Nothing
   reads the key (grep for `supports_push_updates`/`live_refresh` in `surfaces/` returns nothing), so
   it is dead contract weight that will mislead the next reader.
9. **A dead pre-discount total is exported from `usePosSale`.** `surfaces/pos-nuxt/app/composables/usePosSale.ts:309`
   computes `formatBRL(cartTotalQ(cart.items))` using `price_q` — the restoration price that
   `presentation/lineDiscounts.ts:68-79` documents as wrong — and exports it at `:1879`. No template
   consumes it today; it is a loaded gun for the next screen.
10. **The cash-note rail bypasses the currency formatter.** `surfaces/pos-nuxt/app/components/PosPaymentWorkspace.vue:721`
    renders `{{ note / 100 }}` while the aria-label on the same element uses `formatBRL(note)`.
    Correct only because every contract preset (`projections/pos.py:1601`) is a whole real.
11. **SSE cannot re-arm after a hard status.** `surfaces/operator-kit/server/utils/eventStream.ts:59-62`
    propagates a non-2xx upstream (403 **and** a Django restart's 502) as a status the `EventSource` spec
    treats as fatal. `useOrdersBoard.ts:113`, `useOrderEvents.ts:11` and `useKdsBoard.ts:41` all guard
    `if (source) return` and never null `source`, so the stream is dead for the session. Only
    `usePosEvents.ts:76-79` recovers, and only on `visibilitychange` — which never fires on a kiosk.
    Net effect: every deploy silently drops the kitchen and kiosk screens to polling.
12. **No refetch on SSE reconnect.** `usePosEvents.ts:51`, `useOrdersBoard.ts:127`,
    `useOrderEvents.ts:26`, `useKdsCustomerBoard.ts:39` all set `realtime = "live"` in `onopen` without
    calling the canonical refetch, and `shouldPollTick` (`pos-nuxt/app/presentation/events.ts:14`) then
    suppresses the poll. Mitigated — but only mitigated — by `is_channel_reliable` returning `True` for
    `backstage-*` (`shopman/shop/eventstream.py:15-20` falls through to
    `DefaultChannelManager.is_channel_reliable`, which returns `True`) plus
    `EVENTSTREAM_STORAGE_CLASS = DjangoModelStorage` (`config/settings.py:1217`) and the proxy forwarding
    `last-event-id` (`eventStream.ts:47-48`). Resume covers the gap when it works; nothing covers it when
    the id is `"error"` or the row expired.
13. **`operator-kit` hardcodes `/api/v1/...` paths.** `useOperatorLock.ts:24,66,83,103,125,155`,
    `useNotifications.ts:26,43,56`, `useStationProvision.ts:13`, `clientErrorReport.ts:19` all bypass the
    `apiPath`/`baseURL` discipline that `usePosApiPath.ts:4` enforces. Harmless today (every app defaults
    `NUXT_APP_BASE_URL` to `/`), fatal the day one is served under a sub-path — which
    `surfaces/operator-kit/app/utils/ssePath.ts:5` explicitly anticipates ("KDS servido em /kds/ na prod").
14. **`retryWithBackoff` auto-retries a POST with no idempotency key.**
    `surfaces/operator-kit/app/utils/retryBackoff.ts:25` retries on `isTransientError`, which includes
    `status === 0`, i.e. a request that may have succeeded server-side
    (`surfaces/operator-kit/app/utils/httpError.ts:33-36`). Its one operator-side consumer is
    `surfaces/production-nuxt/app/composables/useOvenFacts.ts:13`.
15. **`submitSale` asserts a falsehood on timeout.** `surfaces/pos-nuxt/app/composables/usePosSale.ts:1578`
    tells the operator "**O pedido não foi fechado**; revise o pagamento e valide de novo." A network
    timeout cannot know that. Harmless in effect — `cart.clientRequestId` survives the failure
    (`usePosSale.ts:1094,1433`) and the server dedupes by it (`shop/services/pos.py:318,3232-3238`) —
    but the copy trains the operator to distrust a correct replay.
16. **KDS is entirely outside the `Action` contract.** `shopman/backstage/projections/kds.py` never
    constructs an `Action`; all five mutations are hardcoded URL+method
    (`useKdsBoard.ts:109,141,143,146,149`). Because `test_action_idempotency_contract.py:87-105` scans
    only `Action(...)` call sites, those five mutating endpoints escape the guardrail silently. Same for
    orders (`order_queue.py` emits zero `Action`s; `board.ts:225-257` hardcodes affordances).
17. **KDS write path never re-gates on 401/403.** `useKdsBoard.ts:86-100` — `postProxy` has no
    `onResponseError` and never calls `flagIfStationLocked`/`flagIfUnauthenticated`;
    `surfaces/kds-nuxt/app/app.vue:9-10` drops `flagIfStationLocked` from the destructure.
18. **KDS has no virtualization and forces synchronous layout every poll.**
    `surfaces/kds-nuxt/app/pages/[ref].vue:427-450` renders all cards in a FLIP `TransitionGroup`; each
    card mounts a `ResizeObserver` plus a `deep: true` watcher on `props.ticket.items`
    (`KdsTicketCard.vue:65-70`). Every 15 s refresh replaces all item objects → `measure()` (`:51-64`)
    reads `scrollHeight`/`offsetTop` per `<li>`. Thousands of reflows at 200 tickets.
19. **Long item names are never fully readable on the KDS.** `KdsTicketCard.vue:202` and
    `KdsTicketModal.vue:165` both `truncate`, with no `title` and no wrap — and the modal is the
    documented escape hatch. Its sibling note fields already use `whitespace-pre-wrap` (`:131,138`).
20. **No cap on the closing movements table.** `shopman/backstage/projections/cash_session.py:202-205`
    emits every movement of the shift; `PosCashReadingCard.vue:101` renders them all.
21. **`R$ ` with nothing after it.** `projections/cash_session.py:214,227` leave
    `counted_amount_display` empty for a shift closed without a `count` entry
    (`packages/cashman/shopman/cashman/services/ledger.py:234-239`); `PosCashReadingCard.vue:54` renders
    `R$ {{ … }}` unconditionally.
22. **`parse_money_to_q` misreads the Brazilian thousands dot.** `shopman/backstage/services/pos.py:38`
    strips `R$` and swaps `,`→`.` but leaves `.` alone: `"1.234"` → R$ 1,23. Unreachable from the POS
    (`presentation/cash.ts:177` rejects it) but this is the closing-count parser, and it is the same
    class of bug as P0-8.
23. **N+1 on the closing page, paid twice on POST.** `projections/closing.py:264-299` runs one
    `Product.objects.get` + one `Quant` query + three lot lookups per SKU
    (`services/closing.py:182-210`), and the POST rebuilds the projection (`operations.py:1085`) before
    `perform_day_closing` builds it again.
24. **Closing double-submit surfaces a raw Postgres message.** `DayClosingView.post` has no idempotency
    key; money and stock are safe (the `DayClosing.date` unique constraint inside
    `services/closing.py:39`'s atomic block rolls the write-offs back), but the `IntegrityError` is not
    a `ValueError`, so `operations.py:1097-1099` returns **400 with the raw DB message** in `detail`.
25. **Timeout-that-succeeded shows a contradiction at closing.** `useDayClosing.ts:40-44` toasts
    "Falha no fechamento." then refreshes; the page then renders the green "Dia fechado" alert
    (`closing.vue:124-128`) beside the red toast, `justClosedDay` stays `false`, the next-step card never
    appears, and the typed quantities are never cleared (`closing.vue:86`).
26. **`_reconciliation_errors` double-counts production.** `services/closing.py:354` computes
    `saleable_by_sku = qty_remaining + qty_applied`, which per `_snapshot` (`:174-176`) is exactly
    `item.qty_available` — stock *after* the day's sales — and `:380` then adds `produced_by_sku` on top.
    Shown to the manager as "Discrepâncias detectadas" (`closing.vue:277-299`).
27. **Emitted-and-never-read keys** (dead contract weight, each verified by grep across `surfaces/`):
    orders cards — `status_color`, `server_now_iso`, `items_count`, `payment_pending`, `change_for_q`,
    `change_back_q`, `waitlist_deadline_iso`, `equipment_out`, and notably **`has_kitchen_note`**
    (`order_queue.py:829`, with an explicit design note at `:149-160` saying both notes must be flagged;
    `OrderCard.vue:211-219` renders only `has_customer_note`). Courier — `position` (live driver
    coordinates fetched from cache at `order_queue.py:533-535` and dropped), `provider`, `active`,
    `requested_at`, `dispatched_at`, `finished_at`. KDS — `status`, `status_label`, `is_cancelled`,
    `instance_type`, `counts.pending/cancelled_recent/done_recent`, all of
    `KDSCustomerOrderProjection.{status,status_label,updated_at_display}`. Cash session —
    `has_open_shift`, `terminal_ref`, `amount_display`, `movements_in_q`, `movements_out_q`,
    `sales_total_q`, `counted_total_q`. Notifications — `POST /notifications/<pk>/action/`
    (`shopman/backstage/api/notifications.py:116-243`) has **zero** consumers, including the
    "não fui eu" session-revoke with its deliberate 409 `needs_confirmation` handshake (`:211-223`);
    `NotificationBell.vue:85-124` renders no action buttons and no link on `action_url`. An operator who
    receives a suspicious-sign-in notice has no way to act on it.

28. **`RecipeWasteRow.capacity_utilization` is computed and CSV-exported but never rendered.**
    `shopman/backstage/projections/production.py:1963-1976` computes it and
    `shopman/backstage/services/production.py:589-596` exports it; the Desperdício table renders only four
    columns (`surfaces/production-nuxt/app/pages/reports.vue:481-489`). The CSV and the screen disagree.
29. **The BFF drops `Content-Disposition`, so the reports CSV loses its filename.**
    `ProductionReportsView` sets it (`shopman/backstage/api/operations.py:983`), but `proxyDjangoPath`
    forwards only `set-cookie`, `location` and `content-type`
    (`surfaces/operator-kit/server/utils/djangoProxy.ts:129-140`). The `<a download>` at `reports.vue:265`
    then names the file from the URL.
30. **Production column gates are declared on the wrong column.**
    `WorkOrderVoidView.production_column = "finished"` (`api/operations.py:2088`) — estornar a *started*
    fornada requires `shop.edit_production_finished`, a column the action does not write.
    `WorkOrderQuickFinishView` (`:2044`) declares only `finished` while also planning. Both oven views
    declare no column at all (`:2114`, `:2135`).
31. **Production write failures never raise the station-lock screen.** `useProductionBoard.post`,
    `useProductionKds.post` and `useQcKiosk.post` toast and stop; none calls `flagIfStationLocked`.
    Every other operator surface does (`pos-nuxt/app/composables/usePosAction.ts:44`,
    `orders-nuxt/app/composables/useOrdersBoard.ts:34`,
    `purchase-nuxt/app/composables/usePurchaseDesk.ts:713`).
32. **The production KDS fetch has no `date` param, so the step/timer/advance block silently vanishes on
    any non-today board.** `useProductionKds.ts:18-22` fetches without a query and `startedCard` matches
    by pk against today's cards only (`ProductionStageGrid.vue:200-204`). Pick "Amanhã", open a started
    row → the dialog renders with no step name, no elapsed chip, no "Avançar", and no explanation.
33. **`advance-step` is not idempotent and double-taps are silent.**
    `backstage/services/production.py:519` increments by one; the composable's busy set makes a second
    in-flight tap return `{ok:false}` with no feedback (`useProductionKds.ts:36`). From two devices, one
    step is skipped with no trace.
34. **Six production reads skip `operatorSessionOnError`** — `useMiseEnPlace.ts:13-20`,
    `useWeighing.ts:9-16`, `useBlindMap.ts:10-17`, `useProductionManagement.ts:9-16`, `useAlerts.ts:7-10`
    (and `useProductionReports`, deliberately, documented at `:6-7`). A session expiring while Preparação
    is on screen leaves an error panel instead of the PIN prompt until the operator navigates.
35. **`useReportsAccess` hides the Relatórios rail item on *any* error, not just 403.**
    `allowed = !!data && !error` (`surfaces/production-nuxt/app/composables/useReportsAccess.ts:15-17`) —
    a transient 502 removes the manager's navigation entry until a remount.
36. **`menuboard.vue:32` reads `data.value?.catalog.sections`** — the optional chain stops at `data.value`
    and then dereferences `catalog` directly. `StorefrontMenuView` always emits `catalog` on 200 today
    (`shopman/storefront/api/surface.py:274`), so this is latent — but it is the one unguarded nested
    access in the app, on the page that renders on a public TV with no operator present. Related:
    `surfaces/production-nuxt/app/utils/api.ts` (`apiPath`) is **dead** — no call site; every fetch
    hardcodes `/api/v1/...` (the same latent baseURL trap as P2-13).


---

## Endpoint & action inventory

### Backstage action contract (the only projection that emits `Action`)
`shopman/backstage/projections/pos.py` — 29 actions, no other backstage projection constructs one
(KDS, orders, production, closing, purchase, marketing, bi all hardcode URLs on the frontend).

| ref | method | declared `idempotency` | key actually sent by the frontend | double-submit reality |
|---|---|---|---|---|
| `open_cash_shift` :1052 | POST | `client_request_id` | yes — `usePosCashSession.ts:104` | replayed by `_cash_idempotent` |
| `close_cash_shift` :1062 | POST | `client_request_id` | yes | replayed; but see **P0-2** (no `terminal_ref`) |
| `cash_movement` :1078 | POST | `client_request_id` | yes | replayed |
| `refund_cash` :1148 | POST | `client_request_id` | yes | replayed |
| `settle_account` :1158 | POST | `client_request_id` | yes | replayed |
| `request_change` :1168 | POST | `client_request_id` | yes | replayed |
| `serve_change_request` :1185 | POST | `client_request_id` | yes | replayed |
| `cancel_change_request` :1195 | POST | `client_request_id` | yes | replayed |
| `close_sale` :1003 | POST | `required` | yes — `usePosSale.ts:1094` | deduped in `shop/services/pos.py:318` |
| `customer_resolve` :1225 | POST | `required` | **no** | resolves by phone; benign but the declaration is unmet |
| `fire_tab` :1287 | POST | `ledger` | id sent, **only logged** (`projections/pos.py:1298`) | protected by the per-`line_id` ticket ledger, not the key |
| `create_tab` :957 | POST | `none` | — | second POST hits the existing ref |
| `open_tab` :967 | POST | `none` | — | idempotent by ref |
| `save_tab` :977 | POST | `none` | — | **P0-1**: replace-by-session_key, last writer wins |
| `review_sale` :990 | POST | `none` | — | pure read |
| `cancel_recent_sale` :1038 | POST | `none` | — | second cancel 404/422s (`operations.py:3361-3366`) |
| `drawer_open` / `drawer_unlock_attempt` / `drawer_left_open` / `drawer_block` / `drawer_blind` / `drawer_unlock` :1088–1138 | POST | `none` | — | telemetry / physical kick |
| `clear_tab` :1251 | DELETE | `none` | — | second DELETE 404s |
| `rename_tab` :1262 | POST | `none` | — | idempotent |
| `move_tab_lines` :1272 | POST | `none` | — | line_ids no longer at source |
| `unfire_tab` :1305 | POST | `none` | — | idempotent |
| `customer_lookup` :1205 / `customer_search` :1215 | GET | `none` | — | reads |
| `reverse_geocode` :1235 | POST | `none` | — | read |

### Idempotency reality table (non-POS mutations, all with **no** key anywhere)
| Mutation | Protection actually present | Verdict |
|---|---|---|
| order confirm / reject | `select_for_update` re-read → `OrderStateConflict` → 409 (`operator_orders.py:127-133,159-165`) | safe |
| order cancel | returns `False` → `OrderConflict` → 409 (`backstage/services/orders.py:111-113`) | safe |
| order advance | **no** `select_for_update`; saved only by `Order.save()` rejecting `dispatched→dispatched` (`packages/orderman/…/order.py:226-243,304`) | safe by accident |
| settle-delivery-cash | `cod_settled_at` read is unlocked; real stop is `cashman_entry_one_cod_settled_per_order_uq`, scoped to **(shift, order_ref)** (`packages/cashman/…/entry.py:232-236`) | **unsafe across a shift close** |
| courier dispatch | `has_active_ride` read is unlocked; saved by directive `create_deduped` (`shop/services/courier.py:203-218`) | safe, but the button stays lit after success (`order_queue.py:559-561`) |
| KDS done / item-check / expedition | `select_for_update` + no-op replay (`shop/services/kds.py:264-286,614-627`) | safe |
| KDS acknowledge | replay returns an error (**P1-8**) | wrong message |
| purchase receipt confirm | `run_idempotent_mutation(scope="purchase.receipt", key=source_ref)` (`backstage/services/purchase.py:195-214`) | safe |
| purchase count confirm | delta recomputed at submit (`services/purchase_count.py:101-152`) | safe |
| campaign fire | **nothing** (**P1-19**) | unsafe on timeout |
| day closing | `DayClosing.date` unique inside the atomic block | safe; raw DB error (P2-24) |

### Production routes (all `HasBackstagePermission`; column gate via `_ProductionActionBase`)
Reads — `production/` `production/kds/` `production/qc/` `production/forecast/`
`production/mise-en-place/` `production/weighing/` all require `backstage.operate_production`;
`production/reports/` `production/management/` `production/weighing/blind-map/` require
`backstage.view_production_reports`. `production/weighing/` can raise `RuntimeError` when the 192-code
blind space is exhausted (`projections/production.py:1078`) → 500.
Writes — `plan` (column `planned`), `start` (`started`), `finish` (`finished`),
`advance-step` (`started`), `quick-finish` (`finished`, **also plans** — P2-30), `void`
(declares `finished`, writes `started` — P2-30), `oven/arm` and `oven/conclude` (no column declared).
Error branches: 400 missing field · 409 `order_shortage` · 409 `material_shortage` (with a structured
`missing[]`) · 409 `state_conflict` · 403 column · and the **500s of P0-11**.
`Action`/`idempotency` coverage here is **zero** — the production projections emit no `Action` at all, so
no production write declares an idempotency posture and nothing verifies one. The consequences are P0-10,
P1-25 and P2-33; `finish` is protected by the server-derived key
(`backstage/services/production.py:462-490`), and `plan`/`start`/`void` by `expected_rev` + status checks.

### SSE inventory
Channels (`shopman/backstage/urls.py:28-42`): `/events/me/` (`user-<id>`), `/events/<kind>/`
(`backstage-<kind>-main`), `/events/<kind>/<scope>/`.
Permissions (`shopman/shop/eventstream.py:128-148`): `orders` → `shop.manage_orders` ∪
`backstage.operate_kds`; `kds` → `operate_kds`; `production` → `operate_production`; `cash` and `tabs` →
`cashman.operate_pos`; `alerts` → five codes. An unmapped `kind` is **denied** and logged
(`:58-61`) — a new channel is born inaccessible, which is the right default.
Reliability: `is_channel_reliable` returns `False` only for `stock-`/`fomo-` (`eventstream.py:15-20`);
`backstage-*` falls through to `True`, and `EVENTSTREAM_STORAGE_CLASS = DjangoModelStorage`
(`config/settings.py:1217`) plus `last-event-id` forwarding (`eventStream.ts:47-48`) means missed events
during a short disconnect **are** replayed.
Subscribers: pos → `/sse/cash` + `/sse/tabs`; orders → `/sse/orders`; kds board → `/sse/kds/<ref>`
(**dead for expedition**, P1-5); kds pickup → `/sse/orders`; operator-kit → `/sse/notifications`.
Not emitted at all: assign, unassign, comment, kitchen-note, equipment-back, cod-settled
(`_sse_emitters.py:261-274`).

### Route inventory
All routes are enumerated with method, permission, request shape, response shape and every error branch
in the per-surface tables produced during this audit; the summary is:
`shopman/backstage/api/urls.py` exposes **150 paths**. Permission classes used:
`HasBackstagePermission` (with `required_permission`, single code or tuple), `IsTrustedStation`,
`IsBackstageOperator`, `CanViewOperatorAlerts`, `AllowAny` (operator login + client-error only).
The backstage **never returns 401** — `DEFAULT_AUTHENTICATION_CLASSES` has only `SessionAuthentication`,
which has no `authenticate_header()`, so DRF downgrades to 403; `shopman/shop/api_errors.py:65-95`
compensates by attaching `error.code = "not_authenticated"`, and
`surfaces/operator-kit/app/utils/httpError.ts:56-60` narrows on the code rather than the status.
Every frontend must therefore branch on `error.code`, never on `status === 401`.

---

## Verified-safe

**Error dialect.** An AST sweep of every `Response(...)` with a 4xx/5xx status across all of
`shopman/backstage/api/` found **zero** payloads missing `detail` (the nine `marketing.py` hits were
variables — `_announcement_edits`, `_publish_at`, `_rule_fields`, `_pairing_error`, all of which build
`{"detail": …, "field": …}`, verified at `marketing.py:621,632,638,741,752`). The two real deviations are
`catalog.py:360` (`errors` as a list) and `telemetry.py:90` (empty 429), both P2. The two sanctioned
supersets — POS `{detail, error:{code,message,field,focus,recovery}}` and the storefront's rate-limit
shape — are documented in `shopman/shop/api_errors.py:20-28` and are consumed correctly.

**Projection key presence.** `shopman/backstage/api/projections.py:13-19` walks
`dataclasses.fields()`, so **every field of every dataclass-backed projection is always serialized**.
There is no conditionally-omitted key anywhere in the backstage contract — the `return {}` branches in
`order_queue.py:859-860,900-904` fall through to dataclass defaults rather than dropping keys. Nullable
members (key present, value `null`) were enumerated and each frontend read was checked individually;
all are guarded. This closes the "conditionally-present key read unguarded" class of white-screen bug
for the whole surface, with the two exceptions above (`kds.py:448,505`, P1-6, which is a *backend*
`AttributeError`, not a frontend one) and `bi-nuxt/app/pages/forecast.vue:210` (a `!` assertion held up
only by an upstream `v-if` ordering — one reorder from a crash).

**Contract drift is guarded.** `surfaces/kds-nuxt/app/generated/kdsContract.ts`,
`orders-nuxt/app/generated/ordersContract.ts` and `pos-nuxt/app/generated/posContract.ts` are generated
by `export_*_schema` commands and asserted by `shopman/backstage/tests/test_*_schema_export.py`.
The one hand-written hole is `_courier_block` (`order_queue.py:539-562`), an untyped dict whose 18 inner
keys are re-declared by hand at `surfaces/orders-nuxt/app/types/orders.ts:38-57`.

**Money.** No float arithmetic on any monetary value, anywhere in the operator surfaces. Backend is
integer centavos end to end (`format_money` and `brl_to_q` use `Decimal` with `ROUND_HALF_UP`,
`packages/utils/shopman/utils/monetary.py:61,80`). KDS, orders and the cash report cross the wire
pre-formatted and are only printed. The only client-side arithmetic is on centavo integers
(`pos-nuxt/app/presentation/cash.ts:193-200`, `orders-nuxt/app/presentation/board.ts:532-542`,
`utils/posIntent.ts:17-26`), and every `/100` is display-only. `R$` prefixing is consistent — the one
projection that pre-prefixes (`closing.py:397`) is rendered bare. The exceptions are the two parser
divergences (P0-8, P2-22) and the receipt recomputation (P1-1) — none of which is float math.

**Blind cash count is enforced server-side, not merely hidden.** `build_cash_session_report`
(`projections/cash_session.py:22-27`) never calls `balance`/`expected_before_count`/`difference`;
`_cash_shift_result` (`operations.py:200-217`) returns only `counted`; the route is gated on
`cashman.audit_shift`; `PosDenominationCounter.vue:25,32` sums only what the operator typed and starts
empty. The leak is the *closing* route (P0-3), not this one.

**Post-close cash entries cannot drift the count.** `packages/cashman/…/services/ledger.py:33,111-116`
re-reads the shift under `select_for_update` and rejects everything but `COUNT_CORRECTION`/`NOTE`/
`RECEIPT_RESULT`; the latter two are sign-`"0"`, so `expected_before_count` cannot move after the count.
A cash sale landing after the close is refused, not absorbed — it surfaces as a variance, which is the
intent.

**PIN brute force is bounded at the model.** `packages/doorman/…/pin_credential.py:154-183` —
`attempts`/`max_attempts`/`locked_until`, incremented with `F()` and enforced before the digest compare.
(The missing *rate limit* on `OperatorUnlockView` and the indistinguishable lockout message are P1-22.)

**The BFF proxy is faithful.** `surfaces/operator-kit/server/utils/djangoProxy.ts:116-143` uses
`ignoreResponseError: true` + `setResponseStatus` + returns `_data`, so `{detail, field, errors,
error.code}` reaches `httpError`/`httpErrorCode` intact; CSRF is derived from the forwarded cookie
(`:102-112`) with an `/admin/login/` bootstrap, and `X-API-Version` mismatch warns without blocking
(`:127`).

**Unhandled-state sweep.** Order with no customer → `""` → "Sem cliente"
(`order_queue.py:1164-1167`, `OrderCard.vue:128`). Order with no items → empty summary, no throw.
Deleted `Channel` row → `channel_ref` is a plain string with a `.get(..., default)` icon map
(`order_queue.py:800`) and a capitalising label fallback (`board.ts:278-281`) — no FK dereference in any
projection. Empty board / empty queue → designed empty states on both. Long names → `truncate` /
`line-clamp-2` everywhere except the KDS modal (P2-19). Cancelled mid-preparation → leaves
`ACTIVE_STATUSES`, and the `status_changed` push forces the refetch. Ticket with zero items →
`all_checked` explicitly `False` (`kds.py:483`). Supplier that never delivered → `lastDeliveryAt: ""`,
formatted defensively (`purchase.py:56`, `presentation/purchase.ts:93`). Material with no cost history →
`preferredCost: null`, guarded. Every `Math.max(...)` in bi-nuxt is seeded and every `reduce` has an
initial value.

**Sub-service failure cannot 500 the orders queue.** `_courier_block`, `_waitlist_badge`,
`_awaiting_work_orders`, `_cancellation_presets`, `_kitchen_note_tags` and
`_fiscal_emission_expected` all degrade to empty inside `try/except`.

**`station_locked` is handled on both orders read paths** — the board suppresses the false network error
(`orders-nuxt/app/pages/index.vue:448-455`) and the detail suppresses the false "not found"
(`[ref].vue:148-158`).

**hub-nuxt failure handling is the reference implementation** the other six apps should adopt —
`surfaces/hub-nuxt/app/presentation/hub.ts:47-92` separates station-locked / login / forbidden /
unavailable by `error.code` (never by matching Portuguese) and offers retry only where retry helps.

**Pickup-board privacy.** Committed orders show `Order.ref` (randomly generated), not `tab_ref`;
pre-commit comandas go through `_public_comanda_code` with `is_numeric_tab_ref` capped at 8 digits
(`kds.py:322-347`, `shop/services/pos.py:144-152`), which correctly excludes 11-digit phone numbers.
Delivery orders are excluded from the public board.

**`sign-ins/` and `notifications/` cannot read another user's data** — both filter on `request.user` with
no client-supplied id (`sign_ins.py:70`, `notifications.py:58`), and `_not_me` re-filters the event by
owner (`notifications.py:207`). The `user-<id>` SSE channel takes the id from the session, never the URL
(`shopman/backstage/urls.py:20-25`), and `_can_read_user_channel` rejects even staff reading another
person's stream (`eventstream.py:71-76`).

**KDS union discrimination and icon mapping are total** — `isExpeditionCard`
(`kds-nuxt/app/presentation/board.ts:56-60`) reads the explicit `is_expedition` flag, and every
`CHANNEL_ICONS` value plus the default is present in `MATERIAL_TO_LUCIDE` (`board.ts:134-141`), so an
unknown `channel_ref` cannot render a blank icon.

**Purchase receipt double-submit is closed at the DB**, and the count confirm is idempotent by
construction (delta recomputed at submit). Audience count is race-safe via an epoch guard
(`useAudienceCount.ts:24,45,52,60`).

**Production reads honour every nullable key.** `WorkOrderCard.started_qty`/`finished_qty`/`yield_rate`/
`loss`/`started_at_display` (`projections/production.py:1519-1530`), `matrix_row.recipe_pk`,
`matrix_row.suggestion`, `kds_card.current_step_index`/`time_remaining_min`,
`dashboard.capacity_percent`, `qc_card.started_qty`/`full_price_qty`/`discounted_qty`/`loss_qty`,
`qc.previous_open_date`, `mise_line.available_display`/`annotation` — each is guarded at its read site
(`ProductionStageGrid.vue:242,340,585,848,869`; `reports.vue:166`; `expedite.vue:143,154,337,429-431`;
`mise-en-place.vue:344,361`). The generated contract types every `| null` the Python emits — the TS does
not lie about optionality.

**Two kiosks closing the same fornada is the one place the loser sees the right thing.**
`CraftExecution.finish` takes `select_for_update` then re-checks status
(`packages/craftsman/shopman/craftsman/services/execution.py:80-100`); `_operator_error` maps
`TERMINAL_STATUS` to 409 `state_conflict`; `useQcKiosk.ts:50` refreshes on it. A `finish` retry after a
post-commit receiver failure is also safe — the server-derived key makes the core return the existing WO
and `_ensure_stock_ledger_closed`/`_ensure_order_links_closed` repair the ledger on replay
(`shopman/shop/services/production.py:404-463`).

**The kiosk clock is never trusted for the oven fact.** `armed_at`/`concluded_at` are server-stamped
(`shopman/backstage/models/oven_run.py:38`, `backstage/services/production.py:296`); the countdown is
explicitly local UX and `+N`/pause/resume declare nothing — ADR-021 §4 is honoured. A backgrounded tab
suspends the tick but `isRinging` re-derives from an absolute `endsAt` on wake, so the alarm fires late
rather than never (subject to P1-26).

**Insufficient input stock at finish is handled end to end** — `check_finish_materials` →
`ProductionStockShortError` → 409 with a structured `missing[]` → `parseShortage` → `ShortageDialog` →
force retry → `_create_stock_short_alert` fires an `OperatorAlert` even on the forced path
(`backstage/services/production.py:428-435`). A `Recipe` deleted or unpublished after the WO exists does
not break the reads: `_build_wo_card` uses `select_related("recipe")` and `_ingredient_name` falls back to
the raw SKU (`projections/production.py:2413-2431`) — only the *write* path trips (P0-11a). The
weighing/mise-en-place frozen-snapshot path is correct: `_work_order_recipe` returns items *and*
`batch_size` from the same source (`:2385-2411`), so a mid-morning `batch_size` edit cannot silently halve
the printed weights.

**Every production board keeps stale data visible with an honest degradation chip rather than blanking**
(`presentation/production.ts:245-261`, used at `ProductionStageGrid.vue:137-146`, `expedite.vue:21`,
`board.vue:25`, `mise-en-place.vue:38-46`, `reports.vue:79`) — the opposite of the KDS behaviour in P0-5.
Double-submit within one tab is guarded on every production write (per-row and per-WO busy sets, plus a
disabled Confirmar). **429 is unreachable** on every backstage route — only `AnonRateThrottle` is
configured (`config/settings.py:844-849`) and every route but operator-login and client-error is
authenticated; **423 is emitted only** by `OperatorPinChangeView` (`api/operations.py:719`).
