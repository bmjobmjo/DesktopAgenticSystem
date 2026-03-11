"""Branding helpers for the Desktop Agentic System UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap

BRAND_NAME = "Desktop Agentic System"
BRAND_APP_ID = "DesktopAgenticSystem.Console"
BRAND_ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def build_brand_pixmap(size: int = 128, compact: bool | None = None) -> QPixmap:
    """Render the DAS logo into a transparent pixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    if compact is None:
        compact = size <= 32
    if compact:
        _paint_compact_brand_mark(painter, size)
    else:
        _paint_full_brand_mark(painter, size)
    painter.end()
    return pixmap


def build_brand_icon() -> QIcon:
    """Build a multi-resolution application icon for title bars and taskbars."""
    icon = QIcon()
    for size in BRAND_ICON_SIZES:
        icon.addPixmap(build_brand_pixmap(size, compact=size <= 32))
    return icon


def ensure_brand_icon_files(base_dir: str | Path | None = None) -> dict[str, Path]:
    """Persist the generated logo as on-disk assets for Windows shell APIs."""
    target_dir = Path(base_dir) if base_dir is not None else Path.cwd() / 'assets' / 'generated'
    target_dir.mkdir(parents=True, exist_ok=True)

    ico_path = target_dir / 'desktop_agentic_system.ico'
    png_path = target_dir / 'desktop_agentic_system.png'

    build_brand_pixmap(256, compact=False).save(str(ico_path), 'ICO')
    build_brand_pixmap(256, compact=False).save(str(png_path), 'PNG')
    return {'ico': ico_path, 'png': png_path}


def _apply_background(painter: QPainter, canvas: QRectF, radius: float) -> None:
    background = QLinearGradient(canvas.topLeft(), canvas.bottomRight())
    background.setColorAt(0.0, QColor("#0f2740"))
    background.setColorAt(0.52, QColor("#005fb8"))
    background.setColorAt(1.0, QColor("#14b8a6"))

    outline_pen = QPen(QColor(255, 255, 255, 40), max(canvas.width() * 0.015, 1.0))
    outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(outline_pen)
    painter.setBrush(background)
    painter.drawRoundedRect(canvas, radius, radius)


def _paint_compact_brand_mark(painter: QPainter, size: int) -> None:
    canvas = QRectF(size * 0.05, size * 0.05, size * 0.90, size * 0.90)
    _apply_background(painter, canvas, size * 0.20)

    screen = QRectF(
        canvas.left() + canvas.width() * 0.14,
        canvas.top() + canvas.height() * 0.16,
        canvas.width() * 0.72,
        canvas.height() * 0.54,
    )
    screen_pen = QPen(QColor("#f8fcff"), max(size * 0.075, 1.8))
    screen_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    screen_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(screen_pen)
    painter.setBrush(QColor(255, 255, 255, 18))
    painter.drawRoundedRect(screen, size * 0.09, size * 0.09)

    graph_pen = QPen(QColor(255, 255, 255, 210), max(size * 0.05, 1.6))
    graph_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    graph_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(graph_pen)
    points = (
        QPointF(screen.left() + screen.width() * 0.16, screen.top() + screen.height() * 0.68),
        QPointF(screen.left() + screen.width() * 0.38, screen.top() + screen.height() * 0.52),
        QPointF(screen.left() + screen.width() * 0.58, screen.top() + screen.height() * 0.60),
        QPointF(screen.left() + screen.width() * 0.80, screen.top() + screen.height() * 0.30),
    )
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)

    painter.setPen(Qt.PenStyle.NoPen)
    for point, color in zip(points, (QColor("#8be9fd"), QColor("#fde68a"), QColor("#c4b5fd"), QColor("#34d399"))):
        painter.setBrush(color)
        painter.drawEllipse(point, size * 0.075, size * 0.075)


def _paint_full_brand_mark(painter: QPainter, size: int) -> None:
    canvas = QRectF(size * 0.08, size * 0.08, size * 0.84, size * 0.84)
    _apply_background(painter, canvas, size * 0.19)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 34))
    painter.drawEllipse(
        QRectF(
            canvas.left() + canvas.width() * 0.08,
            canvas.top() + canvas.height() * 0.04,
            canvas.width() * 0.62,
            canvas.height() * 0.30,
        )
    )

    screen = QRectF(
        canvas.left() + canvas.width() * 0.18,
        canvas.top() + canvas.height() * 0.20,
        canvas.width() * 0.64,
        canvas.height() * 0.42,
    )
    screen_pen = QPen(QColor("#f8fcff"), max(size * 0.042, 2.0))
    screen_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    screen_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(screen_pen)
    painter.setBrush(QColor(255, 255, 255, 18))
    painter.drawRoundedRect(screen, size * 0.055, size * 0.055)

    graph_pen = QPen(QColor(255, 255, 255, 185), max(size * 0.02, 1.6))
    graph_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    graph_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(graph_pen)

    points = (
        QPointF(screen.left() + screen.width() * 0.16, screen.top() + screen.height() * 0.68),
        QPointF(screen.left() + screen.width() * 0.36, screen.top() + screen.height() * 0.50),
        QPointF(screen.left() + screen.width() * 0.56, screen.top() + screen.height() * 0.60),
        QPointF(screen.left() + screen.width() * 0.78, screen.top() + screen.height() * 0.30),
    )
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)

    node_radius = size * 0.045
    painter.setPen(Qt.PenStyle.NoPen)
    for point, color in zip(points, (QColor("#8be9fd"), QColor("#fde68a"), QColor("#c4b5fd"), QColor("#34d399"))):
        painter.setBrush(color)
        painter.drawEllipse(point, node_radius, node_radius)

    stand_pen = QPen(QColor(255, 255, 255, 220), max(size * 0.034, 1.9))
    stand_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(stand_pen)
    painter.drawLine(
        QPointF(screen.center().x(), screen.bottom() + canvas.height() * 0.05),
        QPointF(screen.center().x(), screen.bottom() + canvas.height() * 0.13),
    )
    painter.drawLine(
        QPointF(screen.center().x() - canvas.width() * 0.13, screen.bottom() + canvas.height() * 0.15),
        QPointF(screen.center().x() + canvas.width() * 0.13, screen.bottom() + canvas.height() * 0.15),
    )

    spark_pen = QPen(QColor("#fff7b8"), max(size * 0.017, 1.2))
    spark_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(spark_pen)
    spark_center = QPointF(screen.right() - screen.width() * 0.12, screen.top() - canvas.height() * 0.02)
    spark_size = size * 0.045
    painter.drawLine(
        QPointF(spark_center.x() - spark_size, spark_center.y()),
        QPointF(spark_center.x() + spark_size, spark_center.y()),
    )
    painter.drawLine(
        QPointF(spark_center.x(), spark_center.y() - spark_size),
        QPointF(spark_center.x(), spark_center.y() + spark_size),
    )
