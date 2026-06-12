
import unittest
import sys
from unittest.mock import MagicMock, patch
import execution_logger

class TestUILogging(unittest.TestCase):
    def setUp(self):
        execution_logger._log_callback = None

    def test_log_propagation(self):
        mock_callback = MagicMock()
        execution_logger.register_log_callback(mock_callback)
        execution_logger.log_execution_step('TEST', 'This is a test log')
        mock_callback.assert_called_once_with('[TEST] This is a test log')

    
if __name__ == '__main__':
    unittest.main()
