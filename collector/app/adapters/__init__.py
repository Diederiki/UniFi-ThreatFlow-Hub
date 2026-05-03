from typing import Any

from app.adapters.base import BaseUniFiCollector, CollectResult
from app.adapters.inventory import (
    UniFiClientInventoryCollector,
    UniFiDeviceInventoryCollector,
)
from app.adapters.local_controller import LocalControllerAdapter
from app.adapters.mock import MockCollector
from app.adapters.unifi_cloud import UnifiCloudAdapter
from app.config import settings

__all__ = [
    "BaseUniFiCollector",
    "CollectResult",
    "LocalControllerAdapter",
    "MockCollector",
    "UnifiClientInventoryCollector",
    "UniFiDeviceInventoryCollector",
    "UnifiCloudAdapter",
    "select_adapter",
]


def select_adapter(branch: dict[str, Any]) -> BaseUniFiCollector:
    """Pick the right adapter for a branch.

    Mock mode wins everything when MOCK_DATA=true.
    Otherwise we look at the controller_url:
      - host endswith ui.com / ubnt.com → UnifiCloudAdapter
      - anything else                   → LocalControllerAdapter
    Phase 4 ships only the mock adapter wired end-to-end; the other two have
    real httpx scaffolding ready for plug-in once we have a live device.
    """
    if settings.mock_data:
        return MockCollector(branch)

    url = (branch.get("controller_url") or "").lower()
    if "ui.com" in url or "ubnt.com" in url:
        return UnifiCloudAdapter(branch)
    return LocalControllerAdapter(branch)
