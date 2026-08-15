import os
import pickle

import pandas as pd
from flask import Blueprint, current_app, request

from data_store import (
    DEFAULT_LANDING_PREVIEW_CATEGORIES,
    _pick_best_landing_preview_row,
    filter_jobs_dataframe,
    is_supabase_database_configured,
    job_to_landing_preview,
    kickoff_job_search_cache_warm,
    preview_jobs,
    preview_jobs_default_landing,
)

bp = Blueprint("landing_search", __name__)


def preview_jobs_from_cache(keyword: str, filter_value: str, city: str = "") -> tuple[list[dict], int]:
    cache_path = os.path.join(current_app.root_path, "jobs_cache.pkl")
    if not os.path.exists(cache_path):
        return [], 0

    with open(cache_path, "rb") as file_handle:
        all_jobs_df = pickle.load(file_handle)

    results_df = filter_jobs_dataframe(all_jobs_df, keyword, filter_value, city=city)
    total = len(results_df)

    filter_label = (filter_value or "").strip() or None
    results = []
    for _, job in results_df.head(3).iterrows():
        results.append(job_to_landing_preview(job.to_dict(), category=filter_label))
    return results, total


def preview_jobs_default_from_cache() -> list[dict]:
    cache_path = os.path.join(current_app.root_path, "jobs_cache.pkl")
    if not os.path.exists(cache_path):
        return []

    with open(cache_path, "rb") as file_handle:
        all_jobs_df = pickle.load(file_handle)

    results: list[dict] = []
    for category in DEFAULT_LANDING_PREVIEW_CATEGORIES:
        category_df = filter_jobs_dataframe(all_jobs_df, "", category)
        if category_df.empty:
            continue
        rows = [row.to_dict() for _, row in category_df.head(25).iterrows()]
        best = _pick_best_landing_preview_row(rows, category) or rows[0]
        results.append(job_to_landing_preview(best, category=category))
    return results


def get_default_landing_preview() -> list[dict]:
    """Default job cards for the homepage (server-rendered for SEO)."""
    try:
        if is_supabase_database_configured():
            results = preview_jobs_default_landing()
            if results:
                return results
        return preview_jobs_default_from_cache()
    except Exception:
        return preview_jobs_default_from_cache()


@bp.route("/landing-search", methods=["POST"])
def landing_search():
    kickoff_job_search_cache_warm()
    payload = request.get_json(silent=True) or {}
    keyword = payload.get("keyword", "").strip()
    filter_value = (payload.get("filter") or "").strip()
    city = (payload.get("city") or "").strip()

    try:
        if is_supabase_database_configured():
            results, total = preview_jobs(keyword, filter_value, city=city)
        else:
            results, total = preview_jobs_from_cache(keyword, filter_value, city=city)
        return {"results": results, "total": total}
    except Exception:
        results, total = preview_jobs_from_cache(keyword, filter_value, city=city)
        return {"results": results, "total": total}


@bp.route("/landing-search/default", methods=["GET"])
def landing_search_default():
    kickoff_job_search_cache_warm()
    try:
        if is_supabase_database_configured():
            results = preview_jobs_default_landing()
            if results:
                return {"results": results}
        return {"results": preview_jobs_default_from_cache()}
    except Exception:
        return {"results": preview_jobs_default_from_cache()}
