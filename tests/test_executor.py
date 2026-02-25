import os
import tempfile

from core.common_data_area import CommonDataArea
from core.executor import Executor
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
