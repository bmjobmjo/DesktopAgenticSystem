"""Tool registry, DB sync, and dispatcher."""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Dict, List, Any

from core.common_data_area import CommonDataArea

# Base Tools Directory
TOOLS_DIR = Path(__file__).parent

ToolFunc = Callable[..., Dict]
TOOLS: Dict[str, ToolFunc] = {}


def _discover_tools() -> None:
    """Dynamically discover tools in the tools directory."""
    global TOOLS
    TOOLS.clear()

    if str(TOOLS_DIR) not in sys.path:
        sys.path.append(str(TOOLS_DIR))

    for root, _, files in os.walk(TOOLS_DIR):
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                module_path = Path(root) / file
                try:
                    rel_path = module_path.relative_to(TOOLS_DIR.parent)
                    module_name = str(rel_path).replace(os.sep, '.')[:-3]
                    module = importlib.import_module(module_name)

                    tool_name = file[:-3]
                    if hasattr(module, tool_name):
                        func = getattr(module, tool_name)
                        if callable(func):
                            TOOLS[tool_name] = func
                            continue

                    for name, obj in inspect.getmembers(module):
                        if inspect.isfunction(obj) and obj.__module__ == module.__name__ and not name.startswith('_'):
                            TOOLS[name] = obj
                except Exception as e:
                    print(f"Failed to load tool from {file} (module: {module_name if 'module_name' in locals() else 'N/A'}): {e}")
                    import traceback
                    traceback.print_exc()

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


def _tool_metadata(name: str, func: ToolFunc) -> Dict[str, str]:
    doc = (func.__doc__ or '').strip()
    first_line = doc.splitlines()[0] if doc else 'No description.'
    try:
        sig = inspect.signature(func)
        param_names = [p for p in sig.parameters.keys() if p != 'status_callback']
        output_schema = str(sig.return_annotation)
    except Exception:
        param_names = []
        output_schema = ''
    return {
        'name': name,
        'description': first_line or 'No description.',
        'input_schema': json.dumps({'parameters': param_names}),
        'output_schema': output_schema,
        'version': '1.0',
    }


def sync_tools_to_db(cda: CommonDataArea | None = None) -> int:
    cda = cda or CommonDataArea()
    db_path = Path(str(cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    tools_map = list_tools()
    tool_meta = [_tool_metadata(name, func) for name, func in tools_map.items()]
    active_names = {item['name'] for item in tool_meta}

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ToolList (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                input_schema TEXT,
                output_schema TEXT,
                version TEXT
            )
            """
        )
        for item in tool_meta:
            cur.execute(
                """
                INSERT INTO ToolList (name, description, input_schema, output_schema, version)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    input_schema=excluded.input_schema,
                    output_schema=excluded.output_schema,
                    version=excluded.version
                """,
                (item['name'], item['description'], item['input_schema'], item['output_schema'], item['version']),
            )
        cur.execute('SELECT name FROM ToolList')
        stale = [str(row[0]) for row in cur.fetchall() if str(row[0]) not in active_names]
        for name in stale:
            cur.execute('DELETE FROM ToolList WHERE name=?', (name,))
        conn.commit()
    finally:
        conn.close()
    return len(tool_meta)


def list_tool_metadata(cda: CommonDataArea | None = None, names: List[str] | None = None) -> List[Dict[str, Any]]:
    cda = cda or CommonDataArea()
    db_path = Path(str(cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
    if not db_path.exists():
        sync_tools_to_db(cda)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
        if not cur.fetchone():
            conn.close()
            sync_tools_to_db(cda)
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
        cur.execute('SELECT name, description, input_schema, output_schema, version FROM ToolList ORDER BY name')
        rows = [
            {
                'name': str(row[0]),
                'description': str(row[1] or ''),
                'input_schema': str(row[2] or ''),
                'output_schema': str(row[3] or ''),
                'version': str(row[4] or ''),
            }
            for row in cur.fetchall()
        ]
    finally:
        conn.close()

    if names is None:
        return rows
    allowed = {str(name).strip() for name in names if str(name).strip()}
    return [row for row in rows if row['name'] in allowed]


def call_tool(name: str, parameters: Dict, status_callback: Callable[[str], None] | None = None) -> Dict:
    tool = get_tool(name)
    if tool is None:
        return {'success': False, 'error': f'Unknown tool: {name}'}
    try:
        sig = inspect.signature(tool)
        if 'status_callback' in sig.parameters:
            return tool(**parameters, status_callback=status_callback)
        return tool(**parameters)
    except Exception as e:
        return {'success': False, 'error': str(e)}
