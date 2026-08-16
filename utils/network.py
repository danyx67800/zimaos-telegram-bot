"""Verifica di latenza e disponibilità di rete via TCP (solo stdlib)."""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse

_IPV6_PORT_RE = re.compile(r"^\[(.+?)\](?::(\d+))?$")


@dataclass
class PingResult:
    target: str
    host: str
    port: int
    ip: str | None
    reachable: bool
    latency_ms: float | None
    error: str | None = None


def _default_port_for(scheme: str) -> int:
    return 80 if scheme == "http" else 443


def parse_target(raw: str) -> tuple[str, int]:
    """Normalizza un host o URL in una coppia (host, porta)."""
    target = raw.strip()
    if not target:
        raise ValueError("Specifica un host o URL, es. /ping google.com")

    scheme = ""
    host = target
    port: int | None = None

    if "://" in target:
        parsed = urlparse(target)
        scheme = (parsed.scheme or "").lower()
        host = parsed.hostname or ""
        port = parsed.port

    if port is None and host:
        if host.startswith("["):
            # Indirizzo IPv6 tra parentesi quadre, es. "[::1]:8080".
            match = _IPV6_PORT_RE.match(host)
            if match:
                host = match.group(1)
                port = int(match.group(2)) if match.group(2) else None
        elif host.count(":") == 1:
            maybe_host, _, maybe_port = host.rpartition(":")
            if maybe_port.isdigit():
                host, port = maybe_host, int(maybe_port)

    if not host:
        raise ValueError("Impossibile ricavare l'host dal target.")

    return host, int(port or _default_port_for(scheme))


def ping(target: str, timeout: float = 5.0) -> PingResult:
    """Verifica disponibilità e latenza (TCP connect) di un host/URL."""
    try:
        host, port = parse_target(target)
    except ValueError as exc:
        return PingResult(
            target=target, host="", port=0, ip=None,
            reachable=False, latency_ms=None, error=str(exc),
        )

    result = PingResult(
        target=target, host=host, port=port, ip=None,
        reachable=False, latency_ms=None,
    )

    try:
        result.ip = socket.gethostbyname(host)
    except socket.gaierror as exc:
        result.error = f"Risoluzione DNS fallita: {exc}"
        return result

    start = time.perf_counter()
    try:
        with socket.create_connection((result.ip, port), timeout=timeout):
            elapsed = time.perf_counter() - start
        result.reachable = True
        result.latency_ms = round(elapsed * 1000, 1)
    except (socket.timeout, TimeoutError):
        result.error = f"Timeout dopo {timeout:.0f}s"
    except ConnectionRefusedError:
        result.error = f"Connessione rifiutata sulla porta {port}"
    except OSError as exc:
        result.error = str(exc)

    return result
