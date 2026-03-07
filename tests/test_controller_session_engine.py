from unittest.mock import MagicMock
import threading

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.executor import Executor
from core.router import Router


class GreetingRouter(Router):
    def __init__(self, cda=None):
        super().__init__(cda)

    def route(self, user_prompt, input_files=None, tool_output=None, chat_history='', max_retries=2):
        return [{
            'type': 'greeting',
            'confidence': 'high',
            'reason': 'test',
            'response_to_user': 'Hello there!',
            'priority': 1,
        }]


def test_controller_session_engine_disabled_by_default():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)

    router = GreetingRouter(cda)
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    response = controller.handle_user_message('Hi', interface='UI')
    assert response.status == 'complete'
    assert controller.session_store.size() == 0


def test_controller_session_engine_creates_and_updates_session():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', True)
    cda.set_setting('current_user_id', '42')

    router = GreetingRouter(cda)
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    response = controller.handle_user_message('Hi', interface='Telegram')
    assert response.status == 'complete'
    assert controller.session_store.size() == 1

    session = controller.session_store.get('42', 'Telegram', 'default')
    assert session is not None
    assert "Hello there!" in session.chat_history
    assert session.awaiting_user_input is False


def test_reset_session_state_clears_ui_session_and_memory():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', True)
    cda.set_setting('current_user_id', '42')

    router = GreetingRouter(cda)
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    response = controller.handle_user_message('Hi', interface='UI')
    assert response.status == 'complete'
    assert controller.session_store.get('42', 'UI', 'default') is not None

    cda.set_memory('agent_activity', 'old activity')
    cda.set_memory('chat_history', 'old history')
    controller.reset_session_state(interface='UI', user_id='42', session_id='default')

    assert controller.session_store.get('42', 'UI', 'default') is None
    assert cda.get_memory('agent_activity', '') == ''
    assert cda.get_memory('chat_history', '') == ''
    assert cda.get_memory('agent_activity_step', -1) == 0


def test_controller_returns_error_when_session_lock_is_busy():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', True)
    cda.set_setting('session_lock_timeout_seconds', 0.25)
    cda.set_setting('current_user_id', '42')

    router = GreetingRouter(cda)
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    session = controller.session_store.get_or_create('42', 'Telegram', 'telegram:abc')
    locked = threading.Event()
    release = threading.Event()

    def hold_lock():
        session.lock.acquire()
        locked.set()
        release.wait(timeout=5)
        session.lock.release()

    worker = threading.Thread(target=hold_lock, daemon=True)
    worker.start()
    assert locked.wait(timeout=1)
    try:
        response = controller.handle_user_message(
            'Hi',
            interface='Telegram',
            user_id='42',
            session_id='telegram:abc',
        )
    finally:
        release.set()
        worker.join(timeout=1)

    assert response.status == 'error'
    assert 'Session lock timeout' in response.content
