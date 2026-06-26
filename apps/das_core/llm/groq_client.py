"""Groq LLM client."""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from core.llm_attachments import format_attachments_for_prompt
from core.ssl_compat import create_ssl_context
from execution_logger import log_exception, log_execution_step
from llm.base_client import BaseLLMClient


def _get_db_path() -> str:
    return r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db'


class GroqClientError(RuntimeError):
    pass


class GroqClient(BaseLLMClient):
    def __init__(self, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()
        self.last_usage: Dict[str, int] = {}

    def generate(
        self,
        prompt: str,
        agent_name: str = "Assistant",
        user_prompt: str = "",
        attachments: List[Dict[str, Any]] | None = None,
    ) -> str:
        api_key = self.cda.get_setting('groq_api_key', '')
        if not api_key:
            raise GroqClientError('Groq API key is missing. Set it in settings.')

        model_id = self.cda.get_setting('groq_model', 'llama-3.3-70b-versatile')
        temperature = float(self.cda.get_setting('groq_temperature', 1.0))
        url = 'https://api.groq.com/openai/v1/chat/completions'

        log_execution_step('GROQ', f"Requesting completion from {model_id} via Groq")

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
            "temperature": temperature,
        }

        data = json.dumps(body).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'User-Agent': 'DesktopAgenticSystem/1.0 (Windows NT 10.0; Win64; x64)',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=120, context=create_ssl_context()) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode('utf-8')
            log_exception('GROQ_ERROR', exc, 'Groq API request failed')
            raise GroqClientError(f"Groq API Error {exc.code}: {error_body}") from exc
        except Exception as exc:
            log_exception('GROQ_ERROR', exc, 'Failed to connect to Groq')
            raise GroqClientError(f"Groq Error: {exc}") from exc

        try:
            response_text = payload['choices'][0]['message']['content']
            usage = payload.get('usage', {})
            tin = int(usage.get('prompt_tokens', 0) or 0)
            tout = int(usage.get('completion_tokens', 0) or 0)
            total = int(usage.get('total_tokens', 0) or 0)

            self.last_usage = {'tin': tin, 'tout': tout, 'total': total}
            self._log_usage(agent_name, user_prompt, prompt_with_attachments, response_text, tin, tout, total)
            log_execution_step('GROQ', 'Received response successfully.')
            return response_text
        except (KeyError, IndexError, TypeError) as exc:
            raise GroqClientError('Unexpected response format from Groq.') from exc

    def _log_usage(
        self,
        agent_name: str,
        user_prompt: str,
        prompt: str,
        response: str,
        tin: int,
        tout: int,
        total: int,
    ) -> None:
        try:
            model_id = self.cda.get_setting('groq_model', 'llama-3.3-70b-versatile')
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO LLMUsage (user_prompt, agent_name, prompt, response, provider, model_name, token_in, token_out, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_prompt, agent_name, prompt, response, 'Groq', model_id, tin, tout, total),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            print(f"Warning: Failed to log LLM usage: {exc}")

