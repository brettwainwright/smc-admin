from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root, so .env is found regardless of the working directory the app starts from
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """App configuration read from .env (real environment variables take precedence).

    Required fields fail at startup naming the key.
    Sensitive fields use repr=False so they don't appear if settings is printed or logged.
    """

    # hide_input_in_errors: a validation error would otherwise echo every .env value, secrets included
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    # Minimum lengths stop a blank value (e.g. a copied .env.example) from being accepted
    username: str = Field(repr=False, min_length=1)  # admin superuser, created/updated by `manage.py ensure_admin`
    password: str = Field(repr=False, min_length=8)
    secret_key: str = Field(repr=False, min_length=32)  # Django SECRET_KEY (sessions, CSRF)
    db_path: Path = BASE_DIR / "data" / "db.sqlite3"
    debug: bool = False
    time_zone: str = "America/Chicago"  # US Central (CST in January); wall-clock zone for event times
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    csrf_trusted_origins: list[str] = []


settings = Settings()
