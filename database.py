import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "interview_prep.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            target_role TEXT,
            resume_text TEXT,
            skills TEXT,
            experience_summary TEXT,
            projects_summary TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            session_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'in_progress',
            overall_score REAL,
            overall_feedback TEXT,
            created_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (candidate_id) REFERENCES candidates(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            order_index INTEGER NOT NULL,
            category TEXT,
            question_text TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL UNIQUE,
            answer_text TEXT,
            score REAL,
            strengths TEXT,
            improvements TEXT,
            ideal_points TEXT,
            created_at TEXT,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        )
    """)

    conn.commit()
    conn.close()


def create_candidate(name, target_role, resume_text, skills, experience_summary, projects_summary):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO candidates (name, target_role, resume_text, skills, experience_summary, projects_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, target_role, resume_text, json.dumps(skills), experience_summary, projects_summary,
          datetime.utcnow().isoformat()))
    conn.commit()
    candidate_id = cur.lastrowid
    conn.close()
    return candidate_id


def get_candidate(candidate_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    conn.close()
    return row


def get_latest_candidate():
    conn = get_connection()
    row = conn.execute("SELECT * FROM candidates ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row


def create_session(candidate_id, session_type):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sessions (candidate_id, session_type, status, created_at)
        VALUES (?, ?, 'in_progress', ?)
    """, (candidate_id, session_type, datetime.utcnow().isoformat()))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return session_id


def add_questions(session_id, questions):
    """questions: list of dicts {category, question_text}"""
    conn = get_connection()
    cur = conn.cursor()
    for idx, q in enumerate(questions):
        cur.execute("""
            INSERT INTO questions (session_id, order_index, category, question_text)
            VALUES (?, ?, ?, ?)
        """, (session_id, idx, q.get("category", "general"), q["question_text"]))
    conn.commit()
    conn.close()


def get_session(session_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row


def get_questions_for_session(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM questions WHERE session_id = ? ORDER BY order_index ASC", (session_id,)
    ).fetchall()
    conn.close()
    return rows


def get_question(question_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    conn.close()
    return row


def save_answer(question_id, answer_text, score, strengths, improvements, ideal_points):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO answers (question_id, answer_text, score, strengths, improvements, ideal_points, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(question_id) DO UPDATE SET
            answer_text=excluded.answer_text,
            score=excluded.score,
            strengths=excluded.strengths,
            improvements=excluded.improvements,
            ideal_points=excluded.ideal_points,
            created_at=excluded.created_at
    """, (question_id, answer_text, score, json.dumps(strengths), json.dumps(improvements),
          json.dumps(ideal_points), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_answers_for_session(session_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT q.id as question_id, q.question_text, q.category, q.order_index,
               a.answer_text, a.score, a.strengths, a.improvements, a.ideal_points
        FROM questions q
        LEFT JOIN answers a ON a.question_id = q.id
        WHERE q.session_id = ?
        ORDER BY q.order_index ASC
    """, (session_id,)).fetchall()
    conn.close()
    return rows


def complete_session(session_id, overall_score, overall_feedback):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sessions SET status='completed', overall_score=?, overall_feedback=?, completed_at=?
        WHERE id=?
    """, (overall_score, overall_feedback, datetime.utcnow().isoformat(), session_id))
    conn.commit()
    conn.close()


def get_all_sessions(candidate_id=None):
    conn = get_connection()
    if candidate_id:
        rows = conn.execute("""
            SELECT s.*, c.name as candidate_name FROM sessions s
            JOIN candidates c ON c.id = s.candidate_id
            WHERE s.candidate_id = ?
            ORDER BY s.created_at DESC
        """, (candidate_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT s.*, c.name as candidate_name FROM sessions s
            JOIN candidates c ON c.id = s.candidate_id
            ORDER BY s.created_at DESC
        """).fetchall()
    conn.close()
    return rows


def get_completed_sessions_with_scores(candidate_id=None):
    conn = get_connection()
    if candidate_id:
        rows = conn.execute("""
            SELECT id, session_type, overall_score, completed_at FROM sessions
            WHERE candidate_id = ? AND status='completed'
            ORDER BY completed_at ASC
        """, (candidate_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, session_type, overall_score, completed_at FROM sessions
            WHERE status='completed'
            ORDER BY completed_at ASC
        """).fetchall()
    conn.close()
    return rows
