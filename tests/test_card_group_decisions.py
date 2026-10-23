import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatMemberStatus

from app.bot import card_decision_keyboard, card_notification_text, card_request_decision
from app.employees import initialize_database, register_employee
from app.workflows import (
    card_request,
    create_card_request,
    initialize_workflows,
)


class CardGroupDecisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "app.sqlite3"
        initialize_database(self.database_path)
        initialize_workflows(self.database_path)
        register_employee(self.database_path, 12345, "Doni")
        self.card_id = create_card_request(
            self.database_path, 12345, "9860356639376169", "D N", 100_000
        )
        self.settings = SimpleNamespace(
            employee_db_path=self.database_path,
            admin_group_id=-100123,
        )
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=-100123),
            edit_text=AsyncMock(),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def callback(self, data: str, user_id: int) -> SimpleNamespace:
        return SimpleNamespace(
            message=self.message,
            data=data,
            from_user=SimpleNamespace(id=user_id),
            answer=AsyncMock(),
        )

    async def test_non_admin_cannot_change_card_decision(self) -> None:
        callback = self.callback(f"card:{self.card_id}:approve", 12345)
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=ChatMemberStatus.MEMBER)
            )
        )
        with patch("app.bot.get_settings", return_value=self.settings):
            await card_request_decision(callback, bot)

        self.assertEqual(card_request(self.database_path, self.card_id)["status"], "pending")
        callback.answer.assert_awaited_once_with(
            "Qarorni faqat guruh adminlari o'zgartira oladi.",
            show_alert=True,
        )
        self.message.edit_text.assert_not_awaited()

    async def test_group_admin_can_reverse_decision_and_message_buttons_update(self) -> None:
        callback = self.callback(f"card:{self.card_id}:approve", 9001)
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR)
            )
        )
        with patch("app.bot.get_settings", return_value=self.settings):
            await card_request_decision(callback, bot)

        saved = card_request(self.database_path, self.card_id)
        self.assertEqual(saved["status"], "approved")
        self.assertEqual(saved["decided_by"], 9001)
        self.assertIn("✅ Tasdiqlandi", self.message.edit_text.await_args.args[0])
        self.assertEqual(
            self.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].text,
            "❌ Rad etish",
        )

        reverse_callback = self.callback(f"card:{self.card_id}:reject", 9002)
        with patch("app.bot.get_settings", return_value=self.settings):
            await card_request_decision(reverse_callback, bot)
        rejected = card_request(self.database_path, self.card_id)
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["decided_by"], 9002)
        self.assertIn("❌ Rad etildi", self.message.edit_text.await_args.args[0])
        self.assertEqual(
            self.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].text,
            "✅ Tasdiqlash",
        )

    def test_notification_uses_emoji_and_status_specific_toggle_buttons(self) -> None:
        request = {
            "id": self.card_id,
            "employee_id": 12345,
            "bot_name": "Doni",
            "card_number": "9860356639376169",
            "cardholder": "D N",
            "amount": 100_000,
            "status": "pending",
        }
        text = card_notification_text(request)

        self.assertIn("👤 Xodim: Doni", text)
        self.assertIn("💳 Karta: 9860356639376169", text)
        self.assertIn("🪪 Ega: D N", text)
        self.assertIn("💰 Summa: 100 000 so'm", text)
        self.assertEqual(
            [button.text for button in card_decision_keyboard(self.card_id, "pending").inline_keyboard[0]],
            ["✅ Tasdiqlash", "❌ Rad etish"],
        )

    def test_second_card_request_for_same_card_today_warns_admin_group(self) -> None:
        repeated_id = create_card_request(
            self.database_path, 12345, "9860356639376169", "D N", 200_000
        )

        repeated_request = card_request(self.database_path, repeated_id)
        self.assertEqual(repeated_request["same_day_count"], 2)
        self.assertIn(
            "⚠️ DIQQAT: Bugun bu kartaga to'lov qilindi. ❌❌❌",
            card_notification_text(repeated_request),
        )

        first_request = card_request(self.database_path, self.card_id)
        self.assertEqual(first_request["same_day_count"], 2)
        self.assertIn(
            "⚠️ DIQQAT: Bugun bu kartaga to'lov qilindi. ❌❌❌",
            card_notification_text(first_request),
        )

    def test_card_request_count_resets_on_uzbekistan_work_date(self) -> None:
        import sqlite3

        connection = sqlite3.connect(self.database_path)
        try:
            previous_day = (
                date.fromisoformat(
                    connection.execute(
                        "SELECT work_date FROM card_requests WHERE id = ?",
                        (self.card_id,),
                    ).fetchone()[0]
                )
                - timedelta(days=1)
            ).isoformat()
            connection.execute(
                "UPDATE card_requests SET work_date = ? WHERE id = ?",
                (previous_day, self.card_id),
            )
            connection.commit()
        finally:
            connection.close()

        new_day_id = create_card_request(
            self.database_path, 12345, "9860356639376169", "D N", 200_000
        )
        new_day_request = card_request(self.database_path, new_day_id)

        self.assertEqual(new_day_request["same_day_count"], 1)
        self.assertNotIn("Bugun bu kartaga to'lov qilindi", card_notification_text(new_day_request))


if __name__ == "__main__":
    unittest.main()
