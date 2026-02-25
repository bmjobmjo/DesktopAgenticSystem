
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.getcwd())

from tools.tool_registry import list_tools, TOOLS

print("All tools in TOOLS keys:", list(TOOLS.keys()))
print("All tools from list_tools():", list(list_tools().keys()))

if 'file_embedding_tool' in TOOLS:
    print("SUCCESS: file_embedding_tool found in TOOLS")
else:
    print("FAILURE: file_embedding_tool NOT found in TOOLS")

if 'ingest_file' in TOOLS:
    print("ingest_file found")
else:
    print("ingest_file NOT found")
