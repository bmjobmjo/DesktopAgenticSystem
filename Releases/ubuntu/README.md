# OASIS Ubuntu Release

This folder contains the Ubuntu-ready non-Docker distribution packs for the OASIS web application and API runtime.

## Current Pack

- Use the latest Ubuntu release zip in this folder, for example `oasis-release-ubuntu*.zip`.

## Prerequisites

- Ubuntu machine
- Python 3.11 or newer
- `python3-venv`
- `python3-pip`
- Internet access during first setup for `pip install`

If Python venv support is not present, install it first:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## Install Steps

1. Copy the zip to the target Ubuntu machine.
2. Extract the zip to a folder of your choice.
3. Open a terminal in the extracted folder.
4. Make the scripts executable:

```bash
chmod +x setup.sh start-api.sh start-ui.sh start-all.sh
```

5. Run setup:

```bash
./setup.sh
```

6. Open `instance-config.json` and review the defaults.

Recommended first change:

```json
"bootstrap_admin_password": "change-this-now"
```

If another OASIS deployment is already using `8080` or `8787`, change both ports before first start.

## Start On Standard Ports

Standard ports:
- Web UI: `8080`
- API: `8787`

Start the full system:

```bash
./start-all.sh
```

Or start separately:

```bash
./start-api.sh
```

```bash
./start-ui.sh
```

## Start On Custom Ports

Edit `instance-config.json` before starting.

Example:

```json
{
  "api_host": "0.0.0.0",
  "api_port": 4041,
  "api_base_url": "",
  "ui_host": "0.0.0.0",
  "ui_port": 4040,
  "cors_origins": [
    "http://YOUR_SERVER_IP:4040",
    "http://127.0.0.1:4040",
    "http://localhost:4040"
  ],
  "bootstrap_admin_password": "change-this-now",
  "sqlite_db_path": "data/instance2/office_automation.db",
  "file_storage_path": "storage/instance2/files",
  "whatsapp_folder_root": "storage/instance2/whatsapp_bridge_exchange",
  "logs_path": "runtime/instance2/logs"
}
```

Then start:

```bash
./start-all.sh
```

Or separately:

```bash
./start-api.sh
```

```bash
./start-ui.sh
```

If the UI is public and the browser is calling the API directly by IP/port, the API must also be reachable from the browser. That means either:

- set `api_host` to `0.0.0.0` and open the API port
- or keep the API private and place a reverse proxy in front of both UI and API

## Default URLs

- Web UI: `http://127.0.0.1:8080`
- API: `http://127.0.0.1:8787`
- API health: `http://127.0.0.1:8787/health`
- Public custom-port example:
  - UI: `http://YOUR_SERVER_IP:4040`
  - API health: `http://YOUR_SERVER_IP:4041/health`

## Notes

- No Docker is required.
- No Node.js is required on the target machine.
- The startup scripts read `instance-config.json` and sync runtime paths into `apps/das_core/settings/user_config.json`.
- Environment variables can still override values from `instance-config.json` if needed.
- For multiple instances on one machine, use a separate extracted folder for each instance and give each one different ports and paths in its own `instance-config.json`.
