import json
import requests
from bs4 import BeautifulSoup

acceptable_locations = [
    "canada", "remote",
    "ontario", "quebec", "british columbia",
    "alberta", "manitoba", "saskatchewan", "nova scotia", "new brunswick",
    "newfoundland and labrador", "prince edward island", "yukon", "northwest territories", "nunavut",
    # Canadian cities larger than Edmonton
    "toronto", "montreal", "calgary", "vancouver", "edmonton"
]

def format_company_name_list(names: list[str]) -> list[str]:
    formatted_names = []
    for name in names:
        formatted_name = name.lower().replace(" ", "").replace("-", "").replace("_", "")
        company_url = f"https://jobs.lever.co/{formatted_name}"
        formatted_names.append(company_url)
    return formatted_names


def get_company_names() -> list[str]:
    names = []
    with open('200_largest_canadian.json', 'r') as f:
        data = json.load(f)
    for entry in data["data"]:
        if "name" in entry:
            names.append(entry["name"])
    return names 



def count_remote_canada_jobs(company_url: str) -> int:
    response = requests.get(company_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    count = 0
    for job in soup.find_all("div", class_="posting"):
        title = job.find("h5").get_text(strip=True) if job.find("h5") else ""
        location = job.find("span", class_="sort-by-location").get_text(strip=True) if job.find("span", class_="sort-by-location") else ""
        location_lower = location.lower()
        # Check for 'remote' in location or in posting-category/posting-tag
        is_remote = "remote" in location_lower
        categories = job.find_all("span", class_="posting-category")
        tags = job.find_all("span", class_="posting-tag")
        for cat in categories + tags:
            if "remote" in cat.get_text(strip=True).lower():
                is_remote = True
        # Check if any acceptable location is in location_lower
        has_acceptable_location = any(loc in location_lower for loc in acceptable_locations)
        if is_remote and has_acceptable_location:
            count += 1
    return count

company_names = get_company_names()
company_urls = format_company_name_list(company_names)

jobs_found = []
no_jobs_found = []
company_job_counts = {}

for url in company_urls:
    print(f"Checking jobs for: {url}")
    company_part = url.split("jobs.lever.co/")[1]
    job_count = count_remote_canada_jobs(url)
    if job_count > 0:
        print(f"{job_count} remote Canada jobs found for {url}")
        jobs_found.append(company_part)
        company_job_counts[company_part] = job_count
    else:
        print(f"No remote Canada jobs found for {url}")
        no_jobs_found.append(company_part)
    print("=" * 60)

print("Companies with remote Canada jobs found:")
for company, count in company_job_counts.items():
    print(f"{company}: {count}")
print("Companies with NO remote Canada jobs found:")
for company in no_jobs_found:
    print(company)