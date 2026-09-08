<#
    Starts all three parts of envless in their own windows.

        .\dev.ps1            start everything
        .\dev.ps1 -Seed      recreate the database contents first

    backend   http://127.0.0.1:8000    the API and its docs at /docs
    frontend  http://localhost:3000    the command centre
    pigeon    http://127.0.0.1:8100    an app running on these environments
#>

param([switch]$Seed)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Require-Setup($path, $what) {
    if (-not (Test-Path $path)) {
        Write-Host "Missing $what. Run .\setup.ps1 first." -ForegroundColor Red
        exit 1
    }
}

Require-Setup "$root\backend\.venv\Scripts\python.exe" "the backend virtual environment"
Require-Setup "$root\pigeon\.venv\Scripts\python.exe" "Pigeon's virtual environment"
Require-Setup "$root\frontend\node_modules" "the frontend's packages"

if ($Seed) {
    Write-Host "Seeding the database..." -ForegroundColor Cyan
    Push-Location "$root\backend"
    & ".\.venv\Scripts\python.exe" seed.py --reset
    Pop-Location
}

Write-Host "Starting the API on http://127.0.0.1:8000" -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)

Start-Sleep -Seconds 3

Write-Host "Starting the command centre on http://localhost:3000" -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"
)

Write-Host "Starting Pigeon on http://127.0.0.1:8100" -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\pigeon'; .\.venv\Scripts\python.exe app.py"
)

Write-Host ""
Write-Host "All three are starting. Open http://localhost:3000" -ForegroundColor Green
Write-Host "Change a value in Pigeon's Development environment and watch http://127.0.0.1:8100 follow."
