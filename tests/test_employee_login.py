import hashlib
import hmac
import json
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlencode

from fastapi import HTTPException, Response
from pydantic import ValidationError
from starlette.requests import Request

from app.employees import Employee, dismiss_employee, initialize_database, register_employee
from app.main import (
    CardRequestCreate,
    DailyReportCreate,
    TelegramLogin,
    admin_panel,
    admin_static_page,
    admin_workflow_dashboard,
    employee_create_daily_report,
    employee_static_page,
    employee_profile,
    get_current_employee,
    require_admin,
    telegram_employee_login,
)
from app.telegram_auth import create_employee_session
from app.workflows import create_card_request, daily_report, initialize_workflows


class EmployeeLoginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "employees.sqlite3"
        initialize_database(self.database_path)
        self.bot_token = "test-bot-token"
        self.secret_key = "a-test-secret-key-that-is-long-enough"
        self.settings = SimpleNamespace(
            bot_token=SimpleNamespace(get_secret_value=lambda: self.bot_token),
            superadmin_id=99999,
            secret_key=SimpleNamespace(get_secret_value=lambda: self.secret_key),
            employee_db_path=self.database_path,
            report_group_id=-5578176162,
            app_env="test",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def signed_init_data(self, telegram_id: int, auth_date: int) -> str:
        fields = {
            "auth_date": str(auth_date),
            "user": json.dumps({"id": telegram_id, "first_name": "Ali"}),
        }
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(fields.items())
        )
        secret_key = hmac.new(
            b"WebAppData",
            self.bot_token.encode(),
            hashlib.sha256,
        ).digest()
        fields["hash"] = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        return urlencode(fields)

    async def test_registered_employee_can_exchange_telegram_data_for_session(self) -> None:
        register_employee(self.database_path, 12345, "Ali Valiyev")
        now = 1_750_000_000
        with (
            patch("app.main.get_settings", return_value=self.settings),
            patch("app.telegram_auth.time.time", return_value=now),
        ):
            response = Response()
            result = await telegram_employee_login(
                TelegramLogin(init_data=self.signed_init_data(12345, now)),
                response,
            )
            cookie = SimpleCookie()
            cookie.load(response.headers["set-cookie"])
            session = cookie["employee_session"].value
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/employee/api/me",
                    "headers": [
                        (b"cookie", f"employee_session={session}".encode()),
                    ],
                }
            )
            profile = await employee_profile(get_current_employee(request))

        self.assertEqual(result, {"status": "authenticated", "role": "employee"})
        self.assertEqual(profile, {"telegram_id": 12345, "bot_name": "Ali Valiyev"})
        self.assertIn("httponly", response.headers["set-cookie"].lower())

    async def test_unregistered_telegram_account_is_rejected(self) -> None:
        now = 1_750_000_000
        with (
            patch("app.main.get_settings", return_value=self.settings),
            patch("app.telegram_auth.time.time", return_value=now),
        ):
            with self.assertRaises(HTTPException) as error:
                await telegram_employee_login(
                    TelegramLogin(init_data=self.signed_init_data(12345, now)),
                    Response(),
                )

        self.assertEqual(error.exception.status_code, 403)

    async def test_invalid_telegram_signature_is_rejected(self) -> None:
        register_employee(self.database_path, 12345, "Ali")
        now = 1_750_000_000
        invalid_data = self.signed_init_data(12345, now).replace("Ali", "Eve")
        with (
            patch("app.main.get_settings", return_value=self.settings),
            patch("app.telegram_auth.time.time", return_value=now),
        ):
            with self.assertRaises(HTTPException) as error:
                await telegram_employee_login(
                    TelegramLogin(init_data=invalid_data),
                    Response(),
                )

        self.assertEqual(error.exception.status_code, 401)

    async def test_superadmin_telegram_account_receives_admin_session(self) -> None:
        now = 1_750_000_000
        with (
            patch("app.main.get_settings", return_value=self.settings),
            patch("app.telegram_auth.time.time", return_value=now),
        ):
            response = Response()
            result = await telegram_employee_login(
                TelegramLogin(init_data=self.signed_init_data(self.settings.superadmin_id, now)),
                response,
            )
            cookie = SimpleCookie()
            cookie.load(response.headers["set-cookie"])
            admin_session = cookie["admin_session"].value
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/admin/api/employees",
                    "headers": [
                        (b"cookie", f"admin_session={admin_session}".encode()),
                    ],
                }
            )
            require_admin(request)

        self.assertEqual(result, {"status": "authenticated", "role": "admin"})

    async def test_employee_session_cannot_access_admin_routes(self) -> None:
        register_employee(self.database_path, 12345, "Ali")
        employee_session = create_employee_session(12345, self.secret_key)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/admin/api/employees",
                "headers": [
                    (b"cookie", f"admin_session={employee_session}".encode()),
                ],
            }
        )
        with patch("app.main.get_settings", return_value=self.settings):
            with self.assertRaises(HTTPException) as error:
                require_admin(request)

        self.assertEqual(error.exception.status_code, 403)

    async def test_admin_panel_loads_telegram_sdk_and_gates_controls(self) -> None:
        html = await admin_panel()

        self.assertIn("telegram.org/js/telegram-web-app.js", html)
        self.assertIn("telegram.initData", html)
        self.assertIn("control.disabled = false", html)
        self.assertIn('name="telegram_id"', html)

    async def test_web_pages_are_separate_static_frontend_files(self) -> None:
        admin_page = await admin_static_page()
        employee_page = await employee_static_page()

        self.assertTrue(Path(admin_page.path).is_file())
        self.assertTrue(Path(employee_page.path).is_file())
        admin_html = Path(admin_page.path).read_text(encoding="utf-8")
        employee_html = Path(employee_page.path).read_text(encoding="utf-8")
        self.assertIn("/static/admin.js", admin_html)
        self.assertIn('id="monthly-ranking"', admin_html)
        self.assertIn('id="overall-ranking"', admin_html)
        self.assertNotIn("Karta to'ldirish so'rovlari", admin_html)
        self.assertNotIn("Admin amallari tarixi", admin_html)
        self.assertNotIn('id="audit"', admin_html)
        self.assertIn("/static/employee.js", employee_html)
        self.assertIn("Sizning birgina xatoyingiz sizni moliyaviy qiyin ahvolga soladi", employee_html)
        self.assertIn('id="card-amount-preview"', employee_html)
        self.assertIn('id="monthly-ranking"', employee_html)
        self.assertIn('id="overall-ranking"', employee_html)
        self.assertIn('maxlength="19" required', employee_html)
        self.assertIn('maxlength="120" required', employee_html)
        self.assertIn('maxlength="13" required', employee_html)
        self.assertIn(
            'name="amount" type="text" inputmode="numeric" pattern="[0-9]{1,3}( [0-9]{3})*" maxlength="13" required',
            employee_html,
        )
        for field in (
            "paynet",
            "levy",
            "simcard",
            "debt_payment",
            "terminal",
            "daily",
            "discount",
            "expense",
        ):
            self.assertIn(
                f'name="{field}" type="text" inputmode="numeric"',
                employee_html,
            )
            self.assertIn(f'name="{field}" type="text"', employee_html)
        self.assertIn('pattern="[0-9]{1,3}( [0-9]{3})*" maxlength="13"', employee_html)
        for field in (
            "paynet",
            "levy",
            "simcard",
            "debt_payment",
            "terminal",
            "daily",
            "discount",
            "expense",
        ):
            self.assertNotRegex(
                employee_html,
                rf'name="{field}"[^>]*value="0"',
            )

    async def test_admin_workflow_api_does_not_expose_card_request_history(self) -> None:
        initialize_workflows(self.database_path)
        register_employee(self.database_path, 12345, "Ali")
        create_card_request(
            self.database_path, 12345, "1234567890123456", "Ali Valiyev", 100_000
        )

        with patch("app.main.get_settings", return_value=self.settings):
            dashboard = await admin_workflow_dashboard()

        self.assertNotIn("cards", dashboard)
        self.assertNotIn("audit", dashboard)

    async def test_report_submission_sends_once_and_replaces_previous_group_message(self) -> None:
        initialize_workflows(self.database_path)
        register_employee(self.database_path, 12345, "Ali")
        bot = SimpleNamespace(
            delete_message=AsyncMock(),
            send_message=AsyncMock(
                side_effect=[
                    SimpleNamespace(message_id=501),
                    SimpleNamespace(message_id=502),
                ]
            ),
        )
        bot_context = AsyncMock()
        bot_context.__aenter__.return_value = bot
        bot_context.__aexit__.return_value = False
        first_payload = DailyReportCreate(
            work_date="2026-10-14",
            paynet=100_000,
            levy=0,
            simcard=2,
            debt_payment=0,
            terminal=0,
            daily=0,
            discount=0,
            expense=0,
        )
        replacement_payload = first_payload.model_copy(update={"paynet": 250_000})

        with (
            patch("app.main.get_settings", return_value=self.settings),
            patch("app.main.Bot", return_value=bot_context),
        ):
            first_result = await employee_create_daily_report(
                first_payload,
                Employee(telegram_id=12345, bot_name="Ali"),
            )
            second_result = await employee_create_daily_report(
                replacement_payload,
                Employee(telegram_id=12345, bot_name="Ali"),
            )

        self.assertEqual(first_result["status"], "pending")
        self.assertEqual(second_result["id"], first_result["id"])
        self.assertEqual(bot.send_message.await_count, 2)
        bot.delete_message.assert_awaited_once_with(
            chat_id=-5578176162,
            message_id=501,
        )
        bot.send_message.assert_awaited_with(
            chat_id=-5578176162,
            text=unittest.mock.ANY,
        )
        self.assertIn("250 000 so'm", bot.send_message.await_args.kwargs["text"])
        stored_report = daily_report(
            self.database_path,
            12345,
            "2026-10-14",
        )
        self.assertEqual(stored_report["notification_message_id"], 502)

    async def test_card_request_accepts_grouped_digits_and_normalizes_payload(self) -> None:
        payload = CardRequestCreate(
            card_number="1234 5678 9012 3456",
            cardholder="  Ali   Valiyev ",
            amount="1 234 567",
        )

        self.assertEqual(payload.card_number, "1234567890123456")
        self.assertEqual(payload.cardholder, "Ali Valiyev")
        self.assertEqual(payload.amount, 1_234_567)

    async def test_card_request_requires_minimum_amount(self) -> None:
        for amount in (1, 9_999):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                CardRequestCreate(
                    card_number="1234567890123456",
                    cardholder="Ali Valiyev",
                    amount=amount,
                )
        accepted = CardRequestCreate(
            card_number="1234567890123456",
            cardholder="Ali Valiyev",
            amount=10_000,
        )
        self.assertEqual(accepted.amount, 10_000)

    async def test_card_request_rejects_invalid_digit_counts_and_non_letter_names(self) -> None:
        invalid_payloads = [
            {"card_number": "1234 5678 9012 345", "cardholder": "Ali", "amount": "100 000"},
            {"card_number": "1234 5678 9012 34567", "cardholder": "Ali", "amount": "100 000"},
            {"card_number": "１２３４ ５６７８ ９０１２ ３４５６", "cardholder": "Ali", "amount": "100 000"},
            {"card_number": "1234 5678 9012 3456", "cardholder": "Ali 2", "amount": "100 000"},
            {"card_number": "1234 5678 9012 3456", "cardholder": "   ", "amount": "100 000"},
            {"card_number": "1234 5678 9012 3456", "cardholder": "Ali", "amount": "10 0x0"},
            {"card_number": "1234 5678 9012 3456", "cardholder": "Ali", "amount": "１０0 000"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                CardRequestCreate(**payload)

    async def test_report_model_requires_integer_values_after_frontend_normalization(self) -> None:
        valid_payload = {
            "work_date": "2026-10-14",
            "paynet": 1_234_567,
            "levy": 0,
            "simcard": 1_000,
            "debt_payment": 25_000,
            "terminal": 0,
            "daily": 0,
            "discount": 0,
            "expense": 0,
        }
        report = DailyReportCreate(**valid_payload)
        self.assertEqual(report.paynet, 1_234_567)
        self.assertEqual(report.simcard, 1_000)

        invalid_payload = {**valid_payload, "paynet": "1 234 567"}
        with self.assertRaises(ValidationError):
            DailyReportCreate(**invalid_payload)

    async def test_admin_routes_reject_missing_admin_session(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/admin/api/employees",
                "headers": [],
            }
        )
        with patch("app.main.get_settings", return_value=self.settings):
            with self.assertRaises(HTTPException) as error:
                require_admin(request)

        self.assertEqual(error.exception.status_code, 401)

    async def test_dismissal_invalidates_existing_employee_session(self) -> None:
        register_employee(self.database_path, 12345, "Ali Valiyev")
        session_cookie = create_employee_session(12345, self.secret_key)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/employee/api/me",
                "headers": [
                    (b"cookie", f"employee_session={session_cookie}".encode()),
                ],
            }
        )
        with patch("app.main.get_settings", return_value=self.settings):
            dismiss_employee(self.database_path, 12345)
            with self.assertRaises(HTTPException) as error:
                get_current_employee(request)

        self.assertEqual(error.exception.status_code, 403)

if __name__ == "__main__":
    unittest.main()
