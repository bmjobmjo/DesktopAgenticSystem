"""Compatibility entrypoint that delegates to apps/api_gateway/main.py."""

from __future__ import annotations

import runpy
from pathlib import Path


def _run() -> None:
    api_root = Path(__file__).resolve().parent / "apps" / "api_gateway"
    runpy.run_path(str(api_root / "main.py"), run_name="__main__")


if __name__ == "__main__":
    _run()
