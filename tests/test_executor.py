import os
import sqlite3
import tempfile

from core.common_data_area import CommonDataArea
from core.executor import Executor
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
