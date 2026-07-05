$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:BACKEND_PORT = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "17000" }

if (-not (Test-Path "backend\.venv")) {
    python -m venv backend\.venv
}
& "backend\.venv\Scripts\Activate.ps1"
pip install -r backend\requirements.txt

if (-not (Test-Path "backend\.env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" "backend\.env"
    Write-Host "Created backend\.env from .env.example — edit if needed."
}

Set-Location (Join-Path $Root "frontend")
npm ci
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run dev" -WindowStyle Normal

Start-Sleep -Seconds 3
Set-Location (Join-Path $Root "backend")
uvicorn app.main:app --reload --port $env:BACKEND_PORT
