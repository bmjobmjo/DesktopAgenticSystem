param(
    [string]$OutputRoot = "",
    [string]$AppVersion = "0.1.12",
    [string]$ApiBaseUrl = "",
    [string]$BundledPythonRoot = "",
    [string]$BundledNodeExe = "",
    [string]$SeedDbPath = "",
    [string]$PackNamePrefix = "oasis-release-pack",
    [string]$TimestampFormat = "yyyyMMdd-HHmm",
    [switch]$SkipUiBuild,
    [switch]$NoZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "Releases"
}

function Get-VenvBasePythonRoot {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $cfgPath = Join-Path $RepoRoot ".venv\pyvenv.cfg"
    if (-not (Test-Path $cfgPath)) {
        return $null
    }

    $exeMatch = Select-String -Path $cfgPath -Pattern '^executable\s*=\s*(.+)$' | Select-Object -First 1
    if ($exeMatch) {
        $exePath = $exeMatch.Matches[0].Groups[1].Value.Trim()
        if (Test-Path $exePath) {
            return Split-Path -Parent $exePath
        }
    }

    $homeMatch = Select-String -Path $cfgPath -Pattern '^home\s*=\s*(.+)$' | Select-Object -First 1
    if ($homeMatch) {
        $homePath = $homeMatch.Matches[0].Groups[1].Value.Trim()
        if (Test-Path (Join-Path $homePath "python.exe")) {
            return $homePath
        }
    }

    return $null
}

if (-not $BundledPythonRoot) {
    $BundledPythonRoot = Get-VenvBasePythonRoot -RepoRoot $RepoRoot
}
if (-not $BundledPythonRoot) {
    throw "Unable to resolve bundled Python root. Pass -BundledPythonRoot explicitly."
}
if (-not (Test-Path (Join-Path $BundledPythonRoot "python.exe"))) {
    throw "Bundled Python runtime not found at $BundledPythonRoot"
}

if (-not $BundledNodeExe) {
    $nodeCandidates = @(
        (Join-Path $RepoRoot "node\node.exe"),
        "D:\programs\node\node.exe"
    )
    foreach ($candidate in $nodeCandidates) {
        if (Test-Path $candidate) {
            $BundledNodeExe = $candidate
            break
        }
    }
}

if (-not $SeedDbPath) {
    $SeedDbPath = Join-Path $RepoRoot "data\OfficeAutomationTest\office_automation.db"
} elseif (-not [System.IO.Path]::IsPathRooted($SeedDbPath)) {
    $SeedDbPath = Join-Path $RepoRoot $SeedDbPath
}
if (-not (Test-Path $SeedDbPath)) {
    throw "Seed database not found at $SeedDbPath"
}

$Timestamp = Get-Date -Format $TimestampFormat
$PackName = "$PackNamePrefix-$AppVersion-$Timestamp"
$StageDir = Join-Path $OutputRoot $PackName
$ZipPath = "$StageDir.zip"

function Invoke-RobocopyCopy {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $copyArgs = @($Source, $Destination, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($ExcludeDirs.Count -gt 0) {
        $copyArgs += "/XD"
        $copyArgs += $ExcludeDirs
    }
    if ($ExcludeFiles.Count -gt 0) {
        $copyArgs += "/XF"
        $copyArgs += $ExcludeFiles
    }

    & robocopy @copyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed for $Source -> $Destination with exit code $LASTEXITCODE"
    }
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Object
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json -Depth 20), $utf8NoBom)
}

function Remove-IfExists {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

$pythonExcludeDirs = @(
    "__pycache__",
    "Doc",
    "include",
    "share",
    "Scripts",
    "Tools",
    "Lib\site-packages",
    "Lib\test",
    "Lib\tkinter",
    "Lib\idlelib"
)
$pythonExcludeDirPaths = @()
foreach ($dir in $pythonExcludeDirs) {
    $pythonExcludeDirPaths += (Join-Path $BundledPythonRoot $dir)
}

Remove-IfExists -Path $StageDir
Remove-IfExists -Path $ZipPath
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

if (-not $SkipUiBuild) {
    Push-Location (Join-Path $RepoRoot "apps\ui_web")
    try {
        $previousApiBase = $env:VITE_API_BASE_URL
        if ($ApiBaseUrl) {
            $env:VITE_API_BASE_URL = $ApiBaseUrl
        } else {
            Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
        }
        npm.cmd run build
    }
    finally {
        if ($null -ne $previousApiBase) {
            $env:VITE_API_BASE_URL = $previousApiBase
        } else {
            Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
        }
        Pop-Location
    }
}

$distDir = Join-Path $RepoRoot "apps\ui_web\dist"
if (-not (Test-Path $distDir)) {
    throw "UI dist folder not found at $distDir. Run without -SkipUiBuild or build the UI first."
}

New-Item -ItemType Directory -Path $StageDir -Force | Out-Null

Invoke-RobocopyCopy `
    -Source $BundledPythonRoot `
    -Destination (Join-Path $StageDir "python") `
    -ExcludeDirs $pythonExcludeDirPaths

if ($BundledNodeExe -and (Test-Path $BundledNodeExe)) {
    $nodeStageDir = Join-Path $StageDir "node"
    New-Item -ItemType Directory -Path $nodeStageDir -Force | Out-Null
    Copy-Item -LiteralPath $BundledNodeExe -Destination (Join-Path $nodeStageDir "node.exe") -Force
}

foreach ($file in @("api_start.py", "app_bootstrap.py", "main.py", "service_start.py")) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot $file) -Destination (Join-Path $StageDir $file) -Force
}

Invoke-RobocopyCopy `
    -Source (Join-Path $RepoRoot "apps\api_gateway") `
    -Destination (Join-Path $StageDir "apps\api_gateway") `
    -ExcludeDirs @("__pycache__", "tests", "logs") `
    -ExcludeFiles @("*.pyc", "*.pyo", "*.db", "*.log")

Invoke-RobocopyCopy `
    -Source (Join-Path $RepoRoot "apps\das_core") `
    -Destination (Join-Path $StageDir "apps\das_core") `
    -ExcludeDirs @("__pycache__", "tests", ".pytest_cache", "auth_state", "data", "logs", "storage", "EmbedingModel", "hf_cache_temp", "for_ref") `
    -ExcludeFiles @("*.pyc", "*.pyo", "user_config.json", "*.db", "*.log")

Invoke-RobocopyCopy `
    -Source (Join-Path $RepoRoot "apps\whatsapp_bridge") `
    -Destination (Join-Path $StageDir "apps\whatsapp_bridge") `
    -ExcludeDirs @("__pycache__", "auth_session", "messenger_previews") `
    -ExcludeFiles @("*.pyc", "*.pyo", "*.log", "*.db")

if (Test-Path (Join-Path $RepoRoot "shared")) {
    Invoke-RobocopyCopy `
        -Source (Join-Path $RepoRoot "shared") `
        -Destination (Join-Path $StageDir "shared") `
        -ExcludeDirs @("__pycache__") `
        -ExcludeFiles @("*.pyc", "*.pyo")
}

New-Item -ItemType Directory -Path (Join-Path $StageDir "apps\ui_web") -Force | Out-Null
Invoke-RobocopyCopy `
    -Source $distDir `
    -Destination (Join-Path $StageDir "apps\ui_web\dist")

New-Item -ItemType Directory -Path (Join-Path $StageDir "scripts") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts\serve_oasis_ui.py") -Destination (Join-Path $StageDir "scripts\serve_oasis_ui.py") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "scripts\prepare_release_instance.py") -Destination (Join-Path $StageDir "scripts\prepare_release_instance.py") -Force

Invoke-RobocopyCopy `
    -Source (Join-Path $RepoRoot "infra\release_pack") `
    -Destination $StageDir

$defaultsPath = Join-Path $RepoRoot "apps\das_core\settings\defaults.json"
$defaults = Get-Content $defaultsPath -Raw | ConvertFrom-Json
$sanitized = [ordered]@{}
foreach ($prop in $defaults.PSObject.Properties) {
    $sanitized[$prop.Name] = $prop.Value
}
$sanitized["sqlite_db_path"] = "data\office_automation.db"
$sanitized["file_storage_path"] = "storage\files"
$sanitized["whatsapp_folder_root"] = "storage\whatsapp_bridge_exchange"
$sanitized["accessible_directories"] = @()
$sanitized["default_directory"] = ""
$sanitized["current_user_id"] = 1
$sanitized["current_username"] = "admin"
$sanitized["current_user_email"] = ""
$sanitized["telegram_enabled"] = $false
$sanitized["telegram_bot_token"] = ""
$sanitized["whatsapp_enabled"] = $false
$sanitized["gmail_enabled"] = $false
$sanitized["gmail_sender_email"] = ""
$sanitized["gmail_sender_name"] = ""
$sanitized["gmail_app_password"] = ""
$sanitized["gmail_test_to"] = ""
$sanitized["gmail_test_subject"] = "Test Email from OASIS"
$sanitized["gmail_test_body"] = "Hello from OASIS"
$sanitized["scheduler_enabled"] = $false
$sanitized["gemini_api_key"] = ""
$sanitized["groq_api_key"] = ""
$sanitized["openrouter_api_key"] = ""

Write-JsonFile -Path (Join-Path $StageDir "apps\das_core\settings\user_config.json") -Object $sanitized
Write-JsonFile -Path (Join-Path $StageDir "apps\das_core\settings\user_config.example.json") -Object $sanitized

$instanceConfig = [ordered]@{
    api_host = "127.0.0.1"
    api_port = 8787
    api_base_url = ""
    ui_host = "127.0.0.1"
    ui_port = 8080
    cors_origins = @(
        "http://127.0.0.1:8080",
        "http://localhost:8080"
    )
    bootstrap_admin_username = "admin"
    bootstrap_admin_email = "admin@local"
    bootstrap_admin_password = ""
    sqlite_db_path = "data/office_automation.db"
    file_storage_path = "storage/files"
    whatsapp_folder_root = "storage/whatsapp_bridge_exchange"
    logs_path = "runtime/logs"
}
Write-JsonFile -Path (Join-Path $StageDir "instance-config.json") -Object $instanceConfig
Write-JsonFile -Path (Join-Path $StageDir "instance-config.example.json") -Object $instanceConfig

foreach ($dir in @(
    "data",
    "storage",
    "storage\files",
    "storage\whatsapp_bridge_exchange",
    "runtime",
    "runtime\logs"
)) {
    New-Item -ItemType Directory -Path (Join-Path $StageDir $dir) -Force | Out-Null
}

$destDb = Join-Path $StageDir "data\office_automation.db"
Copy-Item -LiteralPath $SeedDbPath -Destination $destDb -Force

if (-not $NoZip) {
    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
}

Write-Host "Release pack created:"
Write-Host "  Folder: $StageDir"
if (-not $NoZip) {
    Write-Host "  Zip:    $ZipPath"
}
