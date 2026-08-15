import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import pickle
from scraper import scrape_all
from data_store import dataframe_to_job_records, is_supabase_database_configured, record_scrape_run, upsert_jobs

def _prefer_direct_urls(df):
    if df is None or df.empty:
        return df
    if "job_url_direct" in df.columns and "job_url" in df.columns:
        df["job_url_direct"] = df["job_url_direct"].where(
            df["job_url_direct"].notna() & (df["job_url_direct"] != ""),
            df["job_url"],
        )
    # Drop rows with no apply URL at all.
    if "job_url_direct" in df.columns:
        df = df[df["job_url_direct"].notna() & (df["job_url_direct"].astype(str).str.strip() != "")]
    return df

def main():
    print("Scraping jobs and updating cache...")
    df = scrape_all(" ")
    df = _prefer_direct_urls(df)
    # Write jobs_cache.pkl to the project root (same as app.root_path)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    final_path = os.path.join(base_dir, 'jobs_cache.pkl')
    tmp_path = final_path + '.tmp'
    try:
        # Write to a temp file first
        with open(tmp_path, 'wb') as f:
            pickle.dump(df, f)
        # Atomically replace the final cache file
        os.replace(tmp_path, final_path)
        print(f"{final_path} updated atomically with {len(df)} jobs.")

        if is_supabase_database_configured():
            records = dataframe_to_job_records(df)
            inserted = upsert_jobs(records)
            record_scrape_run("completed", jobs_seen=inserted, message="Cache refresh and Supabase sync completed.")
            print(f"Synced {inserted} jobs to Supabase.")
            print("Validating apply links (removes expired listings)...")
            import subprocess
            validate_script = os.path.join(base_dir, "scripts", "validate_job_links.py")
            subprocess.run(
                [sys.executable, validate_script, "--workers", "12", "--prune-unknown-aggregators"],
                check=False,
            )
        else:
            print("Supabase is not configured. Skipping database sync.")
    except Exception as e:
        # Cleanup temp file on error and re-raise
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        if is_supabase_database_configured():
            record_scrape_run("failed", jobs_seen=0, message=str(e))
        raise

if __name__ == "__main__":
    main()
