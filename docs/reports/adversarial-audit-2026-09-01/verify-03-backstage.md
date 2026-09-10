# Adversarial re-audit of `03-backstage-contract.md` § P0

Method: each of the 11 P0 claims was attacked, not confirmed. For each, the cited lines were re-read
at HEAD (`ba3281031`), the surrounding code was searched for a guard the original auditor might have
missed (caller-side check, serializer, DB constraint, middleware, settings default, `select_for_update`),
the trigger was checked against what this deployment actually configures (`config/settings.py`,
`config/management/commands/seed.py`, `.do/*.yaml`), and the test suite was read for a test that
exercises the claimed-broken path. No tests were executed (shared DB). Read-only; nothing was edited.

**Headline: the facts held; the severities did not.** Nine of eleven are true statements about the code
that do not meet the house's own bar for P0 (blocks go-live / loses money / corrupts data / breaches
security). Two survive at P0 intact.

## Verdicts

| # | Verdict | Corrected severity | Evidence that decided it |
|---|---------|--------------------|--------------------------|
| 1 | OVERSTATED | **P1** | Fact holds: `shopman/shop/services/pos.py:1994-1998` emits `remove_line` for every existing line; grep for `version\|If-Match\|etag\|claimed_by\|expected_rev` over `shop/services/pos.py` + `backstage/api/operations.py` + `backstage/models/pos.py` returns only `_expected_rev` (production, `operations.py:1832`) and `last_touched_at` writes — no read of either. But the deployment has **one** drawer (`config/management/commands/seed.py:7437` `CashTerminal.default()`, one terminal), and the second half of the repro is false: `surfaces/pos-nuxt/app/pages/display.vue` contains no `action.call`/`saveTab`/`usePosSale` — the display never writes. A durable trace does exist (`_audit_line_diff`, `shop/services/pos.py:243-261`, emits `line_removed`). |
| 2 | OVERSTATED | **P1** | Fact holds exactly as written: `shopman/backstage/api/operations.py:2311` reads `request.data.get("terminal_ref")` while the other cash views use `_terminal_do_pedido` (`operations.py:2641-2649`); `surfaces/pos-nuxt/app/composables/usePosCashSession.ts:132-138` sends only `{closing_amount, notes}`, and `openCashShift` (`:126-128`) does send `terminal_ref` — the asymmetry is real. `close_cash_shift` → `current_shift(terminal_ref, strict=True)` (`backstage/services/pos.py:685`) → `resolve_terminal` raises `POSTerminalAmbiguous` (`:773-777`). `cash.close_shift` has exactly one caller in `shopman/` (`backstage/services/pos.py:697`), so there is no second surface. `shopman/backstage/tests/test_terminal_ambiguo.py` covers `movement`, never `close`. Severity drops because the trigger does not exist today and is reversible from the same screen that creates it (Terminal `is_active` is editable at `packages/cashman/.../admin_unfold/admin.py:141-149`). |
| 3 | OVERSTATED | **P1** | Half the claim is wrong (see below). Fact that survives: `shopman/backstage/services/closing.py:445` puts `payment_method_totals` — day revenue by method — in a payload gated only by `backstage.perform_closing` (`operations.py:1070-1077`), a permission *Gerente* holds (`setup_groups.py:165`) while `cashman.audit_shift` is deliberately withheld (`setup_groups.py:239-241`), and `POSCashReportView`'s docstring says that number is not for the manager (`operations.py:2895-2902`). It is SSR-serialised (`surfaces/pos-nuxt/app/composables/useDayClosing.ts:19-22`, cookie headers, no `server:false`). Not rendered by any component. |
| 4 | OVERSTATED | **P2** | Fact holds: `projections/closing.py:246-252` filters `_quantity__gt=0`, and `closing.vue:338` (`v-if="closing.has_items && …"`) plus `presentation/closing.ts:60-61` (`if (!items.length) return false`) both disarm the CTA. But the trigger requires **every** saleable SKU at zero, and the catalogue carries non-perishables that do not sell out: `config/management/commands/seed.py:284-304` stocks `AG` (água), `MT`, `BK`, `TP`, `PT`, `CX`, `GL`, `QC`, `QP`, `GR`, `THL`, `LN` into the saleable `vitrine` position (`seed.py:2756`, `is_saleable=True`). |
| 5 | CONFIRMED (fact) / OVERSTATED (severity) | **P1** | Verified in this repo's own dependency: `surfaces/kds-nuxt/node_modules/nuxt/dist/app/composables/asyncData.js:376` — `asyncData.data.value = unref(options.default())` in the `.catch`. `useKdsBoard.ts:16-22` and `useKdsCustomerBoard.ts:11-14` pass no `default`, so `data` → `undefined` → `view` → `null` → `[ref].vue:339 v-if="view"` fails. The dead-code finding is right: `[ref].vue:333` `v-else-if="error && view"` can never be reached. Severity drops because the poll continues and the board returns on the next success (15 s / 10 s) — degradation, not loss. |
| 6 | CONFIRMED (fact) / OVERSTATED (severity) | **P1** | `shopman/backstage/projections/kds.py:183` `KDSInstance.objects.get(ref=…, is_active=True)`; `backstage/api/kds.py:68-70` has no `try`; `shop/api_errors.py:56-57` returns `None` for a non-DRF exception; no middleware in `config/settings.py:241-261` translates `ObjectDoesNotExist`. The URL converter is `<slug:ref>` (`api/urls.py:188`), so a typo reaches the view. The house's own standard is proven two routes below: `test_api_kds_surface.py:243,252` assert 404 for a missing ticket and a missing expedition order. Severity drops: recovery is re-ticking `is_active`; no money, no data. |
| 7 | **CONFIRMED** | **P0** | The strongest of the eleven, and it got stronger. Backend gate at `operations.py:1325-1335`; `validate_manager_override` (`shop/services/pos.py:1938-1945`) raises `manager_approval_required` when neither badge nor username+pin is present; `PosIntentError.status = 422` (`shop/services/pos_intent.py:69`). `shopman/backstage/tests/test_api_orders_cancel_policy.py:176-184` asserts exactly that 422 for a paid order — the backend behaviour is deliberate and tested. `grep -rl manager_approval surfaces/*/app` returns pos-nuxt and operator-kit **only**; orders-nuxt has zero occurrences, and `useOrderDetail.ts:54` sends `{reason, cancellation_code}`. No alternative surface: `POSCancelRecentSaleView` covers POS sales, not web orders. Cancelling a paid web order from the Gestor is impossible. |
| 8 | OVERSTATED | **P1** | Divergence is real: FE `purchase.ts:55-62` — `"1.250"` has no comma → `Number("1.250")` = 1.25 → 125 q; BE `backstage/services/purchase.py:797-801` — no comma, one dot with 3 decimals → `else` → strip dots → 125000 q. But the FE number never reaches the server: `usePurchaseDesk.ts:962-972` posts `lines: receiptLines.value` (the raw `costInput` text); `receiptTotalCostQ` (`:531-533`) feeds only the on-screen summary/`receiptSnapshot`. **The stored value is the correct one** — the defect is a 100×-wrong preview, not corrupt data. |
| 9 | OVERSTATED | **P1** | Fact holds, and is worse than stated: `config/settings.py:1474-1477` pins the `shopman` logger to `"DEBUG" if DEBUG else "INFO"` — hardcoded, so unlike `root`/`django` (`:1466,1471`) it cannot even be raised with `DJANGO_LOG_LEVEL`. Sentry (`settings.py:1495-1497`) never sees these because the exceptions are swallowed, not re-raised. The counts in the claim are wrong: `operations.py` has **28** `except Exception`, **25** `logger.debug`, 2 `warning/error` — "24, 25 of which" is arithmetically impossible. Severity: observability + a raw Python string in a 400; nothing breaks. |
| 10 | **CONFIRMED** | **P0** | `backstage/services/production.py:154-157` calls `production_core.quick_plan` → `shop/services/production.py:208-214` → `CraftPlanning.plan` → `scheduling.py:86-98` → `_create_work_order` → `WorkOrder.objects.create` (`scheduling.py:129`), unconditionally, with no lookup for an existing same-day WO. `apply_finish`'s guard hashes `work_order.pk` (`backstage/services/production.py:479-490`), so a fresh pk mints a fresh key every time — the guard is structurally unreachable, exactly as claimed. `WorkOrderQuickFinishView` (`operations.py:2046-2081`) accepts no client key. `useQcKiosk.ts:38` `submitting` is in-process only. Consequence is a second `production_changed(action="finished")` fan-out → a second `kind=MAKE` ledger write and a second insumo consumption. Data corruption in the stock ledger: P0 stands. |
| 11 | OVERSTATED | **P1** (a) / **P2** (b) | Both legs verified. (a) `_get_active_recipe` raises `ValueError` (`shop/services/production.py:503-509`); `_operator_error` returns a non-`CraftError` unchanged (`backstage/services/production.py:49-50`); `WorkOrderQuickFinishView` (`operations.py:2079`), `WorkOrderVoidView` (`:2104`), `WorkOrderAdvanceStepView` (`:2033`) and both oven views (`:2129,:2146`) catch `ProductionError` only, while Plan/Start/Finish (`:1930,:1969,:2012` area) also catch `ValueError`. `_ProductionActionBase` (`operations.py:1854-1893`) has no `handle_exception`. (b) `_get_work_order` sits outside the `try` at `backstage/services/production.py:427` and `:503` — but the oven views *do* translate it (`:267-269, :299-301`). Severity: (a) is a real dialect leak on a narrow race (recipe deactivated inside the kiosk's 30 s snapshot); (b) needs a `wo_id` no surface produces. |

**Counts — CONFIRMED at P0: 2 · OVERSTATED: 9 · REFUTED: 0 · DUPLICATE: 0.**

No claim was factually false end-to-end, and none is a duplicate of another or of a documented
accepted decision. The audit's defect is severity inflation, not fabrication: it labelled nine real
P1/P2 findings P0, which is itself a defect — a list where 11 of 11 are "P0" cannot be triaged.

---

## What the original auditor got wrong, claim by claim

### P0-1 — POS comanda last-writer-wins

**Right:** there is no revision, no `If-Match`, no `select_for_update`, and `_replace_session_ops`
genuinely removes every line and re-adds the client's snapshot. I looked specifically for a caller-side
guard, a serializer check, a unique index and a lock, and found none. The proposed fix is sound.

**Wrong, three ways.**

1. **The repro's premise is not this deployment.** The seed registers a single drawer
   (`seed.py:7437`, `CashTerminal.default()`); there is no second till. The docstring the auditor
   quotes (`backstage/services/pos.py:729-742`) says the second till is a *future* case — it is
   written in the future tense ("Quando a loja tiver balcão + totem"), and the auditor read it as a
   statement about today.
2. **The single-till fallback is partly false.** "on the POS and the `/display` window" does not hold:
   `surfaces/pos-nuxt/app/pages/display.vue` has no write path at all — no `action.call`, no
   `usePosSale`, no `saveTab`. Only "the same comanda open in two browser tabs" survives, which is an
   unusual gesture on a single kiosk-style till.
3. **"nothing on either screen says so" overstates the silence.** `_audit_line_diff`
   (`shop/services/pos.py:243-261`) writes a durable `line_removed` session event inside the same
   transaction. The auditor mentions it and then dismisses it as "an audit event no operator ever
   sees" — true of the moment, false of the forensics: the loss is reconstructable.

Money can be lost (the customer is undercharged by A's three items), which is why this stays P1 and
not P2. But it is concurrency-gated on a configuration the shop does not have.

### P0-2 — Cash shift cannot be closed with a second drawer

**Right, and precisely right.** The asymmetry between `POSCashCloseView` and the other nine cash views
is exactly as described, the frontend genuinely omits `terminal_ref` on close while sending it on open,
and `cash.close_shift` has one caller in the whole tree, so there is no back door. The test file that
exists for this hazard (`test_terminal_ambiguo.py`) covers `movement` and `resolve_terminal` and stops
short of `close` — the coverage gap is real.

**Wrong on severity, for two reasons.** First, the trigger is a configuration nobody has made: one
`Terminal` in the seed, and the P0 bar is not met by a bug behind an unset config. Second — and this is
the substantive difference from the trap the docstring memorialises — **there is an exit through the
UI**. The condition is created in Admin → Equipamentos and is undone in the same screen: `Terminal`'s
Unfold admin exposes `is_active` (`packages/cashman/shopman/cashman/contrib/admin_unfold/admin.py:141-149`).
The 2026-08 incident was unrecoverable because *nothing* the operator could reach changed the state;
here, un-ticking the row that caused it restores close. That is a P1 with a documented workaround, not
a P0 dead end. Fix it anyway — the one-line change to `_terminal_do_pedido` is free.

### P0-3 — Closing projection leaks the apuração

**Right on the leak.** `payment_method_totals` (day revenue by method, `services/closing.py:445`) is in
a response gated only by `backstage.perform_closing`, a permission *Gerente* has and which the house
pairs with an explicit refusal of `audit_shift` (`setup_groups.py:239-241`). `POSCashReportView`'s
docstring names revenue privacy as the reason for its own gate and says "nem para o gerente"
(`operations.py:2900-2902`). Those two facts cannot both be the policy. This should be fixed.

**Wrong on the half that carried the P0.** The claim's force comes from the blind count — "quem sabe o
esperado não conta às cegas", the sentence the auditor quotes from `setup_groups.py`. That half does not
hold. `_cash_shift_summary` computes `expected_amount_q` / `difference_q` / `blind_closing_amount_q`
**only in the `for shift in closed:` loop** (`services/closing.py:415-431`). The `open_shifts` rows
carry `id`, `terminal_ref`, `operator`, `opened_at` and nothing else (`:437-444`). The manager about to
count blind is counting an **open** shift, and the projection tells them nothing about it. There is no
gabarito. What leaks is the arithmetic of shifts *already counted*, plus the day's revenue mix.

Second correction: the auditor's own text concedes that neither page renders the key
(`app/types/closing.ts` does not declare it) — so the exposure is a JSON payload readable in devtools by
an authenticated *Gerente*, the most trusted operator role in the house. That is a policy inconsistency
worth closing, not a breach. P1.

### P0-4 — Sold-out day cannot be closed

**Right on the mechanism.** `has_items` gates the submit block twice over (template `closing.vue:338`
and `presentation/closing.ts:60`), the backend is perfectly happy with an empty list
(`services/closing.py:39-97`), and the Admin/Unfold alternative is gone. The one-line fix is correct.

**Wrong on reachability, which is what makes it a P0 claim rather than a P2 one.** `has_items` is false
only when **no** saleable SKU has stock — not when the bread sells out. This catalogue is not bread-only:
`STOCK_VITRINE` (`seed.py:254-304`) stocks bottled water (`AG`, 48) and eleven mercearia SKUs
(`MT`, `BK`, `TP`, `PT`, `CX`, `GL`, `QC`, `QP`, `GR`, `THL`, `LN`) into `vitrine`, which is the
`is_saleable=True` position (`seed.py:2756`). Shelf-stable grocery and bottled water do not go to zero
on the day the bread sells out. "For a bakery whose model is selling out, the day it sells out is the
day…" reads a plausible sentence about bread onto a query that is about every saleable SKU at once.

### P0-5 — Failed poll blanks the board

**Right, and I verified it against the exact dependency in this tree** rather than from general Nuxt
knowledge: `surfaces/kds-nuxt/node_modules/nuxt/dist/app/composables/asyncData.js:376` really does
`asyncData.data.value = unref(options.default())` in the error path, and neither composable passes a
`default`. The dead-code observation about `[ref].vue:333` is correct and is the kind of finding worth
having: a comment two lines above it (`:325-326`) asserts the opposite of what the code does.

**Wrong on severity.** The board comes back on the next successful poll — 15 s on the kitchen board,
10 s on the customer TV — and the poll keeps running (`setInterval` is untouched by the error path).
Nothing is written, nothing is lost, nothing is unrecoverable. The "forever" in the auditor's repro is
borrowed from P0-6 (a permanent 500), and belongs to that claim, not this one. A transient blank is P1.

### P0-6 — Unknown/deactivated station → 500

**Right on every element**, and I checked the three places a rescue could plausibly live: `api_errors.py`
(returns `None` for a non-DRF exception, `:55-57`), the middleware stack (`settings.py:241-261`, nothing
that translates `ObjectDoesNotExist`), and the URL converter (`<slug:ref>`, `api/urls.py:188` — a typo
does reach the view). The inconsistency is sharp because the neighbouring ticket routes already answer
404 and have tests saying so (`test_api_kds_surface.py:243-256`).

**Wrong on severity only.** No money, no data, and recovery is the same Admin tick that caused it. What
makes it worth fixing is diagnosability — the tablet blames the network for a configuration change —
which is a P1 concern. Note also that this claim and P0-5 are not independent findings so much as two
halves of one story: the auditor's "forever" scenario requires both, and fixing either one alone
removes the "blaming the network" symptom.

### P0-7 — "Cancelar (gerente)" dead end — **CONFIRMED, P0**

I attacked this one hardest and it did not move. Every escape I looked for is closed:

- `validate_manager_override` does not exempt a caller who is themselves a manager — it rejects on the
  *absence of the payload field*, before any identity check (`shop/services/pos.py:1938-1945`), and the
  design comment at `:1946-1949` says that is deliberate ("a segunda assinatura existe para haver duas
  pessoas").
- The backend is not accidental: `test_api_orders_cancel_policy.py:176-184` asserts the 422 and
  `:229-240` asserts `cancel_requires_approval is True` on the projection. The contract is tested from
  the server's side and simply never implemented on the client's.
- `grep -rl manager_approval surfaces/*/app` → pos-nuxt + operator-kit only. orders-nuxt: zero.
- No second surface can do it. `POSCancelRecentSaleView` is scoped to recent POS sales; Admin does not
  execute order lifecycle.
- The policy fires broadly, not narrowly: `requires_approval=True` for captured payment **or**
  `unknown` **or** an exception reading payment (`shop/services/cancellation.py:153-165`) — the
  fail-closed default means even a payman hiccup lands here.

A paid web order that the customer wants cancelled cannot be cancelled by the operator. That blocks a
real, routine, money-bearing operation with no workaround. P0 confirmed.

### P0-8 — Purchase money parser divergence

**Right that the two parsers disagree**, and the arithmetic in the claim is correct: `"1.250"` is 125 q
on the client and 125000 q on the server. The missing test cases are missing.

**Wrong about the consequence, which is the whole of the severity.** The client's number is never sent.
`confirmReceipt` posts `lines: receiptLines.value` — the raw `costInput` strings
(`usePurchaseDesk.ts:962-972`) — and the server parses them itself. `receiptTotalCostQ`
(`usePurchaseDesk.ts:531-533`) feeds the on-screen summary and `receiptSnapshot` only. So the claim's
"the server writes 125000 centavos … to `Move`/`SupplierMaterialCost`" describes the server writing the
**correct** pt-BR reading of "1.250". Nothing is corrupted; the preview lies by 100×. That is still a
genuine money-UI defect — an operator who trusts the R$ 1,25 preview and "corrects" the field can talk
themselves into a real error — but it is a wrong number on a screen, not a wrong number in the ledger.
P1. (The `"1.234.567"` case is milder still: `NaN` → 0 trips the blocker at `purchase.ts:447`, so the
confirm is disarmed rather than wrong.)

### P0-9 — Broad `except Exception` invisible at INFO

**Right, and the underlying fact is worse than the claim.** `config/settings.py:1474-1477` pins the
`shopman` logger's level to `"DEBUG" if DEBUG else "INFO"` as a literal — it is not read from
`DJANGO_LOG_LEVEL` the way `root` and `django` are (`:1466,:1471`). So an operator debugging on
go-live day cannot even raise the level by env var without a deploy. Sentry does not compensate: the
exceptions are swallowed and never reach the Django integration.

**Wrong on severity, and sloppy on the arithmetic.** The claim says "**24** `except Exception as exc:`
blocks, **25** of which log via `logger.debug`" — 25 of 24 is impossible. The real counts at HEAD are
28 `except Exception` and 25 `logger.debug`. Beyond the slip: nothing here breaks, nothing is lost,
nothing is exposed to a customer. It is a diagnosability defect (plus a mild leak of a raw Python
exception string into a 400 body). Worth fixing before go-live; not a go-live blocker. P1.

### P0-10 — `quick-finish` idempotency structurally unreachable — **CONFIRMED, P0**

The one claim where I went looking for a consolidation guard and expected to find one — the neighbouring
`set_planned_quantity` docstring says "create, adjust, **or consolidate**" — and there is none on this
path. `quick_plan` (`shop/services/production.py:208-214`) calls `CraftPlanning.plan`, which goes
straight to `_create_work_order` → `WorkOrder.objects.create` (`scheduling.py:86-98, :129`) with no
lookup for an existing same-recipe/same-day/same-position work order. The finish-leg key really is
`f"production.finish:{work_order.pk}:{digest}"` (`backstage/services/production.py:490`), so a fresh pk
defeats it by construction. `WorkOrderQuickFinishView` accepts no client key. The only guard in the
whole path is `useQcKiosk.ts:38`'s in-process `submitting` ref, which a reload discards.

The consequence reaches the stock ledger — a second `production_changed(action="finished")` fan-out is
a second `kind=MAKE` write and a second insumo consumption — which is data corruption in the one place
the house treats as immutable. P0 confirmed.

### P0-11 — Four production writes emit HTML 500

**Right on both legs**, verified line by line, including the negative check that `_ProductionActionBase`
(`operations.py:1854-1893`) defines only `initial` and no `handle_exception`, so nothing catches these
above the view.

**Wrong on severity, and the two legs are not the same size.**

- **(a) `ValueError` on quick-finish/void/advance-step/oven** is a genuine dialect violation on a narrow
  race: the recipe must be deactivated inside the kiosk's ≤30 s snapshot window. The operator gets a
  generic toast and a retry that never works — annoying and undiagnosable, but bounded, and the
  reachable trigger is a manager deactivating a recipe mid-service. P1.
- **(b) `WorkOrder.DoesNotExist`** needs a `wo_id` that does not exist in the database. No surface
  produces one: every id comes from a board projection, and work orders are voided, never deleted. It
  is reachable by a hand-crafted request or a stale tab after a reseed. The claim's own evidence
  undercuts its urgency — the two oven views already translate it (`backstage/services/production.py:267,299`),
  which shows the house knows the pattern and applied it where it mattered. P2.

Neither leg loses money, corrupts data, or breaches anything. The proposed fix (translate
`WorkOrder.DoesNotExist` once in `_ProductionActionBase.handle_exception`) is the right shape and cheap;
it just is not a go-live blocker.
