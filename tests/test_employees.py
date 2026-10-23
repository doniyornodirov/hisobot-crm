import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.bot import start_command
from app.employees import (
    Employee,
    dismiss_employee,
    get_active_employee,
    initialize_database,
    list_active_employees,
    register_employee,
)


class EmployeeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "employees.sqlite3"
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_register_and_find_active_employee(self) -> None:
        status = register_employee(self.database_path, 12345, "Ali Valiyev")

        self.assertEqual(status, "created")
        self.assertEqual(
            get_active_employee(self.database_path, 12345).bot_name,
            "Ali Valiyev",
        )

    def test_dismissed_employee_is_not_active(self) -> None:
        register_employee(self.database_path, 12345, "Ali Valiyev")

        self.assertTrue(dismiss_employee(self.database_path, 12345))
        self.assertIsNone(get_active_employee(self.database_path, 12345))
        self.assertFalse(dismiss_employee(self.database_path, 12345))
        self.assertEqual(list_active_employees(self.database_path), [])

    def test_register_reactivates_dismissed_employee(self) -> None:
        register_employee(self.database_path, 12345, "Ali")
        dismiss_employee(self.database_path, 12345)

        status = register_employee(self.database_path, 12345, "Ali Valiyev")

        self.assertEqual(status, "reactivated")
        self.assertEqual(
            get_active_employee(self.database_path, 12345).bot_name,
            "Ali Valiyev",
        )


class BotStartTests(unittest.IsolatedAsyncioTestCase):
    async def test_superadmin_receives_admin_panel_link(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=999),
            chat=SimpleNamespace(type="private"),
            answer=AsyncMock(),
            bot=SimpleNamespace(set_chat_menu_button=AsyncMock()),
        )
        settings = SimpleNamespace(
            superadmin_id=999,
            employee_db_path="unused.sqlite3",
            web_app_url="https://example.org/employee",
        )
        with patch("app.bot.get_settings", return_value=settings):
            await start_command(message)

        button = message.bot.set_chat_menu_button.await_args.kwargs["menu_button"]
        self.assertEqual(button.text, "Admin panel")
        self.assertEqual(button.web_app.url, "https://example.org/")
        self.assertNotIn("reply_markup", message.answer.await_args.kwargs)

    async def test_unregistered_user_receives_telegram_id_for_admin(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=12345),
            chat=SimpleNamespace(type="private"),
            answer=AsyncMock(),
            bot=SimpleNamespace(set_chat_menu_button=AsyncMock()),
        )
        settings = SimpleNamespace(
            superadmin_id=999,
            employee_db_path="unused.sqlite3",
            web_app_url="https://example.org/employee",
        )
        with (
            patch("app.bot.get_settings", return_value=settings),
            patch("app.bot.get_active_employee", return_value=None),
        ):
            await start_command(message)

        self.assertIn("12345", message.answer.await_args.args[0])
        self.assertIn("superadminga", message.answer.await_args.args[0])
        self.assertNotIn("reply_markup", message.answer.await_args.kwargs)

    async def test_registered_employee_is_directed_to_web_app(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=12345),
            chat=SimpleNamespace(type="private"),
            answer=AsyncMock(),
            bot=SimpleNamespace(set_chat_menu_button=AsyncMock()),
        )
        settings = SimpleNamespace(
            superadmin_id=999,
            employee_db_path="unused.sqlite3",
            web_app_url="https://example.org/employee",
        )
        with (
            patch("app.bot.get_settings", return_value=settings),
            patch(
                "app.bot.get_active_employee",
                return_value=Employee(telegram_id=12345, bot_name="Ali"),
            ),
        ):
            await start_command(message)

        self.assertIn("Ali", message.answer.await_args.args[0])
        self.assertIn("pastidagi", message.answer.await_args.args[0])
        button = message.bot.set_chat_menu_button.await_args.kwargs["menu_button"]
        self.assertEqual(button.text, "Hisobot")


if __name__ == "__main__":
    unittest.main()
