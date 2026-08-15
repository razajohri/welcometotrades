# Deploy find_jobs_canada to Railway from this repo root.
# Prereq: npm i -g @railway/cli  &&  railway login

$ErrorActionPreference = "Stop"

function Invoke-Railway {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & railway @Args
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) { exit $code }
}
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Require-RailwayAuth {
    Invoke-Railway whoami | Out-Null
}

function Ensure-RailwayProject {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    railway status 2>&1 | Out-Null
    $linked = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if (-not $linked) {
        Write-Host "Creating Railway project find-jobs-canada..."
        Invoke-Railway init --name find-jobs-canada
    }
}

function Sync-EnvFromDotEnv {
    param([string]$EnvPath = ".env")
    if (-not (Test-Path $EnvPath)) {
        Write-Host "Missing .env - copy from .env.example and fill in keys." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Syncing variables from $EnvPath (skipping deploy until done)..."
    Get-Content $EnvPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }

        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if ($val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($val.StartsWith("'") -and $val.EndsWith("'")) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if (-not $key) { return }
        if ($key -eq "FLASK_ENV") { return }

        Write-Host "  set $key"
        Invoke-Railway variable set "${key}=${val}" --skip-deploys | Out-Null
    }
}

Require-RailwayAuth
Ensure-RailwayProject

Write-Host ""
Write-Host "First deploy (creates the web service)..."
Invoke-Railway up --yes --detach

Sync-EnvFromDotEnv

Write-Host ""
Write-Host "Redeploying with environment variables..."
Invoke-Railway up --yes --detach

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. railway domain"
Write-Host "  2. railway logs"
Write-Host "  3. Stripe webhook -> https://YOUR-DOMAIN.up.railway.app/webhook"
Write-Host "  4. Smoke test: homepage, login, search job count"
