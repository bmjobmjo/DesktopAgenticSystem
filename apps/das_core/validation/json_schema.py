"""Shared JSON schema helpers."""

from __future__ import annotations

from typing import Any, Iterable


class SchemaError(ValueError):
    pass


def require_dict(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise SchemaError(f"{name} must be a dict")
    return value


def require_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{name} must be a string")
    return value


def require_enum(value: Any, name: str, allowed: Iterable[str]) -> str:
    require_str(value, name)
    allowed_set = set(allowed)
    if value not in allowed_set:
        raise SchemaError(f"{name} must be one of {sorted(allowed_set)}")
    return value


def require_keys(data: dict, keys: Iterable[str], name: str = 'object') -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise SchemaError(f"{name} missing keys: {', '.join(missing)}")
