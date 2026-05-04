from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    api_key: str = Field(min_length=8, description="Site Manager API key from unifi.ui.com → Settings → API")


class ImportSummaryOut(BaseModel):
    total_seen: int
    created: int
    skipped_existing: int
    failed: int
    errors: list[str] = []
