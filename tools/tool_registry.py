"""Tool registry and dispatcher."""

from __future__ import annotations

from typing import Callable, Dict

import os
import importlib
import inspect
from typing import Callable, Dict
import sys
from pathlib import Path

# Base Tools Directory
TOOLS_DIR = Path(__file__).parent

ToolFunc = Callable[..., Dict]
TOOLS: Dict[str, ToolFunc] = {}

def _discover_tools():
    """Dynamically discover tools in the tools directory."""
    global TOOLS
    TOOLS.clear()
    
    # Add tools root to sys.path if needed, though usually covered by project root
    if str(TOOLS_DIR) not in sys.path:
         sys.path.append(str(TOOLS_DIR))

    for root, _, files in os.walk(TOOLS_DIR):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                module_path = Path(root) / file
                # Calculate relative module name: tools.filesystem.list_directory
                try:
                    rel_path = module_path.relative_to(TOOLS_DIR.parent)
                    module_name = str(rel_path).replace(os.sep, ".")[:-3]
                    
                    module = importlib.import_module(module_name)
                    
                    # 1. Check for filename match (Convention)
                    tool_name = file[:-3]
                    if hasattr(module, tool_name):
                        func = getattr(module, tool_name)
                        if callable(func):
                            TOOLS[tool_name] = func
                            continue
                            
                    # 2. Check for public functions defined in this module
                    for name, obj in inspect.getmembers(module):
                        if inspect.isfunction(obj) and obj.__module__ == module.__name__:
                            if not name.startswith("_"):
                                # Avoid helpers if possible, or maybe we accept all?
                                # For sqlite_tools.py, it likely has execute_sql. 
                                # Let's add them. 
                                # Potential collision if multiple files define same function?
                                TOOLS[name] = obj
                                
                except Exception as e:
                    print(f"Failed to load tool from {file} (module: {module_name if 'module_name' in locals() else 'N/A'}): {e}")
                    import traceback
                    traceback.print_exc()

    # Aliases for better UX or backward compatibility
    if 'ingest_file' in TOOLS:
        TOOLS['file_ingestion'] = TOOLS['ingest_file']
        TOOLS['file_embedding_tool'] = TOOLS['ingest_file']

def list_tools() -> Dict[str, ToolFunc]:
    if not TOOLS:
        _discover_tools()
    return dict(TOOLS)


def get_tool(name: str) -> ToolFunc | None:
    if name not in TOOLS:
        _discover_tools()
    return TOOLS.get(name)


def call_tool(name: str, parameters: Dict, status_callback: Callable[[str], None] | None = None) -> Dict:
    tool = get_tool(name)
    if tool is None:
        return {'success': False, 'error': f'Unknown tool: {name}'}
    try:
        # Check if tool signature accepts status_callback
        sig = inspect.signature(tool)
        if 'status_callback' in sig.parameters:
            return tool(**parameters, status_callback=status_callback)
        return tool(**parameters)
    except Exception as e:
        return {'success': False, 'error': str(e)}
