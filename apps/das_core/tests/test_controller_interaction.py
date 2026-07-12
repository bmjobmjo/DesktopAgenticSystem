
import json
from unittest.mock import MagicMock
from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.router import Router
from core.executor import Executor

class MockRouter(Router):
    def __init__(self, response_type, content):
        super().__init__()
        self.response = {
            'type': response_type,
            'confidence': 'high',
            'reason': 'test',
        }
        if response_type == 'continue':
            self.response['selected_agent'] = 'file_manager'
        else:
            self.response['response_to_user'] = content

    def route(self, user_prompt, chat_history='', max_retries=2):
        return self.response

def test_controller_handles_greeting():
    cda = CommonDataArea()
    cda.reset()
    
    # Router returns greeting
    router = MockRouter('greeting', 'Hello there!')
    executor = MagicMock(spec=Executor)
    
    controller = Controller(cda, router, executor)
    response = controller.handle_user_message('Hi')
    
    assert response.status == 'complete'
    assert response.content == 'Hello there!'
    # Executor should NOT be called
    executor.execute.assert_not_called()

def test_controller_handles_clarification():
    cda = CommonDataArea()
    cda.reset()
    
    # Router returns request_user_input
    router = MockRouter('request_user_input', 'What do you mean?')
    executor = MagicMock(spec=Executor)
    
    controller = Controller(cda, router, executor)
    response = controller.handle_user_message('ambiguous command')
    
    assert response.status == 'request_user_input'
    assert response.content == 'What do you mean?'
    # Executor should NOT be called
    executor.execute.assert_not_called()
from unittest.mock import MagicMock

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.executor import Executor, ExecutorResult
from core.router import Router


class ResumeSafeRouter(Router):
    def __init__(self):
        super().__init__()
        self.calls = []

    def route(self, user_prompt, chat_history='', max_retries=2, **kwargs):
        self.calls.append(user_prompt)
        return {
            'type': 'greeting',
            'confidence': 'high',
            'reason': 'test',
            'response_to_user': f'Rerouted: {user_prompt}',
        }


def test_controller_reroutes_after_router_request_user_input_reply():
    cda = CommonDataArea()
    cda.reset()

    router = ResumeSafeRouter()
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)
    controller.awaiting_user_input = True
    controller.current_task = {
        'type': 'request_user_input',
        'response_to_user': 'Please clarify.',
    }

    response = controller.handle_user_message('Here is my clarification')

    assert response.status == 'complete'
    assert response.content == 'Rerouted: Here is my clarification'
    executor.execute.assert_not_called()
    assert router.calls == ['Here is my clarification']


def test_controller_retry_phrase_reuses_previous_user_intent():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("session_engine_enabled", False)
    cda.set_memory(
        "chat_history",
        (
            "User[UserID:1][Interface:WEB]: now list my remianing tasks\n"
            "Assistant[UserID:1][Interface:WEB]: System Error: executor_response missing keys"
        ),
    )

    router = ResumeSafeRouter()
    executor = MagicMock(spec=Executor)
    controller = Controller(cda, router, executor)

    response = controller.handle_user_message("try again", interface="WEB", user_id="1")

    assert response.status == "complete"
    assert response.content == "Rerouted: now list my remianing tasks"
    assert router.calls == ["now list my remianing tasks"]
    executor.execute.assert_not_called()


class PassthroughRouter:
    def route(self, user_prompt, chat_history='', max_retries=2, **kwargs):
        return {
            'type': 'agent_call',
            'selected_agent': 'file_manager',
            'instruction': 'Rewritten instruction from router',
            'parameters': {'list_type': 'pending'},
            'priority': 1,
        }


class CaptureExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, agent_name, user_prompt, **kwargs):
        self.calls.append(
            {
                'agent_name': agent_name,
                'user_prompt': user_prompt,
                'interface_type': kwargs.get('interface_type'),
            }
        )
        return ExecutorResult(status='complete', content='ok', ui_feedback=[])


class ResumeThenCompleteExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ExecutorResult(
                status='request_user_input',
                content='Please confirm deletion.',
                ui_feedback=[],
            )
        return ExecutorResult(
            status='complete',
            content='Employee deleted successfully.',
            ui_feedback=[],
        )


def test_router_handoff_preserves_original_user_input_and_whatsapp_interface():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('session_engine_enabled', False)

    router = PassthroughRouter()
    executor = CaptureExecutor()
    controller = Controller(cda, router=router, executor=executor)

    response = controller.handle_user_message('List pending tasks from yesterday', interface='WhatsApp')

    assert response.status == 'complete'
    assert len(executor.calls) == 1
    assert executor.calls[0]['agent_name'] == 'file_manager'
    assert executor.calls[0]['user_prompt'] == 'List pending tasks from yesterday'
    assert '[ROUTER_PARAMETERS]' not in executor.calls[0]['user_prompt']
    assert executor.calls[0]['interface_type'] == 'WHATSAPP'


def test_controller_preserves_completion_message_after_resumed_agent_input():
    cda = CommonDataArea()
    cda.reset()

    router = PassthroughRouter()
    executor = ResumeThenCompleteExecutor()
    controller = Controller(cda, router=router, executor=executor)

    first = controller.handle_user_message('delete employee 2')
    assert first.status == 'request_user_input'
    assert first.content == 'Please confirm deletion.'

    second = controller.handle_user_message('yes please')
    assert second.status == 'complete'
    assert second.content == 'Employee deleted successfully.'
