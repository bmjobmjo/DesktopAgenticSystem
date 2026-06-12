Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python virtual environment not found. Run .\setup.ps1 first."
}

$cfgJson = & $python .\scripts\prepare_release_instance.py --root . --sync-settings --format json
$cfg = $cfgJson | ConvertFrom-Json

$hostName = if ($env:OASIS_UI_HOST) { $env:OASIS_UI_HOST } else { [string]$cfg.ui_host }
$port = if ($env:OASIS_UI_PORT) { $env:OASIS_UI_PORT } else { [string]$cfg.ui_port }

& $python .\scripts\serve_oasis_ui.py --root .\apps\ui_web\dist --host $hostName --port $port
