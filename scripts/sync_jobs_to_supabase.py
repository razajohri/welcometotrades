import os
import pickle
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_store import dataframe_to_job_records, is_supabase_database_configured, record_scrape_run, upsert_jobs


def main() -> None:
    if not is_supabase_database_configured():
        raise RuntimeError("Supabase database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(base_dir, "jobs_cache.pkl")
    if not os.path.exists(cache_path):
        raise FileNotFoundError(f"Job cache not found at {cache_path}")

    with open(cache_path, "rb") as file_handle:
        df = pickle.load(file_handle)

    records = dataframe_to_job_records(df)
    synced = upsert_jobs(records)
    record_scrape_run("completed", jobs_seen=synced, message="Existing pickle cache synced to Supabase.")
    print(f"Synced {synced} jobs from jobs_cache.pkl to Supabase.")


if __name__ == "__main__":
    main()
