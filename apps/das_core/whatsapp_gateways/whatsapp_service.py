"""WhatsApp shared-folder bridge service."""

from __future__ import annotations

import json
import random
import re
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from core.common_data_area import CommonDataArea
from execution_logger import log_exception, log_execution_step
from whatsapp_gateways.whatsapp_controller import WhatsAppController
from whatsapp_gateways.whatsapp_log import whatsapp_log

MENU_TEXT = (
    "Available commands:\n"
    "/register - Link your WhatsApp to DAS.\n"
    "Use: send /register, then send your WhatsApp number, then OTP.\n\n"
    "/new - Start a fresh conversation.\n"
    "Use: send /new to clear current context and agent activity history."
)

UNREGISTERED_HI_TEXT = (
    "You have reached Oasis, but you are not a registered user. "
    "Initiate registration by sending /register"
)


class WhatsAppFolderService:
    def __init__(self, cda: CommonDataArea, whatsapp_controller: WhatsAppController) -> None:
        self.cda = cda
        self.whatsapp_controller = whatsapp_controller
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._last_error: str = ""
        self._running: bool = False
        self._register_contexts: Dict[str, Dict[str, Any]] = {}

    def _enabled(self) -> bool:
        return bool(self.cda.get_setting("whatsapp_enabled", False))

    def _poll_seconds(self) -> float:
        try:
            return max(0.5, float(self.cda.get_setting("whatsapp_poll_seconds", 1.0) or 1.0))
        except Exception:
            return 1.0

    def _root_dir(self) -> Path:
        configured = str(self.cda.get_setting("whatsapp_folder_root", "") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return Path("data") / "whatsapp_exchange"

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()

    def _db_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path()), timeout=20)
        conn.execute("PRAGMA busy_timeout = 20000")
        return conn

    def _headless_auth_session_dir(self) -> Path:
        configured = str(self.cda.get_setting("whatsapp_headless_auth_session_dir", "") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return Path(__file__).resolve().parents[2] / "whatsapp_bridge" / "headless" / "auth_session"

    def _paths(self) -> Dict[str, Path]:
        root = self._root_dir()
        return {
            "root": root,
            "received": root / "received",
            "send": root / "send",
            "working": root / "working",
            "backup": root / "backup",
            "error": root / "error",
            "staging": root / "staging",
        }

    def _ensure_dirs(self) -> None:
        for path in self._paths().values():
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _message_folder_id() -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{ts}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _timestamp_utc() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _normalize_mobile(value: str) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @classmethod
    def _normalize_channel_id(cls, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        low = raw.lower()
        if "@lid" in low:
            return low
        return cls._normalize_mobile(raw)

    def _is_duplicate_inbound(self, message_id: str) -> bool:
        mid = str(message_id or "").strip()
        if not mid:
            return False
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ChannelInboundMessages (provider, message_id, handled) VALUES (?, ?, 0)",
                ("whatsapp", mid),
            )
            conn.commit()
            return False
        except sqlite3.IntegrityError:
            return True
        finally:
            conn.close()

    def _mark_inbound_handled(self, message_id: str) -> None:
        mid = str(message_id or "").strip()
        if not mid:
            return
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE ChannelInboundMessages SET handled=1 WHERE provider=? AND message_id=?",
                ("whatsapp", mid),
            )
            conn.commit()
        finally:
            conn.close()

    def start(self) -> None:
        if not self._enabled():
            whatsapp_log("whatsapp_start", "WhatsApp folder bridge disabled; watcher not started.")
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._ensure_dirs()
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            log_execution_step("WHATSAPP_START", "WhatsApp folder watcher started.")

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            self._thread = None
            self._running = False
            log_execution_step("WHATSAPP_STOP", "WhatsApp folder watcher stopped.")

    def restart(self) -> None:
        self.stop()
        self.start()

    @staticmethod
    def _safe_attachment_name(name: str, fallback: str = "attachment.bin") -> str:
        raw = str(name or "").strip()
        candidate = raw or fallback
        candidate = re.sub(r'[\\/:*?"<>|]+', "_", candidate)
        return candidate[:180] or fallback

    def _move_tree(self, src: Path, dst: Path) -> Path:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            raise FileExistsError(f"Target folder exists: {dst}")
        return Path(shutil.move(str(src), str(dst)))

    def _write_error(self, message_dir: Path, code: str, detail: str) -> None:
        text = f"{self._timestamp_utc()}\n{code}\n{detail}\n"
        (message_dir / "error.txt").write_text(text, encoding="utf-8")

    def _find_inbound_messages(self) -> List[Tuple[str, Path]]:
        received = self._paths()["received"]
        items: List[Tuple[str, Path]] = []
        if not received.exists():
            return items
        for sender_dir in received.iterdir():
            if not sender_dir.is_dir():
                continue
            sender_folder_raw = str(sender_dir.name or "").strip()
            if not sender_folder_raw:
                continue
            for msg_dir in sender_dir.iterdir():
                if msg_dir.is_dir():
                    items.append((sender_folder_raw, msg_dir))
        items.sort(key=lambda x: x[1].name)
        return items

    def _collect_attachment_paths(self, message_dir: Path, attachments: Any) -> List[str]:
        if not isinstance(attachments, list):
            return []
        resolved: List[str] = []
        for item in attachments:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("relative_path", "") or "").strip().replace("\\", "/")
            if not rel:
                continue
            full = (message_dir / rel).resolve()
            if full.exists() and full.is_file():
                resolved.append(str(full))
        return resolved

    def _same_channel_identity(self, a: str, b: str) -> bool:
        na = self._normalize_channel_id(a)
        nb = self._normalize_channel_id(b)
        if not na or not nb:
            return False
        if "@lid" in na or "@lid" in nb:
            return na == nb
        return self._normalize_mobile(na) == self._normalize_mobile(nb)

    def _canonical_sender_id(self, payload: Dict[str, Any], sender_folder_raw: str) -> str:
        sender_id = self._normalize_channel_id(str(payload.get("sender_id", "") or ""))
        sender_folder = self._normalize_channel_id(str(payload.get("sender_folder", "") or sender_folder_raw))
        if "@lid" in sender_id:
            return sender_id
        if "@lid" in sender_folder:
            return sender_folder
        if sender_folder:
            return sender_folder
        return sender_id

    def _validate_inbound_payload(self, payload: Dict[str, Any], expected_sender_folder: str) -> Tuple[bool, str]:
        required = [
            "protocol",
            "direction",
            "message_id",
            "provider",
            "bridge_id",
            "sender_id",
            "sender_folder",
            "timestamp_utc",
            "text",
            "attachments",
        ]
        for key in required:
            if key not in payload:
                return False, f"Missing required field: {key}"
        if str(payload.get("protocol", "")).strip() != "das.whatsapp.folder/1.0":
            return False, "Invalid protocol"
        if str(payload.get("direction", "")).strip().lower() != "inbound":
            return False, "Invalid direction"
        if str(payload.get("provider", "")).strip().lower() != "whatsapp":
            return False, "Invalid provider"
        sender_folder = str(payload.get("sender_folder", "") or "").strip()
        if not self._same_channel_identity(sender_folder, expected_sender_folder):
            return False, "sender_folder does not match containing folder"
        return True, ""

    def _ensure_users_whatsapp_id_column(self) -> None:
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]).lower(): str(r[1]) for r in cur.fetchall()}
            if "whatsapid" not in cols:
                cur.execute("ALTER TABLE Users ADD COLUMN WhatsapID TEXT")
                conn.commit()
        finally:
            conn.close()

    def _find_user_by_whatsapp_number(self, mobile: str) -> str:
        mobile = self._normalize_mobile(mobile)
        if not mobile:
            return ""
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]) for r in cur.fetchall()}
            if "id" not in cols:
                return ""
            candidates = [c for c in ("whatsapp_number", "whatsapnumber", "whatsappnumber", "mobile_number") if c in cols]
            if not candidates:
                return ""
            cur.execute(f"SELECT id, {', '.join(candidates)} FROM Users")
            for row in cur.fetchall():
                uid = str(row[0] or "").strip()
                for value in row[1:]:
                    if self._normalize_mobile(str(value or "")) == mobile:
                        return uid
            return ""
        finally:
            conn.close()

    def _bind_channel_id_to_user(self, channel_id: str, user_id: str) -> None:
        channel_id = self._normalize_channel_id(channel_id)
        user_id = str(user_id or "").strip()
        if not channel_id or not user_id:
            return
        self._ensure_users_whatsapp_id_column()
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE Users SET WhatsapID=? WHERE id=?", (channel_id, user_id))
            try:
                cur.execute(
                    """
                    INSERT INTO ChannelUsers (provider, channel_user_id, user_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(provider, channel_user_id)
                    DO UPDATE SET user_id=excluded.user_id, updated_at=CURRENT_TIMESTAMP
                    """,
                    ("whatsapp", channel_id, user_id),
                )
            except sqlite3.OperationalError:
                cur.execute(
                    "UPDATE ChannelUsers SET user_id=?, updated_at=CURRENT_TIMESTAMP WHERE provider=? AND channel_user_id=?",
                    (user_id, "whatsapp", channel_id),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "INSERT INTO ChannelUsers (provider, channel_user_id, user_id) VALUES (?, ?, ?)",
                        ("whatsapp", channel_id, user_id),
                    )
            conn.commit()
        finally:
            conn.close()

    def _bind_sender_identities_to_user(self, primary_channel_id: str, payload: Optional[Dict[str, Any]], user_id: str) -> None:
        user_id = str(user_id or "").strip()
        if not user_id:
            return

        raw_candidates: List[str] = [str(primary_channel_id or "").strip()]
        if isinstance(payload, dict):
            raw_candidates.extend([
                str(payload.get("sender_folder", "") or "").strip(),
                str(payload.get("sender_id", "") or "").strip(),
            ])

        normalized: List[str] = []
        for value in raw_candidates:
            cid = self._normalize_channel_id(value)
            if cid and cid not in normalized:
                normalized.append(cid)
        if not normalized:
            return

        lids = [cid for cid in normalized if "@lid" in cid]
        non_lids = [cid for cid in normalized if "@lid" not in cid]
        for cid in (non_lids + lids):
            try:
                self._bind_channel_id_to_user(cid, user_id)
            except Exception:
                try:
                    self.whatsapp_controller._bind_channel_to_user(cid, user_id)
                except Exception:
                    pass

    @staticmethod
    def _otp() -> str:
        return f"{random.randint(100000, 999999)}"

    @staticmethod
    def _is_register_text(text: str) -> bool:
        t = str(text or "").strip().lower()
        return t in {"register", "/register", "\\register"}

    @staticmethod
    def _is_menu_text(text: str) -> bool:
        return str(text or "").strip().lower() == "/menu"

    @staticmethod
    def _is_new_text(text: str) -> bool:
        return str(text or "").strip().lower() == "/new"

    @staticmethod
    def _is_greeting_text(text: str) -> bool:
        t = re.sub(r"\s+", " ", str(text or "").strip().lower())
        return t in {"hi", "hello", "hey", "hii"}

    @staticmethod
    def _should_reply_to_unregistered(text: str) -> bool:
        return WhatsAppFolderService._is_register_text(text) or WhatsAppFolderService._is_greeting_text(text)

    def _handle_registration_message(self, sender_logical_id: str, text: str, payload: Optional[Dict[str, Any]] = None) -> str:
        norm = str(text or "").strip()
        lower = norm.lower()
        ctx = self._register_contexts.get(sender_logical_id)

        if not ctx:
            if lower not in {"register", "/register", "\\register"}:
                return ""
            self._register_contexts[sender_logical_id] = {
                "state": "await_mobile",
                "created_at": time.time(),
            }
            return "Please share your WhatsApp number (with country code), e.g. 919876543210"

        state = str(ctx.get("state", ""))
        if state == "await_mobile":
            mobile = self._normalize_mobile(norm)
            if len(mobile) < 10:
                return "Invalid number. Please send a valid WhatsApp number with country code."
            user_id = self._find_user_by_whatsapp_number(mobile)
            if not user_id:
                return "This number is not registered in DAS. Please contact admin."
            otp = self._otp()
            ctx.update({
                "state": "await_otp",
                "user_id": user_id,
                "mobile": mobile,
                "otp": otp,
                "otp_at": time.time(),
            })
            self.send_text(mobile, f"Your DAS WhatsApp registration OTP is: {otp}")
            return "OTP sent to your registered WhatsApp number. Please send that OTP here from this same chat."

        if state == "await_otp":
            otp = re.sub(r"\D+", "", norm)
            expected = str(ctx.get("otp", ""))
            if otp != expected:
                return "Invalid OTP. Please send the OTP exactly as received."
            user_id = str(ctx.get("user_id", "")).strip()
            if not user_id:
                return "Registration failed. Please send Register again."
            self._bind_sender_identities_to_user(sender_logical_id, payload, user_id)
            self._register_contexts.pop(sender_logical_id, None)
            return "Registration completed successfully."

        self._register_contexts.pop(sender_logical_id, None)
        return "Please send Register to start again."

    def _cleanup_unregistered_message(self, moved: Path) -> None:
        try:
            shutil.rmtree(str(moved), ignore_errors=False)
        except Exception:
            pass
        try:
            parent = moved.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    def _resolve_mapped_user(self, logical_sender_id: str, payload: Dict[str, Any]) -> str:
        """Resolve mapped user and auto-bind channel IDs when a mobile fallback exists."""
        sender_id = str(logical_sender_id or "").strip()
        if not sender_id:
            return ""

        mapped_user = self.whatsapp_controller._find_user_id_by_channel_mapping(sender_id)
        if mapped_user:
            return str(mapped_user)

        candidates = [
            str(payload.get("sender_id", "") or "").strip(),
            str(payload.get("sender_folder", "") or "").strip(),
            sender_id,
        ]
        seen: set[str] = set()
        for candidate in candidates:
            mobile = self._normalize_mobile(candidate)
            if not mobile or mobile in seen:
                continue
            seen.add(mobile)

            mapped_user = self.whatsapp_controller._find_user_id_by_channel_mapping(mobile)
            if not mapped_user:
                mapped_user = self.whatsapp_controller._find_user_id_by_mobile_number(mobile)
            if not mapped_user:
                continue

            mapped_user = str(mapped_user).strip()
            if not mapped_user:
                continue

            # Bind the current channel identity (including @lid) once a mobile match is found.
            self._bind_sender_identities_to_user(sender_id, payload, mapped_user)
            whatsapp_log("inbound_autobind", f"channel_id={sender_id} user_id={mapped_user}")
            return mapped_user

        for candidate in candidates:
            candidate_id = self._normalize_channel_id(candidate)
            if "@lid" not in candidate_id:
                continue
            lid = self._normalize_mobile(candidate_id)
            if not lid:
                continue
            reverse_map = self._headless_auth_session_dir() / f"lid-mapping-{lid}_reverse.json"
            if not reverse_map.exists():
                continue
            try:
                raw_value = json.loads(reverse_map.read_text(encoding="utf-8"))
            except Exception:
                continue
            mapped_mobile = self._normalize_mobile(str(raw_value or ""))
            if not mapped_mobile or mapped_mobile in seen:
                continue
            seen.add(mapped_mobile)
            mapped_user = self.whatsapp_controller._find_user_id_by_channel_mapping(mapped_mobile)
            if not mapped_user:
                mapped_user = self.whatsapp_controller._find_user_id_by_mobile_number(mapped_mobile)
            if not mapped_user:
                continue
            mapped_user = str(mapped_user).strip()
            if not mapped_user:
                continue

            self._bind_sender_identities_to_user(sender_id, payload, mapped_user)
            whatsapp_log(
                "inbound_autobind_lid",
                f"channel_id={sender_id} mapped_mobile={mapped_mobile} user_id={mapped_user}",
            )
            return mapped_user

        return ""

    def _process_one_inbound(self, sender_folder_raw: str, source_dir: Path) -> None:
        p = self._paths()
        working_dir = p["working"] / "received" / sender_folder_raw / source_dir.name
        backup_dir = p["backup"] / "received" / sender_folder_raw / source_dir.name
        error_dir = p["error"] / "received" / sender_folder_raw / source_dir.name

        moved = self._move_tree(source_dir, working_dir)
        try:
            payload_path = moved / "message.json"
            if not payload_path.exists():
                raise ValueError("message.json not found")
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("message.json must be a JSON object")

            ok, reason = self._validate_inbound_payload(payload, sender_folder_raw)
            if not ok:
                raise ValueError(reason)

            dedupe_key = str(payload.get("provider_message_id", "") or payload.get("message_id", "")).strip()
            if self._is_duplicate_inbound(dedupe_key):
                whatsapp_log("duplicate_inbound", f"sender_folder={sender_folder_raw} message_id={dedupe_key}")
                self._move_tree(moved, backup_dir)
                return

            text = str(payload.get("text", "") or "").strip()
            files = self._collect_attachment_paths(moved, payload.get("attachments", []))

            reply_target = str(payload.get("sender_folder", "") or sender_folder_raw).strip() or sender_folder_raw
            logical_sender_id = self._canonical_sender_id(payload, sender_folder_raw)

            if self._is_menu_text(text):
                self.send_text(reply_target, MENU_TEXT)
                self._mark_inbound_handled(dedupe_key)
                self._move_tree(moved, backup_dir)
                return

            if self._is_new_text(text):
                mapped_for_new = self._resolve_mapped_user(logical_sender_id, payload)
                if not mapped_for_new:
                    self._mark_inbound_handled(dedupe_key)
                    self._move_tree(moved, backup_dir)
                    return
                else:
                    new_response = self.whatsapp_controller.handle_inbound_safe(logical_sender_id, "/new", files=[])
                    self.send_text(reply_target, new_response or "Started a new chat session.")
                self._mark_inbound_handled(dedupe_key)
                self._move_tree(moved, backup_dir)
                return

            reg_active = logical_sender_id in self._register_contexts
            reg_requested = self._is_register_text(text)
            if reg_active or reg_requested:
                reg_response = self._handle_registration_message(logical_sender_id, text, payload=payload)
                if reg_response:
                    self.send_text(reply_target, reg_response)
                else:
                    self._cleanup_unregistered_message(moved)
                try:
                    self._move_tree(moved, backup_dir)
                except Exception:
                    pass
                self._mark_inbound_handled(dedupe_key)
                return

            mapped_user = self._resolve_mapped_user(logical_sender_id, payload)
            if not mapped_user:
                if self._is_greeting_text(text):
                    self.send_text(reply_target, UNREGISTERED_HI_TEXT)
                elif not self._should_reply_to_unregistered(text):
                    self._mark_inbound_handled(dedupe_key)
                    self._move_tree(moved, backup_dir)
                    return
                self._mark_inbound_handled(dedupe_key)
                self._move_tree(moved, backup_dir)
                return

            ack = "File received. Working on it..." if files else "Message received. Working on it..."
            self.send_text(reply_target, ack)

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
                    self.send_text(reply_target, full)
                except Exception:
                    return

            finalize_state = {"done": False}

            def _finalize_success() -> None:
                if finalize_state["done"]:
                    return
                finalize_state["done"] = True
                self._mark_inbound_handled(dedupe_key)
                self._move_tree(moved, backup_dir)

            def _completion(text_out: str) -> None:
                if text_out:
                    self.send_text(reply_target, text_out)
                try:
                    _finalize_success()
                except Exception as finalize_exc:
                    log_exception(
                        "WHATSAPP_INBOUND_FINALIZE_ERROR",
                        finalize_exc,
                        {"sender_folder": sender_folder_raw, "message_dir": str(moved)},
                    )

            response = self.whatsapp_controller.handle_inbound_safe(
                logical_sender_id,
                text,
                files=files,
                ui_callback=_channel_ui_feedback,
                completion_callback=_completion,
            )
            if response:
                self.send_text(reply_target, response)
            is_async = getattr(self.whatsapp_controller, "conversation_manager", None) is not None
            if not is_async:
                _finalize_success()
        except Exception as exc:
            moved_to_error = self._move_tree(moved, error_dir)
            self._write_error(moved_to_error, "INTERNAL_ERROR", str(exc))
            raise

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._ensure_dirs()
                for sender_folder_raw, msg_dir in self._find_inbound_messages():
                    if self._stop_event.is_set():
                        break
                    try:
                        self._process_one_inbound(sender_folder_raw, msg_dir)
                    except Exception as exc:
                        log_exception(
                            "WHATSAPP_INBOUND_PROCESS_ERROR",
                            exc,
                            {"sender_folder": sender_folder_raw, "message_dir": str(msg_dir)},
                        )
                        whatsapp_log("inbound_error", f"sender_folder={sender_folder_raw} folder={msg_dir.name} error={exc}")
                self._last_error = ""
            except Exception as exc:
                self._last_error = str(exc)
                log_exception("WHATSAPP_POLL_ERROR", exc, {})
                whatsapp_log("poll_error", self._last_error)
            time.sleep(self._poll_seconds())

    def send_text(self, recipient_mobile: str, text: str) -> Dict[str, Any]:
        recipient_id = self._normalize_channel_id(recipient_mobile)
        content = str(text or "").strip()
        if not recipient_id:
            return {"ok": False, "error": "Invalid recipient"}
        if not content:
            return {"ok": False, "error": "Message text is empty"}

        p = self._paths()
        self._ensure_dirs()
        msg_id = self._message_folder_id()

        staging_dir = p["staging"] / "send" / recipient_id / msg_id
        final_dir = p["send"] / recipient_id / msg_id
        staging_dir.mkdir(parents=True, exist_ok=False)

        (staging_dir / "message.txt").write_text(content, encoding="utf-8")

        try:
            self._move_tree(staging_dir, final_dir)
            whatsapp_log("outbound", f"recipient={recipient_id} message_id={msg_id}")
            return {"ok": True, "message_id": msg_id, "path": str(final_dir)}
        except Exception as exc:
            err_dir = p["error"] / "send" / recipient_id / msg_id
            try:
                moved = self._move_tree(staging_dir, err_dir)
                self._write_error(moved, "INTERNAL_ERROR", str(exc))
            except Exception:
                pass
            whatsapp_log("outbound_error", f"recipient={recipient_id} error={exc}")
            return {"ok": False, "error": str(exc)}

    def send_file(self, recipient_mobile: str, file_path: str, caption: str = "") -> Dict[str, Any]:
        recipient_id = self._normalize_channel_id(recipient_mobile)
        source = Path(str(file_path or "")).expanduser().resolve()
        text = str(caption or "")
        if not recipient_id:
            return {"ok": False, "error": "Invalid recipient"}
        if not source.exists() or not source.is_file():
            return {"ok": False, "error": f"File not found: {source}"}

        p = self._paths()
        self._ensure_dirs()
        msg_id = self._message_folder_id()

        staging_dir = p["staging"] / "send" / recipient_id / msg_id
        final_dir = p["send"] / recipient_id / msg_id
        staging_dir.mkdir(parents=True, exist_ok=False)

        safe_name = self._safe_attachment_name(source.name, fallback=f"file_{uuid.uuid4().hex}.bin")
        staged_file = staging_dir / safe_name
        shutil.copy2(str(source), str(staged_file))

        if text.strip():
            (staging_dir / "message.txt").write_text(text.strip(), encoding="utf-8")

        try:
            self._move_tree(staging_dir, final_dir)
            whatsapp_log("outbound_file", f"recipient={recipient_id} message_id={msg_id} file={safe_name}")
            return {
                "ok": True,
                "message_id": msg_id,
                "path": str(final_dir),
                "file_name": safe_name,
            }
        except Exception as exc:
            err_dir = p["error"] / "send" / recipient_id / msg_id
            try:
                moved = self._move_tree(staging_dir, err_dir)
                self._write_error(moved, "INTERNAL_ERROR", str(exc))
            except Exception:
                pass
            whatsapp_log("outbound_file_error", f"recipient={recipient_id} file={safe_name} error={exc}")
            return {"ok": False, "error": str(exc)}

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": bool(self._running and self._thread is not None and self._thread.is_alive()),
            "last_error": self._last_error,
            "root": str(self._root_dir()),
            "poll_seconds": self._poll_seconds(),
        }















