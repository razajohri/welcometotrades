import logging
import os
import pickle
import re
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)

import pandas as pd
from httpx import ConnectError, TimeoutException
import stripe
from flask import Flask, g, make_response, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_session import Session

from contact_handler import contact_bp
from data_store import (
    ensure_profile_for_checkout,
    filter_jobs_dataframe,
    get_profile_by_email,
    get_profile_by_user_id,
    get_subscription_by_stripe_subscription_id,
    get_subscription_by_user_id,
    is_supabase_auth_configured,
    is_supabase_database_configured,
    job_alerts_enabled_for_user,
    job_alerts_table_exists,
    search_jobs,
    send_magic_link,
    set_job_alert_enabled,
    sign_in_user,
    sign_up_user,
    sync_profile_from_auth_user,
    upsert_subscription,
    user_has_active_subscription,
    verify_email_otp_code,
    verify_magic_link,
    warm_jobs_search_cache,
)
from landing_search_api import bp as landing_search_bp, get_default_landing_preview
from pricing import PRO_PLANS, get_plan, plan_label_for_price_id
from seo import (
    SUPPORT_EMAIL,
    build_faq_schema,
    build_organization_schema,
    build_robots_txt,
    build_sitemap_xml,
    build_website_schema,
    clarity_project_id,
    ga4_measurement_id,
    get_page_seo,
    google_site_verification,
    homepage_faq_items,
    schema_json,
)

IS_PRODUCTION = bool(
    os.getenv("RAILWAY_ENVIRONMENT")
    or os.getenv("RENDER")
    or os.getenv("FLASK_ENV", "").lower() == "production"
)

app = Flask(__name__)
app.register_blueprint(landing_search_bp)
app.register_blueprint(contact_bp)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or "local-dev-secret"

SESSION_DAYS = max(int(os.getenv("SESSION_DAYS", "30")), 1)
SESSION_LIFETIME = timedelta(days=SESSION_DAYS)
app.config["PERMANENT_SESSION_LIFETIME"] = SESSION_LIFETIME
app.config["REMEMBER_COOKIE_DURATION"] = SESSION_LIFETIME
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"

if IS_PRODUCTION:
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = True
    app.config["PREFERRED_URL_SCHEME"] = "https"
else:
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = os.path.join(app.root_path, "flask_session")
    Session(app)

app.config["TEST_MODE"] = os.getenv("TEST_MODE", "false").lower() == "true"

if is_supabase_database_configured():
    def _warm_job_cache_on_startup() -> None:
        try:
            count = warm_jobs_search_cache()
            logging.getLogger(__name__).info("Preloaded %s jobs into search cache", count)
        except Exception as exc:
            logging.getLogger(__name__).warning("Job search cache warmup failed: %s", exc)

    threading.Thread(target=_warm_job_cache_on_startup, daemon=True, name="job-cache-warmup").start()

if IS_PRODUCTION:
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

CANONICAL_HOST = os.getenv("CANONICAL_HOST", "www.welcometotrades.com").lower()
PUBLIC_SITE_HOSTS = {
    "welcometotrades.com",
    "www.welcometotrades.com",
}


@app.before_request
def enforce_canonical_host():
    if not IS_PRODUCTION:
        return None

    host = (request.host or "").split(":")[0].lower()
    if host not in PUBLIC_SITE_HOSTS or host == CANONICAL_HOST:
        return None

    path = request.full_path
    if path.endswith("?"):
        path = path[:-1]

    return redirect(f"https://{CANONICAL_HOST}{path}", code=301)


@app.after_request
def add_security_headers(response):
    if not IS_PRODUCTION:
        return response

    response.headers.setdefault(
        "Strict-Transport-Security",
        "max-age=31536000; includeSubDomains",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "upgrade-insecure-requests",
    )
    return response


@app.context_processor
def inject_contact_form_config():
    from contact_handler import RECAPTCHA_SECRET_KEY, RECAPTCHA_SITE_KEY

    return {
        "recaptcha_site_key": RECAPTCHA_SITE_KEY or "",
        "recaptcha_enabled": bool(RECAPTCHA_SECRET_KEY),
    }


@app.context_processor
def inject_homepage_seo():
    if request.endpoint != "root":
        return {}
    faq = homepage_faq_items()
    return {
        "homepage_faq": faq,
        "schema_organization_json": schema_json(build_organization_schema()),
        "schema_website_json": schema_json(build_website_schema()),
        "schema_faq_json": schema_json(build_faq_schema(faq)),
    }


@app.context_processor
def inject_seo():
    endpoint = request.endpoint or ""
    path = request.path or "/"
    page_seo = get_page_seo(endpoint, path)
    overrides = getattr(g, "seo_overrides", None)
    if overrides:
        page_seo = {**page_seo, **overrides}
    return {
        "seo_title": page_seo["title"],
        "seo_description": page_seo["description"],
        "seo_canonical": page_seo["canonical"],
        "seo_robots": page_seo["robots"],
        "seo_og_image": page_seo["og_image"],
        "ga4_measurement_id": ga4_measurement_id(),
        "clarity_project_id": clarity_project_id(),
        "google_site_verification": google_site_verification(),
        "support_email": SUPPORT_EMAIL,
    }


def get_pagination_pages(current_page: int, total_pages: int) -> list[int | str]:
    """Page numbers for pagination UI; 'ellipsis' marks gaps (HeroUI-style windows)."""
    current_page = max(1, int(current_page))
    total_pages = max(1, int(total_pages))
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    pages = {1, total_pages, current_page, current_page - 1, current_page + 1}
    if current_page <= 3:
        pages.update({2, 3, 4})
    if current_page >= total_pages - 2:
        pages.update({total_pages - 3, total_pages - 2, total_pages - 1})

    ordered = sorted(p for p in pages if 1 <= p <= total_pages)
    result: list[int | str] = []
    previous = 0
    for page_num in ordered:
        if previous and page_num - previous > 1:
            result.append("ellipsis")
        result.append(page_num)
        previous = page_num
    return result


@app.template_filter("intcomma")
def intcomma_filter(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


@app.context_processor
def inject_pagination_helper():
    return {"get_pagination_pages": get_pagination_pages}


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


stripe.api_key = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


def _stripe_checkout_mode(price_id: str) -> str:
    """Use payment mode for one-time prices, subscription for recurring."""
    if not price_id or not stripe.api_key:
        return "subscription"
    try:
        price = stripe.Price.retrieve(price_id)
        return "subscription" if price.get("recurring") else "payment"
    except Exception:
        return "subscription"


def _start_stripe_checkout(selected_plan: dict[str, Any], *, user_id: str, email: str):
    price_id = selected_plan["price_id"]
    mode = _stripe_checkout_mode(price_id)
    session_kwargs: dict[str, Any] = {
        "payment_method_types": ["card"],
        "mode": mode,
        "line_items": [{"price": price_id, "quantity": 1}],
        "customer_email": email,
        "client_reference_id": user_id,
        "metadata": {
            "user_id": user_id,
            "email": email,
            "plan_key": selected_plan["key"],
            "price_id": price_id,
        },
        "success_url": url_for("subscription_success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": url_for("subscribe", _external=True),
    }
    if mode == "subscription":
        session_kwargs["subscription_data"] = {
            "metadata": {"user_id": user_id, "plan_key": selected_plan["key"]},
        }
    checkout_session = stripe.checkout.Session.create(**session_kwargs)
    upsert_subscription(
        user_id=user_id,
        email=email,
        status="checkout_started",
        stripe_customer_id=checkout_session.get("customer"),
        stripe_checkout_session_id=checkout_session["id"],
        stripe_price_id=price_id,
    )
    return redirect(checkout_session.url)


def _sync_subscription_from_stripe(
    *,
    user_id: str,
    email: str | None,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None = None,
    stripe_price_id: str | None = None,
    stripe_checkout_session_id: str | None = None,
    status: str = "active",
) -> None:
    current_period_end = None
    resolved_status = status
    resolved_price_id = stripe_price_id

    if stripe_subscription_id and stripe.api_key:
        try:
            sub = stripe.Subscription.retrieve(stripe_subscription_id)
            resolved_status = sub.get("status") or status
            current_period_end = sub.get("current_period_end")
            if current_period_end:
                current_period_end = datetime.utcfromtimestamp(current_period_end).isoformat() + "Z"
            items = (sub.get("items") or {}).get("data") or []
            if items:
                resolved_price_id = items[0].get("price", {}).get("id") or resolved_price_id
            if sub.get("cancel_at_period_end") and resolved_status == "active":
                resolved_status = "active"
        except Exception as exc:
            logging.getLogger(__name__).warning("Could not refresh Stripe subscription %s: %s", stripe_subscription_id, exc)

    upsert_subscription(
        user_id=user_id,
        email=email,
        status=resolved_status,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=resolved_price_id,
        stripe_checkout_session_id=stripe_checkout_session_id,
        current_period_end=current_period_end,
    )


class User(UserMixin):
    def __init__(self, user_id: str, email: str, is_admin: bool = False, subscribed: bool = False):
        self.id = user_id
        self.email = email
        self.username = email
        self.is_admin = is_admin
        self.subscribed = subscribed

    def get_id(self) -> str:
        return self.id

    @property
    def is_subscribed(self) -> bool:
        return self.subscribed or self.is_admin or app.config.get("TEST_MODE")


def build_user(profile: dict) -> User:
    return User(
        user_id=profile["id"],
        email=profile["email"],
        is_admin=bool(profile.get("is_admin", False)),
        subscribed=user_has_active_subscription(profile["id"]),
    )


def _is_valid_user_id(user_id: str | None) -> bool:
    if not user_id:
        return False
    try:
        uuid.UUID(str(user_id))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _clear_stale_login_session() -> None:
    for key in ("_user_id", "_fresh", "_id"):
        session.pop(key, None)
    session.pop("auth_user_id", None)
    session.pop("auth_email", None)


def _is_transient_supabase_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectError, TimeoutException)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (10060, 10061, 11001):
        return True
    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, OSError) and getattr(cause, "errno", None) in (10060, 10061, 11001)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    if not _is_valid_user_id(user_id):
        _clear_stale_login_session()
        return None
    try:
        profile = get_profile_by_user_id(user_id)
    except Exception as exc:
        if _is_transient_supabase_error(exc):
            logging.getLogger(__name__).warning("Supabase unreachable while loading user: %s", exc)
            session_user_id = session.get("auth_user_id")
            session_email = session.get("auth_email")
            if session_user_id == user_id and session_email:
                return User(
                    user_id=user_id,
                    email=session_email,
                    is_admin=False,
                    subscribed=False,
                )
            return None
        raise
    if not profile:
        _clear_stale_login_session()
        return None
    return build_user(profile)


def persist_user_login(user: User) -> None:
    session.permanent = True
    session["auth_user_id"] = user.id
    session["auth_email"] = user.email
    login_user(user, remember=True)


def is_subscribed() -> bool:
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin or app.config.get("TEST_MODE"):
        return True
    if is_supabase_database_configured():
        return user_has_active_subscription(current_user.id)
    return bool(getattr(current_user, "subscribed", False))


def is_valid_email(email: str) -> bool:
    return re.match(r"[^@]+@[^@]+\.[^@]+", email or "") is not None


def format_display_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return str(value)


def subscription_status_label(status: str | None, has_access: bool, price_id: str | None = None) -> str:
    if app.config.get("TEST_MODE"):
        return "Active (test mode)"
    if has_access:
        if status == "lifetime":
            return "Lifetime access"
        if status == "trialing":
            return f"Active trial — {plan_label_for_price_id(price_id)}"
        if status == "active":
            plan_name = plan_label_for_price_id(price_id)
            return f"Active — {plan_name}" if plan_name != "Pro access" else "Active"
        return "Active"
    if not status:
        return "Not subscribed"
    labels = {
        "checkout_started": "Checkout in progress",
        "past_due": "Payment issue",
        "canceled": "Canceled",
        "inactive": "Not subscribed",
    }
    return labels.get(status.lower(), status.replace("_", " ").title())


def format_auth_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "error sending magic link email" in lowered or "error sending confirmation email" in lowered:
        return (
            "We couldn't send the sign-in email. This is usually a Supabase SMTP / Resend setup issue. "
            "Check that your Supabase SMTP sender is verified, Resend domain is verified, "
            "and SMTP is saved in Supabase."
        )
    if "email not confirmed" in lowered:
        return "Please confirm your email address before logging in."
    if "invalid login credentials" in lowered:
        return "We could not sign you in. Check your email or create an account first."
    if "user already registered" in lowered:
        return "An account with that email already exists. Try signing in instead."
    if "signups not allowed" in lowered or "user not found" in lowered:
        return "No account found for that email. Create an account first."
    if "rate limit" in lowered:
        return "Too many requests. Please wait a few minutes and try again."
    if "invalid" in lowered and "expired" in lowered:
        return (
            "Email link is invalid or has expired. Request a new sign-in email, then use the "
            "6-digit code from that email (recommended for Outlook/Hotmail), or copy the link "
            "into Chrome or Safari instead of opening it inside your mail app."
        )
    return message or "Authentication failed."


def auth_confirm_redirect_url() -> str:
    explicit = os.getenv("SUPABASE_AUTH_REDIRECT_URL", "").strip()
    if explicit:
        return explicit
    return url_for("auth_confirm", _external=True)


def complete_passwordless_login(auth_response: Any) -> User:
    auth_user = getattr(auth_response, "user", None)
    if not auth_user:
        raise RuntimeError("Supabase did not return a user record.")
    profile = sync_profile_from_auth_user(auth_user)
    user = build_user(profile)
    persist_user_login(user)
    return user


def post_auth_redirect():
    if is_subscribed():
        return redirect(url_for("index"))
    pending_plan = session.pop("pending_plan", None)
    if pending_plan:
        return redirect(url_for("subscribe", plan=pending_plan))
    return redirect(url_for("subscribe"))


def checkout_email() -> str | None:
    if current_user.is_authenticated:
        return current_user.email
    return session.get("checkout_email")


def can_view_subscribe() -> bool:
    return current_user.is_authenticated or bool(session.get("checkout_email"))


def absolute_site_url(endpoint: str, **values: Any) -> str:
    return f"https://{CANONICAL_HOST}{url_for(endpoint, **values)}"


def access_cta_url() -> str:
    # Free launch: send everyone to /search. Keep /access page for later monetization.
    if app.config.get("TEST_MODE") or current_user.is_authenticated:
        return absolute_site_url("index")
    return absolute_site_url("access")


def sign_in_cta_url() -> str:
    return absolute_site_url("login")


def redirect_authenticated_subscriber():
    """Send paying users to job search; everyone else can use login/register."""
    if current_user.is_authenticated and is_subscribed():
        return redirect(url_for("index"))
    return None


def redirect_authenticated_to_portal():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return None


@app.context_processor
def inject_access_cta():
    return {
        "access_cta_url": access_cta_url(),
        "sign_in_cta_url": sign_in_cta_url(),
    }


def search_jobs_from_cache(
    keyword: str,
    filter_value: str,
    page: int,
    results_per_page: int,
    city: str = "",
) -> tuple[pd.DataFrame, int]:
    cache_path = os.path.join(app.root_path, "jobs_cache.pkl")
    if not os.path.exists(cache_path):
        return pd.DataFrame(), 0

    with open(cache_path, "rb") as file_handle:
        all_jobs_df = pickle.load(file_handle)

    results_df = filter_jobs_dataframe(all_jobs_df, keyword, filter_value, city=city)

    total_jobs = len(results_df)
    page = max(int(page), 1)
    results_per_page = max(int(results_per_page), 1)
    start_idx = (page - 1) * results_per_page
    if start_idx >= total_jobs:
        start_idx = 0
    end_idx = start_idx + results_per_page
    return results_df.iloc[start_idx:end_idx], total_jobs


@app.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if not can_view_subscribe():
        return redirect(url_for("access"))

    if current_user.is_authenticated and is_subscribed():
        return redirect(url_for("index"))

    error = None
    message = request.args.get("message")
    selected_plan = get_plan(request.form.get("plan") if request.method == "POST" else request.args.get("plan"))
    email = checkout_email()

    if request.method == "POST":
        if not selected_plan:
            error = "Please choose a plan."
        elif not email or not is_valid_email(email):
            return redirect(url_for("access"))
        elif not stripe.api_key:
            error = "Stripe is not configured yet."
        elif not is_supabase_database_configured():
            error = "Supabase database is not configured yet."
        else:
            try:
                if current_user.is_authenticated:
                    user_id = current_user.id
                    checkout_email_addr = current_user.email
                else:
                    profile = ensure_profile_for_checkout(email)
                    user_id = profile["id"]
                    checkout_email_addr = profile["email"]
                return _start_stripe_checkout(
                    selected_plan,
                    user_id=user_id,
                    email=checkout_email_addr,
                )
            except Exception as exc:
                logging.getLogger(__name__).exception("Failed to start Stripe checkout")
                error = str(exc) or "Could not start checkout. Please try again."

    return render_template(
        "subscribe.html",
        error=error,
        message=message,
        plans=PRO_PLANS,
        checkout_email=email,
        is_checkout_guest=not current_user.is_authenticated,
    )


@app.route("/subscription_success")
def subscription_success():
    session_id = request.args.get("session_id")
    payment_confirmed = False
    checkout = None
    checkout_email_addr = None
    sign_in_link_sent = False
    if session_id and stripe.api_key:
        try:
            checkout = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
            payment_confirmed = (
                checkout.get("payment_status") == "paid"
                or checkout.get("status") == "complete"
            )
        except Exception:
            payment_confirmed = False

    if payment_confirmed and is_supabase_database_configured() and checkout:
        metadata = checkout.get("metadata") or {}
        price_id = (metadata or {}).get("price_id")
        checkout_email_addr = (
            checkout.get("customer_email")
            or metadata.get("email")
            or session.get("checkout_email")
        )
        user_id = checkout.get("client_reference_id") or metadata.get("user_id")
        if not user_id and checkout_email_addr:
            profile = get_profile_by_email(checkout_email_addr)
            user_id = profile["id"] if profile else None

        subscription_obj = checkout.get("subscription")
        stripe_subscription_id = None
        if isinstance(subscription_obj, dict):
            stripe_subscription_id = subscription_obj.get("id")
            price_id = price_id or (
                ((subscription_obj.get("items") or {}).get("data") or [{}])[0]
                .get("price", {})
                .get("id")
            )
        elif isinstance(subscription_obj, str):
            stripe_subscription_id = subscription_obj

        if user_id:
            _sync_subscription_from_stripe(
                user_id=user_id,
                email=checkout_email_addr,
                stripe_subscription_id=stripe_subscription_id,
                stripe_customer_id=checkout.get("customer"),
                stripe_price_id=price_id,
                stripe_checkout_session_id=session_id,
                status="active",
            )

        if current_user.is_authenticated:
            profile = get_profile_by_user_id(current_user.id)
            if profile:
                persist_user_login(build_user(profile))
        elif checkout_email_addr:
            try:
                send_magic_link(
                    checkout_email_addr,
                    auth_confirm_redirect_url(),
                    should_create_user=False,
                )
                sign_in_link_sent = True
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Could not send post-checkout sign-in link to %s: %s",
                    checkout_email_addr,
                    exc,
                )

    g.seo_overrides = {
        "title": (
            "Payment Successful — Welcome to Trades"
            if payment_confirmed
            else "Payment Pending — Welcome to Trades"
        ),
    }
    return render_template(
        "subscription_success.html",
        payment_confirmed=payment_confirmed,
        sign_in_link_sent=sign_in_link_sent,
        checkout_email=checkout_email_addr,
    )


@app.route("/search", methods=["GET", "POST"])
def index():
    # Launch mode: full search is free (no login / Stripe gate).
    keyword = ""
    filter_val = ""
    city_val = ""
    page = 1
    results_per_page = 20
    total_jobs = 0
    page_jobs = pd.DataFrame()
    error = None

    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()
        filter_val = (request.form.get("filter") or "").strip()
        city_val = (request.form.get("city") or "").strip()
        page = max(int(request.form.get("page", 1)), 1)
        results_per_page = max(int(request.form.get("results_per_page", 20)), 1)
    else:
        keyword = (request.args.get("keyword") or "").strip()
        filter_val = (request.args.get("filter") or "").strip()
        city_val = (request.args.get("city") or "").strip()
        page = max(int(request.args.get("page", 1) or 1), 1)
        results_per_page = max(int(request.args.get("results_per_page", 20) or 20), 1)

    try:
        if is_supabase_database_configured():
            rows, total_jobs = search_jobs(
                keyword=keyword,
                filter_value=filter_val,
                page=page,
                results_per_page=results_per_page,
                city=city_val,
            )
            page_jobs = pd.DataFrame(rows)
        else:
            page_jobs, total_jobs = search_jobs_from_cache(
                keyword, filter_val, page, results_per_page, city=city_val
            )
            if page_jobs.empty and total_jobs == 0 and not os.path.exists(os.path.join(app.root_path, "jobs_cache.pkl")):
                error = "No database or local job cache is configured yet."
    except Exception as exc:
        error = f"Search is unavailable right now: {exc}"

    total_pages = max((total_jobs + results_per_page - 1) // results_per_page, 1)

    available_cities: list[str] = []
    try:
        from data_store import list_available_cities
        available_cities = list_available_cities()
    except Exception:
        available_cities = []

    return render_template(
        "index.html",
        error=error,
        keyword=keyword,
        filter=filter_val,
        city=city_val,
        available_cities=available_cities,
        page=page,
        total_pages=total_pages,
        results_per_page=results_per_page,
        page_jobs=page_jobs,
        total_results=total_jobs,
    )


@app.route("/landing-canada")
def landing_canada():
    return redirect(url_for("root"), code=301)


@app.route("/robots.txt")
def robots_txt():
    response = make_response(build_robots_txt())
    response.mimetype = "text/plain"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/favicon.ico")
def favicon_ico():
    response = send_from_directory(
        os.path.join(app.root_path, "static"),
        "wtt-favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )
    # Short cache so Chrome drops the old Remote Jobs Canada localhost icon
    response.headers["Cache-Control"] = "public, max-age=300, must-revalidate"
    return response


@app.route("/sitemap.xml")
def sitemap_xml():
    try:
        body = build_sitemap_xml()
    except Exception as exc:
        logging.getLogger(__name__).exception("sitemap.xml generation failed: %s", exc)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"  <url><loc>{get_page_seo('root', '/')['canonical']}</loc></url>\n"
            "</urlset>\n"
        )
    response = make_response(body)
    response.mimetype = "application/xml"
    response.charset = "utf-8"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/google42140a1051f05180.html")
def google_search_console_verification():
    return send_from_directory(app.root_path, "google42140a1051f05180.html", mimetype="text/html")


@app.route("/")
def root():
    return render_template(
        "landing_canada.html",
        landing_preview_jobs=get_default_landing_preview(),
    )


@app.route("/access", methods=["GET", "POST"])
def access():
    auth_redirect = redirect_authenticated_to_portal()
    if auth_redirect:
        return auth_redirect

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not is_valid_email(email):
            error = "Please enter a valid email address."
        else:
            session["checkout_email"] = email
            return redirect(url_for("subscribe"))

    return render_template("access.html", error=error, email=email)


@app.route("/signin")
def signin_redirect():
    auth_redirect = redirect_authenticated_subscriber()
    if auth_redirect:
        return auth_redirect
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    auth_redirect = redirect_authenticated_subscriber()
    if auth_redirect:
        return auth_redirect

    error = request.args.get("error")
    message = request.args.get("message")
    prefilled_email = request.args.get("email", "").strip().lower()
    show_otp_form = bool(error and "expired" in error.lower() and prefilled_email)

    if request.method == "POST":
        email = request.form["username"].strip().lower()
        otp_code = request.form.get("otp_code", "").strip()

        if not is_valid_email(email):
            error = "Please enter a valid email address."
        elif not is_supabase_auth_configured():
            error = "Supabase auth is not configured yet."
        elif otp_code:
            if not re.fullmatch(r"\d{6,8}", otp_code):
                error = "Enter the 6-digit code from your email."
                prefilled_email = email
                show_otp_form = True
            else:
                try:
                    auth_response = verify_email_otp_code(email, otp_code)
                    complete_passwordless_login(auth_response)
                    return post_auth_redirect()
                except Exception as exc:
                    error = format_auth_error(exc)
                    prefilled_email = email
                    show_otp_form = True
        else:
            try:
                send_magic_link(
                    email,
                    auth_confirm_redirect_url(),
                    should_create_user=False,
                )
                message = (
                    "Check your email for a sign-in link and a 6-digit code. "
                    "If you use Outlook or Hotmail, enter the code below — the link often won't work in mail apps."
                )
                prefilled_email = email
                show_otp_form = True
            except Exception as exc:
                error = format_auth_error(exc)

    return render_template(
        "login.html",
        error=error,
        message=message,
        email=prefilled_email,
        show_otp_form=show_otp_form or bool(message and not error),
        magic_link_sent=bool(message and not error),
        already_signed_in=current_user.is_authenticated,
        current_email=current_user.email if current_user.is_authenticated else "",
    )


@app.route("/auth/confirm")
def auth_confirm():
    token_hash = request.args.get("token_hash")
    auth_type = request.args.get("type", "email")

    if not token_hash:
        return redirect(url_for("login", error="Invalid or expired sign-in link. Request a new one and use the 6-digit code if you are on Outlook or Hotmail."))

    if not is_supabase_auth_configured():
        return redirect(url_for("login", error="Supabase auth is not configured yet."))

    try:
        auth_response = verify_magic_link(token_hash, auth_type)
        complete_passwordless_login(auth_response)
        return post_auth_redirect()
    except Exception as exc:
        logging.getLogger(__name__).exception("Magic link verification failed")
        return redirect(url_for("login", error=format_auth_error(exc)))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("auth_user_id", None)
    session.pop("auth_email", None)
    session.pop("checkout_email", None)
    session.pop("pending_plan", None)
    return redirect(url_for("login"))


@app.route("/account")
@login_required
def account():
    profile = get_profile_by_user_id(current_user.id) or {}
    subscription = get_subscription_by_user_id(current_user.id)
    has_access = is_subscribed()
    sub_status = (subscription or {}).get("status")
    price_id = (subscription or {}).get("stripe_price_id")
    status_label = subscription_status_label(sub_status, has_access, price_id)
    status_tone = "active" if has_access else "inactive"
    if sub_status in {"past_due", "checkout_started"}:
        status_tone = "warning"

    cancel_at_period_end = False
    if subscription and subscription.get("stripe_subscription_id") and stripe.api_key:
        try:
            stripe_sub = stripe.Subscription.retrieve(subscription["stripe_subscription_id"])
            cancel_at_period_end = bool(stripe_sub.get("cancel_at_period_end"))
        except Exception:
            cancel_at_period_end = False

    can_cancel = bool(
        has_access
        and subscription
        and subscription.get("stripe_subscription_id")
        and sub_status in {"active", "trialing"}
        and sub_status != "lifetime"
        and not cancel_at_period_end
    )

    return render_template(
        "account.html",
        profile=profile,
        subscription=subscription,
        status_label=status_label,
        status_tone=status_tone,
        member_since=format_display_date(profile.get("created_at")),
        renews_on=format_display_date((subscription or {}).get("current_period_end")),
        can_cancel=can_cancel,
        cancel_scheduled=cancel_at_period_end,
        cancel_message=request.args.get("cancel_message"),
        cancel_error=request.args.get("cancel_error"),
        alert_message=request.args.get("alert_message"),
        job_alerts_enabled=job_alerts_enabled_for_user(current_user.id),
        job_alerts_available=job_alerts_table_exists(),
        has_access=has_access,
    )


@app.route("/account/job-alerts", methods=["POST"])
@login_required
def update_job_alerts():
    if not job_alerts_table_exists():
        return redirect(url_for("account", cancel_error="Job alerts are not available yet."))

    enabled = request.form.get("enabled") == "1"
    try:
        set_job_alert_enabled(current_user.id, enabled)
    except Exception:
        logging.getLogger(__name__).exception("Failed to update job alert preferences")
        return redirect(url_for("account", cancel_error="Could not update job alert preferences."))

    message = "Daily job alerts turned on." if enabled else "Daily job alerts turned off."
    return redirect(url_for("account", alert_message=message))


@app.route("/account/cancel-subscription", methods=["POST"])
@login_required
def cancel_subscription():
    subscription = get_subscription_by_user_id(current_user.id)
    if not subscription or not subscription.get("stripe_subscription_id"):
        return redirect(url_for("account", cancel_error="No active subscription to cancel."))

    if not stripe.api_key:
        return redirect(url_for("account", cancel_error="Billing is not configured yet."))

    try:
        stripe.Subscription.modify(
            subscription["stripe_subscription_id"],
            cancel_at_period_end=True,
        )
        _sync_subscription_from_stripe(
            user_id=current_user.id,
            email=subscription.get("email") or current_user.email,
            stripe_subscription_id=subscription["stripe_subscription_id"],
            stripe_customer_id=subscription.get("stripe_customer_id"),
            stripe_price_id=subscription.get("stripe_price_id"),
            status="active",
        )
        return redirect(
            url_for(
                "account",
                cancel_message="Your subscription will cancel at the end of the current billing period.",
            )
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Failed to cancel subscription")
        return redirect(url_for("account", cancel_error=str(exc) or "Could not cancel subscription."))


@app.route("/register", methods=["GET", "POST"])
def register():
    auth_redirect = redirect_authenticated_subscriber()
    if auth_redirect:
        return auth_redirect

    error = None
    message = None
    prefilled_email = request.args.get("email", "").strip().lower()

    show_otp_form = False

    if request.method == "POST":
        email = request.form["username"].strip().lower()
        otp_code = request.form.get("otp_code", "").strip()

        if not is_valid_email(email):
            error = "Please enter a valid email address."
        elif not is_supabase_auth_configured():
            error = "Supabase auth is not configured yet."
        elif otp_code:
            if not re.fullmatch(r"\d{6,8}", otp_code):
                error = "Enter the 6-digit code from your email."
                prefilled_email = email
                show_otp_form = True
            else:
                try:
                    auth_response = verify_email_otp_code(email, otp_code)
                    complete_passwordless_login(auth_response)
                    return post_auth_redirect()
                except Exception as exc:
                    error = format_auth_error(exc)
                    prefilled_email = email
                    show_otp_form = True
        else:
            try:
                send_magic_link(
                    email,
                    auth_confirm_redirect_url(),
                    should_create_user=True,
                )
                message = (
                    "Check your email for a sign-up link and a 6-digit code. "
                    "Outlook/Hotmail users should enter the code below."
                )
                prefilled_email = email
                show_otp_form = True
            except Exception as exc:
                error = format_auth_error(exc)

    return render_template(
        "register.html",
        error=error,
        message=message,
        email=prefilled_email,
        show_otp_form=show_otp_form or bool(message and not error),
        magic_link_sent=bool(message and not error),
    )


@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        return f"Webhook error: {exc}", 400

    event_type = event.get("type")
    object_data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = object_data.get("client_reference_id") or (object_data.get("metadata") or {}).get("user_id")
        email = object_data.get("customer_email") or (object_data.get("metadata") or {}).get("email")
        if not user_id and email:
            profile = get_profile_by_email(email)
            user_id = profile["id"] if profile else None
        if user_id:
            metadata = object_data.get("metadata") or {}
            _sync_subscription_from_stripe(
                user_id=user_id,
                email=email,
                stripe_customer_id=object_data.get("customer"),
                stripe_subscription_id=object_data.get("subscription"),
                stripe_price_id=metadata.get("price_id"),
                stripe_checkout_session_id=object_data.get("id"),
                status="active",
            )

    elif event_type in {"customer.subscription.updated", "customer.subscription.created"}:
        subscription_id = object_data.get("id")
        existing = get_subscription_by_stripe_subscription_id(subscription_id) if subscription_id else None
        if existing:
            _sync_subscription_from_stripe(
                user_id=existing["user_id"],
                email=existing.get("email"),
                stripe_customer_id=object_data.get("customer"),
                stripe_subscription_id=subscription_id,
                stripe_price_id=existing.get("stripe_price_id"),
                status=object_data.get("status") or "active",
            )

    elif event_type == "customer.subscription.deleted":
        subscription_id = object_data.get("id")
        if subscription_id:
            existing = get_subscription_by_stripe_subscription_id(subscription_id)
            if existing:
                upsert_subscription(
                    user_id=existing["user_id"],
                    email=existing.get("email"),
                    status="canceled",
                    stripe_customer_id=object_data.get("customer"),
                    stripe_subscription_id=subscription_id,
                    stripe_price_id=existing.get("stripe_price_id"),
                )

    return "", 200


@app.route("/lifetime-access", methods=["GET"])
def lifetime_access():
    if current_user.is_authenticated:
        if is_subscribed():
            return redirect(url_for("index"))
        return redirect(url_for("subscribe"))
    return redirect(url_for("register"))


@app.route("/post-a-job")
def post_a_job():
    return render_template("post_a_job.html")


@app.route("/guides/remote-jobs-canada")
def guides_remote_jobs_canada():
    return render_template("guides/remote_jobs_canada.html")


@app.route("/support")
def support():
    return render_template("support.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


def print_routes() -> None:
    print("\nRegistered Flask routes:")
    for rule in app.url_map.iter_rules():
        methods = ",".join(sorted(rule.methods))
        print(f"{rule.endpoint:30s} {methods:20s} {rule}")
    print()


if not IS_PRODUCTION:
    print_routes()

if __name__ == "__main__":
    app.run(debug=True)
