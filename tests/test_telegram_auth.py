import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode

from app.telegram_auth import (
    create_employee_session,
    validate_employee_session,
    validate_telegram_init_data,
)


class TelegramInitDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bot_token = "test-bot-token"
        self.now = 1_750_000_000

    def signed_init_data(self, user_id: int, auth_date: int) -> str:
        fields = {
            "auth_date": str(auth_date),
            "query_id": "query-1",
            "user": json.dumps({"id": user_id, "first_name": "Ali"}),
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

    def test_accepts_fresh_data_signed_by_bot(self) -> None:
        data = self.signed_init_data(12345, self.now)

        user = validate_telegram_init_data(data, self.bot_token, now=self.now)

        self.assertEqual(user["id"], 12345)

    def test_rejects_modified_data(self) -> None:
        data = self.signed_init_data(12345, self.now).replace("Ali", "Eve")

        with self.assertRaises(ValueError):
            validate_telegram_init_data(data, self.bot_token, now=self.now)

    def test_rejects_expired_data(self) -> None:
        data = self.signed_init_data(12345, self.now - 301)

        with self.assertRaises(ValueError):
            validate_telegram_init_data(data, self.bot_token, now=self.now)

    def test_rejects_duplicate_fields(self) -> None:
        data = self.signed_init_data(12345, self.now) + "&auth_date=1"

        with self.assertRaises(ValueError):
            validate_telegram_init_data(data, self.bot_token, now=self.now)


class EmployeeSessionTests(unittest.TestCase):
    def test_session_is_signed_and_expires(self) -> None:
        token = create_employee_session(12345, "test-secret", now=1000, lifetime_seconds=60)

        self.assertEqual(validate_employee_session(token, "test-secret", now=1059), 12345)
        self.assertIsNone(validate_employee_session(token, "wrong-secret", now=1059))
        self.assertIsNone(validate_employee_session(token, "test-secret", now=1060))


if __name__ == "__main__":
    unittest.main()
