from core.common_data_area import CommonDataArea
from core.router import Router
from llm.mock_client import MockLLMClient


def test_router_selects_file_manager():
    cda = CommonDataArea()
    cda.reset()
    cda.set_runtime('llm_client', MockLLMClient())

    router = Router(cda)
    result = router.route('List files in the directory')
    assert result['selected_agent'] == 'file_manager'
