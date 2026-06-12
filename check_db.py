import sqlite3

def check_db():
    conn = sqlite3.connect('d:\\Works\\GenericAgent\\DesktopAgenticSystem\\backend.db')
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    print("Tables:", tables)

    if 'SystemSettings' in tables:
        cur.execute("SELECT setting_key, setting_value FROM SystemSettings")
        print("SystemSettings:", cur.fetchall())
    elif 'Settings' in tables:
        cur.execute("SELECT * FROM Settings")
        print("Settings:", cur.fetchall())

check_db()
