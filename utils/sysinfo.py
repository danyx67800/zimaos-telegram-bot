"""Funzioni di monitoraggio di sistema basate su psutil."""

from __future__ import annotations

import time
from pathlib import Path

import psutil

# Clock tick al secondo (Linux). 100 è il valore tipico; fallback per altri OS.
_CLK_TCK = getattr(__import__("os"), "sysconf", lambda _name: 100)("SC_CLK_TCK") or 100


def cpu_percent(interval: float = 0.5) -> float:
    """Percentuale di utilizzo CPU campionata sull'intervallo indicato."""
    return psutil.cpu_percent(interval=interval)


def virtual_memory() -> dict:
    """Statistiche RAM del sistema."""
    mem = psutil.virtual_memory()
    return {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": mem.percent,
    }


def disk_usage() -> list[dict]:
    """Uso dei dischi, filtrando i mount virtuali meno significativi."""
    result: list[dict] = []
    skipped_fstypes = {"squashfs", "iso9660"}

    for part in psutil.disk_partitions(all=False):
        if part.fstype in skipped_fstypes:
            continue
        if part.mountpoint.startswith(("/snap/", "/boot/efi")):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            # Mount non accessibile o smontato nel frattempo.
            continue
        if usage.total <= 0:
            continue
        result.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        )
    return result


def system_uptime_seconds() -> float:
    """Uptime del sistema (host ZimaOS)."""
    return time.time() - psutil.boot_time()


def container_uptime_seconds() -> float | None:
    """Uptime del container (PID 1) letto da /proc/1/stat.

    Restituisce None se /proc non è disponibile (es. fuori da Linux).
    """
    try:
        stat = Path("/proc/1/stat").read_text()
        # Il campo "comm" (2°) può contenere spazi e parentesi: si taglia
        # tutto fino all'ultima ")", poi "starttime" (22°) è all'indice 19.
        fields = stat[stat.rfind(")") + 2 :].split()
        start_ticks = int(fields[19])
    except (OSError, ValueError, IndexError):
        return None

    started_seconds_ago = start_ticks / _CLK_TCK
    return max(system_uptime_seconds() - started_seconds_ago, 0.0)


def format_bytes(num: float) -> str:
    """Formatta un numero di byte in unità leggibili."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} EB"


def format_uptime(seconds: float) -> str:
    """Formatta un intervallo di secondi come '1g 2h 3m 4s'."""
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}g")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
