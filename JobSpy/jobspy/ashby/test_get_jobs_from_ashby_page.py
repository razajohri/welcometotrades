import requests
from bs4 import BeautifulSoup

def print_job_locations_and_remote(company_url: str):
    import json
    graphql_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": "1password"},
        "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {\n  jobBoard: jobBoardWithTeams(\n    organizationHostedJobsPageName: $organizationHostedJobsPageName\n  ) {\n    teams {\n      id\n      name\n      parentTeamId\n      __typename\n    }\n    jobPostings {\n      id\n      title\n      teamId\n      locationId\n      locationName\n      workplaceType\n      employmentType\n      secondaryLocations {\n        ...JobPostingSecondaryLocationParts\n        __typename\n      }\n      compensationTierSummary\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment JobPostingSecondaryLocationParts on JobPostingSecondaryLocation {\n  locationId\n  locationName\n  __typename\n}"
    }
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    response = requests.post(graphql_url, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        print(f"Failed to fetch jobs from GraphQL API: {graphql_url}")
        print(f"Status code: {response.status_code}")
        print(response.text)
        return
    data = response.json()
    print("--- DEBUG: Raw API response ---")
    print(json.dumps(data, indent=2))
    print("--- END DEBUG ---\n")
    job_board = data.get("data", {}).get("jobBoard", {})
    teams = job_board.get("teams", [])
    team_map = {team["id"]: team["name"] for team in teams}
    jobs = job_board.get("jobPostings", [])
    print(f"{graphql_url} shows {len(jobs)} job results.")
    for job in jobs:
        title = job.get("title", "")
        team_name = team_map.get(job.get("teamId", ""), "Unknown")
        location = job.get("locationName", "")
        url = f"https://jobs.ashbyhq.com/1password/{job.get('id', '')}"
        workplace_type = job.get("workplaceType") or ""
        is_remote = workplace_type.lower() == "remote" or "remote" in (location or "").lower()
        print(f"Team: {team_name}")
        print(f"Title: {title}")
        print(f"Location: {location}")
        print(f"Remote: {'Yes' if is_remote else 'No'}")
        print(f"URL: {url}")
        print("-" * 40)

url = "https://jobs.ashbyhq.com/1password"
print(f"Checking jobs for: {url}")
print_job_locations_and_remote(url)
