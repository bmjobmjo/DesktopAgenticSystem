import os
import sqlite3
import tempfile
from pathlib import Path
from zipfile import ZipFile

from core.common_data_area import CommonDataArea
from core.db_schema import init_db
from core.executor import Executor
from tools.tool_registry import call_tool, get_tool, sync_tools_to_db


def test_create_zip_bundles_multiple_files_under_storage_subfolder():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as storage_dir:
        cda.set_setting("file_storage_path", storage_dir)

        first = Path(storage_dir, "generated", "report.pdf")
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_text("pdf-data", encoding="utf-8")

        second = Path(storage_dir, "generated", "summary.xlsx")
        second.write_text("xlsx-data", encoding="utf-8")

        result = call_tool(
            "create_zip",
            {
                "output_filename": "bundle",
                "subfolder": "archives",
                "file_paths": [str(first), str(second)],
            },
        )

        assert result["success"] is True
        zip_path = Path(result["file_path"])
        assert zip_path.exists()
        assert zip_path.suffix.lower() == ".zip"
        assert zip_path.parent == Path(storage_dir, "archives")
        assert result["meta"]["source_file_count"] == 2
        assert result["meta"]["compression"] == "deflated"

        with ZipFile(zip_path, "r") as archive:
            assert sorted(archive.namelist()) == ["report.pdf", "summary.xlsx"]
            assert archive.read("report.pdf").decode("utf-8") == "pdf-data"
            assert archive.read("summary.xlsx").decode("utf-8") == "xlsx-data"


def test_create_zip_accepts_custom_archive_paths_and_tracks_created_file():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as storage_dir:
        cda.set_setting("file_storage_path", storage_dir)

        first = Path(storage_dir, "generated", "report.pdf")
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_text("pdf-data", encoding="utf-8")

        second = Path(storage_dir, "generated", "summary.xlsx")
        second.write_text("xlsx-data", encoding="utf-8")

        executor = Executor(cda)
        result = executor._execute_tool_call(
            agent_name="tester",
            loop_idx=0,
            tool_name="create_zip",
            parameters={
                "output_filename": "custom_bundle.zip",
                "subfolder": "archives",
                "file_paths": [str(first), str(second)],
                "archive_paths": ["docs/report.pdf", "sheets/summary.xlsx"],
            },
            status_cb=None,
        )

        assert result["success"] is True
        created_files = cda.get_memory("created_files")
        assert created_files
        assert created_files[-1]["file_path"] == result["file_path"]

        with ZipFile(result["file_path"], "r") as archive:
            assert sorted(archive.namelist()) == ["docs/report.pdf", "sheets/summary.xlsx"]


def test_sync_tools_to_db_registers_create_zip_metadata():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tools.db")
        cda.set_setting("sqlite_db_path", db_path)
        init_db()
        sync_tools_to_db(cda)

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT description, input_schema, output_schema, example_call FROM ToolList WHERE name=?",
                ("create_zip",),
            )
            row = cur.fetchone()
        finally:
            conn.close()

        assert row is not None
        description, input_schema, output_schema, example_call = row
        assert "ZIP archive" in description
        assert "file_paths" in input_schema
        assert "bundled file count" in output_schema.lower()
        assert "project_bundle" in example_call
        assert get_tool("create_zip") is not None
