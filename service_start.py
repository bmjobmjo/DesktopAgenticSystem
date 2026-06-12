"""Compatibility entrypoint that delegates to apps/das_core/service_start.py."""

from __future__ import annotations

import os
import runpy
from pathlib import Path


def _run() -> None:
    core_root = Path(__file__).resolve().parent / "apps" / "das_core"
    os.chdir(core_root)
    runpy.run_path(str(core_root / "service_start.py"), run_name="__main__")


if __name__ == "__main__":
    _run()
