"""Read-only subscription storefront preview. No payment or licensing endpoint.

IMPORTANT: This module intentionally cannot activate, purchase, or enforce a
subscription. A trustworthy paid license requires a hosted verification backend
and verified payment integration, neither is included in this preview.
"""

PLANS = (
    {"id": "demo", "hours": None},
    {"id": "day", "hours": 24, "amount_kopeks": 5900},
    {"id": "three_days", "hours": 72, "amount_kopeks": 12900},
    {"id": "week", "hours": 168, "amount_kopeks": 24900},
)


def snapshot():
    return {
        "enabled": False,
        "payments_enabled": False,
        "activation_enabled": False,
        "status": "preview",
        "remaining_seconds": None,
        "expiring_soon": False,
        "plans": [dict(plan) for plan in PLANS],
        "payment_methods": ["bank_transfer", "steam_items"],
    }
