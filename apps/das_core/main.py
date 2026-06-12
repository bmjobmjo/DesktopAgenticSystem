"""Application entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QSplashScreen

from app_bootstrap import build_application
from ui.chat_ui import ChatUI
from ui.branding import BRAND_APP_ID, BRAND_NAME, build_brand_icon, build_brand_pixmap, ensure_brand_icon_files


def _configure_windows_identity() -> None:
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(BRAND_APP_ID)
    except Exception:
        pass


def _apply_windows_taskbar_icon(window, icon_path: Path | None) -> None:
    if sys.platform != 'win32' or icon_path is None or not icon_path.exists():
        return
    try:
        import ctypes

        image_icon = 1
        lr_loadfromfile = 0x00000010
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1

        user32 = ctypes.windll.user32
        hwnd = int(window.winId())
        small_handle = user32.LoadImageW(None, str(icon_path), image_icon, 16, 16, lr_loadfromfile)
        big_handle = user32.LoadImageW(None, str(icon_path), image_icon, 32, 32, lr_loadfromfile)
        if small_handle:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, small_handle)
        if big_handle:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, big_handle)
        window._brand_hicon_small = small_handle
        window._brand_hicon_big = big_handle
    except Exception:
        pass


def main() -> None:
    _configure_windows_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(BRAND_NAME)
    app.setApplicationDisplayName(BRAND_NAME)
    icon_assets = ensure_brand_icon_files(Path.cwd() / 'assets' / 'generated')
    icon_path = icon_assets.get('ico')
    app_icon = build_brand_icon()
    if icon_path and icon_path.exists():
        app_icon.addFile(str(icon_path))
    app.setWindowIcon(app_icon)

    splash = QSplashScreen(build_brand_pixmap(300), Qt.WindowType.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    splash.setFont(QFont("Segoe UI", 10))
    splash.show()
    splash.showMessage("Starting OASIS...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, QColor("#ffffff"))
    app.processEvents()

    splash.showMessage("Loading services...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, QColor("#ffffff"))
    app.processEvents()
    cda, conversation_manager = build_application()

    def _shutdown_services() -> None:
        try:
            tg_service = cda.get_runtime('telegram_channel_service')
            if tg_service:
                tg_service.stop()
                cda.set_runtime('telegram_channel_service', None)
            wa_service = cda.get_runtime('whatsapp_folder_service')
            if wa_service:
                wa_service.stop()
                cda.set_runtime('whatsapp_folder_service', None)
            scheduler_service = cda.get_runtime('scheduler_service')
            if scheduler_service:
                scheduler_service.stop()
                cda.set_runtime('scheduler_service', None)
            conversation_manager.shutdown()
        except Exception:
            pass

    app.aboutToQuit.connect(_shutdown_services)
    splash.showMessage("Opening workspace...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, QColor("#ffffff"))
    app.processEvents()
    ui = ChatUI(conversation_manager=conversation_manager, cda=cda)
    ui.setWindowIcon(app_icon)
    ui.show()
    _apply_windows_taskbar_icon(ui, icon_path)
    splash.finish(ui)
    sys.exit(app.exec())


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        from core.db_schema import init_db
        init_db()
    except Exception as e:
        print(f"Database initialization failed: {e}")
    main()
