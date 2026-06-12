Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python virtual environment not found. Run .\setup.ps1 first."
}

$cfgJson = & $python .\scripts\prepare_release_instance.py --root . --sync-settings --format json
$cfg = $cfgJson | ConvertFrom-Json
$uiLogDir = [string]$cfg.logs_path
New-Item -ItemType Directory -Path $uiLogDir -Force | Out-Null

$uiScript = Join-Path $PSScriptRoot "start-ui.ps1"
$uiOut = Join-Path $uiLogDir "ui.out.log"
$uiErr = Join-Path $uiLogDir "ui.err.log"

Start-Process `
  -FilePath "powershell.exe" `
  -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uiScript `
  -WorkingDirectory $PSScriptRoot `
  -RedirectStandardOutput $uiOut `
  -RedirectStandardError $uiErr `
  -WindowStyle Hidden

& .\start-api.ps1
