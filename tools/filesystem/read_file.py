"""Read file tool."""

from __future__ import annotations

import os
from typing import Dict

from PyPDF2 import PdfReader

from tools.filesystem import ensure_accessible


def read_file(file_path: str) -> Dict:
    """
    Read the content of a file (Text or PDF).

    Args:
        file_path (str): The absolute path to the file to read.

    Returns:
        Dict: A dictionary containing 'success' (bool) and 'data' (dict) or 'error' (str).
              Data includes 'content' (str) and 'type' (str).
    """

    ok, error = ensure_accessible(file_path)
    if not ok:
        return {'success': False, 'error': error}

    if not os.path.exists(file_path):
        return {'success': False, 'error': 'File does not exist.'}

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.pdf':
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or '')
            content = '\n'.join(text_parts)
            return {'success': True, 'data': {'file_path': file_path, 'type': 'pdf', 'content': content}}

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return {'success': True, 'data': {'file_path': file_path, 'type': 'text', 'content': content}}
    except Exception as exc:  # noqa: BLE001
        return {'success': False, 'error': str(exc)}
