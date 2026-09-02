# 10 — Notifications: the half of the experience that happens on the phone (audited by lead)

Scope note: PR #472 is in flight on this area (placeholder derivation + two copy defects). It
is a good fix and these findings are **complementary, not overlapping** — none of them are
addressed by it. Anything implemented here must land *after* #472 to avoid conflicting in
`notification_sms.py`, `_notification_templates.py` and `seed.py`.

## P0

### N-1. Every transactional e-mail is sent From a non-routable address, and that "success" kills the fallback chain
- `config/settings.py:819` — `DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@shopman.local")`
- `shopman/shop/adapters/notification_email.py:218-220` — `from_email = config.get("from_email") or settings.DEFAULT_FROM_EMAIL`
  (with a second literal fallback, `noreply@example.com`)
- Set in **neither** deploy spec: `grep DEFAULT_FROM_EMAIL .do/*.yaml` → no match

`.local` is a reserved TLD (RFC 6762, mDNS). It has no public DNS, no SPF, no DMARC alignment.
Mail sent From it is rejected or spam-filed by essentially every receiver.

The damage is not "some e-mail bounces". It is the **fallback chain**:
`shopman/shop/services/notification.py:172-176` treats a truthy `send()` as delivered and
**returns immediately** — SMS and WhatsApp are never attempted. `send_mail(fail_silently=False)`
raises only if the *relay* refuses; a relay that accepts-then-bounces returns success. So the
adapter reports True, the chain stops, and the log line says `Email sent`.

The event that rides this chain is `payment_requested` — the payment link. Customer never
receives it, order expires unpaid, nobody is alerted. This is the same outcome as item 4 of
`docs/plans/fallbacks-perigosos-go-live.md`, reached through a door that item 4's fix
(`_BACKENDS_INERTES`, now correctly implemented at `notification_email.py:238`) does not cover:
the backend is genuinely live, it is the *sender identity* that is invalid.

**Fix.** `DEFAULT_FROM_EMAIL` must have no default — absent ⇒ `ImproperlyConfigured` at boot
(the pattern `packages/doorman/apps.py` already uses correctly), or at minimum derive from
`Shop.email` (`nelson@boulangerie.com.br`, already seeded and real). Declare it in both specs.
Independently, the chain should not treat "the relay accepted it" as "the customer got it" for
money-carrying events — but the sender identity is the cheap, complete fix.

## P1

### N-2. Seeding the Admin templates makes the ASCII SMS bodies dead code, and roughly triples SMS cost
- `shopman/shop/adapters/_notification_templates.py:56-64` — `render_message` returns the DB
  body unconditionally when one exists; the channel fallback dict is only reached when it does not
- `config/management/commands/seed.py:7213-7245` — the seed writes a `NotificationTemplate` row
  for **every** order event
- `shopman/shop/adapters/notification_sms.py:26-52` — the ASCII fallback table, whose comment
  states the reason for its existence: *"acento fora do GSM-7 força UCS-2 e o segmento cai de
  160 para 70 caracteres — o SMS passa a custar o dobro"*

After `seed` runs, that table is unreachable. Measured, using the seeded bodies:

| event | seeded body | ASCII fallback |
|---|---|---|
| `order_accepted` | UCS-2, 89 units → **2 segments** | GSM-7, 43 → 1 segment |
| `payment_requested` | UCS-2, 153 units → **3 segments** | GSM-7, 99 → 1 segment |
| `order_ready_pickup` | UCS-2, 80 units → **2 segments** | GSM-7, 36 → 1 segment |

The author of the fallback table predicted exactly this and the seed defeated it. Note the
comment says *"Estes são só o fallback"* — which is true in principle and false in practice: the
fallback is never the value.

### N-3. WhatsApp bold markup leaks into SMS and plain-text e-mail
The seeded bodies use `*{order_ref}*` and `*{total}*` — WhatsApp markdown. The same string is
sent verbatim as the SMS text and as `message=` (the plain-text part) of every e-mail
(`notification_email.py:225`). The customer reads `Seu pedido *NB-1234* foi confirmado` with
literal asterisks. It also contributes to N-2's segment count.

**Fix for N-2 + N-3 together.** Either (a) keep one body and strip channel-specific markup at
render time per channel, or (b) let `NotificationTemplate` carry a per-channel body and have
`render_message` prefer the channel's. (a) is smaller and preserves the "shopkeeper edits one
text" design; the transform is: drop `*`, collapse `\n\n`, and for SMS transliterate to ASCII
— all of which the house already knows how to express.

## P2

### N-4. Omotenashi gaps in the seeded bodies
Judged against "what would a thoughtful host have already said":
- `order_ready_pickup` — *"Venha buscar. Obrigado!"* says nothing about **until when** it will
  be held, or **where**. For a bakery item that goes stale, "guardamos até as 18h" is the
  single most useful sentence on the message.
- `order_cancelled` / `order_rejected` — neither says what happens to **money already paid**.
  A customer who paid and reads "cancelado" with no word about the refund is alarmed, and calls.
  (#472 improves both by pointing at the order screen; the refund sentence is still absent.)
- `payment_expired` — *"O pedido foi cancelado automaticamente"* is a dead end. No way back,
  no link, no invitation to re-order.
- `order_received_outside_hours` — states the total but never says **when** they will be
  attended ("assim que abrirmos" — abrimos when?). The shop's hours are known data.

These are the owner's call on tone; they are recorded as concrete gaps, not applied.

## Verified-safe
- Item 4 of the fallbacks doc **is fixed**: `notification_email.is_available` now rejects
  console/locmem/dummy backends via `_BACKENDS_INERTES` (`notification_email.py:236-247`). The
  doc is stale on this point.
- `SafeFormatMap` / `render_template` degrade correctly: a shopkeeper's typo in an Admin
  template yields an imperfect message rather than silence. That is the right trade.
- The 328-key `OmotenashiCopy` catalogue carries sane pt-BR defaults; the notification templates
  are a separate, correctly-modelled concern.
