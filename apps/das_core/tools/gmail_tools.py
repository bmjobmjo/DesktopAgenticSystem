"""Tools for sending outbound email through a configured Gmail account."""

from __future__ import annotations

__tool_exports__ = ["send_gmail_email"]

import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from tools.filesystem import ensure_accessible
from tools.output_utils import get_storage_root


def _db_path(cda: CommonDataArea) -> Path:
    # 1. Try sqlite_db_path from settings
    path_str = cda.get_setting("sqlite_db_path")
    if path_str:
        p = Path(str(path_str)).resolve()
        if p.exists() and p.is_file():
            # Check if this database has a Users table
            try:
                import sqlite3
                conn = sqlite3.connect(str(p))
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
                has_users = bool(cur.fetchone())
                conn.close()
                if has_users:
                    return p
            except Exception:
                pass

    # 2. Check sibling path of __file__ up 3 levels to "data/office_automation.db"
    try:
        p_fallback = Path(__file__).resolve().parent.parent.parent / "data" / "office_automation.db"
        if p_fallback.exists() and p_fallback.is_file():
            return p_fallback
    except Exception:
        pass

    # 3. Check relative path from CWD looking upward
    try:
        for rel in ("data/office_automation.db", "../data/office_automation.db", "../../data/office_automation.db"):
            p_cwd = Path(rel).resolve()
            if p_cwd.exists() and p_cwd.is_file():
                return p_cwd
    except Exception:
        pass

    # 4. Fallback to default setting or backend.db
    return Path(str(cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()


def _normalize_recipients(value: List[str] | str) -> List[str]:
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.replace(";", ",").split(",")]
    else:
        raw_items = [str(item or "").strip() for item in (value or [])]
    recipients = [item for item in raw_items if item]
    if not recipients:
        raise ValueError("At least one recipient email address is required.")
    return recipients


def _resolve_recipients(to: List[str] | str, cda: CommonDataArea) -> List[str]:
    raw_list = _normalize_recipients(to)
    resolved: List[str] = []
    
    current_email = str(cda.get_setting("current_user_email") or "").strip()
    if not current_email:
        uid = str(cda.get_setting("current_user_id") or "").strip()
        if not uid:
            prompt_ctx = cda.get_memory("prompt_context_dict") or {}
            if isinstance(prompt_ctx, dict):
                uid = str(prompt_ctx.get("UID") or "").strip()
        if uid:
            import sqlite3
            db_path = _db_path(cda)
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                try:
                    cur = conn.cursor()
                    cur.execute("PRAGMA table_info(Users)")
                    cols = {str(r[1]) for r in cur.fetchall()}
                    if "email" in cols:
                        cur.execute("SELECT email FROM Users WHERE id=? LIMIT 1", (uid,))
                        row = cur.fetchone()
                        if row and row[0]:
                            current_email = str(row[0]).strip()

                    if not current_email:
                        cur.execute("PRAGMA table_info(Employees)")
                        e_cols = {str(r[1]) for r in cur.fetchall()}
                        if "linked_user_id" in e_cols:
                            candidate_cols = [c for c in ("personal_email", "official_email") if c in e_cols]
                            if candidate_cols:
                                cur.execute(
                                    f"SELECT {', '.join(candidate_cols)} FROM Employees WHERE linked_user_id=? LIMIT 1",
                                    (uid,),
                                )
                                row = cur.fetchone()
                                if row:
                                    for val in row:
                                        if val:
                                            current_email = str(val).strip()
                                            break
                except Exception:
                    pass
                finally:
                    conn.close()

    for email in raw_list:
        email_norm = email.lower()
        is_placeholder = "example.com" in email_norm or "recipient" in email_norm
        if is_placeholder and current_email:
            resolved.append(current_email)
        else:
            resolved.append(email)
            
    return resolved


def _resolve_attachment(path_str: str, storage_root: Path) -> Path:
    candidate = Path(str(path_str or "").strip()).expanduser().resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Attachment does not exist: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"Attachment path is not a file: {candidate}")

    within_storage_root = False
    try:
        within_storage_root = candidate.is_relative_to(storage_root)
    except AttributeError:
        within_storage_root = str(candidate).lower().startswith(str(storage_root).lower())

    if not within_storage_root:
        ok, error = ensure_accessible(str(candidate))
        if not ok:
            raise ValueError(f"{error}: {candidate}")
    return candidate


def _add_attachments(message: EmailMessage, attachment_paths: List[str] | None, cda: CommonDataArea) -> List[Dict[str, Any]]:
    storage_root = get_storage_root(cda)
    attached: List[Dict[str, Any]] = []
    for raw_path in attachment_paths or []:
        path = _resolve_attachment(raw_path, storage_root)
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        payload = path.read_bytes()
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=path.name)
        attached.append(
            {
                "file_path": str(path),
                "filename": path.name,
                "size_bytes": len(payload),
                "content_type": f"{maintype}/{subtype}",
            }
        )
    return attached


def send_gmail_email(
    to: List[str] | str,
    subject: str,
    body: str,
    cc: List[str] | str | None = None,
    bcc: List[str] | str | None = None,
    html_body: str = "",
    attachment_paths: List[str] | None = None,
    status_callback=None,
) -> Dict[str, Any]:
    """Send an email using the Gmail sender address and app password stored in settings."""

    cda = CommonDataArea()
    gmail_enabled = bool(cda.get_setting("gmail_enabled", False))
    sender_email = str(cda.get_setting("gmail_sender_email", "") or "").strip()
    app_password = str(cda.get_setting("gmail_app_password", "") or "").strip()
    sender_name = str(cda.get_setting("gmail_sender_name", "") or "").strip()

    if not gmail_enabled:
        return {"success": False, "error": "gmail_enabled is disabled in settings."}
    if not sender_email:
        return {"success": False, "error": "gmail_sender_email is not configured in settings."}
    if not app_password:
        return {"success": False, "error": "gmail_app_password is not configured in settings."}

    try:
        to_list = _resolve_recipients(to, cda)
        cc_list = _normalize_recipients(cc) if cc else []
        bcc_list = _normalize_recipients(bcc) if bcc else []
        if not str(subject or "").strip():
            raise ValueError("subject is required.")
        if not str(body or "").strip() and not str(html_body or "").strip():
            raise ValueError("body or html_body is required.")

        message = EmailMessage()
        message["Subject"] = str(subject).strip()
        message["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        if str(body or "").strip():
            message.set_content(str(body))
        else:
            message.set_content("This email contains HTML content.")
        if str(html_body or "").strip():
            message.add_alternative(str(html_body), subtype="html")

        attachments = _add_attachments(message, attachment_paths, cda)
        all_recipients = to_list + cc_list + bcc_list

        if status_callback:
            status_callback(f"Sending email to {len(all_recipients)} recipient(s)...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as client:
            client.login(sender_email, app_password)
            client.send_message(message, from_addr=sender_email, to_addrs=all_recipients)
        if status_callback:
            status_callback("")

        return {
            "success": True,
            "message": "Email sent successfully.",
            "sender_email": sender_email,
            "to": to_list,
            "cc": cc_list,
            "bcc_count": len(bcc_list),
            "subject": str(subject).strip(),
            "attachment_count": len(attachments),
            "attachments": attachments,
        }
    except Exception as exc:
        if status_callback:
            status_callback("")
        return {"success": False, "error": str(exc)}
