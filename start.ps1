# NoLoop API backend — Windows / PowerShell launcher (:4000)
# Usage:  ./start.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Create venv + install deps on first run
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e .
}

# Port defaults to 4000 (override with $env:API_PORT)
$port = if ($env:API_PORT) { $env:API_PORT } else { "4000" }

# Run the API (uses the venv's uvicorn without needing to "activate")
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port $port
