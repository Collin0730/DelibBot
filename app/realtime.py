"""In-process WebSocket hub: one room per deliberation.

Good for a single web instance (the Railway default). To scale out, swap the
dict for Redis pub/sub; nothing else needs to change.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass(eq=False)
class Conn:
    ws: WebSocket
    role: str
    participant_id: str | None
    name: str


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, set[Conn]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def join(self, room: str, conn: Conn) -> None:
        self.rooms.setdefault(room, set()).add(conn)

    def leave(self, room: str, conn: Conn) -> None:
        self.rooms.get(room, set()).discard(conn)

    def online(self, room: str) -> list[str]:
        return sorted({c.participant_id for c in self.rooms.get(room, set()) if c.participant_id})

    async def _send(self, room: str, event: dict, only_participant: str | None, staff_only: bool) -> None:
        for c in list(self.rooms.get(room, set())):
            if only_participant and c.participant_id != only_participant:
                continue
            if staff_only and c.role == "participant":
                continue
            try:
                await c.ws.send_json(event)
            except Exception:  # noqa: BLE001 - a dead socket is cleaned up by its own handler
                self.leave(room, c)

    def publish(self, room, event: dict, only_participant=None, staff_only: bool = False) -> None:
        """Safe to call from any thread, including background jobs."""
        if not self.loop:
            return
        coro = self._send(str(room), event, str(only_participant) if only_participant else None, staff_only)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            running.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, self.loop)


hub = Hub()
jobs = ThreadPoolExecutor(max_workers=6, thread_name_prefix="job")
