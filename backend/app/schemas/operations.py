from datetime import datetime
from pydantic import BaseModel


class PruneReportOut(BaseModel):
    started_at: datetime
    finished_at: datetime
    audit_logs_deleted: int
    collector_runs_deleted: int
    rollups_optimized: list[str]
    disk_percent: float
    disk_free_bytes: int
    watchdog_fired: bool
    actions_taken: list[str]
    errors: list[str]


class ReclaimEstimate(BaseModel):
    """Best-effort estimate of bytes that scripts/reclaim.sh could free."""
    audit_logs_rows_to_delete: int
    collector_runs_rows_to_delete: int
    failed_inserts_rows: int
    docker_hint: str
