import json
import pytest

from llm.mock_client import MockLLMClient
from llm.response_validator import parse_json, InvalidJSONError


def test_mock_router_json():
    client = MockLLMClient()
    prompt = 'ROLE: ROUTER\nUser: list files'
    output = client.generate(prompt)
    data = parse_json(output)
    assert data['selected_agent'] == 'file_manager'


def test_validator_rejects_invalid_json():
    with pytest.raises(InvalidJSONError):
        parse_json('not json')


def test_mock_file_manager_tool_call_then_complete():
    client = MockLLMClient()
    # Prompt matching the template structure expected by MockLLMClient
    prompt = (
        "Agent Name:\nFileManager Agent\n"
        "Default Working Directory:\nC:/data\n"
        "Tool Results:\n\n"
        "User Inputs:\n"
    )
    output = client.generate(prompt)
    data = json.loads(output)
    assert data['action']['type'] == 'tool_call'
    assert data['action']['tool_request']['parameters']['directory_path'] == 'C:/data'

    prompt2 = (
        "Agent Name:\nFileManager Agent\n"
        "Default Working Directory:\nC:/data\n"
        "Tool Results:\nfile1.txt\n"
        "User Inputs:\n"
    )
    output2 = client.generate(prompt2)
    data2 = json.loads(output2)
    assert data2['action']['type'] == 'complete'
    assert 'file1.txt' in data2['conversation_update']['content']
