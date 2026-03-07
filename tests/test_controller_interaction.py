
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
