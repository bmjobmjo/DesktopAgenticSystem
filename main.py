"""Application entrypoint."""

from __future__ import annotations

import os
import sys
import atexit
from pathlib import Path
from PySide6.QtWidgets import QApplication

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.executor import Executor
from core.router import Router
from settings.config_loader import load_settings_into_cda
from ui.chat_ui import ChatUI
from ui.branding import BRAND_APP_ID, BRAND_NAME, build_brand_icon, ensure_brand_icon_files


def build_controller() -> Controller:
    cda = CommonDataArea()
    load_settings_into_cda(cda)

    from tools.tool_registry import sync_tools_to_db
    sync_tools_to_db(cda)

    # Register Custom Agents
    from agents.registry import register_agent
    custom_agents = cda.get_setting('custom_agents', [])
    for agent in custom_agents:
        try:
            register_agent(agent['name'], agent['description'], agent['prompt_path'])
            print(f"Registered custom agent: {agent['name']}")
        except Exception as e:
            print(f"Failed to register agent {agent.get('name')}: {e}")

    from llm.factory import get_llm_client
    llm_client = get_llm_client(cda)
    cda.set_runtime('llm_client', llm_client)

    router = Router(cda)
    executor = Executor(cda)
    controller = Controller(cda=cda, router=router, executor=executor)

    cda.set_runtime('router', router)
    cda.set_runtime('executor', executor)
    cda.set_runtime('controller', controller)

    # Optional WhatsApp channel integration (local webhook + gateway client).
    try:
        from core.whatsapp_channel import WhatsAppChannelService
        wa_service = WhatsAppChannelService(cda=cda, controller=controller)
        wa_service.start()
        cda.set_runtime('whatsapp_channel_service', wa_service)
        atexit.register(lambda: wa_service.stop())
    except Exception as e:
        print(f"WhatsApp channel init failed: {e}")

    # Optional Telegram channel integration (polling mode).
    try:
        from telagram_gateways.telegram_controller import TelegramController
        from telagram_gateways.telegram_service import TelegramChannelService

        tg_controller = TelegramController(cda=cda, controller=controller)
        tg_service = TelegramChannelService(cda=cda, telegram_controller=tg_controller)
        tg_service.start()
        cda.set_runtime('telegram_controller', tg_controller)
        cda.set_runtime('telegram_channel_service', tg_service)
        atexit.register(lambda: tg_service.stop())
    except Exception as e:
        print(f"Telegram channel init failed: {e}")

    # Optional Scheduler service integration (background polling).
    try:
        from core.scheduler_service import SchedulerService

        scheduler_service = SchedulerService(cda=cda, controller=controller)
        scheduler_service.start()
        cda.set_runtime('scheduler_service', scheduler_service)
        atexit.register(lambda: scheduler_service.stop())
    except Exception as e:
        print(f"Scheduler service init failed: {e}")

    return controller


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
    controller = build_controller()

    def _shutdown_whatsapp_channel() -> None:
        try:
            cda = controller.cda
            wa_service = cda.get_runtime('whatsapp_channel_service')
            if wa_service:
                wa_service.stop()
                cda.set_runtime('whatsapp_channel_service', None)
            tg_service = cda.get_runtime('telegram_channel_service')
            if tg_service:
                tg_service.stop()
                cda.set_runtime('telegram_channel_service', None)
            scheduler_service = cda.get_runtime('scheduler_service')
            if scheduler_service:
                scheduler_service.stop()
                cda.set_runtime('scheduler_service', None)
        except Exception:
            pass

    app.aboutToQuit.connect(_shutdown_whatsapp_channel)
    ui = ChatUI(controller)
    ui.setWindowIcon(app_icon)
    ui.show()
    _apply_windows_taskbar_icon(ui, icon_path)
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


