from datetime import datetime

from pydantic import BaseModel


class TableHealth(BaseModel):
    name: str
    rows: int
    bytes_on_disk: int
    bytes_uncompressed: int
    compression_ratio: float | None = None
    parts: int
    oldest_event: datetime | None = None
    newest_event: datetime | None = None


class StorageHealth(BaseModel):
    clickhouse_ok: bool
    raw_flow_events: TableHealth | None = None
    raw_threat_events: TableHealth | None = None
    rollup_1m: TableHealth | None = None
    rollup_5m: TableHealth | None = None
    rollup_15m: TableHealth | None = None
    rollup_1h: TableHealth | None = None
    rollup_1d: TableHealth | None = None
    failed_inserts_30d: int = 0
    rollup_freshness_1m_seconds: int | None = None
    events_per_day_estimate: int | None = None


class RetentionPolicy(BaseModel):
    table: str
    ttl_days: int


class RetentionList(BaseModel):
    items: list[RetentionPolicy]


class RetentionUpdate(BaseModel):
    items: list[RetentionPolicy]
