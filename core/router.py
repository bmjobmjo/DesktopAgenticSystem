"""Router component for agent selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agents.registry import ROUTER_PROMPT_PATH, list_agents
from tools.tool_registry import list_tool_metadata
from core.common_data_area import CommonDataArea
from llm.mock_client import MockLLMClient
from llm.response_validator import InvalidJSONError, parse_json
from prompts.renderer import render
from execution_logger import log_router_decision, log_prompt, log_execution_step, log_chat_history, ExecutionLogger
from core.llm_attachments import build_llm_attachments, extract_attachment_paths, format_attachments_for_prompt
from validation.router_validator import SchemaError, validate_router_response


class RouterError(RuntimeError):
    pass


class Router:
    def __init__(self, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()

    @staticmethod
    def _normalize_file_routes(data: List[Dict[str, Any]], attachment_paths: List[str]) -> List[Dict[str, Any]]:
        if not attachment_paths:
            return data

        has_incoming = any(
            isinstance(item, dict)
            and str(item.get('type', '') or '') == 'agent_call'
            and str(item.get('selected_agent', '') or '') == 'incoming_file_processor'
            for item in data
        )
        if has_incoming:
            return data

        incoming_task: Dict[str, Any] = {
            'type': 'agent_call',
            'selected_agent': 'incoming_file_processor',
            "instruction": "First inspect/process the attached file using the exact path from [ATTACHED FILES] and the user's request.",
            'confidence': 'high',
            'reason': 'Attached files must always go to the dedicated file processor first.',
            'response_to_user': 'I am processing the attached file.',
            'priority': 1,
        }

        downstream: List[Dict[str, Any]] = []
        for idx, item in enumerate(data, start=2):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get('type', '') or '').strip()
            if item_type not in ('agent_call', 'tool_call', 'continue'):
                continue
            cloned = dict(item)
            cloned['priority'] = idx
            if item_type == 'agent_call':
                instruction = str(cloned.get('instruction', '') or '').strip()
                prefix = 'After incoming_file_processor runs, continue using the same attached file path(s), the same file content, and the file processor findings.'
                cloned['instruction'] = f"{prefix} {instruction}".strip()
            downstream.append(cloned)

        return [incoming_task, *downstream] if downstream else [incoming_task]

    def _emit_trace(self, event_type: str, payload: Dict[str, Any]) -> None:
        handler = self.cda.get_runtime('executor_trace_handler')
        if callable(handler):
            try:
                import copy
                handler(event_type, copy.deepcopy(payload))
            except Exception:
                # Trace callback failures should not break execution flow.
                pass

    def route(
        self, 
        user_prompt: str, 
        input_files: List[Path] | None = None,
        tool_output: str | None = None,
        chat_history: str = '', 
        session_ctx: Any | None = None,
        interface_type: str = 'UI',
        max_retries: int = 2
    ) -> List[Dict]:
        """
        Determines the best course of action for a user request.
        
        This method:
        1. Compiles a list of available agents based on the user's identity/role.
        2. Compiles a list of available tools for direct execution.
        3. Constructs a prompt including the user request, file context, and any previous tool output.
        4. Queries the LLM to decide whether to delegate to an agent or execute a tool directly.
        5. Parses and validates the LLM's JSON response.
        
        Args:
            user_prompt: The user's natural language request.
            input_files: Optional list of paths to files attached to the request.
            tool_output: Optional output from a previously executed tool (for feedback loops).
            chat_history: Recent conversation history to provide context.
            max_retries: Number of retry attempts for invalid LLM responses.
            
        Returns:
            A list of task dictionaries (e.g., {'type': 'continue', 'selected_agent': '...', ...}).
        """
        log_execution_step('ROUTER_START', f"Routing user prompt: {user_prompt[:100]}...")

        template = ROUTER_PROMPT_PATH.read_text(encoding='utf-8')
        
        # 1. Identify User & Filter Agents
        # Try multiple identity candidates and use the first that yields agents.
        user_candidates: List[str] = []
        current_user_id = str(self.cda.get_setting('current_user_id', '') or '').strip()
        current_user_email = str(self.cda.get_setting('current_user_email', '') or '').strip()
        current_username = str(self.cda.get_setting('current_username', '') or '').strip()
        fallback_user_email = str(self.cda.get_setting('user_email', '') or '').strip()

        for c in [current_user_id, current_user_email, current_username, fallback_user_email]:
            if c and c not in user_candidates:
                user_candidates.append(c)

        agent_list_data: List[Dict[str, str]] = []
        selected_identity = ''
        for identity in user_candidates:
            try:
                candidate_agents = list_agents(identity)
            except Exception:
                candidate_agents = []
            if candidate_agents:
                agent_list_data = candidate_agents
                selected_identity = identity
                break

        if not agent_list_data:
            log_execution_step('ROUTER_AGENT_FALLBACK', f"No agents found for candidates={user_candidates}.")
        else:
            log_execution_step('ROUTER_AGENT_IDENTITY', f"Using identity='{selected_identity}' with {len(agent_list_data)} agent(s).")

        agent_list = json.dumps(agent_list_data, indent=2)

        # 2. Prepare Tool List for Direct Execution
        # Retrieve all available tools and format their descriptions for the prompt.
        # This allows the router to call tools like 'list_directory' directly for simple tasks.
        tool_rows = list_tool_metadata(self.cda)
        tool_descriptions = []
        for row in tool_rows:
            name = str(row.get('name', '') or '')
            doc = str(row.get('description', '') or 'No description.')
            tool_descriptions.append(f"- {name}: {doc}")
        tool_list_str = "\n".join(tool_descriptions)

        # 3. Handle File Context
        # Paths remain in the prompt and bounded extracted content is sent separately to the LLM.
        file_context = ""
        llm_attachments = build_llm_attachments(input_files, self.cda) if input_files else []
        if input_files:
            file_entries = [
                f"{idx}. name: {f.name}\n   path: {f}"
                for idx, f in enumerate(input_files, start=1)
            ]
            file_list_str = "\n".join(file_entries)
            file_context = f"\n\n[ATTACHED FILES]\n{file_list_str}\n[END ATTACHED FILES]\n"
        
        # 4. Handle Tool Feedback Context
        # If this is a re-route after a tool execution, inject the tool's output.
        # This prompts the LLM to synthesize a final answer based on the result.
        effective_context = ""
        if tool_output:
             effective_context = f"\n\n[SYSTEM: TOOL OUTPUT]\n{tool_output}\n[END TOOL OUTPUT]\n(Please summarize this result for the user or take next step.)"

        # 5. Render Prompt
        prompt = render(
            template,
            {
                'AGENT_LIST': agent_list,
                'TOOL_LIST': tool_list_str,
                'USER_PROMPT': user_prompt + file_context + effective_context,
                'CHAT_HISTORY': chat_history,
                'TOOL_OUTPUT': tool_output or '',
                'INTERFACE_TYPE': interface_type,
            },
        )

        # 6. Log History for Debugging
        session_id = str(self.cda.get_setting('active_log_session', 'default'))
        log_chat_history('Router', session_id, chat_history)

        llm_client = self.cda.get_runtime('llm_client') or MockLLMClient()
        last_error: Exception | None = None

        # 6. Query LLM & Parse Response
        for attempt in range(max_retries + 1):
            import threading
            cancel_event = self.cda.get_runtime('cancel_event')
            if cancel_event and isinstance(cancel_event, threading.Event) and cancel_event.is_set():
                log_execution_step('ROUTER_CANCELLED', "Routing cancelled by user.")
                return [{'type': 'error', 'message': 'Execution cancelled by user'}]
                
            prompt_for_trace = prompt
            attachment_trace = format_attachments_for_prompt(llm_attachments)
            if attachment_trace:
                prompt_for_trace = f"{prompt}\n\n{attachment_trace}"
            prompt_file = ExecutionLogger.save_trace_file("router_prompt", prompt_for_trace)
            trace_payload = {
                'agent_name': 'Router',
                'loop': 1,
                'attempt': attempt + 1,
                'user_prompt': user_prompt,
                'filepath': prompt_file
            }
            self._emit_trace('llm_prepared_prompt', trace_payload)
            log_execution_step('ROUTER_TRACE_FILE', f"Prompt file: {prompt_file}")
            self._emit_trace('router_trace_file', {'phase': 'prompt', 'filepath': prompt_file})

            import time
            start_time = time.time()
            try:
                response_text = llm_client.generate(
                    prompt, 
                    agent_name='Router', 
                    user_prompt=user_prompt,
                    attachments=llm_attachments,
                )
            except TypeError as exc:
                if "unexpected keyword argument" in str(exc).lower():
                    response_text = llm_client.generate(
                        prompt, 
                        agent_name='Router', 
                        user_prompt=user_prompt
                    )
                else:
                    raise
            time_taken = time.time() - start_time
            usage = getattr(llm_client, 'last_usage', {})

            response_file = ExecutionLogger.save_trace_file("router_response", response_text)
            self._emit_trace(
                'llm_response',
                {
                    'agent_name': 'Router',
                    'loop': 1,
                    'attempt': attempt + 1,
                    'response_file': response_file,
                    'time_taken': time_taken,
                    'tokens_used': usage.get('total', 0)
                },
            )
            log_execution_step('ROUTER_TRACE_FILE', f"Response file: {response_file}")
            self._emit_trace('router_trace_file', {'phase': 'response', 'filepath': response_file})
            
            # Log the full interaction
            log_prompt('Router', prompt, response_text)

            try:
                data = parse_json(response_text)
                
                # Normalize to list
                if isinstance(data, dict):
                    data = [data]
                
                validate_router_response(data)

                attachment_paths = extract_attachment_paths(llm_attachments) if llm_attachments else []
                if attachment_paths:
                    data = self._normalize_file_routes(data, attachment_paths)

                # Log the parsed decision (detailed log)
                if llm_attachments:
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        item['_llm_attachments'] = llm_attachments
                        item['_attached_file_paths'] = attachment_paths

                log_router_decision(data)
                selected_targets = [
                    (item.get('selected_agent') if item.get('type') in ('agent_call', 'continue') else item.get('tool_name'))
                    for item in data
                ]
                selected_targets = [t for t in selected_targets if t]
                decision_types = [item.get('type', '') for item in data]
                log_execution_step('ROUTER_SELECTED', f"Selected targets: {selected_targets} | Response file: {response_file}")
                
                # Trace decision
                self._emit_trace(
                    'router_decision',
                    {
                        'response_file': response_file,
                        'selected_targets': selected_targets,
                        'decision_types': decision_types,
                    },
                )
                self._emit_trace('router_summary', {'response_file': response_file, 'selected_targets': selected_targets})
                
                return data
            except (InvalidJSONError, SchemaError) as exc:
                log_execution_step('ROUTER_RETRY', f"Attempt {attempt+1} failed: {exc}")
                self._emit_trace('error_router_validation', {'error': str(exc), 'attempt': attempt + 1})
                last_error = exc
                continue

        error_msg = f"Router failed after {max_retries+1} attempts: {last_error}"
        log_execution_step('ROUTER_ERROR', error_msg)
        self._emit_trace('error_router_fatal', {'message': error_msg})
        raise RouterError(str(last_error)) from last_error

