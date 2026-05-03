from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Branding / env
    app_name: str = Field("UniFi Threatflow Hub for AmSpec", alias="APP_NAME")
    app_env: str = Field("production", alias="APP_ENV")
    app_domain: str = Field("threatflow.amspec.group", alias="APP_DOMAIN")
    log_level: str = Field("info", alias="LOG_LEVEL")
    mock_data: bool = Field(True, alias="MOCK_DATA")

    # Secrets
    session_secret: str = Field(..., alias="SESSION_SECRET")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    fernet_key: str = Field(..., alias="FERNET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 12  # 12 hours

    # Postgres
    postgres_host: str = Field("postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("threatflow", alias="POSTGRES_DB")
    postgres_user: str = Field("threatflow", alias="POSTGRES_USER")
    postgres_password: str = Field("", alias="POSTGRES_PASSWORD")

    # ClickHouse
    clickhouse_host: str = Field("clickhouse", alias="CLICKHOUSE_HOST")
    clickhouse_http_port: int = Field(8123, alias="CLICKHOUSE_HTTP_PORT")
    clickhouse_native_port: int = Field(9000, alias="CLICKHOUSE_NATIVE_PORT")
    clickhouse_db: str = Field("threatflow", alias="CLICKHOUSE_DB")
    clickhouse_user: str = Field("threatflow", alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field("", alias="CLICKHOUSE_PASSWORD")

    # Redis
    redis_host: str = Field("redis", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_password: str = Field("", alias="REDIS_PASSWORD")

    # CORS
    cors_allow_origins: str = Field("https://threatflow.amspec.group", alias="CORS_ALLOW_ORIGINS")

    # Admin bootstrap
    admin_email: str = Field("admin@amspecgroup.com", alias="ADMIN_EMAIL")

    # Collector
    collector_interval_seconds: int = Field(30, alias="COLLECTOR_INTERVAL_SECONDS")
    collector_max_concurrent: int = Field(10, alias="COLLECTOR_MAX_CONCURRENT")
    collector_timeout_seconds: int = Field(10, alias="COLLECTOR_TIMEOUT_SECONDS")
    collector_retries: int = Field(2, alias="COLLECTOR_RETRIES")

    # ClickHouse insert tuning
    ch_batch_size: int = Field(5000, alias="CH_BATCH_SIZE")
    ch_flush_interval_ms: int = Field(2000, alias="CH_FLUSH_INTERVAL_MS")
    ch_insert_retries: int = Field(3, alias="CH_INSERT_RETRIES")

    # ---- Derived ------------------------------------------------------------
    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def postgres_async_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
