import sqlite3
from pathlib import Path
from types import SimpleNamespace

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.db_schema import init_db
from core.executor import ExecutorResult
from core.scheduler_service import SchedulerService


class StubRouter:
    def route(self, **kwargs):
        return [{"type": "continue", "selected_agent": "file_manager", "instruction": kwargs.get("user_prompt", "") }]


class CapturingExecutor:
    def __init__(self, cda: CommonDataArea) -> None:
        self.cda = cda
        self.prompt_ctx = {}
        self.execution_meta = {}

    def execute(self, *args, **kwargs):
        self.prompt_ctx = dict(self.cda.get_memory("prompt_context_dict", {}) or {})
        self.execution_meta = dict(self.cda.get_memory("execution_metadata_dict", {}) or {})
        return ExecutorResult(status="complete", content="scheduled-ok", ui_feedback=[])


class FakeTelegramService:
    def __init__(self) -> None:
        self.sent_messages = []
        self.sent_documents = []

    def send_text(self, chat_id: str, text: str):
        self.sent_messages.append((chat_id, text))
        return {"ok": True}

    def send_document(self, chat_id: str, file_path: str, caption: str = ""):
        self.sent_documents.append((chat_id, file_path, caption))
        return {"ok": True}


class FakeController:
    def handle_user_message(self, *args, **kwargs):
        return SimpleNamespace(status="complete", content="owner-result")


def test_controller_exposes_scheduled_execution_metadata():
    cda = CommonDataArea()
    cda.reset()

    executor = CapturingExecutor(cda)
    controller = Controller(cda=cda, router=StubRouter(), executor=executor)

    response = controller.handle_user_message(
        "Run the scheduled task",
        interface="Scheduler",
        user_id="owner-1",
        session_id="scheduler:42",
        execution_metadata={
            "is_scheduled_task": True,
            "schedule_id": 42,
            "schedule_owner_id": "owner-1",
            "execution_source": "scheduler",
        },
    )

    assert response.status == "complete"
    assert executor.prompt_ctx["IS_SCHEDULED_TASK"] == "1"
    assert executor.prompt_ctx["SCHEDULE_ID"] == "42"
    assert executor.prompt_ctx["SCHEDULE_OWNER_ID"] == "owner-1"
    assert executor.prompt_ctx["EXECUTION_SOURCE"] == "scheduler"
    assert executor.execution_meta["is_scheduled_task"] is True


def test_scheduler_service_sends_result_to_owner_channels(tmp_path: Path):
    cda = CommonDataArea()
    cda.reset()

    db_path = tmp_path / "scheduler_test.db"
    cda.set_setting("sqlite_db_path", str(db_path))
    init_db()

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ChannelUsers (provider, channel_user_id, user_id) VALUES (?, ?, ?)",
            ("telegram", "tg-chat-1", "owner-1"),
        )
        cur.execute(
            """
            INSERT INTO Schedules (
                title, task_prompt, schedule_type, interval_minutes,
                run_hour, run_minute, run_day_of_week, run_day_of_month,
                is_enabled, status, next_run_at, owner, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Test schedule",
                "Send result to owner",
                "other",
                60,
                9,
                0,
                0,
                1,
                1,
                "active",
                "2000-01-01 00:00:00",
                "owner-1",
                "owner-1",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    tg_service = FakeTelegramService()
    cda.set_runtime("telegram_channel_service", tg_service)

    svc = SchedulerService(cda=cda, controller=FakeController())
    result = svc.run_schedule_now(1)

    assert result["last_result"] == "[ok] owner-result"
    assert tg_service.sent_messages == [("tg-chat-1", "[ok] owner-result")]


def test_one_time_schedule_creates_audited_run_and_completes(tmp_path: Path):
    cda = CommonDataArea(); cda.reset()
    db_path = tmp_path / "one_time.db"; cda.set_setting("sqlite_db_path", str(db_path)); init_db()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""INSERT INTO Schedules (title,task_prompt,schedule_type,interval_minutes,status,is_enabled,next_run_at,schedule_mode,owner)
                        VALUES ('Once','do work','other',1,'active',1,'2000-01-01 00:00:00','once','owner-1')""")
        conn.commit()
    finally: conn.close()
    SchedulerService(cda=cda, controller=FakeController()).run_schedule_now(1)
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT status FROM Schedules WHERE id=1").fetchone()[0] == "completed"
        assert conn.execute("SELECT status,prompt_snapshot FROM ScheduleRuns WHERE schedule_id=1").fetchone() == ("succeeded", "do work")
    finally: conn.close()
