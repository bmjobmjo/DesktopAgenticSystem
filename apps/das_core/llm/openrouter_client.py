"""OpenRouter LLM client."""

from __future__ import annotations

import json
import sqlite3
import sys
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


def _safe_stdout_write(text: str) -> None:
    stream = getattr(sys, "stdout", None)
    if stream is None or not hasattr(stream, "write"):
        return
    try:
        stream.write(text)
        if hasattr(stream, "flush"):
            stream.flush()
    except Exception:
        pass


class OpenRouterClientError(RuntimeError):
    pass


class OpenRouterClient(BaseLLMClient):
    def __init__(self, cda: CommonDataArea | None = None) -> None:
        self.cda = cda or CommonDataArea()
        self.last_usage = {}
        self.last_usage = {}

    def generate(
        self, 
        prompt: str, 
        agent_name: str = "Assistant", 
        user_prompt: str = "",
        attachments: List[Dict[str, Any]] | None = None,
    ) -> str:
        api_key = self.cda.get_setting('openrouter_api_key', '')
        model_id = self.cda.get_setting('openrouter_model', 'stepfun/step-3.5-flash')
        url = 'https://openrouter.ai/api/v1/chat/completions'

        log_execution_step('OPENROUTER', f"Requesting completion from {model_id} via OpenRouter")

        if not api_key:
            raise OpenRouterClientError("OpenRouter API key is not configured in Settings.")

        def _as_bool(value: Any, default: bool) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                raw = value.strip().lower()
                if raw in {"1", "true", "yes", "on"}:
                    return True
                if raw in {"0", "false", "no", "off"}:
                    return False
            if value is None:
                return default
            return bool(value)

        try:
            temperature = float(self.cda.get_setting('openrouter_temperature', 1.0))
        except Exception:
            temperature = 1.0
        if temperature < 0.0:
            temperature = 0.0
        if temperature > 2.0:
            temperature = 2.0
        try:
            top_p = float(self.cda.get_setting('openrouter_top_p', 1.0))
        except Exception:
            top_p = 1.0
        if top_p <= 0.0:
            top_p = 0.01
        if top_p > 1.0:
            top_p = 1.0
        include_reasoning = _as_bool(self.cda.get_setting('openrouter_include_reasoning', False), False)

        seed = None
        seed_raw = self.cda.get_setting('openrouter_seed', '')
        try:
            if str(seed_raw).strip() != '':
                seed = int(str(seed_raw).strip())
        except Exception:
            seed = None

        provider_order_raw = str(self.cda.get_setting('openrouter_provider_order', '') or '').strip()
        provider_order = [item.strip() for item in provider_order_raw.split(',') if item.strip()]
        allow_fallbacks = _as_bool(self.cda.get_setting('openrouter_allow_fallbacks', True), True)
        require_parameters = _as_bool(self.cda.get_setting('openrouter_require_parameters', False), False)

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
            "stream": True,
            "temperature": temperature,
            "top_p": top_p,
        }
        if include_reasoning:
            body["include_reasoning"] = True
        if seed is not None:
            body["seed"] = seed

        provider_cfg: Dict[str, Any] = {}
        if provider_order:
            provider_cfg["order"] = provider_order
        if provider_order:
            provider_cfg["allow_fallbacks"] = allow_fallbacks
        if require_parameters:
            provider_cfg["require_parameters"] = True
        if provider_cfg:
            body["provider"] = provider_cfg
        
        data = json.dumps(body).encode('utf-8')
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'HTTP-Referer': 'http://localhost:8000',
                'X-Title': 'DesktopAgenticSystem',
            },
            method='POST',
        )

        full_response = ""
        tin = 0
        tout = 0
        total = 0
        reasoning_tokens = 0

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    if line.startswith('data: '):
                        data_str = line[6:]
                        if data_str == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                content = delta.get('content')
                                if content:
                                    full_response += content
                                    _safe_stdout_write(content)
                            
                            usage = chunk.get('usage')
                            if usage:
                                tin = usage.get('prompt_tokens', 0)
                                tout = usage.get('completion_tokens', 0)
                                total = usage.get('total_tokens', 0)
                                self.last_usage = {'tin': tin, 'tout': tout, 'total': total}
                                
                                # OpenRouter might pass reasoning tokens in different fields
                                reasoning_tokens = usage.get('reasoningTokens', usage.get('reasoning_tokens', 0))
                                if not reasoning_tokens and 'completion_tokens_details' in usage:
                                    reasoning_tokens = usage['completion_tokens_details'].get('reasoning_tokens', 0)
                                
                                if reasoning_tokens:
                                    _safe_stdout_write(f"\nReasoning tokens: {reasoning_tokens}\n")
                                    
                        except json.JSONDecodeError:
                            pass
        except Exception as exc:
            log_exception('OPENROUTER_ERROR', exc, f"Failed to connect to OpenRouter")
            raise OpenRouterClientError(f"OpenRouter Error: {exc}") from exc

        log_execution_step('OPENROUTER', "Received streaming response successfully.")
        
        _safe_stdout_write("\n")
        
        # Log to DB
        self._log_usage(agent_name, user_prompt, prompt_with_attachments, full_response, tin, tout, total)
        
        return full_response

    def _log_usage(self, agent_name: str, user_prompt: str, prompt: str, response: str, tin: int, tout: int, total: int):
        try:
            model_id = self.cda.get_setting('openrouter_model', 'stepfun/step-3.5-flash')
            conn = sqlite3.connect(_get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO LLMUsage (user_prompt, agent_name, prompt, response, provider, model_name, token_in, token_out, total_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_prompt, agent_name, prompt, response, 'OpenRouter', model_id, tin, tout, total))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Failed to log LLM usage: {e}")
