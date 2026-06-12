"""Router component for agent selection."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
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


class RouterTasks(list):
    """List-like router result with single-item dict compatibility access."""

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, str):
            if len(self) == 1 and isinstance(super().__getitem__(0), dict):
                return super().__getitem__(0)[key]
            raise KeyError(key)
        return super().__getitem__(key)


def list_tools(cda: CommonDataArea | None = None) -> Dict[str, Dict[str, Any]]:
    """Compatibility helper retained for older tests that patch core.router.list_tools."""
    resolved_cda = cda or CommonDataArea()
    rows = list_tool_metadata(resolved_cda)
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str(row.get('name', '') or '').strip()
        if name:
            out[name] = dict(row)
    return out


class Router:
    def __init__(self, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()

    def _get_prompt_context(self, session_ctx: Any | None = None) -> Dict[str, Any]:
        if session_ctx is not None:
            try:
                ctx = session_ctx.get_memory('prompt_context_dict', {})
                if isinstance(ctx, dict):
                    return dict(ctx)
            except Exception:
                pass
        ctx = self.cda.get_memory('prompt_context_dict', {})
        return dict(ctx) if isinstance(ctx, dict) else {}

    def _lookup_user_role(self, user_id: str, user_email: str, username: str) -> tuple[str, str]:
        db_path_str = str(self.cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db').strip()
        db_path = Path(db_path_str).resolve()
        if not db_path.exists():
            return "", ""

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            user_cols = {str(row[1]) for row in cur.fetchall()}
            if not user_cols:
                return "", ""

            role_col = 'role_id' if 'role_id' in user_cols else ('roleID' if 'roleID' in user_cols else '')
            if not role_col:
                return "", ""

            base_query = f"""
                SELECT r.id, r.name
                FROM Users u
                JOIN Roles r ON r.id = u.{role_col}
                WHERE {{where_clause}}
                LIMIT 1
            """

            if user_id and user_id.isdigit():
                cur.execute(base_query.format(where_clause="u.id = ?"), (int(user_id),))
                row = cur.fetchone()
                if row:
                    return str(row[0] or ''), str(row[1] or '')

            if user_email and 'email' in user_cols:
                cur.execute(base_query.format(where_clause="u.email = ?"), (user_email,))
                row = cur.fetchone()
                if row:
                    return str(row[0] or ''), str(row[1] or '')

            username_clauses: List[str] = []
            username_params: List[str] = []
            if username:
                if 'username' in user_cols:
                    username_clauses.append("u.username = ?")
                    username_params.append(username)
                if 'full_name' in user_cols:
                    username_clauses.append("u.full_name = ?")
                    username_params.append(username)
            if username_clauses:
                cur.execute(
                    base_query.format(where_clause=" OR ".join(username_clauses)),
                    tuple(username_params),
                )
                row = cur.fetchone()
                if row:
                    return str(row[0] or ''), str(row[1] or '')
        except Exception:
            return "", ""
        finally:
            if conn is not None:
                conn.close()

        return "", ""

    def _resolve_user_identity_fields(self, session_ctx: Any | None = None) -> Dict[str, str]:
        prompt_ctx = self._get_prompt_context(session_ctx)

        current_user_id = str(
            prompt_ctx.get('UID')
            or self.cda.get_setting('current_user_id', '')
            or ''
        ).strip()
        current_user_email = str(self.cda.get_setting('current_user_email', '') or '').strip()
        current_username = str(
            prompt_ctx.get('USER_NAME')
            or self.cda.get_setting('current_username', '')
            or ''
        ).strip()

        role_name = str(
            prompt_ctx.get('USER_ROLE')
            or prompt_ctx.get('USER_ROLE_NAME')
            or self.cda.get_setting('current_user_role_name', '')
            or self.cda.get_setting('user_role_name', '')
            or ''
        ).strip()
        role_id = str(
            prompt_ctx.get('USER_ROLE_ID')
            or self.cda.get_setting('current_user_role_id', '')
            or self.cda.get_setting('user_role_id', '')
            or ''
        ).strip()

        if not role_name or not role_id:
            db_role_id, db_role_name = self._lookup_user_role(current_user_id, current_user_email, current_username)
            if not role_id and db_role_id:
                role_id = db_role_id
            if not role_name and db_role_name:
                role_name = db_role_name

        return {
            'UID': current_user_id,
            'USER_NAME': current_username,
            'USER_ROLE': role_name,
            'USER_ROLE_ID': role_id,
        }

    @staticmethod
    def _parse_handoff_hint(tool_output: str | None) -> Dict[str, str]:
        if not tool_output:
            return {}
        try:
            parsed = json.loads(tool_output)
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        if str(parsed.get('event', '') or '').strip() != 'agent_requested_handoff':
            return {}
        return {
            'source_agent': str(parsed.get('source_agent', '') or '').strip(),
            'requested_agent': str(parsed.get('requested_agent', '') or '').strip(),
            'agent_hint': str(parsed.get('agent_hint', '') or '').strip(),
        }

    def _resolve_agent_hint(self, tool_output: str | None, session_ctx: Any | None = None) -> str:
        hint = ''
        if session_ctx is not None:
            try:
                hint = str(session_ctx.get_memory('interaction_agent_hint', '') or '').strip()
            except Exception:
                hint = ''
        if not hint:
            hint = str(self.cda.get_memory('interaction_agent_hint', '') or '').strip()

        parsed = self._parse_handoff_hint(tool_output)
        hinted = str(parsed.get('agent_hint', '') or '').strip()
        if hinted:
            hint = hinted
            try:
                self.cda.set_memory('interaction_agent_hint', hint)
            except Exception:
                pass
        return hint

    @staticmethod
    def _normalize_file_routes(
        data: List[Dict[str, Any]],
        attachment_paths: List[str],
        tool_output: str | None = None,
    ) -> List[Dict[str, Any]]:
        if not attachment_paths:
            return data

        handoff_hint = Router._parse_handoff_hint(tool_output)
        source_agent = handoff_hint.get('source_agent', '')
        requested_agent = handoff_hint.get('requested_agent', '')

        # Critical loop guard:
        # If we are re-routing after incoming_file_processor already requested a handoff,
        # do not force incoming_file_processor again just because attachments exist.
        if source_agent == 'incoming_file_processor':
            rewritten: List[Dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                if (
                    str(item.get('type', '') or '').strip() == 'agent_call'
                    and str(item.get('selected_agent', '') or '').strip() == 'incoming_file_processor'
                    and requested_agent
                ):
                    cloned = dict(item)
                    cloned['selected_agent'] = requested_agent
                    reason = str(cloned.get('reason', '') or '').strip()
                    guard_note = (
                        "incoming_file_processor has already ingested/processed attachments; "
                        "continuing downstream to avoid re-entry loop."
                    )
                    cloned['reason'] = f"{reason} {guard_note}".strip()
                    rewritten.append(cloned)
                else:
                    rewritten.append(dict(item))
            return rewritten

        has_incoming = any(
            isinstance(item, dict)
            and str(item.get('type', '') or '') == 'agent_call'
            and str(item.get('selected_agent', '') or '') == 'incoming_file_processor'
            for item in data
        )
        if has_incoming:
            return data

        # Compatibility path:
        # If the model already selected direct ingestion tool calls, do not
        # force-prepend incoming_file_processor.
        has_direct_ingestion_tool = any(
            isinstance(item, dict)
            and str(item.get('type', '') or '').strip() == 'tool_call'
            and str(item.get('tool_name', '') or '').strip() in {'file_embedding_tool', 'file_ingestion', 'ingest_file'}
            for item in data
        )
        if has_direct_ingestion_tool:
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

    def _interaction_token_limit(self) -> int:
        raw = self.cda.get_setting('interaction_max_tokens', 120000)
        try:
            value = int(raw)
        except Exception:
            value = 120000
        base_limit = max(0, value)
        extra_raw = self.cda.get_memory('interaction_token_allowance_extra', 0)
        try:
            extra = int(extra_raw or 0)
        except Exception:
            extra = 0
        return base_limit + max(0, extra)

    def _interaction_tokens_used(self) -> int:
        usage = self.cda.get_memory('interaction_token_usage', {})
        if not isinstance(usage, dict):
            return 0
        try:
            return int(usage.get('total', 0) or 0)
        except Exception:
            return 0

    def _consume_interaction_tokens(self, used_tokens: int, source: str) -> None:
        used = max(0, int(used_tokens or 0))
        if used <= 0:
            return
        usage = self.cda.get_memory('interaction_token_usage', {})
        if not isinstance(usage, dict):
            usage = {}
        total = int(usage.get('total', 0) or 0) + used
        usage['total'] = total
        usage[source] = int(usage.get(source, 0) or 0) + used
        self.cda.set_memory('interaction_token_usage', usage)
        limit = self._interaction_token_limit()
        if limit > 0 and total > limit:
            raise RouterError(
                f"Interaction token budget exceeded (used={total}, limit={limit}) while routing."
            )

    def _build_db_schema_context(self, max_tables: int = 20, max_columns_per_table: int = 12) -> str:
        """
        Build a compact DB schema snapshot for prompt context to reduce unnecessary
        routing tool calls.
        """
        db_path_str = str(self.cda.get_setting('sqlite_db_path', 'backend.db') or 'backend.db').strip()
        db_path = Path(db_path_str).resolve()
        if not db_path.exists():
            return "Schema snapshot unavailable (database file not found)."

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                LIMIT ?
                """,
                (int(max_tables),),
            )
            tables = [str(r[0]) for r in cur.fetchall() if r and r[0]]
            if not tables:
                return "Schema snapshot unavailable (no user tables)."

            lines: List[str] = []
            for table_name in tables:
                safe_table = table_name.replace('"', '""')
                cur.execute(f'PRAGMA table_info(\"{safe_table}\")')
                cols = cur.fetchall()
                if not cols:
                    lines.append(f"- {table_name}: (no columns)")
                    continue

                col_tokens: List[str] = []
                for row in cols[:max_columns_per_table]:
                    col_name = str(row[1] or '')
                    col_type = str(row[2] or '').strip() or 'ANY'
                    col_tokens.append(f"{col_name} {col_type}")
                if len(cols) > max_columns_per_table:
                    col_tokens.append(f"... +{len(cols) - max_columns_per_table} more")
                lines.append(f"- {table_name}: {', '.join(col_tokens)}")
            return "\n".join(lines)
        except Exception:
            return "Schema snapshot unavailable (error while reading database schema)."
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _format_tool_params(input_schema_raw: str) -> str:
        if not input_schema_raw:
            return "none"
        try:
            parsed = json.loads(input_schema_raw)
            params = parsed.get('parameters', []) if isinstance(parsed, dict) else []
            if not isinstance(params, list) or not params:
                return "none"
            chunks: List[str] = []
            for item in params:
                if not isinstance(item, dict):
                    continue
                pname = str(item.get('name', '') or '').strip()
                if not pname:
                    continue
                ptype = str(item.get('type', 'Any') or 'Any').strip()
                preq = bool(item.get('required', False))
                pdesc = str(item.get('description', '') or '').strip()
                label = f"{pname} ({ptype}{', required' if preq else ''})"
                if pdesc:
                    label += f": {pdesc}"
                chunks.append(label)
            return "; ".join(chunks) if chunks else "none"
        except Exception:
            return "none"

    def _build_router_db_tools_detail(self) -> str:
        """
        Build detailed DB-tool usage text using ToolList metadata.
        """
        default_rows = {
            'dbschema': {
                'description': 'Retrieve database schema metadata for routing decisions.',
                'input_schema': json.dumps({'parameters': []}, ensure_ascii=False),
                'example_call': '{"tool_name":"dbschema","parameters":{}}',
            },
            'sql': {
                'description': 'Run tightly scoped read-only SQL required for routing metadata checks.',
                'input_schema': json.dumps(
                    {
                        'parameters': [
                            {
                                'name': 'queries',
                                'type': 'list[str] | str',
                                'required': True,
                                'description': 'Single SQL statement or a list of SQL statements.',
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                'example_call': '{"tool_name":"sql","parameters":{"queries":["SELECT name FROM Agents LIMIT 5"]}}',
            },
        }

        rows = list_tool_metadata(self.cda, names=['dbschema', 'sql', 'get_database_schema', 'execute_sql'])

        normalized: Dict[str, Dict[str, str]] = {}
        for row in rows:
            raw_name = str(row.get('name', '') or '').strip()
            if raw_name in ('dbschema', 'get_database_schema'):
                key = 'dbschema'
            elif raw_name in ('sql', 'execute_sql'):
                key = 'sql'
            else:
                continue
            normalized[key] = {
                'description': str(row.get('description', '') or '').strip(),
                'input_schema': str(row.get('input_schema', '') or ''),
                'example_call': str(row.get('example_call', '') or '').strip(),
            }

        lines: List[str] = []
        for tool_name in ('dbschema', 'sql'):
            row = normalized.get(tool_name) or default_rows[tool_name]
            desc = row.get('description') or default_rows[tool_name]['description']
            params = self._format_tool_params(row.get('input_schema', ''))
            example = row.get('example_call') or default_rows[tool_name]['example_call']
            lines.append(f"- `{tool_name}`")
            lines.append(f"  Purpose: {desc}")
            lines.append(f"  Parameters: {params}")
            lines.append(f"  Example: {example}")
        return "\n".join(lines)

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
        2. Compiles DB-routing context (schema snapshot + DB tool guide).
        3. Constructs a prompt including the user request, file context, and any previous tool output.
        4. Queries the LLM to decide whether to delegate to an agent or use DB-routing tools.
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
        identity_fields = self._resolve_user_identity_fields(session_ctx)
        current_user_id = identity_fields['UID']
        current_user_email = str(self.cda.get_setting('current_user_email', '') or '').strip()
        current_username = identity_fields['USER_NAME']
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

        # 2. Prepare DB-Only Routing Context
        db_schema_context = self._build_db_schema_context()
        router_db_tools_detail = self._build_router_db_tools_detail()

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

        # Reuse the same shared session memory used by agent prompts so router
        # can reason over recent execution facts in follow-up turns.
        if session_ctx is not None:
            try:
                agent_activity = str(session_ctx.get_memory('agent_activity', '') or '')
            except Exception:
                agent_activity = str(self.cda.get_memory('agent_activity', '') or '')
        else:
            agent_activity = str(self.cda.get_memory('agent_activity', '') or '')
        agent_hint = self._resolve_agent_hint(tool_output, session_ctx=session_ctx)

        # 5. Render Prompt
        prompt = render(
            template,
            {
                'AGENT_LIST': agent_list,
                'ROUTER_DB_TOOLS_DETAIL': router_db_tools_detail,
                'USER_PROMPT': user_prompt + file_context + effective_context,
                'UID': identity_fields['UID'],
                'USER_NAME': identity_fields['USER_NAME'],
                'USER_ROLE': identity_fields['USER_ROLE'],
                'USER_ROLE_ID': identity_fields['USER_ROLE_ID'],
                'DATE_TIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'CHAT_HISTORY': chat_history,
                'AGENT_ACTIVITY': agent_activity,
                'AGENT_HINT': agent_hint,
                'TOOL_OUTPUT': tool_output or '',
                'INTERFACE_TYPE': interface_type,
                'DB_SCHEMA_CONTEXT': db_schema_context,
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

            token_limit = self._interaction_token_limit()
            if token_limit > 0 and self._interaction_tokens_used() >= token_limit:
                raise RouterError(
                    f"Interaction token budget reached before router call "
                    f"(used={self._interaction_tokens_used()}, limit={token_limit})."
                )

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
            consumed_total = int(usage.get('total', 0) or 0)
            if consumed_total <= 0:
                consumed_total = max(1, (len(prompt) + len(response_text)) // 4)
            self._consume_interaction_tokens(consumed_total, source='router')

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
                    data = self._normalize_file_routes(data, attachment_paths, tool_output=tool_output)

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
                
                return RouterTasks(data)
            except (InvalidJSONError, SchemaError) as exc:
                log_execution_step('ROUTER_RETRY', f"Attempt {attempt+1} failed: {exc}")
                self._emit_trace('error_router_validation', {'error': str(exc), 'attempt': attempt + 1})
                last_error = exc
                continue

        error_msg = f"Router failed after {max_retries+1} attempts: {last_error}"
        log_execution_step('ROUTER_ERROR', error_msg)
        self._emit_trace('error_router_fatal', {'message': error_msg})
        raise RouterError(str(last_error)) from last_error

