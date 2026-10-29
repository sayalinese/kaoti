import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from ..errors import InvalidInput
from .question_utils import clean_text, infer_type, validate_question

QUESTION_RE = re.compile(r"^(?:\[[^\]]{0,12}\]\s*)?(\d{1,4})\s*[、.．:：)）]\s*(.+)$")
OPTION_RE = re.compile(r"^([A-H])\s*[.．、]?\s*(.+)$")
ANSWER_LINE_RE = re.compile(r"^(?:正确答案|确答案|参考答案|答案|Answer|answer)\s*[:：]\s*(.*)$")
ANSWER_TAIL_RE = re.compile(r"(?:正确答案|确答案|参考答案|答案|Answer|answer)\s*[:：]\s*([A-H、,，\s]*)\s*$")
EXPLANATION_RE = re.compile(r"^(?:【解析】|解析)\s*[:：]?\s*(.*)$")

SECTION_LABELS = ("单选题", "多选题", "判断题")


@dataclass
class SourceLine:
    text: str
    style: str


def _heading_level(style: str, text: str) -> int:
    style_lower = (style or "").lower()
    if "heading 1" in style_lower or "标题 1" in style_lower:
        return 1
    if "heading 2" in style_lower or "标题 2" in style_lower:
        return 2
    match = re.match(r"^(#{1,2})\s+(.+)$", text)
    if match:
        return len(match.group(1))
    return 0


def _strip_heading(text: str) -> str:
    return re.sub(r"^#{1,2}\s*", "", text).strip()


def _detect_section(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text)
    compact = re.sub(r"^[一二三四五六七八九十百0-9]+[、.．]", "", compact)
    compact = compact.lstrip("、.．")
    for label in SECTION_LABELS:
        if compact in (label, label + "部分"):
            return label
    return None


def _is_list_style(style: str) -> bool:
    style_lower = (style or "").lower()
    return "list paragraph" in style_lower or "列表" in style_lower


def _derive_subject(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^\s*\d{4}\s*年?", "", stem)
    stem = re.sub(r"(理论)?(复习)?(题库|资料|试卷|答案)$", "", stem)
    stem = stem.strip(" _-")
    return stem or "未分类科目"


def _extract_lines(document) -> list[SourceLine]:
    lines = []
    for paragraph in document.paragraphs:
        style = paragraph.style.name if paragraph.style else ""
        text = paragraph.text.replace("\xa0", " ").replace("\t", " ")
        for part in re.split(r"[\r\n\v]+", text):
            part = part.strip()
            if part:
                lines.append(SourceLine(part, style))
    return lines


def _accept_option(current: dict, key: str) -> bool:
    used = {option["key"] for option in current["options"]}
    if key in used:
        return False
    if not current["options"]:
        return key == "A"
    last_key = current["options"][-1]["key"]
    return key > last_key


def _append_text(current: dict, text: str) -> None:
    if current["options"]:
        current["options"][-1]["text"] += text
    else:
        current["stem_parts"].append(text)


def _fill_option_gap(current: dict, next_key: str) -> None:
    if not current["options"] or not current["pending_options"]:
        return
    last_key = current["options"][-1]["key"]
    for code in range(ord(last_key) + 1, ord(next_key)):
        if not current["pending_options"]:
            break
        key = chr(code)
        current["options"].append(
            {"key": key, "text": current["pending_options"].pop(0)}
        )
        current["notes"].append(f"已自动补全无标签选项 {key}")
    if current["pending_options"]:
        current["options"][-1]["text"] += "".join(current["pending_options"])
        current["pending_options"].clear()


def _finalize(current: dict) -> dict:
    stem_parts = list(current["stem_parts"])
    options = list(current["options"])
    notes = list(current["notes"])

    if (
        not options
        and len(stem_parts) >= 3
        and stem_parts[0].rstrip().endswith(("(", "（", ":", "："))
    ):
        tail = stem_parts[1:]
        if 2 <= len(tail) <= 8 and all(len(part) <= 30 for part in tail):
            options = [
                {"key": chr(ord("A") + index), "text": part}
                for index, part in enumerate(tail)
            ]
            stem_parts = stem_parts[:1]
            notes.append("已自动补全无标签选项")

    pending = list(current["pending_options"])
    if pending:
        option_keys = {option["key"] for option in options}
        raw_answer = current["answer_raw"] or ""
        raw_letters = sorted(set(re.findall(r"[A-H]", raw_answer.upper())))
        missing = [letter for letter in raw_letters if letter not in option_keys]
        for key in missing:
            if not pending:
                break
            options.append({"key": key, "text": pending.pop(0)})
            notes.append(f"已自动补全无标签选项 {key}")
        if pending:
            if options:
                options[-1]["text"] += "".join(pending)
            else:
                stem_parts.append("".join(pending))
        options.sort(key=lambda item: item["key"])

    stem = "".join(stem_parts).strip()
    type_ = infer_type(options, current["answer_raw"], current["section"])
    data, warnings = validate_question(
        {
            "type": type_,
            "stem": stem,
            "options": options,
            "answer": current["answer_raw"],
            "explanation": "".join(current["explanation_parts"]),
        }
    )
    status = "ready" if not warnings else "needs_review"

    return {
        "number": current["number"],
        "type": data["type"],
        "stem": data["stem"],
        "options": data["options"],
        "answer": data["answer"],
        "explanation": data["explanation"],
        "status": status,
        "warnings": warnings,
        "notes": list(dict.fromkeys(notes)),
    }


def _parse_questions(lines: list[SourceLine]) -> list[dict]:
    questions = []
    current = None
    section = None

    for line in lines:
        text = line.text
        if _heading_level(line.style, text):
            if current:
                questions.append(_finalize(current))
                current = None
            continue

        section_label = _detect_section(text)
        if section_label:
            if current:
                questions.append(_finalize(current))
                current = None
            section = section_label
            continue

        question_match = QUESTION_RE.match(text)
        if question_match:
            if current:
                questions.append(_finalize(current))
            current = {
                "number": int(question_match.group(1)),
                "stem_parts": [question_match.group(2)],
                "options": [],
                "answer_raw": None,
                "explanation_parts": [],
                "pending_options": [],
                "notes": [],
                "section": section,
            }
            continue

        if current is None:
            continue

        if text.startswith("你的答案"):
            continue

        if current["answer_raw"] is not None:
            explanation_match = EXPLANATION_RE.match(text)
            if explanation_match:
                current["explanation_parts"].append(explanation_match.group(1))
            continue

        tail_match = ANSWER_TAIL_RE.search(text)
        if tail_match:
            before = text[: tail_match.start()].strip()
            if before:
                option_match = OPTION_RE.match(before)
                if option_match and _accept_option(current, option_match.group(1)):
                    current["options"].append(
                        {
                            "key": option_match.group(1),
                            "text": clean_text(option_match.group(2)),
                        }
                    )
                else:
                    _append_text(current, before)
            current["answer_raw"] = tail_match.group(1) or ""
            continue

        answer_match = ANSWER_LINE_RE.match(text)
        if answer_match:
            current["answer_raw"] = answer_match.group(1).strip()
            continue

        option_match = OPTION_RE.match(text)
        if option_match:
            key = option_match.group(1)
            if (
                not current["options"]
                and key in ("B", "C", "D")
                and len(current["stem_parts"]) >= 2
            ):
                candidate = current["stem_parts"][-1].strip()
                if len(candidate) <= 40 and not candidate.endswith(
                    ("。", "？", "！", ")", "）", ":", "：")
                ):
                    current["options"].append(
                        {"key": "A", "text": current["stem_parts"].pop()}
                    )
                    current["notes"].append("已自动补全无标签选项 A")

            if _accept_option(current, key):
                _fill_option_gap(current, key)
                current["options"].append(
                    {"key": key, "text": clean_text(option_match.group(2))}
                )
                continue

        if current["options"] and _is_list_style(line.style) and len(text) <= 40:
            current["pending_options"].append(text)
            continue

        _append_text(current, text)

    if current:
        questions.append(_finalize(current))
    return questions


def _dedupe(questions: list[dict]) -> tuple[list[dict], int]:
    groups = {}
    order = []
    for question in questions:
        key = question["stem"] + "\x1f" + "\x1e".join(
            option["key"] + ":" + option["text"] for option in question["options"]
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(question)

    unique = []
    removed = 0
    for key in order:
        group = groups[key]
        if len(group) == 1:
            unique.append(group[0])
            continue

        def score(question):
            return (
                question["status"] == "ready",
                len(question["answer"]),
                len(question["options"]),
                -len(question["warnings"]),
            )

        best = max(group, key=score)
        others = [str(question["number"]) for question in group if question is not best]
        note = "与第 " + "、".join(others) + " 题内容重复，已合并"
        if len({tuple(question["answer"]) for question in group}) > 1:
            note += "（重复题答案不一致，已保留首题答案）"
        best["notes"] = list(dict.fromkeys(best.get("notes", []) + [note]))
        unique.append(best)
        removed += len(group) - 1

    return unique, removed


def _build_preview(lines: list[SourceLine], filename: str, source_hash: str) -> dict:
    if not lines:
        raise InvalidInput("文档是空的，没有可导入的内容")

    subject_heading = None
    paper_heading = None
    document_title = None
    for line in lines:
        level = _heading_level(line.style, line.text)
        if level == 1 and not subject_heading:
            subject_heading = _strip_heading(line.text)[:80]
            continue
        if level == 2 and not paper_heading:
            paper_heading = _strip_heading(line.text)[:80]
            continue
        if level == 0 and not document_title:
            plain = line.text.strip()
            if (
                not QUESTION_RE.match(plain)
                and not OPTION_RE.match(plain)
                and not ANSWER_LINE_RE.match(plain)
                and not _detect_section(plain)
                and len(plain) <= 80
            ):
                document_title = plain

    parsed = _parse_questions(lines)
    questions, duplicates_removed = _dedupe(parsed)
    if not questions:
        raise InvalidInput("没有识别到题目，请检查文档格式")

    for index, question in enumerate(questions, start=1):
        question["client_id"] = f"q{index}"

    filename = Path(filename).name
    suggested_subject = subject_heading or _derive_subject(filename)
    suggested_paper = paper_heading or document_title or Path(filename).stem
    if suggested_paper == suggested_subject:
        suggested_paper = Path(filename).stem

    types = Counter(question["type"] for question in questions)
    ready_count = sum(1 for question in questions if question["status"] == "ready")
    warning_count = sum(1 for question in questions if question["warnings"])

    return {
        "source_file": filename,
        "source_hash": source_hash,
        "document_title": document_title or "",
        "suggested_subject": suggested_subject.strip() or "未分类科目",
        "suggested_paper": suggested_paper.strip() or Path(filename).stem,
        "questions": questions,
        "notes": [
            f"原始识别 {len(parsed)} 道，合并 {duplicates_removed} 道重复题后保留 {len(questions)} 道。"
        ]
        if duplicates_removed
        else [],
        "stats": {
            "parsed_total": len(parsed),
            "total": len(questions),
            "ready": ready_count,
            "needs_review": len(questions) - ready_count,
            "duplicates_removed": duplicates_removed,
            "warnings": warning_count,
            "types": {
                "single": types.get("single", 0),
                "multiple": types.get("multiple", 0),
                "tf": types.get("tf", 0),
            },
        },
    }


def parse_docx(data: bytes, filename: str) -> dict:
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise InvalidInput("无法读取 DOCX 文件，请确认文件没有损坏") from exc

    return _build_preview(
        _extract_lines(document),
        filename,
        hashlib.sha256(data).hexdigest(),
    )


def parse_text(text: str, filename: str, source_hash: str | None = None) -> dict:
    # OCR/PDF text can merge adjacent options; split them before parsing.
    text = re.sub(r"\s+(?=[A-H]\s*[.．、:：])", "\n", text or "")
    text = re.sub(r"(?<=[A-Ha-z])(?=(?:Answer|answer|答案|正确答案)\s*[:：])", "\n", text)
    lines = [
        SourceLine(part.strip(), "")
        for part in re.split(r"[\r\n\v]+", text or "")
        if part.strip()
    ]
    raw = (text or "").encode("utf-8")
    return _build_preview(
        lines,
        filename,
        source_hash or hashlib.sha256(raw).hexdigest(),
    )
