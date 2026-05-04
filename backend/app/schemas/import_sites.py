from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    api_key: str = Field(min_length=8, description="Site Manager API key from unifi.ui.com → Settings → API")
    firewalls_only: bool = Field(default=True, description="Skip controllers/NVRs/software hosts; keep only UDM/UDR/UCG/Fortress")


class ImportSummaryOut(BaseModel):
    total_seen: int
    created: int
    skipped_existing: int
    skipped_non_firewall: int = 0
    failed: int
    errors: list[str] = []
