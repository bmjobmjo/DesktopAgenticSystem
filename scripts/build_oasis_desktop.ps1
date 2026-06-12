param(
    [string]$OutputRoot = "",
    [string]$AppVersion = "0.1.7",
    [string]$NodeExe = "D:\programs\node\node.exe",
    [switch]$NoZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $RepoRoot "Releases\desktop\windows"
}

$PackName = "oasis-desktop-$AppVersion"
$StageDir = Join-Path $OutputRoot $PackName
$ZipPath = Join-Path $OutputRoot "$PackName.zip"
$WorkRoot = Join-Path $RepoRoot ".tmp_pyinstaller"
$BuildRoot = Join-Path $WorkRoot "build"
$SpecRoot = Join-Path $WorkRoot "spec"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$VenvSitePackages = Join-Path $RepoRoot ".venv\Lib\site-packages"
$VenvCfgPath = Join-Path $RepoRoot ".venv\pyvenv.cfg"
$WhatsAppHeadlessDir = Join-Path $RepoRoot "apps\whatsapp_bridge\headless"

function Remove-IfExists {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
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

function To-PyInstallerPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return $Path.Replace('\', '/')
}

function Get-VenvBasePython {
    param([Parameter(Mandatory = $true)][string]$CfgPath)
    if (-not (Test-Path $CfgPath)) {
        return $null
    }
    $match = Select-String -Path $CfgPath -Pattern '^executable\s*=\s*(.+)$' | Select-Object -First 1
    if (-not $match) {
        return $null
    }
    return $match.Matches[0].Groups[1].Value.Trim()
}

if (-not (Test-Path $PythonExe) -and -not (Get-VenvBasePython -CfgPath $VenvCfgPath) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "No usable Python runtime found for the desktop build."
}

$SeedDb = Join-Path $RepoRoot "data\OfficeAutomationTest\office_automation.db"
if (-not (Test-Path $SeedDb)) {
    throw "Seed database not found at $SeedDb"
}
if (-not (Test-Path $WhatsAppHeadlessDir)) {
    throw "WhatsApp headless bridge directory not found at $WhatsAppHeadlessDir"
}
if (-not (Test-Path $NodeExe)) {
    throw "Node executable not found at $NodeExe"
}

Remove-IfExists -Path $StageDir
Remove-IfExists -Path $ZipPath
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $SpecRoot -Force | Out-Null

$hiddenImports = @(
    "tools.agent_creation_tools",
    "tools.create_zip",
    "tools.export_file",
    "tools.gmail_tools",
    "tools.render_image",
    "tools.scheduler_tools",
    "tools.sqlite_tools",
    "tools.telegram_tools",
    "tools.tool_metadata_registry",
    "tools.tool_registry",
    "tools.whatsapp_tools",
    "tools.embeddings.file_ingestion",
    "tools.filesystem.copy_file",
    "tools.filesystem.inspect_file",
    "tools.filesystem.list_directory",
    "tools.filesystem.move_file",
    "tools.filesystem.read_file",
    "prompts",
    "prompts.renderer"
)

$pyiArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", $PackName,
    "--icon", (Join-Path $RepoRoot "apps\das_core\assets\generated\desktop_agentic_system.ico"),
    "--distpath", $OutputRoot,
    "--workpath", $BuildRoot,
    "--specpath", $SpecRoot,
    ("--add-data=" + (To-PyInstallerPath (Join-Path $RepoRoot "apps\das_core\agents")) + ";agents"),
    ("--add-data=" + (To-PyInstallerPath (Join-Path $RepoRoot "apps\das_core\assets")) + ";assets"),
    ("--add-data=" + (To-PyInstallerPath (Join-Path $RepoRoot "apps\das_core\settings")) + ";settings"),
    ("--add-data=" + (To-PyInstallerPath (Join-Path $RepoRoot "apps\das_core\reference")) + ";reference"),
    ("--add-data=" + (To-PyInstallerPath (Join-Path $RepoRoot "apps\das_core\prompts")) + ";prompts"),
    ("--add-data=" + (To-PyInstallerPath $WhatsAppHeadlessDir) + ";apps/whatsapp_bridge/headless"),
    ("--add-data=" + (To-PyInstallerPath $NodeExe) + ";node"),
    ("--add-data=" + (To-PyInstallerPath $SeedDb) + ";data"),
    (Join-Path $RepoRoot "apps\das_core\main.py")
)

foreach ($hiddenImport in $hiddenImports) {
    $pyiArgs += @("--hidden-import", $hiddenImport)
}

$pythonCommand = $PythonExe
$basePythonExe = Get-VenvBasePython -CfgPath $VenvCfgPath
$previousPythonPath = $env:PYTHONPATH
$useSystemPython = $false
try {
    if (Test-Path $PythonExe) {
        $venvPythonOk = $false
        try {
            & $PythonExe -V | Out-Null
            $venvPythonOk = ($LASTEXITCODE -eq 0)
        }
        catch {
            $venvPythonOk = $false
        }

        if (-not $venvPythonOk) {
            if ($basePythonExe -and (Test-Path $basePythonExe)) {
                $pythonCommand = $basePythonExe
            } else {
                $useSystemPython = $true
            }
        }
    } elseif ($basePythonExe -and (Test-Path $basePythonExe)) {
        $pythonCommand = $basePythonExe
    } else {
        $useSystemPython = $true
    }

    if ($useSystemPython) {
        $pythonCommand = "python"
        if (-not (Test-Path $VenvSitePackages)) {
            throw "Fallback site-packages not found at $VenvSitePackages"
        }
        $resolvedSitePackages = (Resolve-Path $VenvSitePackages).Path
        if ($previousPythonPath) {
            $env:PYTHONPATH = "$resolvedSitePackages;$previousPythonPath"
        } else {
            $env:PYTHONPATH = $resolvedSitePackages
        }
    }

    & $pythonCommand -m PyInstaller @pyiArgs
}
finally {
    if ($null -ne $previousPythonPath) {
        $env:PYTHONPATH = $previousPythonPath
    } else {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
}
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$defaultsPath = Join-Path $RepoRoot "apps\das_core\settings\defaults.json"
$defaults = Get-Content $defaultsPath -Raw | ConvertFrom-Json
$sanitized = [ordered]@{}
foreach ($prop in $defaults.PSObject.Properties) {
    $sanitized[$prop.Name] = $prop.Value
}

$sanitized["sqlite_db_path"] = "data\office_automation.db"
$sanitized["file_storage_path"] = "storage\files"
$sanitized["accessible_directories"] = @()
$sanitized["default_directory"] = ""
$sanitized["current_user_id"] = 1
$sanitized["current_username"] = "admin"
$sanitized["current_user_email"] = ""
$sanitized["telegram_enabled"] = $false
$sanitized["telegram_bot_token"] = ""
$sanitized["telegram_test_chat_id"] = ""
$sanitized["whatsapp_enabled"] = $false
$sanitized["whatsapp_folder_root"] = "storage\whatsapp_bridge_exchange"
$sanitized["whatsapp_sender_id"] = ""
$sanitized["whatsapp_test_to"] = ""
$sanitized["gmail_enabled"] = $false
$sanitized["gmail_sender_email"] = ""
$sanitized["gmail_sender_name"] = ""
$sanitized["gmail_app_password"] = ""
$sanitized["gmail_test_to"] = ""
$sanitized["scheduler_enabled"] = $false
$sanitized["gemini_api_key"] = ""
$sanitized["groq_api_key"] = ""
$sanitized["openrouter_api_key"] = ""

$internalSettingsDir = Join-Path $StageDir "_internal\settings"
Write-JsonFile -Path (Join-Path $internalSettingsDir "user_config.json") -Object $sanitized
Write-JsonFile -Path (Join-Path $internalSettingsDir "user_config.example.json") -Object $sanitized

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

Copy-Item -LiteralPath $SeedDb -Destination (Join-Path $StageDir "data\office_automation.db") -Force

Copy-Item -LiteralPath (Join-Path $RepoRoot "Releases\desktop\windows\README.md") -Destination (Join-Path $StageDir "README.md") -Force

if (-not $NoZip) {
    Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
}

Write-Host "Desktop release created:"
Write-Host "  Folder: $StageDir"
if (-not $NoZip) {
    Write-Host "  Zip:    $ZipPath"
}
