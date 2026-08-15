import json
import requests
from bs4 import BeautifulSoup




def print_job_locations_and_remote(company_url: str):
    response = requests.get(company_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = soup.find_all("tr", class_="job-post")
    print(f"{company_url} shows {len(jobs)} job results.")
    for job in jobs:
        a_tag = job.find("a")
        if a_tag:
            p_tags = a_tag.find_all("p")
            title = p_tags[0].get_text(strip=True) if len(p_tags) > 0 else ""
            location = p_tags[1].get_text(strip=True) if len(p_tags) > 1 else ""
            is_remote = "remote" in location.lower()
            print(f"Title: {title}")
            print(f"Location: {location}")
            print(f"Remote: {'Yes' if is_remote else 'No'}")
            print("-" * 40)



url = b"https://job-boards.greenhouse.io/atomiccartoons"
names = [
    "stackadapt",
    "levio",
    "criticalmass",
    "geotab",
    "momentumfinancialservicesgroup",
    "juullabs",
    "jobber",
    "tucows"
]
print(f"Checking jobs for: {url}")
print_job_locations_and_remote(url)