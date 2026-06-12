import sqlite3
import pytest
from pathlib import Path
from llm.mock_client import MockLLMClient, _get_db_path
from core.db_schema import init_db

def test_llm_logging():
    # Ensure DB is initialized
    init_db()
    
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get initial count
    cursor.execute("SELECT COUNT(*) FROM LLMUsage")
    initial_count = cursor.fetchone()[0]
    
    # Trigger LLM call
    client = MockLLMClient()
    prompt = "Test Prompt"
    user_prompt = "Hello AI"
    agent_name = "TestAgent"
    
    client.generate(prompt, agent_name=agent_name, user_prompt=user_prompt)
    
    # Check new count
    cursor.execute("SELECT * FROM LLMUsage ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    
    assert row is not None
    assert row[2] == user_prompt # user_prompt
    assert row[3] == agent_name  # agent_name
    assert row[4] == prompt      # prompt
    assert row[5] is not None    # response
    assert isinstance(row[6], int) # token_in
    assert isinstance(row[7], int) # token_out
    assert isinstance(row[8], int) # total_tokens
    
    conn.close()
    print("Verification test passed!")

if __name__ == "__main__":
    test_llm_logging()
