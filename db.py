import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

import bcrypt

DB_PATH = os.environ.get("EXAM_CREATE_DB", os.path.join(os.path.dirname(__file__), "data.db"))


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                num_questions INTEGER NOT NULL,
                source_text TEXT NOT NULL,
                questions_json TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                graded_json TEXT NOT NULL,
                total_score INTEGER NOT NULL,
                max_score INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        if not _column_exists(conn, "users", "theme"):
            conn.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'dark'")


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str, password: str) -> tuple[bool, str]:
    email = _normalize_email(email)
    if not _EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at, theme) VALUES (?, ?, ?, ?)",
                (email, pw_hash, datetime.utcnow().isoformat(), "dark"),
            )
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "An account with that email already exists."


def verify_user(email: str, password: str) -> Optional[dict]:
    email = _normalize_email(email)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, theme FROM users WHERE username = ?",
            (email,),
        ).fetchone()
    if not row:
        return None
    if not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return None
    return {"id": row["id"], "email": row["username"], "theme": row["theme"] or "dark"}


def update_user_theme(user_id: int, theme: str) -> None:
    if theme not in ("light", "dark"):
        return
    with get_conn() as conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user_id))


def save_exam(
    user_id: int,
    title: str,
    difficulty: str,
    source_text: str,
    questions: list[dict],
    answers: dict,
    graded: dict,
    total_score: int,
    max_score: int,
) -> int:
    answers_serializable = {str(k): v for k, v in answers.items()}
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO exams
                (user_id, title, difficulty, num_questions, source_text,
                 questions_json, answers_json, graded_json,
                 total_score, max_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                difficulty,
                len(questions),
                source_text,
                json.dumps(questions),
                json.dumps(answers_serializable),
                json.dumps(graded),
                int(total_score),
                int(max_score),
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def list_exams(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, difficulty, num_questions,
                   total_score, max_score, created_at
            FROM exams
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_exam(user_id: int, exam_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM exams WHERE user_id = ? AND id = ?",
            (user_id, exam_id),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["questions"] = json.loads(data.pop("questions_json"))
    answers_raw = json.loads(data.pop("answers_json"))
    data["answers"] = {int(k): v for k, v in answers_raw.items()}
    data["graded"] = json.loads(data.pop("graded_json"))
    return data


def delete_exam(user_id: int, exam_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM exams WHERE user_id = ? AND id = ?",
            (user_id, exam_id),
        )


def user_stats(user_id: int) -> dict:
    """Return progress stats for the user's home page."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT total_score, max_score, created_at
            FROM exams
            WHERE user_id = ?
            ORDER BY datetime(created_at) ASC
            """,
            (user_id,),
        ).fetchall()

    total_tests = len(rows)
    if total_tests == 0:
        return {
            "total_tests": 0,
            "average_score": None,
            "best_score": None,
            "tests_today": 0,
            "tests_this_week": 0,
            "daily_average": 0.0,
            "weekly_average": 0.0,
            "last_test_at": None,
        }

    now = datetime.utcnow()
    today = now.date()
    week_ago = now - timedelta(days=7)

    percentages = []
    tests_today = 0
    tests_this_week = 0
    parsed_dates = []
    for r in rows:
        try:
            dt = datetime.fromisoformat(r["created_at"])
        except ValueError:
            continue
        parsed_dates.append(dt)
        if r["max_score"]:
            percentages.append((r["total_score"] / r["max_score"]) * 100)
        if dt.date() == today:
            tests_today += 1
        if dt >= week_ago:
            tests_this_week += 1

    first_dt = parsed_dates[0] if parsed_dates else now
    days_active = max(1, (now - first_dt).days + 1)
    weeks_active = max(1.0, days_active / 7.0)

    return {
        "total_tests": total_tests,
        "average_score": round(sum(percentages) / len(percentages), 1) if percentages else None,
        "best_score": round(max(percentages), 1) if percentages else None,
        "tests_today": tests_today,
        "tests_this_week": tests_this_week,
        "daily_average": round(total_tests / days_active, 2),
        "weekly_average": round(total_tests / weeks_active, 2),
        "last_test_at": parsed_dates[-1].isoformat() if parsed_dates else None,
    }
