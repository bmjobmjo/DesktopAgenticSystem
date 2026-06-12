"""Tools specifically to support the AgentCreationAgent in making new agents."""

__tool_exports__ = ['get_database_schema', 'list_available_tools', 'read_agent_template', 'save_new_agent']

from typing import Dict, List, Any
import sqlite3
from pathlib import Path

from execution_logger import log_execution_step, log_exception
from tools.tool_registry import list_tools
from core.common_data_area import CommonDataArea
from agents.registry import register_agent
from tools.sqlite_tools import execute_sql

def get_database_schema() -> Dict[str, Any]:
    """
    Returns the full database schema including all tables and their columns.
    Useful for an Agent to determine if new tables are needed.
    """
    cda = CommonDataArea()
    db_path_str = cda.get_setting('sqlite_db_path', 'backend.db')
    db_path = Path(db_path_str).resolve()
    
    if not db_path.exists():
         return {"success": False, "error": f"Database file not found at {db_path}"}
         
    schema = {}
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]
            
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [dict(
                    cid=col[0],
                    name=col[1],
                    type=col[2],
                    notnull=bool(col[3]),
                    default_value=col[4],
                    pk=bool(col[5])
                ) for col in cursor.fetchall()]
                
                schema[table] = columns
                
        return {"success": True, "schema": schema}
    except Exception as e:
        log_exception("SCHEMA_TOOL_ERROR", e, {"db_path": str(db_path)})
        return {"success": False, "error": str(e)}

def list_available_tools() -> Dict[str, Any]:
    """
    Returns a list of all tools currently registered in the system along with their descriptions and schemas.
    Helps the Agent determine if the requested functionality is already supported by existing tools.
    """
    try:
        tools_dict = list_tools()
        tools_info = []
        
        import inspect
        for name, func in tools_dict.items():
            doc = (func.__doc__ or "").strip()
            sig = inspect.signature(func)
            
            # Simple parameter parsing for clarity
            params = []
            for param_name, param in sig.parameters.items():
                if param_name == "status_callback":
                     continue
                params.append({"name": param_name})
                
            tools_info.append({
                "name": name,
                "description": doc.split("\n")[0] if doc else "No description",
                "parameters": params
            })
            
        return {"success": True, "tools": tools_info}
    except Exception as e:
        log_exception("LIST_TOOLS_ERROR", e)
        return {"success": False, "error": str(e)}

def read_agent_template() -> Dict[str, Any]:
    """
    Reads the standard agent prompt template file that should be used as the base
    for creating a new agent system prompt.
    """
    candidate_paths = [
        (Path.cwd() / "prompts" / "templates" / "agent_template.txt").resolve(),
        (Path(__file__).resolve().parents[1] / "prompts" / "templates" / "agent_template.txt").resolve(),
    ]

    try:
        template_path = next((path for path in candidate_paths if path.exists()), None)
        if template_path is None:
             return {"success": False, "error": "Template file not found"}
             
        content = template_path.read_text(encoding='utf-8')
        return {"success": True, "template": content}
    except Exception as e:
         log_exception("READ_TEMPLATE_ERROR", e, {"paths": [str(path) for path in candidate_paths]})
         return {"success": False, "error": str(e)}

def save_new_agent(name: str, description: str, prompt_content: str) -> Dict[str, Any]:
    """
    Saves a newly designed agent directly into the database so it can be used by the system.
    If an agent with the given name already exists, it will UPDATE the agent with the new description and prompt.
    Automatically assigns the agent to the 'Admin' role.
    
    Args:
        name: A unique snake_case name for the agent (e.g. 'water_tracker').
        description: A short sentence summarizing what the agent does.
        prompt_content: The comprehensive system prompt text for the agent, formatted correctly based on the template.
    """
    try:
        # Save to database via the registry method
        register_agent(name, description, prompt_content)
        
        return {"success": True, "message": f"Successfully registered new agent: {name}"}
    except Exception as e:
        log_exception("SAVE_AGENT_ERROR", e, {"name": name})
        return {"success": False, "error": str(e)}
