"""Scrape USA + Canada on-site mining and trades jobs.

Primary volume comes from Indeed + ZipRecruiter + Google Jobs.
SaaS ATS boards are skipped by default — enable with SCRAPE_ATS=1 once mining
company lists are configured in config/ats_companies.json.
"""

from __future__ import annotations

from pathlib import Path
import os
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
jobspy_path = ROOT / "JobSpy"
if jobspy_path.exists():
    sys.path.insert(0, str(jobspy_path))

from ats_companies import patch_jobspy_company_lists  # noqa: E402
from ats_location import is_trades_job_row  # noqa: E402
from jobspy import scrape_jobs  # noqa: E402

# Core roles from product handoff + high-volume synonyms for board coverage.
TRADE_SEARCH_TERMS = (
    "Haul Truck Operator",
    "Mine Haul Truck",
    "Mine Equipment Operator",
    "Heavy Equipment Operator",
    "Dozer Operator",
    "Grader Operator",
    "Excavator Operator",
    "Loader Operator",
    "Wheel Loader Operator",
    "Open Pit Operator",
    "Surface Miner",
    "Underground Operator",
    "Underground Miner",
    "Underground Mining",
    "Shaft Miner",
    "Mine Operator",
    "Mining Operator",
    "Mill Operator",
    "Process Plant Operator",
    "Process Operator Mining",
    "Plant Operator Mining",
    "Crusher Operator",
    "Conveyor Operator",
    "Driller",
    "Drill Operator Mining",
    "Jumbo Operator",
    "Blast Operator",
    "Blaster Mining",
    "General Mine Laborer",
    "Mine Labourer",
    "Utility Worker Mining",
    "Construction Miner",
    "Construction Helper Mining",
    "Heavy Duty Mechanic",
    "Heavy Equipment Mechanic",
    "Mobile Equipment Mechanic",
    "Field Mechanic Mining",
    "Mine Mechanic",
    "Maintenance Mechanic Mining",
    "Millwright",
    "Industrial Millwright",
    "Mine Electrician",
    "Underground Electrician",
    "Underground Maintenance Electrician",
    "Industrial Electrician Mining",
    "Instrumentation Technician Mining",
    "Welder Mining",
    "Structural Welder",
    "Boilermaker Mining",
    "Pipefitter Mining",
    "Ironworker Mining",
    "Rigger Mining",
    "Assayer",
    "Safety Technician Mining",
    "Mine Safety",
    "Mine Geologist",
    "Mining Geologist",
    "FIFO Mining",
    "Fly In Fly Out Mining",
    "Camp Mining Jobs",
    # French-Canadian / Quebec volume
    "Opérateur camion minier",
    "Mineur souterrain",
    "Mécanicien équipements lourds",
)

ATS_SEARCH_TERMS = (
    "haul truck",
    "excavator",
    "underground miner",
    "mill operator",
    "millwright",
    "heavy duty mechanic",
    "electrician",
    "welder",
    "blaster",
    "mine geologist",
)

# Country-level sweeps (main volume).
INDEED_COUNTRIES = (
    ("Canada", "Canada"),
    ("USA", "United States"),
)

# Mining / industrial hubs — extra Indeed queries for denser local inventory.
INDEED_HUB_LOCATIONS = (
    ("Canada", "Timmins, ON"),
    ("Canada", "Sudbury, ON"),
    ("Canada", "Kirkland Lake, ON"),
    ("Canada", "Thunder Bay, ON"),
    ("Canada", "Red Lake, ON"),
    ("Canada", "Val-d'Or, QC"),
    ("Canada", "Rouyn-Noranda, QC"),
    ("Canada", "Sept-Îles, QC"),
    ("Canada", "Fort McMurray, AB"),
    ("Canada", "Edmonton, AB"),
    ("Canada", "Calgary, AB"),
    ("Canada", "Saskatoon, SK"),
    ("Canada", "Thompson, MB"),
    ("Canada", "Flin Flon, MB"),
    ("Canada", "Labrador City, NL"),
    ("Canada", "Yellowknife, NT"),
    ("Canada", "Kamloops, BC"),
    ("Canada", "Prince George, BC"),
    ("Canada", "Williams Lake, BC"),
    ("USA", "Elko, NV"),
    ("USA", "Winnemucca, NV"),
    ("USA", "Battle Mountain, NV"),
    ("USA", "Reno, NV"),
    ("USA", "Salt Lake City, UT"),
    ("USA", "Phoenix, AZ"),
    ("USA", "Tucson, AZ"),
    ("USA", "Morenci, AZ"),
    ("USA", "Denver, CO"),
    ("USA", "Boise, ID"),
    ("USA", "Coeur d'Alene, ID"),
    ("USA", "Spokane, WA"),
    ("USA", "Gillette, WY"),
    ("USA", "Casper, WY"),
    ("USA", "Butte, MT"),
    ("USA", "Hibbing, MN"),
    ("USA", "Marquette, MI"),
    ("USA", "Fairbanks, AK"),
    ("USA", "Anchorage, AK"),
)

# Shorter hub query set so regional sweeps stay fast but still fatten inventory.
HUB_SEARCH_TERMS = (
    "Haul Truck Operator",
    "Heavy Equipment Operator",
    "Underground Miner",
    "Mill Operator",
    "Heavy Duty Mechanic",
    "Millwright",
    "Mine Electrician",
    "Welder",
    "Mine Labourer",
    "Process Plant Operator",
    "FIFO Mining",
    "Boilermaker",
)

GOOGLE_QUERIES = (
    "haul truck operator jobs Canada",
    "haul truck operator jobs USA",
    "underground miner jobs Canada",
    "underground miner jobs USA",
    "heavy equipment operator mining jobs Canada",
    "heavy equipment operator mining jobs USA",
    "millwright mining jobs Canada",
    "millwright mining jobs USA",
    "heavy duty mechanic mine jobs Canada",
    "heavy duty mechanic mine jobs USA",
    "excavator operator mining jobs",
    "loader operator mining jobs",
    "mine electrician jobs Canada",
    "mine electrician jobs USA",
    "process plant operator mining jobs",
    "crusher operator jobs mining",
    "jumbo operator underground mining",
    "blaster mining jobs Canada",
    "mine geologist jobs Canada USA",
    "FIFO mining jobs Canada",
    "camp mining jobs Canada",
    "mill operator mining jobs",
    "open pit mining jobs USA",
    "boilermaker mining jobs Canada",
    "pipefitter mining jobs Canada USA",
    "mobile equipment mechanic mining jobs",
    "fly in fly out mining jobs Canada",
    "mining jobs Timmins Sudbury",
    "mining jobs Elko Nevada",
)

# Broad catch-alls — noisier raw results, title filter keeps niche roles.
CATCHALL_SEARCH_TERMS = (
    "mining jobs",
    "underground mining",
    "open pit mining",
    "FIFO mining camp",
    "heavy equipment mining",
    "trades mining site",
)

# Aim ~10k+ after filter/dedupe: high per-query caps + many role/location combos.
INDEED_RESULTS_PER_QUERY = int(os.getenv("INDEED_RESULTS_PER_QUERY", "800"))
INDEED_HUB_RESULTS_PER_QUERY = int(os.getenv("INDEED_HUB_RESULTS_PER_QUERY", "200"))
ZIP_RESULTS_PER_QUERY = int(os.getenv("ZIP_RESULTS_PER_QUERY", "400"))
ATS_RESULTS_WANTED = int(os.getenv("ATS_RESULTS_WANTED", "500"))
GOOGLE_RESULTS_WANTED = int(os.getenv("GOOGLE_RESULTS_WANTED", "300"))
SCRAPE_ATS = os.getenv("SCRAPE_ATS", "").strip().lower() in {"1", "true", "yes"}
SCRAPE_HUBS = os.getenv("SCRAPE_HUBS", "1").strip().lower() not in {"0", "false", "no"}
SCRAPE_ZIPRECRUITER = os.getenv("SCRAPE_ZIPRECRUITER", "").strip().lower() in {"1", "true", "yes"}
SCRAPE_CATCHALL = os.getenv("SCRAPE_CATCHALL", "1").strip().lower() not in {"0", "false", "no"}


def _dedupe_jobs(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    url_col = "job_url_direct" if "job_url_direct" in df.columns else "job_url"
    if url_col not in df.columns:
        return df
    df = df.copy()
    df[url_col] = df[url_col].astype(str).str.strip()
    df = df[df[url_col].notna() & (df[url_col] != "")]
    return df.drop_duplicates(subset=[url_col], keep="first")


def _filter_trades_jobs(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    def row_ok(row) -> bool:
        remote_flag = row.get("is_remote")
        if remote_flag is not False and remote_flag is not True:
            remote_flag = None
        return is_trades_job_row(
            site=str(row.get("site", "")),
            location=str(row.get("location", "")),
            title=str(row.get("title", "")),
            description=str(row.get("description", "") or ""),
            is_remote=remote_flag,
            company=str(row.get("company", "")),
        )

    before = len(df)
    filtered = df[df.apply(row_ok, axis=1)].copy()
    dropped = before - len(filtered)
    if dropped:
        print(f"Filtered {dropped} rows (non-trades, remote-only, or outside USA/Canada).")
    return filtered


def scrape_ats(search_term: str) -> pd.DataFrame:
    print(f"Scraping ATS boards for: {search_term}")
    frames: list[pd.DataFrame] = []
    for country, location in INDEED_COUNTRIES:
        try:
            df = scrape_jobs(
                site_name=["ashby", "greenhouse", "lever"],
                search_term=search_term,
                is_remote=False,
                country_indeed=country,
                location=location,
                results_wanted=ATS_RESULTS_WANTED,
                hours_old=336,
                linkedin_fetch_description=False,
            )
        except Exception as exc:
            print(f"  ATS {country} skipped ({exc})")
            continue
        if df is not None and not df.empty:
            print(f"  -> {len(df)} ATS jobs ({country})")
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def scrape_indeed_country() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(TRADE_SEARCH_TERMS) * len(INDEED_COUNTRIES)
    i = 0
    for country, location in INDEED_COUNTRIES:
        for term in TRADE_SEARCH_TERMS:
            i += 1
            print(f"Indeed {i}/{total}: {term} @ {country}")
            try:
                df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=term,
                    is_remote=False,
                    country_indeed=country,
                    location=location,
                    results_wanted=INDEED_RESULTS_PER_QUERY,
                    linkedin_fetch_description=False,
                )
            except Exception as exc:
                print(f"  skipped ({exc})")
                continue
            if df is not None and not df.empty:
                print(f"  -> {len(df)} jobs")
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def scrape_indeed_catchall() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(CATCHALL_SEARCH_TERMS) * len(INDEED_COUNTRIES)
    i = 0
    for country, location in INDEED_COUNTRIES:
        for term in CATCHALL_SEARCH_TERMS:
            i += 1
            print(f"Indeed catch-all {i}/{total}: {term} @ {country}")
            try:
                df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=term,
                    is_remote=False,
                    country_indeed=country,
                    location=location,
                    results_wanted=INDEED_RESULTS_PER_QUERY,
                    linkedin_fetch_description=False,
                )
            except Exception as exc:
                print(f"  skipped ({exc})")
                continue
            if df is not None and not df.empty:
                print(f"  -> {len(df)} jobs")
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def scrape_indeed_hubs() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(INDEED_HUB_LOCATIONS) * len(HUB_SEARCH_TERMS)
    i = 0
    for country, location in INDEED_HUB_LOCATIONS:
        for term in HUB_SEARCH_TERMS:
            i += 1
            print(f"Indeed hub {i}/{total}: {term} @ {location} ({country})")
            try:
                df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=term,
                    is_remote=False,
                    country_indeed=country,
                    location=location,
                    results_wanted=INDEED_HUB_RESULTS_PER_QUERY,
                    linkedin_fetch_description=False,
                )
            except Exception as exc:
                print(f"  skipped ({exc})")
                continue
            if df is not None and not df.empty:
                print(f"  -> {len(df)} jobs")
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def scrape_ziprecruiter() -> pd.DataFrame:
    """ZipRecruiter is strongest for US skilled trades / equipment roles."""
    frames: list[pd.DataFrame] = []
    # Prefer US + a Canada sweep; ZipRecruiter inventory is US-heavy.
    locations = (
        ("USA", "United States"),
        ("Canada", "Canada"),
    )
    terms = HUB_SEARCH_TERMS + (
        "Haul Truck Operator",
        "Underground Miner",
        "Heavy Equipment Mechanic",
        "Mine Electrician",
        "Process Plant Operator",
        "Mine Labourer",
    )
    # Dedupe while preserving order
    seen: set[str] = set()
    unique_terms: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_terms.append(term)

    total = len(unique_terms) * len(locations)
    i = 0
    for country, location in locations:
        for term in unique_terms:
            i += 1
            print(f"ZipRecruiter {i}/{total}: {term} @ {location} ({country})")
            try:
                df = scrape_jobs(
                    site_name=["zip_recruiter"],
                    search_term=term,
                    is_remote=False,
                    country_indeed=country,
                    location=location,
                    results_wanted=ZIP_RESULTS_PER_QUERY,
                    linkedin_fetch_description=False,
                )
            except Exception as exc:
                print(f"  skipped ({exc})")
                continue
            if df is not None and not df.empty:
                print(f"  -> {len(df)} jobs")
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def scrape_google() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for query in GOOGLE_QUERIES:
        print(f"Google Jobs: {query}")
        try:
            df = scrape_jobs(
                site_name=["google"],
                google_search_term=query,
                results_wanted=GOOGLE_RESULTS_WANTED,
                linkedin_fetch_description=False,
            )
        except Exception as exc:
            print(f"  skipped ({exc})")
            continue
        if df is not None and not df.empty:
            print(f"  -> {len(df)} Google jobs")
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def scrape_all(keyword: str = "mining") -> pd.DataFrame:
    del keyword
    patch_jobspy_company_lists()

    parts: list[pd.DataFrame] = []

    # Indeed first — this is where nearly all real trades volume comes from.
    print("=== Indeed country-wide sweep ===")
    parts.append(scrape_indeed_country())

    if SCRAPE_CATCHALL:
        print("=== Indeed catch-all mining sweep ===")
        parts.append(scrape_indeed_catchall())

    if SCRAPE_HUBS:
        print("=== Indeed mining-hub sweep ===")
        parts.append(scrape_indeed_hubs())

    if SCRAPE_ZIPRECRUITER:
        print("=== ZipRecruiter ===")
        parts.append(scrape_ziprecruiter())
    else:
        print("Skipping ZipRecruiter (set SCRAPE_ZIPRECRUITER=1 to enable).")

    print("=== Google Jobs ===")
    parts.append(scrape_google())

    if SCRAPE_ATS:
        print("=== ATS boards (optional) ===")
        for ats_term in ATS_SEARCH_TERMS:
            parts.append(scrape_ats(ats_term))
    else:
        print("Skipping ATS boards (set SCRAPE_ATS=1 to enable).")

    frames = [d for d in parts if d is not None and not d.empty]
    if not frames:
        print("No jobs scraped.")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    print(f"Combined before filter/dedupe: {len(df)}")
    df = _filter_trades_jobs(df)
    df = _dedupe_jobs(df)

    print("NUMBER OF JOBS:")
    print(len(df))
    if not df.empty and "site" in df.columns:
        print(df["site"].value_counts().to_string())
    return df
