"""Executor response validator."""

from __future__ import annotations

import json
from typing import Dict

from validation.json_schema import SchemaError, require_dict, require_enum, require_keys, require_str


_ACTION_TYPES = ['tool_call', 'request_user_input', 'continue', 'agent_call', 'complete']


def _validate_plan(plan: Dict) -> None:
    require_dict(plan, 'plan')
    
    # Relaxed validation to accommodate both old and new plan structures
    # like {"steps": [...], "current_step": 1}.
    if 'current_step' not in plan:
        plan['current_step'] = ""
    else:
        val = plan['current_step']
        if val is None:
            plan['current_step'] = ""
        elif isinstance(val, list):
            plan['current_step'] = "\n".join(str(s) for s in val)
        else:
            plan['current_step'] = str(val)

    if 'revised_plan' in plan:
        val = plan['revised_plan']
        if val is None:
            plan['revised_plan'] = ""
        elif isinstance(val, list):
            plan['revised_plan'] = "\n".join(str(s) for s in val)
        else:
            plan['revised_plan'] = str(val)


def _validate_action(action: Dict) -> None:
    # Normalize common LLM deviations before strict validation.
    if action is None:
        action = {'type': 'complete'}
    elif isinstance(action, str):
        action = {'type': action}

    require_dict(action, 'action')
    require_keys(action, ['type'], 'action')
    action_type_raw = str(action.get('type', '')).strip().lower()
    alias_map = {
        'none': 'complete',
        'response': 'complete',
        'final': 'complete',
        'done': 'complete',
        'finish': 'complete',
        'completed': 'complete',
        'tool': 'tool_call',
        'ask_user': 'request_user_input',
    }
    action['type'] = alias_map.get(action_type_raw, action_type_raw)
    action_type = require_enum(action.get('type'), 'action.type', _ACTION_TYPES)

    if action_type == 'tool_call':
        require_keys(action, ['tool_request'], 'action')
        tool_request = require_dict(action.get('tool_request'), 'action.tool_request')
        require_keys(tool_request, ['tool_name', 'parameters'], 'action.tool_request')
        require_str(tool_request.get('tool_name'), 'action.tool_request.tool_name')
        require_dict(tool_request.get('parameters'), 'action.tool_request.parameters')
    else:
        # tool_request is optional for other action types
        if 'tool_request' in action:
            tr_value = action.get('tool_request')
            if tr_value is not None:
                tool_request = require_dict(tr_value, 'action.tool_request')
                if 'tool_name' in tool_request:
                    require_str(tool_request.get('tool_name'), 'action.tool_request.tool_name')
                if 'parameters' in tool_request:
                    require_dict(tool_request.get('parameters'), 'action.tool_request.parameters')

    # Add flexible tracking for explicit user outputs
    if 'UserMessageType' in action:
        require_str(action.get('UserMessageType'), 'action.UserMessageType')
    if 'UserMessage' in action:
        require_str(action.get('UserMessage'), 'action.UserMessage')


def _validate_conversation_update(update: Dict | str) -> None:
    if isinstance(update, str):
        update = {'content': update}
        
    require_dict(update, 'conversation_update')
    require_keys(update, ['content'], 'conversation_update')
    require_str(update.get('content'), 'conversation_update.content')
    return update


def _validate_reasoning(reasoning: Dict) -> None:
    require_dict(reasoning, 'reasoning')
    require_keys(reasoning, ['summary'], 'reasoning')
    require_str(reasoning.get('summary'), 'reasoning.summary')


def _validate_ui_feedback(ui_feedback: Dict) -> None:
    require_dict(ui_feedback, 'ui_feedback')
    
    # Default missing fields logic
    if 'status' not in ui_feedback or ui_feedback.get('status') is None:
        ui_feedback['status'] = 'info'
    if 'message' not in ui_feedback or ui_feedback.get('message') is None:
        ui_feedback['message'] = ''
    if 'progress_hint' not in ui_feedback or ui_feedback.get('progress_hint') is None:
        ui_feedback['progress_hint'] = ''

    require_str(ui_feedback.get('status'), 'ui_feedback.status')
    require_str(ui_feedback.get('message'), 'ui_feedback.message')
    require_str(ui_feedback.get('progress_hint'), 'ui_feedback.progress_hint')


def validate_executor_response(data: Dict) -> Dict:
    try:
        data = require_dict(data, 'executor_response')
        require_keys(
            data,
            ['plan', 'action', 'conversation_update', 'reasoning', 'ui_feedback'],
            'executor_response'
        )
        _validate_plan(data.get('plan'))
        _validate_action(data.get('action'))
        data['conversation_update'] = _validate_conversation_update(data.get('conversation_update'))
        _validate_reasoning(data.get('reasoning'))
        _validate_ui_feedback(data.get('ui_feedback'))
        
        # Validate top-level UserMessage formats if not nested in action
        if 'UserMessageType' in data:
            require_str(data.get('UserMessageType'), 'UserMessageType')
        if 'UserMessage' in data:
            require_str(data.get('UserMessage'), 'UserMessage')
            
        return data
    except SchemaError as e:
        print(f"[DEBUG] Validation Error: {e}")
        print(f"[DEBUG] Raw Data: {json.dumps(data, indent=2)}")
        raise


__all__ = ['validate_executor_response', 'SchemaError']
