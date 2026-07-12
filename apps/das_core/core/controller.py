"""Controller orchestrator."""

from __future__ import annotations

import logging
import json
import inspect
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.common_data_area import CommonDataArea
from core.chat_session import ChatSession, SessionStore
from core.session_context import SessionContext
from core.executor import Executor, ExecutorError
from core.router import Router, RouterError
from execution_logger import log_execution_step, log_exception, log_chat_history
from tools.output_utils import collect_created_file_info


@dataclass
class ControllerResponse:
    status: str
    content: str
    ui_feedback: List[Dict[str, Any]]
    tool_request: Optional[Dict[str, Any]] = None


class Controller:
    _RETRY_INTENT_PHRASES = {
        "again",
        "retry",
        "try again",
        "re try",
        "re-try",
        "do it again",
        "run again",
        "same again",
    }
    _IDENTITY_PROMPT_KEYS = (
        "UID",
        "USER_NAME",
        "USER_EMAIL",
        "USER_ROLE",
        "USER_ROLE_ID",
        "CURRENT_EMPLOYEE_ID",
        "CURRENT_EMPLOYEE_CODE",
        "CURRENT_EMPLOYEE_NAME",
        "CURRENT_EMPLOYEE_DESIGNATION",
        "CURRENT_EMPLOYEE_LINKED_USER_ID",
        "CURRENT_EMPLOYEE_DETAILS_SUMMARY",
        "CURRENT_EMPLOYEE_DETAILS_COUNT",
    )

    def __init__(
        self,
        cda: CommonDataArea | None = None,
        router: Router | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.cda = cda or CommonDataArea()
        self.router = router or Router(self.cda)
        self.executor = executor or Executor(self.cda)
        self.session_store = SessionStore()
        self._active_session: Optional[ChatSession] = None
        
        # New State Management
        self.task_queue: List[Dict] = []
        self.current_task: Optional[Dict] = None
        self.awaiting_user_input: bool = False

    @staticmethod
    def _merge_followup_response(
        initial_result: Any,
        followup_response: ControllerResponse,
    ) -> ControllerResponse:
        initial_content = str(getattr(initial_result, 'content', '') or '').strip()
        if initial_content:
            followup_content = str(followup_response.content or '').strip()
            followup_response.content = (
                f"{initial_content}\n\n{followup_content}"
                if followup_content
                else initial_content
            )

        initial_feedback = getattr(initial_result, 'ui_feedback', None)
        if isinstance(initial_feedback, list) and initial_feedback:
            followup_response.ui_feedback = list(initial_feedback) + list(followup_response.ui_feedback or [])
        return followup_response

    @staticmethod
    def _session_last_message(session: ChatSession) -> str:
        history = str(session.chat_history or "").strip()
        if not history:
            return ""
        lines = [ln.strip() for ln in history.splitlines() if ln.strip()]
        return lines[-1] if lines else ""

    @staticmethod
    def _session_user_display(session: ChatSession) -> str:
        metadata_name = str(session.metadata.get("user_name", "") or "").strip()
        if metadata_name:
            return metadata_name
        return session.user_id

    def list_active_sessions(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for sess in self.session_store.list_sessions():
            last_seen = sess.last_access_utc
            idle_sec = max(0, int((now - last_seen).total_seconds()))
            out.append(
                {
                    "user_id": str(sess.user_id or ""),
                    "user": self._session_user_display(sess),
                    "channel": str(sess.interface or ""),
                    "session_id": str(sess.session_id or ""),
                    "last_message": self._session_last_message(sess),
                    "last_access_utc": last_seen.isoformat(),
                    "idle_seconds": idle_sec,
                    "chat_history": str(sess.chat_history or ""),
                }
            )
        out.sort(key=lambda x: x.get("last_access_utc", ""), reverse=True)
        if out:
            return out

        # Fallback: expose current live CDA conversation as one pseudo-session
        # so Sessions tab remains useful even when session engine is disabled/off.
        cda_history = str(self.cda.get_memory('chat_history', '') or '').strip()
        if cda_history:
            iface = str(self.cda.get_setting('interface', 'UI') or 'UI')
            uid = str(self.cda.get_setting('current_user_id', '') or 'unknown')
            uname = str(self.cda.get_setting('current_username', '') or '').strip() or uid
            lines = [ln.strip() for ln in cda_history.splitlines() if ln.strip()]
            last_message = lines[-1] if lines else ""
            out.append(
                {
                    "user_id": uid,
                    "user": uname,
                    "channel": iface,
                    "session_id": "cda-live",
                    "last_message": last_message,
                    "last_access_utc": datetime.now(timezone.utc).isoformat(),
                    "idle_seconds": 0,
                    "chat_history": cda_history,
                }
            )
        return out

    def close_inactive_channel_sessions(self, interface: str, timeout_seconds: int = 3600) -> List[Dict[str, Any]]:
        closed: List[Dict[str, Any]] = []
        iface_norm = self._normalize_interface_type(interface)
        now = datetime.now(timezone.utc)

        for sess in self.session_store.list_sessions():
            if self._normalize_interface_type(sess.interface) != iface_norm:
                continue
            idle = (now - sess.last_access_utc).total_seconds()
            if idle < int(timeout_seconds):
                continue

            key = sess.key()
            removed = self.session_store.remove_key(key)
            if not removed:
                continue
            closed.append(
                {
                    "user_id": str(sess.user_id or ""),
                    "session_id": str(sess.session_id or ""),
                    "interface": str(sess.interface or ""),
                    "last_message": self._session_last_message(sess),
                    "idle_seconds": int(idle),
                }
            )
        return closed

    def _resolve_user_identity(self, user_id: str) -> tuple[str, str]:
        """Resolve (username, email) for a user id from Users table if possible."""
        uid = str(user_id or "").strip()
        if not uid:
            return "", ""
        db_path = Path(str(self.cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
        if not db_path.exists():
            return "", ""

        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]) for r in cur.fetchall()}
            if 'id' not in cols:
                return "", ""
            name_col = 'username' if 'username' in cols else ('full_name' if 'full_name' in cols else '')
            email_col = 'email' if 'email' in cols else ''
            select_cols: list[str] = []
            if name_col:
                select_cols.append(name_col)
            if email_col:
                select_cols.append(email_col)
            if not select_cols:
                return "", ""
            cur.execute(f"SELECT {', '.join(select_cols)} FROM Users WHERE id=? LIMIT 1", (uid,))
            row = cur.fetchone()
            if not row:
                return "", ""
            name = str(row[0] or "").strip() if len(row) >= 1 else ""
            email = str(row[1] or "").strip() if len(row) >= 2 else ""

            if not email:
                cur.execute("PRAGMA table_info(Employees)")
                e_cols = {str(r[1]) for r in cur.fetchall()}
                if "linked_user_id" in e_cols:
                    candidate_cols = [c for c in ("personal_email", "official_email") if c in e_cols]
                    if candidate_cols:
                        cur.execute(
                            f"SELECT {', '.join(candidate_cols)} FROM Employees WHERE linked_user_id=? LIMIT 1",
                            (uid,),
                        )
                        erow = cur.fetchone()
                        if erow:
                            for val in erow:
                                if val:
                                    email = str(val).strip()
                                    break

            return name, email
        except Exception:
            return "", ""
        finally:
            conn.close()

    def _resolve_user_role(self, user_id: str, user_email: str, username: str) -> tuple[str, str]:
        """Resolve (role_id, role_name) from Users -> Roles when possible."""
        uid = str(user_id or "").strip()
        email = str(user_email or "").strip()
        uname = str(username or "").strip()
        db_path = Path(str(self.cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
        if not db_path.exists():
            return "", ""

        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            user_cols = {str(r[1]) for r in cur.fetchall()}
            if not user_cols:
                return "", ""
            role_col = 'role_id' if 'role_id' in user_cols else ('roleID' if 'roleID' in user_cols else '')
            if not role_col:
                return "", ""

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Roles'")
            if not cur.fetchone():
                return "", ""
            cur.execute("PRAGMA table_info(Roles)")
            role_cols = {str(r[1]) for r in cur.fetchall()}
            if 'id' not in role_cols or 'name' not in role_cols:
                return "", ""

            base_query = f"""
                SELECT r.id, r.name
                FROM Users u
                JOIN Roles r ON r.id = u.{role_col}
                WHERE {{where_clause}}
                LIMIT 1
            """

            if uid and uid.isdigit():
                cur.execute(base_query.format(where_clause="u.id = ?"), (int(uid),))
                row = cur.fetchone()
                if row:
                    return str(row[0] or ""), str(row[1] or "")

            if email and 'email' in user_cols:
                cur.execute(base_query.format(where_clause="u.email = ?"), (email,))
                row = cur.fetchone()
                if row:
                    return str(row[0] or ""), str(row[1] or "")

            name_clauses: List[str] = []
            name_params: List[str] = []
            if uname:
                if 'username' in user_cols:
                    name_clauses.append("u.username = ?")
                    name_params.append(uname)
                if 'full_name' in user_cols:
                    name_clauses.append("u.full_name = ?")
                    name_params.append(uname)
            if name_clauses:
                cur.execute(base_query.format(where_clause=" OR ".join(name_clauses)), tuple(name_params))
                row = cur.fetchone()
                if row:
                    return str(row[0] or ""), str(row[1] or "")

            return "", ""
        except Exception:
            return "", ""
        finally:
            conn.close()

    @staticmethod
    def _summarize_employee_details(rows: List[Dict[str, Any]], max_items: int = 20, max_chars: int = 2000) -> str:
        if not rows:
            return ""
        parts: List[str] = []
        extra_count = 0
        for idx, row in enumerate(rows):
            if idx >= max_items:
                extra_count = len(rows) - max_items
                break
            label = str(row.get("detail_label") or row.get("detail_key") or "detail").strip()
            value = str(row.get("detail_value_text") or "").strip()
            if not value:
                file_id = str(row.get("file_id") or "").strip()
                if file_id:
                    value = f"file_id={file_id}"
            if not value:
                effective_date = str(row.get("effective_date") or "").strip()
                if effective_date:
                    value = effective_date
            category = str(row.get("category") or "").strip()
            text = f"{label}: {value}" if value else label
            if category:
                text = f"[{category}] {text}"
            parts.append(text)
        summary = " | ".join(p for p in parts if p)
        if extra_count > 0:
            summary = f"{summary} | (+{extra_count} more)" if summary else f"(+{extra_count} more)"
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3].rstrip() + "..."
        return summary

    def _resolve_linked_employee_context(self, user_id: str) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "CURRENT_EMPLOYEE_ID": "",
            "CURRENT_EMPLOYEE_CODE": "",
            "CURRENT_EMPLOYEE_NAME": "",
            "CURRENT_EMPLOYEE_DESIGNATION": "",
            "CURRENT_EMPLOYEE_LINKED_USER_ID": "",
            "CURRENT_EMPLOYEE_DETAILS_SUMMARY": "",
            "CURRENT_EMPLOYEE_DETAILS_COUNT": "0",
        }
        uid = str(user_id or "").strip()
        if not uid:
            return defaults
        db_path = Path(str(self.cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
        if not db_path.exists():
            return defaults

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Employees'")
            if not cur.fetchone():
                return defaults

            cur.execute("PRAGMA table_info(Employees)")
            employee_cols = {str(r[1]) for r in cur.fetchall()}
            if "id" not in employee_cols or "linked_user_id" not in employee_cols:
                return defaults

            select_cols = [
                col for col in (
                    "id",
                    "employee_code",
                    "full_name",
                    "designation",
                    "linked_user_id",
                    "employment_status",
                    "updated_at",
                    "created_at",
                )
                if col in employee_cols
            ]
            order_parts: List[str] = []
            if "employment_status" in employee_cols:
                order_parts.append("CASE WHEN lower(coalesce(employment_status, ''))='active' THEN 0 ELSE 1 END ASC")
            if "updated_at" in employee_cols:
                order_parts.append("CASE WHEN updated_at IS NULL OR updated_at='' THEN 1 ELSE 0 END ASC")
                order_parts.append("updated_at DESC")
            elif "created_at" in employee_cols:
                order_parts.append("CASE WHEN created_at IS NULL OR created_at='' THEN 1 ELSE 0 END ASC")
                order_parts.append("created_at DESC")
            order_parts.append("id DESC")
            cur.execute(
                f"SELECT {', '.join(select_cols)} FROM Employees WHERE linked_user_id=? "
                f"ORDER BY {', '.join(order_parts)} LIMIT 1",
                (uid,),
            )
            employee_row = cur.fetchone()
            if not employee_row:
                return defaults

            employee = dict(employee_row)
            employee_id = str(employee.get("id") or "").strip()
            defaults["CURRENT_EMPLOYEE_ID"] = employee_id
            defaults["CURRENT_EMPLOYEE_CODE"] = str(employee.get("employee_code") or "").strip()
            defaults["CURRENT_EMPLOYEE_NAME"] = str(employee.get("full_name") or "").strip()
            defaults["CURRENT_EMPLOYEE_DESIGNATION"] = str(employee.get("designation") or "").strip()
            defaults["CURRENT_EMPLOYEE_LINKED_USER_ID"] = str(employee.get("linked_user_id") or "").strip()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='EmployeeDetails'")
            if not cur.fetchone() or not employee_id:
                return defaults

            cur.execute("PRAGMA table_info(EmployeeDetails)")
            detail_cols = {str(r[1]) for r in cur.fetchall()}
            if "employee_id" not in detail_cols:
                return defaults
            detail_select_cols = [
                col for col in (
                    "id",
                    "detail_key",
                    "detail_label",
                    "detail_type",
                    "detail_value_text",
                    "file_id",
                    "category",
                    "effective_date",
                    "is_current",
                )
                if col in detail_cols
            ]
            where_sql = "employee_id=?"
            if "is_current" in detail_cols:
                where_sql += " AND coalesce(is_current, 1)=1"
            order_sql = ", ".join(col for col in ("category", "detail_key", "id") if col in detail_cols) or "rowid"
            cur.execute(
                f"SELECT {', '.join(detail_select_cols)} FROM EmployeeDetails "
                f"WHERE {where_sql} ORDER BY {order_sql}",
                (employee_id,),
            )
            details = [dict(r) for r in cur.fetchall()]
            defaults["CURRENT_EMPLOYEE_DETAILS_COUNT"] = str(len(details))
            defaults["CURRENT_EMPLOYEE_DETAILS_SUMMARY"] = self._summarize_employee_details(details)
            return defaults
        except Exception:
            return defaults
        finally:
            conn.close()

    def _set_prompt_identity_context(self, user_id: str, username: str, user_email: str = "") -> None:
        """Update placeholder context so identity placeholders are session-correct."""
        uid = str(user_id or "").strip()
        uname = str(username or "").strip() or (f"User {uid}" if uid else "")
        uemail = str(user_email or "").strip()
        role_id, role_name = self._resolve_user_role(uid, uemail, uname)
        if not role_id:
            role_id = str(
                self.cda.get_setting('current_user_role_id', '')
                or self.cda.get_setting('user_role_id', '')
                or ''
            ).strip()
        if not role_name:
            role_name = str(
                self.cda.get_setting('current_user_role_name', '')
                or self.cda.get_setting('user_role_name', '')
                or ''
            ).strip()

        # CDA settings used by router and some prompt builders.
        if uid:
            self.cda.set_setting('current_user_id', uid)
        if uname:
            self.cda.set_setting('current_username', uname)
        if uemail:
            self.cda.set_setting('current_user_email', uemail)
        self.cda.set_setting('current_user_role_id', role_id or '')
        self.cda.set_setting('current_user_role_name', role_name or '')
        employee_ctx = self._resolve_linked_employee_context(uid)
        for key, value in employee_ctx.items():
            self.cda.set_setting(key.lower(), value)

        # CDA/session prompt placeholders used by executor replacement.
        base_ctx = self.cda.get_memory('prompt_context_dict', {})
        if not isinstance(base_ctx, dict):
            base_ctx = {}
        ctx = dict(base_ctx)
        if uid:
            ctx['UID'] = uid
        if uname:
            ctx['USER_NAME'] = uname
        if uemail:
            ctx['USER_EMAIL'] = uemail
        ctx['USER_ROLE_ID'] = role_id or ''
        ctx['USER_ROLE'] = role_name or ''
        for key, value in employee_ctx.items():
            ctx[key] = value
        self.cda.set_memory('prompt_context_dict', ctx)

        if self._active_session is not None:
            self._active_session.metadata['prompt_context_dict'] = dict(ctx)
            if uname:
                self._active_session.metadata['user_name'] = uname

    def _session_engine_enabled(self) -> bool:
        raw = self.cda.get_setting('session_engine_enabled', True)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(raw)

    def _resolve_session_identity(
        self,
        interface: str,
        user_id_override: Optional[str] = None,
        channel_id: Optional[str] = None,
        session_id_override: Optional[str] = None,
    ) -> tuple[str, str, str]:
        user_id = str(user_id_override or self.cda.get_setting('current_user_id', '') or '').strip() or 'unknown'
        iface = str(interface or self.cda.get_setting('interface', 'UI') or 'UI').strip() or 'UI'
        session_id = str(session_id_override or channel_id or 'default').strip() or 'default'
        return user_id, iface, session_id

    @staticmethod
    def _normalize_interface_type(interface: str) -> str:
        raw = str(interface or '').strip().lower()
        if raw in ('ui', 'desktop', 'desktop_ui'):
            return 'UI'
        if raw in ('web', 'browser'):
            return 'WEB'
        if raw in ('telegram', 'tg'):
            return 'TELEGRAM'
        if raw in ('whatsapp', 'whatsap', 'wa'):
            return 'WHATSAPP'
        if raw in ('scheduler', 'schedule', 'sheduler'):
            return 'SCHEDULER'
        return 'UI'

    @staticmethod
    def _extract_last_user_message_from_history(history: str) -> str:
        text = str(history or "")
        if not text.strip():
            return ""
        pattern = re.compile(r"^User\[.*?\]:\s*(.+)$")
        for raw_line in reversed(text.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if not match:
                continue
            content = str(match.group(1) or "").strip()
            if content:
                return content
        return ""

    def _resolve_retry_intent_message(self, message: str, history: str) -> str:
        text = str(message or "").strip()
        if not text:
            return ""
        normalized = re.sub(r"\s+", " ", text.lower())
        normalized = re.sub(r"[!?.,;:]+$", "", normalized).strip()
        if normalized not in self._RETRY_INTENT_PHRASES:
            return ""
        candidate = self._extract_last_user_message_from_history(history)
        if not candidate:
            return ""
        if candidate.strip().lower() == text.strip().lower():
            return ""
        return candidate

    def _activate_session(
        self,
        interface: str,
        user_id_override: Optional[str] = None,
        channel_id: Optional[str] = None,
        session_id_override: Optional[str] = None,
    ) -> Optional[ChatSession]:
        if not self._session_engine_enabled():
            return None

        user_id, iface, session_id = self._resolve_session_identity(
            interface,
            user_id_override=user_id_override,
            channel_id=channel_id,
            session_id_override=session_id_override,
        )
        session = self.session_store.get_or_create(user_id, iface, session_id)
        try:
            timeout_seconds = float(self.cda.get_setting('session_lock_timeout_seconds', 5) or 5)
        except Exception:
            timeout_seconds = 5.0
        timeout_seconds = max(0.25, timeout_seconds)
        acquired = session.lock.acquire(timeout=timeout_seconds)
        if not acquired:
            raise TimeoutError(
                f"Session lock timeout for interface={iface} user_id={user_id} session_id={session_id}"
            )
        self._active_session = session

        # Load session state into controller/CDA for backward-compatible router/executor usage.
        self.task_queue = session.task_queue
        self.current_task = session.current_task
        self.awaiting_user_input = session.awaiting_user_input
        self.cda.set_memory('chat_history', session.chat_history)
        self.cda.set_memory('agent_activity', session.agent_activity)
        self.cda.set_memory('agent_activity_collection', session.agent_activity_collection)
        self.cda.set_memory('AgentActivity', session.agent_activity_collection)
        self.cda.set_memory('agent_activity_step', session.agent_activity_step)
        return session

    def _deactivate_session(self) -> None:
        session = self._active_session
        if session is None:
            return
        try:
            # Flush mutable state back into session.
            session.task_queue = self.task_queue
            session.current_task = self.current_task
            session.awaiting_user_input = self.awaiting_user_input
            session.touch()
        finally:
            session.lock.release()
            self._active_session = None

    def _get_session_context(self) -> Optional[SessionContext]:
        if self._active_session is None:
            return None
        return SessionContext(self.cda, self._active_session)

    def _get_chat_history(self) -> str:
        if self._active_session is not None:
            return self._active_session.chat_history
        return str(self.cda.get_memory('chat_history', '') or '')

    def _set_chat_history(self, history: str) -> None:
        if self._active_session is not None:
            self._active_session.chat_history = history
            return
        self.cda.set_memory('chat_history', history)

    def _route(
        self,
        message: str,
        input_files=None,
        tool_output=None,
        chat_history: str = '',
        interface_type: str = 'UI',
    ) -> List[Dict]:
        route_sig = inspect.signature(self.router.route)
        kwargs: Dict[str, Any] = {
            'user_prompt': message,
            'chat_history': chat_history,
        }
        if input_files is not None:
            kwargs['input_files'] = input_files
        if tool_output is not None:
            kwargs['tool_output'] = tool_output
        if 'session_ctx' in route_sig.parameters:
            kwargs['session_ctx'] = self._get_session_context()
        if 'interface_type' in route_sig.parameters:
            kwargs['interface_type'] = interface_type
        try:
            return self.router.route(**kwargs)
        except RouterError as exc:
            if not self._is_token_budget_error(str(exc)):
                raise
            token_request = self._build_token_budget_request_payload(
                source='router',
                detail=str(exc),
            )
            return [
                {
                    'type': 'request_user_input',
                    'confidence': 'high',
                    'reason': 'Interaction token budget reached; explicit user approval required to continue.',
                    'response_to_user': token_request['prompt'],
                    'tool_request': token_request,
                    '_awaiting_token_budget_approval': True,
                    '_token_resume_message': message,
                    '_token_resume_input_files': [str(f) for f in (input_files or [])],
                }
            ]

    def _emit_trace(self, event_type: str, payload: Dict[str, Any]) -> None:
        handler = self.cda.get_runtime('executor_trace_handler')
        if callable(handler):
            try:
                import copy
                handler(event_type, copy.deepcopy(payload))
            except Exception:
                # Trace callback failures should not break execution flow.
                pass

    def _get_int_setting(self, key: str, default: int) -> int:
        raw = self.cda.get_setting(key, default)
        try:
            value = int(raw)
        except Exception:
            value = int(default)
        return value

    def _increment_interaction_counter(self, key: str, step: int = 1) -> int:
        try:
            current = int(self.cda.get_memory(key, 0) or 0)
        except Exception:
            current = 0
        updated = max(0, current) + max(0, int(step or 0))
        self.cda.set_memory(key, updated)
        return updated

    def _allow_reroute(self, reason: str) -> tuple[bool, str]:
        reroutes = self._increment_interaction_counter('interaction_reroute_count', 1)
        max_reroutes = max(1, self._get_int_setting('interaction_max_reroutes', 12))
        if reroutes <= max_reroutes:
            return True, ''
        msg = (
            "Safety stop: too many Router re-routes in one interaction "
            f"(count={reroutes}, limit={max_reroutes}) while {reason}."
        )
        log_execution_step('CONTROLLER_REROUTE_GUARD', msg)
        return False, msg

    def _allow_agent_execution(self, agent_name: str) -> tuple[bool, str]:
        total_calls = self._increment_interaction_counter('interaction_agent_call_total', 1)
        max_total = max(1, self._get_int_setting('interaction_max_agent_calls', 24))
        if total_calls > max_total:
            msg = (
                "Safety stop: too many agent executions in one interaction "
                f"(count={total_calls}, limit={max_total})."
            )
            log_execution_step('CONTROLLER_AGENT_CALL_GUARD', msg)
            return False, msg

        canonical = self._canonical_agent_name(agent_name)
        if not canonical:
            return True, ''

        per_agent = self.cda.get_memory('interaction_agent_call_counts', {})
        if not isinstance(per_agent, dict):
            per_agent = {}
        next_count = int(per_agent.get(canonical, 0) or 0) + 1
        per_agent[canonical] = next_count
        self.cda.set_memory('interaction_agent_call_counts', per_agent)

        max_same = max(1, self._get_int_setting('interaction_max_same_agent_calls', 6))
        if next_count > max_same:
            msg = (
                "Safety stop: same agent executed repeatedly in one interaction "
                f"(agent={agent_name}, count={next_count}, limit={max_same})."
            )
            log_execution_step('CONTROLLER_AGENT_REPEAT_GUARD', msg)
            return False, msg
        return True, ''

    def _allow_tool_call(self, tool_name: str, parameters: Any) -> tuple[bool, str]:
        total_calls = self._increment_interaction_counter('interaction_tool_call_total', 1)
        max_total = max(1, self._get_int_setting('interaction_max_tool_calls', 24))
        if total_calls > max_total:
            msg = (
                "Safety stop: too many tool calls in one interaction "
                f"(count={total_calls}, limit={max_total})."
            )
            log_execution_step('CONTROLLER_TOOL_CALL_GUARD', msg)
            return False, msg

        try:
            serialized_params = json.dumps(parameters or {}, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            serialized_params = str(parameters)
        signature = f"{str(tool_name or '').strip().lower()}::{serialized_params}"
        signatures = self.cda.get_memory('interaction_tool_call_signatures', [])
        if not isinstance(signatures, list):
            signatures = []
        signatures = list(signatures)
        signatures.append(signature)
        max_history = max(5, self._get_int_setting('interaction_tool_signature_history', 20))
        signatures = signatures[-max_history:]
        self.cda.set_memory('interaction_tool_call_signatures', signatures)

        repeat_count = sum(1 for item in signatures if item == signature)
        max_repeat = max(1, self._get_int_setting('interaction_max_same_tool_calls', 4))
        if repeat_count > max_repeat:
            msg = (
                "Safety stop: repeated identical tool call detected "
                f"(tool={tool_name}, count={repeat_count}, limit={max_repeat})."
            )
            log_execution_step('CONTROLLER_TOOL_REPEAT_GUARD', msg)
            return False, msg

        return True, ''

    def _interaction_effective_token_limit(self) -> int:
        base = max(0, self._get_int_setting('interaction_max_tokens', 120000))
        extra_raw = self.cda.get_memory('interaction_token_allowance_extra', 0)
        try:
            extra = int(extra_raw or 0)
        except Exception:
            extra = 0
        return base + max(0, extra)

    def _interaction_base_token_limit(self) -> int:
        return max(1, self._get_int_setting('interaction_max_tokens', 120000))

    @staticmethod
    def _is_token_budget_error(message: str) -> bool:
        lowered = str(message or '').lower()
        return 'token budget' in lowered or 'budget reached' in lowered

    def _build_token_budget_request_payload(self, source: str, detail: str = '') -> Dict[str, Any]:
        usage = self.cda.get_memory('interaction_token_usage', {})
        used = 0
        if isinstance(usage, dict):
            try:
                used = int(usage.get('total', 0) or 0)
            except Exception:
                used = 0
        limit = self._interaction_effective_token_limit()
        increment = self._interaction_base_token_limit()
        prompt = (
            f"Token budget reached for this interaction (used={used}, limit={limit}). "
            f"Reply 'yes' to continue with one more budget block (+{increment} tokens), or 'no' to stop."
        )
        return {
            'permission_type': 'token_budget_continue',
            'source': source,
            'used_tokens': used,
            'limit_tokens': limit,
            'suggested_increment': increment,
            'detail': str(detail or ''),
            'prompt': prompt,
        }

    @staticmethod
    def _parse_user_yes_no(text: str) -> bool | None:
        value = str(text or '').strip().lower()
        if not value:
            return None
        yes_values = {
            'y', 'yes', 'ok', 'okay', 'continue', 'proceed', 'go', 'go ahead', 'approve', 'approved', 'sure',
        }
        no_values = {
            'n', 'no', 'stop', 'cancel', 'abort', 'deny', 'denied', 'do not continue', "don't continue",
        }
        if value in yes_values:
            return True
        if value in no_values:
            return False
        if value.startswith('yes') or value.startswith('ok') or value.startswith('continue'):
            return True
        if value.startswith('no') or value.startswith('stop') or value.startswith('cancel'):
            return False
        return None

    @staticmethod
    def _canonical_agent_name(agent_name: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', str(agent_name or '').strip().lower())

    def _get_interaction_executed_agents(self) -> List[str]:
        raw = self.cda.get_memory('interaction_executed_agents', [])
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        for item in raw:
            canonical = self._canonical_agent_name(str(item or ''))
            if canonical:
                out.append(canonical)
        return out

    def _mark_interaction_agent_executed(self, agent_name: str) -> None:
        canonical = self._canonical_agent_name(agent_name)
        if not canonical:
            return
        executed = self._get_interaction_executed_agents()
        if canonical in executed:
            return
        executed.append(canonical)
        self.cda.set_memory('interaction_executed_agents', executed)

    def _has_interaction_agent_executed(self, agent_name: str) -> bool:
        canonical = self._canonical_agent_name(agent_name)
        if not canonical:
            return False
        return canonical in self._get_interaction_executed_agents()

    def _is_agent_in_queue(self, agent_name: str) -> bool:
        canonical = self._canonical_agent_name(agent_name)
        if not canonical:
            return False
        for task in self.task_queue:
            if not isinstance(task, dict):
                continue
            task_type = str(task.get('type', '') or '').strip()
            if task_type not in ('agent_call', 'continue'):
                continue
            queued = self._canonical_agent_name(str(task.get('selected_agent', '') or ''))
            if queued == canonical:
                return True
        return False

    def _remove_agent_from_queue(self, agent_name: str) -> int:
        canonical = self._canonical_agent_name(agent_name)
        if not canonical:
            return 0
        removed = 0
        kept: List[Dict[str, Any]] = []
        for task in self.task_queue:
            if not isinstance(task, dict):
                kept.append(task)
                continue
            task_type = str(task.get('type', '') or '').strip()
            queued = self._canonical_agent_name(str(task.get('selected_agent', '') or ''))
            if task_type in ('agent_call', 'continue') and queued == canonical:
                removed += 1
                continue
            kept.append(task)
        if removed:
            self.task_queue = kept
        return removed

    def _reset_interaction_safeguards(self) -> None:
        self.cda.set_memory('interaction_handoff_count', 0)
        self.cda.set_memory('interaction_token_usage', {'total': 0, 'router': 0, 'executor': 0})
        self.cda.set_memory('interaction_executed_agents', [])
        self.cda.set_memory('interaction_agent_hint', '')
        self.cda.set_memory('interaction_token_allowance_extra', 0)
        self.cda.set_memory('interaction_queue_steps', 0)
        self.cda.set_memory('interaction_reroute_count', 0)
        self.cda.set_memory('interaction_agent_call_total', 0)
        self.cda.set_memory('interaction_agent_call_counts', {})
        self.cda.set_memory('interaction_tool_call_total', 0)
        self.cda.set_memory('interaction_tool_call_signatures', [])

    @staticmethod
    def _compose_agent_instruction(task: Dict[str, Any], fallback_prompt: str) -> str:
        """
        Build the effective agent input.

        Router-originated agent calls should receive the original user input unchanged.
        Resume flows use the latest user reply as instruction.
        Non-router handoffs can still use explicit instruction payloads.
        """
        # For resumed tasks, the current task instruction is already the latest user reply.
        if bool(task.get('_resume', False)):
            instruction = str(task.get('instruction', '') or '').strip()
            return instruction or str(fallback_prompt or '').strip()

        # For router handoff, preserve the user message exactly.
        if bool(task.get('_preserve_user_input', False)):
            original = str(task.get('_original_user_input', '') or '').strip()
            if original:
                return original

        instruction = str(task.get('instruction', '') or '').strip()
        return instruction or str(fallback_prompt or '').strip()

    def clear_current_task(self) -> None:
        """Clears the controller's active task state (typically used on new chats)."""
        self.current_task = None
        self.awaiting_user_input = False
        self.task_queue.clear()
        if self._active_session is not None:
            self._active_session.current_task = None
            self._active_session.awaiting_user_input = False
            self._active_session.task_queue.clear()

    @staticmethod
    def _reset_prompt_context(prompt_ctx: Any) -> Dict[str, Any]:
        preserved: Dict[str, Any] = {}
        if isinstance(prompt_ctx, dict):
            for key in Controller._IDENTITY_PROMPT_KEYS:
                if key in prompt_ctx:
                    preserved[key] = prompt_ctx[key]
        preserved.update(
            {
                "CHAT_HISTORY": "",
                "TOOL_DATA": "",
                "CREATED_FILES": [],
                "LAST_CREATED_FILE": "",
                "INSTRUCTIONS": "",
                "IS_SCHEDULED_TASK": "0",
                "SCHEDULE_ID": "",
                "SCHEDULE_OWNER_ID": "",
                "EXECUTION_SOURCE": "",
            }
        )
        return preserved

    def _clear_transient_memory(self) -> None:
        self.cda.set_memory('chat_history', '')
        self.cda.set_memory('AgentActivity', [])
        self.cda.set_memory('agent_activity_collection', [])
        self.cda.set_memory('agent_activity', '')
        self.cda.set_memory('agent_activity_step', 0)
        self.cda.set_memory('plan', '')
        self.cda.set_memory('tool_data', '')
        self.cda.set_memory('created_files', [])
        self.cda.set_memory('last_created_file', None)
        self.cda.set_memory('last_action', '')
        self.cda.set_memory('execution_metadata_dict', {})
        self.cda.set_memory('active_executor_agent', '')
        self.cda.set_memory('current_chat_id', None)
        self.cda.set_memory(
            'prompt_context_dict',
            self._reset_prompt_context(self.cda.get_memory('prompt_context_dict', {})),
        )
        if hasattr(self.cda, 'session') and isinstance(self.cda.session, dict):
            self.cda.session.clear()

    def reset_session_state(
        self,
        interface: str = 'UI',
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Drop stored session state and clear transient conversation memory for a fresh chat."""
        iface = (interface or 'UI').strip() or 'UI'
        effective_user_id = str(user_id or self.cda.get_setting('current_user_id', '') or '').strip() or 'unknown'
        effective_session_id = str(session_id or 'default').strip() or 'default'

        self.clear_current_task()
        removed = self.session_store.remove(effective_user_id, iface, effective_session_id)
        if not removed:
            keys_to_remove = [
                sess.key()
                for sess in self.session_store.list_sessions()
                if self._normalize_interface_type(sess.interface) == self._normalize_interface_type(iface)
                and str(sess.session_id or '').strip() == effective_session_id
            ]
            for key in keys_to_remove:
                self.session_store.remove_key(key)

        if self._active_session is not None:
            active_iface = self._normalize_interface_type(self._active_session.interface)
            active_session_id = str(self._active_session.session_id or '').strip() or 'default'
            if active_iface == self._normalize_interface_type(iface) and active_session_id == effective_session_id:
                self._active_session.chat_history = ''
                self._active_session.agent_activity = ''
                self._active_session.agent_activity_collection = []
                self._active_session.agent_activity_step = 0
                self._active_session.current_chat_id = None
                self._active_session.metadata['prompt_context_dict'] = self._reset_prompt_context(
                    self._active_session.metadata.get('prompt_context_dict', {})
                )
                self._active_session.metadata.pop('active_executor_agent', None)

        self._clear_transient_memory()

    def handle_user_message(
        self,
        message: str,
        files: List[str] | None = None,
        interface: str = "UI",
        user_id: str | None = None,
        channel_id: str | None = None,
        session_id: str | None = None,
        ui_callback=None,
        execution_metadata: Dict[str, Any] | None = None,
    ) -> ControllerResponse:
        """
        Main entry point for user interaction.
        
        Orchestrates the flow:
        1. Checks if the user is responding to a specific agent request (resume task).
        2. If new request, calls Router to determine tasks.
        3. Populates the task queue.
        4. Initiates queue processing.
        """
        iface = (interface or "UI").strip() or "UI"
        iface_type = self._normalize_interface_type(iface)
        prev_user_id = self.cda.get_setting('current_user_id', '')
        prev_username = self.cda.get_setting('current_username', '')
        prev_user_email = self.cda.get_setting('current_user_email', '')
        prev_user_role_name = self.cda.get_setting('current_user_role_name', '')
        prev_user_role_id = self.cda.get_setting('current_user_role_id', '')
        prev_prompt_ctx = self.cda.get_memory('prompt_context_dict', {})
        prev_execution_metadata = self.cda.get_memory('execution_metadata_dict', {})
        self.cda.set_setting('interface', iface)
        self.cda.set_setting('INTERFACE_TYPE', iface_type)
        self.cda.set_memory('INTERFACE_TYPE', iface_type)
        effective_user_id = str(user_id) if user_id is not None else str(prev_user_id or '')
        resolved_name = ''
        resolved_email = ''
        if effective_user_id:
            resolved_name, resolved_email = self._resolve_user_identity(effective_user_id)
        if user_id is not None:
            self.cda.set_setting('current_user_id', str(user_id))
            if not resolved_name:
                self.cda.set_setting('current_username', '')
            if not resolved_email:
                self.cda.set_setting('current_user_email', '')
        if resolved_name:
            self.cda.set_setting('current_username', resolved_name)
        if resolved_name and self._active_session is not None:
            self._active_session.metadata['user_name'] = resolved_name
        if resolved_email:
            self.cda.set_setting('current_user_email', resolved_email)
        log_execution_step('USER_INPUT', f"{message} [Files: {len(files) if files else 0}] [Interface: {iface}] [InterfaceType: {iface_type}]")
        self._emit_trace('user_input', {'message': message, 'files': files, 'interface': iface, 'interface_type': iface_type})
        try:
            self._activate_session(
                iface,
                user_id_override=user_id,
                channel_id=channel_id,
                session_id_override=session_id,
            )
            self._set_prompt_identity_context(effective_user_id, resolved_name, resolved_email)
            metadata_payload = dict(execution_metadata) if isinstance(execution_metadata, dict) else {}
            if metadata_payload:
                metadata_payload.setdefault('execution_source', iface_type.lower())
                self.cda.set_memory('execution_metadata_dict', metadata_payload)
                prompt_ctx = self.cda.get_memory('prompt_context_dict', {})
                if not isinstance(prompt_ctx, dict):
                    prompt_ctx = {}
                prompt_ctx = dict(prompt_ctx)
                prompt_ctx['IS_SCHEDULED_TASK'] = '1' if bool(metadata_payload.get('is_scheduled_task')) else '0'
                prompt_ctx['SCHEDULE_ID'] = str(metadata_payload.get('schedule_id', '') or '')
                prompt_ctx['SCHEDULE_OWNER_ID'] = str(metadata_payload.get('schedule_owner_id', '') or '')
                prompt_ctx['EXECUTION_SOURCE'] = str(metadata_payload.get('execution_source', '') or '')
                self.cda.set_memory('prompt_context_dict', prompt_ctx)
                if self._active_session is not None:
                    self._active_session.metadata['prompt_context_dict'] = dict(prompt_ctx)
            if not (self.awaiting_user_input and self.current_task is not None):
                self._reset_interaction_safeguards()
            return self._handle_user_message_impl(message, files=files, ui_callback=ui_callback, interface_type=iface_type)
        except Exception as exc:
            error_msg = f"System Error: {exc}"
            log_execution_step('CONTROLLER_ERROR', error_msg)
            log_exception('CONTROLLER_ERROR', exc, {'message': message, 'interface': iface, 'user_id': user_id})
            return ControllerResponse(
                status='error',
                content=error_msg,
                ui_feedback=[],
            )
        finally:
            self._deactivate_session()
            if user_id is not None:
                self.cda.set_setting('current_user_id', prev_user_id)
                self.cda.set_setting('current_username', prev_username)
                self.cda.set_setting('current_user_email', prev_user_email)
                self.cda.set_setting('current_user_role_name', prev_user_role_name)
                self.cda.set_setting('current_user_role_id', prev_user_role_id)
            if isinstance(prev_prompt_ctx, dict):
                self.cda.set_memory('prompt_context_dict', prev_prompt_ctx)
            if isinstance(prev_execution_metadata, dict):
                self.cda.set_memory('execution_metadata_dict', prev_execution_metadata)

    def _handle_user_message_impl(
        self,
        message: str,
        files: List[str] | None = None,
        interface_type: str = 'UI',
        ui_callback=None,
    ) -> ControllerResponse:
        
        # 1. Handle Pending Input (Bypass Router)
        # If an agent was waiting for user input (e.g. "What is your destination?"),
        # we bypass the router and resume that specific agent's execution.
        if self.awaiting_user_input and self.current_task:
            if bool(self.current_task.get('_awaiting_token_budget_approval', False)):
                decision = self._parse_user_yes_no(message)
                request_meta = self.current_task.get('tool_request') if isinstance(self.current_task, dict) else {}
                if not isinstance(request_meta, dict):
                    request_meta = {}
                if decision is None:
                    self.awaiting_user_input = True
                    return ControllerResponse(
                        status='request_user_input',
                        content="Please reply with 'yes' to continue, or 'no' to stop.",
                        ui_feedback=[],
                        tool_request=request_meta,
                    )
                if decision is False:
                    self.awaiting_user_input = False
                    self.current_task = None
                    return ControllerResponse(
                        status='complete',
                        content='Stopped to avoid additional token usage.',
                        ui_feedback=[],
                    )

                increment = request_meta.get('suggested_increment')
                try:
                    increment_value = int(increment)
                except Exception:
                    increment_value = self._interaction_base_token_limit()
                if increment_value <= 0:
                    increment_value = self._interaction_base_token_limit()
                current_extra = self.cda.get_memory('interaction_token_allowance_extra', 0)
                try:
                    current_extra_value = int(current_extra or 0)
                except Exception:
                    current_extra_value = 0
                self.cda.set_memory('interaction_token_allowance_extra', current_extra_value + increment_value)
                log_execution_step(
                    'CONTROLLER_TOKEN_APPROVED',
                    (
                        f"User approved extra interaction budget +{increment_value} tokens "
                        f"(new_effective_limit={self._interaction_effective_token_limit()})."
                    ),
                )

                task_type = str(self.current_task.get('type', '') or '').strip()
                resume_message = str(self.current_task.get('_token_resume_message', '') or '')
                resume_files = self.current_task.get('_token_resume_input_files')
                if not isinstance(resume_files, list):
                    resume_files = None
                self.current_task.pop('_awaiting_token_budget_approval', None)
                self.current_task.pop('_token_resume_message', None)
                self.current_task.pop('_token_resume_input_files', None)
                self.awaiting_user_input = False

                if task_type in ('agent_call', 'continue'):
                    task = self.current_task
                    self.current_task = None
                    self.task_queue.insert(0, task)
                    return self._process_queue(resume_message or message, ui_callback, interface_type=interface_type)

                self.current_task = None
                return self._handle_user_message_impl(
                    resume_message or message,
                    files=resume_files,
                    interface_type=interface_type,
                    ui_callback=ui_callback,
                )

            task_type = str(self.current_task.get('type', '') or '').strip()
            if task_type in ('agent_call', 'continue'):
                log_execution_step('CONTROLLER_RESUME', f"Resuming task {self.current_task.get('selected_agent')} with user input.")
                self.awaiting_user_input = False
                # Force current task instruction to latest user answer for resume flow.
                self.current_task['instruction'] = message
                self.current_task['_resume'] = True

                # Execute with user input
                result = self._execute_current_task(message, ui_callback, interface_type=interface_type)

                # If task is still requesting input (e.g. multi-turn), return immediately
                if result.status == 'request_user_input':
                    self.awaiting_user_input = True
                    return ControllerResponse(
                        status='request_user_input',
                        content=result.content,
                        ui_feedback=result.ui_feedback,
                        tool_request=result.tool_request
                    )

                # If task error, stop
                if result.status == 'error':
                     return ControllerResponse(status='error', content=result.content, ui_feedback=result.ui_feedback)

                # If task complete, check if we have more in queue
                if result.status == 'complete':
                     # Append this result to history is done in _execute_current_task.
                     # Preserve the completed user-facing message while continuing any queued work.
                     followup = self._process_queue(message, ui_callback, interface_type=interface_type)
                     return self._merge_followup_response(result, followup)
            else:
                log_execution_step('CONTROLLER_REROUTE_AFTER_INPUT', f"Pending task type '{task_type}' is not resumable; routing fresh user input.")
                self.awaiting_user_input = False
                self.current_task = None

        history = self._get_chat_history()
        routing_message = message
        retry_message = self._resolve_retry_intent_message(message, history)
        if retry_message:
            routing_message = retry_message
            log_execution_step(
                'CONTROLLER_RETRY_INTENT_RESOLVED',
                f"Expanded retry intent '{message}' to previous user request: {retry_message}",
            )

        try:
            # 2. Route New Request
            # Ask the Router to breakdown the user message into one or more tasks.
            # Can return Agent tasks (delegate) or Tool tasks (direct execution).
            
            # Convert file strings to Path objects
            from pathlib import Path
            input_files = [Path(f) for f in files] if files else None
            
            routes = self._route(routing_message, input_files=input_files, chat_history=history, interface_type=interface_type)
            if isinstance(routes, dict):
                routes = [routes]

            for route in routes:
                if not isinstance(route, dict):
                    continue
                route_type = str(route.get('type', '') or '').strip()
                if route_type in ('agent_call', 'continue'):
                    route.setdefault('_preserve_user_input', True)
                    route.setdefault('_original_user_input', routing_message)
            
            # Sort routes by priority (ascending), default to 99 if missing
            routes.sort(key=lambda x: x.get('priority', 99))
            
            # Note: Deliberately preserving `agent_activity` here to carry context across the entire active chat session.
            
            self.task_queue = routes
            self.current_task = None
            
            self._emit_trace('controller_task_queue', {'queue_size': len(routes), 'routes': routes})

            if not self.task_queue:
                return ControllerResponse(
                    status='complete',
                    content="I'm sorry, I couldn't determine how to help with that.",
                    ui_feedback=[]
                )

            # 3. Start Execution Loop
            return self._process_queue(message, ui_callback, interface_type=interface_type)

        except Exception as exc:
            error_msg = f"System Error: {exc}"
            log_execution_step('CONTROLLER_ERROR', error_msg)
            log_exception('CONTROLLER_ERROR', exc, {'message': message})
            return ControllerResponse(
                status='error',
                content=error_msg,
                ui_feedback=[],
            )

    def _process_queue(self, user_message: str, ui_callback=None, interface_type: str = 'UI') -> ControllerResponse:
        """
        Process the task queue serially until completion or user input required.
        
        Iterates through self.task_queue:
        - Handles 'greeting' or simple responses directly.
        - Delegates mechanism to _execute_current_task for Agents/Tools.
        - Aggregates results and UI feedback.
        """
        
        total_content = []
        all_ui_feedback = []
        max_queue_steps = max(1, self._get_int_setting('interaction_max_queue_steps', 120))
        
        while self.task_queue:
            queue_steps = self._increment_interaction_counter('interaction_queue_steps', 1)
            if queue_steps > max_queue_steps:
                stop_msg = (
                    "Safety stop: too many queued task steps in one interaction "
                    f"(count={queue_steps}, limit={max_queue_steps})."
                )
                log_execution_step('CONTROLLER_QUEUE_GUARD', stop_msg)
                return ControllerResponse(status='error', content=stop_msg, ui_feedback=all_ui_feedback)

            import threading
            cancel_event = self.cda.get_runtime('cancel_event')
            if cancel_event and isinstance(cancel_event, threading.Event) and cancel_event.is_set():
                log_execution_step('CONTROLLER_CANCELLED', "Controller queue processing cancelled by user.")
                self.clear_current_task()
                return ControllerResponse(status='error', content="Execution stopped by user.", ui_feedback=all_ui_feedback)
                
            self.current_task = self.task_queue.pop(0)
            current_task_type = str(self.current_task.get('type', '') or '').strip()
            if current_task_type in ('agent_call', 'continue'):
                selected_agent = str(self.current_task.get('selected_agent', '') or '')
                self._mark_interaction_agent_executed(selected_agent)
                allowed, reason = self._allow_agent_execution(selected_agent)
                if not allowed:
                    return ControllerResponse(status='error', content=reason, ui_feedback=all_ui_feedback)
            
            # Check for direct response interaction (greeting/clarification)
            if self.current_task.get('type') in ('greeting', 'request_user_input'):
                response_content = self.current_task.get('response_to_user', '')
                status = 'request_user_input' if self.current_task.get('type') == 'request_user_input' else 'complete'
                
                # If requesting input, pause queue here
                if status == 'request_user_input':
                    self.awaiting_user_input = True
                    if bool(self.current_task.get('_awaiting_token_budget_approval', False)):
                        self.current_task.setdefault('_token_resume_message', user_message)
                    # Return immediately to wait for user
                    return ControllerResponse(
                        status='request_user_input',
                        content=response_content,
                        ui_feedback=all_ui_feedback,
                        tool_request=self.current_task.get('tool_request'),
                    )
                
                # Greeting / completion message
                total_content.append(response_content)
                self._append_history(user_message if not total_content else '', response_content)
                continue

            # Execute Agent/Tool Task
            result = self._execute_current_task(user_message, ui_callback, interface_type=interface_type)
            
            all_ui_feedback.extend(result.ui_feedback)
            if result.content:
                total_content.append(result.content)

            if result.status == 'agent_call':
                handoff_count = int(self.cda.get_memory('interaction_handoff_count', 0) or 0) + 1
                self.cda.set_memory('interaction_handoff_count', handoff_count)
                max_handoffs = max(0, self._get_int_setting('interaction_max_handoffs', 12))
                if max_handoffs > 0 and handoff_count > max_handoffs:
                    stop_msg = (
                        f"Safety stop: too many agent handoffs in one interaction "
                        f"(count={handoff_count}, limit={max_handoffs})."
                    )
                    log_execution_step('CONTROLLER_HANDOFF_GUARD', stop_msg)
                    return ControllerResponse(status='error', content=stop_msg, ui_feedback=all_ui_feedback)

                new_agent = result.tool_request.get('selected_agent')
                source_agent = str(self.current_task.get('selected_agent', '') or '')
                if not str(new_agent or '').strip():
                    log_execution_step(
                        'CONTROLLER_HANDOFF_IGNORED',
                        f"Ignored empty handoff request from '{source_agent}'.",
                    )
                    continue

                already_in_queue = self._is_agent_in_queue(new_agent)
                already_executed = self._has_interaction_agent_executed(new_agent)
                if already_in_queue or already_executed:
                    reason_parts: List[str] = []
                    if already_in_queue:
                        reason_parts.append('already in queue')
                    if already_executed:
                        reason_parts.append('already executed in this interaction')
                    reason = ', '.join(reason_parts) or 'duplicate handoff'
                    log_execution_step(
                        'CONTROLLER_HANDOFF_IGNORED',
                        f"Ignored handoff {source_agent} -> {new_agent}: {reason}.",
                    )
                    continue

                removed_count = self._remove_agent_from_queue(new_agent)
                handoff_instruction = str(result.content or '').strip()
                agent_hint = (
                    f"{source_agent or 'Previous agent'} suggested routing to '{new_agent}'. "
                    f"{handoff_instruction if handoff_instruction else 'No explicit instruction provided.'}"
                )
                self.cda.set_memory('interaction_agent_hint', agent_hint)
                log_execution_step(
                    'CONTROLLER_HANDOFF_BLOCKED',
                    f"Blocked direct agent-to-agent handoff: {source_agent} -> {new_agent}. Re-routing via Router. "
                    f"Removed queued duplicates: {removed_count}.",
                )
                reroute_hint = json.dumps(
                    {
                        'event': 'agent_requested_handoff',
                        'source_agent': source_agent,
                        'requested_agent': new_agent,
                        'instruction': handoff_instruction,
                        'agent_hint': agent_hint,
                        'removed_from_queue': removed_count,
                        'policy': 'Agents must not directly call other agents. Router must choose the next task.',
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                reroute_allowed, reroute_error = self._allow_reroute('handling blocked agent handoff')
                if not reroute_allowed:
                    return ControllerResponse(status='error', content=reroute_error, ui_feedback=all_ui_feedback)
                task_input_files = self.current_task.get('_attached_file_paths') or None
                new_routes = self._route(
                    user_message,
                    input_files=[Path(f) for f in task_input_files] if task_input_files else None,
                    tool_output=reroute_hint,
                    chat_history=self._get_chat_history(),
                    interface_type=interface_type,
                )
                if isinstance(new_routes, dict):
                    new_routes = [new_routes]
                for route in new_routes or []:
                    if not isinstance(route, dict):
                        continue
                    route_type = str(route.get('type', '') or '').strip()
                    if route_type in ('agent_call', 'continue'):
                        route['_internal_reroute'] = True
                        # Use router instruction for downstream handoff tasks instead of replaying
                        # original user prompt every loop.
                        route['_preserve_user_input'] = False
                        route.setdefault('_original_user_input', user_message)
                if new_routes:
                    for task in reversed(new_routes):
                        self.task_queue.insert(0, task)
                continue

            if result.status == 'request_user_input':
                self.awaiting_user_input = True
                if isinstance(result.tool_request, dict) and str(result.tool_request.get('permission_type', '') or '') == 'token_budget_continue':
                    self.current_task['_awaiting_token_budget_approval'] = True
                    self.current_task['_token_resume_message'] = user_message
                    if '_attached_file_paths' in self.current_task:
                        self.current_task['_token_resume_input_files'] = list(self.current_task.get('_attached_file_paths') or [])
                return ControllerResponse(
                    status='request_user_input',
                    content="\n\n".join(total_content), # Return what we have so far + question
                    ui_feedback=all_ui_feedback,
                    tool_request=result.tool_request
                )
            
            if result.status == 'error':
                 # Stop chain on error
                 return result

        return ControllerResponse(
            status='complete',
            content="\n\n".join(total_content),
            ui_feedback=all_ui_feedback
        )

    def _execute_current_task(self, prompt: str, ui_callback=None, interface_type: str = 'UI') -> Any: # Returns ExecutorResult-like object
        """
        Executes a single task from the queue.
        
        Handles two main types of tasks:
        1. Tool Call: Directly executes a tool (via Router instruction) and feeds result back to Router.
        2. Agent Execution: Delegates the task to a specific Agent via the Executor.
        """
        
        # 1. Check for Direct Tool Call (New Router Capability)
        if self.current_task.get('type') == 'tool_call':
            tool_name = self.current_task.get('tool_name')
            params = self.current_task.get('parameters', {})
            
            log_execution_step('CONTROLLER_TOOL', f"Router Executing Tool: {tool_name}")
            
            try:
                # Direct import to avoid circular dependency
                from tools.tool_registry import call_tool
                
                tool_payload = {
                    'agent_name': 'Controller',
                    'tool_name': tool_name,
                    'parameters': params,
                }
                self._emit_trace('tool_prepared', tool_payload)
                allowed, guard_msg = self._allow_tool_call(str(tool_name or ''), params)
                if not allowed:
                    from core.executor import ExecutorResult
                    result = ExecutorResult(status='error', content=guard_msg, ui_feedback=[])
                    self._append_history(prompt, result.content)
                    return result

                status_cb = self.cda.get_runtime('tool_status_handler')
                if status_cb:
                    status_cb(f"Routing direct tool call for '{tool_name}'...")
                    
                result_data = call_tool(tool_name, params, status_callback=status_cb)
                if status_cb:
                    status_cb("") # Clear progress

                self.cda.set_memory('tool_data', result_data)
                created = collect_created_file_info(result_data)
                if created is not None:
                    created_files = self.cda.get_memory('created_files', [])
                    if not isinstance(created_files, list):
                        created_files = []
                    created_files = list(created_files)
                    created_files.append(created)
                    self.cda.set_memory('created_files', created_files)
                    self.cda.set_memory('last_created_file', created)

                self._emit_trace('tool_result', {**tool_payload, 'result': result_data})
                
                # Feedback Loop: Send tool result back to Router for synthesis
                # This allows the Router to see the output of the tool it requested
                # and generate a final natural language response or FURTHER tasks.
                tool_output_str = json.dumps(result_data, indent=2)
                log_execution_step('CONTROLLER_TOOL_FEEDBACK', f"Feeding result back to Router: {tool_output_str[:100]}...")
                
                # Re-route with tool output
                reroute_allowed, reroute_error = self._allow_reroute('feeding tool output back to Router')
                if not reroute_allowed:
                    from core.executor import ExecutorResult
                    result = ExecutorResult(status='error', content=reroute_error, ui_feedback=[])
                    self._append_history(prompt, result.content)
                    return result
                task_input_files = self.current_task.get('_attached_file_paths') or None
                new_routes = self._route(
                    prompt,
                    input_files=[Path(f) for f in task_input_files] if task_input_files else None,
                    tool_output=tool_output_str,
                    chat_history=self._get_chat_history(),
                    interface_type=interface_type,
                )
                if isinstance(new_routes, dict):
                    new_routes = [new_routes]
                for route in new_routes or []:
                    if not isinstance(route, dict):
                        continue
                    route_type = str(route.get('type', '') or '').strip()
                    if route_type in ('agent_call', 'continue'):
                        route.setdefault('_preserve_user_input', True)
                        route.setdefault('_original_user_input', prompt)
                
                # Handle complex re-routing: if Router returns more tasks, prepend them to queue
                if new_routes:
                    first_task = new_routes[0]
                    # If there are multiple tasks, or the first task is NOT a simple greeting/input, 
                    # we should probably prepend them to continue the flow.
                    if len(new_routes) > 1 or first_task.get('type') in ('agent_call', 'continue', 'tool_call'):
                        log_execution_step('CONTROLLER_REROUTE', f"Adding {len(new_routes)} tasks from feedback loop to queue.")
                        # Insert at the beginning of the queue
                        for task in reversed(new_routes):
                            self.task_queue.insert(0, task)
                        
                        # Return a 'complete' status for THIS task execution, 
                        # but _process_queue will pick up the next task.
                        from core.executor import ExecutorResult
                        return ExecutorResult(status='complete', content='', ui_feedback=[])
                    
                    # Simple case: just a message back to user
                    content = first_task.get('response_to_user', f"Tool executed. Result: {tool_output_str}")
                    status = 'complete'
                else:
                    content = f"Tool executed. Result: {tool_output_str}"
                    status = 'complete'

                from core.executor import ExecutorResult
                result = ExecutorResult(status=status, content=content, ui_feedback=[], tool_request=None)
            except Exception as e:
                error_msg = f"Tool execution failed: {e}"
                log_execution_step('CONTROLLER_TOOL_ERROR', error_msg)
                from core.executor import ExecutorResult
                result = ExecutorResult(status='error', content=error_msg, ui_feedback=[])
                
            self._append_history(prompt, result.content)
            return result

        # 2. Standard Agent Execution
        # Handle 'agent_call' (new) or 'continue' (legacy)
        route_type = self.current_task.get('type')
        if route_type in ('agent_call', 'continue'):
            agent_name = self.current_task.get('selected_agent')
            # Build effective instruction while preserving raw user input for router-originated tasks.
            task_instruction = self._compose_agent_instruction(self.current_task, prompt)
            refined_instruction = str(self.current_task.get('instruction', '') or '').strip() or task_instruction
            prompt_ctx = self.cda.get_memory('prompt_context_dict', {})
            if not isinstance(prompt_ctx, dict):
                prompt_ctx = {}
            prompt_ctx = dict(prompt_ctx)
            prompt_ctx['INSTRUCTIONS'] = refined_instruction
            self.cda.set_memory('prompt_context_dict', prompt_ctx)
            if self._active_session is not None:
                self._active_session.metadata['prompt_context_dict'] = dict(prompt_ctx)
            resume = bool(self.current_task.get('_resume', False))
            
            # Delegate to Executor for the agent loop
            self._emit_trace('controller_delegate_agent', {'agent_name': agent_name, 'instruction': task_instruction})
            try:
                result = self.executor.execute(
                    agent_name,
                    task_instruction,
                    ui_callback=ui_callback,
                    resume=resume,
                    session_ctx=self._get_session_context(),
                    interface_type=interface_type,
                    llm_attachments=self.current_task.get('_llm_attachments'),
                    input_files=self.current_task.get('_attached_file_paths'),
                )
            except ExecutorError as exc:
                if not self._is_token_budget_error(str(exc)):
                    raise
                token_request = self._build_token_budget_request_payload(
                    source=f"agent:{agent_name}",
                    detail=str(exc),
                )
                from core.executor import ExecutorResult
                result = ExecutorResult(
                    status='request_user_input',
                    content=str(token_request.get('prompt', 'Token budget reached. Continue?')),
                    ui_feedback=[],
                    tool_request=token_request,
                )

            if bool(self.current_task.get('_internal_reroute', False)):
                self._append_history('', result.content)
            else:
                self._append_history(prompt, result.content)
            return result

        # Fallback for unexpected task types
        error_msg = f"Unknown task type: {route_type}"
        log_execution_step('CONTROLLER_ERROR', error_msg)
        from core.executor import ExecutorResult
        return ExecutorResult(status='error', content=error_msg, ui_feedback=[])

    def _append_history(self, user_msg: str, assistant_msg: str):
        history = self._get_chat_history()
        if self._active_session is not None:
            user_id = str(self._active_session.user_id or '')
            iface = str(self._active_session.interface or 'UI')
        else:
            user_id = str(self.cda.get_setting('current_user_id', '') or '')
            iface = str(self.cda.get_setting('interface', 'UI') or 'UI')
        user_prefix = f"User[UserID:{user_id}][Interface:{iface}]"
        assistant_prefix = f"Assistant[UserID:{user_id}][Interface:{iface}]"
        if history:
            history += '\n'
        if user_msg:
             history += f"{user_prefix}: {user_msg}\n"
        history += f"{assistant_prefix}: {assistant_msg}"
        
        self._set_chat_history(history)
        self._persist_channel_chat_turn(user_msg, assistant_msg, user_id=user_id, interface=iface)
        
        # Log History for Debugging
        session_id = str(self.cda.get_setting('active_log_session', 'default'))
        log_chat_history('Controller', session_id, history)

    def _persist_channel_chat_turn(self, user_msg: str, assistant_msg: str, user_id: str, interface: str) -> None:
        """Persist non-UI channel turns into ChatHistory/ChatLog so history page can show them."""
        if self._normalize_interface_type(interface) == 'UI':
            return

        db_path = Path(str(self.cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
        if not db_path.exists():
            return

        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(ChatHistory)")
            ch_cols = {str(row[1]) for row in cur.fetchall()}
            cur.execute("PRAGMA table_info(ChatLog)")
            cl_cols = {str(row[1]) for row in cur.fetchall()}

            chat_id: Optional[int] = None
            if self._active_session is not None and self._active_session.current_chat_id is not None:
                existing_chat_id = int(self._active_session.current_chat_id)
                cur.execute("SELECT 1 FROM ChatHistory WHERE id=?", (existing_chat_id,))
                if cur.fetchone():
                    chat_id = existing_chat_id

            if chat_id is None:
                title = (user_msg or assistant_msg or "New Chat").strip()[:50] or "New Chat"
                if 'user_id' in ch_cols and 'interface' in ch_cols:
                    cur.execute(
                        "INSERT INTO ChatHistory (title, user_id, interface) VALUES (?, ?, ?)",
                        (title, user_id, interface),
                    )
                elif 'user_id' in ch_cols:
                    cur.execute(
                        "INSERT INTO ChatHistory (title, user_id) VALUES (?, ?)",
                        (title, user_id),
                    )
                else:
                    cur.execute("INSERT INTO ChatHistory (title) VALUES (?)", (title,))
                chat_id = int(cur.lastrowid)
                if self._active_session is not None:
                    self._active_session.current_chat_id = chat_id

            if 'agent_activity' in ch_cols and chat_id is not None:
                activity = ""
                if self._active_session is not None:
                    activity = str(self._active_session.agent_activity or "")
                if not activity:
                    activity = str(self.cda.get_memory('agent_activity', '') or '')
                if activity:
                    cur.execute(
                        "UPDATE ChatHistory SET agent_activity=? WHERE id=?",
                        (activity, chat_id),
                    )

            def _insert_row(role: str, content: str) -> None:
                text = str(content or "").strip()
                if not text:
                    return
                if 'user_id' in cl_cols and 'interface' in cl_cols:
                    cur.execute(
                        "INSERT INTO ChatLog (chat_id, role, content, user_id, interface) VALUES (?, ?, ?, ?, ?)",
                        (chat_id, role, text, user_id, interface),
                    )
                elif 'user_id' in cl_cols:
                    cur.execute(
                        "INSERT INTO ChatLog (chat_id, role, content, user_id) VALUES (?, ?, ?, ?)",
                        (chat_id, role, text, user_id),
                    )
                else:
                    cur.execute(
                        "INSERT INTO ChatLog (chat_id, role, content) VALUES (?, ?, ?)",
                        (chat_id, role, text),
                    )

            _insert_row("User", user_msg)
            _insert_row("Agent", assistant_msg)
            conn.commit()
        except Exception as exc:
            log_exception(
                'CHAT_DB_PERSIST_ERROR',
                exc,
                {'interface': interface, 'user_id': user_id},
            )
        finally:
            conn.close()





