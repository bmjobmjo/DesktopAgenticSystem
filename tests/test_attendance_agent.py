
import unittest
from unittest.mock import MagicMock, patch
from core.executor import Executor
from core.common_data_area import CommonDataArea
from llm.base_client import BaseLLMClient
from agents.registry import AGENTS

class MockLLM(BaseLLMClient):
    def __init__(self):
        self.last_prompt = ""
        self.call_count = 0
    
    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        self.call_count += 1
        
        if self.call_count == 1:
            # First call: Request Tool Execution
            return '''
            {
              "plan": {
                 "original_plan": ["Clock in user"],
                 "current_step": "Clock in user",
                 "revised_plan": "Clock in user"
              },
              "action": {
                "type": "tool_call",
                "tool_request": {
                   "tool_name": "execute_sql",
                   "parameters": {
                      "queries": ["INSERT INTO Attendance (user_id, check_in_time) VALUES (101, '2023-01-01 12:00:00')"]
                   }
                }
              },
              "conversation_update": {
                  "content": "Clocking you in..."
              },
              "reasoning": {
                  "summary": "User requested check-in."
              },
              "ui_feedback": {
                  "status": "working",
                  "message": "Clocking in...",
                  "progress_hint": "Step 1"
              }
            }
            '''
        else:
            # Second call: Completion
            return '''
            {
              "plan": {
                 "original_plan": ["Clock in user"],
                 "current_step": "Clock in user",
                 "revised_plan": "Task Completed"
              },
              "action": {
                "type": "request_user_input"
              },
              "conversation_update": {
                  "content": "Clocked in successfully."
              },
              "reasoning": {
                  "summary": "Task completed."
              },
              "ui_feedback": {
                  "status": "completed",
                  "message": "Done.",
                  "progress_hint": "Step 1"
              }
            }
            '''

class TestAttendanceAgent(unittest.TestCase):
    def setUp(self):
        self.cda = CommonDataArea() 
        self.cda.reset()
        # Create Attendance table for testing
        from tools.sqlite_tools import execute_sql
        execute_sql(["CREATE TABLE IF NOT EXISTS Attendance (user_id INTEGER, check_in_time TEXT)"])
        
        self.mock_llm = MockLLM()
        self.executor = Executor(self.cda, self.mock_llm)

    def test_context_injection(self):
        # We need to ensure 'attendance_manager' is in registry (it should be real)
        if 'attendance_manager' not in AGENTS:
             # If running in isolation where registry isn't updated? 
             # Registry.py is imported in executor.py, so it should be fine if file was updated.
             pass

        user_prompt = "Clock me in"
        
        # Execute
        try:
            result = self.executor.execute('attendance_manager', user_prompt)
        except Exception as e:
            with open('error.log', 'w') as f:
                f.write(str(e))
            raise e
        
        # Verify prompt contained injected variables
        self.assertIn("USER_ID: 101", self.mock_llm.last_prompt)
        self.assertIn("USERNAME: User", self.mock_llm.last_prompt)
        # Date time is dynamic, just check the tag is replaced
        self.assertNotIn("{{DATE_TIME}}", self.mock_llm.last_prompt) # Should be replaced
        self.assertIn("SYSTEM_TIME:", self.mock_llm.last_prompt)

    def test_execution_flow(self):
        result = self.executor.execute('attendance_manager', "Clock me in")
        self.assertEqual(result.content, "Clocked in successfully.")
        self.assertEqual(result.status, "request_user_input") 
        # Actually Executor returns final result. The mock returned tool_call, 
        # so Executor would execute tool and loop. 
        # But MockLLM always returns the *same* response, so it would loop infinitely if we don't handle that.
        # Wait, Executor loop breaks if Max Turns is reached or status complete.
        # The mock response above has action type 'tool_call'. Executor will run it, then call LLM again with result.
        # IF LLM returns SAME response, it will loop.
        # For this simple test, we just want to verify Prompt Rendering (first step).
        # We can inspect the first prompt.
        pass

if __name__ == '__main__':
    unittest.main()
