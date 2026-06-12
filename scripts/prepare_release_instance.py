from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "api_host": "127.0.0.1",
    "api_port": 8787,
    "api_base_url": "",
    "ui_host": "127.0.0.1",
    "ui_port": 8080,
    "cors_origins": [
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    "bootstrap_admin_username": "admin",
    "bootstrap_admin_email": "admin@local",
    "bootstrap_admin_password": "",
    "sqlite_db_path": "data/office_automation.db",
    "file_storage_path": "storage/files",
    "whatsapp_folder_root": "storage/whatsapp_bridge_exchange",
    "logs_path": "runtime/logs",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _resolve_path(root: Path, value: str) -> str:
    candidate = Path(str(value).strip())
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return str(candidate)


def _normalize(root: Path, raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_CONFIG)
    merged.update(raw or {})

    merged["api_host"] = str(merged.get("api_host", DEFAULT_CONFIG["api_host"]) or DEFAULT_CONFIG["api_host"])
    merged["ui_host"] = str(merged.get("ui_host", DEFAULT_CONFIG["ui_host"]) or DEFAULT_CONFIG["ui_host"])
    merged["api_base_url"] = str(merged.get("api_base_url", "") or "").strip()
    merged["api_port"] = int(merged.get("api_port", DEFAULT_CONFIG["api_port"]) or DEFAULT_CONFIG["api_port"])
    merged["ui_port"] = int(merged.get("ui_port", DEFAULT_CONFIG["ui_port"]) or DEFAULT_CONFIG["ui_port"])

    cors = merged.get("cors_origins", DEFAULT_CONFIG["cors_origins"])
    if isinstance(cors, str):
        cors_list = [x.strip() for x in cors.split(",") if x.strip()]
    elif isinstance(cors, list):
        cors_list = [str(x).strip() for x in cors if str(x).strip()]
    else:
        cors_list = list(DEFAULT_CONFIG["cors_origins"])
    merged["cors_origins"] = cors_list or list(DEFAULT_CONFIG["cors_origins"])

    for key in ("bootstrap_admin_username", "bootstrap_admin_email", "bootstrap_admin_password"):
        merged[key] = str(merged.get(key, "") or "")

    for key in ("sqlite_db_path", "file_storage_path", "whatsapp_folder_root", "logs_path"):
        merged[key] = _resolve_path(root, str(merged.get(key, DEFAULT_CONFIG[key]) or DEFAULT_CONFIG[key]))

    return merged


def _sync_settings(root: Path, config: dict[str, Any]) -> None:
    settings_path = root / "apps" / "das_core" / "settings" / "user_config.json"
    settings = _load_json(settings_path)
    settings["sqlite_db_path"] = config["sqlite_db_path"]
    settings["file_storage_path"] = config["file_storage_path"]
    settings["whatsapp_folder_root"] = config["whatsapp_folder_root"]
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _sync_runtime_js(root: Path, config: dict[str, Any]) -> None:
    runtime_js_path = root / "apps" / "ui_web" / "dist" / "runtime-config.js"
    runtime_js_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "apiBaseUrl": config["api_base_url"],
        "apiPort": config["api_port"],
    }
    runtime_js_path.write_text(
        "window.__OASIS_RUNTIME_CONFIG__ = " + json.dumps(payload, indent=2) + ";\n",
        encoding="utf-8",
    )


def _emit_shell(config: dict[str, Any]) -> str:
    lines = [
        f"export DAS_API_HOST={json.dumps(config['api_host'])}",
        f"export DAS_API_PORT={json.dumps(str(config['api_port']))}",
        f"export OASIS_UI_HOST={json.dumps(config['ui_host'])}",
        f"export OASIS_UI_PORT={json.dumps(str(config['ui_port']))}",
        f"export DAS_API_CORS_ORIGINS={json.dumps(','.join(config['cors_origins']))}",
        f"export DAS_BOOTSTRAP_ADMIN_USERNAME={json.dumps(config['bootstrap_admin_username'])}",
        f"export DAS_BOOTSTRAP_ADMIN_EMAIL={json.dumps(config['bootstrap_admin_email'])}",
    ]
    if config["bootstrap_admin_password"]:
        lines.append(f"export DAS_BOOTSTRAP_ADMIN_PASSWORD={json.dumps(config['bootstrap_admin_password'])}")
    return "\n".join(lines)


def _emit_powershell(config: dict[str, Any]) -> str:
    lines = [
        f"$env:DAS_API_HOST = {json.dumps(config['api_host'])}",
        f"$env:DAS_API_PORT = {json.dumps(str(config['api_port']))}",
        f"$env:OASIS_UI_HOST = {json.dumps(config['ui_host'])}",
        f"$env:OASIS_UI_PORT = {json.dumps(str(config['ui_port']))}",
        f"$env:DAS_API_CORS_ORIGINS = {json.dumps(','.join(config['cors_origins']))}",
        f"$env:DAS_BOOTSTRAP_ADMIN_USERNAME = {json.dumps(config['bootstrap_admin_username'])}",
        f"$env:DAS_BOOTSTRAP_ADMIN_EMAIL = {json.dumps(config['bootstrap_admin_email'])}",
    ]
    if config["bootstrap_admin_password"]:
        lines.append(f"$env:DAS_BOOTSTRAP_ADMIN_PASSWORD = {json.dumps(config['bootstrap_admin_password'])}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a release-pack instance from instance-config.json.")
    parser.add_argument("--root", default=".", help="Pack root.")
    parser.add_argument("--sync-settings", action="store_true", help="Write runtime paths into apps/das_core/settings/user_config.json.")
    parser.add_argument("--format", choices=("json", "shell", "powershell"), default="json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = root / "instance-config.json"
    config = _normalize(root, _load_json(config_path))

    Path(config["logs_path"]).mkdir(parents=True, exist_ok=True)
    Path(config["file_storage_path"]).mkdir(parents=True, exist_ok=True)
    Path(config["whatsapp_folder_root"]).mkdir(parents=True, exist_ok=True)
    Path(config["sqlite_db_path"]).parent.mkdir(parents=True, exist_ok=True)

    if args.sync_settings:
        _sync_settings(root, config)
        _sync_runtime_js(root, config)

    if args.format == "json":
        print(json.dumps(config))
    elif args.format == "shell":
        print(_emit_shell(config))
    else:
        print(_emit_powershell(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
