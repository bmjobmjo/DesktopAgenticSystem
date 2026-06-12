"""Image rendering tool based on PySide6."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from core.common_data_area import CommonDataArea
from tools.output_utils import (
    build_error_result,
    build_success_result,
    ensure_extension,
    normalize_columns,
    placeholder_text,
    replace_placeholders,
    resolve_output_path,
)

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap

SUPPORTED_FORMATS = {"png", "jpg", "jpeg", "webp"}
_QT_APP = None


def _ensure_qt_app() -> None:
    global _QT_APP
    if QGuiApplication.instance() is not None:
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _QT_APP = QGuiApplication([])


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _color(value: Any, default: str) -> QColor:
    color = QColor(str(value or default))
    return color if color.isValid() else QColor(default)


def _resolve_text(text: Any, data: Dict[str, Any] | None) -> str:
    return replace_placeholders(placeholder_text(text), data)


def _draw_text(painter: QPainter, element: Dict[str, Any], data: Dict[str, Any] | None) -> None:
    font = QFont(str(element.get("font_family", "Segoe UI") or "Segoe UI"), _coerce_int(element.get("font_size"), 16))
    font.setBold(bool(element.get("bold", False)))
    painter.setFont(font)
    painter.setPen(_color(element.get("color"), "#111111"))
    x = _coerce_int(element.get("x"), 0)
    y = _coerce_int(element.get("y"), 0)
    width = _coerce_int(element.get("width"), 400)
    height = _coerce_int(element.get("height"), 40)
    flags = Qt.AlignLeft | Qt.AlignVCenter
    painter.drawText(QRect(x, y, width, height), int(flags), _resolve_text(element.get("text", ""), data))


def _draw_rect(painter: QPainter, element: Dict[str, Any]) -> None:
    x = _coerce_int(element.get("x"), 0)
    y = _coerce_int(element.get("y"), 0)
    width = _coerce_int(element.get("width"), 100)
    height = _coerce_int(element.get("height"), 100)
    painter.fillRect(x, y, width, height, _color(element.get("fill"), "#ffffff"))
    border = _coerce_int(element.get("border_width"), 1)
    if border > 0:
        painter.setPen(QPen(_color(element.get("border_color"), "#cccccc"), border))
        painter.drawRect(x, y, width, height)


def _draw_image(painter: QPainter, element: Dict[str, Any]) -> None:
    path = Path(str(element.get("path", "") or "")).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image asset not found: {path}")
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        raise ValueError(f"Unsupported image asset: {path}")
    x = _coerce_int(element.get("x"), 0)
    y = _coerce_int(element.get("y"), 0)
    width = _coerce_int(element.get("width"), pixmap.width())
    height = _coerce_int(element.get("height"), pixmap.height())
    painter.drawPixmap(x, y, width, height, pixmap)


def _draw_table(painter: QPainter, element: Dict[str, Any], data: Dict[str, Any] | None) -> None:
    rows = element.get("rows") if isinstance(element.get("rows"), list) else []
    columns = normalize_columns(element.get("columns"), rows)
    if not columns:
        return
    x = _coerce_int(element.get("x"), 0)
    y = _coerce_int(element.get("y"), 0)
    width = _coerce_int(element.get("width"), 600)
    row_height = _coerce_int(element.get("row_height"), 32)
    col_width = max(1, width // len(columns))
    painter.setPen(QPen(_color(element.get("border_color"), "#555555"), 1))
    header_fill = _color(element.get("header_fill"), "#d9e8fb")
    body_fill = _color(element.get("body_fill"), "#ffffff")
    font = QFont(str(element.get("font_family", "Segoe UI") or "Segoe UI"), _coerce_int(element.get("font_size"), 11))
    painter.setFont(font)

    for idx, col in enumerate(columns):
        rect = QRect(x + idx * col_width, y, col_width, row_height)
        painter.fillRect(rect, header_fill)
        painter.drawRect(rect)
        painter.drawText(rect.adjusted(6, 0, -6, 0), int(Qt.AlignLeft | Qt.AlignVCenter), _resolve_text(col["header"], data))

    for row_index, row in enumerate(rows, start=1):
        for col_index, col in enumerate(columns):
            rect = QRect(x + col_index * col_width, y + row_index * row_height, col_width, row_height)
            painter.fillRect(rect, body_fill)
            painter.drawRect(rect)
            text = _resolve_text(row.get(col["key"], ""), data) if isinstance(row, dict) else ""
            painter.drawText(rect.adjusted(6, 0, -6, 0), int(Qt.AlignLeft | Qt.AlignVCenter), text)


def _draw_elements(painter: QPainter, elements: List[Dict[str, Any]] | None, data: Dict[str, Any] | None) -> int:
    count = 0
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        element_type = str(element.get("type", "text") or "text").strip().lower()
        if element_type == "text":
            _draw_text(painter, element, data)
        elif element_type == "rect":
            _draw_rect(painter, element)
        elif element_type == "image":
            _draw_image(painter, element)
        elif element_type == "table":
            _draw_table(painter, element, data)
        else:
            continue
        count += 1
    return count


def render_image(
    output_filename: str,
    format: str = "png",
    mode: str = "template",
    template_path: str | None = None,
    data: Dict[str, Any] | None = None,
    elements: List[Dict[str, Any]] | None = None,
    width: int | None = None,
    height: int | None = None,
    background: Dict[str, Any] | None = None,
    subfolder: str = "generated",
    options: Dict[str, Any] | None = None,
    status_callback=None,
) -> Dict[str, Any]:
    """Render an image file under the configured file storage path."""

    cda = CommonDataArea()
    output_path: Path | None = None
    try:
        fmt = str(format or "png").strip().lower() or "png"
        run_mode = str(mode or "template").strip().lower() or "template"
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError("format must be one of png, jpg, jpeg, webp.")
        if run_mode not in {"template", "canvas"}:
            raise ValueError("mode must be 'template' or 'canvas'.")

        _, output_path = resolve_output_path(output_filename, subfolder, cda)
        output_path = ensure_extension(output_path, fmt)

        if status_callback:
            status_callback("Rendering image...")
        _ensure_qt_app()

        image: QImage
        template_used = ""
        if run_mode == "template":
            if not template_path:
                raise ValueError("template_path is required when mode='template'.")
            template = Path(str(template_path)).resolve()
            if not template.exists():
                raise FileNotFoundError("Template image does not exist.")
            template_used = str(template)
            image = QImage(str(template))
            if image.isNull():
                raise ValueError("Template image could not be loaded.")
        else:
            canvas_width = _coerce_int(width, 1200)
            canvas_height = _coerce_int(height, 675)
            image = QImage(canvas_width, canvas_height, QImage.Format_ARGB32)
            fill_color = _color((background or {}).get("color"), "#ffffff")
            image.fill(fill_color)

        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            if background and run_mode == "template" and background.get("overlay_color"):
                painter.fillRect(image.rect(), _color(background.get("overlay_color"), "#ffffff"))
            elements_rendered = _draw_elements(painter, elements, data)
        finally:
            painter.end()

        if not image.save(str(output_path), fmt.upper()):
            raise RuntimeError("Image encoder failed to save the output file.")

        meta = {
            "template_used": template_used,
            "elements_rendered": elements_rendered,
            "placeholder_count": len(data or {}),
            "placeholders_filled": len(data or {}),
            "storage_subfolder": subfolder,
        }
        if options:
            meta["options"] = options
        if status_callback:
            status_callback("")
        return build_success_result(
            output_path=output_path,
            fmt=fmt,
            mode=run_mode,
            message="Image rendered successfully.",
            meta=meta,
            width=image.width(),
            height=image.height(),
        )
    except Exception as exc:
        if status_callback:
            status_callback("")
        return build_error_result(
            output_path=output_path,
            fmt=str(format or "png"),
            mode=str(mode or "template"),
            message="Image render failed.",
            error=str(exc),
            meta={"storage_subfolder": subfolder},
        )
