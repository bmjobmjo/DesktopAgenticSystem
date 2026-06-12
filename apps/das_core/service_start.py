"""Start DAS core services without launching the desktop UI."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_SELF_DIR = Path(__file__).resolve().parent
if sys.path:
    try:
        if Path(sys.path[0]).resolve() == _SELF_DIR:
            sys.path.pop(0)
    except Exception:
        pass

import logging as _stdlib_logging

sys.modules.setdefault("logging", _stdlib_logging)
if str(_SELF_DIR) not in sys.path:
    sys.path.insert(0, str(_SELF_DIR))

from app_bootstrap import build_application
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start DAS core runtime as a headless service.")
    parser.add_argument("--detach", action="store_true", help="Run service in background and return.")
    return parser.parse_args()


def _detach_process() -> int:
    current_script = Path(__file__).resolve()
    cmd = [sys.executable, str(current_script)]
    for arg in sys.argv[1:]:
        if arg != "--detach":
            cmd.append(arg)

    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / "service_start.out.log"
    err_path = log_dir / "service_start.err.log"
    out_fh = out_path.open("a", encoding="utf-8")
    err_fh = err_path.open("a", encoding="utf-8")

    kwargs: dict[str, object] = {
        "cwd": str(Path(__file__).resolve().parent),
        "stdin": subprocess.DEVNULL,
        "stdout": out_fh,
        "stderr": err_fh,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(cmd, **kwargs)
    print(f"DAS service started in background (pid={proc.pid}).")
    print(f"stdout: {out_path}")
    print(f"stderr: {err_path}")
    return 0


def _shutdown(cda, conversation_manager) -> None:
    try:
        tg_service = cda.get_runtime("telegram_channel_service")
        if tg_service:
            tg_service.stop()
            cda.set_runtime("telegram_channel_service", None)
    except Exception:
        pass

    try:
        wa_service = cda.get_runtime("whatsapp_folder_service")
        if wa_service:
            wa_service.stop()
            cda.set_runtime("whatsapp_folder_service", None)
    except Exception:
        pass

    try:
        scheduler_service = cda.get_runtime("scheduler_service")
        if scheduler_service:
            scheduler_service.stop()
            cda.set_runtime("scheduler_service", None)
    except Exception:
        pass

    try:
        conversation_manager.shutdown()
    except Exception:
        pass


def _run_foreground(args: argparse.Namespace) -> int:
    cda, conversation_manager = build_application()
    atexit.register(lambda: _shutdown(cda, conversation_manager))

    stop_requested = {"value": False}

    def _handle_stop(signum, _frame) -> None:
        stop_requested["value"] = True
        print(f"Received signal {signum}. Stopping DAS service...")

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, _handle_stop)

    print("DAS core service started (headless mode). Press Ctrl+C to stop.")
    try:
        while not stop_requested["value"]:
            time.sleep(1.0)
    finally:
        _shutdown(cda, conversation_manager)
    return 0


def main() -> int:
    args = _parse_args()
    if args.detach:
        return _detach_process()
    return _run_foreground(args)


if __name__ == "__main__":
    raise SystemExit(main())
