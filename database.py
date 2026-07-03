import sqlite3
from pathlib import Path

from config import get_data_dir


DB_PATH = get_data_dir() / "lead.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database() -> None:
    get_data_dir().mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                website TEXT UNIQUE,
                country TEXT,
                industry TEXT,
                status TEXT DEFAULT 'new',
                confidence REAL DEFAULT 0.0,
                reason TEXT,
                sent_at TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                email TEXT,
                email_type TEXT,
                source_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rejected_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT,
                domain TEXT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def insert_company(company_name, website, country, industry, status, confidence, reason) -> int:
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM companies WHERE website = ?", (website,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE companies
                SET company_name = COALESCE(NULLIF(?, ''), company_name),
                    country = COALESCE(NULLIF(?, ''), country),
                    industry = COALESCE(NULLIF(?, ''), industry),
                    status = ?,
                    confidence = ?,
                    reason = ?
                WHERE id = ?
                """,
                (company_name, country, industry, status, confidence, reason, existing["id"]),
            )
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO companies
                (company_name, website, country, industry, status, confidence, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (company_name or website or "Unknown", website, country, industry, status, confidence, reason),
        )
        return int(cur.lastrowid)


def insert_contact(company_id, email, email_type, source_url) -> int:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM contacts WHERE company_id = ? AND lower(email) = lower(?)",
            (company_id, email),
        ).fetchone()
        if existing:
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO contacts (company_id, email, email_type, source_url)
            VALUES (?, ?, ?, ?)
            """,
            (company_id, email, email_type, source_url),
        )
        return int(cur.lastrowid)


def insert_rejected_result(title, url, domain, reason) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO rejected_results (title, url, domain, reason)
            VALUES (?, ?, ?, ?)
            """,
            (title, url, domain, reason),
        )
        return int(cur.lastrowid)


def get_all_companies() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(conn.execute("SELECT * FROM companies ORDER BY id DESC").fetchall())


def get_contacts_by_company(company_id) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                "SELECT * FROM contacts WHERE company_id = ? ORDER BY id",
                (company_id,),
            ).fetchall()
        )


def get_companies_by_status(status) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                "SELECT * FROM companies WHERE status = ? ORDER BY id",
                (status,),
            ).fetchall()
        )


def update_company_status(company_id, status, last_error=None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE companies SET status = ?, last_error = ? WHERE id = ?",
            (status, last_error, company_id),
        )


def mark_company_sent(company_id) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE companies
            SET status = 'sent', sent_at = CURRENT_TIMESTAMP, last_error = NULL
            WHERE id = ?
            """,
            (company_id,),
        )


def mark_company_failed(company_id, error_message) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE companies SET status = 'send_failed', last_error = ? WHERE id = ?",
            (str(error_message), company_id),
        )
