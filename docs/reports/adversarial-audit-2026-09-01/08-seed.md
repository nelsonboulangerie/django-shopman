# 08 — Seed data & bootstrap identity (audited by lead)

## P0

### S-1. `seed` bypasses the very guard that protects operator identity in production
- `config/management/commands/seed.py:936` — `call_command("setup_operators", "--yes", verbosity=0)`
- `shopman/shop/management/commands/setup_operators.py:30-31` — `DEV_PIN = "1234"`, `ADMIN_PASSWORD = "admin"`
- `setup_operators.py:96-103` — `--yes` exists *specifically* to force the caller to confirm
  "this is NOT production, PIN 1234 and password 'admin' are dev values". The seed answers
  that question with a hardcoded yes.

**Consequence.** `seed` is the deployment bootstrap (it lives in `config/`, it is what the
alpha runs). `_resolve_admin_password` (`seed.py:893-909`) correctly refuses to run outside
DEBUG without `ADMIN_PASSWORD` — so there IS an env guard for the *superuser*. There is none
for the operators. Once `ADMIN_PASSWORD` is supplied, the run proceeds to give **every real
operator PIN 1234**, and password `admin` to those who need one.

The PIN is the operator's identity for money: it is what the cash ledger records against a
sangria, a refund, a discount, a shift close. PIN 1234 for everyone means the counter has no
identity at all — any person who walks up is the manager.

**Fix.** `setup_operators` must refuse to run when `SHOPMAN_ENVIRONMENT == "production"` (or
when not `DEBUG`) regardless of `--yes`; `--yes` should confirm intent, not certify the
environment — the environment is a fact the process can read for itself. The seed should call
it only in non-production, and in production either skip operator creation or require
per-operator PINs from env.

### S-2. Dev badge tokens are derived from the username with no secret
- `setup_operators.py:57` — `hashlib.sha256(f"shopman-dev-badge:{username}".encode()).hexdigest()[:N]`
- issued into `PinCredential.badge_hash` at `setup_operators.py:_emitir_cracha`

**Consequence.** The salt string is a literal in a source file. Operator usernames are not
secret — they are shown on screen, written into the cash ledger, and printed on receipts.
Anyone who can read the repo (or guess `marina`, `admin`, …) can compute a valid badge token
offline and present it to the lock screen as that operator. This is a *second*, independent
identity bypass that survives fixing the PIN, and it is silent: the audit trail will name the
impersonated operator.

**Fix.** Same environment gate as S-1, plus derive dev badges from `SECRET_KEY` so the token
is not computable from public information even in dev.

## P1

### S-3. The shop ships with placeholder social links that reach the customer and Google
- `config/management/commands/seed.py:745-749` — `social_links` = `https://instagram.com/example`,
  `https://www.facebook.com/example`, `http://www.example.com.br`
- Rendered as clickable icons: `surfaces/storefront-nuxt/app/components/ShopHeader.vue:17,311-315`
- Emitted into structured data as the brand's official profiles:
  `surfaces/storefront-nuxt/app/presentation/seo.ts:185-186` → JSON-LD `sameAs`

Every other identity field in the same block is real and carefully set (phone `554333231997`,
`nelson@boulangerie.com.br`, the Londrina address, lat/long). These three were never replaced.
At go-live a customer tapping Instagram lands nowhere, and `sameAs` tells Google that
`example.com` is the bakery's official site — which is exactly the signal that merges a brand
with an unrelated domain in the knowledge panel.

**Fix.** Replace with the real profiles, or emit an empty list. An empty `social_links` renders
nothing (`v-if="socialLinks.length"`) and omits `sameAs` — both correct. A wrong link is worse
than no link.

### S-4. Superuser is seeded with `admin@example.com`
- `seed.py:915`. Low blast radius (it is not a delivery address for anything today), but it is
  the address a password-reset flow would target if one is ever enabled on the Admin.

## Accepted, not defects (verified deliberate)

- **58 products use Unsplash stock photos** (`seed.py:1120`, 59 call sites). Documented decision
  at `seed.py:1296-1305`: the house's own 51 photos cover what it has photographed; where it has
  none (drinks, Kãnfa, some breads) Unsplash is a reviewed placeholder, and the Porquinho is
  deliberately left photo-less because a wrong photo is worse than none. Recorded here so it is
  a *choice at launch* rather than a surprise — it does put `images.unsplash.com` in the
  customer's render path.
- **All 51 local product images resolve.** Referenced-vs-present diff is exactly zero in both
  directions (51/51). The `SHOPMAN_PRODUCT_IMAGE_BASE` env indirection (`seed.py:1113-1116`)
  correctly keeps the domain pointer out of the code.
- **Omotenashi copy**: 328 keys carry sane pt-BR defaults in `shopman/shop/omotenashi/copy.py`;
  the seed overrides one on purpose. The override mechanism is right; nothing is missing.
- **Seed calibration is real**, not invented: opening stock and the daily production plan are
  derived from actual NFC-e XML archives (jun/2019, jun/2021) per `seed.py:107-110,243-253`.
- **`CAFE-GRAO` min_stock / `tamura` supplier e-mail**: not in seed source. That residue lives
  in the alpha *database* and must be corrected there, not here.
