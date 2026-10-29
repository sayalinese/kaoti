import json
import math
import uuid

from .db import db, now_iso
from .errors import Conflict, InvalidInput, NotFound
from .services.question_utils import TYPES, clean_text, validate_question


def _loads(value, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _question_dict(row) -> dict:
    keys = row.keys()
    data = {
        "id": row["id"],
        "number": row["number"],
        "type": row["type"],
        "stem": row["stem"],
        "options": _loads(row["options"], []),
        "answer": _loads(row["answer"], []),
        "answer_source": row["answer_source"] if "answer_source" in keys else "source",
        "explanation": row["explanation"],
        "status": row["status"],
        "review_note": row["review_note"],
        "paper_id": row["paper_id"],
        "favorite": bool(row["favorite"]) if "favorite" in keys else False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    for key in ("subject_id", "subject_name", "paper_name"):
        if key in keys:
            data[key] = row[key]
    return data


def list_tree() -> dict:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id AS subject_id,
                s.name AS subject_name,
                p.id AS paper_id,
                p.name AS paper_name,
                p.created_at AS paper_created,
                (SELECT COUNT(*) FROM questions q WHERE q.paper_id = p.id) AS question_count,
                (SELECT COUNT(*) FROM questions q
                 WHERE q.paper_id = p.id AND q.status = 'ready') AS ready_count,
                (SELECT COUNT(*) FROM favorites f
                 JOIN questions q ON q.id = f.question_id
                 WHERE q.paper_id = p.id) AS favorite_count
            FROM subjects s
            JOIN papers p ON p.subject_id = s.id
            ORDER BY s.created_at, p.created_at
            """
        ).fetchall()

        total_questions = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        total_ready = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE status = 'ready'"
        ).fetchone()[0]
        total_favorites = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]

    subjects = {}
    for row in rows:
        subject_id = row["subject_id"]
        if subject_id not in subjects:
            subjects[subject_id] = {
                "id": subject_id,
                "name": row["subject_name"],
                "papers": [],
            }
        subjects[subject_id]["papers"].append(
            {
                "id": row["paper_id"],
                "name": row["paper_name"],
                "question_count": row["question_count"],
                "ready_count": row["ready_count"],
                "favorite_count": row["favorite_count"],
            }
        )

    return {
        "subjects": list(subjects.values()),
        "totals": {
            "questions": total_questions,
            "ready": total_ready,
            "favorites": total_favorites,
        },
    }


def list_questions(
    paper_id: str | None = None,
    favorite_only: bool = False,
    query: str = "",
    type_filter: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    page = max(1, int(page))
    page_size = min(100, max(1, int(page_size)))

    where = ["1 = 1"]
    params = []
    if paper_id:
        where.append("q.paper_id = ?")
        params.append(paper_id)
    if favorite_only:
        where.append("f.question_id IS NOT NULL")
    if type_filter in TYPES:
        where.append("q.type = ?")
        params.append(type_filter)
    if status in ("ready", "needs_review"):
        where.append("q.status = ?")
        params.append(status)
    query = clean_text(query, 200)
    if query:
        where.append("(q.stem LIKE ? OR q.options LIKE ?)")
        pattern = f"%{query}%"
        params.extend([pattern, pattern])

    where_sql = " AND ".join(where)
    joins = """
        FROM questions q
        JOIN papers p ON p.id = q.paper_id
        JOIN subjects s ON s.id = p.subject_id
        LEFT JOIN favorites f ON f.question_id = q.id
    """

    if favorite_only and not paper_id:
        order_sql = "ORDER BY f.created_at DESC, q.id"
    else:
        order_sql = "ORDER BY p.created_at, q.number IS NULL, q.number, q.id"

    offset = (page - 1) * page_size
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) {joins} WHERE {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT q.*, p.name AS paper_name, s.id AS subject_id, s.name AS subject_name,
                   CASE WHEN f.question_id IS NULL THEN 0 ELSE 1 END AS favorite
            {joins}
            WHERE {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    pages = max(1, math.ceil(total / page_size)) if total else 1
    return {
        "questions": [_question_dict(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "total": total,
        },
    }


def get_question(question_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            """
            SELECT q.*, p.name AS paper_name, s.id AS subject_id, s.name AS subject_name,
                   CASE WHEN f.question_id IS NULL THEN 0 ELSE 1 END AS favorite
            FROM questions q
            JOIN papers p ON p.id = q.paper_id
            JOIN subjects s ON s.id = p.subject_id
            LEFT JOIN favorites f ON f.question_id = q.id
            WHERE q.id = ?
            """,
            (question_id,),
        ).fetchone()
    if not row:
        raise NotFound("题目不存在")
    return _question_dict(row)


def update_question(question_id: str, payload: dict) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            raise NotFound("题目不存在")

        merged = {
            "type": payload.get("type", row["type"]),
            "stem": payload.get("stem", row["stem"]),
            "options": payload.get("options", _loads(row["options"], [])),
            "answer": payload.get("answer", _loads(row["answer"], [])),
            "explanation": payload.get("explanation", row["explanation"]),
        }
        data, warnings = validate_question(merged)
        if not data["stem"] or len(data["options"]) < 2:
            raise InvalidInput("题干和至少两个选项不能为空")

        status = "ready" if not warnings else "needs_review"
        review_note = "；".join(warnings)
        conn.execute(
            """
            UPDATE questions
            SET type = ?, stem = ?, options = ?, answer = ?, explanation = ?,
                answer_source = 'manual', status = ?, review_note = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["type"],
                data["stem"],
                json.dumps(data["options"], ensure_ascii=False),
                json.dumps(data["answer"], ensure_ascii=False),
                data["explanation"],
                status,
                review_note,
                now_iso(),
                question_id,
            ),
        )
    return get_question(question_id)


def set_favorite(question_id: str, favorite: bool) -> dict:
    with db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not exists:
            raise NotFound("题目不存在")
        if favorite:
            conn.execute(
                "INSERT OR IGNORE INTO favorites (question_id, created_at) VALUES (?, ?)",
                (question_id, now_iso()),
            )
        else:
            conn.execute("DELETE FROM favorites WHERE question_id = ?", (question_id,))
    return {"question_id": question_id, "favorite": favorite}


def delete_paper(paper_id: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT id, subject_id FROM papers WHERE id = ?", (paper_id,)
        ).fetchone()
        if not row:
            raise NotFound("考题不存在")

        subject_id = row["subject_id"]
        conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE subject_id = ?", (subject_id,)
        ).fetchone()[0]
        subject_removed = False
        if remaining == 0:
            conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
            subject_removed = True

    return {"deleted": True, "subject_removed": subject_removed}


def create_import(
    subject_name: str,
    paper_name: str,
    source_file: str,
    source_hash: str,
    questions: list,
) -> dict:
    subject_name = clean_text(subject_name, 80)
    paper_name = clean_text(paper_name, 120)
    source_file = clean_text(source_file, 300)
    source_hash = clean_text(source_hash, 80)

    if not subject_name:
        raise InvalidInput("科目名称不能为空")
    if not paper_name:
        raise InvalidInput("考题名称不能为空")
    if not isinstance(questions, list) or not questions:
        raise InvalidInput("没有可导入的题目")
    if len(questions) > 2000:
        raise InvalidInput("一次最多导入 2000 道题")

    prepared = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise InvalidInput(f"第 {index} 道题格式无效")
        data, warnings = validate_question(item)
        if not data["stem"] or len(data["options"]) < 2:
            number = item.get("number") or index
            raise InvalidInput(
                f"第 {number} 道题缺少题干或不足两个选项，请先修正或取消勾选"
            )
        try:
            number = int(item.get("number")) if item.get("number") is not None else None
        except (TypeError, ValueError):
            number = None
        status = "ready" if not warnings else "needs_review"
        review_note = "；".join(warnings)
        if item.get("status") == "needs_review" and status == "ready":
            status = "needs_review"
            incoming = item.get("warnings")
            if isinstance(incoming, list):
                cleaned = [clean_text(warning, 200) for warning in incoming]
                cleaned = [warning for warning in cleaned if warning]
                review_note = "；".join(cleaned) or "导入时标记为待核对"
            else:
                review_note = "导入时标记为待核对"
        answer_source = item.get("answer_source", "source")
        if answer_source not in ("source", "llm", "manual"):
            answer_source = "source"
        prepared.append((number, data, status, review_note, answer_source))

    ready_count = sum(1 for item in prepared if item[2] == "ready")
    needs_review = len(prepared) - ready_count
    timestamp = now_iso()

    with db() as conn:
        subject = conn.execute(
            "SELECT id FROM subjects WHERE name = ?", (subject_name,)
        ).fetchone()
        if subject:
            subject_id = subject["id"]
        else:
            subject_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO subjects (id, name, created_at) VALUES (?, ?, ?)",
                (subject_id, subject_name, timestamp),
            )

        existing = conn.execute(
            "SELECT 1 FROM papers WHERE subject_id = ? AND name = ?",
            (subject_id, paper_name),
        ).fetchone()
        if existing:
            raise Conflict(
                f"科目「{subject_name}」下已有同名考题「{paper_name}」，请换一个名称"
            )

        paper_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO papers (id, subject_id, name, source_file, source_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (paper_id, subject_id, paper_name, source_file, source_hash, timestamp),
        )

        for number, data, status, review_note, answer_source in prepared:
            conn.execute(
                """
                INSERT INTO questions (
                    id, paper_id, number, type, stem, options, answer, answer_source, explanation,
                    status, review_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    paper_id,
                    number,
                    data["type"],
                    data["stem"],
                    json.dumps(data["options"], ensure_ascii=False),
                    json.dumps(data["answer"], ensure_ascii=False),
                    answer_source,
                    data["explanation"],
                    status,
                    review_note,
                    timestamp,
                    timestamp,
                ),
            )

    return {
        "paper_id": paper_id,
        "subject_id": subject_id,
        "imported": len(prepared),
        "ready": ready_count,
        "needs_review": needs_review,
    }
