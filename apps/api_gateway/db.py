"""SQLite persistence helpers for API gateway."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from security import token_hash


def _resolve_db_path(cda: Any) -> Path:
    configured = str(cda.get_setting("sqlite_db_path", "backend.db") or "backend.db").strip()
    return Path(configured).resolve()


def _parse_db_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def connect(cda: Any) -> sqlite3.Connection:
    db_path = _resolve_db_path(cda)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _users_columns(cur: sqlite3.Cursor) -> set[str]:
    cur.execute("PRAGMA table_info(Users)")
    return {str(row[1]) for row in cur.fetchall()}


def _ensure_user_column(cur: sqlite3.Cursor, cols: set[str], column: str, ddl: str) -> None:
    if column in cols:
        return
    cur.execute(f"ALTER TABLE Users ADD COLUMN {ddl}")
    cols.add(column)


def _normalize_base_username(value: str, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_]+", "_", raw)
    raw = raw.strip("_")
    if not raw:
        raw = fallback
    return raw[:40]


def _unique_username(cur: sqlite3.Cursor, desired: str, current_id: int) -> str:
    candidate = desired
    suffix = 1
    while True:
        cur.execute(
            "SELECT id FROM Users WHERE lower(COALESCE(username,''))=lower(?) AND id<>? LIMIT 1",
            (candidate, int(current_id)),
        )
        if not cur.fetchone():
            return candidate
        suffix += 1
        candidate = f"{desired}_{suffix}"


def ensure_api_schema(cda: Any) -> None:
    conn = connect(cda)
    try:
        cur = conn.cursor()

        cols = _users_columns(cur)
        _ensure_user_column(cur, cols, "username", "username TEXT")
        _ensure_user_column(cur, cols, "password_hash", "password_hash TEXT")
        _ensure_user_column(cur, cols, "is_active", "is_active INTEGER NOT NULL DEFAULT 1")
        _ensure_user_column(cur, cols, "is_admin", "is_admin INTEGER NOT NULL DEFAULT 0")
        _ensure_user_column(cur, cols, "force_password_change", "force_password_change INTEGER NOT NULL DEFAULT 0")
        _ensure_user_column(cur, cols, "password_updated_at", "password_updated_at DATETIME")
        _ensure_user_column(cur, cols, "last_login", "last_login DATETIME")
        _ensure_user_column(cur, cols, "created_at", "created_at DATETIME")
        _ensure_user_column(cur, cols, "whatsapp_number", "whatsapp_number TEXT")

        if "registration_timestamp" in cols:
            cur.execute(
                """
                UPDATE Users
                SET created_at = registration_timestamp
                WHERE (created_at IS NULL OR TRIM(COALESCE(created_at, ''))='')
                  AND registration_timestamp IS NOT NULL
                """
            )

        name_source_expr = "COALESCE(email, full_name, '')" if "full_name" in cols else "COALESCE(email, '')"
        cur.execute(
            f"SELECT id, {name_source_expr} as name_source FROM Users WHERE username IS NULL OR TRIM(username)=''"
        )
        for row in cur.fetchall():
            uid = int(row["id"])
            source = str(row["name_source"] or "")
            if "@" in source:
                source = source.split("@", 1)[0]
            base = _normalize_base_username(source, fallback=f"user{uid}")
            username = _unique_username(cur, base, uid)
            cur.execute("UPDATE Users SET username=? WHERE id=?", (username, uid))

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ApiSessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                last_seen_at DATETIME,
                revoked_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE
"""SQLite persistence helpers for API gateway."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from security import token_hash


def _resolve_db_path(cda: Any) -> Path:
    configured = str(cda.get_setting("sqlite_db_path", "backend.db") or "backend.db").strip()
    return Path(configured).resolve()


def _parse_db_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def connect(cda: Any) -> sqlite3.Connection:
    db_path = _resolve_db_path(cda)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _users_columns(cur: sqlite3.Cursor) -> set[str]:
    cur.execute("PRAGMA table_info(Users)")
    return {str(row[1]) for row in cur.fetchall()}


def _ensure_user_column(cur: sqlite3.Cursor, cols: set[str], column: str, ddl: str) -> None:
    if column in cols:
        return
    cur.execute(f"ALTER TABLE Users ADD COLUMN {ddl}")
    cols.add(column)


def _normalize_base_username(value: str, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_]+", "_", raw)
    raw = raw.strip("_")
    if not raw:
        raw = fallback
    return raw[:40]


def _unique_username(cur: sqlite3.Cursor, desired: str, current_id: int) -> str:
    candidate = desired
    suffix = 1
    while True:
        cur.execute(
            "SELECT id FROM Users WHERE lower(COALESCE(username,''))=lower(?) AND id<>? LIMIT 1",
            (candidate, int(current_id)),
        )
        if not cur.fetchone():
            return candidate
        suffix += 1
        candidate = f"{desired}_{suffix}"


def ensure_api_schema(cda: Any) -> None:
    conn = connect(cda)
    try:
        cur = conn.cursor()

        cols = _users_columns(cur)
        _ensure_user_column(cur, cols, "username", "username TEXT")
        _ensure_user_column(cur, cols, "password_hash", "password_hash TEXT")
        _ensure_user_column(cur, cols, "is_active", "is_active INTEGER NOT NULL DEFAULT 1")
        _ensure_user_column(cur, cols, "is_admin", "is_admin INTEGER NOT NULL DEFAULT 0")
        _ensure_user_column(cur, cols, "force_password_change", "force_password_change INTEGER NOT NULL DEFAULT 0")
        _ensure_user_column(cur, cols, "password_updated_at", "password_updated_at DATETIME")
        _ensure_user_column(cur, cols, "last_login", "last_login DATETIME")
        _ensure_user_column(cur, cols, "created_at", "created_at DATETIME")
        _ensure_user_column(cur, cols, "whatsapp_number", "whatsapp_number TEXT")

        if "registration_timestamp" in cols:
            cur.execute(
                """
                UPDATE Users
                SET created_at = registration_timestamp
                WHERE (created_at IS NULL OR TRIM(COALESCE(created_at, ''))='')
                  AND registration_timestamp IS NOT NULL
                """
            )

        name_source_expr = "COALESCE(email, full_name, '')" if "full_name" in cols else "COALESCE(email, '')"
        cur.execute(
            f"SELECT id, {name_source_expr} as name_source FROM Users WHERE username IS NULL OR TRIM(username)=''"
        )
        for row in cur.fetchall():
            uid = int(row["id"])
            source = str(row["name_source"] or "")
            if "@" in source:
                source = source.split("@", 1)[0]
            base = _normalize_base_username(source, fallback=f"user{uid}")
            username = _unique_username(cur, base, uid)
            cur.execute("UPDATE Users SET username=? WHERE id=?", (username, uid))

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ApiSessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                last_seen_at DATETIME,
                revoked_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_sessions_user ON ApiSessions(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_api_sessions_exp ON ApiSessions(expires_at)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS AuthAuditLog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                actor_user_id INTEGER,
                target_user_id INTEGER,
                target_email TEXT,
                detail TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()
    finally:
        conn.close()


def ensure_default_admin(cda: Any, *, username: str, email: str, password_hash_value: str) -> Dict[str, Any]:
    conn = connect(cda)
    try:
        cur = conn.cursor()
        user_cols = _users_columns(cur)
        admin_role_id: Optional[int] = None
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='Roles'")
        if cur.fetchone() and "role_id" in user_cols:
            cur.execute("SELECT id FROM Roles WHERE lower(name)='admin' LIMIT 1")
            role_row = cur.fetchone()
            if role_row:
                admin_role_id = int(role_row["id"])

        cur.execute("SELECT id, username, email, is_admin FROM Users WHERE is_admin=1 ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        if row:
            data = dict(row)
            if admin_role_id is not None:
                cur.execute(
                    "UPDATE Users SET role_id=? WHERE id=?",
                    (admin_role_id, int(row["id"])),
                )
                conn.commit()
                data["role_id"] = admin_role_id
            return data

        admin_username = _normalize_base_username(username, fallback="admin")
        admin_email = str(email or "").strip() or f"{admin_username}@local"

        if admin_role_id is not None:
            cur.execute(
                """
                INSERT INTO Users (
                    username, email, password_hash,
                    is_active, is_admin, force_password_change, role_id,
                    password_updated_at, created_at
                )
                VALUES (?, ?, ?, 1, 1, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (admin_username, admin_email, password_hash_value, admin_role_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO Users (
                    username, email, password_hash,
                    is_active, is_admin, force_password_change,
                    password_updated_at, created_at
                )
                VALUES (?, ?, ?, 1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (admin_username, admin_email, password_hash_value),
            )
        user_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO AuthAuditLog(action, actor_user_id, target_user_id, target_email, detail) VALUES (?, ?, ?, ?, ?)",
            ("seed_admin", user_id, user_id, admin_email, "Initial admin account seeded"),
        )
        conn.commit()
        return {
            "id": user_id,
            "username": admin_username,
            "email": admin_email,
            "is_admin": 1,
            "role_id": admin_role_id,
        }
    finally:
        conn.close()


def get_user_by_login(cda: Any, login: str) -> Optional[Dict[str, Any]]:
    value = str(login or "").strip()
    if not value:
        return None
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, username, email, password_hash, is_active, is_admin, force_password_change
            FROM Users
            WHERE lower(COALESCE(username,''))=lower(?) OR lower(COALESCE(email,''))=lower(?)
            LIMIT 1
            """,
            (value, value),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(cda: Any, user_id: int) -> Optional[Dict[str, Any]]:
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, username, email, mobile_number, telegram_chat_id, WhatsapID,
                   is_active, is_admin, force_password_change, role_id, created_at, last_login
            FROM Users WHERE id=? LIMIT 1
            """,
            (int(user_id),),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_session(cda: Any, user_id: int, raw_token: str, *, ttl_hours: int = 12) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=max(1, int(ttl_hours)))
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ApiSessions(user_id, token_hash, expires_at, last_seen_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (int(user_id), token_hash(raw_token), expires_at.isoformat()),
        )
        cur.execute("UPDATE Users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (int(user_id),))
        conn.commit()
    finally:
        conn.close()


def resolve_session(cda: Any, raw_token: str) -> Optional[Dict[str, Any]]:
    hashed = token_hash(raw_token)
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id as session_id, s.user_id, s.created_at, s.expires_at, s.revoked_at,
                   u.username, u.email, u.is_active, u.is_admin, u.force_password_change,
                   u.password_updated_at
            FROM ApiSessions s
            JOIN Users u ON u.id = s.user_id
            WHERE s.token_hash=?
            LIMIT 1
            """,
            (hashed,),
        )
        row = cur.fetchone()
        if not row:
            return None

        data = dict(row)
        if data.get("revoked_at"):
            return None

        expires_dt = _parse_db_datetime(data.get("expires_at"))
        if expires_dt is None:
            return None
        if expires_dt <= datetime.now(timezone.utc):
            return None

        created_dt = _parse_db_datetime(data.get("created_at"))
        password_updated_dt = _parse_db_datetime(data.get("password_updated_at"))
        if created_dt is not None and password_updated_dt is not None and created_dt < password_updated_dt:
            return None

        try:
            cur.execute("UPDATE ApiSessions SET last_seen_at=CURRENT_TIMESTAMP WHERE id=?", (data["session_id"],))
            conn.commit()
        except sqlite3.OperationalError as exc:
            # Session reads should not fail the whole API request if SQLite is briefly busy.
            if "database is locked" not in str(exc).lower():
                raise
        return data
    finally:
        conn.close()


def revoke_session(cda: Any, raw_token: str) -> None:
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE ApiSessions SET revoked_at=CURRENT_TIMESTAMP WHERE token_hash=? AND revoked_at IS NULL",
            (token_hash(raw_token),),
        )
        conn.commit()
    finally:
        conn.close()


def revoke_user_sessions(cda: Any, user_id: int, *, except_raw_token: str = "") -> None:
    except_hash = token_hash(except_raw_token) if except_raw_token else ""
    conn = connect(cda)
    try:
        cur = conn.cursor()
        if except_hash:
            cur.execute(
                """
                UPDATE ApiSessions
                SET revoked_at=CURRENT_TIMESTAMP
                WHERE user_id=? AND revoked_at IS NULL AND token_hash<>?
                """,
                (int(user_id), except_hash),
            )
        else:
            cur.execute(
                "UPDATE ApiSessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=? AND revoked_at IS NULL",
                (int(user_id),),
            )
        conn.commit()
    finally:
        conn.close()


def refresh_session_after_password_change(cda: Any, raw_token: str) -> None:
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE ApiSessions
            SET created_at=CURRENT_TIMESTAMP, last_seen_at=CURRENT_TIMESTAMP
            WHERE token_hash=? AND revoked_at IS NULL
            """,
            (token_hash(raw_token),),
        )
        conn.commit()
    finally:
        conn.close()


def set_user_password(
    cda: Any,
    user_id: int,
    password_hash_value: str,
    *,
    force_password_change: bool,
    actor_user_id: Optional[int],
    detail: str,
) -> None:
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE Users
            SET password_hash=?, force_password_change=?, password_updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (password_hash_value, int(1 if force_password_change else 0), int(user_id)),
        )
        cur.execute(
            "INSERT INTO AuthAuditLog(action, actor_user_id, target_user_id, detail) VALUES (?, ?, ?, ?)",
            ("set_password", actor_user_id, int(user_id), detail),
        )
        conn.commit()
    finally:
        conn.close()


def create_user(
    cda: Any,
    *,
    username: str,
    email: str,
    password_hash_value: str,
    is_admin: bool,
    mobile_number: str,
    whatsapp_number: str,
    telegram_chat_id: str,
    actor_user_id: int,
) -> Dict[str, Any]:
    conn = connect(cda)
    try:
        cur = conn.cursor()

        uname = _normalize_base_username(username, fallback="user")
        temp_uname = uname
        idx = 1
        while True:
            cur.execute("SELECT id FROM Users WHERE lower(COALESCE(username,''))=lower(?) LIMIT 1", (temp_uname,))
            if not cur.fetchone():
                uname = temp_uname
                break
            idx += 1
            temp_uname = f"{uname}_{idx}"

        normalized_email = str(email or "").strip().lower()
        if not normalized_email:
            normalized_email = f"{uname}@local"

        cur.execute("SELECT id FROM Users WHERE lower(COALESCE(email,''))=lower(?) LIMIT 1", (normalized_email,))
        if cur.fetchone():
            raise ValueError("Email already exists")

        cur.execute(
            """
            INSERT INTO Users (
                username, email, password_hash,
                mobile_number, whatsapp_number, telegram_chat_id,
                is_active, is_admin, force_password_change,
                password_updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                uname,
                normalized_email,
                password_hash_value,
                str(mobile_number or "").strip(),
                str(whatsapp_number or "").strip(),
                str(telegram_chat_id or "").strip(),
                int(1 if is_admin else 0),
            ),
        )
        new_id = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO AuthAuditLog(action, actor_user_id, target_user_id, target_email, detail) VALUES (?, ?, ?, ?, ?)",
            ("create_user", int(actor_user_id), new_id, normalized_email, "Admin created user"),
        )
        conn.commit()
        return {
            "id": new_id,
            "username": uname,
            "email": normalized_email,
            "is_admin": int(1 if is_admin else 0),
            "force_password_change": 1,
        }
    finally:
        conn.close()


def audit(
    cda: Any,
    *,
    action: str,
    actor_user_id: Optional[int],
    target_user_id: Optional[int],
    target_email: str = "",
    detail: str = "",
) -> None:
    conn = connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO AuthAuditLog(action, actor_user_id, target_user_id, target_email, detail) VALUES (?, ?, ?, ?, ?)",
            (action, actor_user_id, target_user_id, target_email, detail),
        )
        conn.commit()
    finally:
        conn.close()
