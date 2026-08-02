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
from execution_logger import log_exception, log_execution_step
from tools.tool_metadata_registry import TOOL_METADATA

# Base Tools Directory
TOOLS_DIR = Path(__file__).parent
KNOWN_TOOL_MODULE_NAMES = {
    'tools.agent_creation_tools',
    'tools.create_zip',
    'tools.export_file',
    'tools.gmail_tools',
    'tools.render_image',
    'tools.scheduler_tools',
    'tools.sqlite_tools',
    'tools.project_file_delivery',
    'tools.telegram_tools',
    'tools.whatsapp_tools',
    'tools.embeddings.file_ingestion',
    'tools.filesystem.copy_file',
    'tools.filesystem.inspect_file',
    'tools.filesystem.list_directory',
    'tools.filesystem.move_file',
    'tools.filesystem.read_file',
}

ToolFunc = Callable[..., Dict]
TOOLS: Dict[str, ToolFunc] = {}


def _register_module_exports(module: Any, file_stem: str) -> None:
    explicit_exports = getattr(module, '__tool_exports__', None)
    if isinstance(explicit_exports, (list, tuple, set)) and explicit_exports:
        for export_name in explicit_exports:
            name = str(export_name or '').strip()
            if not name or name.startswith('_'):
                continue
            func = getattr(module, name, None)
            if callable(func):
                TOOLS[name] = func
        return

    if hasattr(module, file_stem):
        func = getattr(module, file_stem)
        if callable(func):
            TOOLS[file_stem] = func


def _load_known_tool_modules(force_reload: bool = False) -> Dict[str, Any]:
    """
    Import tool modules explicitly so frozen desktop builds do not depend on
    walking a real filesystem tree to discover available tools.
    """
    modules: Dict[str, Any] = {}
    for module_name in sorted(KNOWN_TOOL_MODULE_NAMES):
        try:
            if force_reload and module_name in sys.modules:
                modules[module_name] = importlib.reload(sys.modules[module_name])
            else:
                modules[module_name] = importlib.import_module(module_name)
        except Exception as exc:
            print(f"Skipping optional tool module {module_name}: {exc}")
            log_execution_step('TOOL_MODULE_SKIP', f"{module_name}: {exc}")
            log_exception('TOOL_MODULE_SKIP', exc, {'module_name': module_name})
    return modules



def _discover_tools(force_reload: bool = False) -> None:
    """Dynamically discover tools in the tools directory."""
    global TOOLS
    TOOLS.clear()

    if str(TOOLS_DIR) not in sys.path:
        sys.path.append(str(TOOLS_DIR))

    loaded_module_names = set(KNOWN_TOOL_MODULE_NAMES)

    for module_name, module in _load_known_tool_modules(force_reload=force_reload).items():
        try:
            _register_module_exports(module, module_name.rsplit('.', 1)[-1])
        except Exception as e:
            print(f"Failed to register known tool module {module_name}: {e}")
            import traceback
            traceback.print_exc()

    for root, _, files in os.walk(TOOLS_DIR):
        for file in files:
            if file == 'tool_registry.py':
                continue
            if file.endswith('.py') and not file.startswith('__'):
                module_path = Path(root) / file
                try:
                    rel_path = module_path.relative_to(TOOLS_DIR.parent)
                    module_name = str(rel_path).replace(os.sep, '.')[:-3]
                    if module_name in loaded_module_names:
                        continue
                    if force_reload and module_name in sys.modules:
                        module = importlib.reload(sys.modules[module_name])
                    else:
                        module = importlib.import_module(module_name)
                    _register_module_exports(module, file[:-3])
                except Exception as e:
                    print(f"Failed to load tool from {file} (module: {module_name if 'module_name' in locals() else 'N/A'}): {e}")
                    import traceback
                    traceback.print_exc()

    TOOLS['list_tools'] = list_tools
    TOOLS['list_tool_metadata'] = list_tool_metadata

    if 'ingest_file' in TOOLS:
        TOOLS['file_ingestion'] = TOOLS['ingest_file']
        TOOLS['file_embedding_tool'] = TOOLS['ingest_file']
    if 'get_database_schema' in TOOLS:
        TOOLS['dbschema'] = TOOLS['get_database_schema']
    if 'execute_sql' in TOOLS:
        TOOLS['sql'] = TOOLS['execute_sql']


def list_tools(force_refresh: bool = False) -> Dict[str, ToolFunc]:
    if force_refresh or not TOOLS:
        _discover_tools(force_reload=force_refresh)
    return dict(TOOLS)


def reload_tool_registry() -> Dict[str, ToolFunc]:
    _discover_tools(force_reload=True)
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

    meta = dict(TOOL_METADATA.get(name, {}) or {})
    parameters = meta.get('parameters')
    if not isinstance(parameters, list):
        parameters = [{'name': p, 'type': 'Any', 'required': True, 'description': ''} for p in param_names]

    example_call = meta.get('example_call')
    if example_call is None:
        example_call = json.dumps({'tool_name': name, 'parameters': {p: f'<{p}>' for p in param_names}}, ensure_ascii=False)

    return {
        'name': name,
        'description': str(meta.get('description') or first_line or 'No description.'),
        'input_schema': json.dumps({'parameters': parameters}, ensure_ascii=False),
        'output_schema': str(meta.get('output_schema') or output_schema or ''),
        'example_call': str(example_call),
        'version': '1.0',
    }


def sync_tools_to_db(cda: CommonDataArea | None = None) -> int:
    cda = cda or CommonDataArea()
    db_path = Path(str(cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db')).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    tools_map = list_tools(force_refresh=True)
    tool_meta = [_tool_metadata(name, func) for name, func in tools_map.items()]
    active_names = {item['name'] for item in tool_meta}

    conn = sqlite3.connect(str(db_path), timeout=20)
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
                version TEXT,
                example_call TEXT
            )
            """
        )
        cur.execute("PRAGMA table_info(ToolList)")
        cols = {str(row[1]) for row in cur.fetchall()}
        if 'example_call' not in cols:
            cur.execute("ALTER TABLE ToolList ADD COLUMN example_call TEXT")

        for item in tool_meta:
            cur.execute(
                """
                INSERT INTO ToolList (name, description, input_schema, output_schema, version, example_call)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    input_schema=excluded.input_schema,
                    output_schema=excluded.output_schema,
                    version=excluded.version,
                    example_call=excluded.example_call
                """,
                (item['name'], item['description'], item['input_schema'], item['output_schema'], item['version'], item['example_call']),
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

    conn = sqlite3.connect(str(db_path), timeout=20)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
        if not cur.fetchone():
            conn.close()
            sync_tools_to_db(cda)
            conn = sqlite3.connect(str(db_path), timeout=20)
            cur = conn.cursor()
        cur.execute("PRAGMA table_info(ToolList)")
        cols = {str(row[1]) for row in cur.fetchall()}
        has_example = 'example_call' in cols
        if has_example:
            cur.execute('SELECT name, description, input_schema, output_schema, version, example_call FROM ToolList ORDER BY name')
        else:
            cur.execute('SELECT name, description, input_schema, output_schema, version FROM ToolList ORDER BY name')
        rows = [
            {
                'name': str(row[0]),
                'description': str(row[1] or ''),
                'input_schema': str(row[2] or ''),
                'output_schema': str(row[3] or ''),
                'version': str(row[4] or ''),
                'example_call': str(row[5] or '') if len(row) > 5 else '',
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
            try:
                return tool(**parameters, status_callback=status_callback)
            except TypeError as e:
                if "unexpected keyword argument" not in str(e):
                    raise
                allowed = {k for k in sig.parameters.keys() if k != 'status_callback'}
                filtered = {k: v for k, v in dict(parameters or {}).items() if k in allowed}
                return tool(**filtered, status_callback=status_callback)
        try:
            return tool(**parameters)
        except TypeError as e:
            if "unexpected keyword argument" not in str(e):
                raise
            allowed = set(sig.parameters.keys())
            filtered = {k: v for k, v in dict(parameters or {}).items() if k in allowed}
            return tool(**filtered)
    except Exception as e:
        return {'success': False, 'error': str(e)}
