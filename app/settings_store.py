import json
import os
import threading
from copy import deepcopy

from .config import DATA_DIR, SETTINGS_PATH

LLM_PROVIDERS = ("deepseek", "siliconflow", "custom")
OCR_PROVIDERS = ("siliconflow",)

DEFAULT_SETTINGS = {
    "llm": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "api_key": "",
    },
    "ocr": {
        "provider": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "PaddlePaddle/PaddleOCR-VL-1.5",
        "api_key": "",
    },
}

_lock = threading.Lock()


class SettingsError(ValueError):
    pass


def _defaults() -> dict:
    return deepcopy(DEFAULT_SETTINGS)


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return _defaults()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SettingsError(f"设置文件无法读取：{exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError("设置文件格式无效")

    merged = _defaults()
    for section in ("llm", "ocr"):
        incoming = raw.get(section)
        if isinstance(incoming, dict):
            for key in merged[section]:
                value = incoming.get(key)
                if isinstance(value, str):
                    merged[section][key] = value
    return merged


def _validate_section(name: str, current: dict, incoming, providers) -> dict:
    if not isinstance(incoming, dict):
        raise SettingsError(f"{name}配置格式无效")

    result = dict(current)

    provider = str(incoming.get("provider", current["provider"])).strip()
    if provider not in providers:
        raise SettingsError(f"{name}服务商无效")

    base_url = str(incoming.get("base_url", current["base_url"])).strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise SettingsError(f"{name}接口地址必须以 http:// 或 https:// 开头")

    model = str(incoming.get("model", current["model"])).strip()
    if not model:
        raise SettingsError(f"{name}模型 ID 不能为空")

    result["provider"] = provider
    result["base_url"] = base_url
    result["model"] = model

    if incoming.get("clear_key") is True:
        result["api_key"] = ""
    else:
        new_key = incoming.get("api_key")
        if isinstance(new_key, str) and new_key.strip():
            result["api_key"] = new_key.strip()
    return result


def save_settings(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise SettingsError("请求内容格式无效")

    with _lock:
        current = load_settings()
        updated = deepcopy(current)
        if "llm" in payload:
            updated["llm"] = _validate_section(
                "大模型", current["llm"], payload["llm"], LLM_PROVIDERS
            )
        if "ocr" in payload:
            updated["ocr"] = _validate_section(
                "OCR", current["ocr"], payload["ocr"], OCR_PROVIDERS
            )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".tmp")
        tmp.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, SETTINGS_PATH)
        return updated


def _key_hint(key: str) -> str:
    if not key:
        return ""
    tail = key[-4:] if len(key) >= 4 else key
    return f"尾号 {tail}"


def public_view(settings: dict | None = None) -> dict:
    data = settings or load_settings()
    view = {}
    for section in ("llm", "ocr"):
        item = dict(data[section])
        key = item.pop("api_key", "")
        item["has_key"] = bool(key)
        item["key_hint"] = _key_hint(key)
        view[section] = item
    view["data_dir"] = str(DATA_DIR)
    view["settings_path"] = str(SETTINGS_PATH)
    return view
