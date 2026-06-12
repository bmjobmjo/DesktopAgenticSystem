"""DAS API gateway entrypoint."""

from __future__ import annotations

import logging as _stdlib_logging
import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.modules.setdefault("logging", _stdlib_logging)

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parents[1]
_DAS_CORE_ROOT = _ROOT / "apps" / "das_core"
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
if str(_DAS_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAS_CORE_ROOT))

import auth
import db
import desktop_port_api
from core.db_schema import init_db
from runtime import registry
from security import hash_password
from settings_api import router as settings_router

def _bootstrap_runtime() -> tuple[object, object]:
    cda, conversation_manager = registry.get_or_init()
    # Ensure core DAS schema exists (Users, ToolList, etc.) before API auth schema migration.
    init_db()
    db.ensure_api_schema(cda)

    admin_username = str(os.getenv("DAS_BOOTSTRAP_ADMIN_USERNAME", "admin")).strip() or "admin"
    admin_email = str(os.getenv("DAS_BOOTSTRAP_ADMIN_EMAIL", "admin@local")).strip() or "admin@local"
    admin_password = str(os.getenv("DAS_BOOTSTRAP_ADMIN_PASSWORD", "admin123")).strip() or "admin123"
    db.ensure_default_admin(
        cda,
        username=admin_username,
        email=admin_email,
        password_hash_value=hash_password(admin_password),
    )

    try:
        from whatsapp_headless_bridge import WhatsAppHeadlessBridgeService

        wa_headless = WhatsAppHeadlessBridgeService(cda=cda)
        cda.set_runtime("whatsapp_headless_bridge_service", wa_headless)

        if bool(cda.get_setting("whatsapp_enabled", False)) and wa_headless.has_linked_auth_session():
            base_folder = str(cda.get_setting("whatsapp_folder_root", "") or "").strip()
            wa_headless.start_daemon(base_folder)
    except Exception as exc:
        print(f"WhatsApp headless auto-start skipped: {exc}")

    return cda, conversation_manager


def _resolve_api_bind(cda: object) -> tuple[str, int]:
    host = str(os.getenv("DAS_API_HOST", "") or "").strip()
    if not host:
        host = str(getattr(cda, "get_setting", lambda *_: "127.0.0.1")("api_host", "127.0.0.1") or "127.0.0.1").strip()
    port_raw = str(os.getenv("DAS_API_PORT", "") or "").strip()
    if not port_raw:
        port_raw = str(getattr(cda, "get_setting", lambda *_: 8787)("api_port", 8787) or 8787).strip()
    try:
        port = int(port_raw)
    except Exception:
        port = 8787
    return host or "127.0.0.1", port


cda, conversation_manager = _bootstrap_runtime()
api_host, api_port = _resolve_api_bind(cda)
cda.set_setting("api_host", api_host)
cda.set_setting("api_port", api_port)
app = FastAPI()
app.state.cda = cda
app.state.conversation_manager = conversation_manager
app.state.api_bind_host = api_host
app.state.api_bind_port = api_port
app.title = "DAS API Gateway"
app.version = "0.1.7"

cors_origins = str(os.getenv("DAS_API_CORS_ORIGINS", "*")).strip()
origins = ["*"] if cors_origins == "*" else [x.strip() for x in cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(auth.admin_router)
app.include_router(settings_router, dependencies=[Depends(auth._require_session)])
app.include_router(desktop_port_api.router)


@app.on_event("shutdown")
async def _shutdown_runtime() -> None:
    registry.shutdown()


@app.get("/")
def root() -> dict:
    return {
        "ok": True,
        "service": "das-api-gateway",
        "auth": ["/auth/login", "/auth/me", "/auth/logout", "/auth/change-password"],
    }


if __name__ == "__main__":
    import uvicorn

    host, port = _resolve_api_bind(cda)
    uvicorn.run(app, host=host, port=port, reload=False)

