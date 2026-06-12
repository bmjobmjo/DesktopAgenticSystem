OASIS Full Distribution Pack
============================

This pack includes:
- DAS API runtime
- DAS core modules used by the API
- Prebuilt OASIS Web UI in `apps/ui_web/dist`
- A small Python static server for the UI
- Windows and Ubuntu startup scripts

Runtime assumptions
-------------------
- Python 3.11+ in PATH
- No Docker required
- No Node.js required on the target machine
- Internet access during first setup to install Python packages

Ports
-----
- Web UI: `http://127.0.0.1:8080`
- API: `http://127.0.0.1:8787`
- API health: `http://127.0.0.1:8787/health`

Windows setup
-------------
1. Open PowerShell in the pack root.
2. Run:
   `.\setup.ps1`
3. Edit `instance-config.json` if you need custom ports, paths, or a bootstrap password.
4. Start both:
   `.\start-all.ps1`

Ubuntu setup
------------
1. Open a terminal in the pack root.
2. Run:
   `chmod +x setup.sh start-api.sh start-ui.sh start-all.sh`
   `./setup.sh`
3. Edit `instance-config.json` if you need custom ports, paths, or a bootstrap password.
4. Start both:
   `./start-all.sh`

Starting separately
-------------------
Windows:
- `.\start-api.ps1`
- `.\start-ui.ps1`

Ubuntu:
- `./start-api.sh`
- `./start-ui.sh`

Configuration
-------------
Primary release config:
- `instance-config.json`

The release scripts use `instance-config.json` to set:
- API host and port
- UI host and port
- CORS origins
- bootstrap admin defaults
- DB path
- storage paths
- logs path

The scripts then sync the runtime paths into:
- `apps/das_core/settings/user_config.json`

Default runtime paths are relative to the pack root:
- `data/office_automation.db`
- `storage/files`
- `storage/whatsapp_bridge_exchange`
- `runtime/logs`

CORS
----
The API start scripts default `DAS_API_CORS_ORIGINS` to:
- `http://127.0.0.1:8080`
- `http://localhost:8080`

If you host the UI on another origin, set `DAS_API_CORS_ORIGINS` before starting the API.

Notes
-----
- This pack intentionally excludes local secrets, current WhatsApp auth sessions, and machine-specific runtime data.
- If you want Telegram, WhatsApp, or LLM provider access, update `apps/das_core/settings/user_config.json` after deployment.
- Environment variables can still override `instance-config.json` for advanced usage.
