"""Re-apply Canada location filter to jobs_cache.pkl without re-scraping."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ats_location import is_canada_job_row

CACHE = ROOT / "jobs_cache.pkl"


def main() -> None:
    df = pickle.load(open(CACHE, "rb"))
    before = len(df)
    mask = df.apply(
        lambda row: is_canada_job_row(
            site=str(row.get("site", "")),
            location=str(row.get("location", "")),
            title=str(row.get("title", "")),
            description=str(row.get("description", "") or ""),
            is_remote=row.get("is_remote") if row.get("is_remote") in (True, False) else None,
            company=str(row.get("company", "")),
        ),
        axis=1,
    )
    filtered = df[mask].copy()
    after = len(filtered)
    print(f"Filtered cache: {before} -> {after} ({before - after} removed)")
    if "site" in filtered.columns:
        print(filtered["site"].value_counts().to_string())
    pickle.dump(filtered, open(CACHE, "wb"))
    print(f"Wrote {CACHE}")


if __name__ == "__main__":
    main()
