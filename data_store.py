import concurrent.futures
import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=True)

from ats_location import is_trades_job_row, city_matches, collect_cities, extract_city

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - runtime dependency
    Client = Any  # type: ignore[assignment]
    create_client = None


SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "lifetime"}

# Sites included in search results. ATS + Indeed + Google Jobs.
LISTED_JOB_SITES = ("ashby", "greenhouse", "lever", "hiringcafe", "indeed", "google")
TRUSTED_JOB_SITES = LISTED_JOB_SITES  # backwards compat

JOB_SEARCH_COLUMNS = (
    "title, company, compensation, job_url_direct, job_url, site, date_posted, location, is_remote, description"
)
JOB_CACHE_TTL_SECONDS = int(os.getenv("JOB_CACHE_TTL_SECONDS", "900"))

_job_search_cache: dict[str, Any] = {"rows": [], "loaded_at": 0.0}
_job_search_cache_lock = threading.Lock()
_cache_warm_cond = threading.Condition(_job_search_cache_lock)
_cache_warm_in_progress = False

# Category buttons map to title keywords (jobs rarely contain the category label itself).
CATEGORY_FILTER_TERMS: dict[str, list[str]] = {
    "Operators": [
        "haul truck", "equipment operator", "dozer", "grader", "excavator",
        "loader", "mine operator", "mine equipment",
    ],
    "Underground": [
        "underground", "underground miner", "underground operator",
        "jumbo", "driller", "blast", "blaster",
    ],
    "Mill & Plant": [
        "mill operator", "process plant", "plant operator", "crusher",
        "conveyor", "assayer", "assay",
    ],
    "Trades": [
        "mechanic", "heavy duty", "millwright", "electrician", "welder", "welding",
    ],
    "Labor": [
        "laborer", "labourer", "utility worker", "construction miner",
        "construction helper", "helper",
    ],
    "Safety & Geology": [
        "safety technician", "safety tech", "geologist", "mine geologist",
    ],
}

_WRITING_TITLE_PATTERNS: tuple[str, ...] = (
    r"\bsocial media\b",
    r"\bcommunity manager\b",
    r"\bemail marketing\b",
    r"\bcreative (strategist|director|producer|lead|manager|copywriter|writer|operations)\b",
    r"\b(content|copy|brand|marketing|communications?) (manager|specialist|coordinator|lead|director|strategist|associate|assistant|officer|consultant|analyst|creator|producer|editor|writer)\b",
    r"\bseo (specialist|strategist|consultant|manager|writer|content|analyst)\b",
    r"\b(pr|public relations) (specialist|manager|coordinator|officer|lead|consultant|associate)\b",
    r"\b(influencer|copywriter|copywriting|copy writing|content creator|content strategist|technical writer|medical writer|grant writer|proposal writer|science writer|ux writer|ghostwriter|proofreader|proofreading|scriptwriter|screenwriter|songwriter|storyteller)\b",
    r"\bfreelance (writer|editor|copywriter|journalist|content)\b",
    r"\b(video|managing|associate|assistant|senior|junior|copy|executive|digital|managing) editor\b",
    r"\bcommunications (manager|specialist|officer|coordinator|lead|director|associate|consultant|analyst)\b",
    r"\b(content|editorial|brand|marketing) (writer|editor|copywriter|strategist|specialist|coordinator|manager|lead|director|producer|creator)\b",
    r"\b(redacteur|redactrice|journaliste|traducteur|traductrice|correcteur|correctrice|communicateur|communicatrice)\b",
    r"\b(localization|localisation) (manager|specialist|lead|coordinator|engineer|writer|editor)\b",
    r"\b(proposal|grant|bid|rfp|tender) (writer|coordinator|manager|specialist)\b",
    r"\bmarketing (coordinator|specialist|associate|analyst|consultant|assistant|intern|manager|director|lead|head)\b",
    r"\b(digital|growth|brand|product|content|email|social|performance|paid social) marketing (specialist|manager|coordinator|lead|strategist|consultant|analyst|associate)\b",
    r"\bbrand (manager|specialist|coordinator|lead|strategist|marketing manager|content|director|head)\b",
    r"\b(paid social|social ads|media buyer|media planner) (specialist|manager|strategist|coordinator|consultant)\b",
    r"\bcommunications (and|&)? marketing\b",
    r"\b(director|head|vp|vice president) of (marketing|communications|content|brand|creative)\b",
    r"\bchief marketing officer\b",
    r"\bcmo\b",
    r"\b(digital|online|web|organic) (content|copy|strategy|strategist|marketing)\b",
    r"\b(content|copy|editorial|communications?) (lead|head|director|manager|specialist|coordinator|associate|consultant|analyst|intern)\b",
    r"\b(customer|product|brand|technical|marketing) (education|enablement|advocacy) (lead|manager|specialist|writer|content)\b",
    r"\bproduct marketing\b",
    r"\b(academic|research) (writer|editor|coordinator|specialist)\b",
    r"\b(english|french|writing|literature|humanities) (tutor|teacher|instructor|professor)\b",
    r"\b(tutor|teacher|instructor).*\b(english|french|writing|literature)\b",
    r"\bmedia relations\b",
    r"\bcorporate communications\b",
    r"\binternal communications\b",
    r"\bemployer brand\b",
    r"\bpublic affairs\b",
)

_WRITING_TITLE_EXCLUSIONS: tuple[str, ...] = (
    "underwriter",
    "underwriting",
    "souscript",
    "software engineer",
    "software developer",
    "data scientist",
    "data science",
    "machine learning",
    "decision scientist",
    "marketing analytics",
    "quantitative",
    "devops",
    "full stack",
    "backend",
    "frontend",
    "accountant",
    "bookkeeper",
    "payroll",
    "mortgage",
    "insurance underwriter",
    "patent examiner",
    "forest analyst",
    "telecom",
    "construction",
    "nurse",
    "physician",
    "sales account",
    "district sales",
    "account executive",
    "business development",
)

_WRITING_DESCRIPTION_STRONG_SIGNALS: tuple[str, ...] = (
    "copywriter",
    "copywriting",
    "content writer",
    "technical writer",
    "grant writer",
    "medical writer",
    "ghostwriter",
    "content strategist",
)

_WRITING_DESCRIPTION_WEAK_SIGNALS: tuple[str, ...] = (
    "science writer",
    "ux writer",
    "seo writer",
    "proofreading",
    "proofreader",
    "journalism",
    "copy editing",
    "content creation",
    "content development",
    "create content",
    "write content",
    "written content",
    "manage content",
    "content calendar",
    "writing skills",
    "writing experience",
    "strong writing",
    "excellent writing",
    "writing sample",
    "content writing",
    "proposal writing",
    "script writing",
    "creative writing",
    "blog writing",
)

_WRITING_DESCRIPTION_TITLE_HINTS: tuple[str, ...] = (
    "market",
    "content",
    "commun",
    "creativ",
    "editor",
    "writer",
    "copy",
    "brand",
    "media",
    "social",
    "seo",
    "pr ",
    "public relation",
    "journal",
    "blog",
    "story",
    "localiz",
    "translat",
    "document",
    "proposal",
    "grant",
    "script",
    "influencer",
    "community",
    "newsletter",
    "podcast",
    "marcom",
    "redact",
    "journalist",
    "traduct",
    "correct",
)

_WRITING_MARKETING_EXCLUSIONS: tuple[str, ...] = (
    "data scientist",
    "data science",
    "marketing analytics",
    "decision scientist",
    "analytics manager",
    "scientist, marketing",
    "marketing scientist",
    "marketing operations",
    "operations manager",
    "financial analyst",
    "project manager",
    "business development",
    "sales account",
)

def _title_matches_category_term(title: str, term: str) -> bool:
    """Match category keywords without common false positives (e.g. underwriter)."""
    title_l = str(title or "").lower()
    term_l = term.lower().strip()
    if not title_l or not term_l:
        return False

    if term_l in {"writer", "writing"}:
        if "underwriter" in title_l or "underwriting" in title_l or "souscript" in title_l:
            return False
    if term_l == "writer":
        return bool(re.search(r"(?<![a-z])writer", title_l))
    if term_l == "writing":
        return bool(re.search(r"(?<![a-z])writing", title_l))

    if term_l == "communications" and "telecommunication" in title_l:
        return False

    if term_l == "typing":
        return bool(re.search(r"\btyping\b", title_l))

    if term_l == "growth":
        if any(
            marker in title_l
            for marker in ("engineer", "engineering", "developer", "scientist", "machine learning", " ml")
        ):
            return False
        return bool(re.search(r"\bgrowth\b", title_l))

    if " " in term_l:
        return term_l in title_l

    if len(term_l) <= 3:
        return bool(re.search(rf"\b{re.escape(term_l)}\b", title_l))

    return term_l in title_l


_DATA_ENTRY_TITLE_EXCLUSIONS = (
    "developer",
    "engineer",
    "software engineering",
    "data scientist",
    "director",
)


def _writing_title_excluded(title: str) -> bool:
    title_l = str(title or "").lower()
    return any(exclusion in title_l for exclusion in _WRITING_TITLE_EXCLUSIONS)


def _title_matches_writing_marketing(title: str) -> bool:
    if not _title_matches_category(title, "Marketing"):
        return False
    title_l = str(title or "").lower()
    return not any(exclusion in title_l for exclusion in _WRITING_MARKETING_EXCLUSIONS)


def _writing_description_match(title: str, description: Any) -> bool:
    desc = str(description or "").lower()[:3000]
    if not desc or desc == "none":
        return False
    if any(signal in desc for signal in _WRITING_DESCRIPTION_STRONG_SIGNALS):
        return True
    title_l = str(title or "").lower()
    if not any(hint in title_l for hint in _WRITING_DESCRIPTION_TITLE_HINTS):
        return False
    return any(signal in desc for signal in _WRITING_DESCRIPTION_WEAK_SIGNALS)


def _title_matches_writing(title: str, description: Any = None) -> bool:
    if _writing_title_excluded(title):
        return False

    terms = CATEGORY_FILTER_TERMS.get("Writing", [])
    if any(_title_matches_category_term(title, term) for term in terms):
        return True

    title_l = str(title or "").lower()
    if any(re.search(pattern, title_l) for pattern in _WRITING_TITLE_PATTERNS):
        return True

    if _title_matches_writing_marketing(title):
        return True

    return _writing_description_match(title, description)


def _title_matches_category(title: str, category: str, description: Any = None) -> bool:
    if category == "Writing":
        return _title_matches_writing(title, description)

    terms = CATEGORY_FILTER_TERMS.get(category, [])
    if not terms:
        return category.lower() in str(title or "").lower()
    if not any(_title_matches_category_term(title, term) for term in terms):
        return False

    if category == "Data Entry":
        title_l = str(title or "").lower()
        if any(ex in title_l for ex in _DATA_ENTRY_TITLE_EXCLUSIONS):
            return False
        if "manager" in title_l and any(
            marker in title_l for marker in ("contact center", "call center", "call centre")
        ):
            return False

    return True


def _apply_title_filters_to_query(query: Any, keyword: str, filter_value: str) -> Any:
    filter_label = (filter_value or "").strip()
    keyword_term = (keyword or "").strip()

    if filter_label in CATEGORY_FILTER_TERMS:
        terms = CATEGORY_FILTER_TERMS[filter_label]
        if terms:
            or_filter = ",".join(f"title.ilike.%{term}%" for term in terms)
            query = query.or_(or_filter)
    elif filter_label:
        query = query.ilike("title", f"%{filter_label}%")

    if keyword_term:
        query = query.ilike("title", f"%{keyword_term}%")
    return query


def filter_jobs_dataframe(df: pd.DataFrame, keyword: str, filter_value: str, city: str = "") -> pd.DataFrame:
    if df.empty:
        return df

    title_s = df["title"].astype(str).str.lower()
    mask = pd.Series(True, index=df.index)
    filter_label = (filter_value or "").strip()
    keyword_term = (keyword or "").strip()
    city_term = (city or "").strip()

    if filter_label in CATEGORY_FILTER_TERMS:
        terms = CATEGORY_FILTER_TERMS[filter_label]
        if terms:
            if filter_label == "Writing" and "description" in df.columns:
                category_mask = df.apply(
                    lambda row, cat=filter_label: _title_matches_category(
                        str(row.get("title") or ""),
                        cat,
                        row.get("description"),
                    ),
                    axis=1,
                )
            else:
                category_mask = title_s.apply(
                    lambda title, cat=filter_label: _title_matches_category(title, cat)
                )
            mask &= category_mask
    elif filter_label:
        mask &= title_s.str.contains(filter_label.lower(), regex=False, na=False)

    if keyword_term:
        mask &= title_s.str.contains(keyword_term.lower(), regex=False, na=False)

    if city_term and "location" in df.columns:
        loc_s = df["location"].astype(str)
        mask &= loc_s.apply(lambda loc, c=city_term: city_matches(loc, c))

    filtered = df[mask]
    if filtered.empty:
        return filtered

    canada_mask = filtered.apply(
        lambda row: is_trades_job_row(
            site=str(row.get("site", "")),
            location=str(row.get("location", "")),
            title=str(row.get("title", "")),
            description=str(row.get("description", "") or ""),
            is_remote=row.get("is_remote") if row.get("is_remote") in (True, False) else None,
            company=str(row.get("company", "")),
        ),
        axis=1,
    )
    result = filtered[canada_mask]
    if "date_posted" in result.columns:
        result = result.sort_values("date_posted", ascending=False, na_position="last")
    return result


def is_supabase_auth_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and create_client)


def is_supabase_database_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and create_client)


def _require_supabase_dependency() -> None:
    if create_client is None:
        raise RuntimeError(
            "The 'supabase' package is not installed. Add it from requirements.txt before using the database layer."
        )


@lru_cache(maxsize=1)
def get_public_client() -> Client:
    _require_supabase_dependency()
    if not is_supabase_auth_configured():
        raise RuntimeError("Supabase auth is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    _require_supabase_dependency()
    if not is_supabase_database_configured():
        raise RuntimeError(
            "Supabase database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return bool(pd.isna(value)) if not isinstance(value, (dict, list, tuple, set)) else False


def _json_safe_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _response_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not data:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _first_row(query: Any) -> dict[str, Any] | None:
    response = query.limit(1).execute()
    rows = _response_rows(response)
    return rows[0] if rows else None


def _build_source_key(job: dict[str, Any]) -> str:
    pieces = [
        str(job.get("site") or ""),
        str(job.get("job_url_direct") or job.get("job_url") or ""),
        str(job.get("title") or ""),
        str(job.get("company") or job.get("company_name") or ""),
    ]
    return hashlib.sha256("|".join(pieces).encode("utf-8")).hexdigest()


def _coerce_text(value: Any) -> str | None:
    safe_value = _json_safe_value(value)
    if safe_value in (None, ""):
        return None
    return str(safe_value)


def _coerce_number(value: Any) -> float | None:
    safe_value = _json_safe_value(value)
    if safe_value in (None, ""):
        return None
    try:
        return float(safe_value)
    except (TypeError, ValueError):
        return None


def format_compensation(compensation: Any) -> str | None:
    if not compensation:
        return None
    if isinstance(compensation, str):
        return compensation
    if not isinstance(compensation, dict):
        return str(compensation)

    min_amount = compensation.get("min_amount")
    max_amount = compensation.get("max_amount")
    currency = compensation.get("currency")
    interval = compensation.get("interval")

    if min_amount and max_amount:
        text = f"{currency or 'USD'} ${int(float(min_amount)):,} - ${int(float(max_amount)):,}"
    elif min_amount:
        text = f"{currency or 'USD'} ${int(float(min_amount)):,}"
    else:
        text = None

    if text and interval:
        return f"{text}/{interval}"
    return text


def build_job_record(job: dict[str, Any]) -> dict[str, Any]:
    safe_job = {str(key): _json_safe_value(value) for key, value in job.items()}
    compensation_text = format_compensation(safe_job.get("compensation"))
    if not compensation_text:
        compensation_text = _coerce_text(safe_job.get("compensation"))

    description = safe_job.get("description")
    if description is not None:
        description = str(description)

    record = {
        "source_key": _build_source_key(safe_job),
        "site": _coerce_text(safe_job.get("site")),
        "title": _coerce_text(safe_job.get("title")),
        "company": _coerce_text(safe_job.get("company") or safe_job.get("company_name")),
        "location": _coerce_text(safe_job.get("location")),
        "description": description,
        "compensation": compensation_text,
        "interval": _coerce_text(safe_job.get("interval")),
        "min_amount": _coerce_number(safe_job.get("min_amount")),
        "max_amount": _coerce_number(safe_job.get("max_amount")),
        "currency": _coerce_text(safe_job.get("currency")),
        "job_type": _coerce_text(safe_job.get("job_type")),
        "job_url": _coerce_text(safe_job.get("job_url")),
        "job_url_direct": _coerce_text(safe_job.get("job_url_direct") or safe_job.get("job_url")),
        "date_posted": _coerce_text(safe_job.get("date_posted")),
        "is_remote": bool(safe_job.get("is_remote", False)),
        "raw_payload": safe_job,
    }
    if jobs_supports_is_active():
        record["is_active"] = bool(safe_job.get("is_active", True))
    return record


def dataframe_to_job_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []

    records: list[dict[str, Any]] = []
    for raw_row in df.to_dict(orient="records"):
        job_record = build_job_record(raw_row)
        if job_record.get("title"):
            records.append(job_record)
    return records


def sign_up_user(email: str, password: str) -> Any:
    return get_public_client().auth.sign_up({"email": email, "password": password})


def sign_in_user(email: str, password: str) -> Any:
    return get_public_client().auth.sign_in_with_password({"email": email, "password": password})


def send_magic_link(email: str, redirect_to: str, *, should_create_user: bool = True) -> Any:
    return get_public_client().auth.sign_in_with_otp(
        {
            "email": email,
            "options": {
                "email_redirect_to": redirect_to,
                "should_create_user": should_create_user,
            },
        }
    )


def verify_magic_link(token_hash: str, auth_type: str = "email") -> Any:
    from supabase_auth.types import VerifyTokenHashParams

    return get_public_client().auth.verify_otp(
        VerifyTokenHashParams(token_hash=token_hash, type=auth_type)
    )


def verify_email_otp_code(email: str, token: str) -> Any:
    """Verify a 6-digit email OTP (works when Outlook/Hotmail prefetch invalidates magic links)."""
    return get_public_client().auth.verify_otp(
        {
            "email": email.strip().lower(),
            "token": token.strip(),
            "type": "email",
        }
    )


def _is_valid_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def get_profile_by_user_id(user_id: str) -> dict[str, Any] | None:
    if not is_supabase_database_configured() or not _is_valid_uuid(user_id):
        return None
    return _first_row(get_service_client().table("profiles").select("*").eq("id", user_id))


def get_profile_by_email(email: str) -> dict[str, Any] | None:
    if not is_supabase_database_configured():
        return None
    return _first_row(get_service_client().table("profiles").select("*").eq("email", email.lower()))


def upsert_profile(user_id: str, email: str, is_admin: bool = False, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": user_id,
        "email": email.lower(),
        "is_admin": bool(is_admin),
        "metadata": metadata or {},
    }
    get_service_client().table("profiles").upsert(payload, on_conflict="id").execute()
    profile = get_profile_by_user_id(user_id)
    return profile or payload


def sync_profile_from_auth_user(auth_user: Any) -> dict[str, Any]:
    email = getattr(auth_user, "email", None) or ""
    user_id = getattr(auth_user, "id", None)
    if not user_id or not email:
        raise RuntimeError("Supabase auth response did not include a user id and email.")
    metadata = getattr(auth_user, "user_metadata", None) or {}
    return upsert_profile(user_id=user_id, email=email, metadata=metadata)


def ensure_profile_for_checkout(email: str) -> dict[str, Any]:
    """Return an existing profile or create a passwordless auth user for Stripe checkout."""
    normalized = email.strip().lower()
    existing = get_profile_by_email(normalized)
    if existing:
        return existing
    if not is_supabase_auth_configured():
        raise RuntimeError("Supabase auth is not configured yet.")

    admin = get_service_client().auth.admin
    try:
        created = admin.create_user(
            {
                "email": normalized,
                "password": secrets.token_urlsafe(32),
                "email_confirm": True,
            }
        )
        return sync_profile_from_auth_user(created.user)
    except Exception as exc:
        if "already" in str(exc).lower():
            existing = get_profile_by_email(normalized)
            if existing:
                return existing
        raise


def upsert_subscription(
    *,
    user_id: str,
    email: str | None = None,
    status: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    stripe_price_id: str | None = None,
    stripe_checkout_session_id: str | None = None,
    current_period_end: str | None = None,
) -> None:
    payload = {
        "user_id": user_id,
        "email": email.lower() if email else None,
        "status": status,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "stripe_price_id": stripe_price_id,
        "stripe_checkout_session_id": stripe_checkout_session_id,
        "current_period_end": current_period_end,
    }
    get_service_client().table("subscriptions").upsert(payload, on_conflict="user_id").execute()


def get_subscription_by_user_id(user_id: str) -> dict[str, Any] | None:
    if not is_supabase_database_configured():
        return None
    return _first_row(get_service_client().table("subscriptions").select("*").eq("user_id", user_id))


def get_subscription_by_stripe_subscription_id(stripe_subscription_id: str) -> dict[str, Any] | None:
    if not is_supabase_database_configured():
        return None
    return _first_row(
        get_service_client().table("subscriptions").select("*").eq("stripe_subscription_id", stripe_subscription_id)
    )


def user_has_active_subscription(user_id: str) -> bool:
    subscription = get_subscription_by_user_id(user_id)
    if not subscription:
        return False
    return (subscription.get("status") or "").lower() in ACTIVE_SUBSCRIPTION_STATUSES


def _jobs_search_query(keyword: str, filter_value: str, *, columns: str, count: str | None = "exact") -> Any:
    query = get_service_client().table("jobs").select(columns, count=count)
    query = query.in_("site", list(LISTED_JOB_SITES))
    if jobs_supports_is_active():
        query = query.eq("is_active", True)
    return _apply_title_filters_to_query(query, keyword, filter_value)


def _job_row_is_eligible(job: dict[str, Any]) -> bool:
    remote_flag = job.get("is_remote")
    if remote_flag not in (True, False):
        remote_flag = None
    return is_trades_job_row(
        site=str(job.get("site") or ""),
        location=str(job.get("location") or ""),
        title=str(job.get("title") or ""),
        description=str(job.get("description") or ""),
        is_remote=remote_flag,
        company=str(job.get("company") or ""),
    )


def invalidate_jobs_search_cache() -> None:
    """Clear the in-memory search cache (call after job upserts)."""
    with _job_search_cache_lock:
        _job_search_cache["rows"] = []
        _job_search_cache["loaded_at"] = 0.0


def _job_search_cache_is_warm_unlocked() -> bool:
    rows = _job_search_cache["rows"]
    loaded_at = _job_search_cache["loaded_at"]
    return bool(rows) and time.time() - loaded_at < JOB_CACHE_TTL_SECONDS


def _job_search_cache_is_warm() -> bool:
    with _job_search_cache_lock:
        return _job_search_cache_is_warm_unlocked()


def kickoff_job_search_cache_warm() -> None:
    """Start loading the full search cache in the background if it is not ready yet."""
    global _cache_warm_in_progress
    with _job_search_cache_lock:
        if _job_search_cache_is_warm_unlocked() or _cache_warm_in_progress:
            return
        _cache_warm_in_progress = True

    def _run() -> None:
        global _cache_warm_in_progress
        try:
            _get_cached_eligible_jobs(force_refresh=True)
        except Exception:
            pass
        finally:
            with _job_search_cache_lock:
                _cache_warm_in_progress = False
                _cache_warm_cond.notify_all()

    threading.Thread(target=_run, daemon=True, name="job-cache-warm").start()


def warm_jobs_search_cache() -> int:
    """Preload Canada job listings into memory. Returns number of cached rows."""
    return len(_get_cached_eligible_jobs(force_refresh=True))


def _get_cached_eligible_jobs(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Load listed jobs once, Canada-filter, and reuse from memory for fast search."""
    global _cache_warm_in_progress

    with _job_search_cache_lock:
        if not force_refresh and _job_search_cache_is_warm_unlocked():
            return list(_job_search_cache["rows"])
        while _cache_warm_in_progress and not force_refresh:
            _cache_warm_cond.wait(timeout=120)
            if _job_search_cache_is_warm_unlocked():
                return list(_job_search_cache["rows"])
        _cache_warm_in_progress = True

    try:
        raw_rows = _fetch_listed_jobs_from_supabase(columns=JOB_SEARCH_COLUMNS)
        eligible_rows = [row for row in raw_rows if _job_row_is_eligible(row)]
        with _job_search_cache_lock:
            _job_search_cache["rows"] = eligible_rows
            _job_search_cache["loaded_at"] = time.time()
        return eligible_rows
    finally:
        with _job_search_cache_lock:
            _cache_warm_in_progress = False
            _cache_warm_cond.notify_all()


def _fetch_listed_jobs_from_supabase(*, columns: str) -> list[dict[str, Any]]:
    page_size = 1000
    offset = 0
    all_rows: list[dict[str, Any]] = []
    while True:
        query = get_service_client().table("jobs").select(columns, count="exact" if offset == 0 else None)
        query = query.in_("site", list(LISTED_JOB_SITES))
        if jobs_supports_is_active():
            query = query.eq("is_active", True)
        response = query.order("date_posted", desc=True).range(offset, offset + page_size - 1).execute()
        batch = _response_rows(response)
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows


def _filter_cached_job_rows(
    rows: list[dict[str, Any]],
    keyword: str,
    filter_value: str,
    city: str = "",
) -> list[dict[str, Any]]:
    filter_label = (filter_value or "").strip()
    keyword_term = (keyword or "").strip()
    city_term = (city or "").strip()
    if not filter_label and not keyword_term and not city_term:
        return rows

    filtered: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or "")
        if filter_label in CATEGORY_FILTER_TERMS:
            if not _title_matches_category(title, filter_label, row.get("description")):
                continue
        elif filter_label and filter_label.lower() not in title.lower():
            continue
        if keyword_term and keyword_term.lower() not in title.lower():
            continue
        if city_term and not city_matches(str(row.get("location") or ""), city_term):
            continue
        filtered.append(row)
    return filtered


def _sort_jobs_by_date_posted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest jobs first; rows without a date sort last."""

    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        value = row.get("date_posted")
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return (0, "")
        return (1, str(value))

    return sorted(rows, key=sort_key, reverse=True)


def _fetch_all_listed_jobs(keyword: str, filter_value: str, *, columns: str, city: str = "") -> list[dict[str, Any]]:
    del columns  # cache uses JOB_SEARCH_COLUMNS
    base_rows = _get_cached_eligible_jobs()
    filtered = _filter_cached_job_rows(base_rows, keyword, filter_value, city=city)
    return _sort_jobs_by_date_posted(filtered)


def list_available_cities(*, limit: int = 80) -> list[str]:
    """City options for search UI, derived from currently eligible jobs."""
    return collect_cities(_get_cached_eligible_jobs(), limit=limit)


def search_jobs(
    *,
    keyword: str,
    filter_value: str,
    page: int,
    results_per_page: int,
    city: str = "",
) -> tuple[list[dict[str, Any]], int]:
    page = max(int(page), 1)
    results_per_page = max(int(results_per_page), 1)

    all_rows = _fetch_all_listed_jobs(keyword, filter_value, columns=JOB_SEARCH_COLUMNS, city=city)
    total_count = len(all_rows)
    if total_count == 0:
        return [], 0

    start_index = (page - 1) * results_per_page
    if start_index >= total_count:
        start_index = 0

    end_index = start_index + results_per_page
    return all_rows[start_index:end_index], total_count


DEFAULT_LANDING_PREVIEW_CATEGORIES: tuple[str, ...] = ("Operators", "Underground", "Trades")

_LANDING_PREVIEW_COLUMNS = (
    "title, company, compensation, description, raw_payload, location, site, date_posted, is_remote, "
    "min_amount, max_amount, currency, interval"
)


def _description_snippet(description: Any, max_len: int = 120) -> str:
    if description is None or (isinstance(description, float) and math.isnan(description)):
        return ""
    text = re.sub(r"\s+", " ", str(description).strip())
    if not text or text.lower() == "nan":
        return ""
    if len(text) <= max_len:
        return text
    clipped = text[:max_len].rsplit(" ", 1)[0]
    return f"{clipped}..." if clipped else f"{text[:max_len]}..."


def _extract_skills_from_job(job: dict[str, Any]) -> str:
    skills = job.get("skills")
    if skills is not None and not (isinstance(skills, float) and math.isnan(skills)):
        skills_text = str(skills).strip()
        if skills_text and skills_text.lower() != "nan":
            return skills_text[:220]

    raw_payload = job.get("raw_payload")
    if isinstance(raw_payload, dict):
        for key in ("skills", "technical_tools"):
            value = raw_payload.get(key)
            if not value:
                continue
            if isinstance(value, list):
                parts = [str(item).strip() for item in value if str(item).strip()]
                if parts:
                    return ", ".join(parts[:10])[:220]
            skills_text = str(value).strip()
            if skills_text and skills_text.lower() != "nan":
                return skills_text[:220]
    return ""


def _job_description_text(job: dict[str, Any]) -> str:
    snippet = _description_snippet(job.get("description"))
    if snippet:
        return snippet

    raw_payload = job.get("raw_payload")
    if isinstance(raw_payload, dict):
        for key in ("description", "requirements_summary", "job_description"):
            snippet = _description_snippet(raw_payload.get(key))
            if snippet:
                return snippet
    return ""


def _landing_preview_richness(job: dict[str, Any]) -> int:
    score = 0
    if _job_description_text(job):
        score += 4
    if job.get("compensation") or _coerce_number(job.get("min_amount")) or _coerce_number(job.get("max_amount")):
        score += 3
    if _extract_skills_from_job(job):
        score += 2
    return score


def _pick_best_landing_preview_row(rows: list[dict[str, Any]], category: str) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    for row in rows:
        if not _job_row_is_eligible(row):
            continue
        title = str(row.get("title") or "")
        if not _title_matches_category(title, category):
            continue
        score = _landing_preview_richness(row)
        if score > best_score:
            best_score = score
            best = row
    return best


def job_to_landing_preview(job: dict[str, Any], *, category: str | None = None) -> dict[str, Any]:
    compensation: str | None = None
    raw_compensation = job.get("compensation")
    if raw_compensation is not None:
        raw_text = str(raw_compensation).strip()
        if raw_text and raw_text.lower() != "nan":
            compensation = raw_text
    if not compensation:
        min_amount = _coerce_number(job.get("min_amount"))
        max_amount = _coerce_number(job.get("max_amount"))
        if min_amount is not None or max_amount is not None:
            compensation = format_compensation(
                {
                    "min_amount": min_amount,
                    "max_amount": max_amount,
                    "currency": job.get("currency"),
                    "interval": job.get("interval"),
                }
            )

    return {
        "title": job.get("title"),
        "company": job.get("company"),
        "category": category,
        "compensation": compensation,
        "skills": _extract_skills_from_job(job),
        "snippet": _job_description_text(job),
    }


def _fetch_one_listed_job_for_category(category: str) -> dict[str, Any] | None:
    if not is_supabase_database_configured():
        return None

    def _base_query() -> Any:
        query = (
            get_service_client()
            .table("jobs")
            .select(_LANDING_PREVIEW_COLUMNS)
            .in_("site", list(LISTED_JOB_SITES))
        )
        if jobs_supports_is_active():
            query = query.eq("is_active", True)
        return _apply_title_filters_to_query(query, "", category)

    best_any: dict[str, Any] | None = None
    for require_description in (True, False):
        query = _base_query()
        if require_description:
            query = query.not_.is_("description", "null").neq("description", "")
        response = query.order("date_posted", desc=True).limit(50).execute()
        picked = _pick_best_landing_preview_row(_response_rows(response), category)
        if picked is None:
            continue
        if _landing_preview_richness(picked) > 0:
            return picked
        if best_any is None:
            best_any = picked
    return best_any


def preview_jobs_default_landing() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for category in DEFAULT_LANDING_PREVIEW_CATEGORIES:
        job: dict[str, Any] | None = None
        if is_supabase_database_configured():
            job = _fetch_one_listed_job_for_category(category)
        if job is None:
            cached = _fetch_all_listed_jobs("", category, columns=JOB_SEARCH_COLUMNS)
            if cached:
                job = _pick_best_landing_preview_row(cached[:25], category) or dict(cached[0])
        if job:
            results.append(job_to_landing_preview(job, category=category))
    return results


def preview_jobs(keyword: str, filter_value: str, limit: int = 3, city: str = "") -> tuple[list[dict[str, Any]], int]:
    if _job_search_cache_is_warm():
        rows = _fetch_all_listed_jobs(keyword, filter_value, columns=JOB_SEARCH_COLUMNS, city=city)
        category = (filter_value or "").strip() or None
        results = [job_to_landing_preview(job, category=category) for job in rows[:limit]]
        return results, len(rows)

    kickoff_job_search_cache_warm()
    return _preview_jobs_from_supabase(keyword, filter_value, limit=limit)


def _preview_jobs_from_supabase(
    keyword: str,
    filter_value: str,
    *,
    limit: int = 3,
    sample_limit: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    """Fast landing-page preview without loading the full in-memory cache."""
    if not is_supabase_database_configured():
        return [], 0

    def _filtered_query(*, select: str, count: str | None = None) -> Any:
        query = get_service_client().table("jobs").select(select, count=count)
        query = query.in_("site", list(LISTED_JOB_SITES))
        if jobs_supports_is_active():
            query = query.eq("is_active", True)
        return _apply_title_filters_to_query(query, keyword, filter_value)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        count_future = pool.submit(
            lambda: _filtered_query(select="id", count="exact").limit(1).execute()
        )
        rows_future = pool.submit(
            lambda: _filtered_query(select=_LANDING_PREVIEW_COLUMNS)
            .order("date_posted", desc=True)
            .limit(sample_limit)
            .execute()
        )
        count_response = count_future.result()
        response = rows_future.result()

    approx_total = int(count_response.count or 0)
    rows = _response_rows(response)
    eligible_rows = [row for row in rows if _job_row_is_eligible(row)]
    filtered = _filter_cached_job_rows(eligible_rows, keyword, filter_value)
    sorted_rows = _sort_jobs_by_date_posted(filtered)
    category = (filter_value or "").strip() or None
    results = [job_to_landing_preview(job, category=category) for job in sorted_rows[:limit]]
    total = approx_total if approx_total else len(sorted_rows)
    return results, total


def upsert_jobs(records: list[dict[str, Any]], chunk_size: int = 500) -> int:
    if not records:
        return 0

    for record in records:
        if jobs_supports_is_active():
            record["is_active"] = True
        else:
            record.pop("is_active", None)

    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        source_key = record.get("source_key")
        if source_key:
            deduped[str(source_key)] = record
    records = list(deduped.values())

    client = get_service_client()
    inserted = 0
    for start in range(0, len(records), chunk_size):
        chunk = records[start : start + chunk_size]
        client.table("jobs").upsert(chunk, on_conflict="source_key").execute()
        inserted += len(chunk)
    invalidate_jobs_search_cache()
    return inserted


@lru_cache(maxsize=1)
def jobs_supports_is_active() -> bool:
    if not is_supabase_database_configured():
        return False
    try:
        get_service_client().table("jobs").select("is_active").limit(1).execute()
        return True
    except Exception:
        return False


def deactivate_jobs(job_ids: list[str], chunk_size: int = 200) -> int:
    if not job_ids or not is_supabase_database_configured():
        return 0

    client = get_service_client()
    affected = 0
    unique_ids = list(dict.fromkeys(job_ids))

    if jobs_supports_is_active():
        for start in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[start : start + chunk_size]
            client.table("jobs").update({"is_active": False}).in_("id", chunk).execute()
            affected += len(chunk)
        return affected

    for start in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[start : start + chunk_size]
        client.table("jobs").delete().in_("id", chunk).execute()
        affected += len(chunk)
    return affected


def record_scrape_run(status: str, jobs_seen: int = 0, message: str | None = None) -> None:
    if not is_supabase_database_configured():
        return
    payload = {
        "status": status,
        "jobs_seen": jobs_seen,
        "message": message,
    }
    get_service_client().table("scrape_runs").insert(payload).execute()


def save_contact_message(
    *,
    email: str,
    subject: str,
    message: str,
    ip_address: str,
    recaptcha_score: float | None,
    user_id: str | None = None,
    delivery_status: str = "received",
) -> None:
    payload = {
        "user_id": user_id,
        "email": email.lower(),
        "subject": subject,
        "message": message,
        "ip_address": ip_address,
        "recaptcha_score": recaptcha_score,
        "delivery_status": delivery_status,
    }
    get_service_client().table("contact_messages").insert(payload).execute()


@lru_cache(maxsize=1)
def job_alerts_table_exists() -> bool:
    if not is_supabase_database_configured():
        return False
    try:
        get_service_client().table("job_alert_preferences").select("user_id").limit(1).execute()
        return True
    except Exception:
        return False


def get_job_alert_preferences(user_id: str) -> dict[str, Any] | None:
    if not job_alerts_table_exists():
        return None
    return _first_row(
        get_service_client().table("job_alert_preferences").select("*").eq("user_id", user_id)
    )


def job_alerts_enabled_for_user(user_id: str) -> bool:
    prefs = get_job_alert_preferences(user_id)
    if prefs is None:
        return True
    return bool(prefs.get("enabled", True))


def set_job_alert_enabled(user_id: str, enabled: bool) -> None:
    if not job_alerts_table_exists():
        raise RuntimeError("Job alerts are not configured yet.")
    payload = {"user_id": user_id, "enabled": enabled}
    get_service_client().table("job_alert_preferences").upsert(payload, on_conflict="user_id").execute()


def list_active_subscribers_for_alerts() -> list[dict[str, str]]:
    if not is_supabase_database_configured():
        return []

    client = get_service_client()
    statuses = list(ACTIVE_SUBSCRIPTION_STATUSES)
    offset = 0
    page_size = 500
    results: list[dict[str, str]] = []
    seen_emails: set[str] = set()

    while True:
        response = (
            client.table("subscriptions")
            .select("user_id, email, status")
            .in_("status", statuses)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = _response_rows(response)
        if not rows:
            break

        for row in rows:
            user_id = str(row.get("user_id") or "").strip()
            if not user_id or not job_alerts_enabled_for_user(user_id):
                continue

            email = (row.get("email") or "").strip().lower()
            if not email:
                profile = get_profile_by_user_id(user_id)
                email = (profile or {}).get("email", "").strip().lower()
            if not email or email in seen_emails:
                continue

            seen_emails.add(email)
            results.append({"user_id": user_id, "email": email})

        if len(rows) < page_size:
            break
        offset += page_size

    return results


def fetch_recent_jobs_for_alerts(*, lookback_hours: int = 24, limit: int = 15) -> list[dict[str, Any]]:
    if not is_supabase_database_configured():
        return []

    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    query = get_service_client().table("jobs").select(JOB_SEARCH_COLUMNS)
    query = query.in_("site", list(LISTED_JOB_SITES))
    if jobs_supports_is_active():
        query = query.eq("is_active", True)
    query = query.gte("date_posted", since.isoformat())
    query = query.order("date_posted", desc=True).limit(max(limit * 3, limit))
    rows = _response_rows(query.execute())
    eligible_rows = [row for row in rows if _job_row_is_eligible(row)]
    return _sort_jobs_by_date_posted(eligible_rows)[:limit]


def start_job_alert_run() -> str | None:
    if not job_alerts_table_exists():
        return None
    run_id = str(uuid.uuid4())
    get_service_client().table("job_alert_runs").insert({"id": run_id, "status": "running"}).execute()
    return run_id


def finish_job_alert_run(
    run_id: str | None,
    *,
    jobs_count: int,
    emails_sent: int,
    emails_skipped: int,
    status: str,
    error_message: str | None = None,
) -> None:
    if not run_id or not job_alerts_table_exists():
        return
    payload = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "jobs_count": jobs_count,
        "emails_sent": emails_sent,
        "emails_skipped": emails_skipped,
        "status": status,
        "error_message": error_message,
    }
    get_service_client().table("job_alert_runs").update(payload).eq("id", run_id).execute()


def touch_job_alert_sent(user_id: str) -> None:
    if not job_alerts_table_exists():
        return
    now = datetime.now(timezone.utc).isoformat()
    prefs = get_job_alert_preferences(user_id)
    if prefs:
        get_service_client().table("job_alert_preferences").update({"last_sent_at": now}).eq(
            "user_id", user_id
        ).execute()
    else:
        get_service_client().table("job_alert_preferences").insert(
            {"user_id": user_id, "enabled": True, "last_sent_at": now}
        ).execute()
