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
    resolved: List[str] = []

    for raw in dirs:
        if isinstance(raw, str) and raw:
            normalized = normalize_path(raw)
            if normalized not in resolved:
                resolved.append(normalized)

    # Always allow the configured managed storage root so uploaded files,
    # generated reports, and ingested artifacts remain readable even when
    # explicit accessible_directories were not configured in a hosted setup.
    storage_root = str(cda.get_setting('file_storage_path', '') or '').strip()
    if storage_root:
        normalized_storage = normalize_path(storage_root)
        if normalized_storage not in resolved:
            resolved.append(normalized_storage)

    return resolved


def ensure_accessible(path: str) -> Tuple[bool, str]:
    dirs = get_accessible_directories()
    if not dirs:
        return False, 'No accessible directories configured.'

    normalized = normalize_path(path)
    for base in dirs:
        if _safe_commonpath(normalized, base):
            return True, ''
    return False, 'Path is outside accessible directories.'
