from flask import Blueprint, jsonify, request

from .. import quiz_store
from ..errors import InvalidInput
from ..services import llm
from ..services.openai_compat import ApiError
from ..settings_store import SettingsError, load_settings
from .. import library_store

bp = Blueprint("quiz", __name__, url_prefix="/api")


@bp.post("/quiz")
def create_quiz():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InvalidInput("请求体必须是 JSON 对象")
    return jsonify(quiz_store.create_attempt(payload)), 201


@bp.post("/questions/<question_id>/explain-options")
def explain_options(question_id: str):
    try:
        question = library_store.get_question(question_id)
        result = llm.explain_question_options(load_settings()["llm"], question)
    except SettingsError as exc:
        return jsonify({"error": str(exc)}), 500
    except ApiError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"ok": True, **result})


@bp.get("/attempts/<attempt_id>")
def get_attempt(attempt_id: str):
    return jsonify(quiz_store.get_attempt(attempt_id))


@bp.post("/attempts/<attempt_id>/answer")
def submit_answer(attempt_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InvalidInput("请求体必须是 JSON 对象")
    return jsonify(quiz_store.submit_answer(attempt_id, payload))


@bp.post("/attempts/<attempt_id>/finish")
def finish_attempt(attempt_id: str):
    return jsonify(quiz_store.finish_attempt(attempt_id))
