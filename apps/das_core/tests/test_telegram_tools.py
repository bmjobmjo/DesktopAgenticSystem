import sqlite3
from pathlib import Path

from core.common_data_area import CommonDataArea
from tools.telegram_tools import _resolve_chat_id


def test_resolve_chat_id_prefers_mapping_when_explicit_matches_user_id(tmp_path):
    db_path = Path(tmp_path) / 'test.db'
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Users (id INTEGER PRIMARY KEY, telegram_chat_id TEXT)")
        cur.execute("CREATE TABLE ChannelUsers (id INTEGER PRIMARY KEY, provider TEXT, channel_user_id TEXT, user_id TEXT)")
        cur.execute("INSERT INTO Users (id, telegram_chat_id) VALUES (?, ?)", (3, '6418599489'))
        cur.execute("INSERT INTO ChannelUsers (provider, channel_user_id, user_id) VALUES (?, ?, ?)", ('telegram', '6418599489', '3'))
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('sqlite_db_path', str(db_path))

    resolved = _resolve_chat_id('3', '3', cda)

    assert resolved == '6418599489'


def test_resolve_chat_id_keeps_real_explicit_chat_id(tmp_path):
    db_path = Path(tmp_path) / 'test.db'
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Users (id INTEGER PRIMARY KEY, telegram_chat_id TEXT)")
        cur.execute("CREATE TABLE ChannelUsers (id INTEGER PRIMARY KEY, provider TEXT, channel_user_id TEXT, user_id TEXT)")
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('sqlite_db_path', str(db_path))

    resolved = _resolve_chat_id('6418599489', '3', cda)

    assert resolved == '6418599489'
