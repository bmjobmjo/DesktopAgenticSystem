"""Project logging package that proxies the standard library logging module.

This avoids name conflicts by executing the stdlib logging package in this
namespace, while still allowing project-specific logging utilities.
"""

from __future__ import annotations

import os as _os
import sys as _sys
import sysconfig as _sysconfig
from pathlib import Path as _Path


def _resolve_stdlib_logging_init() -> _Path:
    candidates: list[_Path] = []

    stdlib_from_sysconfig = _sysconfig.get_path("stdlib")
    if stdlib_from_sysconfig:
        candidates.append(_Path(stdlib_from_sysconfig) / "logging" / "__init__.py")

    candidates.append(_Path(_sys.base_prefix) / "Lib" / "logging" / "__init__.py")
    candidates.append(_Path(_sys.prefix) / "Lib" / "logging" / "__init__.py")
    candidates.append(_Path(_os.__file__).resolve().parent / "logging" / "__init__.py")

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Unable to locate standard-library logging package. "
        f"Checked: {[str(p) for p in candidates]}"
    )


_stdlib_init_path = _resolve_stdlib_logging_init()
_stdlib_logging_dir = str(_stdlib_init_path.parent)
if _stdlib_logging_dir not in __path__:
    __path__.append(_stdlib_logging_dir)

_code = _stdlib_init_path.read_text(encoding="utf-8")
exec(compile(_code, str(_stdlib_init_path), "exec"), globals())
