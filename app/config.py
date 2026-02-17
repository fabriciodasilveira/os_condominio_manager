from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    database_url: str | None = None
    db_user: str = "condominio"
    db_password: str = "condominio"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "condominio_os"
    upload_dir: str = "app/uploads"

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claims_sub: str = "mailto:admin@condominio.local"

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
