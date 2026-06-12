import sqlite3

from core.channel_commands import NEW_SESSION_RESET_MESSAGE
from core.common_data_area import CommonDataArea
from telagram_gateways.telegram_controller import TelegramController


class _DummyConversationManager:
    def __init__(self) -> None:
        self.reset_calls = []

    def reset_conversation(self, conversation_id: str, interface: str | None = None, user_id: str | None = None) -> bool:
        self.reset_calls.append((conversation_id, interface, user_id))
        return True


def test_telegram_new_command_clears_pending_auth_and_resets_session(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE Users (id INTEGER PRIMARY KEY, email TEXT, username TEXT, telegram_chat_id TEXT)"
        )
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT)"
        )
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    manager = _DummyConversationManager()
    controller = TelegramController(cda=cda, conversation_manager=manager)
    controller._pending_email_by_chat.add("555")

    response = controller.handle_inbound_text("555", "/new\r\n")

    assert response == NEW_SESSION_RESET_MESSAGE
    assert "555" not in controller._pending_email_by_chat
    assert manager.reset_calls == [("telegram:555", "Telegram", None)]
