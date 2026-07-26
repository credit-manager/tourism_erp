"""
Centralized, environment-driven configuration with production safety validation.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    app_name: str = "Tourism ERP"
    database_url: str = "sqlite:///tourism_erp.db"
    secret_key: str = "change-me-in-production"
    session_cookie_max_age: int = 60 * 60 * 8
    upload_dir: str = "static/uploads"
    api_v1_prefix: str = "/api/v1"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="before")
    @classmethod
    def check_production_safety(cls, values):
        env = values.get("environment", "")
        if env in ("production", "staging"):
            db_url = str(values.get("database_url", ""))
            if db_url.startswith("sqlite"):
                raise ValueError("ممنوع استخدام SQLite في الإنتاج. استخدم PostgreSQL (DATABASE_URL=postgresql://...))")
            if values.get("secret_key") == "change-me-in-production":
                raise ValueError("غيّر SECRET_KEY الافتراضي قبل التشغيل في الإنتاج")
        return values


settings = Settings()
