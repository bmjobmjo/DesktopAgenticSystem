from datetime import datetime, timezone

from ui.chat_ui import ChatUI


def test_history_timestamp_is_converted_from_utc_to_local_time():
    raw = "2026-03-10 14:41:12"

    formatted = ChatUI._format_history_timestamp(raw)

    expected = (
        datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .astimezone(datetime.now().astimezone().tzinfo)
        .strftime("%Y-%m-%d %H:%M:%S")
    )
    assert formatted == expected
