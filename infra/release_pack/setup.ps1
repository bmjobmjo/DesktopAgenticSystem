Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Get-BundledPython {
    $python = Join-Path $PSScriptRoot "python\python.exe"
    if (-not (Test-Path $python)) {
        throw "Bundled Python runtime not found at $python"
    }
    return $python
}

$bundledPython = Get-BundledPython
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$steps = @(
    @{ Activity = "Preparing runtime"; Status = "Creating virtual environment"; Percent = 10; Command = { & $bundledPython -m venv .venv } },
    @{ Activity = "Preparing runtime"; Status = "Upgrading pip tooling"; Percent = 35; Command = { & $venvPython -m pip install --upgrade pip setuptools wheel } },
    @{ Activity = "Preparing runtime"; Status = "Installing hosted runtime dependencies"; Percent = 60; Command = { & $venvPython -m pip install -r .\apps\das_core\requirements.hosted.txt } },
    @{ Activity = "Preparing runtime"; Status = "Installing API dependencies"; Percent = 85; Command = { & $venvPython -m pip install -r .\apps\api_gateway\requirements.txt } }
)

if (-not (Test-Path $venvPython)) {
    & $bundledPython -V | Out-Null
}

foreach ($step in $steps) {
    if ($step.Percent -eq 10 -and (Test-Path $venvPython)) {
        continue
    }
    Write-Progress -Activity $step.Activity -Status $step.Status -PercentComplete $step.Percent
    & $step.Command
}

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment creation failed. Missing $venvPython"
}

Write-Progress -Activity "Preparing runtime" -Status "Complete" -PercentComplete 100
Write-Host "Runtime environment is ready."
