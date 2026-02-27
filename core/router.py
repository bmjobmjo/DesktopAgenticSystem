"""Router component for agent selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agents.registry import ROUTER_PROMPT_PATH, list_agents
from tools.tool_registry import list_tools
from core.common_data_area import CommonDataArea
from llm.mock_client import MockLLMClient
from llm.response_validator import InvalidJSONError, parse_json
from prompts.renderer import render
from execution_logger import log_router_decision, log_prompt, log_execution_step, log_chat_history, ExecutionLogger
from validation.router_validator import SchemaError, validate_router_response


class RouterError(RuntimeError):
    pass


class Router:
    def __init__(self, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()

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
        tools_map = list_tools()
        tool_descriptions = []
        for name, func in tools_map.items():
            doc = (func.__doc__ or "").strip().split('\n')[0]
            tool_descriptions.append(f"- {name}: {doc}")
        tool_list_str = "\n".join(tool_descriptions)

        # 3. Handle File Context
        # If input files are provided, list them in the prompt.
        # We generally avoid reading full content here to save tokens, relying on agents/tools to process.
        file_context = ""
        if input_files:
            file_list_str = "\n".join([f"- {f.name} ({f})" for f in input_files])
            file_context = f"\n\n[ATTACHED FILES]\nThe user has attached the following files:\n{file_list_str}\n[END ATTACHED FILES]\n"
        
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
                
            prompt_file = ExecutionLogger.save_trace_file("router_prompt", prompt)
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
            response_text = llm_client.generate(
                prompt, 
                agent_name='Router', 
                user_prompt=user_prompt
            )
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
                
                # Log the parsed decision (detailed log)
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
