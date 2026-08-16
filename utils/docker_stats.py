"""Interrogazione del socket Docker via API HTTP (nessuna dipendenza SDK)."""

from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path

DOCKER_SOCKET = "/var/run/docker.sock"


class _UnixSocketConnection(http.client.HTTPConnection):
    """HTTPConnection che dialoga su un socket unix invece che su TCP."""

    def __init__(self, socket_path: str, timeout: float = 5.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def is_available() -> bool:
    """True se il socket Docker è montato nel container."""
    return Path(DOCKER_SOCKET).exists()


def _get(path: str) -> bytes:
    conn = _UnixSocketConnection(DOCKER_SOCKET)
    try:
        conn.request("GET", path, headers={"Host": "localhost"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"L'API Docker ha risposto {resp.status}")
        return resp.read()
    finally:
        conn.close()


def list_containers(all_containers: bool = True) -> list[dict]:
    """Elenco dei container dall'Engine API (equivalente di 'docker ps -a')."""
    query = "all=1" if all_containers else ""
    raw = _get(f"/containers/json?{query}").decode("utf-8")
    return json.loads(raw)
