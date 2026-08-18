"""USA + Canada on-site location helpers for mining / trades jobs."""

from __future__ import annotations

import re
from typing import Any

TRADE_ROLE_TERMS: tuple[str, ...] = (
    "haul truck", "haul truck operator", "mine equipment", "equipment operator",
    "dozer operator", "dozer", "grader operator", "grader", "excavator operator",
    "excavator", "loader operator", "loader", "underground operator",
    "underground miner", "underground mine", "mine operator", "mill operator",
    "process plant", "plant operator", "crusher operator", "crusher",
    "conveyor operator", "conveyor", "driller", "drill operator", "jumbo operator",
    "jumbo", "blast operator", "blaster", "blasting", "mine laborer", "mine labourer",
    "general laborer", "general labourer", "utility worker", "construction miner",
    "construction helper", "heavy duty mechanic", "heavy-duty mechanic", "hd mechanic",
    "millwright", "electrician", "underground electrician", "maintenance electrician",
    "welder", "welding", "assayer", "assay", "safety technician", "safety tech",
    "mine geologist", "mining geologist", "geologist", "mechanic", "miner", "mining",
)

REMOTE_ONLY_MARKERS = (
    "fully remote", "100% remote", "work from home", "work-from-home", "wfh",
    "remote only", "remote-only", "remote position", "remote role", "remote job",
    "telecommute", "anywhere in the world", "work from anywhere",
)

FOREIGN_COUNTRY_MARKERS = (
    "united kingdom", " australia", " new zealand", " germany", " france", " india",
    " philippines", " mexico", " brazil", " south africa", " chile", " peru",
    " poland", " singapore", " ireland", " dubai", " uae",
)

CANADA_LOCATION_TERMS = (
    "canada", "canadian", "ontario", "quebec", "british columbia", "alberta",
    "manitoba", "saskatchewan", "nova scotia", "new brunswick", "newfoundland",
    "prince edward island", "yukon", "northwest territories", "nunavut",
    "timmins", "sudbury", "thunder bay", "red lake", "kirkland lake", "val-d'or",
    "val dor", "rouyn-noranda", "sept-iles", "labrador city", "fort mcmurray",
    "calgary", "edmonton", "vancouver", "kamloops", "prince george", "saskatoon",
    "regina", "winnipeg", "toronto", "ottawa", "montreal", "halifax",
)

CANADA_PROVINCE_CODES = ("on", "qc", "bc", "ab", "mb", "sk", "ns", "nb", "nl", "pe", "yt", "nt", "nu")

US_LOCATION_TERMS = (
    "united states", "usa", "u.s.", "u.s.a", "alaska", "arizona", "california",
    "colorado", "florida", "idaho", "illinois", "kentucky", "louisiana", "michigan",
    "minnesota", "missouri", "montana", "nevada", "new mexico", "north dakota",
    "ohio", "oklahoma", "oregon", "pennsylvania", "south dakota", "texas", "utah",
    "washington", "west virginia", "wyoming", "elko", "winnemucca", "reno", "denver",
    "phoenix", "tucson", "salt lake", "boise", "spokane", "casper", "gillette",
    "hibbing", "marquette", "butte", "fairbanks", "anchorage",
)

US_STATE_CODES = (
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
    "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
    "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
    "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
)

_INDEED_PROVINCE_COUNTRY = re.compile(
    r",\s*(bc|on|qc|ab|mb|sk|ns|nb|nl|pe|yt|nt|nu)\s*,\s*ca\s*$", re.I,
)
_INDEED_STATE_COUNTRY = re.compile(
    r",\s*([A-Z]{2})\s*,?\s*(usa|us|united states)?\s*$", re.I,
)
_CITY_SPLIT = re.compile(r"[,/|•]+")
_CITY_JUNK_PREFIXES = frozenset(
    {
        "remote",
        "hybrid",
        "onsite",
        "on-site",
        "on site",
        "anywhere",
        "nationwide",
        "multiple locations",
        "various",
        "various locations",
        "united states",
        "usa",
        "canada",
        "north america",
    }
)
_REGION_CODES = frozenset(CANADA_PROVINCE_CODES + US_STATE_CODES + ("dc",))
_REGION_NAMES = frozenset(
    {
        "ontario",
        "quebec",
        "québec",
        "british columbia",
        "alberta",
        "manitoba",
        "saskatchewan",
        "nova scotia",
        "new brunswick",
        "newfoundland",
        "newfoundland and labrador",
        "prince edward island",
        "yukon",
        "northwest territories",
        "nunavut",
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
        "district of columbia",
    }
)
_COUNTRY_NAMES = frozenset({"canada", "ca", "usa", "us", "u.s.", "u.s.a.", "united states", "remote"})


def _strip_trailing_region(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    tokens = text.rsplit(None, 1)
    if len(tokens) == 2 and tokens[1].lower().rstrip(".") in _REGION_CODES:
        return tokens[0].strip(" -")
    lowered = text.lower()
    for name in sorted(_REGION_NAMES, key=len, reverse=True):
        suffix = f" {name}"
        if lowered.endswith(suffix):
            return text[: -len(suffix)].strip(" -")
    return text


def extract_city(location: str) -> str:
    loc = (location or "").strip()
    if not loc:
        return ""
    if loc.lower() in _COUNTRY_NAMES:
        return ""

    if "," in loc:
        parts = [p.strip() for p in loc.split(",") if p.strip()]
    else:
        parts = [p.strip() for p in _CITY_SPLIT.split(loc) if p.strip()]
    if not parts:
        return ""

    city = parts[0]
    if city.lower() in _CITY_JUNK_PREFIXES and len(parts) > 1:
        city = parts[1]
        parts = parts[1:]
    raw_city = city
    city = _strip_trailing_region(city)
    if not city:
        return ""

    lowered = city.lower()
    remaining = [p.lower().strip() for p in parts[1:] if p.strip()]
    had_region_suffix = city.casefold() != raw_city.strip().casefold()
    remaining_has_code = any(p.rstrip(".") in _REGION_CODES for p in remaining)
    region_only = lowered in _REGION_NAMES or lowered in _REGION_CODES
    if region_only and not had_region_suffix and not remaining_has_code:
        return ""
    if lowered in _CITY_JUNK_PREFIXES or lowered in _COUNTRY_NAMES:
        return ""
    if len(city) < 2 or len(city) > 40:
        return ""
    if city.isupper() and len(city) > 3:
        city = city.title()
    return city


def city_matches(location: str, city_filter: str) -> bool:
    needle = (city_filter or "").strip().lower()
    if not needle:
        return True
    return needle in (location or "").lower()


def collect_cities(rows: list[dict[str, Any]], *, limit: int = 0) -> list[str]:
    labels_by_key: dict[str, str] = {}
    for row in rows:
        city = extract_city(str(row.get("location") or ""))
        if not city:
            continue
        key = city.lower()
        if key not in labels_by_key:
            labels_by_key[key] = city

    names = sorted(labels_by_key.values(), key=str.casefold)
    if limit and len(names) > limit:
        return names[:limit]
    return names


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _contains_term(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if " " in term:
        return term in text
    if len(term) <= 3:
        return bool(re.search(rf"\b{re.escape(term)}\b", text, re.I))
    return term in text


def is_trade_role_title(title: str) -> bool:
    text = (title or "").lower()
    return bool(text) and _contains_any(text, TRADE_ROLE_TERMS)


def looks_remote_only(text: str, *, is_remote: bool | None = None) -> bool:
    lowered = (text or "").lower()
    if is_remote is True and not any(
        marker in lowered for marker in ("mine", "mining", "camp", "fly-in", "fifo", "site")
    ):
        return True
    return _contains_any(lowered, REMOTE_ONLY_MARKERS)


def is_us_or_canada_location(location: str, combined: str | None = None) -> bool:
    loc = (location or "").strip().lower()
    text = (combined or loc).lower()

    if _contains_any(f" {text} ", FOREIGN_COUNTRY_MARKERS):
        if not (
            "canada" in text
            or "united states" in text
            or re.search(r"\b(usa|u\.s\.a?)\b", text)
        ):
            return False

    if "canada" in loc or "canada" in text:
        return True
    if loc in ("ca", "canada") or _INDEED_PROVINCE_COUNTRY.search(loc):
        return True
    if any(_contains_term(loc, code) for code in CANADA_PROVINCE_CODES):
        return True
    if _contains_any(loc, CANADA_LOCATION_TERMS) or _contains_any(text, CANADA_LOCATION_TERMS):
        return True

    if "united states" in text or re.search(r"\b(usa|u\.s\.a?)\b", text):
        return True
    if _contains_any(loc, US_LOCATION_TERMS) or _contains_any(text, US_LOCATION_TERMS):
        return True

    state_match = _INDEED_STATE_COUNTRY.search(loc)
    if state_match and state_match.group(1).lower() in US_STATE_CODES:
        return True

    if loc in {"us", "usa", "u.s.", "u.s.a.", "united states"}:
        return True

    return False


def is_trades_job_row(
    *,
    site: str,
    location: str,
    title: str,
    description: str = "",
    is_remote: bool | None = None,
    company: str = "",
) -> bool:
    del site, company
    title_s = str(title or "")
    loc = str(location or "")
    desc = str(description or "")[:1500]
    combined = f"{title_s} {loc} {desc}".lower()

    if not is_trade_role_title(title_s):
        return False
    if looks_remote_only(combined, is_remote=is_remote):
        return False
    return is_us_or_canada_location(loc, combined)


def is_canada_remote(
    combined: str,
    *,
    company_slug: str | None = None,
    canadian_employers: set[str] | None = None,
    is_remote: bool | None = None,
) -> bool:
    """JobSpy ATS shim: keep on-site USA/Canada trades roles (not remote desk)."""
    del company_slug, canadian_employers
    text = (combined or "").lower().strip()
    if not text:
        return False
    if not _contains_any(text, TRADE_ROLE_TERMS):
        return False
    if looks_remote_only(text, is_remote=is_remote):
        return False
    return is_us_or_canada_location("", text)


# Backwards-compatible alias for older call sites during the port.
is_canada_job_row = is_trades_job_row
