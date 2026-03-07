"""WhatsApp channel integration: local webhook receiver + gateway client."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import queue
import sqlite3
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib import request as urlrequest
from urllib.parse import urlparse

from core.common_data_area import CommonDataArea
from execution_logger import log_exception, log_execution_step


class WhatsAppChannelService:
    def __init__(self, cda: CommonDataArea, controller: Any) -> None:
        self.cda = cda
        self.controller = controller
        self._http_server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._gateway_proc: subprocess.Popen | None = None
        self._gateway_log_thread: threading.Thread | None = None
        self._inbound_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=2000)
        self._inbound_worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db"))).resolve()

    def _gateway_url(self) -> str:
        return str(self.cda.get_setting("whatsapp_gateway_url", "http://127.0.0.1:5715") or "").rstrip("/")

    def _secret(self) -> str:
        return str(self.cda.get_setting("whatsapp_webhook_secret", "change-me") or "change-me")

    def start(self) -> None:
        if not bool(self.cda.get_setting("whatsapp_enabled", False)):
            return

        self._start_inbound_worker()
        self._start_webhook_server()
        if bool(self.cda.get_setting("whatsapp_auto_start_gateway", False)):
            self._start_gateway_process()

    def stop(self) -> None:
        with self._lock:
            if self._http_server is not None:
                try:
                    self._http_server.shutdown()
                except Exception:
                    pass
                self._http_server = None
            if self._server_thread is not None and self._server_thread.is_alive():
                self._server_thread.join(timeout=1.0)
            self._server_thread = None

            if self._gateway_proc is not None:
                try:
                    self._gateway_proc.terminate()
                except Exception:
                    pass
                self._gateway_proc = None
            self._gateway_log_thread = None
            self._stop_event.set()
            if self._inbound_worker_thread is not None and self._inbound_worker_thread.is_alive():
                self._inbound_worker_thread.join(timeout=1.0)
            self._inbound_worker_thread = None
            self._drain_inbound_queue()

    def _drain_inbound_queue(self) -> None:
        while True:
            try:
                self._inbound_queue.get_nowait()
                self._inbound_queue.task_done()
            except queue.Empty:
                return

    def _start_inbound_worker(self) -> None:
        with self._lock:
            if self._inbound_worker_thread is not None and self._inbound_worker_thread.is_alive():
                return
            self._stop_event.clear()

            def _worker() -> None:
                while not self._stop_event.is_set():
                    try:
                        payload = self._inbound_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    try:
                        self.handle_inbound(payload)
                    except Exception as exc:
                        log_exception("WHATSAPP_INBOUND_WORKER_ERROR", exc, payload)
                    finally:
                        self._inbound_queue.task_done()

            self._inbound_worker_thread = threading.Thread(target=_worker, daemon=True)
            self._inbound_worker_thread.start()

    def enqueue_inbound(self, payload: Dict[str, Any]) -> bool:
        """Queue inbound webhook payload for async processing; returns False if queue is full."""
        try:
            self._inbound_queue.put_nowait(payload)
            return True
        except queue.Full:
            return False

    def _start_gateway_process(self) -> None:
        with self._lock:
            if self._gateway_proc is not None and self._gateway_proc.poll() is None:
                return
            gateway_url = self._gateway_url()
            if self._is_gateway_port_in_use(gateway_url):
                log_execution_step("WHATSAPP_GATEWAY", f"Gateway already listening at {gateway_url}; skipping auto-start.")
                return
            cmd = str(self.cda.get_setting("whatsapp_gateway_command", "node whatsapp-gateway/src/server.js") or "").strip()
            if not cmd:
                return
            env = os.environ.copy()
            env["WEBHOOK_URL"] = self.webhook_url()
            env["WEBHOOK_SECRET"] = self._secret()
            default_auth_dir = str((Path.cwd() / "whatsapp-gateway" / "auth_state").resolve())
            default_media_dir = str((Path.cwd() / "whatsapp-gateway" / "inbound_media").resolve())
            env["AUTH_DIR"] = str(self.cda.get_setting("whatsapp_auth_dir", default_auth_dir) or default_auth_dir)
            env["MEDIA_DIR"] = str(self.cda.get_setting("whatsapp_media_dir", default_media_dir) or default_media_dir)
            try:
                self._gateway_proc = subprocess.Popen(
                    cmd,
                    cwd=str(Path.cwd()),
                    env=env,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                log_execution_step("WHATSAPP_GATEWAY", f"Started process: {cmd}")
                self._start_gateway_log_pump(self._gateway_proc)
            except Exception as exc:
                log_exception("WHATSAPP_GATEWAY_START_ERROR", exc, {"command": cmd})

    @staticmethod
    def _is_gateway_port_in_use(gateway_url: str) -> bool:
        try:
            parsed = urlparse(str(gateway_url or "").strip())
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 5715)
            with socket.create_connection((host, port), timeout=0.8):
                return True
        except Exception:
            return False

    def _start_gateway_log_pump(self, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return

        def _pump() -> None:
            try:
                for raw_line in proc.stdout:
                    line = str(raw_line or "").strip()
                    if line:
                        log_execution_step("WHATSAPP_GATEWAY_OUT", line)
            except Exception as exc:
                log_exception("WHATSAPP_GATEWAY_LOG_PUMP_ERROR", exc, {})

        self._gateway_log_thread = threading.Thread(target=_pump, daemon=True)
        self._gateway_log_thread.start()

    def webhook_url(self) -> str:
        host = str(self.cda.get_setting("whatsapp_webhook_host", "127.0.0.1") or "127.0.0.1")
        port = int(self.cda.get_setting("whatsapp_webhook_port", 5716) or 5716)
        return f"http://{host}:{port}/channel/inbound/whatsapp"

    def _start_webhook_server(self) -> None:
        with self._lock:
            if self._http_server is not None:
                return
            host = str(self.cda.get_setting("whatsapp_webhook_host", "127.0.0.1") or "127.0.0.1")
            port = int(self.cda.get_setting("whatsapp_webhook_port", 5716) or 5716)

            service = self

            class _Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    if self.path != "/channel/inbound/whatsapp":
                        self.send_response(404)
                        self.end_headers()
                        return
                    raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
                    sig = self.headers.get("X-Webhook-Signature", "")
                    if not service._verify_signature(raw, sig):
                        self.send_response(401)
                        self.end_headers()
                        return

                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        self.send_response(400)
                        self.end_headers()
                        return

                    try:
                        queued = service.enqueue_inbound(payload)
                        if not queued:
                            log_execution_step("WHATSAPP_WEBHOOK_QUEUE_FULL", "Inbound queue is full; dropping message")
                            self.send_response(503)
                            self.end_headers()
                            return
                    except Exception as exc:
                        log_exception("WHATSAPP_WEBHOOK_ENQUEUE_ERROR", exc, payload)
                        self.send_response(500)
                        self.end_headers()
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')

                def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                    return

            self._http_server = ThreadingHTTPServer((host, port), _Handler)
            self._server_thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
            self._server_thread.start()
            log_execution_step("WHATSAPP_WEBHOOK", f"Listening at http://{host}:{port}/channel/inbound/whatsapp")

    def _verify_signature(self, raw: bytes, signature: str) -> bool:
        expected = hmac.new(self._secret().encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return bool(signature) and hmac.compare_digest(expected, signature)

    def _is_duplicate_message(self, provider: str, message_id: str) -> bool:
        if not message_id:
            return False
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ChannelInboundMessages (provider, message_id, handled) VALUES (?, ?, 0)",
                (provider, message_id),
            )
            conn.commit()
            return False
        except sqlite3.IntegrityError:
            return True
        finally:
            conn.close()

    def _mark_handled(self, provider: str, message_id: str) -> None:
        if not message_id:
            return
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE ChannelInboundMessages SET handled=1 WHERE provider=? AND message_id=?",
                (provider, message_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _resolve_or_create_user_id(self, provider: str, channel_user_id: str) -> str:
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id FROM ChannelUsers WHERE provider=? AND channel_user_id=?",
                (provider, channel_user_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])

            fallback = str(self.cda.get_setting("current_user_id", "") or "").strip()
            user_id = fallback if fallback else channel_user_id
            cur.execute(
                "INSERT INTO ChannelUsers (provider, channel_user_id, user_id) VALUES (?, ?, ?)",
                (provider, channel_user_id, user_id),
            )
            conn.commit()
            return user_id
        finally:
            conn.close()

    def _resolve_user_id_from_channel_mapping(self, provider: str, channel_user_id: str) -> str:
        if not provider or not channel_user_id:
            return ""
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id FROM ChannelUsers WHERE provider=? AND channel_user_id=?",
                (provider, channel_user_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])
            return ""
        finally:
            conn.close()

    @staticmethod
    def _is_ignorable_channel_jid(channel_user_id: str) -> bool:
        raw = str(channel_user_id or "").strip().lower()
        if not raw:
            return True
        # Ignore noisy non-user channels.
        if raw == "status@broadcast":
            return True
        if raw.endswith("@newsletter"):
            return True
        return False

    @staticmethod
    def _normalize_number(value: str) -> str:
        if not value:
            return ""
        return "".join(ch for ch in str(value) if ch.isdigit())

    @staticmethod
    def _extract_number_from_jid(channel_user_id: str) -> str:
        raw = str(channel_user_id or "").strip()
        if not raw:
            return ""
        # Typical forms: 9198xxxxxxx@s.whatsapp.net, 9198xxxxxxx:12@s.whatsapp.net
        left = raw.split("@", 1)[0]
        left = left.split(":", 1)[0]
        return WhatsAppChannelService._normalize_number(left)

    @staticmethod
    def _numbers_match(sender: str, stored: str) -> bool:
        a = WhatsAppChannelService._normalize_number(sender)
        b = WhatsAppChannelService._normalize_number(stored)
        if not a or not b:
            return False
        if a == b:
            return True
        # Tolerate saved-with/without country code; require reasonable phone length.
        if len(a) >= 8 and len(b) >= 8 and (a.endswith(b) or b.endswith(a)):
            return True
        return False

    def _resolve_enrolled_user_id_by_phone(self, channel_user_id: str) -> str:
        sender_num = self._extract_number_from_jid(channel_user_id)
        if not sender_num:
            return ""

        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]) for r in cur.fetchall()}
            if "id" not in cols:
                return ""

            # Preferred order: whatsapp_number, then mobile_number.
            select_cols = ["id"]
            if "whatsapp_number" in cols:
                select_cols.append("whatsapp_number")
            else:
                select_cols.append("'' AS whatsapp_number")
            if "mobile_number" in cols:
                select_cols.append("mobile_number")
            else:
                select_cols.append("'' AS mobile_number")

            cur.execute(f"SELECT {', '.join(select_cols)} FROM Users")
            for row in cur.fetchall():
                user_id = str(row[0]) if row and row[0] is not None else ""
                wa_num = str(row[1] or "") if len(row) > 1 else ""
                mobile_num = str(row[2] or "") if len(row) > 2 else ""
                if self._numbers_match(sender_num, wa_num) or self._numbers_match(sender_num, mobile_num):
                    return user_id
            return ""
        finally:
            conn.close()

    def handle_inbound(self, payload: Dict[str, Any]) -> None:
        provider = str(payload.get("provider", "whatsapp") or "whatsapp").strip().lower()
        message_id = str(payload.get("message_id", "") or "").strip()
        channel_user_id = str(payload.get("channel_user_id", "") or "").strip()
        text = str(payload.get("text", "") or "").strip()
        files_payload = payload.get("files", [])
        files: list[str] = []
        if isinstance(files_payload, list):
            for item in files_payload:
                if isinstance(item, str):
                    candidate = str(item).strip()
                elif isinstance(item, dict):
                    candidate = str(item.get("path", "") or "").strip()
                else:
                    candidate = ""
                if candidate:
                    try:
                        p = Path(candidate).expanduser().resolve()
                        if p.exists() and p.is_file():
                            files.append(str(p))
                    except Exception:
                        continue
        session_id = str(payload.get("session_id", "default") or "default").strip()
        timeout_seconds = int(self.cda.get_setting("channel_session_timeout_seconds", 3600) or 3600)

        if not text and not files:
            return
        if not text and files:
            text = "Process the attached files."
        if self._is_duplicate_message(provider, message_id):
            log_execution_step("WHATSAPP_WEBHOOK_DUP", f"Duplicate message skipped: {message_id}")
            return

        if self._is_ignorable_channel_jid(channel_user_id):
            log_execution_step(
                "WHATSAPP_INBOUND_SKIPPED",
                f"Ignored non-user channel sender '{channel_user_id}'.",
            )
            return

        user_id = self._resolve_enrolled_user_id_by_phone(channel_user_id)
        if not user_id:
            user_id = self._resolve_user_id_from_channel_mapping(provider, channel_user_id)
            if user_id:
                log_execution_step(
                    "WHATSAPP_INBOUND_FALLBACK",
                    f"Using ChannelUsers mapping for sender '{channel_user_id}' -> user_id={user_id}",
                )

        if not user_id:
            try:
                user_id = self._resolve_or_create_user_id(provider, channel_user_id)
                if user_id:
                    log_execution_step(
                        "WHATSAPP_INBOUND_AUTO_MAP",
                        f"Auto-mapped sender '{channel_user_id}' -> user_id={user_id}",
                    )
            except Exception:
                user_id = ""

        if not user_id:
            log_execution_step(
                "WHATSAPP_INBOUND_SKIPPED",
                f"No enrolled user match for sender '{channel_user_id}'. Message ignored.",
            )
            return
        # Keep channel mapping table in sync for traceability/joins.
        try:
            self._resolve_or_create_user_id(provider, channel_user_id)
        except Exception:
            pass

        log_execution_step(
            "WHATSAPP_INBOUND",
            f"Message from {channel_user_id} matched enrolled user_id={user_id} files={len(files)}",
        )

        try:
            # Expire stale channel sessions and notify users.
            try:
                expired = self.controller.close_inactive_channel_sessions("WhatsApp", timeout_seconds=timeout_seconds)
                for item in expired:
                    to_id = str(item.get("session_id", "") or "").replace("whatsapp:", "").strip()
                    if to_id:
                        self.send_text(to_id, "Your chat session expired due to inactivity (1 hour). Session closed.")
            except Exception:
                pass

            target_id = session_id or channel_user_id
            if target_id:
                self.send_text(target_id, "Message received. Working on it...")

            last_status = {"value": ""}

            def _channel_ui_feedback(feedback: Dict[str, Any]) -> None:
                try:
                    status = str((feedback or {}).get("status", "") or "").strip()
                    message = str((feedback or {}).get("message", "") or "").strip()
                    hint = str((feedback or {}).get("progress_hint", "") or "").strip()
                    parts = [x for x in [message, hint] if x]
                    text_out = " | ".join(parts).strip()
                    if not text_out:
                        return
                    prefix = f"[{status}] " if status else ""
                    full = f"{prefix}{text_out}"
                    if full == last_status["value"]:
                        return
                    last_status["value"] = full
                    self.send_text(target_id, full)
                except Exception:
                    return

            result = self.controller.handle_user_message(
                text,
                files=files or None,
                interface="WhatsApp",
                user_id=user_id,
                channel_id=channel_user_id,
                session_id=f"whatsapp:{channel_user_id}",
                ui_callback=_channel_ui_feedback,
            )
            out_text = str(getattr(result, "content", "") or "").strip()
            if out_text:
                self.send_text(target_id, out_text)
            self._mark_handled(provider, message_id)
        except Exception as exc:
            log_exception("WHATSAPP_INBOUND_EXEC_ERROR", exc, payload)

    def send_text(self, to: str, text: str) -> Dict[str, Any]:
        url = f"{self._gateway_url()}/send"
        body = json.dumps({"to": to, "text": text}).encode("utf-8")
        req = urlrequest.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=15) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data if isinstance(data, dict) else {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_gateway_status(self) -> Dict[str, Any]:
        url = f"{self._gateway_url()}/status"
        req = urlrequest.Request(url, method="GET")
        try:
            with urlrequest.urlopen(req, timeout=8) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data if isinstance(data, dict) else {"connected": False}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    def get_gateway_qr(self) -> Dict[str, Any]:
        url = f"{self._gateway_url()}/qr"
        req = urlrequest.Request(url, method="GET")
        try:
            with urlrequest.urlopen(req, timeout=8) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data if isinstance(data, dict) else {"ok": False}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def disconnect(self) -> Dict[str, Any]:
        url = f"{self._gateway_url()}/disconnect"
        req = urlrequest.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=12) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data if isinstance(data, dict) else {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
