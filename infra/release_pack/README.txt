OASIS release pack runtime files.

Windows:
- bundled Python runtime is included under ./python
- run setup.ps1 first
- setup creates .venv and installs dependencies from the internet

Linux:
- system python3 is still required
- run setup.sh first
- packaged .sh files use Unix line endings

Both:
- instance-config.json controls ports and runtime paths
- if another deployment already uses 8080 or 8787, change both API and UI ports before first start
- if the UI is public and the browser calls the API directly, the API must also be public or fronted by a reverse proxy
- start-all launches UI + API
