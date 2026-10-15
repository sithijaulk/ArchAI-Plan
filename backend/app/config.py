from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    app_name: str = "ArchAI-Plan"
    app_env: str = "development"
    database_url: str = "mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/archai_plan"
    jwt_secret_key: str = "replace-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    upload_dir: str = "app/uploads"
    max_upload_mb: int = 10
    elia_model_artifact_path: str | None = None
    elia_model_service_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
