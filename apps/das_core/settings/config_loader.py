"""Settings loader and persistence utilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from core.common_data_area import CommonDataArea

DEFAULTS_PATH = Path(__file__).with_name("defaults.json")
USER_CONFIG_PATH = Path(__file__).with_name("user_config.json")
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
LEGACY_WHATSAPP_ROOTS = {
    r"D:\DAS_Exchange".lower(),
    r"D:/DAS_Exchange".lower(),
}


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def _portable_default_paths(base_dir: Path) -> Dict[str, str]:
    return {
        "sqlite_db_path": str((base_dir / "data" / "office_automation.db").resolve()),
        "file_storage_path": str((base_dir / "storage" / "files").resolve()),
        "whatsapp_folder_root": str((base_dir / "storage" / "whatsapp_bridge_exchange").resolve()),
        "logs_path": str((base_dir / "runtime" / "logs").resolve()),
    }


def _should_replace_legacy_whatsapp_root(value: str) -> bool:
    clean = str(value or "").strip()
    if not clean:
        return True
    return clean.replace("/", "\\").lower() in LEGACY_WHATSAPP_ROOTS


def normalize_runtime_paths(settings: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    resolved = dict(settings)
    changed = False
    base_dir = _app_root()
    portable_defaults = _portable_default_paths(base_dir)

    for key in ("sqlite_db_path", "file_storage_path", "logs_path"):
        raw = str(resolved.get(key, "") or "").strip()
        if not raw:
            resolved[key] = portable_defaults[key]
            changed = True
            continue
        raw_path = Path(raw).expanduser()
        if not raw_path.is_absolute():
            resolved_value = str((base_dir / raw_path).resolve())
            if resolved_value != raw:
                resolved[key] = resolved_value
                changed = True

    wa_raw = str(resolved.get("whatsapp_folder_root", "") or "").strip()
    if _should_replace_legacy_whatsapp_root(wa_raw):
        resolved["whatsapp_folder_root"] = portable_defaults["whatsapp_folder_root"]
        changed = True
    else:
        wa_path = Path(wa_raw).expanduser()
        if not wa_path.is_absolute():
            resolved_value = str((base_dir / wa_path).resolve())
            if resolved_value != wa_raw:
                resolved["whatsapp_folder_root"] = resolved_value
                changed = True

    return resolved, changed


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_defaults() -> Dict[str, Any]:
    return _load_json(DEFAULTS_PATH)


def load_user_config() -> Dict[str, Any]:
    return _load_json(USER_CONFIG_PATH)


def load_settings() -> Dict[str, Any]:
    defaults = load_defaults()
    user = load_user_config()
    merged = {**defaults, **user}
    merged, _ = normalize_runtime_paths(merged)
    return merged


def normalize_embedding_settings(settings: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    resolved = dict(settings)
    changed = False

    if str(resolved.get("embedding_model_name", "") or "").strip() != DEFAULT_EMBEDDING_MODEL:
        resolved["embedding_model_name"] = DEFAULT_EMBEDDING_MODEL
        changed = True
    for legacy_key in ("embedding_local_files_only", "embedding_model_path", "embedding_max_tokens", "embedding_chunk_overlap_tokens"):
        if legacy_key in resolved:
            resolved.pop(legacy_key, None)
            changed = True

    return resolved, changed


def save_settings(settings: Dict[str, Any]) -> None:
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_PATH.write_text(
        json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8"
    )


def init_cda_prompt_context(cda: CommonDataArea | None = None) -> Dict[str, Any]:
    """
    Build the startup prompt context dictionary in CDA.
    Executor will consult this dictionary first for {{TAG}} replacement.
    """
    cda = cda or CommonDataArea()
    prompt_context = {
        'UID': str(cda.get_setting('current_user_id', '')),
        'USER_NAME': cda.get_setting('current_username', ''),
        'USER_EMAIL': cda.get_setting('current_user_email', ''),
        'USER_ROLE': cda.get_setting('current_user_role_name', cda.get_setting('user_role_name', '')),
        'USER_ROLE_NAME': cda.get_setting('current_user_role_name', cda.get_setting('user_role_name', '')),
        'USER_ROLE_ID': str(cda.get_setting('current_user_role_id', cda.get_setting('user_role_id', ''))),
        'CURRENT_EMPLOYEE_ID': '',
        'CURRENT_EMPLOYEE_CODE': '',
        'CURRENT_EMPLOYEE_NAME': '',
        'CURRENT_EMPLOYEE_DESIGNATION': '',
        'CURRENT_EMPLOYEE_LINKED_USER_ID': '',
        'CURRENT_EMPLOYEE_DETAILS_SUMMARY': '',
        'CURRENT_EMPLOYEE_DETAILS_COUNT': '0',
        'LOCATION': cda.get_setting('location', ''),
        'ACCESSIBLE_DIRECTORIES': cda.get_setting('accessible_directories', []),
        'DEFAULT_DIRECTORY': cda.get_setting('default_directory', ''),
        'PATH_RULES': cda.get_setting('path_rules', ''),
        'CHAT_HISTORY': cda.get_memory('chat_history', ''),
    }
    cda.set_memory('prompt_context_dict', prompt_context)
    return prompt_context


def load_settings_into_cda(cda: CommonDataArea | None = None) -> Dict[str, Any]:
    cda = cda or CommonDataArea()
    settings = load_settings()
    settings, changed = normalize_embedding_settings(settings)
    settings, runtime_paths_changed = normalize_runtime_paths(settings)
    changed = changed or runtime_paths_changed
    if changed:
        save_settings(settings)
    for key, value in settings.items():
        cda.set_setting(key, value)
    init_cda_prompt_context(cda)
    return settings


def update_setting(key: str, value: Any) -> Dict[str, Any]:
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
    return settings
