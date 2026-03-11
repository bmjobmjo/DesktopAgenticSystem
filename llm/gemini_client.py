"""Gemini LLM client."""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from llm.base_client import BaseLLMClient
from core.llm_attachments import format_attachments_for_prompt


def _get_db_path() -> str:
    # Use the same path as core/db_schema.py
    return r'd:\Works\GenericAgent\DesktopAgenticSystem\data\office_automation.db'


class GeminiClientError(RuntimeError):
    pass


class GeminiClient(BaseLLMClient):
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
        api_key = self.cda.get_setting('gemini_api_key', '')
        if not api_key:
            raise GeminiClientError('Gemini API key is missing. Set it in settings.')

        model_id = self.cda.get_setting('gemini_model', 'gemini-1.5-flash')
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{model_id}:generateContent?key={api_key}'
        )
        temperature = float(self.cda.get_setting('gemini_temperature', 0.0))
        
        attachment_block = format_attachments_for_prompt(attachments)
        prompt_with_attachments = prompt if not attachment_block else f"{prompt}\n\n{attachment_block}"

        parts: List[Dict[str, Any]] = [{'text': prompt_with_attachments}]
        for item in attachments or []:
            if str(item.get('kind', '') or '') != 'image':
                continue
            mime_type = str(item.get('mime_type', '') or '').strip()
            data_base64 = str(item.get('data_base64', '') or '').strip()
            if not mime_type or not data_base64:
                continue
            parts.append({'inline_data': {'mime_type': mime_type, 'data': data_base64}})

        body = {
            'contents': [
                {
                    'role': 'user',
                    'parts': parts
                }
            ],
            'generationConfig': {
                'temperature': temperature
            },
            'safetySettings': [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }
        
        # Only add thinkingConfig for specific 'thinking' models to prevent 400 errors
        if 'thinking' in model_id.lower():
            body['generationConfig']['thinkingConfig'] = {'includeThoughts': False}
        data = json.dumps(body).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode('utf-8')
            print(f"[ERROR] Gemini API Error: {error_body}")
            raise GeminiClientError(f"Gemini API Error {exc.code}: {error_body}") from exc
        except Exception as exc:  # noqa: BLE001
            raise GeminiClientError(str(exc)) from exc

        try:
            response_text = payload['candidates'][0]['content']['parts'][0]['text']
            
            # Extract token usage if present
            usage = payload.get('usageMetadata', {})
            tin = usage.get('promptTokenCount', 0)
            tout = usage.get('candidatesTokenCount', 0)
            total = usage.get('totalTokenCount', 0)
            
            self.last_usage = {'tin': tin, 'tout': tout, 'total': total}
            
            # Log to DB
            self._log_usage(agent_name, user_prompt, prompt_with_attachments, response_text, tin, tout, total)
            
            return response_text
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiClientError('Unexpected response format from Gemini.') from exc

    def _log_usage(self, agent_name: str, user_prompt: str, prompt: str, response: str, tin: int, tout: int, total: int):
        try:
            model_id = self.cda.get_setting('gemini_model', 'gemini-1.5-flash')
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO LLMUsage (user_prompt, agent_name, prompt, response, provider, model_name, token_in, token_out, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_prompt, agent_name, prompt, response, 'Gemini', model_id, tin, tout, total))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to log LLM usage: {e}")
