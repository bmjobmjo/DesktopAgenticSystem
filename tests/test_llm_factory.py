from core.common_data_area import CommonDataArea
from llm.factory import get_llm_client
from llm.groq_client import GroqClient
from llm.mock_client import MockLLMClient


def test_factory_returns_groq_client_for_groq_provider():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('llm_provider', 'groq')

    client = get_llm_client(cda)

    assert isinstance(client, GroqClient)


def test_factory_returns_mock_for_unknown_provider():
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting('llm_provider', 'unknown-provider')

    client = get_llm_client(cda)

    assert isinstance(client, MockLLMClient)
