import sqlite3
from pathlib import Path
import json

# DB Path
DB_PATH = Path(r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db')

def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Migrating Database Schema...")

    # 1. Enhance Agents Table
    # We will recreate it to ensure correct schema
    cursor.execute("DROP TABLE IF EXISTS Agents_New")
    cursor.execute("""
    CREATE TABLE Agents_New (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        prompt_content TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Copy existing data if any (mapping correctly)
    try:
        cursor.execute("SELECT agent_name, agent_prompt FROM Agents")
        existing_agents = cursor.fetchall()
        for name, prompt in existing_agents:
            cursor.execute("INSERT INTO Agents_New (name, prompt_content) VALUES (?, ?)", (name, prompt))
        print(f"Migrated {len(existing_agents)} existing agents from old table.")
        cursor.execute("DROP TABLE Agents")
    except sqlite3.OperationalError:
        print("Agents table likely didn't exist or had different schema. Skipping copy.")

    cursor.execute("ALTER TABLE Agents_New RENAME TO Agents")

    # 2. Enhance Roles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    )
    """)
    
    # 3. Create RoleAgents Mapping
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS RoleAgents (
        role_id INTEGER,
        agent_id INTEGER,
        PRIMARY KEY (role_id, agent_id),
        FOREIGN KEY(role_id) REFERENCES Roles(id),
        FOREIGN KEY(agent_id) REFERENCES Agents(id)
    )
    """)

    # 4. Ensure Users Table has role_id
    # check if column exists
    cursor.execute("PRAGMA table_info(Users)")
    columns = [c[1] for c in cursor.fetchall()]
    if 'role_id' not in columns and 'roleID' not in columns:
        print("Adding role_id to Users...")
        # We can't easily add FK constraint in SQLite via ALTER, but adding column is fine
        cursor.execute("ALTER TABLE Users ADD COLUMN role_id INTEGER REFERENCES Roles(id)")
    elif 'roleID' in columns:
        print("Users table already has roleID (using that as FK).")

    conn.commit()
    conn.close()
    print("Schema Migration Complete.")

def populate_initial_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Insert Default Role (Admin)
    cursor.execute("INSERT OR IGNORE INTO Roles (name, description) VALUES ('Admin', 'Full Access')")
    cursor.execute("INSERT OR IGNORE INTO Roles (name, description) VALUES ('User', 'Standard Access')")
    
    # Get Admin Role ID
    cursor.execute("SELECT id FROM Roles WHERE name='Admin'")
    admin_role_id = cursor.fetchone()[0]

    # 2. Migrate Built-in Agents from registry.py
    # This requires importing the module, but we might just parse/hardcode common ones to be safe
    # Or rely on the next step where we read registry.
    
    # Let's read registry.py manually or import it?
    # Importing is better to get the actual prompts path.
    # But files are local.
    
    # For now, let's just setup the structure. Actual agent migration will be separate.
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate_db()
    populate_initial_data()
