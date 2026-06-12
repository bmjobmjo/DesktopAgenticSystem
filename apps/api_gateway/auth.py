"""Authentication and admin-user endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

import db
from security import generate_temp_password, generate_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _get_cda(request: Request):
    cda = getattr(request.app.state, "cda", None)
    if cda is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return cda


def _extract_bearer(request: Request) -> str:
    header = str(request.headers.get("authorization", "") or "").strip()
    if not header.lower().startswith("bearer "):
        return ""
    return header[7:].strip()


def _require_session(request: Request) -> Dict[str, Any]:
    cda = _get_cda(request)
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    session = db.resolve_session(cda, token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    if int(session.get("is_active") or 0) != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    if int(session.get("force_password_change") or 0) == 1:
        allowed_paths = {"/auth/me", "/auth/logout", "/auth/change-password"}
        if request.url.path not in allowed_paths:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required")
    request.state.auth_token = token
    request.state.session = session
    return session


def _require_admin(session: Dict[str, Any] = Depends(_require_session)) -> Dict[str, Any]:
    if int(session.get("is_admin") or 0) != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return session


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    email: Optional[str] = None
    is_admin: bool = False
    mobile_number: str = ""
    whatsapp_number: str = ""
    telegram_chat_id: str = ""


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    cda = _get_cda(request)
    user = db.get_user_by_login(cda, payload.login)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if int(user.get("is_active") or 0) != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    if not verify_password(payload.password, str(user.get("password_hash") or "")):
        db.audit(cda, action="login_failed", actor_user_id=None, target_user_id=user.get("id"), detail="Invalid password")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = generate_token()
    db.create_session(cda, int(user["id"]), token)
    db.audit(cda, action="login_success", actor_user_id=int(user["id"]), target_user_id=int(user["id"]), detail="Login success")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user.get("username"),
            "email": user.get("email"),
            "is_admin": int(user.get("is_admin") or 0) == 1,
            "force_password_change": int(user.get("force_password_change") or 0) == 1,
        },
    }


@router.post("/logout")
def logout(request: Request, session: Dict[str, Any] = Depends(_require_session)):
    token = getattr(request.state, "auth_token", "")
    if token:
        db.revoke_session(_get_cda(request), token)
    db.audit(_get_cda(request), action="logout", actor_user_id=int(session["user_id"]), target_user_id=int(session["user_id"]), detail="Logout")
    return {"ok": True}


@router.get("/me")
def me(request: Request, session: Dict[str, Any] = Depends(_require_session)):
    cda = _get_cda(request)
    user = db.get_user_by_id(cda, int(session["user_id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user["id"],
        "username": user.get("username"),
        "email": user.get("email"),
        "mobile_number": user.get("mobile_number") or "",
        "whatsapp_id": user.get("WhatsapID") or "",
        "telegram_chat_id": user.get("telegram_chat_id") or "",
        "is_admin": int(user.get("is_admin") or 0) == 1,
        "is_active": int(user.get("is_active") or 0) == 1,
        "force_password_change": int(user.get("force_password_change") or 0) == 1,
    }


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, request: Request, session: Dict[str, Any] = Depends(_require_session)):
    cda = _get_cda(request)
    user = db.get_user_by_id(cda, int(session["user_id"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current_hash = db.get_user_by_login(cda, str(user.get("username") or ""))
    if not current_hash or not verify_password(payload.current_password, str(current_hash.get("password_hash") or "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is invalid")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")

    db.set_user_password(
        cda,
        int(session["user_id"]),
        hash_password(payload.new_password),
        force_password_change=False,
        actor_user_id=int(session["user_id"]),
        detail="User changed password",
    )
    current_token = getattr(request.state, "auth_token", "")
    db.revoke_user_sessions(cda, int(session["user_id"]), except_raw_token=current_token)
    if current_token:
        db.refresh_session_after_password_change(cda, current_token)
    return {"ok": True}


@admin_router.post("")
def create_user(payload: CreateUserRequest, request: Request, admin: Dict[str, Any] = Depends(_require_admin)):
    cda = _get_cda(request)
    temp_password = generate_temp_password()
    try:
        created = db.create_user(
            cda,
            username=payload.username.strip(),
            email=str(payload.email or "").strip(),
            password_hash_value=hash_password(temp_password),
            is_admin=payload.is_admin,
            mobile_number=str(payload.mobile_number or "").strip(),
            whatsapp_number=str(payload.whatsapp_number or "").strip(),
            telegram_chat_id=str(payload.telegram_chat_id or "").strip(),
            actor_user_id=int(admin["user_id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "user": created,
        "password_sent": False,
        "delivery_note": "Manual password handover (email disabled)",
        "temporary_password": temp_password,
    }


@admin_router.post("/{user_id}/send-new-password")
def send_new_password(user_id: int, request: Request, admin: Dict[str, Any] = Depends(_require_admin)):
    cda = _get_cda(request)
    user = db.get_user_by_id(cda, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    temp_password = generate_temp_password()
    db.set_user_password(
        cda,
        user_id,
        hash_password(temp_password),
        force_password_change=True,
        actor_user_id=int(admin["user_id"]),
        detail="Admin generated temporary password",
    )
    db.revoke_user_sessions(cda, user_id)

    email = str(user.get("email") or "").strip()

    db.audit(
        cda,
        action="send_new_password",
        actor_user_id=int(admin["user_id"]),
        target_user_id=user_id,
        target_email=email,
        detail="Manual password handover (email disabled)",
    )

    return {
        "ok": True,
        "user_id": user_id,
        "password_sent": False,
        "delivery_note": "Manual password handover (email disabled)",
        "temporary_password": temp_password,
    }

@admin_router.get("")
def list_users(request: Request, admin: Dict[str, Any] = Depends(_require_admin)):
    cda = _get_cda(request)
    conn = db.connect(cda)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(Users)")
        cols = {str(row[1]) for row in cur.fetchall()}
        whatsapp_expr = "Users.whatsapp_number" if "whatsapp_number" in cols else "''"
        role_id_expr = "Users.role_id" if "role_id" in cols else ("Users.roleID" if "roleID" in cols else "NULL")
        role_text_col = "role" if "role" in cols else ""
        shift_id_expr = "Users.shiftID" if "shiftID" in cols else "NULL"
        department_id_expr = "Users.department_id" if "department_id" in cols else "NULL"
        shift_text_col = "Users.shift" if "shift" in cols else ("Users.shift_name" if "shift_name" in cols else "")
        department_text_col = "Users.department" if "department" in cols else (
            "Users.dept" if "dept" in cols else ("Users.department_name" if "department_name" in cols else "''")
        )
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Roles' LIMIT 1")
        roles_exists = cur.fetchone() is not None
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shifts' LIMIT 1")
        shifts_exists = cur.fetchone() is not None
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Departments' LIMIT 1")
        departments_exists = cur.fetchone() is not None

        role_lookup_expr = (
            f"COALESCE(NULLIF(Users.{role_text_col}, ''), (SELECT name FROM Roles WHERE id={role_id_expr} LIMIT 1), '')"
            if roles_exists and role_text_col
            else (
                f"COALESCE((SELECT name FROM Roles WHERE id={role_id_expr} LIMIT 1), '')"
                if roles_exists
                else (role_text_col or "''")
            )
        )
        shift_lookup_expr = (
            f"COALESCE(NULLIF({shift_text_col}, ''), (SELECT ShiftName FROM shifts WHERE ShiftID={shift_id_expr} LIMIT 1), '')"
            if shifts_exists and shift_text_col
            else (
                f"COALESCE((SELECT ShiftName FROM shifts WHERE ShiftID={shift_id_expr} LIMIT 1), '')"
                if shifts_exists
                else (shift_text_col or "''")
            )
        )
        department_lookup_expr = (
            f"COALESCE(NULLIF({department_text_col}, ''), (SELECT department_name FROM Departments WHERE departmentID={department_id_expr} LIMIT 1), '')"
            if departments_exists and department_text_col
            else (
                f"COALESCE((SELECT department_name FROM Departments WHERE departmentID={department_id_expr} LIMIT 1), '')"
                if departments_exists
                else (department_text_col or "''")
            )
        )
        cur.execute(
            f"""
            SELECT id, username, email, mobile_number, telegram_chat_id, {whatsapp_expr} AS whatsapp_number, WhatsapID,
                   is_active, is_admin, force_password_change, created_at, last_login,
                   {role_id_expr} AS role_id,
                   {role_lookup_expr} AS role,
                   {shift_id_expr} AS shift_id,
                   {shift_lookup_expr} AS shift,
                   {department_id_expr} AS department_id,
                   {department_lookup_expr} AS department
            FROM Users
            ORDER BY id ASC
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
        shift_options = []
        if shifts_exists:
            cur.execute("SELECT ShiftID AS id, ShiftName AS name FROM shifts ORDER BY ShiftName")
            shift_options = [dict(row) for row in cur.fetchall()]
        department_options = []
        if departments_exists:
            cur.execute("SELECT departmentID AS id, department_name AS name FROM Departments ORDER BY department_name")
            department_options = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    return {
        "count": len(rows),
        "users": [
            {
                "id": r.get("id"),
                "username": r.get("username"),
                "email": r.get("email") or "",
                "mobile_number": r.get("mobile_number") or "",
                "telegram_chat_id": r.get("telegram_chat_id") or "",
                "whatsapp_number": r.get("whatsapp_number") or "",
                "is_active": int(r.get("is_active") or 0) == 1,
                "is_admin": int(r.get("is_admin") or 0) == 1,
                "force_password_change": int(r.get("force_password_change") or 0) == 1,
                "role_id": r.get("role_id"),
                "role": r.get("role") or "",
                "shift_id": r.get("shift_id"),
                "shift": r.get("shift") or "",
                "department_id": r.get("department_id"),
                "department": r.get("department") or "",
                "created_at": r.get("created_at"),
                "last_login": r.get("last_login"),
            }
            for r in rows
        ],
        "shift_options": shift_options,
        "department_options": department_options,
    }



