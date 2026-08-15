"""End-to-end paywall + payment flow tests (TEST_MODE must be false on the server)."""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

BASE = os.getenv("TEST_BASE_URL", "http://127.0.0.1:5000")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "TestPass123!")


class FlowTest:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.notes: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        msg = f"{name}" + (f" - {detail}" if detail else "")
        if ok:
            self.passed.append(msg)
            print(f"PASS: {msg}")
        else:
            self.failed.append(msg)
            print(f"FAIL: {msg}")

    def summary(self) -> int:
        print("\n" + "=" * 60)
        print(f"Passed: {len(self.passed)}  Failed: {len(self.failed)}")
        if self.notes:
            print("\nNotes:")
            for note in self.notes:
                print(f"  - {note}")
        if self.failed:
            print("\nFailures:")
            for item in self.failed:
                print(f"  - {item}")
        return 0 if not self.failed else 1


def redirect_target(response: requests.Response) -> str:
    location = response.headers.get("Location", "")
    if location.startswith("/"):
        return location
    if location:
        return urlparse(location).path or location
    return location


def ensure_test_user(email: str, password: str) -> None:
    from data_store import get_profile_by_email, get_service_client, sync_profile_from_auth_user

    if get_profile_by_email(email):
        return
    admin = get_service_client().auth.admin
    try:
        created = admin.create_user({"email": email, "password": password, "email_confirm": True})
        sync_profile_from_auth_user(created.user)
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise


def clear_subscription(user_id: str) -> None:
    from data_store import get_service_client

    get_service_client().table("subscriptions").delete().eq("user_id", user_id).execute()


def activate_subscription(user_id: str, email: str) -> None:
    from data_store import upsert_subscription

    upsert_subscription(
        user_id=user_id,
        email=email,
        status="active",
        stripe_price_id=STRIPE_PRICE_ID or None,
    )


def login(session: requests.Session, email: str, password: str) -> bool:
    response = session.post(
        f"{BASE}/login",
        data={"username": email, "password": password},
        allow_redirects=False,
        timeout=20,
    )
    return response.status_code in (301, 302)


def main() -> int:
    t = FlowTest()

    if TEST_MODE:
        t.notes.append("TEST_MODE=true in .env bypasses paywall. Set TEST_MODE=false and restart Flask.")
        t.check("TEST_MODE is disabled for payment testing", False, "TEST_MODE=true")
        return t.summary()

    t.check("TEST_MODE is disabled for payment testing", True)

    stamp = int(time.time())
    email = os.getenv("TEST_USER_EMAIL", f"paytest{stamp}@example.com").strip().lower()
    password = TEST_USER_PASSWORD

    try:
        ensure_test_user(email, password)
    except Exception as exc:
        t.check("Ensure confirmed test user exists", False, str(exc))
        return t.summary()

    from data_store import get_profile_by_email

    profile = get_profile_by_email(email)
    if not profile:
        t.check("Load test user profile", False)
        return t.summary()

    user_id = profile["id"]
    clear_subscription(user_id)

    session = requests.Session()
    t.check("Login unpaid test user", login(session, email, password))

    blocked = session.get(f"{BASE}/search", allow_redirects=False, timeout=15)
    t.check(
        "Unpaid user blocked from /search",
        blocked.status_code in (301, 302) and "/subscribe" in redirect_target(blocked),
        redirect_target(blocked),
    )

    subscribe_page = session.get(f"{BASE}/subscribe", timeout=15)
    t.check("Unpaid user can open /subscribe", subscribe_page.status_code == 200)

    stripe_ready = (
        STRIPE_API_KEY.startswith("sk_test_")
        and "placeholder" not in STRIPE_API_KEY
        and STRIPE_PRICE_ID.startswith("price_")
        and "placeholder" not in STRIPE_PRICE_ID
    )

    if stripe_ready:
        checkout = session.post(f"{BASE}/subscribe", allow_redirects=False, timeout=20)
        checkout_url = checkout.headers.get("Location", "")
        t.check(
            "Subscribe POST starts Stripe Checkout",
            checkout.status_code in (301, 302) and "checkout.stripe.com" in checkout_url,
            checkout_url[:80],
        )
        if checkout_url:
            t.notes.append(f"Complete checkout manually: {checkout_url}")
            t.notes.append("Test card: 4242 4242 4242 4242, any future expiry, any CVC.")
    else:
        t.notes.append("Stripe not configured. Run scripts/setup_stripe_test.py after adding sk_test_ key.")
        t.check("Subscribe POST starts Stripe Checkout", False, "Stripe keys missing")

    activate_subscription(user_id, email)
    session = requests.Session()
    t.check("Re-login after simulated payment", login(session, email, password))

    allowed = session.get(f"{BASE}/search", allow_redirects=False, timeout=15)
    t.check(
        "Paid user can access /search",
        allowed.status_code == 200,
        f"status={allowed.status_code} location={redirect_target(allowed)}",
    )

    subscribed_redirect = session.get(f"{BASE}/subscribe", allow_redirects=False, timeout=15)
    t.check(
        "Paid user redirected away from /subscribe",
        subscribed_redirect.status_code in (301, 302) and "/search" in redirect_target(subscribed_redirect),
        redirect_target(subscribed_redirect),
    )

    return t.summary()


if __name__ == "__main__":
    raise SystemExit(main())
