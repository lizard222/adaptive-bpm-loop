from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация каркаса. Переопределяется переменными окружения с префиксом ABL_."""

    database_url: str = "postgresql://abl:abl_dev_password@localhost:5432/abl"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"  # >=32 байт (RFC 7518)
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 120
    documents_dir: str = "generated_documents"

    model_config = {"env_prefix": "ABL_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
