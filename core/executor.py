"""Executor component for agent prompts and tool loops."""

from __future__ import annotations

import json
import re
import sqlite3
import inspect
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agents.registry import get_agent
from core.common_data_area import CommonDataArea
from llm.mock_client import MockLLMClient
from llm.response_validator import InvalidJSONError, parse_json
from execution_logger import log_tool_call, log_prompt, log_execution_step, log_exception, log_chat_history, ExecutionLogger
from tools.tool_registry import call_tool
from validation.executor_validator import SchemaError, validate_executor_response


class ExecutorError(RuntimeError):
    pass


@dataclass
class ExecutorResult:
    status: str
    content: str
    ui_feedback: List[Dict[str, Any]]
    tool_request: Optional[Dict[str, Any]] = None


_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")


class Executor:
    def __init__(
        self,
        cda: CommonDataArea | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.cda = cda or CommonDataArea()
        self.llm_client = llm_client
        self.execution_context: Dict[str, Any] = {}

    def _debug_mode_enabled(self) -> bool:
        raw = self.cda.get_setting('debug_mode', False)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(raw)

    def _emit_trace(self, event_type: str, payload: Dict[str, Any]) -> None:
        handler = self.cda.get_runtime('executor_trace_handler')
        if callable(handler):
            try:
                import copy
                handler(event_type, copy.deepcopy(payload))
            except Exception:
                # Trace callback failures should not break execution flow.
                pass

    def _request_permission(self, action_type: str, payload: Dict[str, Any]) -> bool:
        if not self._debug_mode_enabled():
            return True
        handler = self.cda.get_runtime('executor_permission_handler')
        if not callable(handler):
            return True
        try:
            return bool(handler(action_type, payload))
        except Exception:
            # Fail-open if UI permission channel itself fails.
            return True

    def _reset_agent_activity(self) -> List[Dict[str, Any]]:
        """
        Start a fresh AgentActivity collection for this execute() call.
        """
        activity: List[Dict[str, Any]] = []
        self.cda.set_memory('AgentActivity', activity)
        self.cda.set_memory('agent_activity_collection', activity)  # Backward-compatible alias
        self.cda.set_memory('agent_activity', '')
        return activity

    def _get_agent_activity(self) -> List[Dict[str, Any]]:
        activity = self.cda.get_memory('AgentActivity', [])
        if not isinstance(activity, list):
            activity = []
        return activity

    def _append_agent_activity(self, key: str, value: Any) -> None:
        activity = self._get_agent_activity()
        activity.append({key: value})
        self.cda.set_memory('AgentActivity', activity)
        self.cda.set_memory('agent_activity_collection', activity)  # Backward-compatible alias

    def _render_agent_activity(self) -> str:
        """
        Render AgentActivity exactly as key/value lines for prompt injection.
        """
        lines: List[str] = []
        for item in self._get_agent_activity():
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                if isinstance(v, (dict, list)):
                    value_text = json.dumps(v, indent=2, ensure_ascii=False)
                else:
                    value_text = str(v)
                lines.append(f"{k} : {value_text}\r\n")
        rendered = "".join(lines)
        self.cda.set_memory('agent_activity', rendered)
        return rendered

    @staticmethod
    def _to_placeholder_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _get_cda_prompt_context(self) -> Dict[str, Any]:
        ctx = self.cda.get_memory('prompt_context_dict', {})
        if isinstance(ctx, dict):
            return ctx
        return {}

    def _set_cda_prompt_context_value(self, key: str, value: Any) -> None:
        ctx = self._get_cda_prompt_context()
        ctx[key] = value
        self.cda.set_memory('prompt_context_dict', ctx)

    def _replace_placeholders(self, template: str, context: Dict[str, Any]) -> str:
        """
        Replace placeholders found in template by scanning for {{TAG}}.
        Lookup order:
        1) DATE_TIME/DAT_TIME direct
        2) CDA prompt_context_dict
        3) Executor dict
        4) provided context
        5) "TAG- not available"
        """
        cda_context = self._get_cda_prompt_context()

        def _replace(match: re.Match[str]) -> str:
            tag = match.group(1)
            if tag in ('DATE_TIME', 'DAT_TIME'):
                return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if tag in cda_context:
                return self._to_placeholder_text(cda_context.get(tag))
            if tag in self.execution_context:
                return self._to_placeholder_text(self.execution_context.get(tag))
            if tag in context:
                return self._to_placeholder_text(context.get(tag))
            return f"{tag}- not available"

        return _PLACEHOLDER_RE.sub(_replace, template)

    def _get_permitted_tool_map(self) -> Dict[str, Any]:
        from tools.tool_registry import list_tools
        tools_map_all = list_tools()
        allowed = self.cda.get_setting('allowed_tools', None)
        if not isinstance(allowed, list) or not allowed:
            return tools_map_all
        allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
        return {name: fn for name, fn in tools_map_all.items() if name in allowed_set}

    def _get_agent_assigned_tools(self, agent_name: str) -> List[str]:
        db_path_str = self.cda.get_setting('sqlite_db_path', 'backend.db')
        db_path = Path(db_path_str).resolve()
        if not db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='AgentTools'")
            if not cur.fetchone():
                conn.close()
                return []
            cur.execute("SELECT id FROM Agents WHERE name=?", (agent_name,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return []
            agent_id = row[0]
            cur.execute("SELECT tool_name FROM AgentTools WHERE agent_id=?", (agent_id,))
            names = [r[0] for r in cur.fetchall()]
            conn.close()
            return names
        except Exception:
            return []

    def _build_detailed_tool_list(self, tools_map: Dict[str, Any]) -> str:
        lines: List[str] = []
        for name in sorted(tools_map.keys()):
            fn = tools_map[name]
            doc = (fn.__doc__ or "").strip().split('\n')[0] or "No description."
            try:
                sig = inspect.signature(fn)
                param_names = [p for p in sig.parameters.keys() if p != 'status_callback']
            except Exception:
                param_names = []

            params_desc = ", ".join(param_names) if param_names else "none"
            example_params = {p: f"<{p}>" for p in param_names}
            example_json = json.dumps(
                {
                    "action": {
                        "type": "tool_call",
                        "tool_request": {"tool_name": name, "parameters": example_params},
                    }
                },
                ensure_ascii=False,
            )

            lines.append(f"- {name}")
            lines.append(f"  Description: {doc}")
            lines.append(f"  Parameters: {params_desc}")
            lines.append(f"  Example: {example_json}")
        return "\n".join(lines)

    def _init_execution_context(self, agent_name: str, user_prompt: str) -> None:
        self._set_cda_prompt_context_value('CHAT_HISTORY', self.cda.get_memory('chat_history', ''))

        tools_map = self._get_permitted_tool_map()
        assigned_tools = self._get_agent_assigned_tools(agent_name)
        if assigned_tools:
            assigned_set = set(assigned_tools)
            tools_map = {k: v for k, v in tools_map.items() if k in assigned_set}
        tool_list_str = self._build_detailed_tool_list(tools_map)

        self.execution_context = {
            'TOOL_LIST': tool_list_str,
            'USER_PROMPT': user_prompt,
            'USER_INPUT': user_prompt,
            'AGENT_ACTIVITY': '',
        }

    def _build_prompt_context(self) -> Dict[str, Any]:
        return {
            'AGENT_ACTIVITY': self._render_agent_activity(),
        }

    def _prepare_prompt(self, template: str, user_prompt: str, loop_idx: int) -> str:
        """
        PreparePrompt:
        - maintain AGENT_ACTIVITY step markers
        - build runtime context map
        - replace {{TAG}} by scanning template
        """
        if loop_idx > 0:
            self._append_agent_activity("Step", loop_idx + 1)

        # Keep latest prompt/input values in executor context for replacement.
        self.execution_context['USER_PROMPT'] = user_prompt
        self.execution_context['USER_INPUT'] = user_prompt
        self.execution_context['AGENT_ACTIVITY'] = self._render_agent_activity()

        context = self._build_prompt_context()
        return self._replace_placeholders(template, context)

    def _execute_prompt(
        self,
        llm_client: Any,
        agent_name: str,
        user_prompt: str,
        prompt: str,
        loop_idx: int,
        max_retries: int,
        status_cb: Optional[Callable[[str], None]],
    ) -> Dict[str, Any]:
        """
        ExecutePrompt:
        - LLM call
        - trace logging
        - error handling + retries for invalid JSON/schema
        """
        data: Dict[str, Any] | None = None
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            llm_payload = {
                'agent_name': agent_name,
                'loop': loop_idx + 1,
                'attempt': attempt + 1,
                'prompt': prompt,
                'user_prompt': user_prompt,
                'filepath': ExecutionLogger.save_trace_file(f"{agent_name}_prompt_step{{{loop_idx+1}}}", prompt)
            }
            self._emit_trace('llm_prepared_prompt', llm_payload)
            if not self._request_permission('llm_call', llm_payload):
                raise ExecutorError('Execution cancelled by user in debug mode before LLM call.')

            if status_cb:
                status_cb("LLM call in progress...")

            import time
            start_time = time.time()
            response_text = llm_client.generate(
                prompt,
                agent_name=agent_name,
                user_prompt=user_prompt
            )
            time_taken = time.time() - start_time
            usage = getattr(llm_client, 'last_usage', {})

            if status_cb:
                status_cb("Processing LLM response...")
            self._emit_trace(
                'llm_response',
                {
                    'agent_name': agent_name,
                    'loop': loop_idx + 1,
                    'attempt': attempt + 1,
                    'response': response_text,
                    'response_file': ExecutionLogger.save_trace_file(f"{agent_name}_response_step{{{loop_idx+1}}}", response_text),
                    'time_taken': time_taken,
                    'tokens_used': usage.get('total', 0)
                },
            )

            log_prompt(agent_name, prompt, response_text)

            try:
                data = parse_json(response_text)
                validate_executor_response(data)
                return data
            except (InvalidJSONError, SchemaError) as exc:
                log_execution_step('EXECUTOR_RETRY', f"Attempt {attempt+1} failed: {exc}")
                print(f"[ERROR] Validation failed: {exc}")
                last_error = exc

        error_msg = f"Executor failed after {max_retries+1} attempts: {last_error}"
        log_execution_step('EXECUTOR_ERROR', error_msg)
        if last_error is not None:
            log_exception('EXECUTOR_ERROR', last_error, {'agent_name': agent_name, 'user_prompt': user_prompt})
        raise ExecutorError(str(last_error)) from last_error

    def _execute_tool_call(
        self,
        agent_name: str,
        loop_idx: int,
        tool_name: str,
        parameters: Dict[str, Any],
        status_cb: Optional[Callable[[str], None]],
    ) -> Dict[str, Any]:
        tool_payload = {
            'agent_name': agent_name,
            'loop': loop_idx + 1,
            'tool_name': tool_name,
            'parameters': parameters,
            'param_file': ExecutionLogger.save_trace_file(f"{tool_name}_params_step{{{loop_idx+1}}}", json.dumps(parameters, indent=2))
        }
        self._emit_trace('tool_prepared', tool_payload)
        if not self._request_permission('tool_call', tool_payload):
            raise ExecutorError(f'Execution cancelled by user in debug mode before tool call: {tool_name}.')

        try:
            if status_cb:
                status_cb(f"Tool call for '{tool_name}' in progress...")
            result = call_tool(tool_name, parameters, status_callback=status_cb)
            if status_cb:
                status_cb("")
        except Exception as exc:
            result = {
                'success': False,
                'error': f'Tool execution exception: {exc}',
                'exception_type': type(exc).__name__,
                'tool_name': tool_name,
            }
            log_execution_step('TOOL_ERROR', f"{tool_name} raised exception: {exc}")
            log_exception('TOOL_ERROR', exc, {'tool_name': tool_name, 'parameters': parameters})

        self._emit_trace(
            'tool_result',
            {
                'agent_name': agent_name,
                'loop': loop_idx + 1,
                'tool_name': tool_name,
                'parameters': parameters,
                'result': result,
                'result_file': ExecutionLogger.save_trace_file(f"{tool_name}_result_step{{{loop_idx+1}}}", json.dumps(result, indent=2, default=str))
            },
        )
        log_tool_call(tool_name, parameters, result)
        self._append_agent_activity("ToolResult", result)
        return result

    def _process_result(
        self,
        agent_name: str,
        user_prompt: str,
        data: Dict[str, Any],
        loop_idx: int,
        ui_updates: List[Dict[str, Any]],
        ui_callback: Optional[Callable[[Dict[str, Any]], None]],
        status_cb: Optional[Callable[[str], None]],
    ) -> Optional[ExecutorResult]:
        """
        ProcessResult:
        - update AGENT_ACTIVITY with LLM/tool/user-input events
        - route by action type (tool_call/request_user_input/agent_call/complete/continue)
        """
        self._append_agent_activity("LLM Result", data)

        ui_feedback = data.get('ui_feedback', {})
        plan_data = data.get('plan', {})
        current_step = ""
        if isinstance(plan_data, dict):
            current_step = str(plan_data.get('current_step', '')).strip()
        if current_step:
            self._append_agent_activity("PlanStep", current_step)
            if isinstance(ui_feedback, dict):
                existing_hint = str(ui_feedback.get('progress_hint', '') or '').strip()
                if not existing_hint:
                    ui_feedback['progress_hint'] = f"Step: {current_step}"
            self._emit_trace(
                'plan_step',
                {
                    'agent_name': agent_name,
                    'loop': loop_idx + 1,
                    'current_step': current_step,
                },
            )
            if status_cb:
                status_cb(f"Step: {current_step}")

        ui_updates.append(ui_feedback)
        if ui_callback:
            ui_callback(ui_feedback)

        action = data['action']
        action_type = action['type']
        log_execution_step('EXECUTOR_ACTION', f"Type: {action_type}")

        if action_type == 'tool_call':
            tool_request = action['tool_request']
            tool_name = tool_request['tool_name']
            parameters = tool_request['parameters']
            result = self._execute_tool_call(agent_name, loop_idx, tool_name, parameters, status_cb)

            if isinstance(result, dict) and result.get('success') is False:
                err_text = str(result.get('error', result))
                if self._is_llm_correctable_tool_error(tool_name, result, err_text):
                    log_execution_step('TOOL_ERROR_RECOVERABLE', f"Feeding tool error back to LLM: {err_text}")
                    return None
                log_execution_step('TOOL_ERROR_FATAL', f"Non-recoverable tool error: {err_text}")
                raise ExecutorError(err_text)
            return None

        if action_type == 'request_user_input':
            content = data['conversation_update']['content']
            ask_payload = {
                'agent_name': agent_name,
                'loop': loop_idx + 1,
                'content': content,
            }
            self._emit_trace('request_user_input', ask_payload)
            if not self._request_permission('request_user_input', ask_payload):
                raise ExecutorError('Execution cancelled by user in debug mode before request_user_input.')
            log_execution_step('EXECUTOR_USER_INPUT', content)
            self._append_agent_activity("UserInput", user_prompt)
            self._append_agent_activity("UserInputRequest", content)
            return ExecutorResult(
                status='request_user_input',
                content=content,
                ui_feedback=ui_updates,
                tool_request=action.get('tool_request'),
            )

        if action_type == 'continue':
            return None

        if action_type == 'agent_call':
            selected_agent = action.get('selected_agent') or action.get('tool_request', {}).get('selected_agent')
            content = data['conversation_update']['content']
            log_execution_step('EXECUTOR_HANDOFF', f"Handing off to: {selected_agent}")
            self._append_history(user_prompt, content)
            return ExecutorResult(
                status='agent_call',
                content=content,
                ui_feedback=ui_updates,
                tool_request={'selected_agent': selected_agent}
            )

        if action_type == 'complete':
            content = action.get('response') or action.get('content') or data.get('conversation_update', {}).get('content', '')
            if not content or len(content) < 10:
                alt_content = data.get('conversation_update', {}).get('content', '')
                if len(alt_content) > len(str(content or "")):
                    content = alt_content

            log_execution_step('EXECUTOR_COMPLETE', str(content)[:100])
            return ExecutorResult(
                status='complete',
                content=str(content),
                ui_feedback=ui_updates,
            )

        raise ExecutorError(f"Unknown action type: {action_type}")

    def _append_history(self, user_msg: str, assistant_msg: str) -> None:
        history = self.cda.get_memory('chat_history', '')
        if history:
            history += '\n'
        if user_msg:
            history += f"User: {user_msg}\n"
        history += f"Assistant: {assistant_msg}"
        self.cda.set_memory('chat_history', history)
        self._set_cda_prompt_context_value('CHAT_HISTORY', history)

        session_id = str(self.cda.get_setting('active_log_session', 'default'))
        log_chat_history('Executor', session_id, history)

    @staticmethod
    def _is_llm_correctable_tool_error(
        tool_name: str,
        result: Any,
        error_text: str,
    ) -> bool:
        """
        Decide whether feeding the tool error back to the LLM is useful.
        True for model-correctable issues (bad SQL/tool choice), False for infra/system failures.
        """
        err = (error_text or "").lower()

        non_llm_fixable = [
            'disk i/o error',
            'database is locked',
            'readonly database',
            'permission denied',
            'access is denied',
            'no such file or directory',
            'network is unreachable',
            'connection reset',
            'timed out',
        ]
        if any(token in err for token in non_llm_fixable):
            return False

        llm_fixable = [
            'syntax error',
            'no such table',
            'no such column',
            'ambiguous column',
            'datatype mismatch',
            'constraint failed',
            'foreign key constraint failed',
            'unique constraint failed',
            'unknown tool',
            'missing key',
            'invalid',
        ]

        if any(token in err for token in llm_fixable):
            return True

        if tool_name == 'execute_sql' and isinstance(result, dict) and 'query_index' in result:
            return True

        return False

    def execute(
        self,
        agent_name: str,
        user_prompt: str,
        ui_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        max_loops: int = 50,
        max_retries: int = 2,
        resume: bool = False,
    ) -> ExecutorResult:
        """
        Executes a task using a specific Agent.
        
        This method runs a ReAct-style loop:
        1. Loads the agent's prompt template.
        2. Injects dynamic context (AGENT_ACTIVITY + CDA/executor dictionaries).
        3. Calls the LLM to decide the next action.
        4. Executes the action (Tool Call or Final Response).
        5. Feeds the result back into the loop until completion or max loops reached.
        
        Args:
            agent_name: Name of the agent to use (must be in registry).
            user_prompt: The specific instruction for the agent.
            ui_callback: Function to handle UI updates from the agent.
            max_loops: Maximum number of turn-taking loops to prevent infinite execution.
            max_retries: Retries for invalid LLM responses per loop.
            resume: Continue same agent execution after request_user_input without resetting state.
            
        Returns:
            ExecutorResult containing the final status, content, and any UI feedback.
        """
        log_execution_step('EXECUTOR_START', f"Agent: {agent_name} | User Prompt: {user_prompt[:100]}...")
        
        # 1. Load Agent Configuration
        agent = get_agent(agent_name)
        if agent.get('prompt_content'):
            template = agent['prompt_content']
        else:
            template = agent['prompt_path'].read_text(encoding='utf-8')
        # Use injected client, or runtime client, or fallback to Mock
        llm_client = self.llm_client or self.cda.get_runtime('llm_client') or MockLLMClient()

        ui_updates: List[Dict[str, Any]] = []
        active_agent = str(self.cda.get_memory('active_executor_agent', ''))
        continuing_same_agent = bool(resume and active_agent == agent_name and self._get_agent_activity())

        if continuing_same_agent:
            # Preserve prior execution context and activity trail.
            self.execution_context['USER_PROMPT'] = user_prompt
            self.execution_context['USER_INPUT'] = user_prompt
            self._append_agent_activity("UserInput", user_prompt)
        else:
            self._init_execution_context(agent_name, user_prompt)
            # Fresh AgentActivity for every new agent execution call.
            self._reset_agent_activity()
            self._append_agent_activity("Step", 1)
            self._append_agent_activity("UserInput", user_prompt)
            self.cda.set_memory('active_executor_agent', agent_name)

        # 2. Main Execution Loop
        for loop_idx in range(max_loops):
            log_execution_step('EXECUTOR_LOOP', f"Loop {loop_idx+1}/{max_loops}")
            status_cb = self.cda.get_runtime('tool_status_handler')
            if status_cb:
                status_cb("Preparing prompt context...")
            prompt = self._prepare_prompt(template, user_prompt, loop_idx)
            session_id = str(self.cda.get_setting('active_log_session', 'default'))
            log_chat_history(agent_name, session_id, self.cda.get_memory('chat_history', ''))

            data = self._execute_prompt(
                llm_client=llm_client,
                agent_name=agent_name,
                user_prompt=user_prompt,
                prompt=prompt,
                loop_idx=loop_idx,
                max_retries=max_retries,
                status_cb=status_cb,
            )

            result = self._process_result(
                agent_name=agent_name,
                user_prompt=user_prompt,
                data=data,
                loop_idx=loop_idx,
                ui_updates=ui_updates,
                ui_callback=ui_callback,
                status_cb=status_cb,
            )
            if result is not None:
                return result

        error_msg = 'Max execution loops reached'
        log_execution_step('EXECUTOR_ERROR', error_msg)
        raise ExecutorError(error_msg)
