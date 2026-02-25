from execution_logger import DETAILED_LOG_FILE, log_router_decision, log_tool_call


def test_execution_logger_writes_file():
    log_router_decision({'selected_agent': 'file_manager', 'confidence': 'high'})
    log_tool_call('list_directory', {'directory_path': 'C:/tmp'}, {'success': True})

    assert DETAILED_LOG_FILE.exists()
    assert DETAILED_LOG_FILE.stat().st_size > 0
