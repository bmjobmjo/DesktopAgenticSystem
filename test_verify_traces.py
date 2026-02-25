import sys
sys.path.insert(0, r"d:\Works\GenericAgent\DesktopAgenticSystem")

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.router import Router
from core.executor import Executor
from execution_logger import ExecutionLogger

cda = CommonDataArea()

# Use Mock Client
from llm.mock_client import MockLLMClient
cda.set_runtime('llm_client', MockLLMClient())

traces = []
def _mock_trace(event_type, payload):
    traces.append((event_type, payload))

cda.set_runtime('executor_trace_handler', _mock_trace)

controller = Controller(cda)

print("Sending mock request...")
controller.handle_user_message("Test router and executor")

print("\n--- CAUGHT TRACES ---")
for evt, payload in traces:
    print(f"\n[EVENT] {evt}")
    for k, v in payload.items():
        if k in ('prompt', 'response', 'message', 'parameters', 'result'):
            print(f"  {k}: {str(v)[:50]}...")
        else:
            print(f"  {k}: {v}")

print("\nVerification Complete.")
