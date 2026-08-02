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


def test_expense_prompt_preserves_created_zip_path_after_later_tool_result():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", "__missing_prompt_context_test__.db")
    executor = Executor(cda)
    executor._init_execution_context("expense_manager", "send the expense ZIP")

    zip_path = "/storage/files/archives/july_expenses.zip"
    executor._record_tool_result(
        {
            "success": True,
            "file_path": zip_path,
            "format": "zip",
            "mode": "bundle",
            "bytes_written": 1234,
            "message": "ZIP archive created successfully.",
        }
    )
    executor._record_tool_result(
        {
            "success": True,
            "rows": [{"id": 6, "whatsapp_number": "+919999999999"}],
        }
    )

    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "agents"
        / "expense_manager"
        / "expense_manager.prompt"
    )
    rendered = executor._prepare_prompt(
        prompt_path.read_text(encoding="utf-8"),
        "send the expense ZIP",
        0,
    )

    assert zip_path in rendered
    assert '"whatsapp_number": "+919999999999"' in rendered
    assert "TOOL_DATA- not available" not in rendered


def test_generic_agent_template_exposes_persistent_created_file_context():
    template_path = (
        Path(__file__).resolve().parents[1]
        / "prompts"
        / "templates"
        / "agent_template.txt"
    )
    template = template_path.read_text(encoding="utf-8")

    assert "LAST_TOOL_RESULT: {{TOOL_DATA}}" in template
    assert "LAST_CREATED_FILE: {{LAST_CREATED_FILE}}" in template
    assert "CREATED_FILES: {{CREATED_FILES}}" in template
