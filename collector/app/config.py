from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

COLLECTOR_VERSION = "0.4.0"


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field("production", alias="APP_ENV")
    log_level: str = Field("info", alias="LOG_LEVEL")
    mock_data: bool = Field(True, alias="MOCK_DATA")

    # Polling
    interval_seconds: int = Field(30, alias="COLLECTOR_INTERVAL_SECONDS")
    max_concurrent: int = Field(10, alias="COLLECTOR_MAX_CONCURRENT")
    timeout_seconds: int = Field(10, alias="COLLECTOR_TIMEOUT_SECONDS")
    retries: int = Field(2, alias="COLLECTOR_RETRIES")

    # Postgres
    postgres_host: str = Field("postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("threatflow", alias="POSTGRES_DB")
    postgres_user: str = Field("threatflow", alias="POSTGRES_USER")
    postgres_password: str = Field("", alias="POSTGRES_PASSWORD")

    # ClickHouse
    clickhouse_host: str = Field("clickhouse", alias="CLICKHOUSE_HOST")
    clickhouse_http_port: int = Field(8123, alias="CLICKHOUSE_HTTP_PORT")
    clickhouse_db: str = Field("threatflow", alias="CLICKHOUSE_DB")
    clickhouse_user: str = Field("threatflow", alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field("", alias="CLICKHOUSE_PASSWORD")

    # Redis
    redis_host: str = Field("redis", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_password: str = Field("", alias="REDIS_PASSWORD")

    # Encryption (for decrypting branch creds)
    fernet_key: str = Field(..., alias="FERNET_KEY")

    # CH insert tuning
    ch_batch_size: int = Field(5000, alias="CH_BATCH_SIZE")
    ch_flush_interval_ms: int = Field(2000, alias="CH_FLUSH_INTERVAL_MS")
    ch_insert_retries: int = Field(3, alias="CH_INSERT_RETRIES")

    @property
    def postgres_async_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = CollectorSettings()
