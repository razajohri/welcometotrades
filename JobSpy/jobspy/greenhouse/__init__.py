from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from jobspy.model import Scraper, ScraperInput, Site, JobPost, Location, JobResponse
from jobspy.util import create_logger

log = create_logger("Greenhouse")

class Greenhouse(Scraper):
    acceptable_locations = [
        "canada", "remote",
        "ontario", "quebec", "british columbia",
        "alberta", "manitoba", "saskatchewan", "nova scotia", "new brunswick",
        "newfoundland and labrador", "prince edward island", "yukon", "northwest territories", "nunavut",
        # Canadian cities larger than Edmonton
        "toronto", "montreal", "calgary", "vancouver", "edmonton"
    ]

    @staticmethod
    def format_company_name_list(names: list[str]) -> list[str]:
        formatted_names = []
        for name in names:
            formatted_name = name.lower().replace(" ", "").replace("_", "").replace("--", "-")
            company_url = f"https://boards.greenhouse.io/{formatted_name}"
            formatted_names.append(company_url)
        return formatted_names

    @staticmethod
    def get_company_names() -> list[str]:
        names = [
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
            "wayfair"
        ]
        return names

    @staticmethod
    def fetch_job_posts(company_url: str) -> JobResponse:
        print(f"[Greenhouse] Scraping company URL: {company_url}")
        try:
            response = requests.get(company_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if response.status_code != 200:
                print(f"[Greenhouse] Failed to fetch {company_url} - Status code: {response.status_code}")
                return JobResponse(jobs=[])
        except Exception as e:
            print(f"[Greenhouse] Error fetching {company_url}: {e}")
            return JobResponse(jobs=[])
        
        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            print(f"[Greenhouse] Failed to parse HTML for {company_url}: {e}")
            return JobResponse(jobs=[])
        
        jobs = soup.find_all("tr", class_="job-post")
        print(f"{company_url} shows {len(jobs)} job results.")
        if not jobs:
            print(f"[Greenhouse] No jobs found for {company_url} - company may not exist or page structure changed")
        
        job_posts = []
        company_slug = company_url.split("boards.greenhouse.io/")[-1].split("/")[0]
        try:
            from ats_companies import get_canadian_employer_slugs
            from ats_location import is_canada_remote
            canadian_employers = get_canadian_employer_slugs()
        except ImportError:
            canadian_employers = set()
            def is_canada_remote(text, company_slug=None, canadian_employers=None):
                text_l = (text or "").lower()
                has_remote = "remote" in text_l
                has_canadian_location = any(
                    loc in text_l
                    for loc in Greenhouse.acceptable_locations
                    if loc != "remote"
                )
                return has_remote and has_canadian_location
        for job in jobs:
            a_tag = job.find("a")
            if a_tag:
                p_tags = a_tag.find_all("p")
                title = p_tags[0].get_text(strip=True) if len(p_tags) > 0 else ""
                location_str = p_tags[1].get_text(strip=True) if len(p_tags) > 1 else ""
                combined = f"{title} {location_str}"
                if is_canada_remote(
                    combined,
                    company_slug=company_slug,
                    canadian_employers=canadian_employers,
                ):
                    has_remote = "remote" in combined.lower()
                    job_url = a_tag["href"] if a_tag.has_attr("href") else company_url
                    # Fetch job description from job page
                    description = None
                    try:
                        job_resp = requests.get(job_url, headers={"User-Agent": "Mozilla/5.0"})
                        job_soup = BeautifulSoup(job_resp.text, "html.parser")
                        desc_tag = job_soup.find("div", class_="content")
                        if desc_tag:
                            description = desc_tag.get_text(strip=True)
                    except Exception as e:
                        description = None
                    location = Location(country=location_str, city=None, state=None)
                    job_post = JobPost(
                        id=None,
                        title=title,
                        company_name=company_slug,
                        job_url=job_url,
                            job_url_direct=job_url,
                        location=location,
                        description=description,
                        is_remote=has_remote
                    )
                    print(f"[Greenhouse] Found job: {job_post.title} | {job_post.location.display_location()} | {job_post.job_url}")
                    job_posts.append(job_post)
        return JobResponse(jobs=job_posts)

    def __init__(self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None):
        super().__init__(Site.GREENHOUSE, proxies=proxies)
        self.session = requests.Session()
        self.scraper_input = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        company_names = self.get_company_names()
        company_urls = self.format_company_name_list(company_names)
        all_job_posts = []
        for url in company_urls:
            job_response = self.fetch_job_posts(url)
            all_job_posts.extend(job_response.jobs)
        return JobResponse(jobs=all_job_posts)

    # Method stubs for completeness
    def _scrape_page(self, *args, **kwargs):
        pass

    def _build_filters(self):
        pass

    def _process_job(self, *args, **kwargs):
        pass

jobs_found = []
no_jobs_found = []
company_job_counts = {}
