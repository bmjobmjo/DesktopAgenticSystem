"""List directory tool."""

from __future__ import annotations

import os
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
    # Implementation for inspect_file would go here.
    # For now, returning a placeholder as the implementation was not provided.
    ok, error = ensure_accessible(file_path)
    if not ok:
        return {'success': False, 'error': error}

    if not os.path.isfile(file_path):
        return {'success': False, 'error': 'File does not exist.'}

    try:
        stat_info = os.stat(file_path)
        file_size = stat_info.st_size
        modified_time = stat_info.st_mtime
        file_extension = os.path.splitext(file_path)[1]

        return {
            'success': True,
            'data': {
                'size_bytes': file_size,
                'modified_time': modified_time,
                'extension': file_extension,
                'file': file_path
            }
        }
    except Exception as e:
        return {'success': False, 'error': f'Error inspecting file: {e}'}


def list_directory(directory_path: str = "", path: str = "") -> Dict:
    """
    List the contents of a directory.

    Args:
        directory_path (str): The absolute path to the directory to list.
        path (str): Alias for directory_path used by some prompts.

    Returns:
        Dict: A dictionary containing 'success' (bool) and 'data' (dict) or 'error' (str).
              Data includes 'entries' (list of filenames) and 'directory' (path).
    """

    target_path = str(directory_path or path or "").strip()
    if not target_path:
        return {'success': False, 'error': 'directory_path (or path) is required.'}

    ok, error = ensure_accessible(target_path)
    if not ok:
        return {'success': False, 'error': error}

    if not os.path.isdir(target_path):
        return {'success': False, 'error': 'Directory does not exist.'}

    entries = sorted(os.listdir(target_path))
    return {'success': True, 'data': {'entries': entries, 'directory': target_path}}
