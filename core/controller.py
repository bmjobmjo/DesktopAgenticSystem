"""Controller orchestrator."""

from __future__ import annotations

import logging
import json
import inspect
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
            return name, email
        except Exception:
            return "", ""
        finally:
            conn.close()

    def _set_prompt_identity_context(self, user_id: str, username: str) -> None:
        """Update placeholder context so {{UID}}/{{USER_NAME}} are session-correct."""
        uid = str(user_id or "").strip()
        uname = str(username or "").strip() or (f"User {uid}" if uid else "")

        # CDA settings used by router and some prompt builders.
        if uid:
            self.cda.set_setting('current_user_id', uid)
        if uname:
            self.cda.set_setting('current_username', uname)

        # CDA/session prompt placeholders used by executor replacement.
        base_ctx = self.cda.get_memory('prompt_context_dict', {})
        if not isinstance(base_ctx, dict):
            base_ctx = {}
        ctx = dict(base_ctx)
        if uid:
            ctx['UID'] = uid
        if uname:
            ctx['USER_NAME'] = uname
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
        if raw in ('whatsapp', 'wa', 'whats_app'):
            return 'WHATSAPP'
        if raw in ('telegram', 'tg'):
            return 'TELEGRAM'
        if raw in ('scheduler', 'schedule', 'sheduler'):
            return 'SCHEDULER'
        return 'UI'

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
        return self.router.route(**kwargs)

    def _emit_trace(self, event_type: str, payload: Dict[str, Any]) -> None:
        handler = self.cda.get_runtime('executor_trace_handler')
        if callable(handler):
            try:
                import copy
                handler(event_type, copy.deepcopy(payload))
            except Exception:
                # Trace callback failures should not break execution flow.
                pass

    def clear_current_task(self) -> None:
        """Clears the controller's active task state (typically used on new chats)."""
        self.current_task = None
        self.awaiting_user_input = False
        self.task_queue.clear()
        if self._active_session is not None:
            self._active_session.current_task = None
            self._active_session.awaiting_user_input = False
            self._active_session.task_queue.clear()

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
        self.session_store.remove(effective_user_id, iface, effective_session_id)

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

        prompt_ctx = self.cda.get_memory('prompt_context_dict', {})
        if isinstance(prompt_ctx, dict):
            prompt_ctx = dict(prompt_ctx)
            prompt_ctx['CHAT_HISTORY'] = ''
            self.cda.set_memory('prompt_context_dict', prompt_ctx)

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
        prev_prompt_ctx = self.cda.get_memory('prompt_context_dict', {})
        prev_execution_metadata = self.cda.get_memory('execution_metadata_dict', {})
        self.cda.set_setting('interface', iface)
        self.cda.set_setting('INTERFACE_TYPE_UI_OR_WHATSAPP_OR_TELEGRAM', iface_type)
        self.cda.set_memory('INTERFACE_TYPE_UI_OR_WHATSAPP_OR_TELEGRAM', iface_type)
        effective_user_id = str(user_id) if user_id is not None else str(prev_user_id or '')
        resolved_name = ''
        resolved_email = ''
        if effective_user_id:
            resolved_name, resolved_email = self._resolve_user_identity(effective_user_id)
        if user_id is not None:
            self.cda.set_setting('current_user_id', str(user_id))
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
            self._set_prompt_identity_context(effective_user_id, resolved_name)
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
                     # Append this result to history is done in _execute_current_task
                     # Now continue queue
                     return self._process_queue(message, ui_callback, interface_type=interface_type)
            else:
                log_execution_step('CONTROLLER_REROUTE_AFTER_INPUT', f"Pending task type '{task_type}' is not resumable; routing fresh user input.")
                self.awaiting_user_input = False
                self.current_task = None

        history = self._get_chat_history()

        try:
            # 2. Route New Request
            # Ask the Router to breakdown the user message into one or more tasks.
            # Can return Agent tasks (delegate) or Tool tasks (direct execution).
            
            # Convert file strings to Path objects
            from pathlib import Path
            input_files = [Path(f) for f in files] if files else None
            
            routes = self._route(message, input_files=input_files, chat_history=history, interface_type=interface_type)
            if isinstance(routes, dict):
                routes = [routes]
            
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
        
        while self.task_queue:
            import threading
            cancel_event = self.cda.get_runtime('cancel_event')
            if cancel_event and isinstance(cancel_event, threading.Event) and cancel_event.is_set():
                log_execution_step('CONTROLLER_CANCELLED', "Controller queue processing cancelled by user.")
                self.clear_current_task()
                return ControllerResponse(status='error', content="Execution stopped by user.", ui_feedback=all_ui_feedback)
                
            self.current_task = self.task_queue.pop(0)
            
            # Check for direct response interaction (greeting/clarification)
            if self.current_task.get('type') in ('greeting', 'request_user_input'):
                response_content = self.current_task.get('response_to_user', '')
                status = 'request_user_input' if self.current_task.get('type') == 'request_user_input' else 'complete'
                
                # If requesting input, pause queue here
                if status == 'request_user_input':
                    self.awaiting_user_input = True
                    # Return immediately to wait for user
                    return ControllerResponse(
                        status='request_user_input',
                        content=response_content,
                        ui_feedback=all_ui_feedback
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
                new_agent = result.tool_request.get('selected_agent')
                log_execution_step('CONTROLLER_HANDOFF', f"Agent requested hand-off to: {new_agent}")
                # Prepend the new agent call to the queue
                handoff_task = {
                    'type': 'agent_call',
                    'selected_agent': new_agent,
                    'instruction': result.content, # Use the summary from previous agent as instruction
                    'priority': 1,
                    '_llm_attachments': self.current_task.get('_llm_attachments', []),
                    '_attached_file_paths': self.current_task.get('_attached_file_paths', []),
                }
                self.task_queue.insert(0, handoff_task)
                continue

            if result.status == 'request_user_input':
                self.awaiting_user_input = True
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
                task_input_files = self.current_task.get('_attached_file_paths') or None
                new_routes = self._route(
                    prompt,
                    input_files=[Path(f) for f in task_input_files] if task_input_files else None,
                    tool_output=tool_output_str,
                    chat_history=self._get_chat_history(),
                    interface_type=interface_type,
                )
                
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
            # Use specific instruction if available, otherwise original prompt
            task_instruction = self.current_task.get('instruction', prompt)
            resume = bool(self.current_task.get('_resume', False))
            
            # Delegate to Executor for the agent loop
            self._emit_trace('controller_delegate_agent', {'agent_name': agent_name, 'instruction': task_instruction})
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





