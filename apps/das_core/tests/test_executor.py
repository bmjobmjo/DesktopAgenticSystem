import os
import sqlite3
import tempfile

import pytest

from core.common_data_area import CommonDataArea
from core.executor import Executor, ExecutorError
from core.db_schema import init_db
from llm.mock_client import MockLLMClient


def test_executor_tool_call_then_complete():
    cda = CommonDataArea()
    cda.reset()
    cda.set_runtime('llm_client', MockLLMClient())

    with tempfile.TemporaryDirectory() as tmpdir:
        cda.set_setting('accessible_directories', [tmpdir])
        cda.set_setting('default_directory', tmpdir)
        # create a file to list
        with open(os.path.join(tmpdir, 'a.txt'), 'w', encoding='utf-8') as f:
            f.write('hello')

        executor = Executor(cda)
        result = executor.execute('file_manager', 'List files')

        assert result.status == 'complete'
        assert 'Here are the files' in result.content
        tool_data = cda.get_memory('tool_data')
        assert tool_data['success'] is True
        assert 'a.txt' in tool_data['data']['entries']


def test_executor_exposes_no_tools_when_agent_has_no_assignments():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_backend.db')
        cda.set_setting('sqlite_db_path', db_path)
        init_db()

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO Agents (name, description, prompt_content, is_active, version) VALUES (?, ?, ?, ?, ?)",
                ('NoToolAgent', 'test', '', 1, 1),
            )
            conn.commit()
        finally:
            conn.close()

        executor = Executor(cda)
        executor._init_execution_context('NoToolAgent', 'hello')

        assert executor.execution_context['TOOL_LIST'] == ''

def test_executor_builds_tool_list_from_toollist_table():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_backend.db')
        cda.set_setting('sqlite_db_path', db_path)
        init_db()

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO Agents (name, description, prompt_content, is_active, version) VALUES (?, ?, ?, ?, ?)",
                ('DbToolAgent', 'test', '', 1, 1),
            )
            agent_id = cur.lastrowid
            cur.execute(
                "INSERT OR REPLACE INTO ToolList (name, description, input_schema, output_schema, version) VALUES (?, ?, ?, ?, ?)",
                ('execute_sql', 'DB description', '{"parameters": ["queries"]}', 'x', '1.0'),
            )
            cur.execute(
                "INSERT INTO AgentTools (agent_id, tool_name) VALUES (?, ?)",
                (agent_id, 'execute_sql'),
            )
            conn.commit()
        finally:
            conn.close()

        executor = Executor(cda)
        executor._init_execution_context('DbToolAgent', 'hello')

        assert 'DB description' in executor.execution_context['TOOL_LIST']
        assert '- execute_sql' in executor.execution_context['TOOL_LIST']


def test_executor_stops_on_repeated_recoverable_tool_errors(monkeypatch):
    class RecoverableToolErrorLLM:
        def __init__(self):
            self.last_usage = {'tin': 10, 'tout': 10, 'total': 20}

        def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
            return (
                '{"plan":{"current_step":"try tool","revised_plan":"retry"},'
                '"action":{"type":"tool_call","tool_request":{"tool_name":"execute_sql","parameters":{"queries":["SELECT 1"]}}},'
                '"conversation_update":{"content":"retrying"},'
                '"reasoning":{"summary":"tool failed"},'
                '"ui_feedback":{"status":"info","message":"retry"}}'
            )

    def _fake_call_tool(tool_name, parameters, status_callback=None):
        return {'success': False, 'error': 'no such table: MissingTable'}

    monkeypatch.setattr('core.executor.call_tool', _fake_call_tool)

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('executor_max_recoverable_tool_error_loops', 2)
    executor = Executor(cda, llm_client=RecoverableToolErrorLLM())

    with pytest.raises(ExecutorError, match='repeated recoverable tool errors'):
        executor.execute('file_manager', 'run sql')


def test_executor_stops_on_repeated_identical_nonterminal_actions():
    class RepeatContinueLLM:
        def __init__(self):
            self.last_usage = {'tin': 10, 'tout': 10, 'total': 20}

        def generate(self, prompt, agent_name='Assistant', user_prompt='', attachments=None):
            return (
                '{"plan":{"current_step":"think","revised_plan":"continue"},'
                '"action":{"type":"continue"},'
                '"conversation_update":{"content":"still working"},'
                '"reasoning":{"summary":"continue loop"},'
                '"ui_feedback":{"status":"info","message":"loop"}}'
            )

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('executor_max_repeated_nonterminal_loops', 3)
    executor = Executor(cda, llm_client=RepeatContinueLLM())

    with pytest.raises(ExecutorError, match='repeated identical non-terminal action plan'):
        executor.execute('file_manager', 'loop check', max_loops=20)
