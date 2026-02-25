"""LLM response validation utilities."""

from __future__ import annotations

import json
from typing import Any


class InvalidJSONError(ValueError):
    pass


def parse_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise InvalidJSONError('Empty response')
    
    if '```' in stripped:
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', stripped, re.DOTALL)
        if match:
            stripped = match.group(1).strip()
            
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise InvalidJSONError('Invalid JSON') from exc
