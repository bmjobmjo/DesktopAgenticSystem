"""Filesystem tool helpers."""

from __future__ import annotations

import os
from typing import List, Tuple

from core.common_data_area import CommonDataArea


def normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def _safe_commonpath(path: str, base: str) -> bool:
    try:
        return os.path.commonpath([path, base]) == base
    except ValueError:
        return False


def get_accessible_directories() -> List[str]:
    cda = CommonDataArea()
    dirs = cda.get_setting('accessible_directories', []) or []
    return [normalize_path(d) for d in dirs if isinstance(d, str) and d]


def ensure_accessible(path: str) -> Tuple[bool, str]:
    dirs = get_accessible_directories()
    if not dirs:
        return False, 'No accessible directories configured.'

    normalized = normalize_path(path)
    for base in dirs:
        if _safe_commonpath(normalized, base):
            return True, ''
    return False, 'Path is outside accessible directories.'
