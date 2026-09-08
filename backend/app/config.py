"""Runtime settings, read once from the environment (and backend/.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://postgres:kali@localhost:5432/envless"
    envless_master_key: str = ""
    cors_origins: str = "http://localhost:3000,http://localhost:8100"

    # An application reading its own configuration pulls rarely - it is told
    # when something changes. These numbers are set well above that, so they
    # only catch something behaving unlike an application.
    runtime_rate_limit: int = 120       # pulls a minute before a token is refused
    runtime_burst_alert: int = 30       # pulls a minute that are worth flagging

    # X-Forwarded-For is set by whoever sends it. Believe it only when
    # something in front of envless is known to be rewriting it, or the source
    # address in every alert becomes whatever the caller felt like claiming.
    trust_proxy_header: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
