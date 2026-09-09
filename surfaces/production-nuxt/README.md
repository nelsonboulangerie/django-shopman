# Produção — production-nuxt

Headless operator surface for the bakery floor (**Produção**, served on the
`prod.` subdomain). Replaces the HTMX "KDS de produção" with a dedicated
Nuxt/UI-Thing app, consuming the canonical projection/action contract at
`api/v1/backstage/production/*` — no business rule is copied; the orchestrator
(Craftsman) decides.

- **Stable name:** `production-nuxt` (by function, like `pos-`/`kds-`/
  `orders-nuxt`). `prod.` is only the public host; never hardcode it
  (it lives in the deploy spec).
- **Gate:** `backstage.operate_production` (staff operator, granted to Cozinha/
  Gerente). Log into the Django admin first to get the session cookie, then open
  the app.
- **Form factor:** tablet/touch-first, light theme (dark available via the toggle
  for the back-of-house floor).
- **Private edge:** every document/API response is `private, no-store`, cannot be
  framed and inherits the security-header middleware from `operator-kit`.

Every production-domain write is fail-closed behind
`useProductionMutationGuard`: it requires an online station and a valid, unexpired
projection, then sends that projection's `projection_generated_at`,
`source_revision`, `fresh_until`, and `contract_version` with the idempotent request.
A local or server `stale_projection` refusal keeps the form open and offers the
contract's refresh recovery; refreshing never repeats the write automatically. Login
and alert acknowledgement are separate backstage contracts and do not consume
production projection metadata.

## Telas

- **Chão ao vivo** (`/`) — started WorkOrders board: advance step, finish (with
  material-shortage override), void. The old HTMX production KDS, now Nuxt.
- **Planejamento** (`/plan`) — the production matrix: per-SKU
  planned/started/finished totals + demand suggestion, inline plan + start.
- **Fornadas** (`/board`) — full-screen operator forecast, still protected by the
  production permission.

`/menuboard` is deliberately absent. The only canonical menuboard is the Django
surface `/menuboard/<ref>/`, protected by staff session or a kiosk token and updated
through its canonical SSE projection. D4 still has to map the physical TVs to refs
and choose the cutover window; this app does not guess or redirect to a board.

## Dev

```bash
npm ci
npm run dev          # http://127.0.0.1:3005  (navigate via 127.0.0.1, never localhost)
npm run test         # vitest — pure presentation layer
```

In development/test, `NUXT_DJANGO_BASE_URL` defaults to `http://127.0.0.1:8000`.
A production build/boot fails unless it receives an explicit environment marker
(`SHOPMAN_ENVIRONMENT`, for example `staging` or `production`) and a non-local HTTPS
`NUXT_DJANGO_BASE_URL`; both must also exist at runtime. The upstream is private
runtime config and is never exposed as `NUXT_PUBLIC_*`.

The generic surface image supplies `https://django-upstream.invalid` only while
compiling this app. That reserved, non-routable origin keeps the image environment
agnostic and is not exported into the runtime stage; the Nitro boot guard still
requires the actual environment and upstream. Local E2E uses a separate double opt-in
documented in `tests/e2e/README.md`.

## Layout

- `app/pages/index.vue` — live floor board (started WorkOrders).
- `app/pages/plan.vue` — planning matrix.
- `app/composables/useProductionKds.ts` — live-floor read-side (fetch + 30s poll) + actions.
- `app/composables/useProductionBoard.ts` — planning read-side + plan/start actions.
- `app/presentation/production.ts` — pure board shaping (tones, affordances, shortage parsing).
- `app/types/production.ts` — TS mirror of the Django production projections.
- `server/api/v1/[...path].ts` — Django proxy (CSRF); transporte canônico na layer
  `operator-kit` (`server/utils/djangoProxy.ts`, auto-importado pelo Nitro).
