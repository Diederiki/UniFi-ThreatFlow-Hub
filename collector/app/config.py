from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field("production", alias="APP_ENV")
    log_level: str = Field("info", alias="LOG_LEVEL")
    mock_data: bool = Field(True, alias="MOCK_DATA")

    interval_seconds: int = Field(30, alias="COLLECTOR_INTERVAL_SECONDS")
    max_concurrent: int = Field(10, alias="COLLECTOR_MAX_CONCURRENT")
    timeout_seconds: int = Field(10, alias="COLLECTOR_TIMEOUT_SECONDS")
    retries: int = Field(2, alias="COLLECTOR_RETRIES")

    redis_host: str = Field("redis", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_password: str = Field("", alias="REDIS_PASSWORD")


settings = CollectorSettings()
