
import unittest
import shutil
import os
import sqlite3
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add project root
import sys
project_root = r"d:\Works\GenericAgent\DesktopAgenticSystem"
if project_root not in sys.path:
    sys.path.append(project_root)

from core.common_data_area import CommonDataArea
from core.db_schema import init_db, DB_PATH
from tools.embeddings.file_ingestion import ingest_file, search_files

class TestFileManagement(unittest.TestCase):
    def setUp(self):
        # Setup CDA with Mock LLM
        self.cda = CommonDataArea()
        self.mock_llm = MagicMock()
        self.mock_llm.generate.return_value = json.dumps({
            "description": "A test receipt for office supplies.",
            "is_expense": True,
            "amount": 123.45,
            "currency": "USD",
            "vendor": "Office Depot",
            "date": "2023-10-27",
            "category": "Office Supplies"
        })
        self.cda.set_runtime('llm_client', self.mock_llm)
        
        # Use temp DB
        self.temp_db_path = "test_file_mgmt.db"
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)
            
        # Patch DB path in modules - simplified by just creating new connection
        # But our tools import DB_PATH directly.
        # We need to monkeypatch DB_PATH in db_schema and ingestion module?
        # Or just run init_db(self.temp_db_path) if supported?
        # DB_PATH is constant. Monkeypatch it.
        
        # Patch global DB_PATH in sys.modules
        import core.db_schema
        core.db_schema.DB_PATH = self.temp_db_path
        
        import tools.embeddings.file_ingestion
        tools.embeddings.file_ingestion.DB_PATH = self.temp_db_path
        
        # Init DB
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        # Initialize schema manually or import init_logic?
        # Let's call init_db() but we need to pass cursor or path?
        # core.db_schema.init_db is hardcoded to connect to DB_PATH
        # But we just patched DB_PATH!
        core.db_schema.init_db()
        conn.close()
        
        # Tests temp dirs
        self.test_dir = Path("d:/Works/GenericAgent/DesktopAgenticSystem/tests/temp_source")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir = Path("d:/Works/GenericAgent/DesktopAgenticSystem/tests/temp_storage")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure setting for storage
        self.cda.set_setting('file_storage_path', str(self.storage_dir))
        
        # Create dummy file
        self.test_file = self.test_dir / "receipt_test.txt"
        self.test_file.write_text("Receipt from Office Depot\nAmount: $123.45\nDate: 2023-10-27\nItems: Pens, Paper.", encoding='utf-8')

    def tearDown(self):
        # Clean up files
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        if self.storage_dir.exists():
            shutil.rmtree(self.storage_dir)
        
        # Remove temp DB
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception as e:
                print(f"Failed to remove temp DB: {e}")

    def test_ingest_and_search(self):
        # 1. Ingest
        print("\nTesting Ingestion...")
        try:
            result = ingest_file(str(self.test_file), category='expense')
            print(f"Ingest Result: {result}")
            
            self.assertTrue(result['success'])
            self.assertTrue(result['is_expense'])
            
            # Verify Copy
            stored_path = Path(result['stored_path'])
            self.assertTrue(stored_path.exists())
            self.assertEqual(stored_path.parent, self.storage_dir)
            
        except Exception as e:
            self.fail(f"Ingestion failed: {e}")
            # We need to clean up strictly to allow re-runs
            conn = sqlite3.connect(self.temp_db_path)
            cursor = conn.cursor()
            # Add cleanup logic here if needed, e.g., delete partially ingested data
            conn.close()
        
        # Verify DB
        conn = sqlite3.connect(self.temp_db_path)
        cursor = conn.cursor()
        
        # Check Files
        cursor.execute("SELECT id, description, file_path FROM Files WHERE filename = ?", (self.test_file.name,))
        file_row = cursor.fetchone()
        self.assertIsNotNone(file_row)
        self.assertIn("receipt", file_row[1])
        self.assertEqual(str(file_row[2]), str(stored_path))
        
        # Check Expenses
        cursor.execute("SELECT amount, vendor FROM Expenses WHERE file_id = ?", (file_row[0],))
        expense_row = cursor.fetchone()
        self.assertIsNotNone(expense_row)
        self.assertEqual(expense_row[0], 123.45)
        self.assertEqual(expense_row[1], 'Office Depot')
        
        # Check Embeddings
        cursor.execute("SELECT COUNT(*) FROM FileEmbeddings WHERE file_id = ?", (file_row[0],))
        count = cursor.fetchone()[0]
        self.assertGreater(count, 1) # Description + Content
        
        # Check specific description chunk
        cursor.execute("SELECT chunk_type FROM FileEmbeddings WHERE file_id = ? AND chunk_type = 'description'", (file_row[0],))
        self.assertIsNotNone(cursor.fetchone())
        
        conn.close()

        # 2. Search
        print("Testing Search...")
        try:
            results = search_files("receipt for office supplies", top_k=1)
            print(f"Search Results: {results}")
            
            self.assertTrue(len(results) > 0)
            self.assertEqual(results[0]['filename'], self.test_file.name)
            self.assertIn('match_type', results[0])
        except Exception as e:
            self.fail(f"Search failed: {e}")

if __name__ == "__main__":
    unittest.main()
