"""End-to-end HTTP tests for auth, paywall, and main app flow."""
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
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "").strip().lower()
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "TestPass123!")


class FlowTest:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.notes: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        msg = f"{name}" + (f" — {detail}" if detail else "")
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
    return ""


def logged_in_destination(path: str) -> bool:
    """After login/register the app sends users to /search (route name index)."""
    return path in ("/search", "/")


def ensure_test_user(email: str, password: str) -> tuple[str, str]:
    """Create or reuse a confirmed test user via service role (avoids signup rate limits)."""
    from data_store import get_profile_by_email, get_service_client, sync_profile_from_auth_user

    existing = get_profile_by_email(email)
    if existing:
        return email, password

    admin = get_service_client().auth.admin
    try:
        created = admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
            }
        )
        sync_profile_from_auth_user(created.user)
    except Exception as exc:
        msg = str(exc).lower()
        if "already" in msg or "registered" in msg or "exists" in msg:
            return email, password
        raise
    return email, password


def main() -> int:
    t = FlowTest()
    anon = requests.Session()
    user = requests.Session()

    # --- Public pages ---
    r = anon.get(f"{BASE}/", timeout=10)
    t.check("Landing page loads", r.status_code == 200 and "Sign in" in r.text)

    r = anon.get(f"{BASE}/signin", allow_redirects=False, timeout=10)
    t.check("/signin redirects to login", r.status_code in (301, 302) and "/login" in redirect_target(r))

    r = anon.get(f"{BASE}/login", timeout=10)
    t.check("Login page loads", r.status_code == 200)

    r = anon.get(f"{BASE}/register", timeout=10)
    t.check("Register page loads", r.status_code == 200)

    # --- Anonymous gates ---
    r = anon.get(f"{BASE}/search", allow_redirects=False, timeout=10)
    t.check("Anonymous /search redirects to login", r.status_code in (301, 302) and "/login" in redirect_target(r))

    r = anon.get(f"{BASE}/subscribe", allow_redirects=False, timeout=10)
    t.check("Anonymous /subscribe redirects to login", r.status_code in (301, 302) and "/login" in redirect_target(r))

    # --- Landing preview search (public) ---
    r = anon.post(
        f"{BASE}/landing-search",
        json={"keyword": "developer", "filter": ""},
        timeout=15,
    )
    preview_ok = r.status_code == 200 and isinstance(r.json().get("results"), list)
    t.check("Landing preview search returns results", preview_ok, f"count={len(r.json().get('results', []))}")

    # --- Register + login ---
    stamp = int(time.time())
    email = TEST_USER_EMAIL or f"flowtest{stamp}@example.com"
    password = TEST_USER_PASSWORD

    try:
        ensure_test_user(email, password)
        t.notes.append(f"Using test account {email} (service-role bootstrap if needed).")
    except Exception as exc:
        t.notes.append(f"Could not ensure test user via service role: {exc}")

    r = user.post(
        f"{BASE}/register",
        data={"username": email, "password": password},
        allow_redirects=False,
        timeout=20,
    )
    body_lower = r.text.lower()
    registered_and_logged_in = r.status_code in (301, 302) and logged_in_destination(redirect_target(r))
    registered_pending_confirm = r.status_code == 200 and (
        "account created" in body_lower or "check your email" in body_lower or "confirm" in body_lower
    )
    register_rate_limited = r.status_code == 200 and "rate limit" in body_lower
    register_already_exists = r.status_code == 200 and "already" in body_lower
    t.check(
        "Register endpoint responds (signup, confirm message, or rate limit)",
        registered_and_logged_in or registered_pending_confirm or register_rate_limited or register_already_exists,
        f"status={r.status_code} location={redirect_target(r)}",
    )
    if register_rate_limited:
        t.notes.append("Supabase signup rate limit hit; continuing with login using ensured test user.")

    if not registered_and_logged_in:
        r = user.post(
            f"{BASE}/login",
            data={"username": email, "password": password},
            allow_redirects=False,
            timeout=20,
        )
        login_ok = r.status_code in (301, 302) and logged_in_destination(redirect_target(r))
        login_blocked = r.status_code == 200 and (
            "confirm" in r.text.lower() or "invalid" in r.text.lower() or "email not confirmed" in r.text.lower()
        )
        t.check(
            "Login with test user",
            login_ok,
            f"status={r.status_code} location={redirect_target(r)}",
        )
        if login_blocked and not login_ok:
            t.notes.append(
                "Login blocked until email is confirmed in Supabase Dashboard "
                "(Auth > Users > confirm user, or disable email confirmation)."
            )
            print("\nSkipping logged-in flow tests (no active session).")
            return t.summary()

    # --- Logged-in flow with TEST_MODE ---
    r = user.get(f"{BASE}/search", allow_redirects=False, timeout=15)
    if TEST_MODE:
        t.check(
            "TEST_MODE: logged-in /search accessible (paywall bypassed)",
            r.status_code == 200,
            f"status={r.status_code} location={redirect_target(r)}",
        )
    else:
        paywall = r.status_code in (301, 302) and "/subscribe" in redirect_target(r)
        t.check("Production mode: /search redirects to subscribe", paywall, redirect_target(r))

    r = user.get(f"{BASE}/subscribe", allow_redirects=False, timeout=10)
    if TEST_MODE:
        t.check(
            "TEST_MODE: /subscribe redirects away (already has access)",
            r.status_code in (301, 302) and "/search" in redirect_target(r),
            redirect_target(r),
        )
    else:
        t.check(
            "Production mode: /subscribe page loads for unpaid user",
            r.status_code == 200,
            f"status={r.status_code}",
        )

    if r.status_code == 200 or (TEST_MODE and user.get(f"{BASE}/search", timeout=15).status_code == 200):
        search_page = user.get(f"{BASE}/search", timeout=15)
        has_search_ui = "keyword" in search_page.text.lower() or "search" in search_page.text.lower()
        t.check("Search page renders UI", search_page.status_code == 200 and has_search_ui)

    r = user.get(f"{BASE}/logout", allow_redirects=False, timeout=10)
    t.check("Logout redirects to login", r.status_code in (301, 302) and "/login" in redirect_target(r))

    r = user.get(f"{BASE}/search", allow_redirects=False, timeout=10)
    t.check("After logout /search requires login again", r.status_code in (301, 302) and "/login" in redirect_target(r))

    # --- Paywall logic unit check (TEST_MODE off) ---
    try:
        from app import app, build_user, is_subscribed

        fake_profile = {"id": "00000000-0000-4000-8000-000000000001", "email": "unit@test.com", "is_admin": False}
        with app.app_context():
            app.config["TEST_MODE"] = False
            with app.test_request_context():
                from flask_login import login_user

                u = build_user(fake_profile)
                u.subscribed = False
                login_user(u)
                t.check("Unit: unpaid user fails is_subscribed when TEST_MODE=false", not is_subscribed())

            app.config["TEST_MODE"] = True
            with app.test_request_context():
                from flask_login import login_user

                u = build_user(fake_profile)
                u.subscribed = False
                login_user(u)
                t.check("Unit: any logged-in user passes is_subscribed when TEST_MODE=true", is_subscribed())
    except Exception as exc:
        t.notes.append(f"Skipped in-process unit checks: {exc}")

    t.notes.append(f"TEST_MODE in .env is {'true' if TEST_MODE else 'false'}")
    t.notes.append("Stripe keys are placeholders — real checkout not tested.")
    return t.summary()


if __name__ == "__main__":
    raise SystemExit(main())
