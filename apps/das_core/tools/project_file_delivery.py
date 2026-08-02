"""Prepare registered project documents for safe outbound delivery."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zipfile import ZIP_DEFLATED, ZipFile

from core.common_data_area import CommonDataArea
from tools.output_utils import get_storage_root, resolve_output_path, sanitize_filename


__tool_exports__ = ["prepare_project_files_for_delivery"]


def _database_path(cda: CommonDataArea) -> Path:
    configured = str(cda.get_setting("sqlite_db_path", "") or "").strip()
    if configured:
        candidate = Path(configured).resolve()
        if candidate.is_file():
            return candidate
    for candidate in (
        Path("data/office_automation.db").resolve(),
        Path("backend.db").resolve(),
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("The configured application database could not be found.")


def _as_ints(values: Iterable[Any] | None) -> List[int]:
    result: List[int] = []
    for value in values or []:
        try:
            item = int(value)
        except (TypeError, ValueError):
            raise ValueError("file_ids must contain only numeric Files.id values.") from None
        if item not in result:
            result.append(item)
    return result


def _as_names(values: Iterable[Any] | None) -> List[str]:
    result: List[str] = []
    for value in values or []:
        name = Path(str(value or "").strip()).name
        if not name:
            continue
        if name.casefold() not in {item.casefold() for item in result}:
            result.append(name)
    return result


def _resolve_stored_path(raw_path: str) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise FileNotFoundError("The registered file has no stored path.")
    stored = Path(raw)
    return stored.resolve() if stored.is_absolute() else (Path.cwd() / stored).resolve()


def prepare_project_files_for_delivery(
    project_id: int,
    file_ids: List[int] | None = None,
    filenames: List[str] | None = None,
    output_filename: str = "",
    bundle_as_zip: bool = False,
    status_callback=None,
) -> Dict[str, Any]:
    """Stage selected project Files records, optionally bundling them as one ZIP.

    Source paths are never supplied by the model. They are resolved from Files rows
    scoped to ``project_id``, which lets registered documents be delivered even when
    their original storage location is not a generic accessible directory.
    """

    try:
        project_key = int(project_id)
        ids = _as_ints(file_ids)
        names = _as_names(filenames)
        if not ids and not names:
            raise ValueError("Provide at least one project file id or filename.")

        if status_callback:
            status_callback("Preparing project document(s) for delivery...")

        cda = CommonDataArea()
        db_path = _database_path(cda)
        connection = sqlite3.connect(str(db_path), timeout=20)
        try:
            cursor = connection.cursor()
            rows = cursor.execute(
                "SELECT id, filename, file_path FROM Files WHERE project_id=? ORDER BY id",
                (project_key,),
            ).fetchall()
        finally:
            connection.close()

        wanted_ids = set(ids)
        wanted_names = {name.casefold() for name in names}
        duplicate_names = [
            name for name in names if sum(str(row[1]).casefold() == name.casefold() for row in rows) > 1
        ]
        if duplicate_names:
            raise ValueError(
                "More than one project file has this filename; select it by file id instead: "
                + ", ".join(sorted(set(duplicate_names)))
            )
        selected = [
            {"id": int(row[0]), "filename": str(row[1]), "file_path": str(row[2])}
            for row in rows
            if int(row[0]) in wanted_ids or str(row[1]).casefold() in wanted_names
        ]
        selected_ids = {item["id"] for item in selected}
        selected_names = {item["filename"].casefold() for item in selected}
        missing_ids = sorted(wanted_ids - selected_ids)
        missing_names = sorted(name for name in names if name.casefold() not in selected_names)
        if missing_ids or missing_names:
            missing = [*(f"id {item}" for item in missing_ids), *missing_names]
            raise ValueError("Selected file(s) are not linked to this project: " + ", ".join(missing))

        sources: List[tuple[Dict[str, Any], Path]] = []
        for item in selected:
            source = _resolve_stored_path(item["file_path"])
            if not source.is_file():
                raise FileNotFoundError(f"Registered project file is unavailable: {item['filename']}")
            sources.append((item, source))

        should_bundle = bool(bundle_as_zip or len(sources) > 1)
        default_name = f"project_{project_key}_files.zip" if should_bundle else sources[0][1].name
        target_name = sanitize_filename(output_filename or default_name)
        storage_root = get_storage_root(cda)
        _, output_path = resolve_output_path(target_name, "outbound/project_files", cda)
        if should_bundle and output_path.suffix.lower() != ".zip":
            output_path = output_path.with_suffix(".zip")

        if should_bundle:
            used_names: set[str] = set()
            with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
                for item, source in sources:
                    name = source.name
                    stem, suffix = Path(name).stem, Path(name).suffix
                    index = 2
                    while name.casefold() in used_names:
                        name = f"{stem}_{index}{suffix}"
                        index += 1
                    used_names.add(name.casefold())
                    archive.write(source, arcname=name)
        else:
            shutil.copy2(sources[0][1], output_path)

        # The output must stay under configured managed storage before it can be
        # passed to a channel-delivery tool.
        output_path = output_path.resolve()
        if not output_path.is_relative_to(storage_root.resolve()):
            raise ValueError("Prepared output is outside managed file storage.")

        if status_callback:
            status_callback("")
        return {
            "success": True,
            "file_path": str(output_path),
            "bundle_as_zip": should_bundle,
            "file_count": len(sources),
            "files": [{"id": item["id"], "filename": item["filename"]} for item, _ in sources],
        }
    except Exception as exc:
        if status_callback:
            status_callback("")
        return {"success": False, "error": str(exc)}
