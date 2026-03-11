import pytest

from validation.router_validator import validate_router_response, SchemaError as RouterSchemaError
from validation.executor_validator import validate_executor_response, SchemaError as ExecutorSchemaError


def test_router_validator_accepts_valid():
    payload = {
        'type': 'agent_call',
        'selected_agent': 'file_manager',
        'confidence': 'high',
        'reason': 'files'
    }
    # Router validation returns a list of items
    assert validate_router_response(payload) == [payload]


def test_router_validator_rejects_invalid():
    with pytest.raises(RouterSchemaError):
        validate_router_response({'type': 'invalid', 'selected_agent': 'x', 'confidence': 'bad', 'reason': 'y'})


def test_executor_validator_accepts_valid():
    payload = {
        'plan': {'current_step': 'step', 'revised_plan': 'plan'},
        'action': {
            'type': 'tool_call',
            'tool_request': {'tool_name': 'list_directory', 'parameters': {}}
        },
        'conversation_update': {'content': ''},
        'reasoning': {'summary': 'ok'},
        'ui_feedback': {'status': 'working', 'message': 'msg', 'progress_hint': 'hint'}
    }
    assert validate_executor_response(payload) == payload


def test_executor_validator_rejects_missing_keys():
    with pytest.raises(ExecutorSchemaError):
        validate_executor_response({'action': {'type': 'complete'}})

def test_executor_validator_lifts_misnested_top_level_fields():
    payload = {
        'plan': {'current_step': 'step', 'revised_plan': 'plan'},
        'action': {
            'type': 'tool_call',
            'tool_request': {'tool_name': 'export_file', 'parameters': {'format': 'pdf'}},
            'conversation_update': {'content': 'Exporting file.'},
            'reasoning': {'summary': 'The tool call should proceed.'},
            'ui_feedback': {'status': 'working', 'message': 'Exporting', 'progress_hint': ''},
        },
    }

    validated = validate_executor_response(payload)

    assert validated['conversation_update']['content'] == 'Exporting file.'
    assert validated['reasoning']['summary'] == 'The tool call should proceed.'
    assert validated['ui_feedback']['message'] == 'Exporting'
    assert 'conversation_update' not in validated['action']
    assert 'reasoning' not in validated['action']
    assert 'ui_feedback' not in validated['action']

