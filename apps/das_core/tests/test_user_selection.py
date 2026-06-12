
import unittest
from unittest.mock import MagicMock
from core.executor import Executor
from core.common_data_area import CommonDataArea
from llm.base_client import BaseLLMClient

class MockLLM(BaseLLMClient):
    def __init__(self):
        self.last_prompt = ""
    
    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        # Return valid JSON to avoid retry logic errors
        return '''
        {
          "plan": { "current_step": "done", "revised_plan": "done" },
          "action": { "type": "complete" },
          "conversation_update": { "content": "done" },
          "reasoning": { "summary": "done" },
          "ui_feedback": { "status": "complete", "message": "done", "progress_hint": "done" }
        }
        '''

class TestUserSelection(unittest.TestCase):
    def setUp(self):
        self.cda = CommonDataArea() 
        self.cda.reset()
        self.mock_llm = MockLLM()
        self.executor = Executor(self.cda, self.mock_llm)

    def test_dynamic_user_context(self):
        # Set settings as if loaded from file
        self.cda.set_setting('current_user_id', 999)
        self.cda.set_setting('current_username', 'TestUser')
        
        # Execute any agent that uses {{UID}} in prompt (e.g. attendance_manager)
        try:
            self.executor.execute('attendance_manager', "Who am I?")
        except:
            pass # We don't care about execution failure, just prompt rendering
            
        # Verify prompt contained injected variables
        # Note: Executor converts int ID to str
        self.assertIn("USER_ID: 999", self.mock_llm.last_prompt)
        self.assertIn("USERNAME: TestUser", self.mock_llm.last_prompt)

if __name__ == '__main__':
    unittest.main()
