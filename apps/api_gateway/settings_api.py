"""Settings API endpoints backed by existing DAS settings loader."""

from __future__ import annotations

import logging as _stdlib_logging
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import auth

sys.modules.setdefault("logging", _stdlib_logging)

_ROOT = Path(__file__).resolve().parents[2]
_DAS_CORE_ROOT = _ROOT / "apps" / "das_core"
if str(_DAS_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAS_CORE_ROOT))

from llm.factory import get_llm_client
from settings.config_loader import init_cda_prompt_context, load_settings, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])

AI_RUNTIME_SETTING_KEYS = {
    "llm_provider",
    "gemini_api_key",
    "gemini_model",
    "gemini_temperature",
    "groq_api_key",
    "groq_model",
    "groq_temperature",
    "local_llm_url",
    "local_llm_model",
    "openrouter_api_key",
    "openrouter_model",
    "openrouter_temperature",
    "openrouter_top_p",
    "openrouter_seed",
    "openrouter_provider_order",
    "openrouter_allow_fallbacks",
    "openrouter_require_parameters",
    "openrouter_include_reasoning",
}


class UpdateSettingsRequest(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


@router.get("")
def get_settings() -> Dict[str, Any]:
    return load_settings()


@router.put("")
def put_settings(
    payload: UpdateSettingsRequest,
    request: Request,
    _admin: Dict[str, Any] = Depends(auth._require_admin),
) -> Dict[str, Any]:
    if not isinstance(payload.values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")

    updates = {str(key): value for key, value in payload.values.items()}
    merged = load_settings()
    ai_settings_changed = any(
        key in AI_RUNTIME_SETTING_KEYS and merged.get(key) != value
        for key, value in updates.items()
    )
    merged.update(updates)
    save_settings(merged)

    cda = getattr(request.app.state, "cda", None)
    if cda is not None:
        for key, value in updates.items():
            cda.set_setting(key, value)
        init_cda_prompt_context(cda)
        if ai_settings_changed:
            cda.set_runtime("llm_client", get_llm_client(cda))
            conversation_manager = getattr(request.app.state, "conversation_manager", None)
            if conversation_manager is not None and hasattr(conversation_manager, "refresh_llm_clients"):
                conversation_manager.refresh_llm_clients()
    return merged
