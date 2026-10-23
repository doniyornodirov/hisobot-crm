import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


_UZBEKISTAN = timezone(timedelta(hours=5))


def _card_total_with_fee(amount: int) -> int:
    return ((amount * 103 + 99_999) // 100_000) * 1_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _work_date() -> date:
    return datetime.now(_UZBEKISTAN).date()


@contextmanager
def _database(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(database_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path("/tmp") / path.name
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.create_function("card_total_with_fee", 1, _card_total_with_fee, deterministic=True)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_workflows(database_path: str | Path) -> None:
    with _database(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS card_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                card_number TEXT NOT NULL,
                cardholder TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                work_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                decision_reason TEXT,
                decided_by INTEGER,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                notification_chat_id INTEGER,
                notification_message_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS money_givings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                note TEXT NOT NULL DEFAULT '',
                work_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                decision_reason TEXT,
                decided_by INTEGER,
                created_at TEXT NOT NULL,
                decided_at TEXT
            );
            CREATE TABLE IF NOT EXISTS debt_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                amount_delta INTEGER NOT NULL CHECK (amount_delta != 0),
                description TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                work_date TEXT NOT NULL,
                paynet INTEGER NOT NULL CHECK (paynet >= 0),
                card_total INTEGER NOT NULL DEFAULT 0 CHECK (card_total >= 0),
                levy INTEGER NOT NULL CHECK (levy >= 0),
                simcard INTEGER NOT NULL CHECK (simcard >= 0),
                debt_payment INTEGER NOT NULL CHECK (debt_payment >= 0),
                giving_total INTEGER NOT NULL DEFAULT 0 CHECK (giving_total >= 0),
                terminal INTEGER NOT NULL CHECK (terminal >= 0),
                daily INTEGER NOT NULL CHECK (daily >= 0),
                discount INTEGER NOT NULL CHECK (discount >= 0),
                expense INTEGER NOT NULL CHECK (expense >= 0),
                comment TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                decision_reason TEXT,
                decided_by INTEGER,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                notification_chat_id INTEGER,
                notification_message_id INTEGER,
                UNIQUE(employee_id, work_date)
            );
            CREATE TABLE IF NOT EXISTS workflow_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_card_employee ON card_requests(employee_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_giving_employee ON money_givings(employee_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_report_employee ON reports(employee_id, work_date);
            CREATE INDEX IF NOT EXISTS idx_debt_employee ON debt_ledger(employee_id, created_at);
            """
        )
        report_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(reports)").fetchall()
        }
        if "card_total" not in report_columns:
            connection.execute(
                "ALTER TABLE reports ADD COLUMN card_total INTEGER NOT NULL DEFAULT 0"
            )
        if "giving_total" not in report_columns:
            connection.execute(
                "ALTER TABLE reports ADD COLUMN giving_total INTEGER NOT NULL DEFAULT 0"
            )
        card_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(card_requests)").fetchall()
        }
        if "notification_chat_id" not in card_columns:
            connection.execute(
                "ALTER TABLE card_requests ADD COLUMN notification_chat_id INTEGER"
            )
        if "notification_message_id" not in card_columns:
            connection.execute(
                "ALTER TABLE card_requests ADD COLUMN notification_message_id INTEGER"
            )
        report_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(reports)").fetchall()
        }
        if "notification_chat_id" not in report_columns:
            connection.execute(
                "ALTER TABLE reports ADD COLUMN notification_chat_id INTEGER"
            )
        if "notification_message_id" not in report_columns:
            connection.execute(
                "ALTER TABLE reports ADD COLUMN notification_message_id INTEGER"
            )
        connection.execute(
            """UPDATE reports
               SET card_total = COALESCE((
                   SELECT SUM(card_total_with_fee(cards.amount))
                   FROM card_requests AS cards
                   WHERE cards.employee_id = reports.employee_id
                     AND cards.work_date = reports.work_date
                     AND cards.status = 'approved'
               ), 0)"""
        )


def _audit(
    connection: sqlite3.Connection,
    employee_id: int,
    actor_id: int,
    action: str,
    details: dict[str, object],
) -> None:
    connection.execute(
        """INSERT INTO workflow_audit (employee_id, actor_id, action, details, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (employee_id, actor_id, action, json.dumps(details, ensure_ascii=False), _now()),
    )


def create_card_request(
    database_path: str | Path,
    employee_id: int,
    card_number: str,
    cardholder: str,
    amount: int,
) -> int:
    if len(card_number) != 16 or not card_number.isascii() or not card_number.isdigit():
        raise ValueError("Karta raqami 16 ta raqamdan iborat bo'lishi kerak")
    if amount < 10_000:
        raise ValueError("Karta so'rovi uchun eng kam summa 10 000 so'm")
    if not cardholder.strip():
        raise ValueError("Karta egasining ismi kiritilishi kerak")
    with _database(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO card_requests
               (employee_id, card_number, cardholder, amount, work_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (employee_id, card_number, cardholder.strip(), amount, _work_date().isoformat(), _now()),
        )
        request_id = int(cursor.lastrowid)
        _audit(connection, employee_id, employee_id, "card_request_created", {"id": request_id, "amount": amount})
        return request_id


def create_money_giving(
    database_path: str | Path,
    employee_id: int,
    amount: int,
    note: str = "",
) -> int:
    if amount <= 0:
        raise ValueError("Summa noldan katta bo'lishi kerak")
    with _database(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO money_givings
               (employee_id, amount, note, work_date, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (employee_id, amount, note.strip(), _work_date().isoformat(), _now()),
        )
        giving_id = int(cursor.lastrowid)
        _audit(connection, employee_id, employee_id, "money_giving_created", {"id": giving_id, "amount": amount})
        return giving_id


def add_debt(
    database_path: str | Path,
    employee_id: int,
    amount: int,
    description: str,
    actor_id: int,
) -> int:
    if amount <= 0:
        raise ValueError("Qarz summasi noldan katta bo'lishi kerak")
    if not description.strip():
        raise ValueError("Qarz sababi kiritilishi kerak")
    with _database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """INSERT INTO debt_ledger
               (employee_id, amount_delta, description, actor_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (employee_id, amount, description.strip(), actor_id, _now()),
        )
        _audit(connection, employee_id, actor_id, "debt_added", {"amount": amount, "description": description.strip()})
        return int(cursor.lastrowid)


def _current_debt(connection: sqlite3.Connection, employee_id: int) -> int:
    row = connection.execute(
        "SELECT COALESCE(SUM(amount_delta), 0) AS balance FROM debt_ledger WHERE employee_id = ?",
        (employee_id,),
    ).fetchone()
    return int(row["balance"])


def _review(
    database_path: str | Path,
    table: str,
    record_id: int,
    employee_id: int,
    approved: bool,
    reason: str,
    admin_id: int,
) -> None:
    if not approved and not reason.strip():
        raise ValueError("Rad etish sababi kiritilishi shart")
    with _database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            f"SELECT employee_id, amount, status FROM {table} WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise LookupError("So'rov topilmadi")
        if int(row["employee_id"]) != employee_id:
            raise LookupError("So'rov topilmadi")
        if row["status"] != "pending":
            raise ValueError("Bu so'rov bo'yicha qaror qabul qilingan")
        status = "approved" if approved else "rejected"
        connection.execute(
            f"""UPDATE {table} SET status = ?, decision_reason = ?, decided_by = ?, decided_at = ?
                WHERE id = ? AND status = 'pending'""",
            (status, reason.strip() or None, admin_id, _now(), record_id),
        )
        _audit(connection, employee_id, admin_id, f"{table}_{status}", {"id": record_id, "reason": reason.strip()})


def review_card_request(
    database_path: str | Path, record_id: int, employee_id: int, approved: bool, reason: str, admin_id: int
) -> None:
    _review(database_path, "card_requests", record_id, employee_id, approved, reason, admin_id)


def card_request(database_path: str | Path, record_id: int) -> dict[str, object] | None:
    with _database(database_path) as connection:
        row = connection.execute(
            """SELECT c.*, e.bot_name,
                      (SELECT COUNT(*) FROM card_requests same_day
                       WHERE same_day.card_number = c.card_number
                         AND same_day.work_date = c.work_date) AS same_day_count
               FROM card_requests c
               LEFT JOIN employees e ON e.telegram_id = c.employee_id
               WHERE c.id = ?""",
            (record_id,),
        ).fetchone()
    return None if row is None else dict(row)


def save_card_notification(
    database_path: str | Path,
    record_id: int,
    chat_id: int,
    message_id: int,
) -> None:
    with _database(database_path) as connection:
        result = connection.execute(
            """UPDATE card_requests SET notification_chat_id = ?, notification_message_id = ?
               WHERE id = ?""",
            (chat_id, message_id, record_id),
        )
        if result.rowcount != 1:
            raise LookupError("Karta so'rovi topilmadi")


def set_card_request_decision(
    database_path: str | Path,
    record_id: int,
    approved: bool,
    actor_id: int,
    reason: str = "",
) -> str:
    result_status = "approved" if approved else "rejected"
    decision_reason = reason.strip() or (None if approved else "Guruh administratori tomonidan rad etildi")
    with _database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT employee_id, work_date, status FROM card_requests WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Karta so'rovi topilmadi")
        previous_status = str(row["status"])
        if previous_status == result_status:
            return previous_status
        connection.execute(
            """UPDATE card_requests
               SET status = ?, decision_reason = ?, decided_by = ?, decided_at = ?
               WHERE id = ?""",
            (result_status, decision_reason, actor_id, _now(), record_id),
        )
        employee_id = int(row["employee_id"])
        work_date = str(row["work_date"])
        current_card_total = connection.execute(
            """SELECT COALESCE(SUM(card_total_with_fee(amount)), 0) AS total
               FROM card_requests
               WHERE employee_id = ? AND work_date = ? AND status = 'approved'""",
            (employee_id, work_date),
        ).fetchone()["total"]
        connection.execute(
            """UPDATE reports SET card_total = ?
               WHERE employee_id = ? AND work_date = ?""",
            (int(current_card_total), employee_id, work_date),
        )
        _audit(
            connection,
            employee_id,
            actor_id,
            f"card_request_{result_status}",
            {
                "id": record_id,
                "previous_status": previous_status,
                "reason": decision_reason or "",
            },
        )
        return result_status


def review_money_giving(
    database_path: str | Path, record_id: int, employee_id: int, approved: bool, reason: str, admin_id: int
) -> str:
    with _database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT employee_id, work_date, status FROM money_givings WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None or int(row["employee_id"]) != employee_id:
            raise LookupError("So'rov topilmadi")
        previous_status = str(row["status"])
        status = "approved" if approved else "rejected"
        if previous_status == status:
            return status
        connection.execute(
            """UPDATE money_givings SET status = ?, decision_reason = ?, decided_by = ?, decided_at = ?
               WHERE id = ?""",
            (status, reason.strip() or None, admin_id, _now(), record_id),
        )
        work_date = str(row["work_date"])
        giving_total = connection.execute(
            """SELECT COALESCE(SUM(amount), 0) AS total FROM money_givings
               WHERE employee_id = ? AND work_date = ? AND status = 'approved'""",
            (employee_id, work_date),
        ).fetchone()["total"]
        connection.execute(
            """UPDATE reports SET giving_total = ?
               WHERE employee_id = ? AND work_date = ?""",
            (int(giving_total), employee_id, work_date),
        )
        _audit(
            connection,
            employee_id,
            admin_id,
            f"money_givings_{status}",
            {
                "id": record_id,
                "previous_status": previous_status,
                "reason": reason.strip(),
            },
        )
        return status


def create_report(database_path: str | Path, employee_id: int, values: dict[str, object]) -> int:
    work_date = str(values.get("work_date", ""))
    try:
        parsed_date = date.fromisoformat(work_date)
    except ValueError as error:
        raise ValueError("Hisobot sanasi yaroqsiz") from error
    if parsed_date > _work_date():
        raise ValueError("Kelajak sanasiga hisobot yuborib bo'lmaydi")
    amount_fields = ("paynet", "levy", "simcard", "debt_payment", "terminal", "daily", "discount", "expense")
    normalized: dict[str, int] = {}
    for field in amount_fields:
        value = values.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field} qiymati manfiy bo'lmagan butun son bo'lishi kerak")
        normalized[field] = value
    comment = str(values.get("comment", "")).strip()[:1000]
    with _database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT id, status, debt_payment FROM reports WHERE employee_id = ? AND work_date = ?",
            (employee_id, work_date),
        ).fetchone()
        if existing is not None and existing["status"] == "approved":
            previous_payment = int(existing["debt_payment"])
            if previous_payment:
                connection.execute(
                    """INSERT INTO debt_ledger
                       (employee_id, amount_delta, description, actor_id, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        employee_id,
                        previous_payment,
                        f"Hisobot #{existing['id']} almashtirildi; oldingi qarz to'lovi bekor qilindi",
                        employee_id,
                        _now(),
                    ),
                )
            _audit(
                connection,
                employee_id,
                employee_id,
                "approved_report_replaced",
                {
                    "id": int(existing["id"]),
                    "work_date": work_date,
                    "previous_debt_payment": previous_payment,
                },
            )
        debt = _current_debt(connection, employee_id)
        if normalized["debt_payment"] > debt:
            raise ValueError("Qarz uchun summa joriy qarzdorlikdan oshmasligi kerak")
        card_total = connection.execute(
            """SELECT COALESCE(SUM(card_total_with_fee(amount)), 0) AS total
               FROM card_requests WHERE employee_id = ? AND work_date = ? AND status = 'approved'""",
            (employee_id, work_date),
        ).fetchone()["total"]
        giving_total = connection.execute(
            """SELECT COALESCE(SUM(amount), 0) AS total FROM money_givings
               WHERE employee_id = ? AND work_date = ? AND status = 'approved'""",
            (employee_id, work_date),
        ).fetchone()["total"]
        values_to_save = (
            normalized["paynet"], int(card_total), normalized["levy"], normalized["simcard"],
            normalized["debt_payment"], int(giving_total), normalized["terminal"], normalized["daily"],
            normalized["discount"], normalized["expense"], comment,
        )
        if existing is not None:
            report_id = int(existing["id"])
            connection.execute(
                """UPDATE reports
                   SET paynet = ?, card_total = ?, levy = ?, simcard = ?, debt_payment = ?,
                       giving_total = ?, terminal = ?, daily = ?, discount = ?, expense = ?,
                       comment = ?, status = 'pending', decision_reason = NULL, decided_by = NULL,
                       decided_at = NULL, created_at = ?,
                       notification_chat_id = NULL, notification_message_id = NULL
                   WHERE id = ?""",
                (*values_to_save, _now(), report_id),
            )
            action = "report_resubmitted"
        else:
            cursor = connection.execute(
                """INSERT INTO reports
                   (employee_id, work_date, paynet, card_total, levy, simcard, debt_payment,
                    giving_total, terminal, daily, discount, expense, comment, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (employee_id, work_date, *values_to_save, _now()),
            )
            report_id = int(cursor.lastrowid)
            action = "report_created"
        _audit(connection, employee_id, employee_id, action, {"id": report_id, "work_date": work_date})
        return report_id


def daily_report(
    database_path: str | Path,
    employee_id: int,
    work_date: str,
) -> dict[str, object] | None:
    with _database(database_path) as connection:
        row = connection.execute(
            """SELECT r.*, e.bot_name
               FROM reports r
               LEFT JOIN employees e ON e.telegram_id = r.employee_id
               WHERE r.employee_id = ? AND r.work_date = ?""",
            (employee_id, work_date),
        ).fetchone()
    return None if row is None else dict(row)


def save_report_notification(
    database_path: str | Path,
    report_id: int,
    chat_id: int,
    message_id: int,
) -> None:
    with _database(database_path) as connection:
        result = connection.execute(
            """UPDATE reports SET notification_chat_id = ?, notification_message_id = ?
               WHERE id = ?""",
            (chat_id, message_id, report_id),
        )
        if result.rowcount != 1:
            raise LookupError("Hisobot topilmadi")


def review_report(
    database_path: str | Path,
    report_id: int,
    approved: bool,
    reason: str,
    admin_id: int,
) -> None:
    if not approved and not reason.strip():
        raise ValueError("Rad etish sababi kiritilishi shart")
    with _database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        report = connection.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if report is None:
            raise LookupError("Hisobot topilmadi")
        previous_status = str(report["status"])
        result_status = "approved" if approved else "rejected"
        if previous_status == result_status:
            return
        employee_id = int(report["employee_id"])
        payment = int(report["debt_payment"])
        if approved and payment > _current_debt(connection, employee_id):
            raise ValueError("Hisobotdagi qarz to'lovi joriy qarzdorlikdan oshib ketdi")
        connection.execute(
            """UPDATE reports SET status = ?, decision_reason = ?, decided_by = ?, decided_at = ?
               WHERE id = ?""",
            (result_status, reason.strip() or None, admin_id, _now(), report_id),
        )
        if payment and (approved or previous_status == "approved"):
            debt_delta = -payment if approved else payment
            debt_description = (
                f"Hisobot #{report_id} qarz to'lovi"
                if debt_delta < 0
                else f"Hisobot #{report_id} qarz qaytarildi"
            )
            connection.execute(
                """INSERT INTO debt_ledger
                   (employee_id, amount_delta, description, actor_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    employee_id,
                    debt_delta,
                    debt_description,
                    admin_id,
                    _now(),
                ),
            )
        _audit(
            connection,
            employee_id,
            admin_id,
            f"report_{result_status}",
            {
                "id": report_id,
                "previous_status": previous_status,
                "reason": reason.strip(),
            },
        )


def _records(connection: sqlite3.Connection, query: str, employee_id: int | None = None) -> list[dict[str, object]]:
    rows = connection.execute(query, () if employee_id is None else (employee_id,)).fetchall()
    return [dict(row) for row in rows]


def employee_dashboard(
    database_path: str | Path,
    employee_id: int,
    work_date: str | None = None,
) -> dict[str, object]:
    today = work_date or _work_date().isoformat()
    try:
        selected_date = date.fromisoformat(today)
    except ValueError as error:
        raise ValueError("Hisobot sanasi yaroqsiz") from error
    if selected_date > _work_date():
        raise ValueError("Kelajak sanasini tanlab bo'lmaydi")
    with _database(database_path) as connection:
        debt = _current_debt(connection, employee_id)
        cards = _records(
            connection,
            """SELECT c.id, c.employee_id, COALESCE(e.bot_name, '') AS bot_name, c.card_number, c.cardholder, c.amount,
                      c.work_date, c.status, c.decision_reason, c.created_at, c.decided_at,
                      CASE WHEN c.status = 'approved' THEN card_total_with_fee(c.amount) ELSE NULL END AS total_with_fee
               FROM card_requests c
               LEFT JOIN employees e ON e.telegram_id = c.employee_id
               WHERE c.employee_id = ? ORDER BY c.id DESC""",
            employee_id,
        )
        givings = _records(
            connection,
            """SELECT g.id, g.employee_id, COALESCE(e.bot_name, '') AS bot_name, g.amount, g.note,
                      g.work_date, g.status, g.decision_reason, g.created_at, g.decided_at
               FROM money_givings g
               LEFT JOIN employees e ON e.telegram_id = g.employee_id
               WHERE g.employee_id = ? ORDER BY g.id DESC""",
            employee_id,
        )
        reports = _records(
            connection,
            """SELECT r.*, COALESCE(e.bot_name, '') AS bot_name
               FROM reports r
               LEFT JOIN employees e ON e.telegram_id = r.employee_id
               WHERE r.employee_id = ? ORDER BY r.work_date DESC, r.id DESC""",
            employee_id,
        )
        debts = _records(
            connection,
            """SELECT amount_delta, description, actor_id, created_at
               FROM debt_ledger WHERE employee_id = ? ORDER BY id DESC""",
            employee_id,
        )
        card_total = connection.execute(
            """SELECT COALESCE(SUM(card_total_with_fee(amount)), 0) AS total
               FROM card_requests WHERE employee_id = ? AND work_date = ? AND status = 'approved'""",
            (employee_id, today),
        ).fetchone()["total"]
        giving_total = connection.execute(
            """SELECT COALESCE(SUM(amount), 0) AS total FROM money_givings
               WHERE employee_id = ? AND work_date = ? AND status = 'approved'""",
            (employee_id, today),
        ).fetchone()["total"]
    ratings = rating_boards(database_path)
    monthly_rating = next(
        (row for row in ratings["monthly"] if row["employee_id"] == employee_id),
        None,
    )
    overall_rating = next(
        (row for row in ratings["overall"] if row["employee_id"] == employee_id),
        None,
    )
    return {
        "work_date": today,
        "debt_balance": debt,
        "card_total_with_fee": int(card_total),
        "approved_giving_total": int(giving_total),
        "rating": {
            "monthly": monthly_rating,
            "overall": overall_rating,
            "monthly_top": [
                row for row in ratings["monthly"] if int(row["rank"]) <= 3
            ],
            "overall_top": [
                row for row in ratings["overall"] if int(row["rank"]) <= 3
            ],
        },
        "cards": cards,
        "givings": givings,
        "reports": reports,
        "debts": debts,
    }


def rating_boards(database_path: str | Path) -> dict[str, list[dict[str, object]]]:
    today = _work_date()
    month_start = today.replace(day=1).isoformat()
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    month_end = next_month.isoformat()

    def rows_for_period(
        connection: sqlite3.Connection,
        date_filter: str,
        date_parameters: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        rows = connection.execute(
            f"""SELECT e.telegram_id AS employee_id, e.bot_name,
                       COALESCE(cards.total, 0) AS card_total_with_fee,
                   COALESCE(givings.total, 0) AS approved_giving_total,
                   COALESCE(reports.total, 0) AS report_submission_total,
                   COALESCE(debts.balance, 0) AS debt_balance
            FROM employees e
            LEFT JOIN (
                SELECT employee_id, SUM(card_total_with_fee(amount)) AS total
                    FROM card_requests
                    WHERE status = 'approved' {date_filter}
                    GROUP BY employee_id
                ) cards ON cards.employee_id = e.telegram_id
                LEFT JOIN (
                    SELECT employee_id, SUM(amount) AS total
                    FROM money_givings
                    WHERE status = 'approved' {date_filter}
                    GROUP BY employee_id
                ) givings ON givings.employee_id = e.telegram_id
                LEFT JOIN (
                    SELECT employee_id,
                           SUM(paynet + card_total + levy + daily - terminal
                               - giving_total - discount - expense + debt_payment) AS total
                    FROM reports
                    WHERE status = 'approved' {date_filter}
                    GROUP BY employee_id
                ) reports ON reports.employee_id = e.telegram_id
                LEFT JOIN (
                    SELECT employee_id, SUM(amount_delta) AS balance
                    FROM debt_ledger
                    GROUP BY employee_id
                ) debts ON debts.employee_id = e.telegram_id
                WHERE e.is_active = 1""",
            date_parameters * 3,
        ).fetchall()
        return [dict(row) for row in rows]

    with _database(database_path) as connection:
        monthly = rows_for_period(
            connection,
            "AND work_date >= ? AND work_date < ?",
            (month_start, month_end),
        )
        overall = rows_for_period(connection, "")

    def rank(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        for row in rows:
            positive_score_amount = (
                int(row["card_total_with_fee"])
                + int(row["approved_giving_total"])
                + int(row["report_submission_total"])
            )
            difference = positive_score_amount - int(row["debt_balance"])
            score_hundredths = (abs(difference) + 500) // 1_000
            row["_score_hundredths"] = (
                -score_hundredths if difference < 0 else score_hundredths
            )
        rows.sort(
            key=lambda row: (
                -int(row["_score_hundredths"]),
                str(row["bot_name"]).casefold(),
                int(row["employee_id"]),
            )
        )
        previous_score: int | None = None
        previous_rank = 0
        for position, row in enumerate(rows, start=1):
            score_hundredths = int(row["_score_hundredths"])
            if score_hundredths != previous_score:
                previous_rank = position
                previous_score = score_hundredths
            row["rank"] = previous_rank
            row["score"] = score_hundredths / 100
            del row["_score_hundredths"]
        return rows

    return {"monthly": rank(monthly), "overall": rank(overall)}


def admin_dashboard(database_path: str | Path) -> dict[str, object]:
    with _database(database_path) as connection:
        cards = _records(
            connection,
            """SELECT * FROM card_requests ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC""",
        )
        givings = _records(
            connection,
            """SELECT * FROM money_givings ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC""",
        )
        reports = _records(
            connection,
            """SELECT * FROM reports ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, work_date DESC, id DESC""",
        )
        debt_rows = _records(
            connection,
            """SELECT employee_id, COALESCE(SUM(amount_delta), 0) AS balance
               FROM debt_ledger GROUP BY employee_id ORDER BY employee_id""",
        )
        debts = _records(
            connection,
            """SELECT * FROM debt_ledger ORDER BY id DESC""",
        )
        audit = _records(
            connection,
            """SELECT * FROM workflow_audit ORDER BY id DESC""",
        )
    return {
        "cards": cards,
        "givings": givings,
        "reports": reports,
        "debt_balances": debt_rows,
        "debts": debts,
        "audit": audit,
        "ratings": {
            period: [row for row in rows if int(row["rank"]) <= 3]
            for period, rows in rating_boards(database_path).items()
        },
    }
