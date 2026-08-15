"""Scrape hiring.cafe remote Canada jobs and merge into jobs_cache.pkl / Supabase."""

from __future__ import annotations

import argparse
import os
import pickle
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from data_store import (
    dataframe_to_job_records,
    is_supabase_database_configured,
    record_scrape_run,
    upsert_jobs,
)
from hiring_cafe_scraper import scrape_hiring_cafe


def _prefer_direct_urls(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "job_url_direct" in df.columns and "job_url" in df.columns:
        df["job_url_direct"] = df["job_url_direct"].where(
            df["job_url_direct"].notna() & (df["job_url_direct"] != ""),
            df["job_url"],
        )
    if "job_url_direct" in df.columns:
        df = df[df["job_url_direct"].notna() & (df["job_url_direct"].astype(str).str.strip() != "")]
    return df


def _dedupe_jobs(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    url_col = "job_url_direct" if "job_url_direct" in df.columns else "job_url"
    if url_col not in df.columns:
        return df
    out = df.copy()
    out[url_col] = out[url_col].astype(str).str.strip()
    out = out[out[url_col].notna() & (out[url_col] != "")]
    return out.drop_duplicates(subset=[url_col], keep="first")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape hiring.cafe remote Canada jobs.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages fetched.")
    parser.add_argument("--max-jobs", type=int, default=None, help="Stop after N kept jobs.")
    parser.add_argument(
        "--replace-cache",
        action="store_true",
        help="Replace jobs_cache.pkl with hiring.cafe results only (default: merge).",
    )
    parser.add_argument("--no-supabase", action="store_true", help="Skip Supabase sync.")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(base_dir, "jobs_cache.pkl")

    df_new = scrape_hiring_cafe(max_pages=args.max_pages, max_jobs=args.max_jobs)
    df_new = _prefer_direct_urls(df_new)
    if df_new.empty:
        print("No hiring.cafe jobs scraped.")
        return

    if args.replace_cache:
        df_final = df_new
    elif os.path.exists(cache_path):
        with open(cache_path, "rb") as handle:
            existing = pickle.load(handle)
        df_final = pd.concat([existing, df_new], ignore_index=True)
        before = len(df_final)
        df_final = _dedupe_jobs(df_final)
        print(f"Merged with cache: {before} -> {len(df_final)} after dedupe")
    else:
        df_final = df_new

    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "wb") as handle:
        pickle.dump(df_final, handle)
    os.replace(tmp_path, cache_path)
    print(f"Updated {cache_path} with {len(df_final)} total jobs.")

    if args.no_supabase or not is_supabase_database_configured():
        print("Skipping Supabase sync.")
        return

    records = dataframe_to_job_records(df_new)
    synced = upsert_jobs(records)
    record_scrape_run(
        "completed",
        jobs_seen=synced,
        message="hiring.cafe scrape completed.",
    )
    print(f"Synced {synced} hiring.cafe jobs to Supabase.")


if __name__ == "__main__":
    main()
