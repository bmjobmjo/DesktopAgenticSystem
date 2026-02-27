"""Application entrypoint."""

from __future__ import annotations

import os
import sys
from PySide6.QtWidgets import QApplication

from core.common_data_area import CommonDataArea
from core.controller import Controller
from core.executor import Executor
from core.router import Router
from settings.config_loader import load_settings_into_cda
from ui.chat_ui import ChatUI


def build_controller() -> Controller:
    cda = CommonDataArea()
    load_settings_into_cda(cda)

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

    return controller


def main() -> None:
    app = QApplication(sys.argv)
    controller = build_controller()
    ui = ChatUI(controller)
    ui.show()
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
