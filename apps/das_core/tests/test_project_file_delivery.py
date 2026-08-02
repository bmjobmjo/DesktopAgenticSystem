import sqlite3
import tempfile
from pathlib import Path
from zipfile import ZipFile

from core.common_data_area import CommonDataArea
from tools.tool_registry import call_tool, get_tool


def _add_project_file(connection, file_id: int, filename: str, path: Path, project_id: int = 7) -> None:
    connection.execute(
        "INSERT INTO Files (id, filename, file_path, project_id) VALUES (?, ?, ?, ?)",
        (file_id, filename, str(path), project_id),
    )


def test_project_file_delivery_stages_registered_external_file_and_bundles_multiple_files():
    cda = CommonDataArea()
    cda.reset()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        storage = root / "managed_storage"
        external = root / "original_uploads"
        external.mkdir()
        first = external / "display.pdf"
        second = external / "requirements.xlsx"
        first.write_text("display document", encoding="utf-8")
        second.write_text("requirements sheet", encoding="utf-8")

        db_path = root / "app.db"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("CREATE TABLE Files (id INTEGER PRIMARY KEY, filename TEXT, file_path TEXT, project_id INTEGER)")
            _add_project_file(connection, 11, first.name, first)
            _add_project_file(connection, 12, second.name, second)
            connection.commit()
        finally:
            connection.close()

        cda.set_setting("sqlite_db_path", str(db_path))
        cda.set_setting("file_storage_path", str(storage))
        # Deliberately omit the external folder from accessible_directories. The
        # Files row plus matching project id is the authorization boundary.
        result = call_tool(
            "prepare_project_files_for_delivery",
            {"project_id": 7, "file_ids": [11, 12], "output_filename": "vsm_documents"},
        )

        assert result["success"] is True
        assert result["bundle_as_zip"] is True
        output = Path(result["file_path"])
        assert output.suffix == ".zip"
        assert output.is_relative_to(storage)
        with ZipFile(output) as archive:
            assert sorted(archive.namelist()) == ["display.pdf", "requirements.xlsx"]


def test_project_file_delivery_rejects_file_not_linked_to_selected_project():
    cda = CommonDataArea()
    cda.reset()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source = root / "confidential.pdf"
        source.write_text("not VSM", encoding="utf-8")
        db_path = root / "app.db"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("CREATE TABLE Files (id INTEGER PRIMARY KEY, filename TEXT, file_path TEXT, project_id INTEGER)")
            _add_project_file(connection, 99, source.name, source, project_id=8)
            connection.commit()
        finally:
            connection.close()

        cda.set_setting("sqlite_db_path", str(db_path))
        cda.set_setting("file_storage_path", str(root / "managed_storage"))
        result = call_tool("prepare_project_files_for_delivery", {"project_id": 7, "file_ids": [99]})

        assert result["success"] is False
        assert "not linked" in result["error"]


def test_project_file_delivery_tool_is_registered():
    assert get_tool("prepare_project_files_for_delivery") is not None
