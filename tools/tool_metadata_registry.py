"""Central metadata registry for user-facing tools."""

from __future__ import annotations

TOOL_METADATA = {
    'list_tools': {
        'description': 'List all currently registered tool names from the live tool registry.',
        'parameters': [
            {'name': 'force_refresh', 'type': 'bool', 'required': False, 'description': 'When true, rebuild the registry from disk before listing tools.'},
        ],
        'output_schema': 'Dict[str, Callable]',
        'example_call': '{"tool_name": "list_tools", "parameters": {"force_refresh": true}}',
    },
    'list_tool_metadata': {
        'description': 'Return detailed metadata for tools stored in ToolList, optionally filtered by tool name.',
        'parameters': [
            {'name': 'cda', 'type': 'CommonDataArea | None', 'required': False, 'description': 'Optional runtime settings container. Usually omitted by agents.'},
            {'name': 'names', 'type': 'list[str] | None', 'required': False, 'description': 'Optional subset of tool names to return.'},
        ],
        'output_schema': 'List[Dict[str, Any]]',
        'example_call': '{"tool_name": "list_tool_metadata", "parameters": {"names": ["export_file", "render_image"]}}',
    },
    'copy_file': {
        'description': 'Copy a file from one accessible path to another accessible path.',
        'parameters': [
            {'name': 'source_path', 'type': 'str', 'required': True, 'description': 'Existing source file path inside accessible directories.'},
            {'name': 'destination_path', 'type': 'str', 'required': True, 'description': 'Target file path inside accessible directories.'},
        ],
        'output_schema': 'Dict with success flag and copied source/destination paths.',
        'example_call': '{"tool_name": "copy_file", "parameters": {"source_path": "C:/Users/Bijumon/Downloads/a.txt", "destination_path": "C:/Users/Bijumon/Downloads/archive/a.txt"}}',
    },
    'move_file': {
        'description': 'Move a file from one accessible path to another accessible path.',
        'parameters': [
            {'name': 'source_path', 'type': 'str', 'required': True, 'description': 'Existing source file path inside accessible directories.'},
            {'name': 'destination_path', 'type': 'str', 'required': True, 'description': 'Target file path inside accessible directories.'},
        ],
        'output_schema': 'Dict with success flag and moved source/destination paths.',
        'example_call': '{"tool_name": "move_file", "parameters": {"source_path": "C:/Users/Bijumon/Downloads/a.txt", "destination_path": "C:/Users/Bijumon/Downloads/processed/a.txt"}}',
    },
    'inspect_file': {
        'description': 'Read file metadata such as size, modification time, and extension for an accessible file.',
        'parameters': [
            {'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Absolute file path inside accessible directories.'},
        ],
        'output_schema': 'Dict with success flag and file metadata.',
        'example_call': '{"tool_name": "inspect_file", "parameters": {"file_path": "C:/Users/Bijumon/Downloads/report.pdf"}}',
    },
    'list_directory': {
        'description': 'List the entries in an accessible directory.',
        'parameters': [
            {'name': 'directory_path', 'type': 'str', 'required': True, 'description': 'Absolute directory path inside accessible directories.'},
        ],
        'output_schema': 'Dict with success flag and directory entries.',
        'example_call': '{"tool_name": "list_directory", "parameters": {"directory_path": "C:/Users/Bijumon/Downloads"}}',
    },
    'read_file': {
        'description': 'Read text content from a plain-text file or extract text from a PDF file.',
        'parameters': [
            {'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Absolute file path inside accessible directories.'},
        ],
        'output_schema': 'Dict with success flag, file type, and extracted content.',
        'example_call': '{"tool_name": "read_file", "parameters": {"file_path": "C:/Users/Bijumon/Downloads/notes.txt"}}',
    },
    'execute_sql': {
        'description': 'Execute one or more SQL statements against the configured SQLite database.',
        'parameters': [
            {'name': 'queries', 'type': 'list[str] | str', 'required': True, 'description': 'Single SQL statement or a list of SQL statements to run in order.'},
        ],
        'output_schema': 'List of query results on success, or an error payload with failure details.',
        'example_call': '{"tool_name": "execute_sql", "parameters": {"queries": ["SELECT name FROM Users LIMIT 5"]}}',
    },
    'get_database_schema': {
        'description': 'Return the current SQLite schema, including tables and columns.',
        'parameters': [],
        'output_schema': 'Dict with success flag and schema map.',
        'example_call': '{"tool_name": "get_database_schema", "parameters": {}}',
    },
    'list_available_tools': {
        'description': 'Return a summarized list of all tools currently registered in code.',
        'parameters': [],
        'output_schema': 'Dict with success flag and tool summaries.',
        'example_call': '{"tool_name": "list_available_tools", "parameters": {}}',
    },
    'read_agent_template': {
        'description': 'Read the base agent prompt template used for creating new agents.',
        'parameters': [],
        'output_schema': 'Dict with success flag and template text.',
        'example_call': '{"tool_name": "read_agent_template", "parameters": {}}',
    },
    'save_new_agent': {
        'description': 'Create or update an agent definition in the database and assign it to the Admin role.',
        'parameters': [
            {'name': 'name', 'type': 'str', 'required': True, 'description': 'Unique snake_case agent name.'},
            {'name': 'description', 'type': 'str', 'required': True, 'description': 'Short summary of what the agent does.'},
            {'name': 'prompt_content', 'type': 'str', 'required': True, 'description': 'Full system prompt content for the agent.'},
        ],
        'output_schema': 'Dict with success flag and save result message.',
        'example_call': '{"tool_name": "save_new_agent", "parameters": {"name": "expense_helper", "description": "Manage expense workflows", "prompt_content": "..."}}',
    },
    'validate_schedule': {
        'description': 'Validate a natural-language schedule request and return parsed schedule fields.',
        'parameters': [
            {'name': 'nl_request', 'type': 'str', 'required': True, 'description': 'Natural-language schedule request.'},
        ],
        'output_schema': 'Dict with success flag and parsed schedule details.',
        'example_call': '{"tool_name": "validate_schedule", "parameters": {"nl_request": "Run every weekday at 9 AM"}}',
    },
    'create_schedule': {
        'description': 'Create a new schedule record, optionally parsing a natural-language request first.',
        'parameters': [
            {'name': 'nl_request', 'type': 'str', 'required': False, 'description': 'Optional natural-language schedule request.'},
            {'name': 'title', 'type': 'str', 'required': False, 'description': 'Human-readable schedule title.'},
            {'name': 'task_prompt', 'type': 'str', 'required': False, 'description': 'Task prompt to execute when the schedule runs.'},
            {'name': 'schedule_type', 'type': 'str', 'required': False, 'description': 'hourly, daily, weekly, monthly, or other.'},
            {'name': 'interval_minutes', 'type': 'int', 'required': False, 'description': 'Interval in minutes for hourly-like schedules.'},
            {'name': 'run_hour', 'type': 'int', 'required': False, 'description': 'Hour of day for scheduled runs.'},
            {'name': 'run_minute', 'type': 'int', 'required': False, 'description': 'Minute of hour for scheduled runs.'},
            {'name': 'run_day_of_week', 'type': 'int', 'required': False, 'description': 'Day of week for weekly schedules, 0-6.'},
            {'name': 'run_day_of_month', 'type': 'int', 'required': False, 'description': 'Day of month for monthly schedules, 1-31.'},
            {'name': 'is_enabled', 'type': 'bool', 'required': False, 'description': 'Whether the schedule starts enabled.'},
            {'name': 'owner', 'type': 'str', 'required': False, 'description': 'Owner user id or label.'},
            {'name': 'created_by', 'type': 'str', 'required': False, 'description': 'Creator user id.'},
        ],
        'output_schema': 'Dict with success flag, schedule id, and next run time.',
        'example_call': '{"tool_name": "create_schedule", "parameters": {"nl_request": "Every weekday at 9 AM send the daily report"}}',
    },
    'list_schedules': {
        'description': 'List schedules stored in the database.',
        'parameters': [
            {'name': 'include_disabled', 'type': 'bool', 'required': False, 'description': 'When false, only enabled schedules are returned.'},
            {'name': 'limit', 'type': 'int', 'required': False, 'description': 'Maximum number of schedules to return.'},
        ],
        'output_schema': 'Dict with success flag, count, and schedule rows.',
        'example_call': '{"tool_name": "list_schedules", "parameters": {"include_disabled": false, "limit": 50}}',
    },
    'update_schedule': {
        'description': 'Update an existing schedule record by id.',
        'parameters': [
            {'name': 'schedule_id', 'type': 'int', 'required': True, 'description': 'Schedule id to update.'},
            {'name': 'title', 'type': 'str', 'required': False, 'description': 'Updated title.'},
            {'name': 'task_prompt', 'type': 'str', 'required': False, 'description': 'Updated task prompt.'},
            {'name': 'schedule_type', 'type': 'str', 'required': False, 'description': 'Updated schedule type.'},
            {'name': 'interval_minutes', 'type': 'int', 'required': False, 'description': 'Updated interval in minutes.'},
            {'name': 'run_hour', 'type': 'int', 'required': False, 'description': 'Updated run hour.'},
            {'name': 'run_minute', 'type': 'int', 'required': False, 'description': 'Updated run minute.'},
            {'name': 'run_day_of_week', 'type': 'int', 'required': False, 'description': 'Updated weekly day.'},
            {'name': 'run_day_of_month', 'type': 'int', 'required': False, 'description': 'Updated monthly day.'},
            {'name': 'is_enabled', 'type': 'bool | None', 'required': False, 'description': 'Optional enabled flag.'},
            {'name': 'owner', 'type': 'str', 'required': False, 'description': 'Updated owner.'},
        ],
        'output_schema': 'Dict with success flag and updated schedule id.',
        'example_call': '{"tool_name": "update_schedule", "parameters": {"schedule_id": 3, "run_hour": 10, "run_minute": 30}}',
    },
    'delete_schedule': {
        'description': 'Delete a schedule by id.',
        'parameters': [
            {'name': 'schedule_id', 'type': 'int', 'required': True, 'description': 'Schedule id to delete.'},
        ],
        'output_schema': 'Dict with success flag and delete count.',
        'example_call': '{"tool_name": "delete_schedule", "parameters": {"schedule_id": 3}}',
    },
    'send_telegram_message': {
        'description': 'Send a text message through the running Telegram channel service.',
        'parameters': [
            {'name': 'message', 'type': 'str', 'required': True, 'description': 'Text message to send.'},
            {'name': 'chat_id', 'type': 'str', 'required': False, 'description': 'Telegram chat id when known.'},
            {'name': 'user_id', 'type': 'str', 'required': False, 'description': 'Internal user id used to resolve a mapped Telegram chat.'},
        ],
        'output_schema': 'Dict with success flag, target chat id, and gateway result.',
        'example_call': '{"tool_name": "send_telegram_message", "parameters": {"message": "Hello from the agent", "chat_id": "123456789"}}',
    },
    'send_telegram_file': {
        'description': 'Send a file through the running Telegram channel service.',
        'parameters': [
            {'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Absolute path to the file to send.'},
            {'name': 'caption', 'type': 'str', 'required': False, 'description': 'Optional caption text.'},
            {'name': 'chat_id', 'type': 'str', 'required': False, 'description': 'Telegram chat id when known.'},
            {'name': 'user_id', 'type': 'str', 'required': False, 'description': 'Internal user id used to resolve a mapped Telegram chat.'},
        ],
        'output_schema': 'Dict with success flag, target chat id, file path, and gateway result.',
        'example_call': '{"tool_name": "send_telegram_file", "parameters": {"file_path": "D:/IVA/generated/report.pdf", "caption": "Latest report", "chat_id": "123456789"}}',
    },
    'ingest_file': {
        'description': 'Copy a file into managed storage, extract content, and index it for retrieval.',
        'parameters': [
            {'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Source file path to ingest.'},
            {'name': 'category', 'type': 'str | None', 'required': False, 'description': 'Optional business category label.'},
            {'name': 'user_description', 'type': 'str | None', 'required': False, 'description': 'Optional extra context used during ingestion.'},
        ],
        'output_schema': 'Dict with success flag and stored file/indexing details.',
        'example_call': '{"tool_name": "ingest_file", "parameters": {"file_path": "C:/Users/Bijumon/Downloads/policy.pdf", "category": "policy"}}',
    },
    'file_ingestion': {
        'description': 'Alias for ingest_file kept for compatibility with existing prompts and routes.',
        'parameters': [
            {'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Source file path to ingest.'},
            {'name': 'category', 'type': 'str | None', 'required': False, 'description': 'Optional business category label.'},
            {'name': 'user_description', 'type': 'str | None', 'required': False, 'description': 'Optional extra context used during ingestion.'},
        ],
        'output_schema': 'Dict with success flag and stored file/indexing details.',
        'example_call': '{"tool_name": "file_ingestion", "parameters": {"file_path": "C:/Users/Bijumon/Downloads/policy.pdf"}}',
    },
    'file_embedding_tool': {
        'description': 'Alias for ingest_file used by file-processing prompts that require ingestion first.',
        'parameters': [
            {'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Source file path to ingest.'},
            {'name': 'category', 'type': 'str | None', 'required': False, 'description': 'Optional business category label.'},
            {'name': 'user_description', 'type': 'str | None', 'required': False, 'description': 'Optional extra context used during ingestion.'},
        ],
        'output_schema': 'Dict with success flag and stored file/indexing details.',
        'example_call': '{"tool_name": "file_embedding_tool", "parameters": {"file_path": "C:/Users/Bijumon/Downloads/policy.pdf"}}',
    },
    'search_files': {
        'description': 'Search previously ingested files using semantic retrieval.',
        'parameters': [
            {'name': 'query', 'type': 'str', 'required': True, 'description': 'Search question or retrieval query.'},
            {'name': 'top_k', 'type': 'int', 'required': False, 'description': 'Maximum number of matches to return.'},
            {'name': 'threshold', 'type': 'float', 'required': False, 'description': 'Minimum similarity threshold.'},
        ],
        'output_schema': 'List of matching file chunks and metadata.',
        'example_call': '{"tool_name": "search_files", "parameters": {"query": "leave policy", "top_k": 5}}',
    },
    'export_file': {
        'description': 'Create a document file under the configured file storage path as CSV, XLSX, DOCX, or PDF.',
        'parameters': [
            {'name': 'output_filename', 'type': 'str', 'required': True, 'description': 'Target file name. The tool writes it under file_storage_path/subfolder.'},
            {'name': 'format', 'type': 'str', 'required': True, 'description': 'One of csv, xlsx, docx, or pdf.'},
            {'name': 'mode', 'type': 'str', 'required': False, 'description': 'raw for direct export or template for template fill.'},
            {'name': 'title', 'type': 'str | None', 'required': False, 'description': 'Optional document title.'},
            {'name': 'template_path', 'type': 'str | None', 'required': False, 'description': 'Existing template file path when mode=template.'},
            {'name': 'data', 'type': 'dict | None', 'required': False, 'description': 'Placeholder values used in templates or content blocks.'},
            {'name': 'columns', 'type': 'list[dict] | None', 'required': False, 'description': 'Column definitions for tabular export.'},
            {'name': 'rows', 'type': 'list[dict] | None', 'required': False, 'description': 'Row records for table export.'},
            {'name': 'sections', 'type': 'list[dict] | None', 'required': False, 'description': 'Narrative content blocks used mainly for DOCX/PDF.'},
            {'name': 'sheet_name', 'type': 'str | None', 'required': False, 'description': 'Worksheet name for XLSX output.'},
            {'name': 'subfolder', 'type': 'str', 'required': False, 'description': 'Subfolder under file_storage_path where the file will be created.'},
            {'name': 'options', 'type': 'dict | None', 'required': False, 'description': 'Optional format-specific flags stored in metadata.'},
        ],
        'output_schema': 'Dict with success flag, created file path, format, bytes written, warnings, and metadata.',
        'example_call': '{"tool_name": "export_file", "parameters": {"output_filename": "attendance_report", "format": "xlsx", "subfolder": "reports", "columns": [{"key": "name", "header": "Name"}, {"key": "status", "header": "Status"}], "rows": [{"name": "Anu", "status": "Present"}]}}',
    },
    'render_image': {
        'description': 'Render an image file under the configured file storage path from a template or a canvas definition.',
        'parameters': [
            {'name': 'output_filename', 'type': 'str', 'required': True, 'description': 'Target image file name. The tool writes it under file_storage_path/subfolder.'},
            {'name': 'format', 'type': 'str', 'required': False, 'description': 'One of png, jpg, jpeg, or webp.'},
            {'name': 'mode', 'type': 'str', 'required': False, 'description': 'template to draw on an existing image or canvas for a blank image.'},
            {'name': 'template_path', 'type': 'str | None', 'required': False, 'description': 'Existing image path when mode=template.'},
            {'name': 'data', 'type': 'dict | None', 'required': False, 'description': 'Placeholder values used by text and table elements.'},
            {'name': 'elements', 'type': 'list[dict] | None', 'required': False, 'description': 'Canvas elements such as text, rect, image, or table.'},
            {'name': 'width', 'type': 'int | None', 'required': False, 'description': 'Canvas width when mode=canvas.'},
            {'name': 'height', 'type': 'int | None', 'required': False, 'description': 'Canvas height when mode=canvas.'},
            {'name': 'background', 'type': 'dict | None', 'required': False, 'description': 'Background color or overlay settings.'},
            {'name': 'subfolder', 'type': 'str', 'required': False, 'description': 'Subfolder under file_storage_path where the image will be created.'},
            {'name': 'options', 'type': 'dict | None', 'required': False, 'description': 'Optional render settings stored in metadata.'},
        ],
        'output_schema': 'Dict with success flag, created image path, dimensions, warnings, and metadata.',
        'example_call': '{"tool_name": "render_image", "parameters": {"output_filename": "certificate", "format": "png", "mode": "canvas", "subfolder": "images", "width": 1200, "height": 675, "elements": [{"type": "text", "x": 120, "y": 100, "width": 600, "height": 50, "text": "{{name}}", "font_size": 28}], "data": {"name": "Bijumon"}}}',
    },
}
