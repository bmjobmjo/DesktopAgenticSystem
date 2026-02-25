"""Application entrypoint."""

from __future__ import annotations

import os
import sys

# Hack to fix Tcl/Tk issue on Windows with venv
if sys.platform == 'win32':
    base_prefix = getattr(sys, 'base_prefix', sys.prefix)
    tcl_dir = os.path.join(base_prefix, 'tcl')
    if os.path.exists(tcl_dir):
        # Specific for Python 3.13 / tcl 8.6
        # Tcl/Tk often needs forward slashes even on Windows
        tcl_lib = os.path.join(tcl_dir, 'tcl8.6').replace('\\', '/')
        tk_lib = os.path.join(tcl_dir, 'tk8.6').replace('\\', '/')
        
        # Force overwrite to fix _MEI... issue
        os.environ['TCL_LIBRARY'] = tcl_lib
        os.environ['TK_LIBRARY'] = tk_lib
        
        # Ensure DLLs are in PATH
        dll_dir = os.path.join(base_prefix, 'DLLs')
        if os.path.exists(dll_dir):
             os.environ['PATH'] = dll_dir + os.pathsep + os.environ['PATH']

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
    controller = build_controller()
    ui = ChatUI(controller)
    ui.run()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        from core.db_schema import init_db
        init_db()
    except Exception as e:
        print(f"Database initialization failed: {e}")
    main()
