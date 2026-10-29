import argparse
import os
import re
import socket
import subprocess
import threading
import webbrowser

from waitress import serve

from app import create_app
from app.config import DATA_DIR
from app.db import DB_PATH

HOST = "127.0.0.1"


def _excluded_port_ranges() -> list[tuple[int, int]]:
    if os.name != "nt":
        return []

    try:
        completed = subprocess.run(
            [
                "netsh",
                "interface",
                "ipv4",
                "show",
                "excludedportrange",
                "protocol=tcp",
            ],
            capture_output=True,
            timeout=5,
            text=True,
            encoding="oem",
            errors="ignore",
        )
    except (OSError, subprocess.SubprocessError):
        return []

    ranges = []
    for start, end in re.findall(r"\b(\d{2,5})\s+(\d{2,5})\b", completed.stdout):
        ranges.append((int(start), int(end)))
    return ranges


def _is_excluded(port: int, ranges) -> bool:
    return any(start <= port <= end for start, end in ranges)


def pick_port() -> int:
    ranges = _excluded_port_ranges()

    for _ in range(24):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((HOST, 0))
            port = sock.getsockname()[1]
        if not _is_excluded(port, ranges):
            return port

    for port in range(5155, 6501):
        if _is_excluded(port, ranges):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port

    raise RuntimeError("没有找到可用端口，请用 --port 手动指定")


def _env_port() -> int:
    try:
        return int(os.environ.get("KAOTI_PORT", "0"))
    except ValueError:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="启动本地题库")
    parser.add_argument("--port", type=int, default=0, help="指定端口，默认自动选择")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发模式：修改 Python 代码后自动重启（使用 Flask 开发服务器）",
    )
    args = parser.parse_args()

    port = args.port or _env_port() or pick_port()
    app = create_app()
    url = f"http://{HOST}:{port}/"

    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if not is_reloader_child:
        print(f"[kaoti] serving at {url}", flush=True)
        print(f"[kaoti] database: {DB_PATH}", flush=True)
        print(f"[kaoti] data directory: {DATA_DIR}", flush=True)
        print("[kaoti] press Ctrl+C to stop", flush=True)
        if args.reload:
            print("[kaoti] hot reload is on", flush=True)

        if not args.no_browser:
            threading.Timer(1.2, webbrowser.open, args=(url,)).start()

    if args.reload:
        os.environ["KAOTI_PORT"] = str(port)
        app.run(host=HOST, port=port, debug=False, use_reloader=True)
        return

    try:
        serve(app, host=HOST, port=port, threads=4, _quiet=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
