"""Helpers for building bounded file payloads for LLM calls."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    import docx  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    docx = None


_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".log", ".sql", ".xml",
    ".html", ".css", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs",
    ".sh", ".ps1", ".bat",
}
_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".ico",
}
_BINARY_HINT_EXTENSIONS = {
    ".mp3", ".wav", ".mp4", ".avi", ".mov", ".zip", ".rar", ".7z", ".exe",
    ".dll", ".bin",
}

_DEFAULT_PER_FILE_CHAR_LIMIT = 12000
_DEFAULT_TOTAL_CHAR_LIMIT = 24000
_DEFAULT_IMAGE_INLINE_MAX_BYTES = 8 * 1024 * 1024


def _setting_int(cda: Any, key: str, default: int) -> int:
    if cda is None:
        return default
    try:
        raw = cda.get_setting(key, default)
        value = int(raw)
        return value if value > 0 else default
    except Exception:
        return default


def _read_text_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _looks_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            sample = handle.read(2048)
    except Exception:
        return False
    return b"\x00" in sample


def _guess_mime_type(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _build_inline_image(path: Path, cda: Any = None) -> tuple[Dict[str, Any], bool, str]:
    max_bytes = _setting_int(cda, "llm_attachment_image_max_bytes", _DEFAULT_IMAGE_INLINE_MAX_BYTES)
    try:
        raw = path.read_bytes()
    except Exception as exc:
        return {}, False, f"Failed to read image: {exc}"

    if not raw:
        return {}, False, "Empty image file"
    if len(raw) > max_bytes:
        return {}, False, f"Image exceeds inline limit ({len(raw)} > {max_bytes} bytes)"

    mime_type = _guess_mime_type(path)
    encoded = base64.b64encode(raw).decode("ascii")
    return (
        {
            "kind": "image",
            "mime_type": mime_type,
            "data_base64": encoded,
            "data_url": f"data:{mime_type};base64,{encoded}",
        },
        True,
        "",
    )


def _extract_content(path: Path) -> tuple[str, bool, str]:
    ext = path.suffix.lower()

    if ext in _BINARY_HINT_EXTENSIONS:
        return "", False, f"Unsupported binary file type: {ext or 'unknown'}"

    if ext == ".pdf":
        if PdfReader is None:
            return "", False, "PyPDF2 not installed"
        try:
            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text, True, ""
        except Exception as exc:
            return "", False, f"Failed to read PDF: {exc}"

    if ext in {".docx", ".doc"}:
        if docx is None:
            return "", False, "python-docx not installed"
        try:
            document = docx.Document(str(path))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            return text, True, ""
        except Exception as exc:
            return "", False, f"Failed to read document: {exc}"

    if ext in _TEXT_EXTENSIONS:
        try:
            return _read_text_file(path), True, ""
        except Exception as exc:
            return "", False, f"Failed to read text file: {exc}"

    if _looks_binary(path):
        return "", False, f"Binary content omitted: {ext or 'unknown'}"

    try:
        return _read_text_file(path), True, ""
    except Exception as exc:
        return "", False, f"Unsupported or unreadable file: {exc}"


def build_llm_attachments(
    paths: Iterable[Path | str] | None,
    cda: Any = None,
) -> List[Dict[str, Any]]:
    per_file_limit = _setting_int(cda, "llm_attachment_char_limit", _DEFAULT_PER_FILE_CHAR_LIMIT)
    total_limit = _setting_int(cda, "llm_attachment_total_char_limit", _DEFAULT_TOTAL_CHAR_LIMIT)
    remaining_total = total_limit
    attachments: List[Dict[str, Any]] = []

    for raw_path in paths or []:
        path = Path(raw_path)
        entry: Dict[str, Any] = {
            "name": path.name,
            "path": str(path),
            "suffix": path.suffix.lower(),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "kind": "text",
            "mime_type": _guess_mime_type(path) if path.exists() else "",
            "readable": False,
            "content": "",
            "truncated": False,
            "omission_reason": "",
        }

        if not path.exists() or not path.is_file():
            entry["omission_reason"] = "File does not exist"
            attachments.append(entry)
            continue

        if path.suffix.lower() in _IMAGE_EXTENSIONS:
            image_payload, readable, omission_reason = _build_inline_image(path, cda)
            entry["readable"] = readable
            entry["omission_reason"] = omission_reason
            if readable:
                entry.update(image_payload)
            attachments.append(entry)
            continue

        extracted, readable, omission_reason = _extract_content(path)
        entry["readable"] = readable
        entry["omission_reason"] = omission_reason

        if not readable:
            attachments.append(entry)
            continue

        normalized = extracted.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            entry["omission_reason"] = "No legible text extracted"
            attachments.append(entry)
            continue

        budget = min(per_file_limit, max(remaining_total, 0))
        if budget <= 0:
            entry["omission_reason"] = "Attachment budget exhausted"
            attachments.append(entry)
            continue

        content = normalized[:budget]
        truncated = len(normalized) > budget
        if truncated:
            content = content.rstrip() + "\n...[truncated]"
        entry["content"] = content
        entry["readable"] = True
        entry["truncated"] = truncated
        entry["char_count"] = len(content)
        remaining_total -= len(content)
        attachments.append(entry)

    return attachments


def format_attachments_for_prompt(attachments: List[Dict[str, Any]] | None) -> str:
    if not attachments:
        return ""

    lines = ["[ATTACHED FILE CONTENT]"]
    for idx, item in enumerate(attachments, start=1):
        lines.append(f"{idx}. name: {item.get('name', '')}")
        lines.append(f"   path: {item.get('path', '')}")
        lines.append(f"   readable: {str(bool(item.get('readable'))).lower()}")
        kind = str(item.get("kind", "text") or "text").strip()
        if kind:
            lines.append(f"   kind: {kind}")
        mime_type = str(item.get("mime_type", "") or "").strip()
        if mime_type:
            lines.append(f"   mime_type: {mime_type}")
        lines.append(f"   truncated: {str(bool(item.get('truncated'))).lower()}")
        size_bytes = item.get("size_bytes", 0)
        if isinstance(size_bytes, int):
            lines.append(f"   size_bytes: {size_bytes}")
        omission_reason = str(item.get("omission_reason", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        if kind == "image" and bool(item.get("readable")):
            lines.append("   note: Image is attached natively to the LLM request. Use the image directly; do not assume OCR text.")
            continue
        if content:
            lines.append("   content:")
            for content_line in content.splitlines():
                lines.append(f"   {content_line}")
        elif omission_reason:
            lines.append(f"   note: {omission_reason}")
    lines.append("[END ATTACHED FILE CONTENT]")
    return "\n".join(lines)


def extract_attachment_paths(attachments: List[Dict[str, Any]] | None) -> List[str]:
    out: List[str] = []
    for item in attachments or []:
        path = str(item.get("path", "") or "").strip()
        if path:
            out.append(path)
    return out
