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

    # 1) Fast path: already clean JSON.
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 2) Common markdown fenced JSON.
    if '```' in stripped:
        import re
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', stripped, re.DOTALL | re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 3) Robust fallback: find first decodable JSON object/array inside noisy wrappers.
    decoder = json.JSONDecoder()
    for i, ch in enumerate(stripped):
        if ch not in '{[':
            continue
        snippet = stripped[i:]
        try:
            obj, _end = decoder.raw_decode(snippet)
            return obj
        except json.JSONDecodeError:
            continue

    raise InvalidJSONError('Invalid JSON')
