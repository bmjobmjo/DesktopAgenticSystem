from unittest.mock import MagicMock
import threading
import sqlite3

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.executor import Executor, ExecutorError, ExecutorResult
from core.router import Router, RouterError


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


class SingleAgentRouter(Router):
    def __init__(self, cda=None):
        super().__init__(cda)

    def route(self, user_prompt, input_files=None, tool_output=None, chat_history='', max_retries=2):
        return [{
            'type': 'agent_call',
            'selected_agent': 'file_manager',
            'instruction': 'do work',
            'confidence': 'high',
            'reason': 'test',
            'priority': 1,
        }]


class TokenGateExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise ExecutorError("Interaction token budget exceeded (used=120001, limit=120000).")
        return ExecutorResult(status='complete', content='completed after approval', ui_feedback=[])


class AlwaysTokenGateExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        raise ExecutorError("Interaction token budget reached before LLM call (used=120000, limit=120000).")


class TokenGateRouter(Router):
    def __init__(self, cda=None):
        super().__init__(cda)
        self.calls = 0

    def route(self, user_prompt, input_files=None, tool_output=None, chat_history='', max_retries=2):
        self.calls += 1
        if self.calls == 1:
            raise RouterError("Interaction token budget reached before router call (used=120000, limit=120000).")
        return [{
            'type': 'greeting',
            'confidence': 'high',
            'reason': 'approved resume',
            'response_to_user': 'continued after approval',
            'priority': 1,
        }]


class RepeatedSameAgentRouter(Router):
    def __init__(self, cda=None):
        super().__init__(cda)

    def route(self, user_prompt, input_files=None, tool_output=None, chat_history='', max_retries=2):
        return [
            {
                'type': 'agent_call',
                'selected_agent': 'file_manager',
                'instruction': 'do work 1',
                'confidence': 'high',
                'reason': 'test',
                'priority': 1,
            },
            {
                'type': 'agent_call',
                'selected_agent': 'file_manager',
                'instruction': 'do work 2',
                'confidence': 'high',
                'reason': 'test',
                'priority': 2,
            },
        ]


class AlwaysCompleteExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return ExecutorResult(status='complete', content=f'complete-{self.calls}', ui_feedback=[])


class ToolFeedbackLoopRouter(Router):
    def __init__(self, cda=None):
        super().__init__(cda)
        self.calls = 0

    def route(self, user_prompt, input_files=None, tool_output=None, chat_history='', max_retries=2):
        self.calls += 1
        return [
            {
                'type': 'tool_call',
                'tool_name': 'fake_tool',
                'parameters': {'value': 1},
                'confidence': 'high',
                'reason': 'test reroute loop',
                'priority': 1,
            }
        ]


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


def test_web_interface_persists_chat_history(tmp_path):
    db_path = tmp_path / "history.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE ChatHistory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                agent_activity TEXT,
                user_id TEXT,
                interface TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ChatLog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                role TEXT,
                content TEXT,
                user_id TEXT,
                interface TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', True)
    cda.set_setting('sqlite_db_path', str(db_path))

    controller = Controller(cda, SingleAgentRouter(cda), AlwaysCompleteExecutor())
    response = controller.handle_user_message('save this web chat', interface='WEB', user_id='9', session_id='web-test')

    assert response.status == 'complete'
    conn = sqlite3.connect(str(db_path))
    try:
        history = conn.execute("SELECT title, user_id, interface FROM ChatHistory").fetchall()
        logs = conn.execute("SELECT role, content, user_id, interface FROM ChatLog ORDER BY id").fetchall()
    finally:
        conn.close()

    assert history == [('save this web chat', '9', 'WEB')]
    assert logs == [
        ('User', 'save this web chat', '9', 'WEB'),
        ('Agent', 'complete-1', '9', 'WEB'),
    ]


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
    cda.set_memory('execution_metadata_dict', {'foo': 'bar'})
    cda.set_memory('active_executor_agent', 'attendance_manager')
    cda.set_memory('prompt_context_dict', {'UID': '42', 'USER_NAME': 'User 42', 'CHAT_HISTORY': 'old history'})
    controller.reset_session_state(interface='UI', user_id='42', session_id='default')

    assert controller.session_store.get('42', 'UI', 'default') is None
    assert cda.get_memory('agent_activity', '') == ''
    assert cda.get_memory('chat_history', '') == ''
    assert cda.get_memory('agent_activity_step', -1) == 0
    assert cda.get_memory('execution_metadata_dict', None) == {}
    assert cda.get_memory('active_executor_agent', None) == ''
    assert cda.get_memory('prompt_context_dict', {}) == {
        'UID': '42',
        'USER_NAME': 'User 42',
        'CHAT_HISTORY': '',
        'TOOL_DATA': '',
        'CREATED_FILES': [],
        'LAST_CREATED_FILE': '',
        'INSTRUCTIONS': '',
        'IS_SCHEDULED_TASK': '0',
        'SCHEDULE_ID': '',
        'SCHEDULE_OWNER_ID': '',
        'EXECUTION_SOURCE': '',
    }


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


def test_controller_requests_token_approval_and_resumes_on_yes():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)
    cda.set_setting('interaction_max_tokens', 100)
    cda.set_memory('interaction_token_usage', {'total': 100, 'router': 0, 'executor': 100})

    router = SingleAgentRouter(cda)
    executor = TokenGateExecutor()
    controller = Controller(cda, router, executor)

    first = controller.handle_user_message('run task', interface='UI')
    assert first.status == 'request_user_input'
    assert 'Token budget reached' in first.content
    assert isinstance(first.tool_request, dict)
    assert first.tool_request.get('permission_type') == 'token_budget_continue'
    assert int(first.tool_request.get('suggested_increment') or 0) == 100

    second = controller.handle_user_message('yes', interface='UI')
    assert second.status == 'complete'
    assert 'completed after approval' in second.content
    assert executor.calls == 2


def test_controller_stops_on_token_approval_no():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)
    cda.set_setting('interaction_max_tokens', 100)
    cda.set_memory('interaction_token_usage', {'total': 100, 'router': 0, 'executor': 100})

    router = SingleAgentRouter(cda)
    executor = AlwaysTokenGateExecutor()
    controller = Controller(cda, router, executor)

    first = controller.handle_user_message('run task', interface='UI')
    assert first.status == 'request_user_input'
    assert 'Token budget reached' in first.content

    second = controller.handle_user_message('no', interface='UI')
    assert second.status == 'complete'
    assert 'Stopped to avoid additional token usage.' in second.content


def test_controller_requests_token_approval_for_router_and_resumes():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)
    cda.set_setting('interaction_max_tokens', 100)
    cda.set_memory('interaction_token_usage', {'total': 120000, 'router': 120000, 'executor': 0})

    router = TokenGateRouter(cda)
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    first = controller.handle_user_message('route this', interface='UI')
    assert first.status == 'request_user_input'
    assert 'Token budget reached' in first.content
    assert isinstance(first.tool_request, dict)
    assert first.tool_request.get('permission_type') == 'token_budget_continue'
    assert int(first.tool_request.get('suggested_increment') or 0) == 100

    second = controller.handle_user_message('yes', interface='UI')
    assert second.status == 'complete'
    assert 'continued after approval' in second.content
    assert router.calls == 2


def test_controller_stops_when_same_agent_repeats_too_many_times():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)
    cda.set_setting('interaction_max_same_agent_calls', 1)

    router = RepeatedSameAgentRouter(cda)
    executor = AlwaysCompleteExecutor()
    controller = Controller(cda, router, executor)

    response = controller.handle_user_message('run tasks', interface='UI')
    assert response.status == 'error'
    assert 'same agent executed repeatedly' in response.content
    assert executor.calls == 1


def test_controller_stops_when_reroute_feedback_loops(monkeypatch):
    def _fake_call_tool(tool_name, parameters, status_callback=None):
        return {'success': True, 'data': {'echo': parameters}}

    monkeypatch.setattr('tools.tool_registry.call_tool', _fake_call_tool)

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)
    cda.set_setting('interaction_max_reroutes', 2)
    cda.set_setting('interaction_max_same_tool_calls', 99)
    cda.set_setting('interaction_max_queue_steps', 200)

    router = ToolFeedbackLoopRouter(cda)
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    response = controller.handle_user_message('loop', interface='UI')
    assert response.status == 'error'
    assert 'too many Router re-routes' in response.content
    assert router.calls >= 3
