"""Compatibility import shim for apps/das_core/app_bootstrap.py."""

from __future__ import annotations

import importlib.util
import logging as _stdlib_logging  # Ensure stdlib logging is loaded before das_core path imports.
import os
import sys
from pathlib import Path

_core_root = Path(__file__).resolve().parent / "apps" / "das_core"
_core_bootstrap = _core_root / "app_bootstrap.py"
if str(_core_root) not in sys.path:
    sys.path.insert(0, str(_core_root))
sys.modules.setdefault("logging", _stdlib_logging)
_spec = importlib.util.spec_from_file_location("das_core_app_bootstrap", _core_bootstrap)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load app bootstrap module from {_core_bootstrap}")

_module = importlib.util.module_from_spec(_spec)
_previous_cwd = os.getcwd()
try:
    os.chdir(_core_root)
    _spec.loader.exec_module(_module)
finally:
    os.chdir(_previous_cwd)

build_application = _module.build_application
