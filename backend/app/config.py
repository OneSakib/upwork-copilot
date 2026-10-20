from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Supabase Postgres connection string (Project Settings -> Database -> Connection string)
    database_url: str
    api_token: str = "change-me"
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-5-5"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        # Supabase hands out postgres:// / postgresql:// URLs; SQLAlchemy needs the psycopg driver named
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


settings = Settings()
