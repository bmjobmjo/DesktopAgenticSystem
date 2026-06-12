import sqlite3
import tempfile

from agents import registry
from core.common_data_area import CommonDataArea
from core.db_schema import init_db


def test_leave_manager_registered_as_builtin():
    assert 'leave_manager' in registry.BUILTIN_AGENTS
    meta = registry.BUILTIN_AGENTS['leave_manager']
    assert meta['prompt_file'].exists()
    assert 'execute_sql' in meta['tool_names']


def test_init_db_creates_leave_tables_and_policies():
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}\\leave_test.db"
        cda.set_setting('sqlite_db_path', db_path)
        init_db()

        conn = sqlite3.connect(db_path, timeout=20
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='LeavePolicies'")
            assert cur.fetchone() is not None
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='LeaveRequests'")
            assert cur.fetchone() is not None
            cur.execute("SELECT leave_type, annual_limit, credit_mode FROM LeavePolicies ORDER BY leave_type")
            rows = cur.fetchall()
            assert ('casual', 12, 'monthly_accrual') in rows
            assert ('sick', 12, 'annual') in rows
        finally:
            conn.close()
