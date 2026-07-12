from datetime import datetime

from core.common_data_area import CommonDataArea
from core.scheduler_agent import compute_next_run, validate_schedule_request


def test_validate_schedule_request_rejects_time_only_prompt():
    cda = CommonDataArea()
    cda.reset()

    parsed = validate_schedule_request("10.30 AM on monday to friday", cda=cda)

    assert parsed["is_valid"] is False
    assert "task prompt" in parsed["reason"].lower()


def test_validate_schedule_request_parses_weekday_dot_time_request():
    cda = CommonDataArea()
    cda.reset()

    parsed = validate_schedule_request(
        "Send attendance and daily task marking reminder on WhatsApp to all by 10.30 AM on monday to friday",
        cda=cda,
    )

    assert parsed["is_valid"] is True
    assert parsed["task_prompt"].lower().startswith("send attendance and daily task marking reminder")
    assert parsed["run_hour"] == 10
    assert parsed["run_minute"] == 30
    assert parsed["days_of_week"] == "0,1,2,3,4"


def test_compute_next_run_honors_multi_weekday_schedule():
    now = datetime(2026, 7, 10, 11, 0, 0)  # Friday
    record = {
        "schedule_type": "daily",
        "interval_minutes": 0,
        "run_hour": 10,
        "run_minute": 30,
        "run_day_of_week": 0,
        "days_of_week": "0,1,2,3,4",
        "run_day_of_month": 1,
    }

    next_run = compute_next_run(record, now=now)

    assert next_run == datetime(2026, 7, 13, 10, 30, 0)  # Next Monday
