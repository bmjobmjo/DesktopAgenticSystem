
import unittest
from unittest.mock import MagicMock
from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.router import Router

class TestControllerErrorHandling(unittest.TestCase):
    def setUp(self):
        self.cda = CommonDataArea()
        self.cda.reset()
        
    def test_controller_catches_exception(self):
        # Mock Router to raise an exception
        mock_router = MagicMock(spec=Router)
        mock_router.route.side_effect = RuntimeError("Simulated Timeout")
        
        executor = MagicMock()
        
        controller = Controller(self.cda, mock_router, executor)
        
        # Should not raise
        response = controller.handle_user_message('Hi')
        
        self.assertEqual(response.status, 'error')
        self.assertIn('System Error: Simulated Timeout', response.content)

if __name__ == '__main__':
    unittest.main()
