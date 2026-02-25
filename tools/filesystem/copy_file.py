"""Copy file tool."""

from __future__ import annotations

import os
import shutil
from typing import Dict

from tools.filesystem import ensure_accessible


def copy_file(source_path: str, destination_path: str) -> Dict:
    """
    Copy a file from source to destination.

    Args:
        source_path (str): The absolute path of the source file.
        destination_path (str): The absolute path of the destination file.

    Returns:
        Dict: A dictionary containing 'success' (bool) and 'data' (dict) or 'error' (str).
    """

    ok_src, error = ensure_accessible(source_path)
    if not ok_src:
        return {'success': False, 'error': error}

    ok_dst, error = ensure_accessible(destination_path)
    if not ok_dst:
        return {'success': False, 'error': error}

    if not os.path.exists(source_path):
        return {'success': False, 'error': 'Source file does not exist.'}

    destination_dir = os.path.dirname(destination_path)
    if destination_dir:
        os.makedirs(destination_dir, exist_ok=True)

    shutil.copy2(source_path, destination_path)
    return {'success': True, 'data': {'source': source_path, 'destination': destination_path}}
