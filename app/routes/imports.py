import hashlib
import mimetypes
from pathlib import Path

from flask import Blueprint, jsonify, request

from .. import library_store
from ..errors import InvalidInput
from ..services import llm, ocr
from ..services.docx_parser import parse_docx, parse_text
from ..services.openai_compat import ApiError
from ..services.pdf_parser import parse_pdf
from ..settings_store import SettingsError, load_settings

bp = Blueprint("imports", __name__, url_prefix="/api/import")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _suggest_missing_answers(preview: dict, config: dict) -> None:
    for question in preview.get("questions", []):
        if question.get("answer"):
            continue
        try:
            suggestion = llm.suggest_question_answer(config, question)
        except (ApiError, SettingsError) as exc:
            question["answer_suggestion_error"] = str(exc)
            continue
        question["answer"] = suggestion["answer"]
        question["answer_source"] = "llm"
        question["answer_suggestion"] = {
            "model": suggestion["model"],
            "latency_ms": suggestion["latency_ms"],
            "explanation": suggestion["explanation"],
        }
        question["status"] = "needs_review"
        warnings = [
            warning
            for warning in question.setdefault("warnings", [])
            if warning not in ("缺少答案", "没有有效答案")
        ]
        question["warnings"] = warnings
        warnings.append("答案由 DeepSeek 生成，请人工确认")


@bp.post("/preview")
def preview():
    file = request.files.get("file")
    if not file or not file.filename:
        raise InvalidInput("请选择要导入的 Word、PDF 或图片文件")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise InvalidInput("支持 DOCX、PDF、PNG、JPG、JPEG 和 WEBP 文件")

    data = file.read()
    if not data:
        raise InvalidInput("文件是空的")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidInput("文件超过 25MB，请拆分后再导入")

    try:
        if suffix == ".docx":
            preview = parse_docx(data, file.filename)
        elif suffix == ".pdf":
            preview = parse_pdf(data, file.filename)
        else:
            settings = load_settings()
            mime_type = file.mimetype or ""
            if not mime_type.startswith("image/"):
                mime_type = IMAGE_MIME_TYPES.get(suffix) or mimetypes.guess_type(file.filename)[0]
            if not mime_type or not mime_type.startswith("image/"):
                raise InvalidInput("无法识别图片格式")
            result = ocr.recognize_image(
                settings["ocr"], data, mime_type
            )
            recognized_text = result["text"]
            validation = None
            try:
                checked = llm.validate_ocr_text(settings["llm"], recognized_text)
                recognized_text = checked["text"]
                validation = {"ok": True, **checked}
            except (ApiError, SettingsError) as exc:
                validation = {"ok": False, "error": str(exc)}
            try:
                structured = llm.structure_ocr_text(settings["llm"], recognized_text)
                parse_source = structured["text"]
                validation = {
                    **(validation or {}),
                    "ok": True,
                    "structured": structured,
                }
            except (ApiError, SettingsError) as exc:
                parse_source = recognized_text
                validation = {"ok": False, "error": str(exc), **(validation or {})}
            try:
                preview = parse_text(
                    parse_source,
                    file.filename,
                    source_hash=hashlib.sha256(data).hexdigest(),
                )
            except InvalidInput:
                if parse_source != recognized_text:
                    preview = parse_text(
                        recognized_text,
                        file.filename,
                        source_hash=hashlib.sha256(data).hexdigest(),
                    )
                else:
                    raise
            preview["ocr"] = {
                "model": result["model"],
                "latency_ms": result["latency_ms"],
                "validation": validation,
            }
    except (ApiError, SettingsError) as exc:
        raise InvalidInput(str(exc)) from exc
    try:
        settings = load_settings()
        _suggest_missing_answers(preview, settings["llm"])
    except SettingsError:
        pass
    return jsonify(preview)


@bp.post("/commit")
def commit():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InvalidInput("请求体必须是 JSON 对象")

    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise InvalidInput("questions 必须是数组")

    return (
        jsonify(
            library_store.create_import(
                subject_name=payload.get("subject", ""),
                paper_name=payload.get("paper", ""),
                source_file=payload.get("source_file", ""),
                source_hash=payload.get("source_hash", ""),
                questions=questions,
            )
        ),
        201,
    )
