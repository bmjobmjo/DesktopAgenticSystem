from concurrent.futures import ThreadPoolExecutor

from core.chat_session import SessionStore


def test_get_or_create_returns_same_instance_for_same_key():
    store = SessionStore()
    s1 = store.get_or_create("1", "UI", "default")
    s2 = store.get_or_create("1", "UI", "default")
    assert s1 is s2
    assert store.size() == 1


def test_get_or_create_creates_distinct_sessions_by_interface_and_session_id():
    store = SessionStore()
    s1 = store.get_or_create("1", "UI", "default")
    s2 = store.get_or_create("1", "Telegram", "default")
    s3 = store.get_or_create("1", "UI", "thread-2")
    assert s1 is not s2
    assert s1 is not s3
    assert store.size() == 3


def test_session_store_thread_safety_single_key():
    store = SessionStore()

    def _create():
        return id(store.get_or_create("42", "Telegram", "s1"))

    with ThreadPoolExecutor(max_workers=12) as ex:
        ids = list(ex.map(lambda _: _create(), range(200)))

    assert len(set(ids)) == 1
    assert store.size() == 1


def test_remove_and_get_lifecycle():
    store = SessionStore()
    assert store.get("u1", "UI", "s1") is None

    store.get_or_create("u1", "UI", "s1")
    assert store.get("u1", "UI", "s1") is not None
    assert store.remove("u1", "UI", "s1") is True
    assert store.get("u1", "UI", "s1") is None
    assert store.remove("u1", "UI", "s1") is False
