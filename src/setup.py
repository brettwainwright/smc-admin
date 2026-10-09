from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root, so .env is found regardless of the working directory the app starts from
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """App configuration read from .env (real environment variables take precedence).

    Every field is required; a missing value fails at startup naming the key.
    Sensitive fields use repr=False so they don't appear if settings is printed or logged.
    """

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    db: str = Field(repr=False)  # SQLAlchemy URL; may contain credentials
    signup_key: str = Field(repr=False)
    username: str = Field(repr=False)
    password: str = Field(repr=False)
    secret_key: str = Field(repr=False)


settings = Settings()
