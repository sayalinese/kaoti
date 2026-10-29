import json
import uuid

from .db import db, now_iso
from .errors import InvalidInput, NotFound
from .services.question_utils import TYPES, normalize_answer


def _loads(value, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _load_attempt(conn, attempt_id: str):
    row = conn.execute(
        "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
    ).fetchone()
    if not row:
        raise NotFound("练习不存在")
    return row


def _paper_info(conn, paper_id: str) -> tuple[str, str]:
    row = conn.execute(
        """
        SELECT s.name AS subject_name, p.name AS paper_name
        FROM papers p JOIN subjects s ON s.id = p.subject_id
        WHERE p.id = ?
        """,
        (paper_id,),
    ).fetchone()
    if not row:
        raise NotFound("考题不存在")
    return row["subject_name"], row["paper_name"]


def _answer_counts(conn, attempt_id: str) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS answered, COALESCE(SUM(is_correct), 0) AS correct
        FROM attempt_answers WHERE attempt_id = ?
        """,
        (attempt_id,),
    ).fetchone()
    return row["answered"], row["correct"]


def create_attempt(payload: dict) -> dict:
    paper_id = (payload.get("paper_id") or "").strip() or None
    favorites_only = bool(payload.get("favorites_only"))
    raw_types = payload.get("types")
    if isinstance(raw_types, list):
        types = []
        for item in raw_types:
            if item in TYPES and item not in types:
                types.append(item)
    else:
        types = []

    try:
        count = int(payload.get("count") or 20)
    except (TypeError, ValueError):
        count = 20
    count = min(1000, max(1, count))

    if not paper_id and not favorites_only:
        raise InvalidInput("请选择要练习的考题")

    where = ["q.status = 'ready'", "q.answer NOT IN ('', '[]')"]
    params = []
    if paper_id:
        where.append("q.paper_id = ?")
        params.append(paper_id)
    if favorites_only:
        where.append("f.question_id IS NOT NULL")
    if types:
        where.append("q.type IN (" + ",".join("?" for _ in types) + ")")
        params.extend(types)

    with db() as conn:
        label = "全部收藏"
        if paper_id:
            subject_name, paper_name = _paper_info(conn, paper_id)
            if favorites_only:
                label = f"收藏 · {paper_name}"
            else:
                label = f"{subject_name} · {paper_name}"
        elif not favorites_only:
            raise InvalidInput("请选择要练习的考题")

        rows = conn.execute(
            f"""
            SELECT q.id
            FROM questions q
            JOIN papers p ON p.id = q.paper_id
            LEFT JOIN favorites f ON f.question_id = q.id
            WHERE {' AND '.join(where)}
            ORDER BY RANDOM()
            LIMIT ?
            """,
            [*params, count],
        ).fetchall()
        question_ids = [row["id"] for row in rows]
        if not question_ids:
            raise InvalidInput("没有可用的题目，请先补充答案或收藏题目")

        attempt_id = str(uuid.uuid4())
        scope = "favorites" if favorites_only else "paper"
        conn.execute(
            """
            INSERT INTO attempts (
                id, paper_id, scope, scope_label, filters, question_ids,
                total, correct_count, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                attempt_id,
                paper_id,
                scope,
                label,
                json.dumps(
                    {"types": types, "count": count}, ensure_ascii=False
                ),
                json.dumps(question_ids, ensure_ascii=False),
                len(question_ids),
                now_iso(),
            ),
        )

    return {
        "id": attempt_id,
        "scope": scope,
        "scope_label": label,
        "total": len(question_ids),
    }


def get_attempt(attempt_id: str) -> dict:
    with db() as conn:
        attempt = _load_attempt(conn, attempt_id)
        question_ids = _loads(attempt["question_ids"], [])
        answers = {
            row["question_id"]: row
            for row in conn.execute(
                "SELECT * FROM attempt_answers WHERE attempt_id = ?", (attempt_id,)
            ).fetchall()
        }

        rows = []
        if question_ids:
            placeholders = ",".join("?" for _ in question_ids)
            rows = conn.execute(
                f"""
                SELECT q.*, p.name AS paper_name, s.name AS subject_name,
                       CASE WHEN f.question_id IS NULL THEN 0 ELSE 1 END AS favorite
                FROM questions q
                JOIN papers p ON p.id = q.paper_id
                JOIN subjects s ON s.id = p.subject_id
                LEFT JOIN favorites f ON f.question_id = q.id
                WHERE q.id IN ({placeholders})
                """,
                question_ids,
            ).fetchall()

    row_map = {row["id"]: row for row in rows}
    finished = bool(attempt["finished_at"])
    questions = []
    for question_id in question_ids:
        row = row_map.get(question_id)
        if not row:
            continue
        answer = answers.get(question_id)
        reveal = finished or answer is not None
        questions.append(
            {
                "id": row["id"],
                "number": row["number"],
                "type": row["type"],
                "stem": row["stem"],
                "options": _loads(row["options"], []),
                "answer_source": row["answer_source"] if "answer_source" in row.keys() else "source",
                "explanation": row["explanation"] if reveal else "",
                "subject_name": row["subject_name"],
                "paper_name": row["paper_name"],
                "favorite": bool(row["favorite"]),
                "chosen": _loads(answer["chosen"], []) if answer else [],
                "answered": answer is not None,
                "is_correct": bool(answer["is_correct"]) if answer else None,
                "correct_answer": _loads(row["answer"], []) if reveal else None,
            }
        )

    answered = sum(1 for question in questions if question["answered"])
    correct = sum(1 for question in questions if question["is_correct"])
    return {
        "id": attempt["id"],
        "paper_id": attempt["paper_id"],
        "scope": attempt["scope"],
        "scope_label": attempt["scope_label"],
        "filters": _loads(attempt["filters"], {}),
        "started_at": attempt["started_at"],
        "finished_at": attempt["finished_at"],
        "finished": finished,
        "total": len(questions),
        "answered": answered,
        "correct": correct,
        "questions": questions,
    }


def submit_answer(attempt_id: str, payload: dict) -> dict:
    question_id = (payload.get("question_id") or "").strip()
    chosen = payload.get("chosen")
    if not question_id:
        raise InvalidInput("缺少题目编号")

    with db() as conn:
        attempt = _load_attempt(conn, attempt_id)
        question_ids = _loads(attempt["question_ids"], [])
        if question_id not in question_ids:
            raise InvalidInput("该题不属于本次练习")

        existing = conn.execute(
            "SELECT * FROM attempt_answers WHERE attempt_id = ? AND question_id = ?",
            (attempt_id, question_id),
        ).fetchone()

        question = conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not question:
            raise NotFound("题目不存在")

        options = _loads(question["options"], [])
        correct_answer = _loads(question["answer"], [])
        if not correct_answer:
            raise InvalidInput("该题答案待补充，无法判分")

        if existing:
            answered, correct = _answer_counts(conn, attempt_id)
            return {
                "question_id": question_id,
                "is_correct": bool(existing["is_correct"]),
                "correct_answer": correct_answer,
                "explanation": question["explanation"],
                "answered": answered,
                "correct": correct,
                "total": len(question_ids),
                "finished": bool(attempt["finished_at"]),
            }

        if attempt["finished_at"]:
            raise InvalidInput("本次练习已结束")

        option_keys = {option["key"] for option in options}
        valid, _ = normalize_answer(chosen, option_keys)
        if not valid:
            raise InvalidInput("请先选择答案")

        is_correct = set(valid) == set(correct_answer)
        conn.execute(
            """
            INSERT INTO attempt_answers (attempt_id, question_id, chosen, is_correct, answered_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                question_id,
                json.dumps(valid, ensure_ascii=False),
                1 if is_correct else 0,
                now_iso(),
            ),
        )

        answered, correct = _answer_counts(conn, attempt_id)
        finished = answered >= len(question_ids)
        if finished:
            conn.execute(
                "UPDATE attempts SET finished_at = ? WHERE id = ?",
                (now_iso(), attempt_id),
            )
        conn.execute(
            "UPDATE attempts SET correct_count = ? WHERE id = ?",
            (correct, attempt_id),
        )

    return {
        "question_id": question_id,
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "explanation": question["explanation"],
        "answered": answered,
        "correct": correct,
        "total": len(question_ids),
        "finished": finished,
    }


def finish_attempt(attempt_id: str) -> dict:
    with db() as conn:
        attempt = _load_attempt(conn, attempt_id)
        if not attempt["finished_at"]:
            conn.execute(
                "UPDATE attempts SET finished_at = ? WHERE id = ?",
                (now_iso(), attempt_id),
            )
    return get_attempt(attempt_id)
