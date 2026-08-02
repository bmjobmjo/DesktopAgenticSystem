# VPS Deployment Reference

## Fictional Ebird Innovation Demo Instance

- Install root: `/opt/fictionalDemoDb`
- Public UI: `http://69.164.244.153:9090`
- API base: `http://69.164.244.153:9091`
- Active database: `/opt/fictionalDemoDb/data/office_automation.db`
- Runtime configuration: `/opt/fictionalDemoDb/instance-config.json`
- Built UI assets: `/opt/fictionalDemoDb/apps/ui_web/dist`
- Logs: `/opt/fictionalDemoDb/runtime/logs`

This is the fixed, fictional Ebird Innovation demo environment. Its active
database is named `office_automation.db`, but it contains the fictional seeded
dataset. Preserve the install root and ports `9090`/`9091`; another VPS
instance uses different ports.

### Update policy

- UI-only changes: update `/opt/fictionalDemoDb/apps/ui_web/dist`.
- Backend logic, prompts, tools, schema, or runtime changes: update the full
  instance contents.
- Fictional business-data changes: update the active database above.
- Configuration changes: update `instance-config.json` without changing the
  configured paths or ports unless the deployment layout is intentionally
  being changed.

### Prompt-only update

After deploying the updated prompt files and
`scripts/sync_builtin_agent_prompts.py`, run:

```bash
cd /opt/fictionalDemoDb
./.venv/bin/python scripts/sync_builtin_agent_prompts.py data/office_automation.db
```

Then restart this instance's API process so subsequent requests use the
revised agent prompt.

## Current Non-Docker Ubuntu/Web Install

- Install root: `/opt/oasis_web_inst_appleberry`
- Start command currently used: `./start-all.sh`

### Current Runtime Paths

- Database: `/opt/oasis_web_inst_appleberry/data/office_automation.db`
- Storage root: `/opt/oasis_web_inst_appleberry/storage`
- WhatsApp exchange folder: `/opt/oasis_web_inst_appleberry/storage/whatsapp_bridge_exchange`
- Logs: `/opt/oasis_web_inst_appleberry/runtime/logs`
- Main config: `/opt/oasis_web_inst_appleberry/instance-config.json`
- User settings: `/opt/oasis_web_inst_appleberry/apps/das_core/settings/user_config.json`

### Current Ports

- Web UI: `4040`
- API: `4041`

### Current Bind Settings

- UI host: `0.0.0.0`
- API host: `0.0.0.0`

## Old Docker-Based Install

- Compose folder: `/opt/vps_bundle`
- Compose file: `/opt/vps_bundle/docker-compose.yml`

### Old Docker Runtime Paths On Host

- Database: `/opt/oasis/runtime/data/office_automation.db`
- Storage root: `/opt/oasis/runtime/storage`
- Logs: `/opt/oasis/runtime/logs`
- Docker-mounted settings file: `/opt/oasis/settings/user_config.json`

### Old Docker Ports

- Web UI: `8080`
- API: `8787`

## Operational Note

If the current non-Docker app is started manually with `./start-all.sh` from an SSH terminal, closing that terminal can stop the API process because the API runs in the foreground.
