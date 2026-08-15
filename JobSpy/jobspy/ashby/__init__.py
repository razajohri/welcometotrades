from __future__ import annotations

import json
import requests
from jobspy.model import Scraper, ScraperInput, Site, JobPost, Location, JobResponse, Country
from bs4 import BeautifulSoup
from jobspy.exception import LinkedInException
from jobspy.linkedin.constant import headers
from jobspy.linkedin.util import (
    is_job_remote,
    job_type_code,
    parse_job_type,
    parse_job_level,
    parse_company_industry
)
from jobspy.model import (
    JobPost,
    Location,
    JobResponse,
    Country,
    Compensation,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    extract_emails_from_text,
    currency_parser,
    markdown_converter,
    plain_converter,
    create_session,
    remove_attributes,
    create_logger,
)

log = create_logger("Ashby")

class Ashby(Scraper):
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
            formatted_name = name.lower().replace(" ", "-").replace("_", "-").replace("--", "-")
            company_url = f"https://jobs.ashbyhq.com/{formatted_name}"
            formatted_names.append(company_url)
        return formatted_names


    @staticmethod
    def get_company_names() -> list[str]:
        names = [
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
            "trulioo"
        ]
        return names


    @staticmethod
    def fetch_job_posts(company_url: str) -> JobResponse:
        print(f"[Ashby] Scraping company URL: {company_url}")
        import json
        # Extract company slug from URL
        company_slug = company_url.split("jobs.ashbyhq.com/")[1]
        graphql_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": company_slug},
            "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {\n  jobBoard: jobBoardWithTeams(\n    organizationHostedJobsPageName: $organizationHostedJobsPageName\n  ) {\n    teams {\n      id\n      name\n      parentTeamId\n      __typename\n    }\n    jobPostings {\n      id\n      title\n      teamId\n      locationId\n      locationName\n      workplaceType\n      employmentType\n      secondaryLocations {\n        ...JobPostingSecondaryLocationParts\n        __typename\n      }\n      compensationTierSummary\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment JobPostingSecondaryLocationParts on JobPostingSecondaryLocation {\n  locationId\n  locationName\n  __typename\n}"
        }
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        response = requests.post(graphql_url, headers=headers, data=json.dumps(payload))
        if response.status_code != 200:
            print(f"Failed to fetch jobs from GraphQL API: {graphql_url}")
            print(f"Status code: {response.status_code}")
            print(response.text)
            return JobResponse(jobs=[])
        
        try:
            data = response.json()
        except Exception as e:
            print(f"[Ashby] Failed to parse JSON response for {company_url}: {e}")
            return JobResponse(jobs=[])
        
        job_board = data.get("data", {}).get("jobBoard") if data.get("data") else None
        if job_board is None:
            print(f"[Ashby] No job board found for {company_url} - company may not exist or API structure changed")
            return JobResponse(jobs=[])
        
        jobs = job_board.get("jobPostings", [])
        print(f"{company_url} shows {len(jobs)} job results.")
        job_posts = []
        for job in jobs:
            # Combine all string fields in job posting
            all_fields = []
            for k, v in job.items():
                if isinstance(v, str):
                    all_fields.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            for vk, vv in item.items():
                                if isinstance(vv, str):
                                    all_fields.append(vv)
            combined = " ".join(all_fields).lower()
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
                        for loc in Ashby.acceptable_locations
                        if loc != "remote"
                    )
                    return has_remote and has_canadian_location
            if is_canada_remote(
                combined,
                company_slug=company_slug,
                canadian_employers=canadian_employers,
            ):
                has_remote = "remote" in combined
                job_id = job.get("id", "")
                job_url = f"https://jobs.ashbyhq.com/{company_slug}/{job_id}"
                # Fetch job description from job page
                description = None
                try:
                    job_resp = requests.get(job_url, headers={"User-Agent": "Mozilla/5.0"})
                    soup = BeautifulSoup(job_resp.text, "html.parser")
                    desc_tag = soup.find("div", class_="posting-section__text")
                    if desc_tag:
                        description = desc_tag.get_text(strip=True)
                except Exception as e:
                    description = None
                # Build Location object
                location_str = job.get("locationName", "")
                location = Location(country=Country.CANADA if "canada" in location_str.lower() else location_str, city=None, state=None)
                job_post = JobPost(
                    id=job_id,
                    title=job.get("title", ""),
                    company_name=company_slug,
                    job_url=job_url,
                        job_url_direct=job_url,
                    location=location,
                    description=description,
                    is_remote=has_remote
                )
                print(f"[Ashby] Found job: {job_post.title} | {job_post.location.display_location()} | {job_post.job_url}")
                job_posts.append(job_post)
        return JobResponse(jobs=job_posts)

    def __init__(self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None):
        super().__init__(Site.ASHBY, proxies=proxies)
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
