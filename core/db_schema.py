import sys
import os

# Add project root to sys.path if running as script
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from pathlib import Path
import time

# DB Path
DB_PATH = Path(r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db')
LEGACY_USER_COLUMNS = {'roleID', 'chat_id'}


def _resolve_db_path() -> Path:
    try:
        from core.common_data_area import CommonDataArea

        configured = str(CommonDataArea().get_setting('sqlite_db_path', '') or '').strip()
        if configured:
            return Path(configured).resolve()
    except Exception:
        pass
    return Path(DB_PATH).resolve()

def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def _create_holiday_list(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS HolidayList (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        holiday_date DATE NOT NULL UNIQUE,
        holiday_name TEXT NOT NULL,
        holiday_type TEXT NOT NULL DEFAULT 'Company',
        description TEXT,
        is_optional BOOLEAN NOT NULL DEFAULT 0,
        created_by INTEGER NOT NULL,
        updated_by INTEGER,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME,
        FOREIGN KEY(created_by) REFERENCES Users(id),
        FOREIGN KEY(updated_by) REFERENCES Users(id)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_holidaylist_date ON HolidayList(holiday_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_holidaylist_type ON HolidayList(holiday_type)")

def _repair_holiday_list_fk_if_needed(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='HolidayList'")
    if not cursor.fetchone():
        return

    cursor.execute("PRAGMA foreign_key_list(HolidayList)")
    fk_rows = cursor.fetchall()
    has_legacy_ref = any((row[2] or '').strip().lower() == 'users_old' for row in fk_rows)
    if not has_legacy_ref:
        return

    print("Repairing HolidayList foreign keys (Users_Old -> Users)...")
    cursor.execute("ALTER TABLE HolidayList RENAME TO HolidayList_Old")
    _create_holiday_list(cursor)
    cursor.execute("""
        INSERT INTO HolidayList
        (id, holiday_date, holiday_name, holiday_type, description, is_optional, created_by, updated_by, created_at, updated_at)
        SELECT
        id, holiday_date, holiday_name, holiday_type, description, is_optional, created_by, updated_by, created_at, updated_at
        FROM HolidayList_Old
    """)
    cursor.execute("DROP TABLE HolidayList_Old")

def init_db():
    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=20)
    cursor = conn.cursor()

    print("Checking Database Schema...")

    # 1. Enhance Agents Table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Agents'")
    if not cursor.fetchone():
        # Create new table directly
        cursor.execute("""
        CREATE TABLE Agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            prompt_content TEXT,
            version INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
    else:
        # Check if Agents table has expected columns
        cursor.execute("PRAGMA table_info(Agents)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'prompt_content' not in columns:
            print("Migrating Agents table schema...")
            # Rename old table
            cursor.execute("ALTER TABLE Agents RENAME TO Agents_Old")
            
            # Create new table
            cursor.execute("""
            CREATE TABLE Agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                prompt_content TEXT,
                version INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Copy data
            try:
                # Map old schema (agent_name, agent_prompt) to new
                cursor.execute("SELECT agent_name, agent_prompt FROM Agents_Old")
                for row in cursor.fetchall():
                    cursor.execute("INSERT OR IGNORE INTO Agents (name, prompt_content) VALUES (?, ?)", (row[0], row[1]))
                # Drop old table
                cursor.execute("DROP TABLE Agents_Old")
            except Exception as e:
                print(f"Warning during Agents migration: {e}")
                
        if 'version' not in columns:
            print("Adding version column to Agents table...")
            cursor.execute("ALTER TABLE Agents ADD COLUMN version INTEGER DEFAULT 1")

    # 1.5 AgentPromptVersion Table for History
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS AgentPromptVersion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        agent_name TEXT,
        prompt_content TEXT,
        version INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(agent_id) REFERENCES Agents(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("PRAGMA table_info(AgentPromptVersion)")
    apv_cols = [row[1] for row in cursor.fetchall()]
    if 'agent_name' not in apv_cols:
        cursor.execute("ALTER TABLE AgentPromptVersion ADD COLUMN agent_name TEXT")
    # Backfill missing agent_name from Agents for existing history rows.
    try:
        cursor.execute("""
            UPDATE AgentPromptVersion
            SET agent_name = (
                SELECT name FROM Agents WHERE Agents.id = AgentPromptVersion.agent_id
            )
            WHERE agent_name IS NULL OR TRIM(agent_name) = ''
        """)
    except Exception:
        pass

    # 2. Roles Table
    # Check if Roles table has correct schema
    cursor.execute("PRAGMA table_info(Roles)")
    r_cols = {row[1]: row for row in cursor.fetchall()}
    
    if r_cols and 'name' not in r_cols:
        print("Migrating Roles table schema...")
        # Likely legacy schema: role_name, roleID
        cursor.execute("ALTER TABLE Roles RENAME TO Roles_Old")
        cursor.execute("""
        CREATE TABLE Roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        )
        """)
        try:
            # Try to copy data if possible
            cursor.execute("SELECT roleID, role_name FROM Roles_Old")
            for rid, rname in cursor.fetchall():
                cursor.execute("INSERT OR IGNORE INTO Roles (id, name, description) VALUES (?, ?, ?)", (rid, rname, 'Legacy Role'))
            cursor.execute("DROP TABLE Roles_Old")
        except Exception as e:
            print(f"Warning during Roles migration: {e}")
            
    # Always ensure the table exists if migration didn't happen or failed
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    )
    """)
    
    # 3. RoleAgents Mapping
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS RoleAgents (
        role_id INTEGER,
        agent_id INTEGER,
        PRIMARY KEY (role_id, agent_id),
        FOREIGN KEY(role_id) REFERENCES Roles(id),
        FOREIGN KEY(agent_id) REFERENCES Agents(id)
    )
    """)

    # 4. Users role_id / migrate legacy roleID
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
    if not cursor.fetchone():
        # Create Users table if it doesn't exist
        cursor.execute("""
        CREATE TABLE Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            mobile_number TEXT,
            whatsapp_number TEXT,
            telegram_chat_id TEXT,
            password_hash TEXT,
            role_id INTEGER REFERENCES Roles(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME
        )
        """)
    else:
        cursor.execute("PRAGMA table_info(Users)")
        u_info = cursor.fetchall()
        u_cols = [c[1] for c in u_info]
        if 'role_id' not in u_cols and 'roleID' not in u_cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN role_id INTEGER REFERENCES Roles(id)")
        elif 'role_id' not in u_cols and 'roleID' in u_cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN role_id INTEGER REFERENCES Roles(id)")
            cursor.execute("UPDATE Users SET role_id = roleID WHERE role_id IS NULL")
        if 'mobile_number' not in u_cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN mobile_number TEXT")
        if 'whatsapp_number' not in u_cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN whatsapp_number TEXT")
        if 'telegram_chat_id' not in u_cols:
            cursor.execute("ALTER TABLE Users ADD COLUMN telegram_chat_id TEXT")

    # Drop legacy Users columns by rebuilding Users table.
    # SQLite drop-column support can vary; table rebuild is deterministic.
    cursor.execute("PRAGMA table_info(Users)")
    u_info = cursor.fetchall()
    u_cols = [c[1] for c in u_info]
    legacy_present = [c for c in u_cols if c in LEGACY_USER_COLUMNS]
    if legacy_present:
        keep_info = [c for c in u_info if c[1] not in LEGACY_USER_COLUMNS]
        col_defs = []
        pk_cols = [c for c in keep_info if c[5] > 0]

        for c in keep_info:
            name = c[1]
            ctype = c[2] or ""
            notnull = bool(c[3])
            dflt = c[4]
            pk = int(c[5])

            parts = [_quote_ident(name)]
            if ctype:
                parts.append(ctype)
            if notnull:
                parts.append("NOT NULL")
            if dflt is not None:
                parts.append(f"DEFAULT {dflt}")
            if len(pk_cols) == 1 and pk == 1:
                parts.append("PRIMARY KEY")
                if str(ctype).upper() == "INTEGER":
                    parts.append("AUTOINCREMENT")

            col_defs.append(" ".join(parts))

        if len(pk_cols) > 1:
            ordered_pk = sorted(pk_cols, key=lambda x: x[5])
            pk_list = ", ".join(_quote_ident(c[1]) for c in ordered_pk)
            col_defs.append(f"PRIMARY KEY ({pk_list})")

        create_sql = f"CREATE TABLE Users_New ({', '.join(col_defs)})"
        keep_cols_sql = ", ".join(_quote_ident(c[1]) for c in keep_info)

        cursor.execute("ALTER TABLE Users RENAME TO Users_Old")
        cursor.execute(create_sql)
        cursor.execute(f"INSERT INTO Users_New ({keep_cols_sql}) SELECT {keep_cols_sql} FROM Users_Old")
        cursor.execute("DROP TABLE Users_Old")
        cursor.execute("ALTER TABLE Users_New RENAME TO Users")

    # 5. Company-wide Holiday List
    _create_holiday_list(cursor)
    _repair_holiday_list_fk_if_needed(cursor)

    # 6. LLM Usage Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS LLMUsage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        user_prompt TEXT,
        agent_name TEXT,
        prompt TEXT,
        response TEXT,
        provider TEXT,
        model_name TEXT,
        token_in INTEGER,
        token_out INTEGER,
        total_tokens INTEGER
    )
    """)
    
    # Migration for LLMUsage
    cursor.execute("PRAGMA table_info(LLMUsage)")
    lu_cols = [row[1] for row in cursor.fetchall()]
    if 'provider' not in lu_cols:
        cursor.execute("ALTER TABLE LLMUsage ADD COLUMN provider TEXT")
    if 'model_name' not in lu_cols:
        cursor.execute("ALTER TABLE LLMUsage ADD COLUMN model_name TEXT")

    conn.commit()
    # conn.close() - Removed to allow further updates

    # 7. File Management Tables
    cursor.execute("PRAGMA table_info(Expenses)")
    e_cols = [row[1] for row in cursor.fetchall()]
    if e_cols and 'file_id' not in e_cols:
        print("Migrating Expenses table schema...")
        cursor.execute("ALTER TABLE Expenses RENAME TO Expenses_Old")
        cursor.execute("""
        CREATE TABLE Expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            amount REAL,
            currency TEXT DEFAULT 'USD',
            category TEXT,
            vendor TEXT,
            date TEXT,
            description TEXT,
            FOREIGN KEY(file_id) REFERENCES Files(id) ON DELETE SET NULL
        )
        """)
        # We don't strictly migrate data here as mapping path to file_id is complex in this script,
        # but we preserve the old table as backup. 
        # For a clean fix, we focus on the new structure.
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT UNIQUE NOT NULL,
        filename TEXT NOT NULL,
        file_type TEXT,
        file_size INTEGER,
        file_hash TEXT,
        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        description TEXT,
        project_id INTEGER REFERENCES Projects(id) ON DELETE SET NULL
    )
    """)

    cursor.execute("PRAGMA table_info(Files)")
    file_cols = {row[1] for row in cursor.fetchall()}
    if 'project_id' not in file_cols:
        cursor.execute("ALTER TABLE Files ADD COLUMN project_id INTEGER")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL DEFAULT 'generic',
        source_id INTEGER,
        chunk_index INTEGER NOT NULL DEFAULT 0,
        type TEXT NOT NULL DEFAULT 'info',
        content TEXT,
        char_count INTEGER,
        token_count INTEGER,
        embedding_vector BLOB,
        enc INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("PRAGMA table_info(Embeddings)")
    emb_cols = {row[1] for row in cursor.fetchall()}
    if 'source_type' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN source_type TEXT NOT NULL DEFAULT 'generic'")
    if 'source_id' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN source_id INTEGER")
    if 'chunk_index' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 0")
    if 'type' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN type TEXT NOT NULL DEFAULT 'info'")
    if 'content' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN content TEXT")
    if 'char_count' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN char_count INTEGER")
    if 'token_count' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN token_count INTEGER")
    if 'embedding_vector' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN embedding_vector BLOB")
    if 'enc' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN enc INTEGER NOT NULL DEFAULT 0")
    if 'created_at' not in emb_cols:
        cursor.execute("ALTER TABLE Embeddings ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_source ON Embeddings(source_type, source_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_type ON Embeddings(type)")

    # Migrate legacy file embedding rows once, then retire old table.
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='FileEmbeddings'")
    if cursor.fetchone():
        try:
            cursor.execute("SELECT COUNT(*) FROM Embeddings")
            new_count = int(cursor.fetchone()[0] or 0)
            if new_count == 0:
                cursor.execute("""
                    INSERT INTO Embeddings (source_type, source_id, chunk_index, type, content, embedding_vector, enc)
                    SELECT 'file', file_id, chunk_index, COALESCE(chunk_type, 'file_text'), content_chunk, embedding_vector, 0
                    FROM FileEmbeddings
                """)
            cursor.execute("DROP TABLE IF EXISTS FileEmbeddings")
        except Exception as e:
            print(f"Warning during FileEmbeddings -> Embeddings migration: {e}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER,
        amount REAL,
        currency TEXT DEFAULT 'USD',
        category TEXT,
        vendor TEXT,
        date TEXT,
        description TEXT,
        FOREIGN KEY(file_id) REFERENCES Files(id) ON DELETE SET NULL
    )
    """)

    # 8. Tool Registry Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ToolList (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        input_schema TEXT,
        output_schema TEXT,
        version TEXT,
        example_call TEXT
    )
    """)
    cursor.execute("PRAGMA table_info(ToolList)")
    tool_cols = {str(row[1]) for row in cursor.fetchall()}
    if 'example_call' not in tool_cols:
        cursor.execute("ALTER TABLE ToolList ADD COLUMN example_call TEXT")

    # 9. Agent -> Tool Mapping
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS AgentTools (
        agent_id INTEGER NOT NULL,
        tool_name TEXT NOT NULL,
        PRIMARY KEY (agent_id, tool_name),
        FOREIGN KEY(agent_id) REFERENCES Agents(id) ON DELETE CASCADE
    )
    """)

    # Populate Tools
    try:
        from tools.tool_registry import sync_tools_to_db
        count = sync_tools_to_db()
        print(f"Syncing {count} tools to registry...")
    except Exception as e:
        print(f"Error syncing tools: {e}")

    # 10. Chat History Tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChatHistory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        agent_activity TEXT,
        user_id TEXT,
        interface TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("PRAGMA table_info(ChatHistory)")
    ch_cols = [row[1] for row in cursor.fetchall()]
    if 'agent_activity' not in ch_cols:
        cursor.execute("ALTER TABLE ChatHistory ADD COLUMN agent_activity TEXT")
    if 'user_id' not in ch_cols:
        cursor.execute("ALTER TABLE ChatHistory ADD COLUMN user_id TEXT")
    if 'interface' not in ch_cols:
        cursor.execute("ALTER TABLE ChatHistory ADD COLUMN interface TEXT")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChatLog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        user_id TEXT,
        interface TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(chat_id) REFERENCES ChatHistory(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("PRAGMA table_info(ChatLog)")
    cl_cols = [row[1] for row in cursor.fetchall()]
    if 'user_id' not in cl_cols:
        cursor.execute("ALTER TABLE ChatLog ADD COLUMN user_id TEXT")
    if 'interface' not in cl_cols:
        cursor.execute("ALTER TABLE ChatLog ADD COLUMN interface TEXT")

    # 11. Channel Identity and Inbound Dedupe
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChannelUsers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        channel_user_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, channel_user_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChannelInboundMessages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        message_id TEXT NOT NULL,
        received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        handled INTEGER DEFAULT 0,
        UNIQUE(provider, message_id)
    )
    """)

    # 12. Scheduler table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS Schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            nl_request TEXT,
            task_prompt TEXT NOT NULL,
            schedule_type TEXT NOT NULL DEFAULT 'other',
            interval_minutes INTEGER NOT NULL DEFAULT 0,
            run_hour INTEGER NOT NULL DEFAULT 9,
            run_minute INTEGER NOT NULL DEFAULT 0,
            run_day_of_week INTEGER NOT NULL DEFAULT 0,
            run_day_of_month INTEGER NOT NULL DEFAULT 1,
            timezone TEXT DEFAULT 'Asia/Calcutta',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'active',
            next_run_at DATETIME,
            last_run_at DATETIME,
            last_result TEXT,
            validation_reason TEXT,
            owner TEXT,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(Schedules)")
    sch_cols = {row[1] for row in cursor.fetchall()}
    if 'nl_request' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN nl_request TEXT")
    if 'task_prompt' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN task_prompt TEXT NOT NULL DEFAULT ''")
    if 'schedule_type' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN schedule_type TEXT NOT NULL DEFAULT 'other'")
    if 'interval_minutes' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 0")
    if 'run_hour' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN run_hour INTEGER NOT NULL DEFAULT 9")
    if 'run_minute' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN run_minute INTEGER NOT NULL DEFAULT 0")
    if 'run_day_of_week' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN run_day_of_week INTEGER NOT NULL DEFAULT 0")
    if 'run_day_of_month' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN run_day_of_month INTEGER NOT NULL DEFAULT 1")
    if 'timezone' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN timezone TEXT DEFAULT 'Asia/Calcutta'")
    if 'is_enabled' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN is_enabled INTEGER NOT NULL DEFAULT 1")
    if 'status' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if 'next_run_at' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN next_run_at DATETIME")
    if 'last_run_at' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN last_run_at DATETIME")
    if 'last_result' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN last_result TEXT")
    if 'validation_reason' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN validation_reason TEXT")
    if 'owner' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN owner TEXT")
    if 'created_by' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN created_by TEXT")
    if 'updated_at' not in sch_cols:
        cursor.execute("ALTER TABLE Schedules ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedules_enabled_next_run ON Schedules(is_enabled, next_run_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedules_type ON Schedules(schedule_type)")

    conn.commit()
    conn.close()
    print("Database Schema Verified (Files, Expenses, ToolList added).")

if __name__ == "__main__":
    init_db()


