"""Typed service configuration (pydantic-settings).

All values come from the environment with sane local defaults.
Nothing here holds secrets at import time — the token is read
per-request so tests never need one.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    meta_api_version: str = "v21.0"
    meta_access_token: str = ""
    rate_limit_search: str = "30/minute"
    rate_limit_insights: str = "60/minute"
    log_level: str = "INFO"
    database_url: str = "sqlite:///snapshots/store.db"


settings = Settings()


def graph_base() -> str:
    return f"https://graph.facebook.com/{settings.meta_api_version}/ads_archive"
