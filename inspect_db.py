import sqlite3
import os

DB_PATH = r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db'

def inspect():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables:", [t[0] for t in tables])

    for table in tables:
        t_name = table[0]
        print(f"\n--- Schema for {t_name} ---")
        cursor.execute(f"PRAGMA table_info({t_name})")
        columns = cursor.fetchall()
        for col in columns:
            print(col)

    conn.close()

if __name__ == "__main__":
    inspect()
