from flask import Blueprint, jsonify, request

from .. import library_store
from ..errors import InvalidInput

bp = Blueprint("library", __name__, url_prefix="/api")


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@bp.get("/library")
def get_library():
    return jsonify(library_store.list_tree())


@bp.get("/questions")
def get_questions():
    return jsonify(
        library_store.list_questions(
            paper_id=request.args.get("paper_id") or None,
            favorite_only=request.args.get("favorite") in ("1", "true"),
            query=request.args.get("q", ""),
            type_filter=request.args.get("type", ""),
            status=request.args.get("status", ""),
            page=_int_arg("page", 1),
            page_size=_int_arg("page_size", 20),
        )
    )


@bp.get("/questions/<question_id>")
def get_question(question_id: str):
    return jsonify(library_store.get_question(question_id))


@bp.put("/questions/<question_id>")
def update_question(question_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InvalidInput("请求体必须是 JSON 对象")
    return jsonify(library_store.update_question(question_id, payload))


@bp.post("/questions/<question_id>/favorite")
def favorite_question(question_id: str):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("favorite"), bool):
        raise InvalidInput("favorite 必须是布尔值")
    return jsonify(library_store.set_favorite(question_id, payload["favorite"]))


@bp.delete("/papers/<paper_id>")
def delete_paper(paper_id: str):
    return jsonify(library_store.delete_paper(paper_id))
