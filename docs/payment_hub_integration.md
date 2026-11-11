# Fortnite Pirate Token — Payment Hub integration contract (v1.3.9)

**Status: UI/catalog and local request drafts only. Real checkout, quotes, trade
acceptance and paid subscription activation are intentionally disabled.**
This document prevents a future implementer from trusting user-side state.

## Supported payment choices

| Desktop launcher option | Actual production processor | Completion evidence |
| --- | --- | --- |
| Telegram Stars | Telegram bot (digital purchases within Telegram) | Bot update `successful_payment` with XTR, order binding and verified server record |
| Bank card | Hosted checkout from licensed payment provider | Signed/verified provider event + independently re-fetched final payment status |
| SBP | Bank/acquirer or licensed PSP checkout | Final provider payment status for the correct order |
| SBP QR | Per-order dynamic QR from payment provider | Same verified final transaction; scanning alone proves nothing |
| Bank transfer | Merchant bank account | Independent merchant-side reconciliation with amount, reference and bank statement |
| Steam items | Separate external Steam-trade workflow | Merchant-side trade/inventory verification, quoted assets, restrictions and finality |

Do not collect raw card numbers, bank access credentials, Steam passwords,
Steam Guard codes or merchant API keys in the Windows app.

**Telegram-only restriction:** Telegram bots and mini apps selling digital
subscriptions must process that purchase in Telegram Stars (`XTR`). Card, bank,
QR and item workflows belong to a separate merchant-controlled desktop/web
checkout, not a Telegram bot invoice or mini app.

**Steam trade warning:** Steam warns not to trade items for something outside
the trade window. Off-platform subscription-for-item trades are not Steam
protected. Have the merchant review platform terms, scam exposure, applicable
trade limits, refunds and business compliance before making skin checkout live.

## Game eligibility

Potential Steam item sources: Dota 2 (570), Rust (252490), TF2 (440),
PUBG (578080), Don't Starve Together (322330), NARAKA (1203220),
Counter-Strike 2 (730). A game listing on Community Market does not imply
that *every* item is tradable or immediately available for transfer.

CS2 trades are Trade Protected and reversible during their 7-day protection
window. Never grant irrevocable entitlement until that window has expired,
the trade has been checked again and there are no pending disputes.
CS2 protected items cannot be combined with non-protected items in a Steam
trade. Other games may have regular trade holds; check item-level restrictions.

## Production architecture (NOT implemented)

1. Set prices and durations in a server-owned tariff table; never let the
   desktop app decide its own price. Keep payment amounts in integer kopeks
   and Stars in integer XTR amounts.
2. Create an HTTPS endpoint authenticated to a verified customer identity.
   Issue a one-use invoice ID with plan, currency, full amount and expiry,
   stored on the merchant server.
3. For cards/SBP/QR: create provider checkout server-side with idempotence key;
   return only a short-lived payment page URL/QR to the launcher. Verify
   webhooks against the provider and re-query payment status before marking
   a given invoice as paid. Handle duplicate/reordered webhook events safely.
4. For Stars: Telegram bot creates `XTR` invoice. Correlate payload to
   merchant invoice/customer ID, verify `successful_payment` server-side,
   store Telegram charge ID once, and support /paysupport and refunds.
5. For Steam items: obtain actual inventory IDs/tradability server-side,
   verified quotes including cash-out friction and fees. Compute a subset
   using `payment_hub.pick_items` with authoritative quoted net kopeks.
   Issue a short-lived acceptance quote bound to asset IDs and receiver.
   Verify actual completed trade contents and trade protection/escrow state
   on a trusted service. No delivery based on screenshots or user claims.
6. For bank transfer: never grant access on an uploaded receipt. Use bank
   reconciliation or merchant confirmation, not a user-clicked button.
7. Issue a signed customer-specific entitlement from the merchant server only
   after verification. The client must check the signed entitlement and
   expiry online, with clear policy for temporary offline usage. Prevent
   duplicate crediting, handle refunds/reversals, retain minimal audit logs.
8. Do not store merchant credentials in git, config.json or bundled files.
   Keep PSP, Telegram and Steam merchant credentials on the secure service.

## Currently implemented (v1.3.9)

- Backend allowlisted catalog and Steam game list.
- `payment_interest_create(plan, method, game)` — **local non-payable draft**
  saved on the customer device. It does not reach the merchant or activate.
- UI selector in Subscriptions, exact method disclaimer and CS2 warning.
- Pure bounded combination selector `pick_items` for future verified quotes;
  not exposed to untrusted client-supplied prices.
- Tests ensuring all methods remain inactive, no licence is granted,
  CS2 cannot be mixed with unprotected items, and near-exact combinations
  minimize overpayment.

## Source documentation

- Telegram digital payments: https://core.telegram.org/bots/payments-stars
- Steam Trade Protection: https://help.steampowered.com/en/faqs/view/365F-4BEE-2AE2-7BDD
- Steam trading risks: https://help.steampowered.com/en/faqs/view/70E6-991B-233B-A37B
- Steam Trade Offers: https://help.steampowered.com/en/faqs/view/1115-91C5-050C-1D60
- Steam Market catalog: https://steamcommunity.com/market
- YooKassa payment status and notifications:
  https://yookassa.ru/developers/using-api/webhooks
