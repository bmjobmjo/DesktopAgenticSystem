"""Deterministic mock LLM client for tests."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List
from pathlib import Path

from llm.base_client import BaseLLMClient
from core.llm_attachments import format_attachments_for_prompt


def _get_db_path() -> str:
    # Use the same path as core/db_schema.py
    return r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db'


class MockLLMClient(BaseLLMClient):
    def __init__(self):
        self.last_usage = {}

    def generate(
        self, 
        prompt: str, 
        agent_name: str = "Assistant", 
        user_prompt: str = "",
        attachments: List[Dict[str, Any]] | None = None,
    ) -> str:
        self.last_attachments = attachments or []
        prompt_with_attachments = prompt
        attachment_block = format_attachments_for_prompt(attachments)
        if attachment_block:
            prompt_with_attachments = f"{prompt}\n\n{attachment_block}"
        response_text = ""
        if 'ROLE: ROUTER' in prompt_with_attachments:
            response_text = json.dumps(
                {
                    'type': 'continue',
                    'selected_agent': 'file_manager',
                    'confidence': 'high',
                    'reason': 'File-related request detected.'
                }
            )
        elif 'Agent Name:\nFileManager Agent' in prompt_with_attachments or 'FileManager Agent' in prompt_with_attachments:
            default_dir = _extract_default_directory(prompt_with_attachments)
            tool_data_present = _has_tool_data(prompt_with_attachments)
            if not tool_data_present:
                payload = {
                    'plan': {
                        'current_step': 'List files in default directory',
                        'revised_plan': 'Use list_directory tool'
                    },
                    'action': {
                        'type': 'tool_call',
                        'tool_request': {
                            'tool_name': 'list_directory',
                            'parameters': {'directory_path': default_dir}
                        }
                    },
                    'conversation_update': {'content': ''},
                    'reasoning': {'summary': 'Need directory contents.'},
                    'ui_feedback': {
                        'status': 'working',
                        'message': 'Listing files',
                        'progress_hint': 'Calling list_directory'
                    }
                }
            else:
                payload = {
                    'plan': {
                        'current_step': 'Summarize results',
                        'revised_plan': 'Complete response'
                    },
                    'action': {'type': 'complete', 'tool_request': {'tool_name': '', 'parameters': {}}},
                    'conversation_update': {
                        'content': 'Here are the files:\n' + tool_data_present
                    },
                    'reasoning': {'summary': 'Tool results received.'},
                    'ui_feedback': {
                        'status': 'complete',
                        'message': 'Done',
                        'progress_hint': 'Completed'
                    }
                }
            response_text = json.dumps(payload)
        elif 'AttendanceManager Agent' in prompt_with_attachments:
             payload = {
              "plan": {
                 "original_plan": ["Clock in user"],
                 "current_step": "Clock in user",
                 "revised_plan": "Task Completed"
              },
              "action": {
                "type": "tool_call",
                "tool_request": {
                   "tool_name": "execute_sql",
                   "parameters": {
                      "queries": ["INSERT INTO Attendance (user_id, check_in_time) VALUES (101, datetime('now'))"]
                   }
                }
              },
              "conversation_update": {
                  "content": "Clocking you in..."
              },
              "reasoning": {
                  "summary": "User requested check-in."
              },
              "ui_feedback": {
                  "status": "working",
                  "message": "Clocking in...",
                  "progress_hint": "Step 1"
              }
            }
             # Basic state toggling for mock (if tool data present, complete)
             tool_data_present = _has_tool_data(prompt_with_attachments)
             if tool_data_present:
                 payload['action'] = {'type': 'complete'}
                 payload['conversation_update']['content'] = "Attendance marked successfully."
                 payload['ui_feedback']['status'] = 'complete'
             
             response_text = json.dumps(payload)
        else:
            response_text = json.dumps({'message': 'unrecognized prompt'})

        # Log to DB
        self.last_usage = {'tin': len(prompt_with_attachments) // 4, 'tout': len(response_text) // 4, 'total': (len(prompt_with_attachments) + len(response_text)) // 4}
        self._log_usage(agent_name, user_prompt, prompt_with_attachments, response_text)
        return response_text

    def _log_usage(self, agent_name: str, user_prompt: str, prompt: str, response: str):
        # Simulated tokens
        tin = len(prompt) // 4
        tout = len(response) // 4
        total = tin + tout
        
        try:
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO LLMUsage (user_prompt, agent_name, prompt, response, token_in, token_out, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_prompt, agent_name, prompt, response, tin, tout, total))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to log LLM usage: {e}")


def _extract_default_directory(prompt: str) -> str:
    lines = prompt.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == 'Default Working Directory:':
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return ''


def _has_tool_data(prompt: str) -> str:
    lines = prompt.splitlines()
    data_lines = []
    capture = False
    for line in lines:
        if line.strip() == 'Tool Results:':
            capture = True
            continue
        if capture:
            if line.strip() == 'User Inputs:':
                break
            data_lines.append(line)
    return '\n'.join(data_lines).strip()
