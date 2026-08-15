"""ATS company slugs for Canada-focused job scraping."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "ats_companies.json"

# Built-in slugs merged with config/ats_companies.json (deduped, order preserved).
_BUILTIN: dict[str, list[str]] = {
    "ashby": [
        "1password",
        "hopper",
        "shopify",
        "hotspexmedia",
        "hive.co",
        "cohere",
        "ramp",
        "evenup",
        "ashby",
        "deel",
        "quora",
        "pear",
        "stepful",
        "atob",
        "abridge",
        "candidhealth",
        "altura",
        "clearco",
        "trulioo",
        "clio",
        "neo-financial",
        "paper",
        "ada",
        "applyboard",
        "dialogue",
        "clearbanc",
        "clearco",
    ],
    "greenhouse": [
        "stackadapt",
        "levio",
        "criticalmass",
        "geotab",
        "momentumfinancialservicesgroup",
        "juullabs",
        "jobber",
        "tucows",
        "constellationsoftwareinc",
        "hootsuite",
        "vidyard",
        "lightspeedhq",
        "benevity",
        "blabuscanada",
        "workleap",
        "navigatrgroupinternal",
        "tribalscale",
        "capco",
        "d2l",
        "epicgames",
        "knak",
        "doordashcanada",
        "shakepay",
        "grafanalabs",
        "onrunning",
        "deepmind",
        "reddit",
        "workato",
        "affirm",
        "samsara",
        "wizinc",
        "clutch",
        "openfarminc",
        "freshbooks",
        "lightspeedhqdu",
        "quince",
        "life360",
        "leagueinc",
        "motive",
        "visiersolutionsinc",
        "ada18",
        "wayfair",
        "clio",
        "dialoguetechnology",
        "ecobee",
        "borrowell",
        "touchbistro",
        "tophatmonocle",
        "later",
        "koho",
        "coinsquare",
        "mindbridge",
        "wealthsimple",
    ],
    "lever": [
        "wattpad",
        "pointclickcare",
        "wealthsimple",
        "docebo",
        "cority",
        "kabam",
        "fullscript",
        "janeapp",
        "waveapps",
        "caseware",
        "sait",
        "trader",
        "super-com",
        "aipconnect",
        "enable",
        "appen",
        "rackspace",
        "brafton",
        "boxlunch",
        "sayari",
        "luxurypresence",
        "welocalize",
        "jobscan-2",
        "stackadapt",
        "waabi",
        "flex",
        "panopto",
        "teleport",
        "xero",
        "kong",
        "pigment",
        "ritual",
        "axiomzen",
        "flowfoundation",
        "owner",
        "clio",
        "dialogue",
        "touchbistro",
        "later",
        "koho",
        "applyboard",
        "ada",
        "hootsuite",
        "vidyard",
        "jobber",
        "geotab",
        "tucows",
        "freshbooks",
        "league",
        "motive",
        "shakepay",
        "borrowell",
        "ecobee",
        "d2l",
        "benevity",
        "lightspeed",
        "shopify",
        "coinberry",
        "neo-financial",
        "paper",
        "clearbanc",
        "clearco",
        "trulioo",
        "1password",
        "hopper",
        "cohere",
    ],
}


def _load_json_slugs() -> dict[str, list[str]]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for site in ("ashby", "greenhouse", "lever"):
        raw = data.get(site, [])
        if isinstance(raw, list):
            out[site] = [str(x).strip() for x in raw if str(x).strip()]
    return out


def _merge_lists(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for items in lists:
        for item in items:
            key = item.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item.strip())
    return merged


def _lever_json_names() -> list[str]:
    """Optional extra Lever slugs from JobSpy's Canadian company seed file."""
    path = ROOT / "JobSpy" / "jobspy" / "lever" / "200_largest_canadian.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("data", [])
    except (OSError, json.JSONDecodeError):
        return []
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name"):
            slug = str(entry["name"]).lower()
            slug = slug.replace(" ", "").replace("-", "").replace("_", "")
            names.append(slug)
    return names


def get_company_slugs(site: str) -> list[str]:
    site = site.lower().strip()
    builtin = list(_BUILTIN.get(site, []))
    configured = _load_json_slugs().get(site, [])
    if site == "lever":
        return _merge_lists(builtin, configured, _lever_json_names())
    return _merge_lists(builtin, configured)


def get_canadian_employer_slugs() -> set[str]:
    slugs: set[str] = set()
    for site in ("ashby", "greenhouse", "lever"):
        for name in get_company_slugs(site):
            slugs.add(name.lower().strip())
    return slugs


def patch_jobspy_company_lists() -> None:
    """Point JobSpy ATS scrapers at expanded company slug lists."""
    os.environ.setdefault("FIND_JOBS_ROOT", str(ROOT))

    from jobspy.ashby import Ashby
    from jobspy.greenhouse import Greenhouse
    from jobspy.lever import Lever

    Ashby.get_company_names = staticmethod(lambda: get_company_slugs("ashby"))  # type: ignore[method-assign]
    Greenhouse.get_company_names = staticmethod(lambda: get_company_slugs("greenhouse"))  # type: ignore[method-assign]
    Lever.get_company_names = staticmethod(lambda: get_company_slugs("lever"))  # type: ignore[method-assign]
