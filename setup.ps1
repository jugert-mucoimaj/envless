<#
    One-time setup: two Python environments, the frontend's packages, the
    Postgres database, and a seeded set of environments to look at.

        .\setup.ps1

    Expects Python 3.11+, Node 20+, and a local Postgres you can reach as the
    postgres user. The local password is read from $env:PGPASSWORD, or falls
    back to the one this project uses for development.
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not $env:PGPASSWORD) { $env:PGPASSWORD = "kali" }

Write-Host "1/5  Creating the envless database" -ForegroundColor Cyan
$exists = & psql -U postgres -h localhost -tAc "select 1 from pg_database where datname='envless'" 2>$null
if ($exists -ne "1") {
    & psql -U postgres -h localhost -c "CREATE DATABASE envless;" | Out-Null
    Write-Host "     created" -ForegroundColor DarkGray
} else {
    Write-Host "     already there" -ForegroundColor DarkGray
}

Write-Host "2/5  Setting up the backend" -ForegroundColor Cyan
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) { & py -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $key = & ".\.venv\Scripts\python.exe" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    (Get-Content ".env") -replace "^ENVLESS_MASTER_KEY=$", "ENVLESS_MASTER_KEY=$key" | Set-Content ".env"
    Write-Host "     wrote backend\.env with a fresh encryption key" -ForegroundColor DarkGray
}
Pop-Location

Write-Host "3/5  Setting up Pigeon" -ForegroundColor Cyan
Push-Location "$root\pigeon"
if (-not (Test-Path ".venv")) { & py -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
Pop-Location

Write-Host "4/5  Installing the frontend's packages" -ForegroundColor Cyan
Push-Location "$root\frontend"
& npm install --silent
if (-not (Test-Path ".env.local")) { Copy-Item ".env.example" ".env.local" }
Pop-Location

Write-Host "5/5  Seeding environments to look at" -ForegroundColor Cyan
Push-Location "$root\backend"
& ".\.venv\Scripts\python.exe" seed.py
Pop-Location

Write-Host ""
Write-Host "Ready. Start everything with .\dev.ps1" -ForegroundColor Green
