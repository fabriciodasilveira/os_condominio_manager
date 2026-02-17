from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    database_url: str = "sqlite:///./app.db"
    upload_dir: str = "app/uploads"

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claims_sub: str = "mailto:admin@condominio.local"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
