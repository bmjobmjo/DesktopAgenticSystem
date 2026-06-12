import sqlite3

from core.common_data_area import CommonDataArea
from whatsapp_gateways.whatsapp_controller import WhatsAppController


def test_whatsapp_controller_matches_user_by_mobile_number(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE Users (id INTEGER PRIMARY KEY, mobile_number TEXT)"
        )
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)"
        )
        cur.execute("INSERT INTO Users (id, mobile_number) VALUES (?, ?)", (7, "+91 98765 43210"))
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))

    class _DummyManager:
        def __init__(self) -> None:
            self.requests = []

        def submit(self, req):
            self.requests.append(req)

    manager = _DummyManager()
    controller = WhatsAppController(cda=cda, conversation_manager=manager)

    response = controller.handle_inbound_text("919876543210", "hello")

    assert response == ""
    assert len(manager.requests) == 1
    req = manager.requests[0]
    assert req.user_id == "7"
    assert req.interface == "WhatsApp"
    assert req.conversation_id == "whatsapp:919876543210"
