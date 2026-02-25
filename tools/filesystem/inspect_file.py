"""Inspect file tool."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict

from tools.filesystem import ensure_accessible


def inspect_file(file_path: str) -> Dict:
    """
    Get detailed metadata about a file.

    Args:
        file_path (str): The absolute path to the file to inspect.

    Returns:
        Dict: A dictionary containing 'success' (bool) and 'data' (dict) or 'error' (str).
              Data includes 'size_bytes', 'modified_time', and 'extension'.
    """

    ok, error = ensure_accessible(file_path)
    if not ok:
        return {'success': False, 'error': error}

    if not os.path.exists(file_path):
        return {'success': False, 'error': 'File does not exist.'}

    stat = os.stat(file_path)
    ext = os.path.splitext(file_path)[1]
    return {
        'success': True,
        'data': {
            'file_path': file_path,
            'size_bytes': stat.st_size,
            'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'extension': ext
        }
    }
