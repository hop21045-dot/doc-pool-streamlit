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


@dataclass(frozen=True)
class SavedItem:
    message_id: str
    channel: str
    saved_at: str
    posted_at: str
    title: str
    text: str
    telegram_link: str
    file_name: str
    pdf_hash: str
    user_sector: str
    company_names: str
    user_tags: str
    user_note: str


@dataclass(frozen=True)
class DailyClipping:
    clip_date: str
    sector: str
    title: str
    summary_md: str
    source_count: int
    created_at: str


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_items (
                message_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                posted_at TEXT,
                title TEXT,
                text TEXT,
                telegram_link TEXT,
                file_name TEXT,
                pdf_hash TEXT,
                user_sector TEXT,
                company_names TEXT,
                user_tags TEXT,
                user_note TEXT,
                PRIMARY KEY(message_id, channel)
            )
            """
        )
        saved_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(saved_items)").fetchall()
        }
        for column_name in ["user_sector", "company_names", "user_tags", "user_note"]:
            if column_name not in saved_columns:
                conn.execute(f"ALTER TABLE saved_items ADD COLUMN {column_name} TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_clippings (
                clip_date TEXT NOT NULL,
                sector TEXT NOT NULL,
                title TEXT NOT NULL,
                summary_md TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(clip_date, sector)
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


def save_saved_item(
    message_id: str,
    channel: str,
    posted_at: str,
    title: str,
    text: str,
    telegram_link: str,
    file_name: str = "",
    pdf_hash: str = "",
    path: Path = DB_PATH,
) -> None:
    ensure_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO saved_items
            (message_id, channel, saved_at, posted_at, title, text, telegram_link, file_name, pdf_hash,
             user_sector, company_names, user_tags, user_note)
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE((SELECT user_sector FROM saved_items WHERE message_id = ? AND channel = ?), ''),
                COALESCE((SELECT company_names FROM saved_items WHERE message_id = ? AND channel = ?), ''),
                COALESCE((SELECT user_tags FROM saved_items WHERE message_id = ? AND channel = ?), ''),
                COALESCE((SELECT user_note FROM saved_items WHERE message_id = ? AND channel = ?), '')
            )
            """,
            (
                message_id, channel, now, posted_at, title, text, telegram_link, file_name, pdf_hash,
                message_id, channel,
                message_id, channel,
                message_id, channel,
                message_id, channel,
            ),
        )


def list_saved_items(path: Path = DB_PATH) -> list[SavedItem]:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            SELECT message_id, channel, saved_at, posted_at, title, text,
                   telegram_link, file_name, COALESCE(pdf_hash, ''),
                   COALESCE(user_sector, ''), COALESCE(company_names, ''),
                   COALESCE(user_tags, ''), COALESCE(user_note, '')
            FROM saved_items
            ORDER BY COALESCE(posted_at, saved_at) DESC
            """
        ).fetchall()
    return [SavedItem(*row) for row in rows]


def update_saved_item_metadata(
    message_id: str,
    channel: str,
    user_sector: str,
    company_names: str,
    user_tags: str,
    user_note: str,
    path: Path = DB_PATH,
) -> None:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE saved_items
            SET user_sector = ?, company_names = ?, user_tags = ?, user_note = ?
            WHERE message_id = ? AND channel = ?
            """,
            (user_sector, company_names, user_tags, user_note, message_id, channel),
        )


def save_daily_clipping(
    clip_date: str,
    sector: str,
    title: str,
    summary_md: str,
    source_count: int,
    path: Path = DB_PATH,
) -> None:
    ensure_db(path)
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_clippings
            (clip_date, sector, title, summary_md, source_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (clip_date, sector, title, summary_md, source_count, now),
        )


def list_daily_clippings(sector: str | None = None, path: Path = DB_PATH) -> list[DailyClipping]:
    ensure_db(path)
    query = """
        SELECT clip_date, sector, title, summary_md, source_count, created_at
        FROM daily_clippings
    """
    params: tuple[Any, ...] = ()
    if sector:
        query += " WHERE sector = ?"
        params = (sector,)
    query += " ORDER BY clip_date DESC, sector"
    with sqlite3.connect(path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [DailyClipping(*row) for row in rows]
