import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.branding import build_brand_icon, build_brand_pixmap


def _get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_brand_pixmap_renders_at_requested_size() -> None:
    _get_app()
    pixmap = build_brand_pixmap(64)
    assert not pixmap.isNull()
    assert pixmap.width() == 64
    assert pixmap.height() == 64


def test_brand_icon_exposes_multiple_sizes() -> None:
    _get_app()
    icon = build_brand_icon()
    sizes = {(size.width(), size.height()) for size in icon.availableSizes()}
    assert (16, 16) in sizes
    assert (256, 256) in sizes


from pathlib import Path
from ui.branding import ensure_brand_icon_files


def test_brand_icon_files_are_written(tmp_path: Path) -> None:
    _get_app()
    paths = ensure_brand_icon_files(tmp_path)
    assert paths["ico"].exists()
    assert paths["png"].exists()
