"""Router response validator."""

from __future__ import annotations

from typing import Dict, List, Any

from validation.json_schema import SchemaError, require_dict, require_enum, require_keys, require_str


def validate_router_response(data: Any) -> List[Dict]:
    if isinstance(data, dict):
        data = [data]
    
    if not isinstance(data, list):
        raise SchemaError("Router response must be a list of tasks or a single task object.")

    for item in data:
        validate_single_task(item)

    return data

def validate_single_task(data: Dict) -> None:
    require_dict(data, 'task_item')
    require_keys(data, ['type', 'confidence', 'reason'], 'task_item')
    require_enum(data.get('type'), 'type', ['greeting', 'request_user_input', 'continue', 'agent_call', 'tool_call'])
    require_enum(data.get('confidence'), 'confidence', ['low', 'medium', 'high'])
    require_str(data.get('reason'), 'reason')

    route_type = data.get('type')
    if route_type in ('continue', 'agent_call'):
        require_keys(data, ['selected_agent'], 'task_item')
        require_str(data.get('selected_agent'), 'selected_agent')
        # Optional priority
        if 'priority' in data:
            if not isinstance(data['priority'], int):
                 raise SchemaError("Priority must be an integer.")
                 
    elif route_type == 'tool_call':
        require_keys(data, ['tool_name', 'parameters'], 'task_item')
        require_str(data.get('tool_name'), 'tool_name')
        require_dict(data.get('parameters'), 'parameters')

    elif route_type in ('greeting', 'request_user_input'):
        require_keys(data, ['response_to_user'], 'task_item')
        require_str(data.get('response_to_user'), 'response_to_user')


__all__ = ['validate_router_response', 'SchemaError']
