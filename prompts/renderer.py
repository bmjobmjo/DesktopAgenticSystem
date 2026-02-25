"""Prompt template renderer."""

from __future__ import annotations

import re
from typing import Any, Dict

_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")


def render(template_str: str, data: Dict[str, Any]) -> str:
    """Render a template string with {{PLACEHOLDER}} values.

    Missing placeholders are replaced with an empty string.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = data.get(key, "")
        if value is None:
            return ""
        return str(value)

    return _PLACEHOLDER_RE.sub(_replace, template_str)
