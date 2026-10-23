import random
import sqlite3
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Employee:
    telegram_id: int
    bot_name: str
    pin: str = "1234"


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path("/tmp") / path.name
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
                dismissed_at TEXT,
                pin TEXT NOT NULL DEFAULT '1234'
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
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(employees)").fetchall()
        }
        if "pin" not in columns:
            connection.execute("ALTER TABLE employees ADD COLUMN pin TEXT NOT NULL DEFAULT '1234'")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
                code TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_used INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def register_employee(
    database_path: str | Path,
    telegram_id: int,
    bot_name: str,
    actor_id: int = 0,
    pin: str = "1234",
) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    clean_pin = (pin or "1234").strip() or "1234"
    with _connection(database_path) as connection:
        existing = connection.execute(
            "SELECT is_active FROM employees WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO employees (telegram_id, bot_name, hired_at, pin)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_id, bot_name, now, clean_pin),
            )
            result = "created"
        else:
            result = "updated" if existing["is_active"] else "reactivated"
            connection.execute(
                """
                UPDATE employees
                SET bot_name = ?, is_active = 1, hired_at = ?, dismissed_at = NULL, pin = ?
                WHERE telegram_id = ?
                """,
                (bot_name, now, clean_pin, telegram_id),
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


def update_employee_pin(
    database_path: str | Path,
    telegram_id: int,
    pin: str,
    actor_id: int = 0,
) -> bool:
    clean_pin = pin.strip()
    if not clean_pin:
        raise ValueError("PIN bo'sh bo'lishi mumkin emas")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connection(database_path) as connection:
        result = connection.execute(
            "UPDATE employees SET pin = ? WHERE telegram_id = ? AND is_active = 1",
            (clean_pin, telegram_id),
        )
        updated = result.rowcount == 1
        if updated:
            connection.execute(
                """INSERT INTO workflow_audit (employee_id, actor_id, action, details, created_at)
                   VALUES (?, ?, 'pin_updated', '{}', ?)""",
                (telegram_id, actor_id, now),
            )
        return updated


def get_active_employee(
    database_path: str | Path,
    telegram_id: int,
) -> Employee | None:
    with _connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT telegram_id, bot_name, COALESCE(pin, '1234') AS pin
            FROM employees
            WHERE telegram_id = ? AND is_active = 1
            """,
            (telegram_id,),
        ).fetchone()
    if row is None:
        return None
    return Employee(telegram_id=row["telegram_id"], bot_name=row["bot_name"], pin=row["pin"])


def list_active_employees(database_path: str | Path) -> list[Employee]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT telegram_id, bot_name, COALESCE(pin, '1234') AS pin
            FROM employees
            WHERE is_active = 1
            ORDER BY bot_name COLLATE NOCASE, telegram_id
            """
        ).fetchall()
    return [
        Employee(telegram_id=row["telegram_id"], bot_name=row["bot_name"], pin=row["pin"])
        for row in rows
    ]


def verify_employee_pin(
    database_path: str | Path,
    identifier: int | str,
    pin: str,
) -> Employee | None:
    clean_pin = str(pin).strip()
    with _connection(database_path) as connection:
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            row = connection.execute(
                """
                SELECT telegram_id, bot_name, COALESCE(pin, '1234') AS pin
                FROM employees
                WHERE telegram_id = ? AND is_active = 1
                """,
                (int(identifier),),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT telegram_id, bot_name, COALESCE(pin, '1234') AS pin
                FROM employees
                WHERE LOWER(bot_name) = LOWER(?) AND is_active = 1
                """,
                (str(identifier).strip(),),
            ).fetchone()
    if row is None:
        return None
    if str(row["pin"]).strip() != clean_pin:
        return None
    return Employee(telegram_id=row["telegram_id"], bot_name=row["bot_name"], pin=row["pin"])


def create_otp_code(
    database_path: str | Path,
    telegram_id: int,
    role: str,
    name: str,
    ttl_minutes: int = 5,
) -> str:
    now_dt = datetime.now(timezone.utc)
    created_at = now_dt.isoformat()
    expires_at = (now_dt + timedelta(minutes=ttl_minutes)).isoformat()

    with _connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
                code TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Eski ishlatilmagan kodlarni bekor qilish
        connection.execute(
            "UPDATE otp_codes SET is_used = 1 WHERE telegram_id = ? AND is_used = 0",
            (telegram_id,),
        )
        # 5 xonali noyob tasodifiy kod hosil qilish
        code = f"{random.randint(10000, 99999)}"
        for _ in range(10):
            existing = connection.execute(
                "SELECT 1 FROM otp_codes WHERE code = ? AND is_used = 0", (code,)
            ).fetchone()
            if not existing:
                break
            code = f"{random.randint(10000, 99999)}"

        connection.execute(
            """
            INSERT OR REPLACE INTO otp_codes
            (code, telegram_id, role, name, created_at, expires_at, is_used)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (code, telegram_id, role, name, created_at, expires_at),
        )
    return code


def verify_and_consume_otp(
    database_path: str | Path,
    code: str,
) -> dict[str, object] | None:
    clean_code = str(code).strip()
    if not clean_code:
        return None
    now_iso = datetime.now(timezone.utc).isoformat()
    with _connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS otp_codes (
                code TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        row = connection.execute(
            """
            SELECT code, telegram_id, role, name, expires_at, is_used
            FROM otp_codes
            WHERE code = ? AND is_used = 0
            """,
            (clean_code,),
        ).fetchone()
        if row is None:
            return None
        if str(row["expires_at"]) < now_iso:
            return None
        # Bir martalik kod - ishlatilgan deb belgilash
        connection.execute("UPDATE otp_codes SET is_used = 1 WHERE code = ?", (clean_code,))
        return {
            "telegram_id": int(row["telegram_id"]),
            "role": str(row["role"]),
            "name": str(row["name"]),
        }
