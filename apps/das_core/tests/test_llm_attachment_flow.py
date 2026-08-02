import json
from unittest.mock import patch

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.executor import Executor, ExecutorError
from core.router import Router
from core.llm_attachments import build_llm_attachments


class RecordingRouterLLM:
    def __init__(self):
        self.attachments = None
        self.prompt = None
        self.last_usage = {}

    def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
        self.attachments = attachments or []
        self.prompt = prompt
        return json.dumps([
            {
                'type': 'agent_call',
                'selected_agent': 'file_manager',
                'instruction': 'Inspect the attached file.',
                'confidence': 'high',
                'reason': 'File content indicates file handling.',
                'priority': 1,
            }
        ])


class RecordingExecutorLLM:
    def __init__(self):
        self.attachments = None
        self.last_usage = {}

    def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
        self.attachments = attachments or []
        return json.dumps({
            'plan': {'current_step': 'Answer user', 'revised_plan': 'Complete response'},
            'action': {'type': 'complete'},
            'conversation_update': {'content': 'done'},
            'reasoning': {'summary': 'done'},
            'ui_feedback': {'status': 'complete', 'message': 'done'},
        })


class HandoffExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, agent_name, user_prompt, **kwargs):
        self.calls.append({
            'agent_name': agent_name,
            'user_prompt': user_prompt,
            'llm_attachments': kwargs.get('llm_attachments'),
            'input_files': kwargs.get('input_files'),
        })
        if len(self.calls) == 1:
            from core.executor import ExecutorResult
            return ExecutorResult(
                status='agent_call',
                content='handoff instruction',
                ui_feedback=[],
                tool_request={'selected_agent': 'database_manager'},
            )
        from core.executor import ExecutorResult
        return ExecutorResult(status='complete', content='final', ui_feedback=[])


class DuplicateHandoffExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, agent_name, user_prompt, **kwargs):
        self.calls.append(agent_name)
        from core.executor import ExecutorResult
        if len(self.calls) == 1:
            return ExecutorResult(
                status='agent_call',
                content='Please route to ExpenseManager',
                ui_feedback=[],
                tool_request={'selected_agent': 'ExpenseManager'},
            )
        return ExecutorResult(status='complete', content=f'done:{agent_name}', ui_feedback=[])


class NewHandoffExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, agent_name, user_prompt, **kwargs):
        self.calls.append(agent_name)
        from core.executor import ExecutorResult
        if len(self.calls) == 1:
            return ExecutorResult(
                status='agent_call',
                content='Please run database reconciliation for this request.',
                ui_feedback=[],
                tool_request={'selected_agent': 'database_manager'},
            )
        return ExecutorResult(status='complete', content=f'done:{agent_name}', ui_feedback=[])


class FixedRouter:
    def route(self, **kwargs):
        return [{
            'type': 'agent_call',
            'selected_agent': 'file_manager',
            'instruction': 'initial instruction',
            'priority': 1,
            '_llm_attachments': kwargs['input_files_payload'],
            '_attached_file_paths': kwargs['input_file_paths'],
        }]


class DuplicateQueueRouter:
    def __init__(self):
        self.calls = []

    def route(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            return [
                {
                    'type': 'agent_call',
                    'selected_agent': 'file_manager',
                    'instruction': 'first task',
                    'priority': 1,
                },
                {
                    'type': 'agent_call',
                    'selected_agent': 'Expense Manager',
                    'instruction': 'queued expense task',
                    'priority': 2,
                },
            ]
        return [
            {
                'type': 'agent_call',
                'selected_agent': 'Expense Manager',
                'instruction': 'rerouted expense task',
                'priority': 1,
            }
        ]


class HintCaptureRouter:
    def __init__(self):
        self.calls = []

    def route(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            return [
                {
                    'type': 'agent_call',
                    'selected_agent': 'file_manager',
                    'instruction': 'first task',
                    'priority': 1,
                }
            ]
        return [
            {
                'type': 'agent_call',
                'selected_agent': 'database_manager',
                'instruction': 'rerouted db task',
                'priority': 1,
            }
        ]


def _fake_png_bytes() -> bytes:
    return bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b'fakepngbytes'


def _fake_jpeg_bytes() -> bytes:
    return bytes([0xFF, 0xD8, 0xFF]) + b'fakejpegbytes'


def test_build_llm_attachments_keeps_image_payload(tmp_path):
    cda = CommonDataArea()
    cda.reset()

    sample = tmp_path / 'receipt.png'
    sample.write_bytes(_fake_png_bytes())

    attachments = build_llm_attachments([sample], cda)
    assert len(attachments) == 1
    assert attachments[0]['kind'] == 'image'
    assert attachments[0]['readable'] is True
    assert attachments[0]['mime_type'] == 'image/png'
    assert attachments[0]['content'] == ''
    assert attachments[0]['data_base64']
    assert attachments[0]['data_url'].startswith('data:image/png;base64,')


def test_build_llm_attachments_truncates(tmp_path):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('llm_attachment_char_limit', 20)
    cda.set_setting('llm_attachment_total_char_limit', 20)

    sample = tmp_path / 'sample.txt'
    sample.write_text('abcdefghijklmnopqrstuvwxyz', encoding='utf-8')

    attachments = build_llm_attachments([sample], cda)
    assert len(attachments) == 1
    assert attachments[0]['truncated'] is True
    assert 'truncated' in attachments[0]['content']


@patch('core.router.list_agents', return_value=[{'name': 'file_manager', 'description': 'Handles files.'}])
def test_router_passes_file_content_to_llm(mock_list_agents, tmp_path):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    llm = RecordingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)

    sample = tmp_path / 'router.txt'
    sample.write_text('router visible text', encoding='utf-8')

    tasks = router.route('route this file', input_files=[sample])

    assert llm.attachments
    assert llm.attachments[0]['content'].startswith('router visible text')
    assert len(tasks) == 1
    assert tasks[0]['selected_agent'] == 'file_manager'
    assert tasks[0]['_llm_attachments'][0]['content'].startswith('router visible text')
    assert tasks[0]['_attached_file_paths'] == [str(sample)]


@patch('core.router.list_agents', return_value=[{'name': 'file_manager', 'description': 'Handles files.'}])
def test_router_renders_identity_placeholders(mock_list_agents):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    cda.set_setting('current_username', 'Bijumon')
    cda.set_setting('current_user_role_name', 'Admin')
    cda.set_setting('current_user_role_id', '7')
    llm = RecordingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)

    tasks = router.route('route this request')

    assert tasks[0]['selected_agent'] == 'file_manager'
    assert llm.prompt is not None
    assert 'USER_ID: 42' in llm.prompt
    assert 'USER_ROLE: Admin' in llm.prompt
    assert 'USER_ROLE_ID: 7' in llm.prompt
    assert 'USERNAME: Bijumon' in llm.prompt


@patch('core.router.list_agents', return_value=[{'name': 'file_manager', 'description': 'Handles files.'}])
def test_router_includes_agent_activity_context(mock_list_agents):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    cda.set_memory('agent_activity', 'Expense Manager: ToolResult : sent monthly report to 4 users')
    llm = RecordingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)

    tasks = router.route('are you sure it was sent to all users?')

    assert tasks[0]['selected_agent'] == 'file_manager'
    assert llm.prompt is not None
    assert 'Agent activity:' in llm.prompt
    assert 'Expense Manager: ToolResult : sent monthly report to 4 users' in llm.prompt


@patch('core.router.list_agents', return_value=[{'name': 'incoming_file_processor', 'description': 'Handles inbound files.'}])
def test_router_passes_image_payload_to_llm(mock_list_agents, tmp_path):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    llm = RecordingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)

    sample = tmp_path / 'photo.jpg'
    sample.write_bytes(_fake_jpeg_bytes())

    tasks = router.route('process attached image', input_files=[sample])

    assert llm.attachments
    assert llm.attachments[0]['kind'] == 'image'
    assert llm.attachments[0]['readable'] is True
    assert llm.attachments[0]['data_url'].startswith('data:image/jpeg;base64,')
    assert len(tasks) == 1
    assert tasks[0]['selected_agent'] == 'file_manager'
    assert tasks[0]['_llm_attachments'][0]['kind'] == 'image'
    assert tasks[0]['_attached_file_paths'] == [str(sample)]


def test_executor_passes_file_content_to_llm(tmp_path):
    cda = CommonDataArea()
    cda.reset()
    llm = RecordingExecutorLLM()
    executor = Executor(cda, llm_client=llm)

    sample = tmp_path / 'agent.txt'
    sample.write_text('agent sees this file', encoding='utf-8')

    result = executor.execute('file_manager', 'use the file', input_files=[str(sample)])

    assert result.status == 'complete'
    assert llm.attachments
    assert llm.attachments[0]['content'].startswith('agent sees this file')


def test_executor_passes_image_payload_to_llm(tmp_path):
    cda = CommonDataArea()
    cda.reset()
    llm = RecordingExecutorLLM()
    executor = Executor(cda, llm_client=llm)

    sample = tmp_path / 'agent.png'
    sample.write_bytes(_fake_png_bytes())

    result = executor.execute('file_manager', 'use the attached image', input_files=[str(sample)])

    assert result.status == 'complete'
    assert llm.attachments
    assert llm.attachments[0]['kind'] == 'image'
    assert llm.attachments[0]['readable'] is True
    assert llm.attachments[0]['data_url'].startswith('data:image/png;base64,')




class GreetingRouterLLM:
    def __init__(self):
        self.attachments = None
        self.last_usage = {}

    def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
        self.attachments = attachments or []
        return json.dumps({
            'type': 'greeting',
            'confidence': 'high',
            'reason': 'No explicit request.',
            'response_to_user': 'Hello'
        })


class ExpenseRouterLLM:
    def __init__(self):
        self.attachments = None
        self.prompt = None
        self.last_usage = {}

    def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
        self.attachments = attachments or []
        self.prompt = prompt
        return json.dumps({
            'type': 'agent_call',
            'selected_agent': 'Expense Manager',
            'instruction': 'Analyze receipt expense details.',
            'confidence': 'high',
            'reason': 'Expense extraction requested.',
            'priority': 1,
        })


class SessionCtxStub:
    def __init__(self, memory):
        self._memory = dict(memory or {})

    def get_memory(self, key, default=None):
        return self._memory.get(key, default)


class HighUsageExecutorLLM:
    def __init__(self):
        self.last_usage = {}

    def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
        self.last_usage = {'tin': 120, 'tout': 40, 'total': 160}
        return json.dumps({
            'plan': {'current_step': 'Done', 'revised_plan': 'Done'},
            'action': {'type': 'complete'},
            'conversation_update': {'content': 'done'},
            'reasoning': {'summary': 'done'},
            'ui_feedback': {'status': 'complete', 'message': 'done'},
        })


@patch('core.router.list_agents', return_value=[{'name': 'incoming_file_processor', 'description': 'Handles inbound files.'}])
def test_router_does_not_override_model_route_for_image_only_prompt(mock_list_agents, tmp_path):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    llm = GreetingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)

    sample = tmp_path / 'just_photo.png'
    sample.write_bytes(_fake_png_bytes())

    tasks = router.route('Attached 1 document(s).', input_files=[sample])

    assert llm.attachments
    assert llm.attachments[0]['kind'] == 'image'
    assert len(tasks) == 1
    assert tasks[0]['type'] == 'greeting'

def test_controller_preserves_attachments_across_handoff(tmp_path):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)

    sample = tmp_path / 'handoff.txt'
    sample.write_text('handoff payload', encoding='utf-8')
    attachments = build_llm_attachments([sample], cda)

    router = FixedRouter()
    executor = HandoffExecutor()
    controller = Controller(cda, router=router, executor=executor)

    def _route_override(message, input_files=None, tool_output=None, chat_history='', interface_type='UI'):
        return router.route(
            user_prompt=message,
            input_files=input_files,
            input_files_payload=attachments,
            input_file_paths=[str(sample)],
        )

    controller._route = _route_override
    response = controller.handle_user_message('start', files=[str(sample)], interface='UI')

    assert response.status == 'complete'
    assert len(executor.calls) == 2
    assert executor.calls[0]['llm_attachments'][0]['content'].startswith('handoff payload')
    assert executor.calls[1]['llm_attachments'][0]['content'].startswith('handoff payload')
    assert executor.calls[1]['input_files'] == [str(sample)]


def test_controller_ignores_agent_handoff_when_target_already_in_queue():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)

    router = DuplicateQueueRouter()
    executor = DuplicateHandoffExecutor()
    controller = Controller(cda, router=router, executor=executor)

    response = controller.handle_user_message('start', interface='UI')

    assert response.status == 'complete'
    assert executor.calls == ['file_manager', 'Expense Manager']
    assert len(router.calls) == 1


def test_controller_passes_agent_hint_to_router_on_non_duplicate_handoff():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)

    router = HintCaptureRouter()
    executor = NewHandoffExecutor()
    controller = Controller(cda, router=router, executor=executor)

    response = controller.handle_user_message('start', interface='UI')

    assert response.status == 'complete'
    assert len(router.calls) == 2
    handoff_payload = json.loads(router.calls[1].get('tool_output', '{}'))
    assert handoff_payload.get('event') == 'agent_requested_handoff'
    assert handoff_payload.get('requested_agent') == 'database_manager'
    assert 'agent_hint' in handoff_payload
    assert 'database_manager' in handoff_payload.get('agent_hint', '').lower()
    assert 'database_manager' in str(cda.get_memory('interaction_agent_hint', '')).lower()


@patch(
    'core.router.list_agents',
    return_value=[
        {'name': 'incoming_file_processor', 'description': 'Handles inbound files.'},
        {'name': 'Expense Manager', 'description': 'Handles expenses.'},
        {'name': 'rag_gen', 'description': 'RAG agent.'},
    ],
)
def test_router_does_not_reinject_incoming_after_file_processor_handoff(mock_list_agents, tmp_path):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    llm = ExpenseRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)

    sample = tmp_path / 'receipt.pdf'
    sample.write_text('receipt text', encoding='utf-8')
    handoff_hint = json.dumps(
        {
            'event': 'agent_requested_handoff',
            'source_agent': 'incoming_file_processor',
            'requested_agent': 'rag_gen',
            'instruction': 'Continue downstream processing.',
        }
    )

    tasks = router.route(
        'spend on Openrouter AI application experiments',
        input_files=[sample],
        tool_output=handoff_hint,
    )

    assert tasks
    assert tasks[0]['selected_agent'] == 'Expense Manager'
    assert all(
        t.get('selected_agent') != 'incoming_file_processor'
        for t in tasks
        if isinstance(t, dict) and t.get('type') == 'agent_call'
    )


@patch('core.router.list_agents', return_value=[{'name': 'file_manager', 'description': 'Handles files.'}])
def test_router_uses_session_agent_activity_context(mock_list_agents):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    llm = RecordingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)
    session_ctx = SessionCtxStub({'agent_activity': 'incoming_file_processor: ToolResult : file already ingested'})

    router.route('what happened', session_ctx=session_ctx)

    assert llm.prompt is not None
    assert 'incoming_file_processor: ToolResult : file already ingested' in llm.prompt


@patch('core.router.list_agents', return_value=[{'name': 'file_manager', 'description': 'Handles files.'}])
def test_router_includes_agent_hint_context(mock_list_agents):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('current_user_id', '42')
    llm = RecordingRouterLLM()
    cda.set_runtime('llm_client', llm)
    router = Router(cda)
    handoff_hint = json.dumps(
        {
            'event': 'agent_requested_handoff',
            'source_agent': 'incoming_file_processor',
            'requested_agent': 'Expense Manager',
            'agent_hint': 'incoming_file_processor suggests Expense Manager for expense posting',
        }
    )

    router.route('post this receipt', tool_output=handoff_hint)

    assert llm.prompt is not None
    assert 'Agent hint from previous turn:' in llm.prompt
    assert 'incoming_file_processor suggests Expense Manager for expense posting' in llm.prompt


def test_executor_stops_when_interaction_token_budget_exceeded():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('interaction_max_tokens', 100)
    cda.set_memory('interaction_token_usage', {'total': 0, 'router': 0, 'executor': 0})
    llm = HighUsageExecutorLLM()
    executor = Executor(cda, llm_client=llm)

    try:
        executor.execute('file_manager', 'check budget limit')
    except ExecutorError as exc:
        assert 'token budget' in str(exc).lower()
    else:
        raise AssertionError('Expected ExecutorError due to interaction token budget limit.')
