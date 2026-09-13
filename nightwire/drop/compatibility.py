"""Temporary Drop-facing facades for clipboard and client-presence behavior."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, MutableMapping
from typing import Any


class DropClipboardService:
    def __init__(self, **operations: Callable[..., Any]):
        self._operations = operations

    def snapshot(self, *args, **kwargs):
        return self._operations["snapshot"](*args, **kwargs)

    def share(self, *args, **kwargs):
        return self._operations["share"](*args, **kwargs)

    def update(self, *args, **kwargs):
        return self._operations["update"](*args, **kwargs)

    def unlock(self, *args, **kwargs):
        return self._operations["unlock"](*args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._operations["delete"](*args, **kwargs)

    def clear(self, *args, **kwargs):
        return self._operations["clear"](*args, **kwargs)


class DropClientVisibilityService:
    def __init__(
        self,
        *,
        records: MutableMapping[str, dict[str, Any]],
        lock: threading.RLock,
        ttl_seconds: int,
        timestamp: Callable[[float | None], str],
        server_record: Callable[[int], dict[str, Any]],
    ):
        self.records = records
        self.lock = lock
        self.ttl_seconds = ttl_seconds
        self.timestamp = timestamp
        self.server_record = server_record

    def purge(self, now: float | None = None) -> None:
        current = time.time() if now is None else now
        stale = [
            client_id
            for client_id, record in self.records.items()
            if current - record["last_seen_epoch"] > self.ttl_seconds
        ]
        for client_id in stale:
            self.records.pop(client_id, None)

    def list_devices(self, port: int):
        with self.lock:
            self.purge()
            clients = [dict(record) for record in self.records.values()]
        clients.sort(key=lambda record: (record["connected_at"], record["ip_address"], record["id"]))
        for record in clients:
            record.pop("last_seen_epoch", None)
        return [self.server_record(port), *clients]

    def heartbeat(
        self,
        client_id: str,
        client_host: str,
        agent: dict[str, Any],
        now: float | None = None,
    ) -> None:
        current = time.time() if now is None else now
        with self.lock:
            self.purge(current)
            previous = self.records.get(client_id)
            connected_at = previous["connected_at"] if previous else self.timestamp(current)
            self.records[client_id] = {
                "id": client_id,
                "role": "client",
                "name": agent["device"],
                "status": "online",
                "ip_address": client_host,
                "ip_addresses": [client_host],
                "primary_ip": client_host,
                "connected_at": connected_at,
                "last_seen": self.timestamp(current),
                "last_seen_epoch": current,
                **agent,
            }


__all__ = ["DropClientVisibilityService", "DropClipboardService"]
