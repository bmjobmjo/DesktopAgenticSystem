import sys
import os

sys.path.insert(0, r"d:\Works\GenericAgent\DesktopAgenticSystem")

from core.common_data_area import CommonDataArea
from llm.factory import get_llm_client
from llm.openrouter_client import OpenRouterClient

cda = CommonDataArea()
cda.set_setting('llm_provider', 'openrouter')
cda.set_setting('openrouter_model', 'stepfun/step-3.5-flash')
cda.set_setting('openrouter_api_key', 'test_key')

client = get_llm_client(cda)

print(f"Client type: {type(client)}")
if isinstance(client, OpenRouterClient):
    print("Factory integration successful.")
else:
    print("Factory integration failed.")
