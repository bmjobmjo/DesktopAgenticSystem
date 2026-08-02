from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import db
from security import hash_password, token_hash


class DummyCda:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_setting(self, key: str, default=None):
        if key == "sqlite_db_path":
            return str(self.db_path)
        return default


def _init_auth_db(tmp_path: Path) -> DummyCda:
    cda = DummyCda(tmp_path / "auth.db")
    conn = sqlite3.connect(str(cda.db_path))
    try:
        conn.execute(
            """
            CREATE TABLE Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                email TEXT,
                password_hash TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_admin INTEGER NOT NULL DEFAULT 0,
                force_password_change INTEGER NOT NULL DEFAULT 0,
                password_updated_at DATETIME,
                created_at DATETIME
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    db.ensure_api_schema(cda)
    return cda


def _create_user(cda: DummyCda) -> int:
    conn = db.connect(cda)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO Users (
                username, email, password_hash, is_active, is_admin,
                force_password_change, password_updated_at, created_at
            )
            VALUES ('admin', 'admin@local', ?, 1, 1, 0, '2026-01-01T00:00:00+00:00', CURRENT_TIMESTAMP)
            """,
            (hash_password("old-password"),),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def test_password_update_time_invalidates_older_sessions(tmp_path):
    cda = _init_auth_db(tmp_path)
    user_id = _create_user(cda)
    token = "old-session-token"

    conn = db.connect(cda)
    try:
        conn.execute(
            """
            INSERT INTO ApiSessions(user_id, token_hash, created_at, expires_at, last_seen_at)
            VALUES (?, ?, '2026-01-01T00:00:00+00:00', '2099-01-03T00:00:00+00:00', CURRENT_TIMESTAMP)
            """,
            (user_id, token_hash(token)),
        )
        conn.execute("UPDATE Users SET password_updated_at='2026-01-02T00:00:00+00:00' WHERE id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()

    assert db.resolve_session(cda, token) is None


def test_revoke_user_sessions_can_keep_current_session(tmp_path):
    cda = _init_auth_db(tmp_path)
    user_id = _create_user(cda)
    keep_token = "keep-session-token"
    revoke_token = "revoke-session-token"

    db.create_session(cda, user_id, keep_token)
    db.create_session(cda, user_id, revoke_token)

    assert db.resolve_session(cda, keep_token) is not None
    assert db.resolve_session(cda, revoke_token) is not None

    db.revoke_user_sessions(cda, user_id, except_raw_token=keep_token)

    assert db.resolve_session(cda, keep_token) is not None
    assert db.resolve_session(cda, revoke_token) is None


def test_existing_admin_without_role_is_backfilled_to_admin_role(tmp_path):
    cda = _init_auth_db(tmp_path)
    conn = db.connect(cda)
    try:
        conn.execute("ALTER TABLE Users ADD COLUMN role_id INTEGER")
        conn.execute(
            "CREATE TABLE Roles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)"
        )
        conn.execute("INSERT INTO Roles(name) VALUES ('Admin')")
        conn.commit()
    finally:
        conn.close()
    user_id = _create_user(cda)

    result = db.ensure_default_admin(
        cda,
        username="admin",
        email="admin@local",
        password_hash_value=hash_password("unused"),
    )

    conn = db.connect(cda)
    try:
        role_id = conn.execute("SELECT role_id FROM Users WHERE id=?", (user_id,)).fetchone()["role_id"]
        admin_role_id = conn.execute("SELECT id FROM Roles WHERE name='Admin'").fetchone()["id"]
    finally:
        conn.close()

    assert role_id == admin_role_id
    assert result["role_id"] == admin_role_id
