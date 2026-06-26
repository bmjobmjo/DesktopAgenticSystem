OASIS release pack runtime files.

Windows:
- bundled Python runtime is included under ./python
- run setup.ps1 first
- setup creates .venv and installs dependencies from the internet

Linux:
- system python3 is still required
- run setup.sh first

Both:
- instance-config.json controls ports and runtime paths
- start-all launches UI + API
