# Weekly job scrape + link validation for find_jobs_canada
# Schedule: Task Scheduler -> weekly, run this script with highest privileges optional.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "venv not found. Run: python -m venv venv && .\venv\Scripts\pip install -r requirements.txt"
}

Set-Location $Root
& $Python scripts\update_jobs_cache.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Weekly job refresh completed at $(Get-Date -Format o)"
