from flask import Blueprint, jsonify, request

from ..errors import InvalidInput
from ..services import llm
from ..services.openai_compat import ApiError
from ..settings_store import SettingsError, load_settings

bp = Blueprint("ocr", __name__, url_prefix="/api/ocr")


@bp.post("/validate")
def validate_text():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InvalidInput("请求体必须是 JSON 对象")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise InvalidInput("text 不能为空")
    if len(text) > 12000:
        raise InvalidInput("OCR 文本不能超过 12000 个字符")

    try:
        config = load_settings()["llm"]
        result = llm.validate_ocr_text(config, text)
    except SettingsError as exc:
        return jsonify({"error": str(exc)}), 500
    except ApiError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"ok": True, **result})
