import sys
sys.path.insert(0, r"d:\Works\GenericAgent\DesktopAgenticSystem")

from core.common_data_area import CommonDataArea
from core.executor import Executor

cda = CommonDataArea()

# Create a mock callback
called_statuses = []
def mock_status_handler(msg: str):
    if msg:
        called_statuses.append(msg)
    print(f"UI STATUS UPDATE: {msg}")

cda.set_runtime('tool_status_handler', mock_status_handler)

# Set up mock executor 
# We don't really want to do a full LLM call, but we can see if the first status logs
try:
    executor = Executor(cda)
    # Give it an agent name
    # We expect it to at least try to load the agent and then say "Preparing prompt context..."
    executor.execute("attendance_manager", "test")
except Exception as e:
    # It will probably fail because we aren't setting up a full env, but we just want to see if the status was called
    pass

print(f"\nCollected Statuses: {called_statuses}")
if len(called_statuses) > 0 and called_statuses[0] == "Preparing prompt context...":
    print("Verification SUCCESS")
else:
    print("Verification FAILED")
