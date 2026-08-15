"""Deactivate Supabase job rows that fail the Canada location filter."""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ats_location import is_canada_job_row
from data_store import (
    _response_rows,
    deactivate_jobs,
    get_service_client,
    is_supabase_database_configured,
    jobs_supports_is_active,
)


def _fetch_jobs_batch(start: int, end: int) -> list[dict]:
    client = get_service_client()
    columns = "id,site,location,title,description,is_remote,company"
    if jobs_supports_is_active():
        columns += ",is_active"
    query = client.table("jobs").select(columns)
    if jobs_supports_is_active():
        query = query.eq("is_active", True)
    response = query.range(start, end).execute()
    return _response_rows(response)


def main() -> None:
    if not is_supabase_database_configured():
        raise RuntimeError("Supabase is not configured.")

    batch_size = 500
    start = 0
    to_deactivate: list[str] = []
    scanned = 0

    while True:
        rows = _fetch_jobs_batch(start, start + batch_size - 1)
        if not rows:
            break

        for row in rows:
            scanned += 1
            remote_flag = row.get("is_remote")
            if remote_flag not in (True, False):
                remote_flag = None
            if is_canada_job_row(
                site=str(row.get("site") or ""),
                location=str(row.get("location") or ""),
                title=str(row.get("title") or ""),
                description=str(row.get("description") or ""),
                is_remote=remote_flag,
                company=str(row.get("company") or ""),
            ):
                continue
            job_id = row.get("id")
            if job_id:
                to_deactivate.append(str(job_id))

        if len(rows) < batch_size:
            break
        start += batch_size

    removed = deactivate_jobs(to_deactivate)
    print(f"Scanned {scanned} active jobs; deactivated {removed} non-Canada listings.")


if __name__ == "__main__":
    main()
