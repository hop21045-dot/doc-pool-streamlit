from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path("data/reports.sqlite3")


@dataclass(frozen=True)
class CachedClassification:
    pdf_hash: str
    source_message_id: str
    file_name: str
    model: str
    result: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class StoredReport:
    pdf_hash: str
    first_message_id: str
    first_seen_at: str
    file_name: str
    file_size: int
    telegram_link: str
    extracted_text: str


def ensure_db(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_reports (
                pdf_hash TEXT PRIMARY KEY,
                first_message_id TEXT,
                first_seen_at TEXT NOT NULL,
                file_name TEXT,
                file_size INTEGER,
                telegram_link TEXT,
                extracted_text TEXT
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(pdf_reports)").fetchall()
        }
        if "extracted_text" not in columns:
            conn.execute("ALTER TABLE pdf_reports ADD COLUMN extracted_text TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_classifications (
                pdf_hash TEXT PRIMARY KEY,
                source_message_id TEXT,
                file_name TEXT,
                model TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(pdf_hash) REFERENCES pdf_reports(pdf_hash)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS duplicate_messages (
                message_id TEXT PRIMARY KEY,
                pdf_hash TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                telegram_link TEXT,
                FOREIGN KEY(pdf_hash) REFERENCES pdf_reports(pdf_hash)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS detailed_analyses (
                pdf_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                analysis_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(pdf_hash, model),
                FOREIGN KEY(pdf_hash) REFERENCES pdf_reports(pdf_hash)
            )
            """
        )


def hash_pdf_bytes(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def register_pdf(
    pdf_hash: str,
    message_id: str,
    file_name: str,
    file_size: int,
    telegram_link: str,
    path: Path = DB_PATH,
) -> bool:
    """Register a PDF. Returns True only when this is the first time seeing it."""
    ensure_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM pdf_reports WHERE pdf_hash = ?",
            (pdf_hash,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                INSERT OR REPLACE INTO duplicate_messages
                (message_id, pdf_hash, seen_at, telegram_link)
                VALUES (?, ?, ?, ?)
                """,
                (message_id, pdf_hash, now, telegram_link),
            )
            return False

        conn.execute(
            """
            INSERT INTO pdf_reports
            (pdf_hash, first_message_id, first_seen_at, file_name, file_size, telegram_link)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pdf_hash, message_id, now, file_name, file_size, telegram_link),
        )
        return True


def get_cached_classification(pdf_hash: str, path: Path = DB_PATH) -> CachedClassification | None:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT pdf_hash, source_message_id, file_name, model, result_json, created_at
            FROM report_classifications
            WHERE pdf_hash = ?
            """,
            (pdf_hash,),
        ).fetchone()

    if not row:
        return None

    return CachedClassification(
        pdf_hash=row[0],
        source_message_id=row[1],
        file_name=row[2],
        model=row[3],
        result=json.loads(row[4]),
        created_at=row[5],
    )


def save_classification(
    pdf_hash: str,
    source_message_id: str,
    file_name: str,
    model: str,
    result: dict[str, Any],
    path: Path = DB_PATH,
) -> None:
    ensure_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO report_classifications
            (pdf_hash, source_message_id, file_name, model, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                pdf_hash,
                source_message_id,
                file_name,
                model,
                json.dumps(result, ensure_ascii=False),
                now,
            ),
        )


def save_extracted_text(pdf_hash: str, extracted_text: str, path: Path = DB_PATH) -> None:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE pdf_reports SET extracted_text = ? WHERE pdf_hash = ?",
            (extracted_text, pdf_hash),
        )


def get_stored_report(pdf_hash: str, path: Path = DB_PATH) -> StoredReport | None:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT pdf_hash, first_message_id, first_seen_at, file_name, file_size,
                   telegram_link, COALESCE(extracted_text, '')
            FROM pdf_reports
            WHERE pdf_hash = ?
            """,
            (pdf_hash,),
        ).fetchone()

    if not row:
        return None

    return StoredReport(
        pdf_hash=row[0],
        first_message_id=row[1],
        first_seen_at=row[2],
        file_name=row[3],
        file_size=row[4] or 0,
        telegram_link=row[5],
        extracted_text=row[6],
    )


def get_detailed_analysis(pdf_hash: str, model: str, path: Path = DB_PATH) -> str | None:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT analysis_text
            FROM detailed_analyses
            WHERE pdf_hash = ? AND model = ?
            """,
            (pdf_hash, model),
        ).fetchone()
    return row[0] if row else None


def save_detailed_analysis(
    pdf_hash: str,
    model: str,
    analysis_text: str,
    path: Path = DB_PATH,
) -> None:
    ensure_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO detailed_analyses
            (pdf_hash, model, analysis_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (pdf_hash, model, analysis_text, now),
        )
