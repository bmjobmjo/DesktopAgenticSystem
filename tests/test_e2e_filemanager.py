import os
import tempfile

from core.common_data_area import CommonDataArea
from core.controller import Controller
from llm.mock_client import MockLLMClient


def test_e2e_filemanager_list_directory():
    cda = CommonDataArea()
    cda.reset()
    cda.set_runtime('llm_client', MockLLMClient())

    with tempfile.TemporaryDirectory() as tmpdir:
        cda.set_setting('accessible_directories', [tmpdir])
        cda.set_setting('default_directory', tmpdir)
        with open(os.path.join(tmpdir, 'file1.txt'), 'w', encoding='utf-8') as f:
            f.write('data')

        controller = Controller(cda=cda)
        response = controller.handle_user_message('List files in the default directory')

        assert response.status == 'complete'
        assert 'file1.txt' in response.content
