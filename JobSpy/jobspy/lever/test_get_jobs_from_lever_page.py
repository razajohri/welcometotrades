import json
import requests
from bs4 import BeautifulSoup


def print_job_locations_and_remote(company_url: str):
    response = requests.get(company_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    jobs = soup.find_all("div", class_="posting")
    for job in jobs:
        title = job.find("h5").get_text(strip=True) if job.find("h5") else ""
        location = job.find("span", class_="sort-by-location").get_text(strip=True) if job.find("span", class_="sort-by-location") else ""
        # Check for remote in location or in tags/categories
        is_remote = "remote" in location.lower()
        # Check for remote in posting-categories or posting-tags
        categories = job.find_all("span", class_="posting-category")
        tags = job.find_all("span", class_="posting-tag")
        for cat in categories + tags:
            if "remote" in cat.get_text(strip=True).lower():
                is_remote = True
        print(f"Title: {title}")
        print(f"Location: {location}")
        print(f"Remote: {'Yes' if is_remote else 'No'}")
        print("-" * 40)


url = "https://jobs.lever.co/wealthsimple"
names = [
    "wattpad",
    "pointclickcare",
    "wealthsimple",
    "docebo",
    "cority",
    "kabam",
    "fullscript",
    "janeapp"
]
print(f"Checking jobs for: {url}")
print_job_locations_and_remote(url)