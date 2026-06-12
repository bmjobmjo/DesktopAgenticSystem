import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.router import Router

class TestRouterFileHandling(unittest.TestCase):
    def setUp(self):
        # We need to mock CommonDataArea properly before Router init
        patcher = patch('core.router.CommonDataArea')
        self.MockCDA = patcher.start()
        self.addCleanup(patcher.stop)
        
        # Setup mock runtime and LLM
        self.mock_cda_instance = self.MockCDA.return_value
        self.mock_llm = MagicMock()
        self.mock_cda_instance.get_runtime.return_value = self.mock_llm
        self.mock_cda_instance.get_setting.return_value = 'test_user'
        
        # Init Router with mocked CDA
        self.router = Router(cda=self.mock_cda_instance)

    @patch('core.router.list_agents')
    @patch('core.router.list_tools')
    def test_file_ingestion_routing(self, mock_list_tools, mock_list_agents):
        # Setup mocks
        mock_list_agents.return_value = [{'name': 'ExpenseAgent', 'description': 'Handles expenses and receipts.'}]
        mock_list_tools.return_value = {'file_embedding_tool': lambda x: None}
        
        # Mock LLM response for a generic file
        self.mock_llm.generate.return_value = json.dumps([
            {
                "type": "tool_call",
                "tool_name": "file_embedding_tool",
                "parameters": {"file_path": "test_doc.pdf"},
                "reason": "Ingesting user file.",
                "confidence": "high",
                "priority": 1
            }
        ])

        # Verify validation directly
        from validation.router_validator import validate_router_response
        data = json.loads(self.mock_llm.generate.return_value)
        validate_router_response(data)

        # Test
        print("Running test_file_ingestion_routing...")
        try:
            files = [Path("test_doc.pdf")]
            tasks = self.router.route("Here is a document", input_files=files)
            print(f"Tasks returned: {tasks}")
        except Exception as e:
            print(f"Test crashed with: {e}")
            import traceback
            traceback.print_exc()
            raise e

        # Verify
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['type'], 'tool_call')
        self.assertEqual(tasks[0]['tool_name'], 'file_embedding_tool')
        self.assertEqual(tasks[0]['parameters']['file_path'], 'test_doc.pdf')

    @patch('core.router.list_agents')
    @patch('core.router.list_tools')
    def test_receipt_routing(self, mock_list_tools, mock_list_agents):
        # Setup mocks
        mock_list_agents.return_value = [{'name': 'ExpenseAgent', 'description': 'Handles expenses and receipts.'}]
        mock_list_tools.return_value = {'file_embedding_tool': lambda x: None}
        
        # Mock LLM response for a receipt (Ingest + Agent)
        self.mock_llm.generate.return_value = json.dumps([
            {
                "type": "tool_call",
                "tool_name": "file_embedding_tool",
                "parameters": {"file_path": "receipt.jpg"},
                "reason": "Ingesting file.",
                "confidence": "high",
                "priority": 1
            },
            {
                "type": "continue",
                "selected_agent": "ExpenseAgent",
                "instruction": "Process the receipt image.",
                "reason": "Receipt processing required.",
                "confidence": "high",
                "priority": 2
            }
        ])

        # Test
        print("Running test_receipt_routing...")
        try:
            files = [Path("receipt.jpg")]
            tasks = self.router.route("Process this receipt", input_files=files)
            print(f"Tasks returned: {tasks}")
        except Exception as e:
            print(f"Test crashed with: {e}")
            import traceback
            traceback.print_exc()
            raise e

        # Verify
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]['type'], 'tool_call')
        self.assertEqual(tasks[1]['selected_agent'], 'ExpenseAgent')

if __name__ == '__main__':
    unittest.main()
