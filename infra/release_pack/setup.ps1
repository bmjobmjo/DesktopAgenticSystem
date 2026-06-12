Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    python -m venv .venv
}

& $python -m pip install --upgrade pip setuptools wheel
& $python -m pip install -r .\apps\das_core\requirements.hosted.txt
& $python -m pip install -r .\apps\api_gateway\requirements.txt

Write-Host "Runtime environment is ready."
