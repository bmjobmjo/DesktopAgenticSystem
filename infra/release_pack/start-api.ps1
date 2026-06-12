Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python virtual environment not found. Run .\setup.ps1 first."
}

$cfgJson = & $python .\scripts\prepare_release_instance.py --root . --sync-settings --format json
$cfg = $cfgJson | ConvertFrom-Json

if (-not $env:DAS_API_HOST) { $env:DAS_API_HOST = [string]$cfg.api_host }
if (-not $env:DAS_API_PORT) { $env:DAS_API_PORT = [string]$cfg.api_port }
if (-not $env:DAS_API_CORS_ORIGINS) { $env:DAS_API_CORS_ORIGINS = (($cfg.cors_origins | ForEach-Object { [string]$_ }) -join ",") }
if (-not $env:DAS_BOOTSTRAP_ADMIN_USERNAME) { $env:DAS_BOOTSTRAP_ADMIN_USERNAME = [string]$cfg.bootstrap_admin_username }
if (-not $env:DAS_BOOTSTRAP_ADMIN_EMAIL) { $env:DAS_BOOTSTRAP_ADMIN_EMAIL = [string]$cfg.bootstrap_admin_email }
if (-not $env:DAS_BOOTSTRAP_ADMIN_PASSWORD -and [string]$cfg.bootstrap_admin_password) {
    $env:DAS_BOOTSTRAP_ADMIN_PASSWORD = [string]$cfg.bootstrap_admin_password
}
if (-not $env:DAS_BOOTSTRAP_ADMIN_PASSWORD) {
    Write-Warning "Using default bootstrap admin password 'admin123'. Set DAS_BOOTSTRAP_ADMIN_PASSWORD before first start."
    $env:DAS_BOOTSTRAP_ADMIN_PASSWORD = "admin123"
}

& $python .\api_start.py
