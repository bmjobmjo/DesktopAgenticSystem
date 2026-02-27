"""Controller orchestrator."""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.common_data_area import CommonDataArea
from core.executor import Executor, ExecutorError
from core.router import Router, RouterError
from execution_logger import log_execution_step, log_exception, log_chat_history


@dataclass
class ControllerResponse:
    status: str
    content: str
    ui_feedback: List[Dict[str, Any]]
    tool_request: Optional[Dict[str, Any]] = None


class Controller:
    def __init__(
        self,
        cda: CommonDataArea | None = None,
        router: Router | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.cda = cda or CommonDataArea()
        self.router = router or Router(self.cda)
        self.executor = executor or Executor(self.cda)
        
        # New State Management
        self.task_queue: List[Dict] = []
        self.current_task: Optional[Dict] = None
        self.awaiting_user_input: bool = False

    def _emit_trace(self, event_type: str, payload: Dict[str, Any]) -> None:
        handler = self.cda.get_runtime('executor_trace_handler')
        if callable(handler):
            try:
                import copy
                handler(event_type, copy.deepcopy(payload))
            except Exception:
                # Trace callback failures should not break execution flow.
                pass

    def clear_current_task(self) -> None:
        """Clears the controller's active task state (typically used on new chats)."""
        self.current_task = None
        self.awaiting_user_input = False
        self.task_queue.clear()

    def handle_user_message(
        self,
        message: str,
        files: List[str] | None = None,
        interface: str = "UI",
        ui_callback=None,
    ) -> ControllerResponse:
        """
        Main entry point for user interaction.
        
        Orchestrates the flow:
        1. Checks if the user is responding to a specific agent request (resume task).
        2. If new request, calls Router to determine tasks.
        3. Populates the task queue.
        4. Initiates queue processing.
        """
        iface = (interface or "UI").strip() or "UI"
        self.cda.set_setting('interface', iface)
        log_execution_step('USER_INPUT', f"{message} [Files: {len(files) if files else 0}] [Interface: {iface}]")
        self._emit_trace('user_input', {'message': message, 'files': files, 'interface': iface})
        
        # 1. Handle Pending Input (Bypass Router)
        # If an agent was waiting for user input (e.g. "What is your destination?"),
        # we bypass the router and resume that specific agent's execution.
        if self.awaiting_user_input and self.current_task:
            log_execution_step('CONTROLLER_RESUME', f"Resuming task {self.current_task.get('selected_agent')} with user input.")
            self.awaiting_user_input = False
            # Force current task instruction to latest user answer for resume flow.
            self.current_task['instruction'] = message
            self.current_task['_resume'] = True
            
            # Execute with user input
            result = self._execute_current_task(message, ui_callback)
            
            # If task is still requesting input (e.g. multi-turn), return immediately
            if result.status == 'request_user_input':
                self.awaiting_user_input = True
                return ControllerResponse(
                    status='request_user_input',
                    content=result.content,
                    ui_feedback=result.ui_feedback,
                    tool_request=result.tool_request
                )
            
            # If task error, stop
            if result.status == 'error':
                 return ControllerResponse(status='error', content=result.content, ui_feedback=result.ui_feedback)

            # If task complete, check if we have more in queue
            if result.status == 'complete':
                 # Append this result to history is done in _execute_current_task
                 # Now continue queue
                 return self._process_queue(message, ui_callback)

        history = self.cda.get_memory('chat_history', '')

        try:
            # 2. Route New Request
            # Ask the Router to breakdown the user message into one or more tasks.
            # Can return Agent tasks (delegate) or Tool tasks (direct execution).
            
            # Convert file strings to Path objects
            from pathlib import Path
            input_files = [Path(f) for f in files] if files else None
            
            routes = self.router.route(message, input_files=input_files, chat_history=history)
            
            # Sort routes by priority (ascending), default to 99 if missing
            routes.sort(key=lambda x: x.get('priority', 99))
            
            # Note: Deliberately preserving `agent_activity` here to carry context across the entire active chat session.
            
            self.task_queue = routes
            self.current_task = None
            
            self._emit_trace('controller_task_queue', {'queue_size': len(routes), 'routes': routes})

            if not self.task_queue:
                return ControllerResponse(
                    status='complete',
                    content="I'm sorry, I couldn't determine how to help with that.",
                    ui_feedback=[]
                )

            # 3. Start Execution Loop
            return self._process_queue(message, ui_callback)

        except Exception as exc:
            error_msg = f"System Error: {exc}"
            log_execution_step('CONTROLLER_ERROR', error_msg)
            log_exception('CONTROLLER_ERROR', exc, {'message': message})
            return ControllerResponse(
                status='error',
                content=error_msg,
                ui_feedback=[],
            )

    def _process_queue(self, user_message: str, ui_callback=None) -> ControllerResponse:
        """
        Process the task queue serially until completion or user input required.
        
        Iterates through self.task_queue:
        - Handles 'greeting' or simple responses directly.
        - Delegates mechanism to _execute_current_task for Agents/Tools.
        - Aggregates results and UI feedback.
        """
        
        total_content = []
        all_ui_feedback = []
        
        while self.task_queue:
            import threading
            cancel_event = self.cda.get_runtime('cancel_event')
            if cancel_event and isinstance(cancel_event, threading.Event) and cancel_event.is_set():
                log_execution_step('CONTROLLER_CANCELLED', "Controller queue processing cancelled by user.")
                self.clear_current_task()
                return ControllerResponse(status='error', content="Execution stopped by user.", ui_feedback=all_ui_feedback)
                
            self.current_task = self.task_queue.pop(0)
            
            # Check for direct response interaction (greeting/clarification)
            if self.current_task.get('type') in ('greeting', 'request_user_input'):
                response_content = self.current_task.get('response_to_user', '')
                status = 'request_user_input' if self.current_task.get('type') == 'request_user_input' else 'complete'
                
                # If requesting input, pause queue here
                if status == 'request_user_input':
                    self.awaiting_user_input = True
                    # Return immediately to wait for user
                    return ControllerResponse(
                        status='request_user_input',
                        content=response_content,
                        ui_feedback=all_ui_feedback
                    )
                
                # Greeting / completion message
                total_content.append(response_content)
                self._append_history(user_message if not total_content else '', response_content)
                continue

            # Execute Agent/Tool Task
            result = self._execute_current_task(user_message, ui_callback)
            
            all_ui_feedback.extend(result.ui_feedback)
            if result.content:
                total_content.append(result.content)

            if result.status == 'agent_call':
                new_agent = result.tool_request.get('selected_agent')
                log_execution_step('CONTROLLER_HANDOFF', f"Agent requested hand-off to: {new_agent}")
                # Prepend the new agent call to the queue
                handoff_task = {
                    'type': 'agent_call',
                    'selected_agent': new_agent,
                    'instruction': result.content, # Use the summary from previous agent as instruction
                    'priority': 1
                }
                self.task_queue.insert(0, handoff_task)
                continue

            if result.status == 'request_user_input':
                self.awaiting_user_input = True
                return ControllerResponse(
                    status='request_user_input',
                    content="\n\n".join(total_content), # Return what we have so far + question
                    ui_feedback=all_ui_feedback,
                    tool_request=result.tool_request
                )
            
            if result.status == 'error':
                 # Stop chain on error
                 return result

        return ControllerResponse(
            status='complete',
            content="\n\n".join(total_content),
            ui_feedback=all_ui_feedback
        )

    def _execute_current_task(self, prompt: str, ui_callback=None) -> Any: # Returns ExecutorResult-like object
        """
        Executes a single task from the queue.
        
        Handles two main types of tasks:
        1. Tool Call: Directly executes a tool (via Router instruction) and feeds result back to Router.
        2. Agent Execution: Delegates the task to a specific Agent via the Executor.
        """
        
        # 1. Check for Direct Tool Call (New Router Capability)
        if self.current_task.get('type') == 'tool_call':
            tool_name = self.current_task.get('tool_name')
            params = self.current_task.get('parameters', {})
            
            log_execution_step('CONTROLLER_TOOL', f"Router Executing Tool: {tool_name}")
            
            try:
                # Direct import to avoid circular dependency
                from tools.tool_registry import call_tool
                
                tool_payload = {
                    'agent_name': 'Controller',
                    'tool_name': tool_name,
                    'parameters': params,
                }
                self._emit_trace('tool_prepared', tool_payload)

                status_cb = self.cda.get_runtime('tool_status_handler')
                if status_cb:
                    status_cb(f"Routing direct tool call for '{tool_name}'...")
                    
                result_data = call_tool(tool_name, params, status_callback=status_cb)
                if status_cb:
                    status_cb("") # Clear progress
                
                self._emit_trace('tool_result', {**tool_payload, 'result': result_data})
                
                # Feedback Loop: Send tool result back to Router for synthesis
                # This allows the Router to see the output of the tool it requested
                # and generate a final natural language response or FURTHER tasks.
                tool_output_str = json.dumps(result_data, indent=2)
                log_execution_step('CONTROLLER_TOOL_FEEDBACK', f"Feeding result back to Router: {tool_output_str[:100]}...")
                
                # Re-route with tool output
                new_routes = self.router.route(prompt, tool_output=tool_output_str, chat_history=self.cda.get_memory('chat_history', ''))
                
                # Handle complex re-routing: if Router returns more tasks, prepend them to queue
                if new_routes:
                    first_task = new_routes[0]
                    # If there are multiple tasks, or the first task is NOT a simple greeting/input, 
                    # we should probably prepend them to continue the flow.
                    if len(new_routes) > 1 or first_task.get('type') in ('agent_call', 'continue', 'tool_call'):
                        log_execution_step('CONTROLLER_REROUTE', f"Adding {len(new_routes)} tasks from feedback loop to queue.")
                        # Insert at the beginning of the queue
                        for task in reversed(new_routes):
                            self.task_queue.insert(0, task)
                        
                        # Return a 'complete' status for THIS task execution, 
                        # but _process_queue will pick up the next task.
                        from core.executor import ExecutorResult
                        return ExecutorResult(status='complete', content='', ui_feedback=[])
                    
                    # Simple case: just a message back to user
                    content = first_task.get('response_to_user', f"Tool executed. Result: {tool_output_str}")
                    status = 'complete'
                else:
                    content = f"Tool executed. Result: {tool_output_str}"
                    status = 'complete'

                from core.executor import ExecutorResult
                result = ExecutorResult(status=status, content=content, ui_feedback=[], tool_request=None)
            except Exception as e:
                error_msg = f"Tool execution failed: {e}"
                log_execution_step('CONTROLLER_TOOL_ERROR', error_msg)
                from core.executor import ExecutorResult
                result = ExecutorResult(status='error', content=error_msg, ui_feedback=[])
                
            self._append_history(prompt, result.content)
            return result

        # 2. Standard Agent Execution
        # Handle 'agent_call' (new) or 'continue' (legacy)
        route_type = self.current_task.get('type')
        if route_type in ('agent_call', 'continue'):
            agent_name = self.current_task.get('selected_agent')
            # Use specific instruction if available, otherwise original prompt
            task_instruction = self.current_task.get('instruction', prompt)
            resume = bool(self.current_task.get('_resume', False))
            
            # Delegate to Executor for the agent loop
            self._emit_trace('controller_delegate_agent', {'agent_name': agent_name, 'instruction': task_instruction})
            result = self.executor.execute(agent_name, task_instruction, ui_callback=ui_callback, resume=resume)
            
            self._append_history(prompt, result.content)
            return result

        # Fallback for unexpected task types
        error_msg = f"Unknown task type: {route_type}"
        log_execution_step('CONTROLLER_ERROR', error_msg)
        from core.executor import ExecutorResult
        return ExecutorResult(status='error', content=error_msg, ui_feedback=[])

    def _append_history(self, user_msg: str, assistant_msg: str):
        history = self.cda.get_memory('chat_history', '')
        user_id = str(self.cda.get_setting('current_user_id', '') or '')
        iface = str(self.cda.get_setting('interface', 'UI') or 'UI')
        user_prefix = f"User[UserID:{user_id}][Interface:{iface}]"
        assistant_prefix = f"Assistant[UserID:{user_id}][Interface:{iface}]"
        if history:
            history += '\n'
        if user_msg:
             history += f"{user_prefix}: {user_msg}\n"
        history += f"{assistant_prefix}: {assistant_msg}"
        
        self.cda.set_memory('chat_history', history)
        
        # Log History for Debugging
        session_id = str(self.cda.get_setting('active_log_session', 'default'))
        log_chat_history('Controller', session_id, history)
