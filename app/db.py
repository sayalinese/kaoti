import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "exams.db"
SCHEMA_VERSION = 2

LEGACY_COLUMNS = {
    "papers": {
        "source_file": "TEXT NOT NULL DEFAULT ''",
        "source_hash": "TEXT NOT NULL DEFAULT ''",
    },
    "questions": {
        "number": "INTEGER",
        "type": "TEXT NOT NULL DEFAULT 'single'",
        "stem": "TEXT NOT NULL DEFAULT ''",
        "options": "TEXT NOT NULL DEFAULT '[]'",
        "answer": "TEXT NOT NULL DEFAULT '[]'",
        "answer_source": "TEXT NOT NULL DEFAULT 'source'",
        "explanation": "TEXT NOT NULL DEFAULT ''",
        "status": "TEXT NOT NULL DEFAULT 'needs_review'",
        "review_note": "TEXT NOT NULL DEFAULT ''",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    },
    "attempts": {
        "scope_label": "TEXT NOT NULL DEFAULT ''",
        "filters": "TEXT NOT NULL DEFAULT '{}'",
        "question_ids": "TEXT NOT NULL DEFAULT '[]'",
        "total": "INTEGER NOT NULL DEFAULT 0",
        "correct_count": "INTEGER NOT NULL DEFAULT 0",
        "started_at": "TEXT NOT NULL DEFAULT ''",
        "finished_at": "TEXT",
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    source_file TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(subject_id, name)
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    number INTEGER,
    type TEXT NOT NULL CHECK(type IN ('single', 'multiple', 'tf')),
    stem TEXT NOT NULL,
    options TEXT NOT NULL,
    answer TEXT NOT NULL,
    answer_source TEXT NOT NULL DEFAULT 'source',
    explanation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('ready', 'needs_review')),
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    question_id TEXT PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL,
    scope TEXT NOT NULL,
    scope_label TEXT NOT NULL DEFAULT '',
    filters TEXT NOT NULL DEFAULT '{}',
    question_ids TEXT NOT NULL,
    total INTEGER NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS attempt_answers (
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    chosen TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    answered_at TEXT NOT NULL,
    PRIMARY KEY (attempt_id, question_id)
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    # The data directory can be removed while the app is stopped; recreate it
    # before opening the database so the next import still persists normally.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _upgrade_legacy_columns(conn)
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_questions_paper ON questions(paper_id);
            CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(type);
            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            """
        )
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"数据库版本 {version} 高于当前程序支持的版本 {SCHEMA_VERSION}"
            )
        if version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()


def _upgrade_legacy_columns(conn: sqlite3.Connection) -> None:
    """Add columns from older local databases without replacing user data."""
    for table, columns in LEGACY_COLUMNS.items():
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def storage_status() -> dict:
    """Return a small read-only diagnostic for the running database."""
    with db() as conn:
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("subjects", "papers", "questions", "favorites", "attempts")
        }
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    return {
        "ok": integrity == "ok",
        "integrity": integrity,
        "schema_version": version,
        "db_path": str(Path(DB_PATH).resolve()),
        "counts": counts,
    }
