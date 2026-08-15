"""Check scraped job URLs and deactivate or remove listings that are dead/expired.

Usage:
  python scripts/validate_job_links.py --limit 200        # sample first
  python scripts/validate_job_links.py                    # full database
  python scripts/validate_job_links.py --dry-run        # report only

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from data_store import deactivate_jobs, get_service_client, jobs_supports_is_active  # noqa: E402

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEAD_BODY_PATTERNS = re.compile(
    r"|".join(
        [
            r"job listing not found",
            r"job posting is no longer available",
            r"no longer accepting applications",
            r"this job has expired",
            r"this job is no longer available",
            r"page you are trying to access is no longer active",
            r"the job you were looking for is no longer available",
            r"jobposting not found",
            r"offre d'emploi n'est plus disponible",
            r"page n'existe plus",
        ]
    ),
    re.IGNORECASE,
)

# Indeed often returns 403 to bots — treat as unknown, not dead.
AGGREGATOR_HOSTS = {
    "ca.indeed.com",
    "www.indeed.com",
    "indeed.com",
}


def _fetch(url: str, timeout: int) -> tuple[int, str]:
    response = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-CA,en;q=0.9"},
    )
    text = (response.text or "")[:12000]
    return response.status_code, text


def classify_job(job: dict[str, Any], timeout: int) -> str:
    """Return: active | dead | unknown"""
    url = (job.get("job_url_direct") or job.get("job_url") or "").strip()
    if not url:
        return "dead"

    host = urlparse(url).netloc.lower()
    try:
        status, body = _fetch(url, timeout)
    except requests.RequestException:
        return "unknown"

    if status in (404, 410):
        return "dead"
    if status >= 500:
        return "unknown"
    if DEAD_BODY_PATTERNS.search(body):
        return "dead"
    if status == 403 and host in AGGREGATOR_HOSTS:
        return "unknown"
    if status >= 400:
        return "dead"
    return "active"


def fetch_jobs(limit: int | None) -> list[dict[str, Any]]:
    client = get_service_client()
    page_size = 500
    offset = 0
    rows: list[dict[str, Any]] = []

    while True:
        end = offset + page_size - 1
        columns = "id,title,site,job_url_direct,job_url"
        if jobs_supports_is_active():
            columns += ",is_active"
        query = (
            client.table("jobs")
            .select(columns)
            .order("date_posted", desc=True)
        )
        if jobs_supports_is_active():
            query = query.eq("is_active", True)
        response = query.range(offset, end).execute()
        batch = response.data or []
        if not batch:
            break
        rows.extend(batch)
        if limit and len(rows) >= limit:
            return rows[:limit]
        if len(batch) < page_size:
            break
        offset += page_size

    return rows[:limit] if limit else rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate job apply links and prune dead listings.")
    parser.add_argument("--limit", type=int, default=None, help="Only check this many jobs (newest first).")
    parser.add_argument("--workers", type=int, default=8, help="Parallel HTTP workers.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout per URL in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not update the database.")
    parser.add_argument(
        "--prune-unknown-aggregators",
        action="store_true",
        help="Also remove indeed/linkedin jobs we could not verify (403/blocked).",
    )
    args = parser.parse_args()

    jobs = fetch_jobs(args.limit)
    if not jobs:
        print("No jobs to validate.")
        return 0

    print(f"Checking {len(jobs)} job URLs (workers={args.workers})...")
    started = time.time()
    active_ids: list[str] = []
    dead_ids: list[str] = []
    unknown_ids: list[str] = []
    unknown = 0
    dead_samples: list[str] = []

    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        future_map = {pool.submit(classify_job, job, args.timeout): job for job in jobs}
        for future in as_completed(future_map):
            job = future_map[future]
            result = future.result()
            job_id = job["id"]
            if result == "active":
                active_ids.append(job_id)
            elif result == "dead":
                dead_ids.append(job_id)
                if len(dead_samples) < 12:
                    url = job.get("job_url_direct") or job.get("job_url") or ""
                    dead_samples.append(f"{job.get('site')} | {job.get('title', '')[:50]} | {url[:80]}")
            else:
                unknown += 1
                unknown_ids.append(job_id)

    elapsed = time.time() - started
    print(f"Done in {elapsed:.1f}s — active={len(active_ids)} dead={len(dead_ids)} unknown={unknown}")

    if dead_samples:
        print("\nSample dead listings:")
        for line in dead_samples:
            print(f"  - {line}")

    if dead_ids and not args.dry_run:
        removed = deactivate_jobs(dead_ids)
        mode = "deactivated (is_active=false)" if jobs_supports_is_active() else "deleted"
        print(f"\n{mode} {removed} dead job(s).")
    elif dead_ids and args.dry_run:
        print(f"\nDry run: would remove {len(dead_ids)} dead job(s).")

    prune_ids: list[str] = []
    if args.prune_unknown_aggregators:
        aggregator_sites = {"indeed", "linkedin", "ca.indeed.com", "www.indeed.com"}
        job_by_id = {j["id"]: j for j in jobs}
        for job_id in unknown_ids:
            job = job_by_id.get(job_id) or {}
            if (job.get("site") or "").lower() in aggregator_sites:
                prune_ids.append(job_id)

    if prune_ids and not args.dry_run:
        removed = deactivate_jobs(prune_ids)
        mode = "deactivated (is_active=false)" if jobs_supports_is_active() else "deleted"
        print(f"{mode} {removed} unverified aggregator job(s).")
    elif prune_ids and args.dry_run:
        print(f"Dry run: would remove {len(prune_ids)} unverified aggregator job(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
