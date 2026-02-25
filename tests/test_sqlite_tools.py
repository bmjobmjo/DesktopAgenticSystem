
import unittest
import sqlite3
import os
from pathlib import Path
from tools.sqlite_tools import execute_sql
from core.common_data_area import CommonDataArea

class TestSQLiteTools(unittest.TestCase):
    def setUp(self):
        self.test_db = 'test_backend.db'
        # Set CDA setting for test
        cda = CommonDataArea()
        cda.set_setting('sqlite_db_path', self.test_db)
        
        # Remove if exists
        try:
            if os.path.exists(self.test_db):
                os.remove(self.test_db)
        except PermissionError:
            pass

    def tearDown(self):
        # Clean up
        try:
            if os.path.exists(self.test_db):
                os.remove(self.test_db)
        except PermissionError:
            pass

    def test_execute_sql_flow(self):
        # 1. Create Table
        create_query = "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"
        results = execute_sql([create_query])
        # Check result. execution_sql returns list of results.
        # For CREATE, it returns "Success..." string.
        self.assertTrue(any("Success" in str(r) for r in results))

        # 2. Insert Data
        insert_queries = [
            "INSERT INTO users (name, age) VALUES ('Alice', 30)",
            "INSERT INTO users (name, age) VALUES ('Bob', 25)"
        ]
        results = execute_sql(insert_queries)
        self.assertEqual(len(results), 2)
        self.assertTrue(all("Success" in str(r) for r in results))

        # 3. Select Data
        select_query = "SELECT name, age FROM users ORDER BY age"
        results = execute_sql([select_query])
        
        rows = results[0]
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 2)
        # rows are dicts
        self.assertEqual(rows[0]['name'], 'Bob') 
        self.assertEqual(rows[0]['age'], 25)
        self.assertEqual(rows[1]['name'], 'Alice')
        self.assertEqual(rows[1]['age'], 30)

    def test_execute_sql_error(self):
        with self.assertRaises(RuntimeError):
            execute_sql(["SELECT * FROM non_existent_table"])

if __name__ == '__main__':
    unittest.main()
