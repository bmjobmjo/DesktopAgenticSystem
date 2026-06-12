"""Local LLM client (OpenAI-compatible)."""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from llm.base_client import BaseLLMClient
from execution_logger import log_execution_step, log_exception
from core.llm_attachments import format_attachments_for_prompt


def _get_db_path() -> str:
    configured = Path("data") / "office_automation.db"
    return str(configured)


class LocalLLMClientError(RuntimeError):
    pass


class LocalLLMClient(BaseLLMClient):
    def __init__(self, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()
        self.last_usage = {}

    def generate(
        self, 
        prompt: str, 
        agent_name: str = "Assistant", 
        user_prompt: str = "",
        attachments: List[Dict[str, Any]] | None = None,
    ) -> str:
        base_url = self.cda.get_setting('local_llm_url', 'http://127.0.0.1:1234/v1')
        model_id = self.cda.get_setting('local_llm_model', 'qwen2.5-14b-instruct-1m')
        
        log_execution_step('LOCAL_LLM', f"Requesting completion from {model_id} at {base_url}")
        
        # Ensure URL ends with /chat/completions if it's just the base
        url = base_url.rstrip('/')
        if not url.endswith('/chat/completions'):
            url += '/chat/completions'

        attachment_block = format_attachments_for_prompt(attachments)
        prompt_with_attachments = prompt if not attachment_block else f"{prompt}\n\n{attachment_block}"

        message_content: Any = prompt_with_attachments
        image_parts = []
        for item in attachments or []:
            if str(item.get('kind', '') or '') != 'image':
                continue
            data_url = str(item.get('data_url', '') or '').strip()
            if not data_url:
                continue
            image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
        if image_parts:
            message_content = [{"type": "text", "text": prompt_with_attachments}, *image_parts]

        body = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": message_content}
            ],
            "temperature": 0.3
        }
        
        data = json.dumps(body).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                content = response.read().decode('utf-8')
                payload = json.loads(content)
        except Exception as exc:
            log_exception('LOCAL_LLM_ERROR', exc, f"Failed to connect to local LLM at {url}")
            raise LocalLLMClientError(f"Local LLM Error: {exc}") from exc

        try:
            response_text = payload['choices'][0]['message']['content']
            log_execution_step('LOCAL_LLM', "Received response successfully.")
            
            # Extract usage if present
            usage = payload.get('usage', {})
            tin = usage.get('prompt_tokens', 0)
            tout = usage.get('completion_tokens', 0)
            total = usage.get('total_tokens', 0)
            
            self.last_usage = {'tin': tin, 'tout': tout, 'total': total}
            
            # Log to DB
            self._log_usage(agent_name, user_prompt, prompt_with_attachments, response_text, tin, tout, total)
            
            return response_text
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMClientError('Unexpected response format from Local LLM.') from exc

    def _log_usage(self, agent_name: str, user_prompt: str, prompt: str, response: str, tin: int, tout: int, total: int):
        try:
            model_id = self.cda.get_setting('local_llm_model', 'qwen2.5-14b-instruct-1m')
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO LLMUsage (user_prompt, agent_name, prompt, response, provider, model_name, token_in, token_out, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_prompt, agent_name, prompt, response, 'Local', model_id, tin, tout, total))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to log LLM usage: {e}")
