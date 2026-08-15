"""Scrape remote Canada jobs from hiring.cafe via SSR pages (__NEXT_DATA__)."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from typing import Any

import pandas as pd
import requests

from ats_location import is_canada_job_row, is_canada_remote

BASE_URL = "https://hiring.cafe/"
USER_AGENT = "Mozilla/5.0 (compatible; WelcomeToTrades/1.0)"
NEXT_DATA_RE = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*([\s\S]*?)\s*</script>',
    re.I,
)
DEFAULT_DELAY_SECONDS = 0.6
DEFAULT_DATE_FETCHED_PAST_N_DAYS = 90


def build_canada_remote_search_state(
    *,
    search_query: str = "",
    days: int = DEFAULT_DATE_FETCHED_PAST_N_DAYS,
) -> dict[str, Any]:
    return {
        "locations": [
            {
                "formatted_address": "Canada",
                "types": ["country"],
                "geometry": {"location": {"lat": "56.1304", "lon": "-106.3468"}},
                "id": "user_country",
                "address_components": [
                    {"long_name": "Canada", "short_name": "CA", "types": ["country"]}
                ],
                "options": {"flexible_regions": []},
            }
        ],
        "workplaceTypes": ["Remote"],
        "defaultToUserLocation": False,
        "userLocation": None,
        "searchQuery": search_query,
        "jobTitleQuery": "",
        "jobDescriptionQuery": "",
        "dateFetchedPastNDays": days,
        "sortBy": "default",
    }


def build_search_url(search_state: dict[str, Any], page_no: int = 0) -> str:
    params: dict[str, str] = {
        "searchState": json.dumps(search_state, separators=(",", ":")),
    }
    if page_no > 0:
        params["page"] = str(page_no)
    return f"{BASE_URL}?{urllib.parse.urlencode(params)}"


def _as_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if item]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_country(value: str) -> str:
    return value.strip().lower().replace(".", "")


def is_hiring_cafe_canada_only(raw: dict[str, Any]) -> bool:
    """Strict Canada-only check using hiring.cafe structured location fields."""
    processed = _as_record(raw.get("v5_processed_job_data")) or {}
    job_information = _as_record(raw.get("job_information")) or {}

    workplace_type = _first_string(processed.get("workplace_type"))
    if workplace_type and workplace_type != "Remote":
        return False

    countries = list(
        dict.fromkeys(
            _normalize_country(c)
            for c in _string_list(processed.get("workplace_countries"))
            + _string_list(processed.get("boundless_workplace_countries"))
        )
    )
    if countries:
        has_canada = any(c in ("canada", "ca") for c in countries)
        has_us = any(
            c in ("united states", "usa", "us", "u s", "u s a")
            or "united states" in c
            for c in countries
        )
        has_other = any(c not in ("canada", "ca") for c in countries)
        if not has_canada or has_us or has_other:
            return False
        return True

    states = [s.lower() for s in _string_list(processed.get("workplace_states"))]
    if states and any(
        s in ("california", "texas", "new york", "florida", "washington", "illinois")
        or re.fullmatch(r"[a-z]{2}", s)
        for s in states
    ):
        if not any(_normalize_country(s) in ("canada", "ca") or "canada" in s for s in states):
            return False

    location = (
        _first_string(processed.get("formatted_workplace_location"))
        or _first_string(processed.get("workplace_cities"))
        or _first_string(processed.get("workplace_states"))
        or ""
    )
    title = (
        _first_string(job_information.get("title"))
        or _first_string(job_information.get("job_title_raw"))
        or _first_string(processed.get("core_job_title"))
        or ""
    )
    description = _first_string(processed.get("requirements_summary")) or ""
    combined = f"{title} {location} {description}".lower()
    return is_canada_remote(combined, is_remote=True)


def _first_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def parse_ssr_page(html: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        if re.search(r"cloudflare|cf-browser-verification|challenge-platform", html, re.I):
            raise RuntimeError("Hiring.cafe returned a Cloudflare challenge page.")
        raise RuntimeError("Hiring.cafe response did not include Next.js search data.")

    data = json.loads(match.group(1))
    page_props = _as_record(_as_record(data.get("props")).get("pageProps"))
    if not page_props:
        raise RuntimeError("Hiring.cafe search data was missing page props.")

    ssr_error = page_props.get("ssrError")
    if ssr_error:
        raise RuntimeError(f"Hiring.cafe SSR search failed: {ssr_error}")

    hits = page_props.get("ssrHits")
    if not isinstance(hits, list):
        hits = []

    return {
        "jobs": [job for job in hits if isinstance(job, dict)],
        "page": page_props.get("ssrPage") or 0,
        "total_count": page_props.get("ssrTotalCount"),
        "page_size": page_props.get("ssrPageSize"),
        "is_last_page": bool(page_props.get("ssrIsLastPage")),
    }


def _format_compensation(processed: dict[str, Any]) -> str | None:
    min_amount = processed.get("yearly_min_compensation")
    max_amount = processed.get("yearly_max_compensation")
    if min_amount is None and max_amount is None:
        return None

    currency = processed.get("listed_compensation_currency") or ""
    frequency = processed.get("listed_compensation_frequency") or "Yearly"
    if min_amount is not None and max_amount is not None:
        amount = f"{int(min_amount)}-{int(max_amount)}"
    elif min_amount is not None:
        amount = f"{int(min_amount)}+"
    else:
        amount = str(int(max_amount))

    parts = [str(currency).strip(), amount, f"/ {frequency}"]
    return " ".join(part for part in parts if part).strip() or None


def map_hiring_cafe_job(raw: dict[str, Any]) -> dict[str, Any] | None:
    job_information = _as_record(raw.get("job_information")) or {}
    processed = _as_record(raw.get("v5_processed_job_data")) or {}
    company_info = _as_record(job_information.get("company_info")) or {}
    enriched_company = _as_record(raw.get("enriched_company_data")) or {}

    apply_url = _first_string(raw.get("apply_url"))
    if not apply_url:
        return None

    title = (
        _first_string(job_information.get("title"))
        or _first_string(job_information.get("job_title_raw"))
        or _first_string(processed.get("core_job_title"))
    )
    if not title:
        return None

    company = (
        _first_string(company_info.get("name"))
        or _first_string(processed.get("company_name"))
        or _first_string(enriched_company.get("name"))
    )
    location = (
        _first_string(processed.get("formatted_workplace_location"))
        or _first_string(processed.get("workplace_cities"))
        or _first_string(processed.get("workplace_states"))
        or _first_string(processed.get("workplace_countries"))
    )
    workplace_type = _first_string(processed.get("workplace_type"))
    commitments = processed.get("commitment")
    if isinstance(commitments, list):
        job_type = ", ".join(str(item) for item in commitments if item)
    else:
        job_type = _first_string(commitments)

    skills = processed.get("technical_tools")
    if isinstance(skills, list):
        skills_text = ", ".join(str(item) for item in skills if item)
    else:
        skills_text = _first_string(skills)

    description = (
        _first_string(job_information.get("description"))
        or _first_string(processed.get("requirements_summary"))
    )

    return {
        "id": _first_string(raw.get("requisition_id") or raw.get("id") or raw.get("objectID")),
        "site": "hiringcafe",
        "job_url": apply_url,
        "job_url_direct": apply_url,
        "title": title,
        "company": company,
        "location": location,
        "date_posted": _first_string(processed.get("estimated_publish_date")),
        "job_type": job_type,
        "interval": _first_string(processed.get("listed_compensation_frequency")),
        "min_amount": processed.get("yearly_min_compensation"),
        "max_amount": processed.get("yearly_max_compensation"),
        "currency": _first_string(processed.get("listed_compensation_currency")),
        "is_remote": workplace_type == "Remote",
        "description": description,
        "company_url": _first_string(enriched_company.get("homepage_uri"))
        or _first_string(processed.get("company_website")),
        "skills": skills_text,
        "work_from_home_type": workplace_type,
    }


def fetch_search_page(
    session: requests.Session,
    *,
    search_state: dict[str, Any],
    page_no: int,
    timeout: int = 30,
) -> dict[str, Any]:
    url = build_search_url(search_state, page_no)
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return parse_ssr_page(response.text)


def scrape_hiring_cafe(
    *,
    search_query: str = "",
    max_pages: int | None = None,
    max_jobs: int | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    days: int = DEFAULT_DATE_FETCHED_PAST_N_DAYS,
) -> pd.DataFrame:
    """Fetch remote Canada jobs from hiring.cafe and return a JobSpy-compatible DataFrame."""
    search_state = build_canada_remote_search_state(search_query=search_query, days=days)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    page_no = 0
    total_count: int | None = None

    print("Scraping hiring.cafe (Canada, Remote)...")
    while True:
        if max_pages is not None and page_no >= max_pages:
            break

        print(f"  page {page_no}...")
        page = fetch_search_page(session, search_state=search_state, page_no=page_no)
        if total_count is None and page.get("total_count") is not None:
            total_count = int(page["total_count"])
            print(f"  -> hiring.cafe reports {total_count:,} matching jobs")

        raw_jobs = page.get("jobs") or []
        added = 0
        for raw_job in raw_jobs:
            if not is_hiring_cafe_canada_only(raw_job):
                continue

            mapped = map_hiring_cafe_job(raw_job)
            if not mapped:
                continue

            apply_url = mapped["job_url_direct"]
            if apply_url in seen_urls:
                continue
            seen_urls.add(apply_url)

            if not is_canada_job_row(
                site=mapped.get("site", ""),
                location=str(mapped.get("location") or ""),
                title=str(mapped.get("title") or ""),
                description=str(mapped.get("description") or ""),
                is_remote=True,
                company=str(mapped.get("company") or ""),
            ):
                continue

            rows.append(mapped)
            added += 1
            if max_jobs is not None and len(rows) >= max_jobs:
                break

        print(f"  -> kept {added} jobs on page {page_no} ({len(rows)} total)")
        if max_jobs is not None and len(rows) >= max_jobs:
            break
        if page.get("is_last_page") or not raw_jobs:
            break

        page_no += 1
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    if not rows:
        print("  -> 0 hiring.cafe jobs kept after filtering")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    print(f"  -> {len(df)} hiring.cafe jobs after Canada/remote filter")
    return df
