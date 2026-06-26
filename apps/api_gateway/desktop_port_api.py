"""Desktop UI parity endpoints for the web client."""

from __future__ import annotations

import json
import base64
import binascii
import os
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import auth
import db
from agents.registry import register_agent
from core.inbound_request import InboundRequest
from core.scheduler_agent import compute_next_run, validate_schedule_request
from tools.gmail_tools import send_gmail_email
from tools.tool_registry import list_tool_metadata, reload_tool_registry, sync_tools_to_db

router = APIRouter(prefix="/uiport", tags=["uiport"], dependencies=[Depends(auth._require_session)])


@dataclass
class ChatJobState:
    request_id: str
    session_id: str
    user_id: str
    log_path: str
    created_at: str
    status: str = "queued"
    content: str = ""
    done: bool = False
    ui_feedback: List[Dict[str, Any]] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    trace_seq: int = 0
    ui_seq: int = 0


_CHAT_JOBS: Dict[str, ChatJobState] = {}
_CHAT_JOBS_LOCK = threading.RLock()


def _chat_log_root(cda: Any) -> Path:
    configured = str(getattr(cda, "get_setting", lambda *_: "")("logs_path", "") or "").strip()
    base = Path(configured) if configured else (Path.cwd() / "runtime" / "logs")
    if not base.is_absolute():
        base = (Path.cwd() / base).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _create_chat_job(cda: Any, session_id: str, user_id: str, request_id: str) -> ChatJobState:
    log_path = _chat_log_root(cda) / f"web_chat_{request_id}.log"
    job = ChatJobState(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        log_path=str(log_path),
        created_at=datetime.utcnow().isoformat() + "Z",
    )
    with _CHAT_JOBS_LOCK:
        _CHAT_JOBS[request_id] = job
    return job


def _append_chat_job_log(job: ChatJobState, event_type: str, payload: Dict[str, Any]) -> None:
    try:
        with open(job.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": datetime.utcnow().isoformat() + "Z",
                "eventType": str(event_type or "").strip() or "trace",
                "payload": payload if isinstance(payload, dict) else {"value": str(payload)},
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _job_trace_callback(job: ChatJobState, event_type: str, data: Dict[str, Any]) -> None:
    payload = data if isinstance(data, dict) else {"value": str(data)}
    with _CHAT_JOBS_LOCK:
        job.trace_seq += 1
        item = {
            "idx": job.trace_seq,
            "eventType": str(event_type or "").strip() or "trace",
            "payload": payload,
        }
        job.trace.append(item)
    _append_chat_job_log(job, item["eventType"], payload)


def _job_status_callback(job: ChatJobState, message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    feedback = {
        "status": "working",
        "message": text,
        "progress_hint": "",
    }
    with _CHAT_JOBS_LOCK:
        job.ui_seq += 1
        item = {"idx": job.ui_seq, **feedback}
        job.ui_feedback.append(item)
    _append_chat_job_log(job, "tool_status", feedback)


def _job_ui_callback(job: ChatJobState, feedback: Dict[str, Any]) -> None:
    if not isinstance(feedback, dict):
        return
    message = str(feedback.get("message", "") or "").strip()
    hint = str(feedback.get("progress_hint", "") or "").strip()
    status = str(feedback.get("status", "") or "").strip()
    if not message and not hint and not status:
        return
    entry = {
        "status": status or "working",
        "message": message,
        "progress_hint": hint,
    }
    with _CHAT_JOBS_LOCK:
        job.ui_seq += 1
        item = {"idx": job.ui_seq, **entry}
        job.ui_feedback.append(item)
    _append_chat_job_log(job, "ui_feedback", entry)


def _get_cda(request: Request):
    cda = getattr(request.app.state, "cda", None)
    if cda is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return cda


def _get_conversation_manager(request: Request):
    mgr = getattr(request.app.state, "conversation_manager", None)
    if mgr is None:
        raise HTTPException(status_code=503, detail="Conversation manager not initialized")
    return mgr


def _get_whatsapp_headless(request: Request):
    cda = _get_cda(request)
    svc = cda.get_runtime("whatsapp_headless_bridge_service")
    if svc is None:
        from whatsapp_headless_bridge import WhatsAppHeadlessBridgeService

        svc = WhatsAppHeadlessBridgeService(cda=cda)
        cda.set_runtime("whatsapp_headless_bridge_service", svc)
    return svc


def _api_bind_info(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    host = str(getattr(request.app.state, "api_bind_host", "") or cda.get_setting("api_host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(getattr(request.app.state, "api_bind_port", 0) or cda.get_setting("api_port", 8787) or 8787)
    except Exception:
        port = 8787
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::", "*"} else host
    running = _is_port_open(probe_host, port)
    scheme = "https" if str(request.url.scheme).lower() == "https" else "http"
    return {
        "running": running,
        "started": running,
        "host": host,
        "port": port,
        "path": "/",
        "url": f"{scheme}://{host}:{port}/",
        "source": "api_gateway",
    }



def _conn(cda: Any):
    return db.connect(cda)


def _fetch_rows(cur: sqlite3.Cursor, sql: str, params: tuple[Any, ...] = ()) -> List[dict]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def _request_user_id(request: Request) -> str:
    session = getattr(request.state, "session", {}) or {}
    return str(session.get("user_id", "") or "").strip()


def _request_is_admin(request: Request) -> bool:
    session = getattr(request.state, "session", {}) or {}
    return int(session.get("is_admin") or 0) == 1


def _history_access_where(
    cols: set[str],
    user_id: str,
    table_alias: str = "ChatHistory",
    *,
    include_all: bool = False,
) -> Tuple[str, tuple[Any, ...]]:
    if include_all:
        return "", ()
    if "user_id" not in cols or not str(user_id or "").strip():
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    return f" WHERE ({prefix}user_id = ? OR {prefix}user_id IS NULL OR {prefix}user_id = '')", (str(user_id),)


def _history_rows_to_context(rows: List[dict]) -> str:
    lines: List[str] = []
    for row in rows:
        role = str(row.get("role", "") or "").strip().lower()
        content = str(row.get("content", "") or "").strip()
        if not content or role == "status":
            continue
        prefix = "User: " if role == "user" else "Agent: "
        lines.append(f"{prefix}{content}")
    return "\n".join(lines)


def _history_rows_to_chat_lines(rows: List[dict]) -> List[dict]:
    out: List[dict] = []
    for row in rows:
        role = str(row.get("role", "") or "").strip().lower()
        content = str(row.get("content", "") or "").strip()
        if not content or role == "status":
            continue
        out.append(
            {
                "id": row.get("id"),
                "role": "user" if role == "user" else "assistant",
                "text": content,
                "timestamp": row.get("timestamp", ""),
            }
        )
    return out


def _tail_lines(path: Path, limit: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if limit <= 0:
        limit = 200
    return "\n".join(lines[-limit:])


def _safe_attachment_name(name: Any, fallback: str = "attachment.bin") -> str:
    raw = str(name or "").strip()
    candidate = Path(raw).name if raw else fallback
    candidate = re.sub(r'[\\/:*?"<>|]+', "_", candidate)
    candidate = candidate.strip(" .")
    return candidate[:180] or fallback


def _web_upload_root(cda: Any) -> Path:
    configured = str(cda.get_setting("file_storage_path", "storage/files") or "storage/files").strip() or "storage/files"
    base = Path(configured)
    if not base.is_absolute():
        base = (Path.cwd() / base).resolve()
    return base / "web_chat_uploads"


def _decode_base64_payload(value: str) -> bytes:
    payload = str(value or "").strip()
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[1] if "," in payload else ""
    if not payload:
        raise ValueError("Empty base64 payload")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 payload") from exc


def _materialize_chat_files(cda: Any, session_id: str, request_id: str, files_any: Any) -> Tuple[list[str], str]:
    if files_any is None:
        return [], ""
    if not isinstance(files_any, list):
        return [], "Field 'files' must be a list"

    resolved: list[str] = []
    upload_root = _web_upload_root(cda)
    max_upload_bytes = 20 * 1024 * 1024
    for idx, item in enumerate(files_any, start=1):
        if isinstance(item, str):
            candidate = item.strip()
            if candidate:
                resolved.append(candidate)
            continue

        if not isinstance(item, dict):
            return [], f"Invalid files[{idx}] entry"

        payload = str(item.get("data_base64", "") or "").strip()
        if not payload:
            path_value = str(item.get("path", "") or item.get("file_path", "") or "").strip()
            if path_value:
                resolved.append(path_value)
                continue
            return [], f"Missing files[{idx}].data_base64"

        try:
            blob = _decode_base64_payload(payload)
        except ValueError as exc:
            return [], f"Invalid files[{idx}] payload: {exc}"

        if len(blob) > max_upload_bytes:
            return [], f"files[{idx}] exceeds max size ({max_upload_bytes} bytes)"

        name = _safe_attachment_name(item.get("filename") or item.get("name"), fallback=f"attachment_{idx}.bin")
        target_dir = upload_root / _safe_attachment_name(session_id, "session")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{request_id}_{idx}_{name}"
        try:
            target.write_bytes(blob)
        except Exception as exc:
            return [], f"Failed to persist files[{idx}]: {exc}"
        resolved.append(str(target.resolve()))

    return resolved, ""



def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except Exception:
        return False


def _find_windows_pid_by_port(port: int) -> int:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return 0

    needle = f":{int(port)}"
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if "LISTENING" not in line:
            continue
        if needle not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            return int(parts[-1])
        except Exception:
            continue
    return 0


def _kill_pid_windows(pid: int) -> bool:
    if int(pid) <= 0:
        return False
    result = subprocess.run(
        ["taskkill", "/PID", str(int(pid)), "/F"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.returncode == 0


def _start_web_ui_process() -> bool:
    root = Path(__file__).resolve().parents[2]
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_path = logs_dir / "ui_web.out.log"
    err_path = logs_dir / "ui_web.err.log"
    with out_path.open("a", encoding="utf-8") as out_fh, err_path.open("a", encoding="utf-8") as err_fh:
        subprocess.Popen(
            [
                "npm.cmd",
                "--prefix",
                "apps/ui_web",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
                "--strictPort",
            ],
            cwd=str(root),
            stdout=out_fh,
            stderr=err_fh,
            stdin=subprocess.DEVNULL,
            creationflags=0x00000008,
        )
    return True


def _start_api_process() -> bool:
    root = Path(__file__).resolve().parents[2]
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_path = logs_dir / "api_start.out.log"
    err_path = logs_dir / "api_start.err.log"
    with out_path.open("a", encoding="utf-8") as out_fh, err_path.open("a", encoding="utf-8") as err_fh:
        subprocess.Popen(
            [sys.executable, "api_start.py"],
            cwd=str(root),
            stdout=out_fh,
            stderr=err_fh,
            stdin=subprocess.DEVNULL,
            creationflags=0x00000008,
        )
    return True


def _delayed_exit(delay_seconds: float = 0.8) -> None:
    def _run() -> None:
        time.sleep(max(0.2, float(delay_seconds)))
        os._exit(0)

    threading.Thread(target=_run, daemon=True).start()
def _logs_candidates() -> Dict[str, List[Path]]:
    root = Path(__file__).resolve().parents[2]
    core_logs = root / "apps" / "das_core" / "logs"
    api_logs = root / "logs"

    def _latest(pattern: str) -> List[Path]:
        if not core_logs.exists():
            return []
        files = sorted(core_logs.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:1]

    return {
        "execution": _latest("detailed_*.log"),
        "prompts": _latest("prompts_*.log"),
        "history": _latest("chat_history_*.log"),
        "telegram": [core_logs / "telegram_channel.log"],
        "whatsapp": [core_logs / "whatsapp_bridge.log", root / "logs" / "whatsapp_bridge.log"],
        "api": [api_logs / "api_start.out.log", api_logs / "api_start.err.log"],
    }


class LogRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    lines: int = Field(default=200, ge=10, le=2000)


class TelegramTestRequest(BaseModel):
    chat_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


class WhatsAppTestRequest(BaseModel):
    to: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=2000)


class EmailTestRequest(BaseModel):
    to: str = Field(min_length=1, max_length=320)
    subject: str = Field(min_length=1, max_length=400)
    body: str = Field(min_length=1, max_length=10000)


class WhatsAppHeadlessRegisterRequest(BaseModel):
    phone_number: str = Field(min_length=5, max_length=32)
    base_folder: str = Field(default="", max_length=1024)


class WhatsAppHeadlessDaemonRequest(BaseModel):
    base_folder: str = Field(default="", max_length=1024)



class WebChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    message: str = ""
    files: List[Dict[str, Any] | str] = Field(default_factory=list)


class WebChatStopRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)


class AgentSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    prompt_content: str = Field(min_length=1)
    is_active: bool = True
    tools: List[str] = Field(default_factory=list)


class AgentRestoreRequest(BaseModel):
    version: int = Field(ge=1)


class RoleSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    agent_names: List[str] = Field(default_factory=list)


class ToolDescriptionRequest(BaseModel):
    description: str = ""


class SchedulerValidateRequest(BaseModel):
    request: str = Field(min_length=1)


class SchedulerSaveRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    task_prompt: str = Field(min_length=1)
    schedule_type: str = Field(default="other")
    interval_minutes: int = 0
    run_hour: int = 9
    run_minute: int = 0
    run_day_of_week: int = 0
    run_day_of_month: int = 1
    timezone: str = "Asia/Calcutta"
    is_enabled: bool = True


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role_id: Optional[int] = None
    role: Optional[str] = None
    shift_id: Optional[int] = None
    shift: Optional[str] = None
    department_id: Optional[int] = None
    department: Optional[str] = None


@router.get("/tab-manifest")
def tab_manifest() -> Dict[str, Any]:
    return {
        "sidebar": ["chat", "history", "sessions", "logs", "settings", "profile"],
        "settings_tabs": [
            "System Settings",
            "AI Config",
            "Agents",
            "Roles",
            "Users",
            "System Tools",
            "Telgram",
            "WhatsApp",
            "Scheduler",
        ],
    }


@router.get("/history")
def history_list(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> Dict[str, Any]:
    cda = _get_cda(request)
    user_id = _request_user_id(request)
    include_all = _request_is_admin(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(ChatHistory)")
        cols = {str(r[1]) for r in cur.fetchall()}
        interface_expr = "interface" if "interface" in cols else "'' as interface"
        where_sql, params = _history_access_where(cols, user_id, include_all=include_all)
        rows = _fetch_rows(
            cur,
            f"SELECT id, title, created_at, {interface_expr} FROM ChatHistory{where_sql} ORDER BY created_at DESC LIMIT ?",
            (*params, int(limit)),
        )
        return {"count": len(rows), "items": rows}
    finally:
        conn.close()


@router.get("/history/{chat_id}")
def history_detail(chat_id: int, request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    user_id = _request_user_id(request)
    include_all = _request_is_admin(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(ChatHistory)")
        ch_cols = {str(r[1]) for r in cur.fetchall()}
        where_sql, params = _history_access_where(ch_cols, user_id, include_all=include_all)
        access_sql = f"id=?{where_sql.replace(' WHERE ', ' AND ', 1)}"
        cur.execute(
            f"SELECT id, title, created_at, agent_activity FROM ChatHistory WHERE {access_sql} LIMIT 1",
            (int(chat_id), *params),
        )
        parent = cur.fetchone()
        if not parent:
            raise HTTPException(status_code=404, detail="Chat history not found")
        rows = _fetch_rows(
            cur,
            "SELECT id, role, content, timestamp FROM ChatLog WHERE chat_id=? ORDER BY timestamp ASC, id ASC",
            (int(chat_id),),
        )
        return {"history": dict(parent), "messages": rows}
    finally:
        conn.close()


@router.post("/history/{chat_id}/resume")
def history_resume(chat_id: int, request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    mgr = _get_conversation_manager(request)
    user_id = _request_user_id(request)
    include_all = _request_is_admin(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="User session missing")

    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(ChatHistory)")
        ch_cols = {str(r[1]) for r in cur.fetchall()}
        where_sql, params = _history_access_where(ch_cols, user_id, include_all=include_all)
        access_sql = f"id=?{where_sql.replace(' WHERE ', ' AND ', 1)}"
        cur.execute(
            f"SELECT id, title, created_at, agent_activity FROM ChatHistory WHERE {access_sql} LIMIT 1",
            (int(chat_id), *params),
        )
        parent = cur.fetchone()
        if not parent:
            raise HTTPException(status_code=404, detail="Chat history not found")

        rows = _fetch_rows(
            cur,
            "SELECT id, role, content, timestamp FROM ChatLog WHERE chat_id=? ORDER BY timestamp ASC, id ASC",
            (int(chat_id),),
        )
    finally:
        conn.close()

    session_id = f"web:chat:{int(chat_id)}"
    history_text = _history_rows_to_context(rows)
    mgr.hydrate_ui_history(
        session_id,
        user_id,
        history_text,
        str(dict(parent).get("agent_activity", "") or ""),
        int(chat_id),
        interface="WEB",
    )
    return {
        "ok": True,
        "session_id": session_id,
        "history": dict(parent),
        "messages": rows,
        "chat_lines": _history_rows_to_chat_lines(rows),
    }


@router.get("/sessions")
def active_sessions(request: Request) -> Dict[str, Any]:
    mgr = _get_conversation_manager(request)
    sessions = mgr.list_active_sessions()
    return {"count": len(sessions), "items": sessions}


@router.get("/logs")
def logs_list() -> Dict[str, Any]:
    cand = _logs_candidates()
    out = {}
    for key, paths in cand.items():
        first = next((p for p in paths if p.exists()), None)
        out[key] = str(first) if first else ""
    return {"logs": out}


@router.post("/logs/read")
def logs_read(payload: LogRequest) -> Dict[str, Any]:
    cand = _logs_candidates()
    key = str(payload.name or "").strip().lower()
    if key not in cand:
        raise HTTPException(status_code=404, detail="Unknown log name")
    path = next((p for p in cand[key] if p.exists()), None)
    if not path:
        return {"name": key, "path": "", "content": ""}
    return {
        "name": key,
        "path": str(path),
        "content": _tail_lines(path, int(payload.lines)),
    }


@router.get("/integrations/status")
def integrations_status(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    tg = cda.get_runtime("telegram_channel_service")
    wa = cda.get_runtime("whatsapp_folder_service")
    sch = cda.get_runtime("scheduler_service")
    ws = _api_bind_info(request)

    return {
        "telegram": tg.get_status() if tg else {"running": False, "enabled": bool(cda.get_setting("telegram_enabled", False))},
        "whatsapp": wa.get_status() if wa else {"running": False, "enabled": bool(cda.get_setting("whatsapp_enabled", False))},
        "scheduler": sch.get_status() if sch else {"running": False, "enabled": bool(cda.get_setting("scheduler_enabled", False))},
        "api": ws,
    }



@router.get("/services/status")
def services_status(request: Request) -> Dict[str, Any]:
    api = _api_bind_info(request)
    return {
        "api": {"running": api["running"], "port": api["port"], "host": api["host"]},
        "web_ui": {"running": _is_port_open("127.0.0.1", 5173), "port": 5173, "pid": _find_windows_pid_by_port(5173)},
    }


@router.post("/services/api/stop")
def service_api_stop(_admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    _delayed_exit(0.8)
    return {"ok": True, "message": "API stop requested"}


@router.post("/services/api/restart")
def service_api_restart(_admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    _start_api_process()
    _delayed_exit(0.8)
    return {"ok": True, "message": "API restart requested"}


@router.post("/services/web-ui/stop")
def service_web_ui_stop(_admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    pid = _find_windows_pid_by_port(5173)
    if pid <= 0:
        return {"ok": False, "error": "Web UI process not found on port 5173"}
    ok = _kill_pid_windows(pid)
    return {"ok": bool(ok), "pid": pid}


@router.post("/services/web-ui/restart")
def service_web_ui_restart(_admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    pid = _find_windows_pid_by_port(5173)
    if pid > 0:
        _kill_pid_windows(pid)
    _start_web_ui_process()
    return {"ok": True, "message": "Web UI restart requested"}

@router.post("/integrations/telegram/restart")
def telegram_restart(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("telegram_channel_service")
    if not svc:
        return {"ok": False, "error": "Telegram service not initialized"}
    status = svc.get_status() if hasattr(svc, "get_status") else {}

    svc.restart()
    return {"ok": True, "status": svc.get_status()}


@router.post("/integrations/telegram/stop")
def telegram_stop(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("telegram_channel_service")
    if not svc:
        return {"ok": False, "error": "Telegram service not initialized", "status": {"running": False}}
    if hasattr(svc, "stop"):
        svc.stop()
    return {"ok": True, "status": svc.get_status() if hasattr(svc, "get_status") else {"running": False}}



@router.post("/integrations/telegram/test-send")
def telegram_test_send(payload: TelegramTestRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("telegram_channel_service")
    if not svc:
        return {"ok": False, "error": "Telegram service not initialized"}
    result = svc.send_text(payload.chat_id, payload.message)
    return {"ok": bool(result.get("ok", False)), "result": result}


@router.post("/integrations/whatsapp/restart")
def whatsapp_restart(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("whatsapp_folder_service")
    if not svc:
        return {"ok": False, "error": "WhatsApp service not initialized"}
    status = svc.get_status() if hasattr(svc, "get_status") else {}

    svc.restart()
    return {"ok": True, "status": svc.get_status()}


@router.post("/integrations/whatsapp/stop")
def whatsapp_stop(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("whatsapp_folder_service")
    if not svc:
        return {"ok": False, "error": "WhatsApp service not initialized", "status": {"running": False}}
    if hasattr(svc, "stop"):
        svc.stop()
    return {"ok": True, "status": svc.get_status() if hasattr(svc, "get_status") else {"running": False}}



@router.post("/integrations/whatsapp/test-send")
def whatsapp_test_send(payload: WhatsAppTestRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("whatsapp_folder_service")
    if not svc:
        return {"ok": False, "error": "WhatsApp service not initialized"}
    result = svc.send_text(payload.to, payload.message)
    return {"ok": bool(result.get("ok", False)), "result": result}


@router.post("/integrations/email/test-send")
def email_test_send(payload: EmailTestRequest, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    result = send_gmail_email(
        to=payload.to,
        subject=payload.subject,
        body=payload.body,
    )
    return {"ok": bool(result.get("success", False)), "result": result}




@router.get("/integrations/whatsapp/headless/status")
def whatsapp_headless_status(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    svc = _get_whatsapp_headless(request)
    return {"ok": True, "status": svc.get_status()}


@router.post("/integrations/whatsapp/headless/register/start")
def whatsapp_headless_register_start(
    payload: WhatsAppHeadlessRegisterRequest,
    request: Request,
    _admin: Dict[str, Any] = Depends(auth._require_admin),
) -> Dict[str, Any]:
    svc = _get_whatsapp_headless(request)
    try:
        status = svc.start_registration(payload.phone_number, payload.base_folder)
        return {"ok": True, "status": status}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status": svc.get_status()}


@router.post("/integrations/whatsapp/headless/register/stop")
def whatsapp_headless_register_stop(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    svc = _get_whatsapp_headless(request)
    status = svc.stop_registration()
    return {"ok": True, "status": status}


@router.post("/integrations/whatsapp/headless/logout")
def whatsapp_headless_logout(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    svc = _get_whatsapp_headless(request)
    status = svc.logout()
    return {"ok": True, "status": status}


@router.post("/integrations/whatsapp/headless/daemon/start")
def whatsapp_headless_daemon_start(
    payload: WhatsAppHeadlessDaemonRequest,
    request: Request,
    _admin: Dict[str, Any] = Depends(auth._require_admin),
) -> Dict[str, Any]:
    svc = _get_whatsapp_headless(request)
    cda = _get_cda(request)
    try:
        svc.stop_registration()
        status = svc.start_daemon(payload.base_folder)
        
        cda.set_setting("whatsapp_enabled", True)
        if payload.base_folder:
            cda.set_setting("whatsapp_folder_root", payload.base_folder)
            
        wa_folder = cda.get_runtime("whatsapp_folder_service")
        if wa_folder:
            wa_folder.start()
            
        return {"ok": True, "status": status}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status": svc.get_status()}


@router.post("/integrations/whatsapp/headless/daemon/stop")
def whatsapp_headless_daemon_stop(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    svc = _get_whatsapp_headless(request)
    status = svc.stop_daemon()
    return {"ok": True, "status": status}


@router.post("/chat/send")
def chat_send(payload: WebChatRequest, request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    mgr = _get_conversation_manager(request)
    user_id = _request_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="User session missing")

    session_id = str(payload.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    message = str(payload.message or "")
    if not message.strip() and not payload.files:
        raise HTTPException(status_code=400, detail="message or files required")

    request_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    files, files_error = _materialize_chat_files(cda, session_id, request_id, payload.files)
    if files_error:
        raise HTTPException(status_code=400, detail=files_error)

    job = _create_chat_job(cda, session_id, user_id, request_id)
    _append_chat_job_log(
        job,
        "user_input",
        {"message": message, "files": files, "interface": "WEB", "interface_type": "WEB"},
    )

    def _complete_callback(response: Any) -> None:
        status = str(getattr(response, "status", "") or "")
        content = str(getattr(response, "content", "") or "")
        ui_feedback = getattr(response, "ui_feedback", [])
        with _CHAT_JOBS_LOCK:
            job.status = status or ("error" if not content else "complete")
            job.content = content
            job.done = True
            if isinstance(ui_feedback, list):
                for feedback in ui_feedback:
                    _job_ui_callback(job, feedback)
        _append_chat_job_log(job, "completion", {"status": job.status, "content": content})

    mgr.submit(
        InboundRequest(
            conversation_id=session_id,
            interface="WEB",
            user_id=user_id,
            message=message,
            files=files,
            execution_metadata={"execution_source": "http", "user_id": user_id, "request_id": request_id},
            ui_callback=lambda feedback: _job_ui_callback(job, feedback),
            status_callback=lambda text: _job_status_callback(job, text),
            trace_callback=lambda event_type, data: _job_trace_callback(job, event_type, data),
            completion_callback=_complete_callback,
        )
    )
    return {
        "ok": True,
        "accepted": True,
        "request_id": request_id,
        "session_id": session_id,
        "log_path": job.log_path,
        "status": job.status,
        "done": job.done,
    }


@router.post("/chat/stop")
def chat_stop(payload: WebChatStopRequest, request: Request) -> Dict[str, Any]:
    mgr = _get_conversation_manager(request)
    session_id = str(payload.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    return {"ok": True, "cancelled": bool(mgr.cancel(session_id))}


@router.get("/chat/status/{request_id}")
def chat_status(request_id: str, request: Request) -> Dict[str, Any]:
    user_id = _request_user_id(request)
    with _CHAT_JOBS_LOCK:
        job = _CHAT_JOBS.get(str(request_id or "").strip())
        if job is None:
            raise HTTPException(status_code=404, detail="Chat request not found")
        if str(job.user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="Chat request access denied")
        return {
            "ok": True,
            "request_id": job.request_id,
            "session_id": job.session_id,
            "status": job.status,
            "content": job.content,
            "done": job.done,
            "error": job.error,
            "ui_feedback": list(job.ui_feedback),
            "trace": list(job.trace),
            "log_path": job.log_path,
            "created_at": job.created_at,
        }



@router.get("/agents")
def agents_list(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        rows = _fetch_rows(
            cur,
            "SELECT id, name, description, prompt_content, version, is_active, created_at FROM Agents ORDER BY name",
        )
        for row in rows:
            cur.execute("SELECT tool_name FROM AgentTools WHERE agent_id=? ORDER BY tool_name", (int(row["id"]),))
            row["tools"] = [str(x[0]) for x in cur.fetchall()]
        return {"count": len(rows), "items": rows}
    finally:
        conn.close()


@router.get("/agents/{agent_name}")
def agent_detail(agent_name: str, request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, description, prompt_content, version, is_active, created_at FROM Agents WHERE name=? LIMIT 1",
            (agent_name,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent = dict(row)
        cur.execute("SELECT tool_name FROM AgentTools WHERE agent_id=? ORDER BY tool_name", (int(agent["id"]),))
        agent["tools"] = [str(x[0]) for x in cur.fetchall()]
        cur.execute(
            "SELECT id, version, created_at, prompt_content FROM AgentPromptVersion WHERE agent_id=? OR agent_name=? ORDER BY version DESC, id DESC",
            (int(agent["id"]), agent_name),
        )
        versions = [dict(x) for x in cur.fetchall()]
        return {"agent": agent, "versions": versions}
    finally:
        conn.close()


@router.post("/agents")
def agent_save(payload: AgentSaveRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    register_agent(payload.name.strip(), payload.description.strip(), payload.prompt_content)

    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM Agents WHERE name=? LIMIT 1", (payload.name.strip(),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Agent save failed")
        agent_id = int(row[0])
        cur.execute("UPDATE Agents SET is_active=? WHERE id=?", (1 if payload.is_active else 0, agent_id))

        cur.execute("DELETE FROM AgentTools WHERE agent_id=?", (agent_id,))
        for tool_name in payload.tools:
            t = str(tool_name or "").strip()
            if not t:
                continue
            cur.execute("INSERT OR IGNORE INTO AgentTools (agent_id, tool_name) VALUES (?, ?)", (agent_id, t))

        conn.commit()
        return {"ok": True, "agent_id": agent_id}
    finally:
        conn.close()


@router.post("/agents/{agent_name}/deactivate")
def agent_deactivate(agent_name: str, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE Agents SET is_active=0 WHERE name=?", (agent_name,))
        conn.commit()
        return {"ok": cur.rowcount > 0}
    finally:
        conn.close()


@router.post("/agents/{agent_name}/restore")
def agent_restore(agent_name: str, payload: AgentRestoreRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, prompt_content, version FROM Agents WHERE name=? LIMIT 1", (agent_name,))
        base = cur.fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent_id = int(base[0])
        current_prompt = str(base[1] or "")
        current_version = int(base[2] or 1)

        cur.execute(
            "SELECT prompt_content FROM AgentPromptVersion WHERE (agent_id=? OR agent_name=?) AND version=? ORDER BY id DESC LIMIT 1",
            (agent_id, agent_name, int(payload.version)),
        )
        old = cur.fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Version not found")
        restored_prompt = str(old[0] or "")

        cur.execute(
            "INSERT INTO AgentPromptVersion (agent_id, agent_name, prompt_content, version) VALUES (?, ?, ?, ?)",
            (agent_id, agent_name, current_prompt, current_version),
        )
        cur.execute(
            "UPDATE Agents SET prompt_content=?, version=?, is_active=1 WHERE id=?",
            (restored_prompt, current_version + 1, agent_id),
        )
        conn.commit()
        return {"ok": True, "agent_id": agent_id, "new_version": current_version + 1}
    finally:
        conn.close()


@router.get("/roles")
def roles_list(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        rows = _fetch_rows(cur, "SELECT id, name, description FROM Roles ORDER BY name")
        for row in rows:
            cur.execute(
                """
                SELECT a.name
                FROM RoleAgents ra
                JOIN Agents a ON a.id = ra.agent_id
                WHERE ra.role_id=?
                ORDER BY a.name
                """,
                (int(row["id"]),),
            )
            row["agents"] = [str(x[0]) for x in cur.fetchall()]
        return {"count": len(rows), "items": rows}
    finally:
        conn.close()


@router.post("/roles")
def role_save(payload: RoleSaveRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")

    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM Roles WHERE name=? LIMIT 1", (name,))
        row = cur.fetchone()
        if row:
            role_id = int(row[0])
            cur.execute("UPDATE Roles SET description=? WHERE id=?", (payload.description.strip(), role_id))
        else:
            cur.execute("INSERT INTO Roles (name, description) VALUES (?, ?)", (name, payload.description.strip()))
            role_id = int(cur.lastrowid)

        cur.execute("DELETE FROM RoleAgents WHERE role_id=?", (role_id,))
        for agent_name in payload.agent_names:
            a = str(agent_name or "").strip()
            if not a:
                continue
            cur.execute("SELECT id FROM Agents WHERE name=? LIMIT 1", (a,))
            arow = cur.fetchone()
            if arow:
                cur.execute("INSERT OR IGNORE INTO RoleAgents (role_id, agent_id) VALUES (?, ?)", (role_id, int(arow[0])))

        conn.commit()
        return {"ok": True, "role_id": role_id}
    finally:
        conn.close()


@router.delete("/roles/{role_id}")
def role_delete(role_id: int, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM RoleAgents WHERE role_id=?", (int(role_id),))
        cur.execute("DELETE FROM Roles WHERE id=?", (int(role_id),))
        conn.commit()
        return {"ok": cur.rowcount > 0}
    finally:
        conn.close()


@router.put("/users/{user_id}")
def user_update(user_id: int, payload: UserUpdateRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    updates: Dict[str, Any] = {}
    fields_set = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))

    if payload.username is not None:
        updates["username"] = payload.username.strip()
    if payload.email is not None:
        updates["email"] = payload.email.strip().lower()
    if payload.mobile_number is not None:
        updates["mobile_number"] = payload.mobile_number.strip()
    if payload.whatsapp_number is not None:
        updates["whatsapp_number"] = payload.whatsapp_number.strip()
    if payload.telegram_chat_id is not None:
        updates["telegram_chat_id"] = payload.telegram_chat_id.strip()
    if payload.is_active is not None:
        updates["is_active"] = 1 if payload.is_active else 0
    if payload.is_admin is not None:
        updates["is_admin"] = 1 if payload.is_admin else 0
    if "role_id" in fields_set:
        updates["role_id"] = int(payload.role_id) if payload.role_id is not None else None
    if payload.role is not None:
        updates["role"] = payload.role.strip()
    if "shift_id" in fields_set:
        updates["shiftID"] = int(payload.shift_id) if payload.shift_id is not None else None
    if payload.shift is not None:
        updates["shift"] = payload.shift.strip()
    if "department_id" in fields_set:
        updates["department_id"] = int(payload.department_id) if payload.department_id is not None else None
    if payload.department is not None:
        updates["department"] = payload.department.strip()

    if not updates:
        return {"ok": True, "updated": 0}

    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(Users)")
        allowed = {str(r[1]) for r in cur.fetchall()}

        sets = []
        vals: List[Any] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            sets.append(f'"{key}"=?')
            vals.append(value)

        if not sets:
            raise HTTPException(status_code=400, detail="No compatible user columns found")

        vals.append(int(user_id))
        cur.execute(f"UPDATE Users SET {', '.join(sets)} WHERE id=?", tuple(vals))
        conn.commit()
        return {"ok": cur.rowcount > 0, "updated": int(cur.rowcount or 0)}
    finally:
        conn.close()


@router.get("/tools")
def tools_list(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    rows = list_tool_metadata(cda)
    return {"count": len(rows), "items": rows}


@router.post("/tools/refresh")
def tools_refresh(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    reload_tool_registry()
    count = sync_tools_to_db(cda)
    return {"ok": True, "count": count}


@router.put("/tools/{tool_name}/description")
def tools_update_description(tool_name: str, payload: ToolDescriptionRequest, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ToolList SET description=? WHERE name=?", (payload.description, tool_name))
        conn.commit()
        return {"ok": cur.rowcount > 0}
    finally:
        conn.close()


@router.get("/scheduler/status")
def scheduler_status(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("scheduler_service")
    if not svc:
        return {"running": False, "enabled": bool(cda.get_setting("scheduler_enabled", False)), "poll_minutes": int(cda.get_setting("scheduler_poll_minutes", 1) or 1)}
    return svc.get_status()


@router.post("/scheduler/restart")
def scheduler_restart(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("scheduler_service")
    if not svc:
        return {"ok": False, "error": "Scheduler service not initialized"}
    status = svc.get_status() if hasattr(svc, "get_status") else {}
    if not bool(status.get("running")):
        return {"ok": False, "error": "Scheduler service is stopped and cannot be started from UI.", "status": status}
    svc.restart()
    return {"ok": True, "status": svc.get_status()}


@router.post("/scheduler/stop")
def scheduler_stop(request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("scheduler_service")
    if not svc:
        return {"ok": False, "error": "Scheduler service not initialized", "status": {"running": False}}
    if hasattr(svc, "stop"):
        svc.stop()
    return {"ok": True, "status": svc.get_status() if hasattr(svc, "get_status") else {"running": False}}



@router.get("/scheduler")
def scheduler_list(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        rows = _fetch_rows(cur, "SELECT * FROM Schedules ORDER BY id DESC")
        return {"count": len(rows), "items": rows}
    finally:
        conn.close()


@router.post("/scheduler/validate")
def scheduler_validate(payload: SchedulerValidateRequest, request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    parsed = validate_schedule_request(payload.request, cda)
    return parsed


def _schedule_next_run_text(record: Dict[str, Any]) -> str:
    next_dt = compute_next_run(record, now=datetime.now())
    return next_dt.strftime("%Y-%m-%d %H:%M:%S")


@router.post("/scheduler")
def scheduler_create(payload: SchedulerSaveRequest, request: Request, session: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    rec = {
        "schedule_type": payload.schedule_type,
        "interval_minutes": payload.interval_minutes,
        "run_hour": payload.run_hour,
        "run_minute": payload.run_minute,
        "run_day_of_week": payload.run_day_of_week,
        "run_day_of_month": payload.run_day_of_month,
    }
    next_run = _schedule_next_run_text(rec)

    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO Schedules (
                title, nl_request, task_prompt, schedule_type,
                interval_minutes, run_hour, run_minute, run_day_of_week, run_day_of_month,
                timezone, is_enabled, status, next_run_at, owner, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                payload.title.strip(),
                payload.task_prompt.strip(),
                payload.task_prompt.strip(),
                payload.schedule_type.strip().lower(),
                int(payload.interval_minutes),
                int(payload.run_hour),
                int(payload.run_minute),
                int(payload.run_day_of_week),
                int(payload.run_day_of_month),
                payload.timezone.strip(),
                1 if payload.is_enabled else 0,
                next_run,
                str(session.get("user_id") or ""),
                str(session.get("user_id") or ""),
            ),
        )
        conn.commit()
        return {"ok": True, "id": int(cur.lastrowid)}
    finally:
        conn.close()


@router.put("/scheduler/{schedule_id}")
def scheduler_update(schedule_id: int, payload: SchedulerSaveRequest, request: Request, session: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    rec = {
        "schedule_type": payload.schedule_type,
        "interval_minutes": payload.interval_minutes,
        "run_hour": payload.run_hour,
        "run_minute": payload.run_minute,
        "run_day_of_week": payload.run_day_of_week,
        "run_day_of_month": payload.run_day_of_month,
    }
    next_run = _schedule_next_run_text(rec)

    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE Schedules
            SET title=?, nl_request=?, task_prompt=?, schedule_type=?,
                interval_minutes=?, run_hour=?, run_minute=?, run_day_of_week=?, run_day_of_month=?,
                timezone=?, is_enabled=?, next_run_at=?, owner=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                payload.title.strip(),
                payload.task_prompt.strip(),
                payload.task_prompt.strip(),
                payload.schedule_type.strip().lower(),
                int(payload.interval_minutes),
                int(payload.run_hour),
                int(payload.run_minute),
                int(payload.run_day_of_week),
                int(payload.run_day_of_month),
                payload.timezone.strip(),
                1 if payload.is_enabled else 0,
                next_run,
                str(session.get("user_id") or ""),
                int(schedule_id),
            ),
        )
        conn.commit()
        return {"ok": cur.rowcount > 0}
    finally:
        conn.close()


@router.delete("/scheduler/{schedule_id}")
def scheduler_delete(schedule_id: int, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    conn = _conn(cda)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM Schedules WHERE id=?", (int(schedule_id),))
        conn.commit()
        return {"ok": cur.rowcount > 0}
    finally:
        conn.close()


@router.post("/scheduler/{schedule_id}/run")
def scheduler_run_now(schedule_id: int, request: Request, _admin: Dict[str, Any] = Depends(auth._require_admin)) -> Dict[str, Any]:
    cda = _get_cda(request)
    svc = cda.get_runtime("scheduler_service")
    if not svc:
        return {"ok": False, "error": "Scheduler service not initialized"}
    result = svc.run_schedule_now(int(schedule_id))
    return {"ok": True, "result": result}








