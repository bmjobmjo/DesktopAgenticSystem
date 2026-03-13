"""Background scheduler service for executing scheduled prompts."""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from core.inbound_request import InboundRequest
from core.scheduler_agent import compute_next_run
from execution_logger import log_exception, log_execution_step


class SchedulerService:
    def __init__(
        self,
        cda: CommonDataArea,
        controller: Any | None = None,
        conversation_manager: Any | None = None,
    ) -> None:
        self.cda = cda
        self.controller = controller
        self.conversation_manager = conversation_manager
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._running = False
        self._last_error = ""
        self._last_tick = ""

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()

    def _poll_minutes(self) -> int:
        try:
            return max(1, int(self.cda.get_setting("scheduler_poll_minutes", 1) or 1))
        except Exception:
            return 1

    def _enabled(self) -> bool:
        return bool(self.cda.get_setting("scheduler_enabled", False))

    def start(self) -> None:
        if not self._enabled():
            log_execution_step("SCHEDULER_START", "Scheduler disabled by settings; service not started.")
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            log_execution_step("SCHEDULER_START", f"Scheduler started (poll={self._poll_minutes()}m).")

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None
            self._running = False
            log_execution_step("SCHEDULER_STOP", "Scheduler stopped.")

    def restart(self) -> None:
        self.stop()
        self.start()

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": bool(self._running and self._thread is not None and self._thread.is_alive()),
            "enabled": self._enabled(),
            "poll_minutes": self._poll_minutes(),
            "last_error": self._last_error,
            "last_tick": self._last_tick,
        }

    def run_schedule_now(self, schedule_id: int) -> Dict[str, Any]:
        db_path = self._db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM Schedules WHERE id=? LIMIT 1", (int(schedule_id),))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Schedule #{schedule_id} not found.")

            self._execute_single_schedule(conn, dict(row), datetime.now())
            conn.commit()

            cur.execute("SELECT id, last_run_at, last_result, next_run_at FROM Schedules WHERE id=? LIMIT 1", (int(schedule_id),))
            updated = cur.fetchone()
            if updated is None:
                raise ValueError(f"Schedule #{schedule_id} disappeared after execution.")

            return dict(updated)
        finally:
            conn.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_due_once()
                self._last_error = ""
            except Exception as exc:
                self._last_error = str(exc)
                log_exception("SCHEDULER_LOOP_ERROR", exc, {})
            self._last_tick = datetime.now().isoformat(timespec="seconds")
            wait_seconds = max(5, self._poll_minutes() * 60)
            self._stop_event.wait(wait_seconds)

    def _run_due_once(self) -> None:
        db_path = self._db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            now = datetime.now()
            now_sql = now.strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                """
                SELECT * FROM Schedules
                WHERE is_enabled=1 AND status='active' AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY COALESCE(next_run_at, created_at) ASC, id ASC
                LIMIT 20
                """,
                (now_sql,),
            )
            due_rows = [dict(r) for r in cur.fetchall()]

            if not due_rows:
                conn.commit()
                return

            for row in due_rows:
                self._execute_single_schedule(conn, row, now)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _schedule_owner_id(row: Dict[str, Any], fallback_user_id: str = "") -> str:
        return str(
            row.get("owner", "")
            or row.get("created_by", "")
            or fallback_user_id
            or ""
        ).strip()

    def _lookup_owner_channels(self, user_id: str) -> Dict[str, str]:
        channels = {
            "telegram_chat_id": "",
            "whatsapp_target": "",
        }
        uid = str(user_id or "").strip()
        if not uid:
            return channels

        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            user_cols = {str(r[1]) for r in cur.fetchall()}
            select_cols = ["id"]
            if "telegram_chat_id" in user_cols:
                select_cols.append("telegram_chat_id")
            else:
                select_cols.append("'' AS telegram_chat_id")
            if "whatsapp_number" in user_cols:
                select_cols.append("whatsapp_number")
            else:
                select_cols.append("'' AS whatsapp_number")
            if "mobile_number" in user_cols:
                select_cols.append("mobile_number")
            else:
                select_cols.append("'' AS mobile_number")

            cur.execute(f"SELECT {', '.join(select_cols)} FROM Users WHERE id=? LIMIT 1", (uid,))
            row = cur.fetchone()
            if row:
                channels["telegram_chat_id"] = str(row[1] or "").strip()
                channels["whatsapp_target"] = str(row[2] or row[3] or "").strip()

            cur.execute("PRAGMA table_info(ChannelUsers)")
            channel_cols = {str(r[1]) for r in cur.fetchall()}
            if {"provider", "channel_user_id", "user_id"}.issubset(channel_cols):
                if not channels["telegram_chat_id"]:
                    cur.execute(
                        "SELECT channel_user_id FROM ChannelUsers WHERE provider=? AND user_id=? ORDER BY id DESC LIMIT 1",
                        ("telegram", uid),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        channels["telegram_chat_id"] = str(row[0]).strip()
                if not channels["whatsapp_target"]:
                    cur.execute(
                        "SELECT channel_user_id FROM ChannelUsers WHERE provider=? AND user_id=? ORDER BY id DESC LIMIT 1",
                        ("whatsapp", uid),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        channels["whatsapp_target"] = str(row[0]).strip()
        finally:
            conn.close()

        return channels

    @staticmethod
    def _extract_existing_files(text: str) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for match in re.findall(r"[A-Za-z]:\\[^\r\n<>\"|?*]+", str(text or "")):
            candidate = str(match).strip().rstrip(".,;:!?)\]")
            try:
                path = Path(candidate)
            except Exception:
                continue
            if not path.exists() or not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(resolved)
        return out

    def _notify_owner_channels(self, owner_user_id: str, message_text: str) -> None:
        channels = self._lookup_owner_channels(owner_user_id)
        text = str(message_text or "").strip()
        if not text:
            return

        telegram_svc = self.cda.get_runtime("telegram_channel_service")
        telegram_chat_id = channels.get("telegram_chat_id", "")
        if telegram_svc is not None and telegram_chat_id:
            try:
                telegram_svc.send_text(telegram_chat_id, text)
                for file_path in self._extract_existing_files(text):
                    telegram_svc.send_document(
                        telegram_chat_id,
                        file_path=file_path,
                        caption="Scheduled task attachment",
                    )
            except Exception as exc:
                log_exception("SCHEDULER_TELEGRAM_NOTIFY_ERROR", exc, {"user_id": owner_user_id})

        whatsapp_svc = self.cda.get_runtime("whatsapp_channel_service")
        whatsapp_target = channels.get("whatsapp_target", "")
        if whatsapp_svc is not None and whatsapp_target:
            try:
                whatsapp_svc.send_text(whatsapp_target, text)
            except Exception as exc:
                log_exception("SCHEDULER_WHATSAPP_NOTIFY_ERROR", exc, {"user_id": owner_user_id})

    def _execute_single_schedule(self, conn: sqlite3.Connection, row: Dict[str, Any], now: datetime) -> None:
        sid = int(row.get("id") or 0)
        task_prompt = str(row.get("task_prompt", "") or "").strip()
        if not task_prompt:
            task_prompt = str(row.get("nl_request", "") or "").strip()

        current = dict(row)
        current["schedule_type"] = str(current.get("schedule_type", "other") or "other").strip().lower()
        current["interval_minutes"] = int(current.get("interval_minutes", 0) or 0)
        current["run_hour"] = int(current.get("run_hour", 9) or 9)
        current["run_minute"] = int(current.get("run_minute", 0) or 0)
        current["run_day_of_week"] = int(current.get("run_day_of_week", 0) or 0)
        current["run_day_of_month"] = int(current.get("run_day_of_month", 1) or 1)

        next_run_dt = compute_next_run(current, now=now)
        next_run_sql = next_run_dt.strftime("%Y-%m-%d %H:%M:%S")
        now_sql = now.strftime("%Y-%m-%d %H:%M:%S")

        if not task_prompt:
            conn.execute(
                """
                UPDATE Schedules
                SET next_run_at=?, last_run_at=?, last_result=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (next_run_sql, now_sql, "[error] Missing task_prompt.", sid),
            )
            return

        run_status = "ok"
        run_output = ""
        owner_user_id = self._schedule_owner_id(row, str(self.cda.get_setting("current_user_id", "") or ""))
        try:
            if self.conversation_manager is not None:
                response = self.conversation_manager.execute_sync(
                    InboundRequest(
                        conversation_id=f"scheduler:{sid}",
                        interface="Scheduler",
                        user_id=owner_user_id or "unknown",
                        message=task_prompt,
                        execution_metadata={
                            "is_scheduled_task": True,
                            "schedule_id": sid,
                            "schedule_owner_id": owner_user_id,
                            "execution_source": "scheduler",
                        },
                    ),
                    timeout=3600,
                )
            elif self.controller is not None:
                response = self.controller.handle_user_message(
                    task_prompt,
                    interface="Scheduler",
                    user_id=owner_user_id or None,
                    session_id=f"scheduler:{sid}",
                    execution_metadata={
                        "is_scheduled_task": True,
                        "schedule_id": sid,
                        "schedule_owner_id": owner_user_id,
                        "execution_source": "scheduler",
                    },
                )
            else:
                raise RuntimeError("No scheduler execution backend configured.")
            run_status = "ok" if str(response.status or "") != "error" else "error"
            run_output = str(response.content or "").strip()
        except Exception as exc:
            run_status = "error"
            run_output = str(exc)
            log_exception("SCHEDULER_RUN_ERROR", exc, {"schedule_id": sid})

        result_text = f"[{run_status}] {run_output}".strip()
        if len(result_text) > 1800:
            result_text = result_text[:1800]

        conn.execute(
            """
            UPDATE Schedules
            SET next_run_at=?, last_run_at=?, last_result=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (next_run_sql, now_sql, result_text, sid),
        )

        if owner_user_id and result_text:
            self._notify_owner_channels(owner_user_id, result_text)

        log_execution_step("SCHEDULER_RUN", f"Schedule #{sid} executed ({run_status}).")
