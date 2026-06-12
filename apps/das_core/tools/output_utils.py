"""Helpers for generated file and image outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from core.common_data_area import CommonDataArea

_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")


def get_storage_root(cda: CommonDataArea | None = None) -> Path:
    cda = cda or CommonDataArea()
    configured = str(cda.get_setting("file_storage_path", "storage/files") or "storage/files").strip()
    if not configured:
        configured = "storage/files"
    return Path(configured).resolve()


def sanitize_subfolder(subfolder: str | None) -> str:
    raw = str(subfolder or "generated").strip().strip("/\\")
    if not raw:
        return "generated"
    parts = [part for part in Path(raw).parts if part not in ("..", ".", "")]
    return str(Path(*parts)) if parts else "generated"


def sanitize_filename(filename: str) -> str:
    name = Path(str(filename or "").strip()).name
    if not name:
        raise ValueError("output_filename is required.")
    if name in (".", ".."):
        raise ValueError("Invalid output_filename.")
    return name


def resolve_output_path(
    output_filename: str,
    subfolder: str | None = None,
    cda: CommonDataArea | None = None,
) -> Tuple[Path, Path]:
    storage_root = get_storage_root(cda)
    target_dir = storage_root / sanitize_subfolder(subfolder)
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = (target_dir / sanitize_filename(output_filename)).resolve()
    if output_path.parent != target_dir.resolve():
        raise ValueError("output_filename must not contain directory traversal.")
    return storage_root, output_path


def ensure_extension(path: Path, expected_ext: str) -> Path:
    ext = expected_ext.lower().lstrip(".")
    if path.suffix.lower() == f".{ext}":
        return path
    return path.with_suffix(f".{ext}")


def placeholder_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return str(value)


def replace_placeholders(text: str, data: Dict[str, Any] | None) -> str:
    values = data or {}

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return placeholder_text(values.get(key, ""))

    return _PLACEHOLDER_RE.sub(_replace, str(text or ""))


def normalize_columns(columns: Iterable[Dict[str, Any]] | None, rows: List[Dict[str, Any]] | None) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for col in columns or []:
        if not isinstance(col, dict):
            continue
        key = ''
        for alias in ('key', 'name', 'data_key', 'data_property', 'field'):
            candidate = str(col.get(alias, '') or '').strip()
            if candidate:
                key = candidate
                break
        if not key:
            continue
        header = str(col.get('header', key) or key)
        normalized.append({'key': key, 'header': header})

    if normalized or not rows:
        return normalized

    first = rows[0] if rows else {}
    if isinstance(first, dict):
        return [{'key': str(k), 'header': str(k)} for k in first.keys()]
    return normalized


def rows_as_matrix(columns: List[Dict[str, str]], rows: List[Dict[str, Any]] | None) -> List[List[str]]:
    matrix: List[List[str]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        matrix.append([placeholder_text(row.get(col["key"], "")) for col in columns])
    return matrix


def build_success_result(
    *,
    output_path: Path,
    fmt: str,
    mode: str,
    message: str,
    warnings: List[str] | None = None,
    meta: Dict[str, Any] | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": True,
        "file_path": str(output_path),
        "format": fmt,
        "mode": mode,
        "bytes_written": output_path.stat().st_size if output_path.exists() else 0,
        "message": message,
        "meta": meta or {},
        "warnings": warnings or [],
        "created_file": True,
    }
    if width is not None:
        result["width"] = width
    if height is not None:
        result["height"] = height
    return result


def build_error_result(
    *,
    output_path: Path | None,
    fmt: str,
    mode: str,
    message: str,
    error: str,
    warnings: List[str] | None = None,
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "success": False,
        "file_path": str(output_path) if output_path is not None else "",
        "format": fmt,
        "mode": mode,
        "message": message,
        "error": error,
        "meta": meta or {},
        "warnings": warnings or [],
    }


def collect_created_file_info(result: Any) -> Dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    if not result.get("success"):
        return None
    file_path = str(result.get("file_path", "") or "").strip()
    if not file_path:
        return None
    return {
        "file_path": file_path,
        "format": str(result.get("format", "") or ""),
        "mode": str(result.get("mode", "") or ""),
        "message": str(result.get("message", "") or ""),
        "bytes_written": int(result.get("bytes_written", 0) or 0),
    }
