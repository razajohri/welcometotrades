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
        company_url = f"https://job-boards.greenhouse.io/{formatted_name}"
        formatted_names.append(company_url)
    return formatted_names


def get_company_names() -> list[str]:
    names = []
    with open('companies.json', 'r') as f:
        data = json.load(f)
    for entry in data["data"]:
        if "name" in entry:
            names.append(entry["name"])
    return names 







def count_remote_canada_jobs(company_url: str) -> int:
    response = requests.get(company_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    openings = soup.find_all("tr", class_="job-post")
    if openings:
        print(f"{company_url} shows {len(openings)} job results.")
    else:
        print(f"{company_url} shows 0 job results.")
    count = 0
    for job in openings:
        a_tag = job.find("a")
        if a_tag:
            p_tags = a_tag.find_all("p")
            title = p_tags[0].get_text(strip=True) if len(p_tags) > 0 else ""
            location = p_tags[1].get_text(strip=True) if len(p_tags) > 1 else ""
            title_lower = title.lower()
            location_lower = location.lower()
            # Try to get description if available (not always present)
            description = ""
            desc_tag = job.find("td", class_="cell")
            if desc_tag:
                description = desc_tag.get_text(strip=True)
            description_lower = description.lower()
            is_remote = "remote" in location_lower
            has_acceptable_location = any(loc in location_lower for loc in acceptable_locations)
            # Count if location-based condition matches
            if is_remote and has_acceptable_location:
                count += 1
            # Count if 'canada' and 'remote' are in title or description
            elif ("canada" in title_lower and "remote" in title_lower) or ("canada" in description_lower and "remote" in description_lower):
                count += 1
    return count

company_names = get_company_names()
company_urls = format_company_name_list(company_names)

jobs_found = []
no_jobs_found = []
company_job_counts = {}


for url in company_urls:
    print(f"Checking jobs for: {url}")
    company_part = url.split("job-boards.greenhouse.io/")[1]
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