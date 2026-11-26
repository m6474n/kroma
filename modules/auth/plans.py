"""Subscription plan definitions and limitation helpers."""

PLANS: dict[str, dict] = {
    "starter": {
        "name": "Starter",
        "price": "$0/mo",
        "max_profiles": 5,
        "max_automations": 2,
        "max_concurrent_profiles": 2,
        "description": "Basic plan for testing and small setups.",
    },
    "pro": {
        "name": "Pro",
        "price": "$29/mo",
        "max_profiles": 50,
        "max_automations": 20,
        "max_concurrent_profiles": 10,
        "description": "Standard plan for multi-account workflows.",
    },
    "enterprise": {
        "name": "Enterprise",
        "price": "$99/mo",
        "max_profiles": 500,
        "max_automations": 100,
        "max_concurrent_profiles": 50,
        "description": "High-volume plan with maximum concurrency.",
    },
}


def get_plan(tier: str | None) -> dict:
    """Return plan config for a given tier name (defaults to starter)."""
    key = (tier or "starter").strip().lower()
    return PLANS.get(key, PLANS["starter"])
