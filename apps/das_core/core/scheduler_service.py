"""Durable dispatcher for saved scheduler jobs and their deliveries."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from core.inbound_request import InboundRequest
from core.scheduler_agent import compute_next_run
from execution_logger import log_exception, log_execution_step


class SchedulerService:
    def __init__(self, cda: CommonDataArea, controller: Any | None = None, conversation_manager: Any | None = None) -> None:
        self.cda, self.controller, self.conversation_manager = cda, controller, conversation_manager
        self._thread: threading.Thread | None = None
        self._stop_event, self._lock = threading.Event(), threading.RLock()
        self._running, self._last_error, self._last_tick = False, "", ""

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()

    def _poll_minutes(self) -> int:
        try: return max(1, int(self.cda.get_setting("scheduler_poll_minutes", 1) or 1))
        except Exception: return 1

    def _enabled(self) -> bool: return bool(self.cda.get_setting("scheduler_enabled", False))

    def start(self) -> None:
        if not self._enabled(): return
        with self._lock:
            if self._thread and self._thread.is_alive(): return
            self._stop_event.clear(); self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True); self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive(): self._thread.join(timeout=2)
            self._thread = None; self._running = False

    def restart(self) -> None: self.stop(); self.start()

    def get_status(self) -> Dict[str, Any]:
        return {"running": bool(self._running and self._thread and self._thread.is_alive()), "enabled": self._enabled(), "poll_minutes": self._poll_minutes(), "last_error": self._last_error, "last_tick": self._last_tick}

    @staticmethod
    def _json(value: Any, fallback: Any) -> Any:
        if isinstance(value, (dict, list)): return value
        try: return json.loads(str(value or ""))
        except Exception: return fallback

    @staticmethod
    def _now() -> datetime: return datetime.now().replace(microsecond=0)
    @staticmethod
    def _sql(dt: datetime | None = None) -> str: return (dt or SchedulerService._now()).strftime("%Y-%m-%d %H:%M:%S")

    def run_schedule_now(self, schedule_id: int) -> Dict[str, Any]:
        """Create a separately audited immediate run without changing cadence."""
        conn = sqlite3.connect(str(self._db_path())); conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM Schedules WHERE id=?", (int(schedule_id),)).fetchone()
            if not row: raise ValueError(f"Schedule #{schedule_id} not found.")
            run_id = self._claim_and_create_run(conn, dict(row), manual=True)
            conn.commit()
            self._execute_run(run_id)
            result = conn.execute("SELECT id,last_run_at,last_result,next_run_at,last_run_id FROM Schedules WHERE id=?", (int(schedule_id),)).fetchone()
            return dict(result) if result else {"id": int(schedule_id)}
        finally: conn.close()

    def retry_run(self, run_id: int) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self._db_path())); conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT schedule_id FROM ScheduleRuns WHERE id=?", (int(run_id),)).fetchone()
            if not row: raise ValueError("Schedule run not found.")
            schedule = conn.execute("SELECT * FROM Schedules WHERE id=?", (row["schedule_id"],)).fetchone()
            if not schedule: raise ValueError("Schedule no longer exists.")
            new_id = self._claim_and_create_run(conn, dict(schedule), manual=True)
            conn.commit(); self._execute_run(new_id)
            return {"run_id": new_id}
        finally: conn.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try: self._run_due_once(); self._last_error = ""
            except Exception as exc: self._last_error = str(exc); log_exception("SCHEDULER_LOOP_ERROR", exc, {})
            self._last_tick = self._now().isoformat(sep=" ")
            self._stop_event.wait(max(5, self._poll_minutes() * 60))

    def _run_due_once(self) -> None:
        conn = sqlite3.connect(str(self._db_path())); conn.row_factory = sqlite3.Row
        run_ids: List[int] = []
        try:
            now = self._sql()
            # BEGIN IMMEDIATE makes row selection/claiming safe across poller processes.
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM Schedules WHERE is_enabled=1 AND status='active' AND (next_run_at IS NULL OR next_run_at<=?) AND (claim_token IS NULL OR claimed_at<?) ORDER BY COALESCE(next_run_at,created_at),id LIMIT 20", (now, self._sql(self._now()-timedelta(minutes=10)))).fetchall()
            for row in rows:
                run_id = self._claim_and_create_run(conn, dict(row))
                if run_id: run_ids.append(run_id)
            conn.commit()
        finally: conn.close()
        for run_id in run_ids: self._execute_run(run_id)

    def _claim_and_create_run(self, conn: sqlite3.Connection, row: Dict[str, Any], manual: bool = False) -> int:
        sid, token, now = int(row["id"]), uuid.uuid4().hex, self._sql()
        if not manual:
            cur = conn.execute("UPDATE Schedules SET claim_token=?,claimed_at=? WHERE id=? AND (claim_token IS NULL OR claimed_at<?)", (token, now, sid, self._sql(self._now()-timedelta(minutes=10))))
            if cur.rowcount != 1: return 0
        spec = self._json(row.get("job_spec"), {})
        prompt = str(spec.get("task_prompt") or row.get("task_prompt") or row.get("nl_request") or "").strip()
        key = f"{sid}:{'manual:'+uuid.uuid4().hex if manual else row.get('next_run_at') or now}"
        try:
            cur = conn.execute("INSERT INTO ScheduleRuns(schedule_id,attempt,idempotency_key,correlation_id,claimed_at,status,prompt_snapshot) VALUES(?,?,?,?,?,'queued',?)", (sid, 1, key, f"scheduler:{sid}:{uuid.uuid4().hex}", now, prompt))
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return 0

    @staticmethod
    def _owner(row: Dict[str, Any], fallback: str = "") -> str:
        return str(row.get("owner") or row.get("created_by") or fallback or "").strip()

    def _owner_telegram(self, user_id: str) -> str:
        if not user_id: return ""
        conn = sqlite3.connect(str(self._db_path()))
        try:
            row = conn.execute("SELECT channel_user_id FROM ChannelUsers WHERE provider='telegram' AND user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
            return str(row[0]) if row else ""
        finally: conn.close()

    def _execute_run(self, run_id: int) -> None:
        conn = sqlite3.connect(str(self._db_path())); conn.row_factory = sqlite3.Row
        try:
            run = conn.execute("SELECT * FROM ScheduleRuns WHERE id=?", (run_id,)).fetchone()
            if not run or run["status"] not in {"queued", "failed"}: return
            schedule = conn.execute("SELECT * FROM Schedules WHERE id=?", (run["schedule_id"],)).fetchone()
            if not schedule: return
            row, run_data = dict(schedule), dict(run)
            conn.execute("UPDATE ScheduleRuns SET status='running',started_at=? WHERE id=?", (self._sql(), run_id)); conn.commit()
            prompt, output, error = str(run_data.get("prompt_snapshot") or "").strip(), "", ""
            try:
                if not prompt: raise ValueError("Missing task prompt.")
                owner = self._owner(row, str(self.cda.get_setting("current_user_id", "") or ""))
                metadata = {"is_scheduled_task": True, "schedule_id": int(row["id"]), "schedule_run_id": run_id, "schedule_owner_id": owner, "execution_source": "scheduler", "correlation_id": run_data.get("correlation_id")}
                if self.conversation_manager:
                    response = self.conversation_manager.execute_sync(InboundRequest(conversation_id=str(run_data["correlation_id"]), interface="Scheduler", user_id=owner or "unknown", message=prompt, execution_metadata=metadata), timeout=3600)
                elif self.controller:
                    response = self.controller.handle_user_message(prompt, interface="Scheduler", user_id=owner or None, session_id=str(run_data["correlation_id"]), execution_metadata=metadata)
                else: raise RuntimeError("No scheduler execution backend configured.")
                if str(getattr(response, "status", "") or "") == "error": raise RuntimeError(str(getattr(response, "content", "Execution failed")))
                output = str(getattr(response, "content", "") or "").strip()
            except Exception as exc:
                error = str(exc); log_exception("SCHEDULER_RUN_ERROR", exc, {"schedule_id": row["id"], "run_id": run_id})
            success = not error
            delivery_failed = False
            if success:
                delivery_failed = not self._deliver(conn, run_id, row, output)
            final = "succeeded" if success and not delivery_failed else "failed"
            summary = (output if success else error)[:1800]
            retry = self._retry_spec(row)
            next_retry = self._sql(self._now()+timedelta(minutes=int(retry.get("backoff_minutes", 5)))) if final == "failed" and int(retry.get("max_attempts", 1)) > 1 else None
            conn.execute("UPDATE ScheduleRuns SET status=?,finished_at=?,result_summary=?,error_text=?,next_retry_at=? WHERE id=?", (final, self._sql(), summary, error[:4000] if error else ("Delivery failed" if delivery_failed else ""), next_retry, run_id))
            self._finalize_schedule(conn, row, run_id, final, summary)
            conn.commit(); log_execution_step("SCHEDULER_RUN", f"Schedule #{row['id']} run #{run_id} {final}.")
        finally: conn.close()

    def _retry_spec(self, row: Dict[str, Any]) -> Dict[str, Any]:
        spec = self._json(row.get("retry_spec"), {})
        return spec if isinstance(spec, dict) else {}

    def _delivery_specs(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        specs = self._json(row.get("delivery_spec"), [])
        if isinstance(specs, list) and specs: return [x for x in specs if isinstance(x, dict)]
        # Compatibility: existing schedules retain owner Telegram notification.
        owner = self._owner(row, str(self.cda.get_setting("current_user_id", "") or "")); chat = self._owner_telegram(owner)
        return [{"channel": "telegram", "recipient": chat, "send_condition": "always", "legacy_owner_notification": True}] if chat else []

    def _deliver(self, conn: sqlite3.Connection, run_id: int, row: Dict[str, Any], output: str) -> bool:
        all_ok = True
        for index, spec in enumerate(self._delivery_specs(row)):
            condition = str(spec.get("send_condition", "on_success"))
            if condition not in {"always", "on_success"}: continue
            channel, recipient = str(spec.get("channel", "")).lower(), str(spec.get("recipient") or spec.get("recipient_ref") or "").strip()
            if not recipient: all_ok = False; continue
            conn.execute("INSERT INTO ScheduleDeliveries(run_id,delivery_index,channel,recipient_ref,attempt,started_at,status,attachments_json) VALUES(?,?,?,?,1,?,'running',?)", (run_id, index, channel, recipient, self._sql(), json.dumps(spec.get("attachments", []))))
            delivery_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            try:
                service = self.cda.get_runtime(f"{channel}_channel_service")
                if service is None: raise RuntimeError(f"{channel} delivery service is unavailable")
                message = f"[ok] {output}" if spec.get("legacy_owner_notification") else output
                response = service.send_text(recipient, message)
                for file_path in spec.get("attachments", []) or []:
                    path = Path(str(file_path)).resolve()
                    if not path.is_file(): raise ValueError("Declared attachment does not exist")
                    (service.send_document if channel == "telegram" else service.send_file)(recipient, str(path), caption="Scheduled task attachment")
                provider_id = str((response or {}).get("message_id") or (response or {}).get("id") or "") if isinstance(response, dict) else ""
                conn.execute("UPDATE ScheduleDeliveries SET status='succeeded',finished_at=?,provider_response_id=? WHERE id=?", (self._sql(), provider_id, delivery_id))
            except Exception as exc:
                all_ok = False
                conn.execute("UPDATE ScheduleDeliveries SET status='failed',finished_at=?,error_text=? WHERE id=?", (self._sql(), str(exc)[:1000], delivery_id))
        return all_ok

    def _finalize_schedule(self, conn: sqlite3.Connection, row: Dict[str, Any], run_id: int, status: str, summary: str) -> None:
        now = self._now(); mode = str(row.get("schedule_mode") or "recurring")
        if mode == "once" and status == "succeeded":
            conn.execute("UPDATE Schedules SET status='completed',is_enabled=0,completed_at=?,last_run_at=?,last_result=?,last_run_id=?,claim_token=NULL,claimed_at=NULL WHERE id=?", (self._sql(now), self._sql(now), f"[ok] {summary}"[:1800], run_id, row["id"])); return
        current = dict(row); current["schedule_type"] = str(current.get("schedule_type") or "other")
        next_run = compute_next_run(current, now=now)
        failures = int(row.get("failure_count") or 0) + (0 if status == "succeeded" else 1)
        conn.execute("UPDATE Schedules SET next_run_at=?,last_run_at=?,last_result=?,last_run_id=?,failure_count=?,claim_token=NULL,claimed_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?", (self._sql(next_run), self._sql(now), f"[{'ok' if status == 'succeeded' else 'error'}] {summary}"[:1800], run_id, failures, row["id"]))
