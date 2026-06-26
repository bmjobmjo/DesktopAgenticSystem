"""Execution logging utilities."""

from __future__ import annotations

import os
import logging
import traceback
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from core.common_data_area import CommonDataArea

def _resolve_log_dir() -> Path:
    try:
        cda = CommonDataArea()
        configured = str(cda.get_setting('logs_path', '') or '').strip()
        if configured:
            base = Path(configured)
            if not base.is_absolute():
                base = (Path.cwd() / base).resolve()
            base.mkdir(parents=True, exist_ok=True)
            return base
    except Exception:
        pass
    fallback = Path(__file__).resolve().parent / 'logs'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# Directories
LOG_DIR = _resolve_log_dir()

class ExecutionLogger:
    """
    Unified Logger component providing static logging methods.
    Does not keep files open; performs Open-Write-Close for every entry.
    """
    _session_ts: str = ""
    _prompt_file: Optional[Path] = None
    _detailed_file: Optional[Path] = None
    _history_file: Optional[Path] = None
    _log_callback: Optional[Callable] = None
    _trace_counter: int = 0
    _trace_lock = threading.Lock()

    @classmethod
    def _init_session(cls):
        """Initializes a new session. Always creates new log files on startup."""
        if cls._session_ts:
            return  # Already initialized in this process

        now = datetime.now()
        ts = now.strftime('%Y%m%d_%H%M%S')
        
        # Keep .session_id updated for reference, but we don't reuse it anymore
        session_file = LOG_DIR / '.session_id'
        try:
            session_file.write_text(ts)
        except Exception:
            pass

        print(f"Initializing log session: {ts}")
        cls._session_ts = ts
        cls._prompt_file = LOG_DIR / f'prompts_{ts}.log'
        cls._detailed_file = LOG_DIR / f'detailed_{ts}.log'
        cls._history_file = LOG_DIR / f'chat_history_{ts}.log'
        
        # 4. Update CommonDataArea
        cda = CommonDataArea()
        cda.set_setting('active_log_session', ts)
        cda.set_setting('prompt_log_path', str(cls._prompt_file))
        cda.set_setting('detailed_log_path', str(cls._detailed_file))
        cda.set_setting('history_log_path', str(cls._history_file))

    @classmethod
    def _write_file(cls, file_path: Path, message: str):
        """Open, Write, and Close the file."""
        cls._init_session()
        try:
            # Ensure directory exists in case user deleted it mid-run
            global LOG_DIR
            LOG_DIR = _resolve_log_dir()
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} - {message}\n")
        except Exception as e:
            print(f"Logging failed to {file_path}: {e}")

    @classmethod
    def register_callback(cls, callback: Callable):
        cls._log_callback = callback

    @classmethod
    def log_prompt(cls, agent_name: str, prompt_text: str, result_text: str):
        entry = (
            f"\n{'-'*80}\n"
            f"AGENT:  {agent_name}\n"
            f"PROMPT:\n{prompt_text}\n"
            f"RESULT:\n{result_text}\n"
            f"{'-'*80}\n"
        )
        cls._write_file(cls._prompt_file, entry)
        
    @classmethod
    def log_chat_history(cls, context_type: str, session_id: str, history_text: str):
        entry = (
            f"\n{'='*80}\n"
            f"CONTEXT TYPE: {context_type}\n"
            f"SESSION ID:   {session_id}\n"
            f"CHAT HISTORY:\n{history_text}\n"
            f"{'='*80}\n"
        )
        cls._write_file(cls._history_file, entry)

    @classmethod
    def log_step(cls, step_type: str, details: str):
        message = f"[{step_type.upper()}] {details}"
        cls._write_file(cls._detailed_file, message)
        if cls._log_callback:
            try:
                cls._log_callback(message)
            except:
                pass

    @classmethod
    def log_exception(cls, step_type: str, exc: Exception, context: Any = None):
        tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        context_text = f" | Context: {context}" if context is not None else ""
        message = (
            f"[{step_type.upper()}] {type(exc).__name__}: {exc}{context_text}\n"
            f"Traceback:\n{tb}"
        )
        cls.log_step(step_type, message)

    @classmethod
    def save_trace_file(cls, prefix: str, content: str) -> str:
        """Saves arbitrary text content to a timestamped file and returns the path."""
        cls._init_session()
        global LOG_DIR
        LOG_DIR = _resolve_log_dir()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with cls._trace_lock:
                cls._trace_counter += 1
                seq = cls._trace_counter

            now = datetime.now()
            ts = now.strftime('%Y%m%d_%H%M%S')
            ms = now.microsecond // 1000
            filename = f"{prefix}_{ts}_{ms:03d}_{seq:06d}.txt"
            file_path = LOG_DIR / filename

            # Use exclusive-create mode to guarantee we never overwrite.
            with open(file_path, "x", encoding="utf-8") as f:
                f.write(content)
            return str(file_path.absolute())
        except FileExistsError:
            # Extremely rare race fallback.
            try:
                fallback = LOG_DIR / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
                with open(fallback, "x", encoding="utf-8") as f:
                    f.write(content)
                return str(fallback.absolute())
            except Exception as e:
                print(f"Failed to save trace file {file_path}: {e}")
                return ""
        except Exception as e:
            print(f"Failed to save trace file {file_path}: {e}")
            return ""

# --- Global Wrappers for Compatibility ---

def register_log_callback(callback):
    ExecutionLogger.register_callback(callback)

def log_prompt(agent_name: str, prompt_text: str, result_text: str) -> None:
    ExecutionLogger.log_prompt(agent_name, prompt_text, result_text)

def log_execution_step(step_type: str, details: str) -> None:
    ExecutionLogger.log_step(step_type, details)

def log_exception(step_type: str, exc: Exception, context: Any = None) -> None:
    ExecutionLogger.log_exception(step_type, exc, context)

def log_chat_history(context_type: str, session_id: str, history_text: str) -> None:
    ExecutionLogger.log_chat_history(context_type, session_id, history_text)

def log_router_decision(decision: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    if isinstance(decision, dict):
        decision = [decision]
    for item in decision:
        target = item.get('tool_name') if item.get('type') == 'tool_call' else item.get('selected_agent', 'unknown')
        label = "Tool" if item.get('type') == 'tool_call' else "Agent"
        conf = item.get('confidence', 'unknown')
        reason = item.get('reason', '')
        log_execution_step('ROUTER', f"Selected {label}: {target} (Conf: {conf}). Reason: {reason}")

def log_tool_call(tool_name: str, parameters: Dict[str, Any], result: Dict[str, Any]) -> None:
    log_execution_step('TOOL_CALL', f"Tool: {tool_name} | Params: {parameters}")
    success = result.get('success', False) if isinstance(result, dict) else 'unknown'
    log_execution_step('TOOL_RESULT', f"Success: {success} | Output: {result}")

# Initialize session immediately
ExecutionLogger._init_session()
ExecutionLogger.log_step('LOGGER_INIT', f"Session active: {ExecutionLogger._session_ts}")

# Backward-compatible module-level file handles used by older tests/callers.
DETAILED_LOG_FILE = ExecutionLogger._detailed_file
PROMPT_LOG_FILE = ExecutionLogger._prompt_file
CHAT_HISTORY_FILE = ExecutionLogger._history_file
