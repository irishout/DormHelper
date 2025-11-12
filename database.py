"""SQLite database layer for DormHelper

Provides initialization and simple CRUD helpers for:
- news (announcements)
- requests (maintenance requests)
- handbook (tree-like reference)
- students and neighbors

The DB file is placed next to this module (dormhelper.db).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any

DB_FILENAME = "dormhelper.db"


def get_db_path() -> str:
    """Return absolute path to the database file next to this module."""
    base = os.path.dirname(__file__)
    return os.path.join(base, DB_FILENAME)


def get_conn() -> sqlite3.Connection:
    """Get a sqlite3 connection with row factory set."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        cur = conn.cursor()

        # News / announcements
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Maintenance requests / appeals
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_name TEXT,
                request_type TEXT NOT NULL,
                description TEXT,
                room TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )

        # Handbook items (simple parent-child tree)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS handbook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER REFERENCES handbook(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                content TEXT,
                sort_order INTEGER DEFAULT 0
            )
            """
        )

        # Students
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                room TEXT,
                floor TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # Neighbors (roommates/contact entries)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS neighbors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                contact TEXT
            )
            """
        )

        # Useful indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_students_room ON students(room)")

        # --- Migrations: ensure expected columns exist in existing DBs ---
        def ensure_column(table: str, column: str, definition: str) -> None:
            cur.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cur.fetchall()]
            if column not in cols:
                # SQLite supports ADD COLUMN with a column definition
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

        # If the app used an older schema, add common missing columns
        try:
            # handbook: parent_id and sort_order
            ensure_column("handbook", "parent_id", "parent_id INTEGER")
            ensure_column("handbook", "sort_order", "sort_order INTEGER DEFAULT 0")
            # requests: created_at and updated_at and status
            ensure_column("requests", "created_at", "created_at TEXT")
            ensure_column("requests", "updated_at", "updated_at TEXT")
            ensure_column("requests", "status", "status TEXT DEFAULT 'open'")
            # news and students created_at
            ensure_column("news", "created_at", "created_at TEXT")
            ensure_column("students", "created_at", "created_at TEXT")
        except Exception:
            # Migration errors should not prevent application from starting; log to stdout
            print("Warning: migration step failed (non-fatal)")

        conn.commit()

        # Backfill common renamed columns for requests from older schemas
        try:
            # add requester_name/request_type if missing
            def col_exists(table: str, col: str) -> bool:
                cur.execute(f"PRAGMA table_info({table})")
                return col in [r[1] for r in cur.fetchall()]

            if not col_exists('requests', 'requester_name'):
                cur.execute("ALTER TABLE requests ADD COLUMN requester_name TEXT")
            if not col_exists('requests', 'request_type'):
                cur.execute("ALTER TABLE requests ADD COLUMN request_type TEXT")

            # If old columns exist (type, student_name, created_date), copy them into new columns
            cur.execute("PRAGMA table_info(requests)")
            existing = [r[1] for r in cur.fetchall()]
            if 'type' in existing:
                cur.execute("UPDATE requests SET request_type = type WHERE request_type IS NULL OR request_type = ''")
            if 'student_name' in existing:
                cur.execute("UPDATE requests SET requester_name = student_name WHERE requester_name IS NULL OR requester_name = ''")
            if 'created_date' in existing and 'created_at' in existing:
                cur.execute("UPDATE requests SET created_at = created_date WHERE (created_at IS NULL OR created_at = '') AND created_date IS NOT NULL")
        except Exception:
            print("Warning: requests backfill failed (non-fatal)")

        conn.commit()

        # Seed sample news if table is empty
        try:
            cur.execute("SELECT COUNT(*) FROM news")
            cnt = cur.fetchone()[0]
            if cnt == 0:
                samples = [
                    (
                        "Добро пожаловать в DormHelper",
                        "Это тестовое объявление. Здесь вы увидите новости и важные сообщения от администрации.",
                    ),
                    (
                        "График уборки общежития",
                        "Уважаемые жильцы! Напоминаем о графике уборки: этажи 1-2 — понедельник, 3-4 — вторник.",
                    ),
                    (
                        "Плановое отключение воды",
                        "В среду с 09:00 до 12:00 будет проводиться плановое отключение воды на всех этажах.",
                    ),
                ]
                now = _now_iso()
                for t, c in samples:
                    cur.execute(
                        "INSERT INTO news (title, content, created_at) VALUES (?, ?, ?)", (t, c, now)
                    )
                conn.commit()
                print(f"Seeded {len(samples)} sample news items")
        except Exception:
            # non-fatal
            pass


### News helpers


def add_news(title: str, content: str) -> int:
    """Insert news item, return id."""
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO news (title, content, created_at) VALUES (?, ?, ?)",
            (title, content, now),
        )
        conn.commit()
        return cur.lastrowid


def get_news(limit: int = 50) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM news ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def get_news_by_id(item_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM news WHERE id = ?", (item_id,))
        row = cur.fetchone()
        return dict(row) if row else None


### Requests helpers


def add_request(
    requester_name: Optional[str], request_type: str, description: str, room: Optional[str]
) -> int:
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        # adapt to existing column names in legacy DBs

        cur.execute("PRAGMA table_info(requests)")
        info_rows = cur.fetchall()
        existing = [r[1] for r in info_rows]
        notnull_map = {r[1]: r[3] for r in info_rows}

        cols = []
        vals = []

        # requester/student name: prefer new column, but if old exists also fill it
        if 'requester_name' in existing:
            cols.append('requester_name'); vals.append(requester_name)
        if 'student_name' in existing and 'student_name' not in cols:
            cols.append('student_name'); vals.append(requester_name)

        # request type: fill both possible names if present
        if 'request_type' in existing:
            cols.append('request_type'); vals.append(request_type)
        if 'type' in existing and 'type' not in cols:
            cols.append('type'); vals.append(request_type)

        # description
        if 'description' in existing:
            cols.append('description'); vals.append(description)

        # room
        if 'room' in existing:
            cols.append('room'); vals.append(room)

        # status
        if 'status' in existing:
            cols.append('status'); vals.append('open')

        # created_at / created_date
        if 'created_at' in existing:
            cols.append('created_at'); vals.append(now)
        if 'created_date' in existing and 'created_date' not in cols:
            cols.append('created_date'); vals.append(now)

        if not cols:
            raise RuntimeError('No compatible columns found in requests table')

        placeholders = ','.join(['?'] * len(cols))
        sql = f"INSERT INTO requests ({', '.join(cols)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(vals))
        conn.commit()
        return cur.lastrowid


def get_requests(limit: int = 100) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM requests ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]


def clear_requests() -> int:
    """Delete all requests and return number of deleted rows."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM requests")
        before = cur.fetchone()[0]
        cur.execute("DELETE FROM requests")
        conn.commit()
        return before


def get_requests_by_room(room: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM requests WHERE room = ? ORDER BY created_at DESC", (room,))
        return [dict(r) for r in cur.fetchall()]


def update_request_status(request_id: int, status: str) -> bool:
    now = _now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE requests SET status = ?, updated_at = ? WHERE id = ?", (status, now, request_id)
        )
        conn.commit()
        return cur.rowcount > 0


### Handbook helpers


def add_handbook_item(title: str, content: str = "", parent_id: Optional[int] = None, sort_order: int = 0) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO handbook (parent_id, title, content, sort_order) VALUES (?, ?, ?, ?)",
            (parent_id, title, content, sort_order),
        )
        conn.commit()
        return cur.lastrowid
    
def delete_handbook_item(title_for_delete: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM handbook WHERE title = ?",
            (title_for_delete,),
        )
        conn.commit()
        return cur.rowcount  


def get_handbook_children(parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        if parent_id is None:
            cur.execute("SELECT * FROM handbook WHERE parent_id IS NULL ORDER BY sort_order, id")
        else:
            cur.execute("SELECT * FROM handbook WHERE parent_id = ? ORDER BY sort_order, id", (parent_id,))
        return [dict(r) for r in cur.fetchall()]


### Students & neighbors


def add_student(full_name: str, room: Optional[str], floor: Optional[str] = None) -> int:
    """Insert a new student and return its id."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO students (full_name, room, floor, created_at) VALUES (?, ?, ?, ?)",
            (full_name, room, floor, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid


def get_student(student_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM students WHERE id = ?", (student_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def find_students_by_room(room: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM students WHERE room = ? ORDER BY full_name", (room,))
        return [dict(r) for r in cur.fetchall()]


def add_neighbor(student_id: int, name: str, contact: Optional[str] = None) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO neighbors (student_id, name, contact) VALUES (?, ?, ?)", (student_id, name, contact)
        )
        conn.commit()
        return cur.lastrowid


def get_neighbors(student_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM neighbors WHERE student_id = ?", (student_id,))
        return [dict(r) for r in cur.fetchall()]
    
def get_student_by_name_room(full_name: str, room: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return a student row matching full_name and room, or None."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM students WHERE full_name = ? AND room = ? LIMIT 1", (full_name, room))
        row = cur.fetchone()
        return dict(row) if row else None


def update_student(student_id: int, full_name: str, room: Optional[str] = None, floor: Optional[str] = None) -> bool:
    """Update student fields (full_name, room, floor). Returns True if row updated."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE students SET full_name = ?, room = ?, floor = ? WHERE id = ?",
            (full_name, room, floor, student_id),
        )
        conn.commit()
        return cur.rowcount > 0


if __name__ == "__main__":
    # quick smoke-run when executed directly
    print("Initializing DB at:", get_db_path())
    init_db()
    print("Database initialized.")
    # show counts
    with get_conn() as c:
        cur = c.cursor()
        for name in ("news", "requests", "handbook", "students", "neighbors"):
            cur.execute(f"SELECT COUNT(*) as cnt FROM {name}")
            print(name, cur.fetchone()[0])
