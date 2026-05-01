from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from .models import JsonDict, now_iso


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[JsonDict]] = set()

    def publish(self, event_type: str, **payload: object) -> None:
        event: JsonDict = {
            "type": event_type,
            "timestamp": now_iso(),
            "payload": payload,
        }
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def subscribe_queue(self) -> asyncio.Queue[JsonDict]:
        queue: asyncio.Queue[JsonDict] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe_queue(self, queue: asyncio.Queue[JsonDict]) -> None:
        self._subscribers.discard(queue)

    async def subscribe(self) -> AsyncIterator[JsonDict]:
        queue: asyncio.Queue[JsonDict] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


def format_sse(event: JsonDict) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
