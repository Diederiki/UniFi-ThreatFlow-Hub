"""/api/observability — live host telemetry for the Operations page.

Reads via psutil from inside the backend container. Because containers share
the host kernel, /proc reflects host-wide metrics (cpu/mem are per-container
unless cgroup limits are off; disk is per-mount). For this stack we surface:
  - CPU percent (1s sample) + core count
  - Memory used/total + percent
  - Disk used/total + percent for the data volume
  - Network rx/tx delta (B/s) since last call (per-process state)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import psutil
from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/observability", tags=["observability"])
log = logging.getLogger(__name__)

# Global state for network deltas
_last_net = {"ts": 0.0, "rx": 0, "tx": 0}


def _disk_for_path(path: str = "/") -> dict[str, int | float]:
    try:
        usage = psutil.disk_usage(path)
        return {"total": int(usage.total), "used": int(usage.used), "free": int(usage.free), "percent": float(usage.percent)}
    except Exception:  # noqa: BLE001
        return {"total": 0, "used": 0, "free": 0, "percent": 0.0}


def _net_rates() -> dict[str, float]:
    counters = psutil.net_io_counters()
    now = time.time()
    rx, tx = int(counters.bytes_recv), int(counters.bytes_sent)
    last_ts, last_rx, last_tx = _last_net["ts"], _last_net["rx"], _last_net["tx"]
    rx_rate = tx_rate = 0.0
    if last_ts > 0:
        dt = max(0.001, now - last_ts)
        rx_rate = max(0.0, (rx - last_rx) / dt)
        tx_rate = max(0.0, (tx - last_tx) / dt)
    _last_net["ts"] = now; _last_net["rx"] = rx; _last_net["tx"] = tx
    return {"rx_bytes_per_s": rx_rate, "tx_bytes_per_s": tx_rate, "rx_total": rx, "tx_total": tx}


@router.get("/host")
async def host_metrics(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    # cpu_percent(interval=None) returns since-last-call; first call returns 0.
    # We poll it twice with a tiny sleep to get a fresh sample on every request.
    psutil.cpu_percent(interval=None)
    await asyncio.sleep(0.1)
    cpu_percent = psutil.cpu_percent(interval=None)

    vm = psutil.virtual_memory()
    return {
        "ts": int(time.time() * 1000),
        "cpu": {
            "percent": float(cpu_percent),
            "cores": int(psutil.cpu_count(logical=True) or 0),
            "load_avg_1m": psutil.getloadavg()[0] if hasattr(psutil, "getloadavg") else None,
        },
        "memory": {
            "total": int(vm.total),
            "used": int(vm.used),
            "available": int(vm.available),
            "percent": float(vm.percent),
        },
        "disk": _disk_for_path("/"),
        "network": _net_rates(),
    }


@router.get("/host/processes")
async def host_processes(_user: User = Depends(get_current_user), limit: int = 10) -> dict[str, Any]:
    """Top processes by RSS — capped to `limit` so we never return more than ~30 rows."""
    procs = []
    for p in psutil.process_iter(attrs=["pid", "name", "memory_info", "cpu_percent"]):
        try:
            mi = p.info.get("memory_info")
            procs.append({
                "pid": p.info.get("pid"),
                "name": p.info.get("name") or "?",
                "rss": int(mi.rss) if mi else 0,
                "cpu_percent": float(p.info.get("cpu_percent") or 0),
            })
        except Exception:  # noqa: BLE001
            continue
    procs.sort(key=lambda x: x["rss"], reverse=True)
    return {"items": procs[: min(limit, 30)]}
