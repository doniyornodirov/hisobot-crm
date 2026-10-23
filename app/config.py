import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    bot_token: SecretStr = SecretStr("8826367314:AAGMdClzpHAMPPPKxZN7MLLt0-V4QCAdFN8")
    superadmin_id: int = Field(default=8686341550, gt=0)
    admin_group_id: int = -1003747381544
    report_group_id: int = -5578176162
    web_app_url: str | None = None
    employee_db_path: str = Field(
        default_factory=lambda: "/tmp/employees.sqlite3"
        if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
        else "data/employees.sqlite3"
    )
    database_url: SecretStr = SecretStr("sqlite:////tmp/employees.sqlite3")
    secret_key: SecretStr = SecretStr("E1p0a67LeWqKnKCEZ_S3BWnRFroExrq6sXwhrcU-ETSYYSUDCjn9TB_7xkEaMpSR")
    postgres_password: SecretStr | None = None
    admin_username: str = "admin"
    admin_password: str = "admin123"

    @field_validator("bot_token", mode="before")
    @classmethod
    def clean_bot_token(cls, value: object) -> object:
        if isinstance(value, str):
            clean = value.strip().strip('"').strip("'")
            return SecretStr(clean)
        elif isinstance(value, SecretStr):
            clean = value.get_secret_value().strip().strip('"').strip("'")
            return SecretStr(clean)
        return value

    @field_validator("secret_key", mode="before")
    @classmethod
    def clean_secret_key(cls, value: object) -> object:
        if isinstance(value, str):
            clean = value.strip().strip('"').strip("'")
            return SecretStr(clean)
        elif isinstance(value, SecretStr):
            clean = value.get_secret_value().strip().strip('"').strip("'")
            return SecretStr(clean)
        return value

    @field_validator("admin_group_id", "report_group_id", "superadmin_id", mode="before")
    @classmethod
    def clean_int_ids(cls, value: object) -> object:
        if isinstance(value, str):
            clean = value.strip().strip('"').strip("'")
            return int(clean)
        return value

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        return value

    @field_validator("web_app_url")
    @classmethod
    def validate_web_app_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("WEB_APP_URL must be an HTTPS URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production" and not os.getenv("VERCEL"):
            placeholders = (
                "replace_with_telegram_bot_token",
                "replace_with_a_random_secret_of_at_least_32_characters",
            )
            configured = (
                self.bot_token.get_secret_value(),
                self.secret_key.get_secret_value(),
            )
            if any(value in placeholders for value in configured):
                raise ValueError("Replace all example credentials before production")
            if self.web_app_url is None:
                raise ValueError("WEB_APP_URL is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
