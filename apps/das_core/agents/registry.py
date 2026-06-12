"""Agent registry and prompt paths."""

from __future__ import annotations


import sqlite3
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.common_data_area import CommonDataArea

_ROOT = Path(__file__).parent
ROUTER_PROMPT_PATH = _ROOT / 'router' / 'router.prompt'

_BUILTIN_DESCRIPTIONS = {
    'agent_creation': 'Helps admins design and create new AI agents by checking tools, planning DB schemas, and writing prompts.',
    'attendance_manager': 'Manage attendance, breaks, and leaves. Records check-ins and check-outs with timestamps and location.',
    'database_manager': 'Manage SQLite database records and schema using controlled SQL operations.',
    'employee_manager': 'Manage employee records, assignments, and profile data.',
    'expense_manager': 'Track, summarize, and manage expense records and supporting documents.',
    'file_manager': 'Handle file listing, inspection, reading, copying, and moving.',
    'holiday_manager': 'Manage company-wide holiday list: create, list, update, and delete holidays.',
    'leave_manager': 'Manage leave requests, approvals, balances, and calendars.',
    'organization_management_agent': 'Manage organization structure, departments, and admin-level master data.',
    'project_manager': 'Manage projects, milestones, deliverables, and project status data.',
    'rag_gen': 'RAG Knowledge Assistant: retrieval-augmented answers over ingested files and stored knowledge.',
    'schedule_manager': 'Validate natural-language schedule requests and create or manage recurring schedules.',
    'task_manager': 'Manage operational tasks, ownership, status updates, and task follow-ups.',
}


def _humanize_agent_name(name: str) -> str:
    return name.replace('_', ' ').strip().capitalize()


def _discover_builtin_agents() -> Dict[str, Dict[str, Any]]:
    builtins: Dict[str, Dict[str, Any]] = {}
    for agent_dir in sorted(_ROOT.iterdir(), key=lambda path: path.name):
        if not agent_dir.is_dir() or agent_dir.name in {'router', '__pycache__'}:
            continue
        prompt_file = agent_dir / f'{agent_dir.name}.prompt'
        if not prompt_file.exists():
            continue
        builtins[agent_dir.name] = {
            'name': agent_dir.name,
            'description': _BUILTIN_DESCRIPTIONS.get(agent_dir.name, _humanize_agent_name(agent_dir.name)),
            'prompt_file': prompt_file,
        }
    return builtins


# Built-in definitions serve as a seed/fallback.
BUILTIN_AGENTS = _discover_builtin_agents()

# Backward-compatible in-memory registry used by legacy tests/callers.
# DB-backed data remains source of truth where available.
AGENTS: Dict[str, Dict[str, Any]] = {
    name: {
        'name': meta['name'],
        'description': meta['description'],
        'prompt_path': meta['prompt_file'],
    }
    for name, meta in BUILTIN_AGENTS.items()
}

ROLE_AGENT_POLICY = {
    'Admin': set(BUILTIN_AGENTS.keys()),
    'User': {'file_manager', 'database_manager', 'attendance_manager', 'leave_manager', 'rag_gen', 'schedule_manager', 'task_manager'},
}

def _get_db_path() -> Path:
    cda = CommonDataArea()
    db_path_str = cda.get_setting('sqlite_db_path', 'backend.db')
    return Path(db_path_str).resolve()

def _ensure_builtins_seeded() -> None:
    """Seed built-in agents into DB if missing."""
    db_path = _get_db_path()
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if table exists (it should created by init_db)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Agents'")
        if not cursor.fetchone():
            conn.close()
            return

        for name, meta in BUILTIN_AGENTS.items():
            cursor.execute("SELECT id FROM Agents WHERE name = ?", (name,))
            existing = cursor.fetchone()
            if not existing:
                # Read content
                p_path = meta['prompt_file']
                content = ""
                if p_path.exists():
                    content = p_path.read_text(encoding='utf-8')
                
                cursor.execute(
                    "INSERT INTO Agents (name, description, prompt_content, is_active) VALUES (?, ?, ?, 1)",
                    (name, meta['description'], content)
                )
                print(f"Seeded built-in agent: {name}")
                agent_id = int(cursor.lastrowid or 0)
            else:
                agent_id = int(existing[0] or 0)

            # Ensure role mappings for this built-in are present without removing user customizations.
            if agent_id > 0:
                for role_name, allowed_agents in ROLE_AGENT_POLICY.items():
                    if name not in allowed_agents:
                        continue
                    cursor.execute("SELECT id FROM Roles WHERE name = ? LIMIT 1", (role_name,))
                    role_row = cursor.fetchone()
                    if not role_row:
                        continue
                    role_id = int(role_row[0] or 0)
                    if role_id > 0:
                        cursor.execute(
                            "INSERT OR IGNORE INTO RoleAgents (role_id, agent_id) VALUES (?, ?)",
                            (role_id, agent_id),
                        )
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to seed built-ins: {e}")

def _ensure_role_agent_mappings() -> None:
    """Ensure default role->agent mappings are present."""
    db_path = _get_db_path()
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Roles'")
        roles_exists = bool(cursor.fetchone())
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='RoleAgents'")
        role_agents_exists = bool(cursor.fetchone())
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Agents'")
        agents_exists = bool(cursor.fetchone())
        if not (roles_exists and role_agents_exists and agents_exists):
            conn.close()
            return

        # NEW: Only seed if RoleAgents is EMPTY.
        # This allows manual overrides in the UI to persist.
        cursor.execute("SELECT COUNT(*) FROM RoleAgents")
        if cursor.fetchone()[0] > 0:
            conn.close()
            return

        cursor.execute(
            "INSERT OR IGNORE INTO Roles (name, description) VALUES ('Admin', 'Full System Access')"
        )
        cursor.execute(
            "INSERT OR IGNORE INTO Roles (name, description) VALUES ('User', 'Standard User Access')"
        )

        for role_name, agent_names in ROLE_AGENT_POLICY.items():
            cursor.execute("SELECT id FROM Roles WHERE name = ?", (role_name,))
            role_row = cursor.fetchone()
            if not role_row:
                continue
            role_id = role_row[0]

            for agent_name in agent_names:
                cursor.execute("SELECT id FROM Agents WHERE name = ?", (agent_name,))
                agent_row = cursor.fetchone()
                if not agent_row:
                    continue
                agent_id = agent_row[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO RoleAgents (role_id, agent_id) VALUES (?, ?)",
                    (role_id, agent_id),
                )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to ensure role-agent mappings: {e}")


def _ensure_default_agent_tool_mappings() -> None:
    """
    Bootstrap permissive tool mappings for built-in agents only when the
    installation has no AgentTools records yet. This prevents fresh desktop
    installs from exposing zero tools to every agent.
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='AgentTools'")
        if not cursor.fetchone():
            conn.close()
            return

        cursor.execute("SELECT COUNT(*) FROM AgentTools")
        if int(cursor.fetchone()[0] or 0) > 0:
            conn.close()
            return

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ToolList'")
        if not cursor.fetchone():
            conn.close()
            return

        cursor.execute("SELECT name FROM ToolList ORDER BY name")
        tool_names = [str(row[0] or '').strip() for row in cursor.fetchall() if str(row[0] or '').strip()]
        if not tool_names:
            conn.close()
            return

        cursor.execute("SELECT id, name FROM Agents WHERE is_active = 1")
        for agent_id, agent_name in cursor.fetchall():
            if str(agent_name or '') not in BUILTIN_AGENTS:
                continue
            for tool_name in tool_names:
                cursor.execute(
                    "INSERT OR IGNORE INTO AgentTools (agent_id, tool_name) VALUES (?, ?)",
                    (int(agent_id), tool_name),
                )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to seed default agent-tool mappings: {e}")

def _extract_email_from_text(value: str) -> Optional[str]:
    if not value:
        return None
    # Supports values like "Name (user@example.com)" and plain email text.
    match = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', value)
    return match.group(1) if match else None

def _get_users_role_expr(cursor: sqlite3.Cursor) -> str:
    """
    Return safe role column reference for Users table.
    Supports migrated schema (role_id) and legacy schema (roleID).
    """
    cursor.execute("PRAGMA table_info(Users)")
    cols = {row[1] for row in cursor.fetchall()}
    if 'role_id' in cols:
        return 'u.role_id'
    if 'roleID' in cols:
        return 'u.roleID'
    return 'u.role_id'

def list_agents(username: str | None = None, return_all: bool = False) -> List[Dict[str, str]]:
    """
    List agents. 
    If return_all=True, returns ALL active agents (for admin UI).
    Else, requires username and returns only agents assigned to that user's role.
    """
    _ensure_builtins_seeded()
    _ensure_role_agent_mappings()
    _ensure_default_agent_tool_mappings()
    
    agents = []
    db_path = _get_db_path()
    
    # Backward compatibility: list_agents() without args historically returned all agents.
    if not username and not return_all:
        return_all = True

    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            if return_all:
                # Admin mode: List all active agents
                cursor.execute("SELECT name, description FROM Agents WHERE is_active = 1")
            else:
                # User mode: Filter by role; accept email, user id, or "Name (email)".
                role_expr = _get_users_role_expr(cursor)
                email_candidate = _extract_email_from_text(username or "")
                user_id_candidate: Optional[int] = None
                if username and str(username).strip().isdigit():
                    user_id_candidate = int(str(username).strip())

                if email_candidate:
                    query = f"""
                        SELECT a.name, a.description
                        FROM Agents a
                        JOIN RoleAgents ra ON a.id = ra.agent_id
                        JOIN Roles r ON ra.role_id = r.id
                        JOIN Users u ON {role_expr} = r.id
                        WHERE u.email = ? AND a.is_active = 1
                    """
                    cursor.execute(query, (email_candidate,))
                elif user_id_candidate is not None:
                    query = f"""
                        SELECT a.name, a.description
                        FROM Agents a
                        JOIN RoleAgents ra ON a.id = ra.agent_id
                        JOIN Roles r ON ra.role_id = r.id
                        JOIN Users u ON {role_expr} = r.id
                        WHERE u.id = ? AND a.is_active = 1
                    """
                    cursor.execute(query, (user_id_candidate,))
                else:
                    # Fallback to legacy behavior (raw username mapped as email)
                    query = f"""
                        SELECT a.name, a.description
                        FROM Agents a
                        JOIN RoleAgents ra ON a.id = ra.agent_id
                        JOIN Roles r ON ra.role_id = r.id
                        JOIN Users u ON {role_expr} = r.id
                        WHERE u.email = ? AND a.is_active = 1
                    """
                    cursor.execute(query, (username,))
            
            for row in cursor.fetchall():
                agents.append({'name': row[0], 'description': row[1]})
            conn.close()
        except Exception as e:
            print(f"DB Error listing agents: {e}")
            agents = []

    # Legacy fallback/merge with in-memory map.
    if return_all:
        seen = {a.get('name') for a in agents}
        for name, meta in AGENTS.items():
            if name not in seen:
                agents.append(
                    {
                        'name': name,
                        'description': str(meta.get('description', '')),
                    }
                )
    
    return agents

def get_agent(name: str) -> Dict[str, Any]:
    """Get agent details (including prompt) from DB."""
    legacy_meta = AGENTS.get(name)
    db_path = _get_db_path()
    
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name, description, prompt_content FROM Agents WHERE name = ?", (name,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                prompt_content = row[2]
                fallback_path = legacy_meta.get('prompt_path') if legacy_meta else None
                return {
                    'name': row[0],
                    'description': row[1],
                    'prompt_content': prompt_content,
                    # Keep prompt_path populated when known for legacy callers/tests.
                    'prompt_path': fallback_path if isinstance(fallback_path, Path) else None,
                }
        except Exception:
            pass

    # Fallback to in-memory registry (legacy/bootstrap behavior).
    if legacy_meta:
        return {
            'name': str(legacy_meta.get('name', name)),
            'description': str(legacy_meta.get('description', '')),
            'prompt_path': legacy_meta.get('prompt_path'),
            'prompt_content': legacy_meta.get('prompt_content'),
        }
    
    raise KeyError(f'Unknown agent: {name}')

def register_agent(name: str, description: str, prompt_content_or_path: str | Path) -> None:
    """Register a new agent into DB. content string or path object."""
    db_path = _get_db_path()
    
    content = ""
    prompt_path: Optional[Path] = None
    if isinstance(prompt_content_or_path, Path) or (isinstance(prompt_content_or_path, str) and (prompt_content_or_path.endswith('.prompt') or prompt_content_or_path.endswith('.txt'))):
         # It's a path
         p = Path(prompt_content_or_path)
         prompt_path = p
         if p.exists():
             content = p.read_text(encoding='utf-8')
    else:
        # It's content
        content = str(prompt_content_or_path)

    # Keep legacy in-memory registry in sync.
    AGENTS[name] = {
        'name': name,
        'description': description,
        'prompt_path': prompt_path,
        'prompt_content': content if not prompt_path else None,
    }

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute("SELECT id, prompt_content, version FROM Agents WHERE name = ?", (name,))
        row = cursor.fetchone()
        
        agent_id = None
        if row:
            agent_id = row[0]
            old_prompt = row[1]
            current_version = row[2] if len(row) > 2 and row[2] is not None else 1
            
            if old_prompt != content:
                cursor.execute(
                    "INSERT INTO AgentPromptVersion (agent_id, agent_name, prompt_content, version) VALUES (?, ?, ?, ?)",
                    (agent_id, name, old_prompt, current_version),
                )
                new_version = current_version + 1
                cursor.execute("UPDATE Agents SET description=?, prompt_content=?, version=?, is_active=1 WHERE id=?", (description, content, new_version, agent_id))
            else:
                cursor.execute("UPDATE Agents SET description=?, is_active=1 WHERE id=?", (description, agent_id))
        else:
            cursor.execute("INSERT INTO Agents (name, description, prompt_content, version) VALUES (?, ?, ?, 1)", (name, description, content))
            agent_id = cursor.lastrowid
            
        # Assign to Admin role by default
        if agent_id:
            cursor.execute("SELECT id FROM Roles WHERE name = 'Admin'")
            admin_role_row = cursor.fetchone()
            if admin_role_row:
                admin_role_id = admin_role_row[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO RoleAgents (role_id, agent_id) VALUES (?, ?)",
                    (admin_role_id, agent_id)
                )
        
        conn.commit()
        conn.close()
    except Exception as e:
         print(f"Failed to register agent in DB: {e}")
         # Backward-compatible behavior: keep in-memory registration even if DB write fails.
         return
