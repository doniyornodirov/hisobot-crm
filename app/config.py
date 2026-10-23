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
    bot_token: SecretStr
    superadmin_id: int = Field(gt=0)
    admin_group_id: int
    report_group_id: int
    web_app_url: str | None = None
    employee_db_path: str = "data/employees.sqlite3"
    database_url: SecretStr
    secret_key: SecretStr
    postgres_password: SecretStr | None = None
    admin_username: str = "admin"
    admin_password: str = "admin123"

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
        if self.app_env == "production":
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
