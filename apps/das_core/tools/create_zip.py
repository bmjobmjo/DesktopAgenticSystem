"""ZIP archive creation tool for bundling multiple files into one output."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from core.common_data_area import CommonDataArea
from tools.filesystem import ensure_accessible
from tools.output_utils import build_error_result, build_success_result, ensure_extension, get_storage_root, resolve_output_path


_COMPRESSION_MAP = {
    "deflated": ZIP_DEFLATED,
    "stored": ZIP_STORED,
}


def _normalize_file_paths(file_paths: List[str] | str) -> List[str]:
    if isinstance(file_paths, str):
        values = [file_paths]
    else:
        values = list(file_paths or [])
    normalized = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not normalized:
        raise ValueError("file_paths must include at least one file path.")
    return normalized


def _normalize_archive_names(archive_paths: List[str] | None, expected_count: int) -> List[str] | None:
    if archive_paths is None:
        return None
    normalized = [str(value or "").strip().strip("/\\") for value in archive_paths]
    if len(normalized) != expected_count:
        raise ValueError("archive_paths must have the same number of items as file_paths.")
    if not all(normalized):
        raise ValueError("archive_paths must not contain empty values.")
    return normalized


def _validate_source_file(path_str: str, storage_root: Path) -> Path:
    source = Path(path_str).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"Source path is not a file: {source}")

    within_storage_root = False
    try:
        within_storage_root = source.is_relative_to(storage_root)
    except AttributeError:
        within_storage_root = str(source).lower().startswith(str(storage_root).lower())

    if within_storage_root:
        return source

    ok, error = ensure_accessible(str(source))
    if not ok:
        raise ValueError(f"{error}: {source}")
    return source


def _compression_value(name: str) -> int:
    normalized = str(name or "deflated").strip().lower()
    if normalized not in _COMPRESSION_MAP:
        raise ValueError("compression must be 'deflated' or 'stored'.")
    return _COMPRESSION_MAP[normalized]


def _unique_archive_name(candidate: str, used: set[str]) -> str:
    path = Path(candidate)
    stem = path.stem or "file"
    suffix = path.suffix
    parent = path.parent
    index = 1
    resolved = candidate
    while resolved.lower() in used:
        index += 1
        renamed = f"{stem}_{index}{suffix}"
        resolved = str(parent / renamed) if str(parent) not in ("", ".") else renamed
    used.add(resolved.lower())
    return resolved


def create_zip(
    output_filename: str,
    file_paths: List[str] | str,
    subfolder: str = "generated",
    archive_paths: List[str] | None = None,
    compression: str = "deflated",
    status_callback=None,
) -> Dict[str, Any]:
    """Create a ZIP archive under the configured file storage path from multiple files."""

    cda = CommonDataArea()
    output_path: Path | None = None
    warnings: List[str] = []
    try:
        source_values = _normalize_file_paths(file_paths)
        archive_values = _normalize_archive_names(archive_paths, len(source_values))
        compression_name = str(compression or "deflated").strip().lower() or "deflated"
        compression_value = _compression_value(compression_name)
        storage_root = get_storage_root(cda)
        _, output_path = resolve_output_path(output_filename, subfolder, cda)
        output_path = ensure_extension(output_path, "zip")

        sources = [_validate_source_file(path_str, storage_root) for path_str in source_values]
        if output_path.exists():
            output_path.unlink()

        if status_callback:
            status_callback(f"Creating ZIP with {len(sources)} file(s)...")

        used_archive_names: set[str] = set()
        archived_files: List[Dict[str, Any]] = []
        total_source_bytes = 0
        with ZipFile(output_path, "w", compression=compression_value) as archive:
            for idx, source in enumerate(sources):
                archive_name = archive_values[idx] if archive_values else source.name
                archive_name = _unique_archive_name(archive_name, used_archive_names)
                archive.write(source, arcname=archive_name)
                size_bytes = source.stat().st_size
                total_source_bytes += size_bytes
                archived_files.append(
                    {
                        "source_path": str(source),
                        "archive_path": archive_name,
                        "size_bytes": size_bytes,
                    }
                )

        if status_callback:
            status_callback("")

        return build_success_result(
            output_path=output_path,
            fmt="zip",
            mode="bundle",
            message="ZIP archive created successfully.",
            warnings=warnings,
            meta={
                "storage_subfolder": subfolder,
                "source_file_count": len(sources),
                "compression": compression_name,
                "archived_files": archived_files,
                "total_source_bytes": total_source_bytes,
            },
        )
    except Exception as exc:
        if status_callback:
            status_callback("")
        return build_error_result(
            output_path=output_path,
            fmt="zip",
            mode="bundle",
            message="ZIP archive creation failed.",
            error=str(exc),
            warnings=warnings,
            meta={"storage_subfolder": subfolder},
        )
