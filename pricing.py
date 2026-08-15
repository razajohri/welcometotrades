"""Stripe plan configuration for Welcome to Trades Pro."""

from __future__ import annotations

import os
from typing import Any

STRIPE_PRODUCT_ID = os.getenv("STRIPE_PRODUCT_ID", "prod_UitNW7MRLfAhlm").strip()

# Price IDs from Stripe (Welcome to Trades Access product) — live account.
STRIPE_PRICE_WEEKLY = os.getenv("STRIPE_PRICE_WEEKLY", "price_1TkpR8EznoT0U9sakEjSKmNY").strip()
STRIPE_PRICE_MONTHLY = os.getenv("STRIPE_PRICE_MONTHLY", "price_1TkpR9EznoT0U9saZm8QaFZU").strip()
STRIPE_PRICE_YEARLY = os.getenv("STRIPE_PRICE_YEARLY", "price_1TkpR9EznoT0U9saDP0fxBrs").strip()

# Backwards compatibility for older single-price deployments.
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", STRIPE_PRICE_YEARLY).strip()

PRO_PLANS: list[dict[str, Any]] = [
    {
        "key": "weekly",
        "price_id": STRIPE_PRICE_WEEKLY,
        "title": "Weekly",
        "compare_at": "$13.99",
        "price": "$5",
        "interval_label": "week",
        "badge": None,
        "button_label": "Get Access",
        "features": ["Access to all jobs"],
        "recurring": True,
    },
    {
        "key": "monthly",
        "price_id": STRIPE_PRICE_MONTHLY,
        "title": "Monthly",
        "compare_at": "$35.99",
        "price": "$19",
        "interval_label": "month",
        "badge": None,
        "button_label": "Get Access",
        "features": ["Access to all jobs", "Save 35% vs weekly"],
        "recurring": True,
    },
    {
        "key": "yearly",
        "price_id": STRIPE_PRICE_YEARLY,
        "title": "Yearly",
        "compare_at": "$99.99",
        "price": "$49",
        "interval_label": "year",
        "badge": None,
        "button_label": "Get Access",
        "features": ["Access to all jobs", "Best value"],
        "recurring": True,
    },
]

PLAN_BY_KEY: dict[str, dict[str, Any]] = {plan["key"]: plan for plan in PRO_PLANS}
PLAN_BY_PRICE_ID: dict[str, dict[str, Any]] = {plan["price_id"]: plan for plan in PRO_PLANS if plan["price_id"]}


def get_plan(plan_key: str | None) -> dict[str, Any] | None:
    if not plan_key:
        return None
    return PLAN_BY_KEY.get(plan_key.strip().lower())


def plan_label_for_price_id(price_id: str | None) -> str:
    if not price_id:
        return "Pro access"
    plan = PLAN_BY_PRICE_ID.get(price_id)
    if plan:
        return plan["title"]
    return "Pro access"
