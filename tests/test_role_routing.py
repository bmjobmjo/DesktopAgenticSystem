import sqlite3
import pytest
from pathlib import Path
from agents.registry import list_agents, _get_db_path
from core.db_schema import init_db

from core.common_data_area import CommonDataArea

def test_role_based_routing():
    # Setup CDA to point to correct DB
    cda = CommonDataArea()
    cda.set_setting('sqlite_db_path', r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db')
    
    # Ensure DB is initialized
    init_db()
    
    db_path = _get_db_path()
    print(f"Test using DB: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Setup Test Data
    print("Setting up test data...")
    
    # Create Test Role
    cursor.execute("INSERT OR IGNORE INTO Roles (name, description) VALUES ('TestRole', 'For testing only')")
    cursor.execute("SELECT id FROM Roles WHERE name = 'TestRole'")
    role_id = cursor.fetchone()[0]
    
    # Create Test User
    test_email = "test_user@example.com"
    cursor.execute("DELETE FROM Users WHERE email = ?", (test_email,))
    cursor.execute("INSERT INTO Users (email, full_name, role_id) VALUES (?, ?, ?)", (test_email, "Test User", role_id))
    
    # Create Test Agent
    agent_name = "secret_agent"
    cursor.execute("INSERT OR IGNORE INTO Agents (name, description, is_active) VALUES (?, 'Top Secret', 1)", (agent_name,))
    cursor.execute("SELECT id FROM Agents WHERE name = ?", (agent_name,))
    agent_id = cursor.fetchone()[0]
    
    # Map Agent to Role
    cursor.execute("DELETE FROM RoleAgents WHERE role_id = ? AND agent_id = ?", (role_id, agent_id))
    cursor.execute("INSERT INTO RoleAgents (role_id, agent_id) VALUES (?, ?)", (role_id, agent_id))
    
    conn.commit()
    
    # 2. Verify Positive Case (User has access)
    print(f"Testing access for {test_email}...")
    agents = list_agents(test_email)
    agent_names = [a['name'] for a in agents]
    print(f"Agents found: {agent_names}")
    
    assert agent_name in agent_names
    
    # 3. Verify Negative Case (User has NO access)
    print("Testing access for unauthorized user...")
    unauthorized_email = "random@example.com"
    agents = list_agents(unauthorized_email)
    print(f"Agents found for unauthorized: {agents}")
    
    assert len(agents) == 0
    
    # 4. Cleanup
    cursor.execute("DELETE FROM RoleAgents WHERE role_id = ?", (role_id,))
    cursor.execute("DELETE FROM Users WHERE email = ?", (test_email,))
    cursor.execute("DELETE FROM Roles WHERE id = ?", (role_id,))
    cursor.execute("DELETE FROM Agents WHERE id = ?", (agent_id,))
    conn.commit()
    conn.close()
    
    print("Verification test passed!")

if __name__ == "__main__":
    test_role_based_routing()
