"""Tools for schedule validation and CRUD operations."""

from __future__ import annotations

__tool_exports__ = ['validate_schedule', 'preview_schedule', 'create_schedule', 'list_schedules', 'list_schedule_runs', 'update_schedule', 'delete_schedule', 'run_schedule_now', 'retry_schedule_run']

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.common_data_area import CommonDataArea
from core.scheduler_agent import compute_next_run, validate_schedule_request


def _db_path(cda: CommonDataArea) -> Path:
    return Path(str(cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()


def _normalize_schedule(
    schedule_type: str,
    interval_minutes: int,
    run_hour: int,
    run_minute: int,
    run_day_of_week: int,
    run_day_of_month: int,
) -> Dict[str, int | str]:
    stype = str(schedule_type or "other").strip().lower()
    if stype not in {"hourly", "daily", "weekly", "monthly", "other"}:
        stype = "other"
    out = {
        "schedule_type": stype,
        "interval_minutes": max(0, int(interval_minutes or 0)),
        "run_hour": max(0, min(int(run_hour or 0), 23)),
        "run_minute": max(0, min(int(run_minute or 0), 59)),
        "run_day_of_week": max(0, min(int(run_day_of_week or 0), 6)),
        "run_day_of_month": max(1, min(int(run_day_of_month or 1), 31)),
    }
    return out


def _record_next_run(payload: Dict[str, Any]) -> str:
    next_run = compute_next_run(payload, now=datetime.now())
    return next_run.strftime("%Y-%m-%d %H:%M:%S")


def validate_schedule(nl_request: str) -> Dict[str, Any]:
    """
    Validate a natural-language schedule request and return structured schedule fields.
    """
    cda = CommonDataArea()
    parsed = validate_schedule_request(str(nl_request or ""), cda=cda)
    return {"success": bool(parsed.get("is_valid", False)), "parsed": parsed}


def preview_schedule(nl_request: str) -> Dict[str, Any]:
    """Return a safe, reviewable schedule proposal without creating a schedule."""
    parsed = validate_schedule_request(str(nl_request or ""), cda=CommonDataArea())
    if not parsed.get("is_valid"):
        return {"success": False, "error": parsed.get("reason", "Invalid schedule request"), "parsed": parsed}
    return {"success": True, "proposal": {"title": parsed["title"], "original_request": nl_request, "task_prompt": parsed["task_prompt"], "recurrence": parsed["schedule_type"], "timing": parsed}}


def create_schedule(
    nl_request: str = "",
    title: str = "",
    task_prompt: str = "",
    schedule_type: str = "other",
    interval_minutes: int = 0,
    run_hour: int = 9,
    run_minute: int = 0,
    run_day_of_week: int = 0,
    days_of_week: str = "",
    run_day_of_month: int = 1,
    is_enabled: bool = True,
    owner: str = "",
    created_by: str = "",
) -> Dict[str, Any]:
    """
    Create a schedule. If nl_request is provided, scheduler agent parses/validates it first.
    """
    cda = CommonDataArea()
    parsed: Optional[Dict[str, Any]] = None
    nl_text = str(nl_request or "").strip()
    explicit_title = str(title or "").strip()
    explicit_prompt = str(task_prompt or "").strip()
    explicit_days_of_week = str(days_of_week or "").strip()
    if nl_text:
        parsed = validate_schedule_request(nl_text, cda=cda)
        if not bool(parsed.get("is_valid", False)):
            return {"success": False, "error": str(parsed.get("reason", "Invalid schedule request")), "parsed": parsed}

    prefer_explicit = bool(explicit_title or explicit_prompt or explicit_days_of_week)

    base = _normalize_schedule(
        schedule_type=(schedule_type if prefer_explicit else (parsed or {}).get("schedule_type", schedule_type)),
        interval_minutes=int((interval_minutes if prefer_explicit else (parsed or {}).get("interval_minutes", interval_minutes)) or 0),
        run_hour=int((run_hour if prefer_explicit else (parsed or {}).get("run_hour", run_hour)) or 0),
        run_minute=int((run_minute if prefer_explicit else (parsed or {}).get("run_minute", run_minute)) or 0),
        run_day_of_week=int((run_day_of_week if prefer_explicit else (parsed or {}).get("run_day_of_week", run_day_of_week)) or 0),
        run_day_of_month=int((run_day_of_month if prefer_explicit else (parsed or {}).get("run_day_of_month", run_day_of_month)) or 1),
    )

    effective_prompt = str(explicit_prompt or (parsed or {}).get("task_prompt", "") or nl_text).strip()
    if not effective_prompt:
        return {"success": False, "error": "task_prompt is required"}

    effective_title = str(explicit_title or (parsed or {}).get("title", "") or effective_prompt[:80] or "Scheduled Task").strip()
    created_uid = str(created_by or cda.get_setting("current_user_id", "") or "").strip()
    owner_uid = str(owner or created_uid).strip()

    payload = dict(base)
    payload["days_of_week"] = str(explicit_days_of_week or (parsed or {}).get("days_of_week", "") or "").strip()
    next_run_at = _record_next_run(payload)

    db_path = _db_path(cda)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO Schedules (
                title, nl_request, task_prompt, schedule_type, interval_minutes,
                run_hour, run_minute, run_day_of_week, days_of_week, run_day_of_month,
                is_enabled, status, next_run_at, validation_reason, owner, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                effective_title,
                nl_text,
                effective_prompt,
                payload["schedule_type"],
                payload["interval_minutes"],
                payload["run_hour"],
                payload["run_minute"],
                payload["run_day_of_week"],
                payload["days_of_week"],
                payload["run_day_of_month"],
                1 if bool(is_enabled) else 0,
                next_run_at,
                str((parsed or {}).get("reason", "") or "").strip(),
                owner_uid,
                created_uid,
            ),
        )
        new_id = int(cur.lastrowid or 0)
        conn.commit()
    finally:
        conn.close()

    return {"success": True, "schedule_id": new_id, "next_run_at": next_run_at}


def list_schedules(include_disabled: bool = True, limit: int = 200) -> Dict[str, Any]:
    """
    List schedules from the database.
    """
    cda = CommonDataArea()
    db_path = _db_path(cda)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        lim = max(1, min(int(limit or 200), 1000))
        if include_disabled:
            cur.execute("SELECT * FROM Schedules ORDER BY id DESC LIMIT ?", (lim,))
        else:
            cur.execute("SELECT * FROM Schedules WHERE is_enabled=1 ORDER BY id DESC LIMIT ?", (lim,))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return {"success": True, "schedules": rows, "count": len(rows)}


def list_schedule_runs(schedule_id: int = 0, status: str = "", limit: int = 100) -> Dict[str, Any]:
    """List newest-first audited scheduler runs, optionally for one schedule."""
    cda = CommonDataArea(); conn = sqlite3.connect(str(_db_path(cda))); conn.row_factory = sqlite3.Row
    try:
        sql, params = "SELECT * FROM ScheduleRuns WHERE 1=1", []
        if int(schedule_id or 0) > 0: sql += " AND schedule_id=?"; params.append(int(schedule_id))
        if status: sql += " AND status=?"; params.append(str(status))
        sql += " ORDER BY COALESCE(started_at,created_at) DESC LIMIT ?"; params.append(max(1, min(int(limit or 100), 500)))
        return {"success": True, "runs": [dict(r) for r in conn.execute(sql, params).fetchall()]}
    finally: conn.close()


def update_schedule(
    schedule_id: int,
    title: str = "",
    nl_request: str = "",
    task_prompt: str = "",
    schedule_type: str = "",
    interval_minutes: int = 0,
    run_hour: int = 9,
    run_minute: int = 0,
    run_day_of_week: int = 0,
    days_of_week: str = "",
    run_day_of_month: int = 1,
    is_enabled: Optional[bool] = None,
    owner: str = "",
) -> Dict[str, Any]:
    """
    Update an existing schedule row.
    """
    sid = int(schedule_id or 0)
    if sid <= 0:
        return {"success": False, "error": "schedule_id must be > 0"}

    cda = CommonDataArea()
    db_path = _db_path(cda)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Schedules WHERE id=? LIMIT 1", (sid,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Schedule {sid} not found"}

        current = dict(row)
        eff_title = str(title or current.get("title", "") or "").strip()
        eff_prompt = str(task_prompt or current.get("task_prompt", "") or "").strip()
        base = _normalize_schedule(
            schedule_type=schedule_type or current.get("schedule_type", "other"),
            interval_minutes=interval_minutes if interval_minutes else int(current.get("interval_minutes", 0) or 0),
            run_hour=run_hour if str(run_hour) != "" else int(current.get("run_hour", 9) or 9),
            run_minute=run_minute if str(run_minute) != "" else int(current.get("run_minute", 0) or 0),
            run_day_of_week=run_day_of_week if str(run_day_of_week) != "" else int(current.get("run_day_of_week", 0) or 0),
            run_day_of_month=run_day_of_month if str(run_day_of_month) != "" else int(current.get("run_day_of_month", 1) or 1),
        )
        eff_nl_request = str(nl_request or current.get("nl_request", "") or "").strip()
        eff_days_of_week = str(days_of_week or current.get("days_of_week", "") or "").strip()
        enabled = int(current.get("is_enabled", 1) or 0) if is_enabled is None else (1 if bool(is_enabled) else 0)
        eff_owner = str(owner or current.get("owner", "") or current.get("created_by", "") or "").strip()
        payload = dict(base)
        payload["days_of_week"] = eff_days_of_week
        next_run_at = _record_next_run(payload)

        cur.execute(
            """
            UPDATE Schedules
            SET title=?, nl_request=?, task_prompt=?, schedule_type=?, interval_minutes=?,
                run_hour=?, run_minute=?, run_day_of_week=?, days_of_week=?, run_day_of_month=?,
                is_enabled=?, next_run_at=?, owner=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                eff_title,
                eff_nl_request,
                eff_prompt,
                base["schedule_type"],
                base["interval_minutes"],
                base["run_hour"],
                base["run_minute"],
                base["run_day_of_week"],
                eff_days_of_week,
                base["run_day_of_month"],
                enabled,
                next_run_at,
                eff_owner,
                sid,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"success": True, "schedule_id": sid}


def delete_schedule(schedule_id: int) -> Dict[str, Any]:
    """
    Delete a schedule by ID.
    """
    sid = int(schedule_id or 0)
    if sid <= 0:
        return {"success": False, "error": "schedule_id must be > 0"}

    cda = CommonDataArea()
    db_path = _db_path(cda)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM Schedules WHERE id=?", (sid,))
        deleted = int(cur.rowcount or 0)
        conn.commit()
    finally:
        conn.close()
    return {"success": bool(deleted > 0), "deleted": deleted, "schedule_id": sid}


def run_schedule_now(schedule_id: int) -> Dict[str, Any]:
    """Run a schedule immediately using the configured scheduler service."""
    sid = int(schedule_id or 0)
    if sid <= 0:
        return {"success": False, "error": "schedule_id must be > 0"}

    cda = CommonDataArea()
    svc = cda.get_runtime("scheduler_service")
    if svc is None:
        return {"success": False, "error": "Scheduler service not initialized"}
    try:
        result = svc.run_schedule_now(sid)
    except Exception as exc:
        return {"success": False, "error": str(exc), "schedule_id": sid}
    return {"success": True, "schedule_id": sid, "result": result}


def retry_schedule_run(run_id: int) -> Dict[str, Any]:
    """Retry a failed schedule run as a new audited execution."""
    cda = CommonDataArea(); svc = cda.get_runtime("scheduler_service")
    if svc is None: return {"success": False, "error": "Scheduler service not initialized"}
    try: return {"success": True, "result": svc.retry_run(int(run_id))}
    except Exception as exc: return {"success": False, "error": str(exc)}


