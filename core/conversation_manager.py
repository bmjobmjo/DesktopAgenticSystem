"""Conversation runtime manager with shared worker-pool scheduling."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.common_data_area import CommonDataArea
from core.controller import Controller, ControllerResponse
from core.conversation_context import ConversationContext
from core.conversation_runtime import ConversationRuntime
from core.executor import Executor
from core.inbound_request import InboundRequest
from core.router import Router
from execution_logger import log_exception, log_execution_step
from llm.factory import get_llm_client


@dataclass
class SyncResult:
    response: Optional[ControllerResponse] = None
    error: Optional[BaseException] = None


class ConversationManager:
    """Owns isolated runtimes and serializes execution per conversation."""

    def __init__(self, app_cda: CommonDataArea, max_workers: int = 16) -> None:
        self.app_cda = app_cda
        self._lock = threading.RLock()
        self._runtimes: Dict[str, ConversationRuntime] = {}
        self._pool = ThreadPoolExecutor(max_workers=max(1, int(max_workers)))

    def _create_runtime(self, conversation_id: str, interface: str, user_id: str) -> ConversationRuntime:
        ctx = ConversationContext(self.app_cda, conversation_id)
        ctx.set_runtime("cancel_event", threading.Event())
        try:
            ctx.set_runtime("llm_client", get_llm_client(ctx))
        except Exception as exc:
            log_exception("CONVERSATION_LLM_INIT_ERROR", exc, {"conversation_id": conversation_id})

        router = Router(ctx)
        executor = Executor(ctx)
        controller = Controller(cda=ctx, router=router, executor=executor)
        return ConversationRuntime(
            conversation_id=conversation_id,
            interface=interface,
            user_id=user_id,
            cda=ctx,
            router=router,
            executor=executor,
            controller=controller,
        )

    def get_or_create_runtime(self, conversation_id: str, interface: str, user_id: str) -> ConversationRuntime:
        conv_id = str(conversation_id or "").strip() or "default"
        iface = str(interface or "UI").strip() or "UI"
        uid = str(user_id or "").strip() or "unknown"
        with self._lock:
            runtime = self._runtimes.get(conv_id)
            if runtime is None:
                runtime = self._create_runtime(conv_id, iface, uid)
                self._runtimes[conv_id] = runtime
            runtime.interface = iface
            runtime.user_id = uid
            runtime.touch()
            return runtime

    def size(self) -> int:
        with self._lock:
            return len(self._runtimes)

    def list_active_sessions(self) -> List[dict]:
        sessions: List[dict] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            runtimes = list(self._runtimes.values())
        for runtime in runtimes:
            try:
                listed = runtime.controller.list_active_sessions()
            except Exception:
                listed = []
            if listed:
                for item in listed:
                    row = dict(item)
                    row.setdefault("session_id", runtime.conversation_id)
                    row.setdefault("channel", runtime.interface)
                    sessions.append(row)
                continue

            history = str(runtime.cda.get_memory("chat_history", "") or "").strip()
            lines = [ln.strip() for ln in history.splitlines() if ln.strip()]
            idle_sec = max(0, int((now - runtime.last_access_utc).total_seconds()))
            sessions.append(
                {
                    "user_id": runtime.user_id,
                    "user": runtime.user_id,
                    "channel": runtime.interface,
                    "session_id": runtime.conversation_id,
                    "last_message": lines[-1] if lines else "",
                    "last_access_utc": runtime.last_access_utc.isoformat(),
                    "idle_seconds": idle_sec,
                    "chat_history": history,
                }
            )
        sessions.sort(key=lambda x: x.get("last_access_utc", ""), reverse=True)
        return sessions

    def get_agent_activity(self, conversation_id: str) -> str:
        with self._lock:
            runtime = self._runtimes.get(str(conversation_id or "").strip() or "default")
        if runtime is None:
            return ""
        return str(runtime.cda.get_memory("agent_activity", "") or "")

    def hydrate_ui_history(
        self,
        conversation_id: str,
        user_id: str,
        chat_history: str,
        agent_activity: str = "",
        current_chat_id: Optional[int] = None,
    ) -> None:
        runtime = self.get_or_create_runtime(conversation_id, "UI", user_id)
        runtime.cda.set_memory("chat_history", str(chat_history or ""))
        runtime.cda.set_memory("agent_activity", str(agent_activity or ""))
        if current_chat_id is not None:
            runtime.cda.set_memory("current_chat_id", int(current_chat_id))
        try:
            session = runtime.controller.session_store.get_or_create(user_id, "UI", conversation_id)
            session.chat_history = str(chat_history or "")
            session.agent_activity = str(agent_activity or "")
            session.current_chat_id = int(current_chat_id) if current_chat_id is not None else None
        except Exception as exc:
            log_exception(
                "CONVERSATION_HISTORY_HYDRATE_ERROR",
                exc,
                {"conversation_id": conversation_id, "user_id": user_id},
            )

    def submit(self, request: InboundRequest) -> None:
        runtime = self.get_or_create_runtime(request.conversation_id, request.interface, request.user_id)
        with runtime.lock:
            runtime.pending.append(request)
            runtime.touch()
            if runtime.running:
                return
            runtime.running = True
        self._pool.submit(self._drain_runtime, runtime)

    def execute_sync(self, request: InboundRequest, timeout: float | None = None) -> ControllerResponse:
        done = threading.Event()
        result = SyncResult()

        def _complete(response: ControllerResponse) -> None:
            result.response = response
            done.set()

        req = InboundRequest(
            conversation_id=request.conversation_id,
            interface=request.interface,
            user_id=request.user_id,
            message=request.message,
            files=list(request.files or []),
            execution_metadata=dict(request.execution_metadata or {}),
            ui_callback=request.ui_callback,
            status_callback=request.status_callback,
            trace_callback=request.trace_callback,
            permission_callback=request.permission_callback,
            completion_callback=_complete,
        )
        self.submit(req)
        if not done.wait(timeout):
            raise TimeoutError(f"Synchronous conversation execution timed out for {request.conversation_id}")
        if result.error is not None:
            raise result.error
        if result.response is None:
            raise RuntimeError(f"Conversation execution produced no response for {request.conversation_id}")
        return result.response

    def cancel(self, conversation_id: str) -> bool:
        conv_id = str(conversation_id or "").strip() or "default"
        with self._lock:
            runtime = self._runtimes.get(conv_id)
        if runtime is None:
            return False
        cancel_event = runtime.cda.get_runtime("cancel_event")
        if cancel_event and isinstance(cancel_event, threading.Event):
            cancel_event.set()
            return True
        return False

    def close_inactive(self, interface: str | None = None, timeout_seconds: int = 3600) -> List[dict]:
        iface = str(interface or "").strip().lower()
        now = datetime.now(timezone.utc)
        closed: List[dict] = []
        remove_ids: List[str] = []

        with self._lock:
            runtimes = list(self._runtimes.values())

        for runtime in runtimes:
            if iface and str(runtime.interface or "").strip().lower() != iface:
                continue
            if runtime.running:
                continue
            idle = (now - runtime.last_access_utc).total_seconds()
            if idle < int(timeout_seconds):
                continue

            history = str(runtime.cda.get_memory("chat_history", "") or "").strip()
            lines = [ln.strip() for ln in history.splitlines() if ln.strip()]
            remove_ids.append(runtime.conversation_id)
            closed.append(
                {
                    "user_id": runtime.user_id,
                    "session_id": runtime.conversation_id,
                    "interface": runtime.interface,
                    "last_message": lines[-1] if lines else "",
                    "idle_seconds": int(idle),
                }
            )

        if remove_ids:
            with self._lock:
                for conv_id in remove_ids:
                    self._runtimes.pop(conv_id, None)
        return closed

    def shutdown(self) -> None:
        with self._lock:
            self._runtimes.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _drain_runtime(self, runtime: ConversationRuntime) -> None:
        while True:
            with runtime.lock:
                if not runtime.pending:
                    runtime.running = False
                    return
                request = runtime.pending.popleft()
                runtime.touch()

            cancel_event = runtime.cda.get_runtime("cancel_event")
            if cancel_event and isinstance(cancel_event, threading.Event):
                cancel_event.clear()

            runtime.cda.set_runtime("executor_trace_handler", request.trace_callback)
            runtime.cda.set_runtime("executor_permission_handler", request.permission_callback)
            runtime.cda.set_runtime("tool_status_handler", request.status_callback)

            try:
                log_execution_step(
                    "CONVERSATION_DISPATCH",
                    f"conversation={runtime.conversation_id} interface={request.interface} user_id={request.user_id}",
                )
                response = runtime.controller.handle_user_message(
                    request.message,
                    files=request.files or None,
                    interface=request.interface,
                    user_id=request.user_id,
                    session_id=request.conversation_id,
                    ui_callback=request.ui_callback,
                    execution_metadata=request.execution_metadata,
                )
            except Exception as exc:
                log_exception(
                    "CONVERSATION_EXECUTION_ERROR",
                    exc,
                    {"conversation_id": runtime.conversation_id, "interface": request.interface},
                )
                response = ControllerResponse(status="error", content=f"System Error: {exc}", ui_feedback=[])
            finally:
                runtime.touch()
                runtime.cda.clear_runtime("executor_trace_handler")
                runtime.cda.clear_runtime("executor_permission_handler")
                runtime.cda.clear_runtime("tool_status_handler")

            if callable(request.completion_callback):
                try:
                    request.completion_callback(response)
                except Exception as exc:
                    log_exception(
                        "CONVERSATION_COMPLETION_CALLBACK_ERROR",
                        exc,
                        {"conversation_id": runtime.conversation_id},
                    )
