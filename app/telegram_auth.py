import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = 300,
) -> dict[str, object]:
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("Duplicate Telegram init data field")
        fields[key] = value

    received_hash = fields.pop("hash", None)
    if received_hash is None:
        raise ValueError("Telegram init data has no hash")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Telegram init data signature is invalid")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Telegram init data is missing required user details") from error

    current_time = int(time.time()) if now is None else now
    if auth_date > current_time + 30 or current_time - auth_date > max_age_seconds:
        raise ValueError("Telegram init data has expired")
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise ValueError("Telegram init data contains an invalid user")
    return user


def create_employee_session(
    telegram_id: int,
    secret: str,
    *,
    now: int | None = None,
    lifetime_seconds: int = 43_200,
) -> str:
    expires_at = (int(time.time()) if now is None else now) + lifetime_seconds
    payload = f"{telegram_id}.{expires_at}"
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_employee_session(
    session: str,
    secret: str,
    *,
    now: int | None = None,
) -> int | None:
    try:
        telegram_id_text, expires_text, received_signature = session.split(".")
        telegram_id = int(telegram_id_text)
        expires_at = int(expires_text)
    except (AttributeError, ValueError):
        return None

    payload = f"{telegram_id}.{expires_at}"
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, received_signature):
        return None
    current_time = int(time.time()) if now is None else now
    if telegram_id <= 0 or expires_at <= current_time:
        return None
    return telegram_id
