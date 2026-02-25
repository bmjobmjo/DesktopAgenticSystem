import sqlite3
from pathlib import Path

DB_PATH = Path(r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db')

def wipe_and_recreate_roles():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("DROP TABLE IF EXISTS RoleAgents")
        cursor.execute("DROP TABLE IF EXISTS Roles")
        conn.commit()
    except Exception as e:
        print(f"Error dropping tables: {e}")

    # Create fresh
    cursor.execute("""
    CREATE TABLE Roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE RoleAgents (
        role_id INTEGER,
        agent_id INTEGER,
        PRIMARY KEY (role_id, agent_id),
        FOREIGN KEY(role_id) REFERENCES Roles(id),
        FOREIGN KEY(agent_id) REFERENCES Agents(id)
    )
    """)
    
    # 5. Insert Default Roles
    cursor.execute("INSERT OR IGNORE INTO Roles (name, description) VALUES ('Admin', 'Full System Access')")
    cursor.execute("INSERT OR IGNORE INTO Roles (name, description) VALUES ('User', 'Standard User Access')")

    conn.commit()
    conn.close()
    print("Roles table recreated successfully.")

if __name__ == "__main__":
    wipe_and_recreate_roles()
