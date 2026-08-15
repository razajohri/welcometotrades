"""Verify Stripe price IDs against STRIPE_API_KEY (run via: railway run py -3 scripts/verify_stripe_prices.py)."""
from __future__ import annotations

import os
import sys

import stripe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

stripe.api_key = os.getenv("STRIPE_API_KEY", "").strip()
if not stripe.api_key:
    print("ERROR: STRIPE_API_KEY not set")
    sys.exit(1)

mode = "live" if stripe.api_key.startswith("sk_live") else "test" if stripe.api_key.startswith("sk_test") else "unknown"
print(f"API key mode: {mode}")
print(f"Product: {os.getenv('STRIPE_PRODUCT_ID', '')}")

price_vars = [
    ("weekly", os.getenv("STRIPE_PRICE_WEEKLY", "")),
    ("monthly", os.getenv("STRIPE_PRICE_MONTHLY", "")),
    ("yearly", os.getenv("STRIPE_PRICE_YEARLY", "")),
]

all_ok = True
for name, price_id in price_vars:
    if not price_id:
        print(f"{name}: MISSING env var")
        all_ok = False
        continue
    try:
        price = stripe.Price.retrieve(price_id)
        recurring = price.get("recurring") or {}
        interval = recurring.get("interval", "one_time")
        print(
            f"{name}: OK {price_id} active={price.get('active')} "
            f"amount={price.get('unit_amount')} {price.get('currency')} interval={interval}"
        )
        if not price.get("active"):
            all_ok = False
    except stripe.error.InvalidRequestError as exc:
        print(f"{name}: FAIL {price_id} -> {exc.user_message or exc}")
        all_ok = False

print("\nListing active recurring prices on this account (first 20):")
try:
    prices = stripe.Price.list(active=True, limit=20, expand=["data.product"])
    for p in prices.auto_paging_iter():
        if not p.get("recurring"):
            continue
        prod = p.get("product")
        prod_name = prod.get("name") if isinstance(prod, dict) else str(prod)
        rec = p.get("recurring") or {}
        print(
            f"  {p.id} | {prod_name} | {p.get('unit_amount')} {p.get('currency')} / {rec.get('interval')}"
        )
except Exception as exc:
    print(f"  Could not list prices: {exc}")

sys.exit(0 if all_ok else 1)
