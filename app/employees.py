import sqlite3
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Employee:
    telegram_id: int
    bot_name: str


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _connection(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = _connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str | Path) -> None:
    with _connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                telegram_id INTEGER PRIMARY KEY,
                bot_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                hired_at TEXT NOT NULL,
                dismissed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def register_employee(
    database_path: str | Path,
    telegram_id: int,
    bot_name: str,
    actor_id: int = 0,
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connection(database_path) as connection:
        existing = connection.execute(
            "SELECT is_active FROM employees WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO employees (telegram_id, bot_name, hired_at)
                VALUES (?, ?, ?)
                """,
                (telegram_id, bot_name, now),
            )
            result = "created"
        else:
            result = "updated" if existing["is_active"] else "reactivated"
            connection.execute(
                """
                UPDATE employees
                SET bot_name = ?, is_active = 1, hired_at = ?, dismissed_at = NULL
                WHERE telegram_id = ?
                """,
                (bot_name, now, telegram_id),
            )
        connection.execute(
            """INSERT INTO workflow_audit (employee_id, actor_id, action, details, created_at)
               VALUES (?, ?, 'employee_registered', ?, ?)""",
            (
                telegram_id,
                actor_id,
                json.dumps({"bot_name": bot_name, "result": result}, ensure_ascii=False),
                now,
            ),
        )
        return result


def dismiss_employee(
    database_path: str | Path,
    telegram_id: int,
    actor_id: int = 0,
) -> bool:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connection(database_path) as connection:
        result = connection.execute(
            """
            UPDATE employees
            SET is_active = 0, dismissed_at = ?
            WHERE telegram_id = ? AND is_active = 1
            """,
            (now, telegram_id),
        )
        dismissed = result.rowcount == 1
        if dismissed:
            connection.execute(
                """INSERT INTO workflow_audit (employee_id, actor_id, action, details, created_at)
                   VALUES (?, ?, 'employee_dismissed', '{}', ?)""",
                (telegram_id, actor_id, now),
            )
        return dismissed


def get_active_employee(
    database_path: str | Path,
    telegram_id: int,
) -> Employee | None:
    with _connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT telegram_id, bot_name
            FROM employees
            WHERE telegram_id = ? AND is_active = 1
            """,
            (telegram_id,),
        ).fetchone()
    if row is None:
        return None
    return Employee(telegram_id=row["telegram_id"], bot_name=row["bot_name"])


def list_active_employees(database_path: str | Path) -> list[Employee]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT telegram_id, bot_name
            FROM employees
            WHERE is_active = 1
            ORDER BY bot_name COLLATE NOCASE, telegram_id
            """
        ).fetchall()
    return [
        Employee(telegram_id=row["telegram_id"], bot_name=row["bot_name"])
        for row in rows
    ]
