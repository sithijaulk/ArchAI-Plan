from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ArchAI-Plan"
    app_env: str = "development"

    # PostgreSQL Database Configuration
    db_host: str = "100.119.58.49"
    db_port: int = 5432
    db_name: str = "archai_plan"
    db_user: str = "archai_team"
    db_password: str = "archai"

    # Optional full URL (if not set, constructed from db_* settings)
    database_url: Optional[str] = "postgresql+psycopg2://archai_team:archai@100.119.58.49:5432/archai_plan"

    jwt_secret_key: str = "replace-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    upload_dir: str = "app/uploads"
    max_upload_mb: int = 10

    # Feature Model Services
    gab_model_service_url: str | None = None
    vsai_model_service_url: str | None = None
    esai_model_service_url: str | None = None
    elia_model_service_url: str | None = None
    cubicasa_weights_path: str = "C:/Users/IMAKA/Desktop/CubicasaRoomSegmentation/weights/cubicasa5k.pkl"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def assemble_db_url(self) -> "Settings":
        if not self.database_url:
            self.database_url = (
                f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        else:
            if self.database_url.startswith("postgres://"):
                self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif self.database_url.startswith("postgresql://") and not self.database_url.startswith("postgresql+"):
                self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return self


settings = Settings()
