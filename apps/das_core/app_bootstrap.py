from __future__ import annotations

import atexit
from typing import Tuple

from core.common_data_area import CommonDataArea
from core.conversation_manager import ConversationManager
from settings.config_loader import load_settings_into_cda


def build_application() -> Tuple[CommonDataArea, ConversationManager]:
    cda = CommonDataArea()
    load_settings_into_cda(cda)

    from tools.tool_registry import sync_tools_to_db
    sync_tools_to_db(cda)

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

    conversation_manager = ConversationManager(cda)
    cda.set_runtime('conversation_manager', conversation_manager)

    try:
        from telagram_gateways.telegram_controller import TelegramController
        from telagram_gateways.telegram_service import TelegramChannelService

        tg_controller = TelegramController(cda=cda, conversation_manager=conversation_manager)
        tg_service = TelegramChannelService(cda=cda, telegram_controller=tg_controller)
        tg_service.start()
        cda.set_runtime('telegram_controller', tg_controller)
        cda.set_runtime('telegram_channel_service', tg_service)
        atexit.register(lambda: tg_service.stop())
    except Exception as e:
        print(f"Telegram channel init failed: {e}")

    try:
        from whatsapp_gateways.whatsapp_controller import WhatsAppController
        from whatsapp_gateways.whatsapp_service import WhatsAppFolderService

        wa_controller = WhatsAppController(cda=cda, conversation_manager=conversation_manager)
        wa_service = WhatsAppFolderService(cda=cda, whatsapp_controller=wa_controller)
        wa_service.start()
        cda.set_runtime('whatsapp_controller', wa_controller)
        cda.set_runtime('whatsapp_folder_service', wa_service)
        atexit.register(lambda: wa_service.stop())
    except Exception as e:
        print(f"WhatsApp folder bridge init failed: {e}")

    try:
        from core.scheduler_service import SchedulerService

        scheduler_service = SchedulerService(cda=cda, conversation_manager=conversation_manager)
        scheduler_service.start()
        cda.set_runtime('scheduler_service', scheduler_service)
        atexit.register(lambda: scheduler_service.stop())
    except Exception as e:
        print(f"Scheduler service init failed: {e}")

    return cda, conversation_manager


