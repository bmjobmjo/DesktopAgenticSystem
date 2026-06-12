"""Shared channel command helpers."""

from __future__ import annotations

import re


NEW_SESSION_COMMAND = "/new"
NEW_SESSION_RESET_MESSAGE = "Started a new chat session. Previous session context cleared."

_NEW_SESSION_RE = re.compile(r"^\s*/new\s*$")


def is_new_session_command(text: str) -> bool:
    """Return True only when the full message is the /new command."""
    return bool(_NEW_SESSION_RE.fullmatch(str(text or "")))
