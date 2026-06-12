from __future__ import annotations

import argparse
import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class SpaRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        self._spa_directory = Path(directory).resolve()
        super().__init__(*args, directory=str(self._spa_directory), **kwargs)

    def translate_path(self, path: str) -> str:
        parsed = urlsplit(path)
        clean_path = posixpath.normpath(unquote(parsed.path))
        parts = [part for part in clean_path.split("/") if part and part not in (".", "..")]
        candidate = self._spa_directory.joinpath(*parts)
        return str(candidate)

    def do_GET(self) -> None:
        target = Path(self.translate_path(self.path))
        if target.exists() and target.is_file():
            return super().do_GET()

        self.path = "/index.html"
        return super().do_GET()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the built OASIS web UI with SPA fallback.")
    parser.add_argument("--root", default="apps/ui_web/dist", help="Path to the built UI dist folder.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8080, help="Bind port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"UI root not found: {root}")

    handler = lambda *a, **kw: SpaRequestHandler(*a, directory=str(root), **kw)
    server = ThreadingHTTPServer((args.host, int(args.port)), handler)
    print(f"OASIS UI serving {root} at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
