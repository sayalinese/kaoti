import os
import sys
from pathlib import Path

APP_NAME = "Kaoti"
DISPLAY_NAME = "考题"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_root()))
    return app_root()


def _ensure_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_data_dir() -> Path:
    override = os.environ.get("KAOTI_DATA_DIR")
    if override:
        candidate = Path(override).expanduser().resolve()
        if _ensure_writable(candidate):
            return candidate

    candidate = app_root() / "data"
    if _ensure_writable(candidate):
        return candidate

    fallback = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA_DIR = resolve_data_dir()
SETTINGS_PATH = DATA_DIR / "settings.json"
WEB_DIR = resource_root() / "web"
