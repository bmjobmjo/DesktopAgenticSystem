"""Runtime process manager for headless WhatsApp bridge scripts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from core.common_data_area import CommonDataArea
from settings.config_loader import update_setting


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class WhatsAppHeadlessBridgeService:
    """Controls register.js and daemon.js as background processes."""

    def __init__(self, cda: CommonDataArea) -> None:
        self.cda = cda
        self._lock = threading.RLock()

        self.root_dir = Path(__file__).resolve().parents[2]
        self.headless_dir = self.root_dir / "apps" / "whatsapp_bridge" / "headless"
        self.windows_bridge_dir = self.root_dir / "apps" / "whatsapp_bridge" / "windows"
        self.register_script = self.headless_dir / "register.js"
        self.daemon_script = self.headless_dir / "daemon.js"
        self.register_exe = self.windows_bridge_dir / "cli_register.exe"
        self.daemon_exe = self.windows_bridge_dir / "cli_daemon.exe"
        self.das_settings_file = self.headless_dir / "das_settings.json"
        self.auth_session_dir = self.headless_dir / "auth_session"

        self._register_proc: Optional[subprocess.Popen[str]] = None
        self._daemon_proc: Optional[subprocess.Popen[str]] = None

        self._register_logs: Deque[str] = deque(maxlen=240)
        self._daemon_logs: Deque[str] = deque(maxlen=240)

        self._register_state: Dict[str, Any] = {
            "running": False,
            "session_id": "",
            "phone_number": "",
            "pairing_code": "",
            "stage": "idle",
            "started_at": "",
            "ended_at": "",
            "exit_code": None,
            "last_error": "",
        }
        self._daemon_state: Dict[str, Any] = {
            "running": False,
            "pid": None,
            "stage": "stopped",
            "started_at": "",
            "ended_at": "",
            "exit_code": None,
            "last_error": "",
        }

    def has_linked_auth_session(self) -> bool:
        creds_file = self.auth_session_dir / "creds.json"
        return creds_file.exists() and creds_file.is_file()

    @staticmethod
    def _normalize_phone(value: str) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    def _which_node(self) -> str:
        candidates = [
            self.root_dir / "node" / "node.exe",
            self.root_dir / "node" / "node",
            self.root_dir / "node" / "node.exe",
            self.root_dir / "node" / "node",
            self.root_dir.parent / "node" / "node.exe",
            self.root_dir.parent / "node" / "node",
            Path(r"D:\programs\node\node.exe"),
        ]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return str(candidate.resolve())
            except Exception:
                continue
        return str(shutil.which("node") or "").strip()

    @staticmethod
    def _is_windows() -> bool:
        return subprocess.os.name == "nt"

    def _resolve_register_command(self, mobile: str, base: str) -> tuple[list[str], Path]:
        node_path = self._which_node()
        if self._is_windows() and node_path and self.register_script.exists():
            return [node_path, str(self.register_script), "--phone", mobile, "--dir", base], self.headless_dir
        if self._is_windows() and self.register_exe.exists():
            return [str(self.register_exe), "--phone", mobile, "--dir", base], self.windows_bridge_dir
        if not node_path:
            raise RuntimeError("Node.js was not found and no packaged Windows WhatsApp bridge executable is available")
        if not self.register_script.exists():
            raise RuntimeError(f"register.js not found: {self.register_script}")
        return [node_path, str(self.register_script), "--phone", mobile, "--dir", base], self.headless_dir

    def _resolve_daemon_command(self) -> tuple[list[str], Path]:
        node_path = self._which_node()
        if self._is_windows() and node_path and self.daemon_script.exists():
            return [node_path, str(self.daemon_script)], self.headless_dir
        if self._is_windows() and self.daemon_exe.exists():
            return [str(self.daemon_exe)], self.windows_bridge_dir
        if not node_path:
            raise RuntimeError("Node.js was not found and no packaged Windows WhatsApp bridge executable is available")
        if not self.daemon_script.exists():
            raise RuntimeError(f"daemon.js not found: {self.daemon_script}")
        return [node_path, str(self.daemon_script)], self.headless_dir

    @staticmethod
    def _is_running(proc: Optional[subprocess.Popen[str]]) -> bool:
        return bool(proc is not None and proc.poll() is None)

    @staticmethod
    def _append_log(target: Deque[str], source: str, line: str) -> None:
        clean = str(line or "").rstrip("\r\n")
        if clean:
            target.append(f"{_utc_now()} [{source}] {clean}")

    def _load_das_settings(self) -> Dict[str, Any]:
        if not self.das_settings_file.exists():
            return {}
        try:
            return json.loads(self.das_settings_file.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def _save_das_settings(self, settings: Dict[str, Any]) -> None:
        self.headless_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(settings, indent=2, ensure_ascii=False)
        self.das_settings_file.write_text(text, encoding="utf-8")

    def _resolve_base_folder(self, base_folder: str = "") -> str:
        candidate = str(base_folder or "").strip()
        if candidate:
            return candidate
        configured = str(self.cda.get_setting("whatsapp_folder_root", "") or "").strip()
        if configured:
            return configured
        from_file = str(self._load_das_settings().get("baseFolder", "") or "").strip()
        if from_file:
            return from_file
        storage = str(self.cda.get_setting("file_storage_path", "storage/files") or "").strip() or "storage/files"
        storage_path = Path(storage)
        if not storage_path.is_absolute():
            storage_path = self.root_dir / storage_path
        return str((storage_path / "whatsapp_bridge_exchange").resolve())

    def _set_base_folder(self, base_folder: str) -> str:
        target = str(base_folder or "").strip()
        if not target:
            raise ValueError("Base folder is required")
        settings = self._load_das_settings()
        settings["enabled"] = True
        settings["baseFolder"] = target
        if "pollingInterval" not in settings:
            settings["pollingInterval"] = 2000
        if "watchNumbers" not in settings:
            settings["watchNumbers"] = []
        self._save_das_settings(settings)
        Path(target).mkdir(parents=True, exist_ok=True)
        try:
            self.cda.set_setting("whatsapp_folder_root", target)
        except Exception:
            pass
        try:
            update_setting("whatsapp_folder_root", target)
        except Exception:
            pass
        return target

    def _start_reader(
        self,
        proc: subprocess.Popen[str],
        stream: Any,
        source: str,
        sink: Deque[str],
        line_callback,
    ) -> None:
        def _run() -> None:
            try:
                for raw in iter(stream.readline, ""):
                    line = str(raw or "")
                    self._append_log(sink, source, line)
                    try:
                        line_callback(line)
                    except Exception:
                        pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()

    def _track_register_exit(self, proc: subprocess.Popen[str]) -> None:
        def _waiter() -> None:
            code = proc.wait()
            with self._lock:
                if self._register_proc is proc:
                    self._register_state["running"] = False
                    self._register_state["ended_at"] = _utc_now()
                    self._register_state["exit_code"] = int(code)
                    if int(code) != 0 and not str(self._register_state.get("last_error", "")).strip():
                        self._register_state["last_error"] = f"register.js exited with code {code}"
                        self._register_state["stage"] = "error"
                    elif int(code) == 0 and self._register_state.get("stage") == "idle":
                        self._register_state["stage"] = "completed"
                    self._register_proc = None

        threading.Thread(target=_waiter, daemon=True).start()

    def _track_daemon_exit(self, proc: subprocess.Popen[str]) -> None:
        def _waiter() -> None:
            code = proc.wait()
            with self._lock:
                if self._daemon_proc is proc:
                    self._daemon_state["running"] = False
                    self._daemon_state["ended_at"] = _utc_now()
                    self._daemon_state["exit_code"] = int(code)
                    self._daemon_state["pid"] = None
                    if int(code) != 0 and not str(self._daemon_state.get("last_error", "")).strip():
                        self._daemon_state["last_error"] = f"daemon.js exited with code {code}"
                        self._daemon_state["stage"] = "error"
                    else:
                        self._daemon_state["stage"] = "stopped"
                    self._daemon_proc = None

        threading.Thread(target=_waiter, daemon=True).start()

    def start_registration(self, phone_number: str, base_folder: str = "") -> Dict[str, Any]:
        with self._lock:
            if self._is_running(self._register_proc):
                raise RuntimeError("Registration process is already running")

            mobile = self._normalize_phone(phone_number)
            if len(mobile) < 10:
                raise ValueError("Invalid phone number")

            base = self._resolve_base_folder(base_folder)
            if not base:
                raise ValueError("Base folder is required")
            base = self._set_base_folder(base)

            # Always start registration with a clean auth session.
            if self.auth_session_dir.exists():
                shutil.rmtree(self.auth_session_dir, ignore_errors=True)

            cmd, cwd = self._resolve_register_command(mobile, base)
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self._register_proc = proc
            self._register_logs.clear()
            self._register_state.update(
                {
                    "running": True,
                    "session_id": uuid.uuid4().hex[:16],
                    "phone_number": mobile,
                    "pairing_code": "",
                    "stage": "starting",
                    "started_at": _utc_now(),
                    "ended_at": "",
                    "exit_code": None,
                    "last_error": "",
                }
            )

            def _on_line(raw: str) -> None:
                line = str(raw or "").strip()
                if not line:
                    return
                m = re.search(r"\[PAIRING_CODE\]\s*([A-Z0-9-]{8,})", line, flags=re.IGNORECASE)
                if not m:
                    m = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", line, flags=re.IGNORECASE)
                if m:
                    self._register_state["pairing_code"] = m.group(1).upper()
                    self._register_state["stage"] = "pairing_code_generated"
                if "[REGISTER_SUCCESS]" in line:
                    self._register_state["stage"] = "linked"
                if "[PAIRING_ERROR]" in line or "[REGISTER_ERROR]" in line:
                    self._register_state["stage"] = "error"
                    self._register_state["last_error"] = line
                    if self._is_running(proc):
                        proc.terminate()
                elif "Booting Baileys Protocol" in line:
                    self._register_state["stage"] = "requesting_pairing_code"

            assert proc.stdout is not None
            assert proc.stderr is not None
            self._start_reader(proc, proc.stdout, "stdout", self._register_logs, _on_line)
            self._start_reader(proc, proc.stderr, "stderr", self._register_logs, _on_line)
            self._track_register_exit(proc)
            return self.get_status()

    def stop_registration(self) -> Dict[str, Any]:
        with self._lock:
            proc = self._register_proc
            if not self._is_running(proc):
                self._register_state["running"] = False
                return self.get_status()
            assert proc is not None
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:
                proc.kill()
            self._register_state["running"] = False
            self._register_state["ended_at"] = _utc_now()
            self._register_state["stage"] = "stopped"
            self._register_proc = None
            return self.get_status()

    def start_daemon(self, base_folder: str = "") -> Dict[str, Any]:
        with self._lock:
            if self._is_running(self._daemon_proc):
                return self.get_status()

            base = self._resolve_base_folder(base_folder)
            if not base:
                raise ValueError("Base folder is required")
            self._set_base_folder(base)

            cmd, cwd = self._resolve_daemon_command()
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self._daemon_proc = proc
            self._daemon_logs.clear()
            self._daemon_state.update(
                {
                    "running": True,
                    "pid": proc.pid,
                    "stage": "starting",
                    "started_at": _utc_now(),
                    "ended_at": "",
                    "exit_code": None,
                    "last_error": "",
                }
            )

            def _on_line(raw: str) -> None:
                line = str(raw or "").strip()
                if not line:
                    return
                if "Protocol Manager initialized" in line:
                    self._daemon_state["stage"] = "running"
                elif "DAS Polling active on:" in line and self._daemon_state.get("stage") == "starting":
                    self._daemon_state["stage"] = "polling"
                if "[Daemon] Uncaught Exception:" in line or "[Daemon] Unhandled Rejection:" in line:
                    self._daemon_state["last_error"] = line
                    if self._daemon_state.get("stage") == "running":
                        self._daemon_state["stage"] = "degraded"

            assert proc.stdout is not None
            assert proc.stderr is not None
            self._start_reader(proc, proc.stdout, "stdout", self._daemon_logs, _on_line)
            self._start_reader(proc, proc.stderr, "stderr", self._daemon_logs, _on_line)
            self._track_daemon_exit(proc)
            return self.get_status()

    def stop_daemon(self) -> Dict[str, Any]:
        with self._lock:
            proc = self._daemon_proc
            if not self._is_running(proc):
                self._daemon_state["running"] = False
                self._daemon_state["pid"] = None
                self._daemon_state["stage"] = "stopped"
                return self.get_status()
            assert proc is not None
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:
                proc.kill()
            self._daemon_state["running"] = False
            self._daemon_state["pid"] = None
            self._daemon_state["ended_at"] = _utc_now()
            self._daemon_state["stage"] = "stopped"
            self._daemon_proc = None
            return self.get_status()

    def stop_all(self) -> None:
        try:
            self.stop_registration()
        except Exception:
            pass
        try:
            self.stop_daemon()
        except Exception:
            pass

    def logout(self) -> Dict[str, Any]:
        with self._lock:
            self.stop_all()
            if self.auth_session_dir.exists():
                shutil.rmtree(self.auth_session_dir, ignore_errors=True)
            self._register_state.update(
                {
                    "running": False,
                    "pairing_code": "",
                    "stage": "logged_out",
                    "ended_at": _utc_now(),
                    "last_error": "",
                }
            )
            self._daemon_state.update(
                {
                    "running": False,
                    "pid": None,
                    "stage": "stopped",
                    "ended_at": _utc_now(),
                    "last_error": "",
                }
            )
            return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            node_path = self._which_node()
            packaged_register = self.register_exe.exists()
            packaged_daemon = self.daemon_exe.exists()
            settings = self._load_das_settings()
            configured_base_folder = str(self.cda.get_setting("whatsapp_folder_root", "") or "").strip()
            file_base_folder = str(settings.get("baseFolder", "") or "").strip()
            effective_base_folder = self._resolve_base_folder("")
            register_running = self._is_running(self._register_proc)
            daemon_running = self._is_running(self._daemon_proc)
            if not register_running:
                self._register_state["running"] = False
            if not daemon_running:
                self._daemon_state["running"] = False
                if self._daemon_proc is None:
                    self._daemon_state["pid"] = None
            return {
                "headless_dir": str(self.headless_dir),
                "scripts": {
                    "register_js": str(self.register_script),
                    "daemon_js": str(self.daemon_script),
                    "register_exists": self.register_script.exists(),
                    "daemon_exists": self.daemon_script.exists(),
                    "register_exe": str(self.register_exe),
                    "daemon_exe": str(self.daemon_exe),
                    "register_exe_exists": packaged_register,
                    "daemon_exe_exists": packaged_daemon,
                },
                "node": {
                    "available": bool(node_path) or (packaged_register and packaged_daemon),
                    "path": node_path,
                    "packaged_windows_bridge": packaged_register and packaged_daemon,
                },
                "settings": {
                    "enabled": bool(settings.get("enabled", False)),
                    "base_folder": effective_base_folder,
                    "configured_base_folder": configured_base_folder,
                    "file_base_folder": file_base_folder,
                    "polling_interval": int(settings.get("pollingInterval", 2000) or 2000),
                    "watch_numbers": list(settings.get("watchNumbers", []) or []),
                },
                "auth_session_exists": self.auth_session_dir.exists(),
                "register": {
                    **self._register_state,
                    "running": register_running,
                    "logs_tail": list(self._register_logs),
                },
                "daemon": {
                    **self._daemon_state,
                    "running": daemon_running,
                    "logs_tail": list(self._daemon_logs),
                },
            }


