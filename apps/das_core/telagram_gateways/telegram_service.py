"""Telegram polling service."""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
import re
import sqlite3
import ssl
from pathlib import Path
from typing import Any, Dict, List
from urllib import parse as urlparse
from urllib import request as urlrequest

from core.common_data_area import CommonDataArea
from core.ssl_compat import create_ssl_context
from execution_logger import log_exception, log_execution_step
from telagram_gateways.telegram_controller import TelegramController
from telagram_gateways.telegram_log import telegram_log


class TelegramChannelService:
    def __init__(self, cda: CommonDataArea, telegram_controller: TelegramController) -> None:
        self.cda = cda
        self.telegram_controller = telegram_controller
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._offset: int = 0
        self._last_error: str = ""
        self._running: bool = False
        self._status_message: str = "Telegram service is idle."
        self._ssl_context: ssl.SSLContext = create_ssl_context()
        self._session_timeout_seconds: int = int(self.cda.get_setting("channel_session_timeout_seconds", 3600) or 3600)

    def _token(self) -> str:
        return str(self.cda.get_setting("telegram_bot_token", "") or "").strip()

    def _poll_timeout(self) -> int:
        try:
            return max(1, int(self.cda.get_setting("telegram_poll_timeout", 25) or 25))
        except Exception:
            return 25

    def _poll_retry_seconds(self) -> float:
        try:
            return max(0.25, float(self.cda.get_setting("telegram_poll_retry_seconds", 2) or 2))
        except Exception:
            return 2.0

    def _api_url(self, method: str) -> str:
        token = self._token()
        return f"https://api.telegram.org/bot{token}/{method}"

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()

    def _is_duplicate_update(self, update_id: int) -> bool:
        if int(update_id or 0) <= 0:
            return False
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ChannelInboundMessages (provider, message_id, handled) VALUES (?, ?, 0)",
                ("telegram", str(update_id)),
            )
            conn.commit()
            return False
        except sqlite3.IntegrityError:
            return True
        finally:
            conn.close()

    def _mark_update_handled(self, update_id: int) -> None:
        if int(update_id or 0) <= 0:
            return
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE ChannelInboundMessages SET handled=1 WHERE provider=? AND message_id=?",
                ("telegram", str(update_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def start(self) -> None:
        if not bool(self.cda.get_setting("telegram_enabled", False)):
            self._running = False
            self._status_message = "Telegram is disabled in settings."
            telegram_log("telegram_start", "Telegram disabled by settings; polling not started.")
            return
        if not self._token():
            self._running = False
            self._status_message = "Telegram bot token is missing."
            log_execution_step("TELEGRAM_START", "Telegram token missing; polling not started.")
            telegram_log("telegram_start", "Bot token missing; polling not started.")
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._running = True
            self._last_error = ""
            self._status_message = "Telegram polling is starting."
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            log_execution_step("TELEGRAM_START", "Telegram polling started.")
            telegram_log(
                "telegram_start",
                f"Polling started timeout={self._poll_timeout()}s retry={self._poll_retry_seconds()}s",
            )
            self._status_message = "Telegram polling is running."

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None
            self._running = False
            self._status_message = "Telegram polling is stopped."
            log_execution_step("TELEGRAM_STOP", "Telegram polling stopped.")
            telegram_log("telegram_stop", "Polling stopped.")

    def restart(self) -> None:
        self._ssl_context = create_ssl_context()
        self.stop()
        self.start()

    def _http_get_json(self, url: str, timeout: int) -> Dict[str, Any]:
        req = urlrequest.Request(url, method="GET")
        with urlrequest.urlopen(req, timeout=timeout, context=self._ssl_context) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            return data if isinstance(data, dict) else {}

    def _http_post_json(self, url: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlrequest.urlopen(req, timeout=timeout, context=self._ssl_context) as res:
            data = json.loads(res.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}

    def _http_post_multipart(
        self,
        url: str,
        fields: Dict[str, str],
        file_field: str,
        file_path: Path,
        timeout: int = 45,
    ) -> Dict[str, Any]:
        boundary = f"----DesktopAgenticBoundary{uuid.uuid4().hex}"
        file_bytes = file_path.read_bytes()
        file_name = file_path.name
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")

        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        req = urlrequest.Request(url, data=bytes(body), headers=headers, method="POST")
        with urlrequest.urlopen(req, timeout=timeout, context=self._ssl_context) as res:
            data = json.loads(res.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}

    def _get_updates(self) -> List[Dict[str, Any]]:
        params = {
            "timeout": self._poll_timeout(),
            "offset": self._offset,
            "allowed_updates": json.dumps(["message"]),
        }
        url = f"{self._api_url('getUpdates')}?{urlparse.urlencode(params)}"
        data = self._http_get_json(url, timeout=self._poll_timeout() + 5)
        if not bool(data.get("ok", False)):
            raise RuntimeError(str(data.get("description", "Telegram getUpdates failed")))
        result = data.get("result", [])
        if isinstance(result, list):
            return [x for x in result if isinstance(x, dict)]
        return []

    @staticmethod
    def _safe_filename(name: str, fallback: str) -> str:
        raw = str(name or "").strip()
        candidate = raw or fallback
        candidate = re.sub(r'[\\/:*?"<>|]+', '_', candidate)
        return candidate[:180] or fallback

    def _inbound_base_dir(self, chat_id: str) -> Path:
        default_directory = str(self.cda.get_setting("default_directory", "") or "").strip()
        if default_directory:
            root = Path(default_directory).expanduser()
        else:
            root = Path("data")
        return root / "telegram_inbound" / (str(chat_id or "").strip() or "unknown")

    def _download_telegram_file(self, file_id: str, suggested_name: str, chat_id: str) -> str:
        file_id = str(file_id or "").strip()
        if not file_id:
            return ""

        meta = self._http_get_json(
            f"{self._api_url('getFile')}?{urlparse.urlencode({'file_id': file_id})}",
            timeout=20,
        )
        if not bool(meta.get('ok', False)):
            raise RuntimeError(str(meta.get('description', 'Telegram getFile failed')))

        result = meta.get('result', {})
        if not isinstance(result, dict):
            raise RuntimeError('Telegram getFile returned invalid payload')

        remote_path = str(result.get('file_path', '') or '').strip()
        if not remote_path:
            raise RuntimeError('Telegram file path missing')

        download_url = f"https://api.telegram.org/file/bot{self._token()}/{remote_path}"
        with urlrequest.urlopen(urlrequest.Request(download_url, method='GET'), timeout=60, context=self._ssl_context) as res:
            data = res.read()

        base_dir = self._inbound_base_dir(chat_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        remote_name = Path(remote_path).name
        fallback_name = remote_name or suggested_name or f"telegram_file_{uuid.uuid4().hex}"
        file_name = self._safe_filename(suggested_name or remote_name, fallback_name)
        out_path = base_dir / f"{uuid.uuid4().hex}_{file_name}"
        out_path.write_bytes(data)
        telegram_log('inbound_file_saved', f"chat_id={chat_id} path={out_path}")
        return str(out_path.resolve())

    def _extract_inbound_payload(self, update: Dict[str, Any]) -> tuple[str, str, List[str]]:
        msg = update.get("message", {})
        if not isinstance(msg, dict):
            return "", "", []

        chat = msg.get("chat", {})
        chat_id = ""
        if isinstance(chat, dict):
            chat_id = str(chat.get("id", "") or "").strip()

        text = str(msg.get("text", "") or msg.get('caption', '') or "").strip()
        files: List[str] = []

        document = msg.get('document')
        if isinstance(document, dict):
            file_id = str(document.get('file_id', '') or '').strip()
            file_name = str(document.get('file_name', '') or 'telegram_document')
            if chat_id and file_id:
                files.append(self._download_telegram_file(file_id, file_name, chat_id))

        photos = msg.get('photo')
        if isinstance(photos, list) and photos:
            largest = None
            for item in photos:
                if not isinstance(item, dict):
                    continue
                if largest is None or int(item.get('file_size', 0) or 0) >= int(largest.get('file_size', 0) or 0):
                    largest = item
            if isinstance(largest, dict):
                file_id = str(largest.get('file_id', '') or '').strip()
                if chat_id and file_id:
                    files.append(self._download_telegram_file(file_id, 'telegram_photo.jpg', chat_id))

        return chat_id, text, [f for f in files if str(f).strip()]

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                try:
                    manager = getattr(self.telegram_controller, 'conversation_manager', None)
                    if manager is not None:
                        expired = manager.close_inactive(
                            'Telegram',
                            timeout_seconds=self._session_timeout_seconds,
                        )
                    elif getattr(self.telegram_controller, 'controller', None) is not None:
                        expired = self.telegram_controller.controller.close_inactive_channel_sessions(
                            'Telegram',
                            timeout_seconds=self._session_timeout_seconds,
                        )
                    else:
                        expired = []
                    for item in expired:
                        sid = str(item.get('session_id', '') or '').replace('telegram:', '').strip()
                        if sid:
                            self.send_text(sid, 'Your chat session expired due to inactivity (1 hour). Session closed.')
                except Exception:
                    pass

                updates = self._get_updates()
                for upd in updates:
                    update_id = int(upd.get('update_id', 0) or 0)
                    if update_id >= self._offset:
                        self._offset = update_id + 1
                    if self._is_duplicate_update(update_id):
                        telegram_log('duplicate', f"update_id={update_id}")
                        continue


                    chat_id, text, files = self._extract_inbound_payload(upd)
                    if not chat_id or (not text and not files):
                        continue
                    telegram_log(
                        'inbound',
                        f"chat_id={chat_id} text_len={len(text)} file_count={len(files)} update_id={update_id}",
                    )
                    ack = 'File received. Working on it...' if files else 'Message received. Working on it...'
                    self.send_text(chat_id, ack)
                    self._process_inbound_message(chat_id, text, files)
                    self._mark_update_handled(update_id)
                self._last_error = ''
                self._status_message = "Telegram polling is running."
            except Exception as exc:
                self._last_error = str(exc)
                self._status_message = f"Telegram polling error: {self._last_error}"
                log_exception('TELEGRAM_POLL_ERROR', exc, {})
                telegram_log('poll_error', self._last_error)
                time.sleep(self._poll_retry_seconds())

    def _process_inbound_message(self, chat_id: str, text: str, files: List[str] | None = None) -> None:
        last_status = {'value': ''}

        def _channel_ui_feedback(feedback: Dict[str, Any]) -> None:
            try:
                status = str((feedback or {}).get('status', '') or '').strip()
                message = str((feedback or {}).get('message', '') or '').strip()
                hint = str((feedback or {}).get('progress_hint', '') or '').strip()
                parts = [x for x in [message, hint] if x]
                text_out = ' | '.join(parts).strip()
                if not text_out:
                    return
                prefix = f"[{status}] " if status else ''
                full = f"{prefix}{text_out}"
                if full == last_status['value']:
                    return
                last_status['value'] = full
                self.send_text(chat_id, full)
            except Exception:
                return

        effective_text = str(text or '').strip()
        inbound_files = [str(f) for f in (files or []) if str(f).strip()]
        if inbound_files:
            docs_msg = f"Attached {len(inbound_files)} document(s)."
            if effective_text:
                effective_text = f"{docs_msg} {effective_text}".strip()
            else:
                effective_text = docs_msg

        def _completion(text_out: str) -> None:
            if text_out:
                self.send_text(chat_id, text_out)

        response_text = self.telegram_controller.handle_inbound_safe(
            chat_id,
            effective_text,
            files=inbound_files,
            ui_callback=_channel_ui_feedback,
            completion_callback=_completion,
        )
        if response_text:
            self.send_text(chat_id, response_text)

    def send_text(self, chat_id: str, text: str) -> Dict[str, Any]:
        payload = {
            'chat_id': str(chat_id),
            'text': str(text or ''),
        }
        try:
            data = self._http_post_json(self._api_url('sendMessage'), payload, timeout=15)
            telegram_log('outbound', f"chat_id={chat_id} ok={bool(data.get('ok', False))} text_len={len(str(text or ''))}")
            return data
        except Exception as exc:
            telegram_log('outbound_error', f"chat_id={chat_id} error={exc}")
            return {'ok': False, 'error': str(exc)}

    def send_document(self, chat_id: str, file_path: str, caption: str = '') -> Dict[str, Any]:
        path = Path(str(file_path or '')).expanduser().resolve()
        if not path.exists() or not path.is_file():
            return {'ok': False, 'error': f"File not found: {path}"}

        fields = {'chat_id': str(chat_id)}
        if str(caption or '').strip():
            fields['caption'] = str(caption)

        try:
            data = self._http_post_multipart(
                self._api_url('sendDocument'),
                fields=fields,
                file_field='document',
                file_path=path,
                timeout=60,
            )
            telegram_log(
                'outbound_document',
                f"chat_id={chat_id} ok={bool(data.get('ok', False))} file={path.name}",
            )
            return data
        except Exception as exc:
            telegram_log('outbound_document_error', f"chat_id={chat_id} file={path.name} error={exc}")
            return {'ok': False, 'error': str(exc)}

    def get_status(self) -> Dict[str, Any]:
        enabled = bool(self.cda.get_setting('telegram_enabled', False))
        has_token = bool(self._token())
        running = bool(self._running and self._thread is not None and self._thread.is_alive())
        if running:
            stage = "running"
        elif not enabled:
            stage = "disabled"
        elif not has_token:
            stage = "missing_token"
        elif self._last_error:
            stage = "error"
        else:
            stage = "stopped"
        return {
            'running': running,
            'offset': self._offset,
            'last_error': self._last_error,
            'enabled': enabled,
            'has_token': has_token,
            'stage': stage,
            'status_message': self._status_message,
            'poll_timeout': self._poll_timeout(),
            'poll_retry_seconds': self._poll_retry_seconds(),
        }


