
import sys
import sqlite3
import os

# Add project root
sys.path.append(r'd:\Works\GenericAgent\DesktopAgenticSystem')

from agents.registry import list_agents, _get_db_path
from settings.config_loader import load_settings_into_cda

print("Loading settings...")
load_settings_into_cda()

print("Triggering agent registration...")
agents = list_agents(return_all=True)
rag_found = any(a['name'] == 'rag_gen' for a in agents)

if rag_found:
    print("SUCCESS: 'rag_gen' found in agent list.")
else:
    print("FAILURE: 'rag_gen' NOT found in agent list.")

# Check Role Mappings
db_path = _get_db_path()
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("\nChecking Role Mappings for 'rag_gen'...")
cursor.execute("SELECT id FROM Agents WHERE name = 'rag_gen'")
row = cursor.fetchone()
if not row:
    print("FAILURE: 'rag_gen' ID not found in DB.")
else:
    agent_id = row[0]
    cursor.execute("""
        SELECT r.name 
        FROM RoleAgents ra 
        JOIN Roles r ON ra.role_id = r.id 
        WHERE ra.agent_id = ?
    """, (agent_id,))
    
    roles = [r[0] for r in cursor.fetchall()]
    print(f"Roles assigned to 'rag_gen': {roles}")
    
    if 'User' in roles and 'Admin' in roles:
        print("SUCCESS: Assigned to User and Admin roles.")
    else:
        print("WARNING: Role assignment incomplete.")

conn.close()
