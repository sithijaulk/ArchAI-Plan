from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "ArchAI-Plan"
    app_env: str = "development"

    # PostgreSQL Database Connection Fields
    db_host: str = "100.119.58.49"
    db_port: int = 5432
    db_name: str = "archai_plan"
    db_user: str = "archai_team"
    db_password: str = "archai"
    database_url: Optional[str] = None

    jwt_secret_key: str = "archai-plan-secret-key-change-in-production-min32chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    upload_dir: str = "app/uploads"
    max_upload_mb: int = 10
    elia_model_artifact_path: str | None = None
    elia_model_service_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        if not self.database_url:
            self.database_url = (
                f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self


settings = Settings()
