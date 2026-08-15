"""SEO metadata and sitemap configuration for Welcome to Trades."""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

SITE_NAME = "Welcome to Trades"
DEFAULT_OG_IMAGE_PATH = "/static/og-image.jpg"
OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
SUPPORT_EMAIL = "hello@welcometotrades.com"
TIKTOK_URL = "https://www.tiktok.com/@rigtimmins"
TIKTOK_HANDLE = "@rigtimmins"

DEFAULT_DESCRIPTION = (
    "Find on-site mining and trades jobs across the USA and Canada — "
    "haul truck operators, underground miners, millwrights, electricians, and more. "
    "Updated listings for skilled trades workers."
)

HOMEPAGE_FAQ: list[dict[str, str]] = [
    {
        "question": "What jobs does Welcome to Trades list?",
        "answer": (
            "We focus on mining and heavy trades roles: haul truck, dozer, excavator, "
            "underground miner, mill and plant operators, drillers, blasters, mechanics, "
            "millwrights, electricians, welders, safety techs, geologists, and related site jobs."
        ),
    },
    {
        "question": "Are these remote jobs?",
        "answer": (
            "No. Welcome to Trades is built for on-site mine, plant, and construction work "
            "in the United States and Canada — including camp and FIFO-style roles where listed."
        ),
    },
    {
        "question": "Which locations are covered?",
        "answer": (
            "USA and Canada. Use the city filter to narrow results to places like Timmins, "
            "Sudbury, Elko, or other mining towns when those cities appear in listings."
        ),
    },
    {
        "question": "Is Welcome to Trades free?",
        "answer": (
            "Yes for launch — browse and search listings free. Paid plans may come later."
        ),
    },
    {
        "question": "How often are jobs updated?",
        "answer": (
            "Listings are refreshed regularly from public job boards and company career pages "
            "for mining and trades roles across the US and Canada."
        ),
    },
    {
        "question": "Where can I follow hiring tips and site updates?",
        "answer": (
            f"Follow {TIKTOK_HANDLE} on TikTok for mining and trades content, then use "
            "welcometotrades.com to search open roles."
        ),
    },
    {
        "question": "What if a job link is broken or expired?",
        "answer": (
            "Mining postings change quickly. Contact us via the site form or email "
            f"{SUPPORT_EMAIL} with the job title and company — we will update or remove it."
        ),
    },
]

PAGE_SEO: dict[str, dict[str, str]] = {
    "root": {
        "title": "Welcome to Trades — Mining & Trades Jobs in the USA and Canada",
        "description": DEFAULT_DESCRIPTION,
        "robots": "index, follow",
    },
    "support": {
        "title": "Support — Welcome to Trades",
        "description": "Get help with Welcome to Trades — mining and trades job search support.",
        "robots": "index, follow",
    },
    "privacy": {
        "title": "Privacy Policy — Welcome to Trades",
        "description": "How Welcome to Trades collects, uses, and protects your personal information.",
        "robots": "index, follow",
    },
    "terms": {
        "title": "Terms of Service — Welcome to Trades",
        "description": "Terms of Service for Welcome to Trades.",
        "robots": "index, follow",
    },
    "lifetime_access": {
        "title": "Get Access — Welcome to Trades",
        "description": "Access mining and trades job search on Welcome to Trades.",
        "robots": "index, follow",
    },
    "guides_remote_jobs_canada": {
        "title": "Mining Jobs Guide — Welcome to Trades",
        "description": "How to find on-site mining and trades jobs in the USA and Canada.",
        "robots": "index, follow",
    },
    "post_a_job": {
        "title": "Post a Trades Job — Welcome to Trades",
        "description": "Post a mining or trades job on Welcome to Trades.",
        "robots": "index, follow",
    },
    "login": {"title": "Sign In — Welcome to Trades", "description": "Sign in to Welcome to Trades.", "robots": "noindex, follow"},
    "register": {"title": "Create Account — Welcome to Trades", "description": "Create your Welcome to Trades account.", "robots": "noindex, follow"},
    "subscribe": {"title": "Plans — Welcome to Trades", "description": "Welcome to Trades access plans.", "robots": "noindex, follow"},
    "access": {"title": "Get Access — Welcome to Trades", "description": "Start searching mining and trades jobs.", "robots": "noindex, follow"},
    "account": {"title": "Your Account — Welcome to Trades", "description": "Manage your Welcome to Trades account.", "robots": "noindex, follow"},
    "subscription_success": {"title": "Payment — Welcome to Trades", "description": "Payment confirmation.", "robots": "noindex, follow"},
    "index": {
        "title": "Job Search — Welcome to Trades",
        "description": "Search on-site mining and trades jobs in the USA and Canada.",
        "robots": "index, follow",
    },
}

SITEMAP_PATHS: list[tuple[str, str]] = [
    ("/", "weekly"),
    ("/search", "daily"),
    ("/guides/remote-jobs-canada", "monthly"),
    ("/post-a-job", "monthly"),
    ("/support", "monthly"),
    ("/privacy", "yearly"),
    ("/terms", "yearly"),
]

ROBOTS_DISALLOW_PATHS = (
    "/account", "/login", "/register", "/subscribe",
    "/subscription_success", "/access", "/webhook",
)


def canonical_host() -> str:
    return os.getenv("CANONICAL_HOST", "www.welcometotrades.com").lower()


def site_base_url() -> str:
    return f"https://{canonical_host()}"


def ga4_measurement_id() -> str:
    return os.getenv("GA4_MEASUREMENT_ID", "").strip()


def google_site_verification() -> str:
    return os.getenv("GOOGLE_SITE_VERIFICATION", "").strip()


def clarity_project_id() -> str:
    return os.getenv("CLARITY_PROJECT_ID", "").strip()


def homepage_faq_items() -> list[dict[str, str]]:
    return HOMEPAGE_FAQ


def build_organization_schema() -> dict[str, Any]:
    base_url = site_base_url()
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": f"{base_url}/",
        "logo": {"@type": "ImageObject", "url": f"{base_url}/static/logo.png", "width": 512, "height": 512},
        "image": f"{base_url}{DEFAULT_OG_IMAGE_PATH}",
        "email": SUPPORT_EMAIL,
        "description": DEFAULT_DESCRIPTION,
        "areaServed": [
            {"@type": "Country", "name": "United States"},
            {"@type": "Country", "name": "Canada"},
        ],
        "sameAs": [TIKTOK_URL],
    }


def build_website_schema() -> dict[str, Any]:
    base_url = site_base_url()
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": f"{base_url}/",
        "description": DEFAULT_DESCRIPTION,
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "logo": {"@type": "ImageObject", "url": f"{base_url}/static/logo.png"},
        },
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{base_url}/search",
            "query-input": "required name=search_term_string",
        },
    }


def build_faq_schema(items: list[dict[str, str]] | None = None) -> dict[str, Any]:
    faq_items = items if items is not None else HOMEPAGE_FAQ
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in faq_items
        ],
    }


def page_seo(endpoint: str) -> dict[str, str]:
    return dict(PAGE_SEO.get(endpoint, PAGE_SEO["root"]))


def get_page_seo(endpoint: str | None, path: str = "/") -> dict[str, str]:
    meta = PAGE_SEO.get(endpoint or "", PAGE_SEO["root"])
    base = site_base_url()
    canonical_path = path if path != "" else "/"
    if not canonical_path.startswith("/"):
        canonical_path = f"/{canonical_path}"
    canonical = base + (canonical_path if canonical_path != "/" else "/")
    return {
        "title": meta.get("title", SITE_NAME),
        "description": meta.get("description", DEFAULT_DESCRIPTION),
        "robots": meta.get("robots", "index, follow"),
        "canonical": meta.get("canonical", canonical),
        "og_image": base + DEFAULT_OG_IMAGE_PATH,
    }


def schema_json(schema: dict[str, Any] | list[Any]) -> str:
    return json.dumps(schema, ensure_ascii=False)


def build_robots_txt() -> str:
    host = site_base_url()
    lines = ["User-agent: *", "Allow: /"]
    for path in ROBOTS_DISALLOW_PATHS:
        lines.append(f"Disallow: {path}")
    lines.append(f"Sitemap: {host}/sitemap.xml")
    return "\n".join(lines) + "\n"


def build_sitemap_xml() -> str:
    host = site_base_url()
    today = date.today().isoformat()
    urls = []
    for path, freq in SITEMAP_PATHS:
        urls.append(
            "  <url>\n"
            f"    <loc>{host}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def json_ld(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False)
