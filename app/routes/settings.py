from flask import Blueprint, jsonify, request

from ..services import llm, ocr
from ..services.openai_compat import ApiError
from ..settings_store import (
    SettingsError,
    load_settings,
    public_view,
    save_settings,
)

bp = Blueprint("settings", __name__, url_prefix="/api/settings")


@bp.get("")
def get_settings():
    try:
        return jsonify(public_view())
    except SettingsError as exc:
        return jsonify({"error": str(exc)}), 500


@bp.put("")
def update_settings():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "请求体必须是 JSON"}), 400
    try:
        updated = save_settings(payload)
        return jsonify(public_view(updated))
    except SettingsError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/test/llm")
def test_llm():
    try:
        config = load_settings()["llm"]
    except SettingsError as exc:
        return jsonify({"error": str(exc)}), 500

    if not config["api_key"]:
        return jsonify({"error": "请先填写并保存大模型 API Key"}), 400

    try:
        return jsonify({"ok": True, **llm.test_connection(config)})
    except ApiError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@bp.post("/test/ocr")
def test_ocr():
    try:
        settings = load_settings()
        config = settings["ocr"]
    except SettingsError as exc:
        return jsonify({"error": str(exc)}), 500

    if not config["api_key"]:
        return jsonify({"error": "请先填写并保存 OCR API Key"}), 400

    payload = request.get_json(silent=True) or {}
    image = payload.get("image", "")

    try:
        result = ocr.test_connection(config, image)
        response = {"ok": True, **result, "validation": None}
        try:
            response["validation"] = {
                "ok": True,
                **llm.validate_ocr_text(settings["llm"], result.get("text", "")),
            }
        except (ApiError, SettingsError) as exc:
            response["validation"] = {"ok": False, "error": str(exc)}
        return jsonify(response)
    except ApiError as exc:
        status = 400 if "测试图片" in str(exc) else 502
        return jsonify({"ok": False, "error": str(exc)}), status
