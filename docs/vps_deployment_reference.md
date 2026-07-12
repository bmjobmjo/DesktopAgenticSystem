# VPS Deployment Reference

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
