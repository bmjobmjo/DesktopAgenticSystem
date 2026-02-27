"""Settings loader and persistence utilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from core.common_data_area import CommonDataArea

DEFAULTS_PATH = Path(__file__).with_name("defaults.json")
USER_CONFIG_PATH = Path(__file__).with_name("user_config.json")


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
    return merged


def _is_sentence_transformer_model_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    # SentenceTransformer folders usually include modules.json.
    return (path / "modules.json").exists()


def _embedding_search_roots() -> list[Path]:
    roots: list[Path] = []
    roots.append(Path.cwd())
    roots.append(Path(__file__).resolve().parents[1])

    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))

    unique: list[Path] = []
    seen = set()
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_bundled_embedding_model_path(model_name: str) -> str:
    model_name = str(model_name or "").strip()
    if not model_name:
        return ""

    model_leaf = model_name.split("/")[-1].split("\\")[-1]
    candidates = []
    for root in _embedding_search_roots():
        candidates.append(root / "models" / model_name)
        candidates.append(root / "models" / model_leaf)
        candidates.append(root / "resources" / "models" / model_name)
        candidates.append(root / "resources" / "models" / model_leaf)

    seen = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        if _is_sentence_transformer_model_dir(path):
            return str(path.resolve())
    return ""


def apply_bundled_embedding_defaults(settings: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    resolved = dict(settings)
    changed = False

    model_path = str(resolved.get("embedding_model_path", "") or "").strip()
    model_name = str(resolved.get("embedding_model_name", "all-MiniLM-L6-v2") or "all-MiniLM-L6-v2").strip()
    if model_path:
        return resolved, False

    bundled = find_bundled_embedding_model_path(model_name)
    if bundled:
        resolved["embedding_model_path"] = bundled
        if not bool(resolved.get("embedding_local_files_only", False)):
            resolved["embedding_local_files_only"] = True
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
        'USER_ROLE_NAME': cda.get_setting('current_user_role_name', cda.get_setting('user_role_name', '')),
        'USER_ROLE_ID': str(cda.get_setting('current_user_role_id', cda.get_setting('user_role_id', ''))),
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
    settings, changed = apply_bundled_embedding_defaults(settings)
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
