# Sales readiness — Fortnite Pirate Token

Current status: **private functional beta, NOT ready to accept money**.

The payment page is intentionally a local demonstration/quote planner. It does not
take card/SBP/QR/Steam inventory payments or activate a subscription.

## Minimum prerequisites for a paid release
1. Create an independent merchant backend, deploy behind TLS and move the licence
   logic off the customer-controlled desktop application.
2. Integrate a compliant payment processor for cards/SBP and hosted QR checkout;
   verify signed provider webhooks, idempotency, amounts and order identities server-side.
3. Telegram purchases of in-bot digital access require the applicable Telegram Stars
   flow. Verify successful payment server-side before granting any access.
4. For Steam items, use a legally and technically supported inventory/trade provider.
   Inspect item ownership, price, deposit settlement, trade holds and refund fraud
   before a payment is considered final. Do not enable CS2/Rust/Dota 2 skins merely
   because they appear in the preview UI.
5. Give users a clear view of plan length, exact price, renewal, cancellation,
   refunds, support and privacy information; never promise ban safety.
6. Issue short-lived server-validated entitlement tokens, one active policy per
   paid account, revocation and expiry. Avoid shipping reusable master keys.
7. Distribute only signed, versioned installers after Windows testing.
8. Review Epic Games' current gameplay-automation rules and branding requirements
   before marketing or selling the utility.

## What testers receive
They receive a **free beta installer**, not a paid subscription. Ask them for bug
reports about app startup, keyboard shortcuts, Fortnite window recognition,
responsive Stop, language switching, and interface layout.

**Do not grant licences automatically from local draft orders.** Only a trusted
server can confirm completed payments and entitlement status.
