import sqlite3
import os
from datetime import date, timedelta

DB_PATH = os.environ.get("DB_PATH", "expenses.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_expense(user_id, amount, category, description, date):
    conn = get_connection()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, description, date)
    )
    conn.commit()
    conn.close()


def get_report(user_id, period):
    conn = get_connection()
    today = date.today()

    if period == "day":
        from_date = today.strftime("%Y-%m-%d")
    elif period == "week":
        from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    elif period == "month":
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? AND date >= ? ORDER BY date DESC",
        (user_id, from_date)
    ).fetchall()
    conn.close()
    return rows
