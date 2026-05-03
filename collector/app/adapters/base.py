"""Common adapter contract per blueprint § Data Fetching.

Every adapter normalizes to the same canonical event dict so the batch writer
and dedupe code never needs to care which UniFi version / endpoint produced
the data.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CollectResult:
    flows: list[dict[str, Any]] = field(default_factory=list)
    threats: list[dict[str, Any]] = field(default_factory=list)
    endpoint_used: str | None = None
    unifi_os_version: str | None = None
    network_app_version: str | None = None

    @property
    def event_count(self) -> int:
        return len(self.flows) + len(self.threats)


class BaseUniFiCollector(abc.ABC):
    """Subclasses authenticate to one branch and return normalized events."""

    def __init__(self, branch: dict[str, Any]) -> None:
        self.branch = branch
        self.branch_id: str = str(branch["id"])
        self.branch_name: str = branch["name"]
        self.branch_code: str = branch["branch_code"]
        self.controller_url: str = branch["controller_url"]
        self.site_id: str = branch.get("site_id") or "default"
        self.ssl_verify: bool = bool(branch.get("ssl_verify", True))
        self.auth_method: str = branch.get("auth_method") or "local"
        self.gateway_model: str | None = branch.get("gateway_model")

    @abc.abstractmethod
    async def collect(self) -> CollectResult:
        ...

    async def close(self) -> None:
        """Override if the adapter holds an httpx.AsyncClient or similar."""
