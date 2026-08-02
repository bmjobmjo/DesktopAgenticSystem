"""Natural-language schedule validation and normalization helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from core.common_data_area import CommonDataArea


_DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_ACTION_HINTS = (
    "send",
    "post",
    "run",
    "generate",
    "create",
    "export",
    "notify",
    "remind",
    "mark",
    "update",
    "submit",
    "sync",
    "backup",
    "email",
    "whatsapp",
    "telegram",
    "report",
    "share",
    "upload",
    "download",
    "refresh",
)


def _extract_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", str(text or ""), re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_time_phrase(value: str) -> tuple[int, int] | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None

    m_12 = re.search(r"\b(\d{1,2})(?:[:.](\d{1,2}))?\s*(am|pm)\b", raw)
    if m_12:
        hour = int(m_12.group(1))
        minute = int(m_12.group(2) or 0)
        suffix = m_12.group(3)
        if hour < 1 or hour > 12 or minute > 59:
            return None
        hour = hour % 12
        if suffix == "pm":
            hour += 12
        return hour, minute

    m_24 = re.search(r"\b(\d{1,2})[:.](\d{1,2})\b", raw)
    if m_24:
        hour = int(m_24.group(1))
        minute = int(m_24.group(2))
        if hour > 23 or minute > 59:
            return None
        return hour, minute

    m_h = re.search(r"\b(?:at|by)\s+(\d{1,2})\b", raw)
    if m_h:
        hour = int(m_h.group(1))
        if hour > 23:
            return None
        return hour, 0

    return None


def _has_action_hint(value: str) -> bool:
    text = f" {str(value or '').strip().lower()} "
    return any(f" {hint} " in text for hint in _ACTION_HINTS)


def _infer_days_of_week(value: str) -> str:
    lower = str(value or "").strip().lower()
    if not lower:
        return ""
    if "monday to friday" in lower or "monday through friday" in lower or "weekdays" in lower:
        return "0,1,2,3,4"
    if "saturday to sunday" in lower or "saturday through sunday" in lower or "weekends" in lower:
        return "5,6"

    days: list[int] = []
    for day, idx in _DAY_INDEX.items():
        if re.search(rf"\b{day}\b", lower) and idx not in days:
            days.append(idx)
    days.sort()
    if len(days) <= 1:
        return ""
    return ",".join(str(idx) for idx in days)


def _extract_task_prompt(nl_request: str) -> str:
    text = str(nl_request or "").strip()
    if not text:
        return ""

    for sep in (":", " - ", " then "):
        if sep in text:
            right = text.split(sep, 1)[1].strip()
            if len(right) >= 3 and _has_action_hint(right):
                return right

    lead_task = re.match(
        r"^(?P<task>.+?)\s+\b(?:at|by)\s+\d{1,2}(?:[:.]\d{1,2})?\s*(?:am|pm)\b.*$",
        text,
        re.IGNORECASE,
    )
    if lead_task:
        candidate = str(lead_task.group("task") or "").strip(" ,.-")
        if _has_action_hint(candidate):
            return candidate

    trailing_task = re.match(
        r"^(?:(?:every\s+)?(?:weekday|weekdays|day|daily|week|weekly|month|monthly|hourly)|"
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+(?:to|through)\s+"
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))?)\b.*?(?P<task>[A-Za-z].+)$",
        text,
        re.IGNORECASE,
    )
    if trailing_task:
        candidate = str(trailing_task.group("task") or "").strip(" ,.-")
        if _has_action_hint(candidate):
            return candidate

    if _has_action_hint(text):
        return text
    return ""


def _fallback_parse(nl_request: str) -> Dict[str, Any]:
    text = str(nl_request or "").strip()
    lower = text.lower()
    task_prompt = _extract_task_prompt(text)
    parsed_time = _parse_time_phrase(lower)
    days_of_week = _infer_days_of_week(lower)
    parsed: Dict[str, Any] = {
        "is_valid": False,
        "reason": "Could not detect schedule pattern.",
        "title": task_prompt[:80] or "Scheduled Task",
        "task_prompt": task_prompt,
        "schedule_type": "other",
        "interval_minutes": 0,
        "run_hour": 9 if parsed_time is None else parsed_time[0],
        "run_minute": 0 if parsed_time is None else parsed_time[1],
        "run_day_of_week": 0,
        "run_day_of_month": 1,
        "days_of_week": days_of_week,
        "schedule_mode": "recurring",
        "run_at": "",
    }

    if "tomorrow" in lower:
        hour, minute = parsed_time if parsed_time is not None else (9, 0)
        run_at = (datetime.now() + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        parsed.update({"is_valid": True, "reason": "Parsed as one-time schedule tomorrow.", "schedule_type": "other", "interval_minutes": 1, "schedule_mode": "once", "run_at": run_at.strftime("%Y-%m-%d %H:%M:%S")})
        return parsed

    m_every_min = re.search(r"every\s+(\d+)\s*minute", lower)
    if m_every_min:
        mins = max(1, int(m_every_min.group(1)))
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as fixed minute interval.",
                "schedule_type": "other",
                "interval_minutes": mins,
            }
        )
        return parsed

    m_every_hour = re.search(r"every\s+(\d+)\s*hour", lower)
    if m_every_hour:
        hrs = max(1, int(m_every_hour.group(1)))
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as hourly interval.",
                "schedule_type": "hourly",
                "interval_minutes": hrs * 60,
            }
        )
        return parsed
    if "hourly" in lower or "every hour" in lower:
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as hourly cadence.",
                "schedule_type": "hourly",
                "interval_minutes": 60,
            }
        )
        return parsed

    if "daily" in lower or "every day" in lower:
        hour, minute = parsed_time if parsed_time is not None else (9, 0)
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as daily cadence.",
                "schedule_type": "daily",
                "run_hour": hour,
                "run_minute": minute,
            }
        )
        return parsed

    if days_of_week:
        hour, minute = parsed_time if parsed_time is not None else (9, 0)
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as selected weekdays cadence.",
                "schedule_type": "daily",
                "run_hour": hour,
                "run_minute": minute,
                "days_of_week": days_of_week,
            }
        )
        return parsed

    if "weekly" in lower or "every week" in lower or any(day in lower for day in _DAY_INDEX):
        hour, minute = parsed_time if parsed_time is not None else (9, 0)
        dow = 0
        for day, idx in _DAY_INDEX.items():
            if day in lower:
                dow = idx
                break
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as weekly cadence.",
                "schedule_type": "weekly",
                "run_hour": hour,
                "run_minute": minute,
                "run_day_of_week": dow,
            }
        )
        return parsed

    if "monthly" in lower or "every month" in lower:
        hour, minute = parsed_time if parsed_time is not None else (9, 0)
        m_day = re.search(r"\b(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?\b", lower)
        dom = int(m_day.group(1)) if m_day else 1
        dom = max(1, min(dom, 31))
        parsed.update(
            {
                "is_valid": True,
                "reason": "Parsed as monthly cadence.",
                "schedule_type": "monthly",
                "run_hour": hour,
                "run_minute": minute,
                "run_day_of_month": dom,
            }
        )
        return parsed

    return parsed


def validate_schedule_request(nl_request: str, cda: Optional[CommonDataArea] = None) -> Dict[str, Any]:
    cda = cda or CommonDataArea()
    llm = cda.get_runtime("llm_client")

    if llm is not None:
        parser_prompt = f"""
You are a scheduler agent. Parse the user's schedule request into strict JSON.
Allowed schedule_type: hourly, daily, weekly, monthly, other

Rules:
- task_prompt = the actual work that should execute.
- hourly: use interval_minutes (>= 60 usually)
- daily: use run_hour (0-23), run_minute (0-59)
- weekly: use run_day_of_week (0=Mon..6=Sun), run_hour, run_minute
- monthly: use run_day_of_month (1-31), run_hour, run_minute
- other: use interval_minutes if periodic else mark invalid
- If unclear, set is_valid=false with reason.

Return JSON only with keys:
is_valid, reason, title, task_prompt, schedule_type, interval_minutes, run_hour, run_minute, run_day_of_week, run_day_of_month, days_of_week, schedule_mode, run_at

User request:
{nl_request}
"""
        try:
            raw = llm.generate(
                parser_prompt,
                agent_name="SchedulerAgent",
                user_prompt="Validate schedule request",
            )
            data = _extract_json_object(raw)
            if data:
                return _normalize_schedule_payload(data, nl_request)
        except Exception:
            pass

    return _normalize_schedule_payload(_fallback_parse(nl_request), nl_request)


def _normalize_schedule_payload(payload: Dict[str, Any], source_text: str = "") -> Dict[str, Any]:
    task_prompt = str(payload.get("task_prompt", "") or "").strip() or _extract_task_prompt(source_text)
    inferred_time = _parse_time_phrase(source_text)
    inferred_days = _infer_days_of_week(source_text)
    schedule_type = str(payload.get("schedule_type", "other") or "other").strip().lower()
    if schedule_type not in {"hourly", "daily", "weekly", "monthly", "other"}:
        schedule_type = "other"

    out = {
        "is_valid": bool(payload.get("is_valid", False)),
        "reason": str(payload.get("reason", "") or "").strip(),
        "title": str(payload.get("title", "") or "").strip() or (task_prompt[:80] if task_prompt else "Scheduled Task"),
        "task_prompt": task_prompt,
        "schedule_type": schedule_type,
        "interval_minutes": int(payload.get("interval_minutes", 0) or 0),
        "run_hour": int(payload.get("run_hour", inferred_time[0] if inferred_time else 9) or (inferred_time[0] if inferred_time else 9)),
        "run_minute": int(payload.get("run_minute", inferred_time[1] if inferred_time else 0) or (inferred_time[1] if inferred_time else 0)),
        "run_day_of_week": int(payload.get("run_day_of_week", 0) or 0),
        "run_day_of_month": int(payload.get("run_day_of_month", 1) or 1),
        "days_of_week": str(payload.get("days_of_week", "") or inferred_days or "").strip(),
        "schedule_mode": str(payload.get("schedule_mode", "recurring") or "recurring").strip().lower(),
        "run_at": str(payload.get("run_at", "") or "").strip(),
    }

    out["run_hour"] = max(0, min(out["run_hour"], 23))
    out["run_minute"] = max(0, min(out["run_minute"], 59))
    out["run_day_of_week"] = max(0, min(out["run_day_of_week"], 6))
    out["run_day_of_month"] = max(1, min(out["run_day_of_month"], 31))
    if out["interval_minutes"] < 0:
        out["interval_minutes"] = 0
    if out["schedule_mode"] not in {"once", "recurring"}:
        out["schedule_mode"] = "recurring"

    if out["days_of_week"] and out["schedule_type"] in {"daily", "weekly"}:
        out["schedule_type"] = "daily"

    if not out["task_prompt"]:
        out["is_valid"] = False
        out["reason"] = "Missing task prompt to execute."

    if out["schedule_type"] in {"hourly", "other"} and out["interval_minutes"] <= 0:
        out["is_valid"] = False
        out["reason"] = out["reason"] or "Interval minutes must be greater than zero."

    return out


def compute_next_run(record: Dict[str, Any], now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now()
    schedule_type = str(record.get("schedule_type", "other") or "other").strip().lower()
    interval_minutes = int(record.get("interval_minutes", 0) or 0)
    run_hour = int(record.get("run_hour", 9) or 9)
    run_minute = int(record.get("run_minute", 0) or 0)
    run_dow = int(record.get("run_day_of_week", 0) or 0)
    run_dom = int(record.get("run_day_of_month", 1) or 1)
    raw_days = str(record.get("days_of_week", "") or "").strip()
    allowed_days = [int(part) for part in raw_days.split(",") if part.strip().isdigit()]
    allowed_days = [day for day in allowed_days if 0 <= day <= 6]
    if allowed_days:
        allowed_days = sorted(set(allowed_days))

    if schedule_type in {"hourly", "other"}:
        delta = max(1, interval_minutes)
        return (now + timedelta(minutes=delta)).replace(second=0, microsecond=0)

    if allowed_days:
        base = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
        for offset in range(0, 8):
            candidate = base + timedelta(days=offset)
            if candidate.weekday() in allowed_days and candidate > now:
                return candidate
        return base + timedelta(days=1)

    if schedule_type == "daily":
        candidate = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if schedule_type == "weekly":
        current = now.weekday()
        days_ahead = (run_dow - current) % 7
        candidate = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0) + timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    if schedule_type == "monthly":
        year = now.year
        month = now.month
        for _ in range(14):
            if month > 12:
                month = 1
                year += 1
            # Pick safe day for month length.
            last_day = 31
            while True:
                try:
                    candidate = datetime(year, month, min(run_dom, last_day), run_hour, run_minute)
                    break
                except ValueError:
                    last_day -= 1
            if candidate > now:
                return candidate
            month += 1
        return now + timedelta(days=30)

    return (now + timedelta(minutes=max(1, interval_minutes or 60))).replace(second=0, microsecond=0)

