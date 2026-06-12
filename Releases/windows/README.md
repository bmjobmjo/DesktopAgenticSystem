# OASIS Windows Release

This folder contains the Windows-ready non-Docker distribution packs for the OASIS web application and API runtime.

## Current Pack

- Use the latest `oasis-release-pack-*.zip` file in this folder.

## Prerequisites

- Windows machine
- Python 3.11 or newer installed and available in `PATH`
- Internet access during first setup for `pip install`
- PowerShell

## Install Steps

1. Copy the zip to the target Windows machine.
2. Extract the zip to a folder of your choice.
3. Open PowerShell in the extracted folder.
4. Run:

```powershell
.\setup.ps1
```

5. Open `instance-config.json` and review the defaults.

Recommended first change:

```json
"bootstrap_admin_password": "change-this-now"
```

## Start On Standard Ports

Standard ports:
- Web UI: `8080`
- API: `8787`

Start the full system:

```powershell
.\start-all.ps1
```

Or start separately:

```powershell
.\start-api.ps1
```

```powershell
.\start-ui.ps1
```

## Start On Custom Ports

Edit `instance-config.json` before starting.

Example:

```json
{
  "api_host": "127.0.0.1",
  "api_port": 9000,
  "api_base_url": "",
  "ui_host": "127.0.0.1",
  "ui_port": 8090,
  "cors_origins": [
    "http://127.0.0.1:8090",
    "http://localhost:8090"
  ],
  "bootstrap_admin_password": "change-this-now",
  "sqlite_db_path": "data/instance2/office_automation.db",
  "file_storage_path": "storage/instance2/files",
  "whatsapp_folder_root": "storage/instance2/whatsapp_bridge_exchange",
  "logs_path": "runtime/instance2/logs"
}
```

Then start:

```powershell
.\start-all.ps1
```

Or separately:

```powershell
.\start-api.ps1
```

```powershell
.\start-ui.ps1
```

## Default URLs

- Web UI: `http://127.0.0.1:8080`
- API: `http://127.0.0.1:8787`
- API health: `http://127.0.0.1:8787/health`

## Notes

- No Docker is required.
- No Node.js is required on the target machine.
- The startup scripts read `instance-config.json` and sync runtime paths into `apps/das_core/settings/user_config.json`.
- Environment variables can still override values from `instance-config.json` if needed.
- For multiple instances on one machine, use a separate extracted folder for each instance and give each one different ports and paths in its own `instance-config.json`.
