"""In-process pub/sub so a change in the command centre reaches running apps.

Write handlers are ordinary sync functions, which FastAPI runs on a worker
thread, while subscribers wait on the event loop. So publishing hops back onto
the loop with `call_soon_threadsafe` rather than touching the queues directly.

Publishing never blocks on a slow reader: a full queue drops the notification,
and the reader catches up on its next poll because every payload carries the
current config version.
"""

import asyncio
from collections import defaultdict
from typing import Any

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at startup so worker threads know where to deliver."""
    global _loop
    _loop = loop


def subscribe(channel: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=16)
    _subscribers[channel].add(queue)
    return queue


def unsubscribe(channel: str, queue: asyncio.Queue) -> None:
    _subscribers[channel].discard(queue)
    if not _subscribers[channel]:
        _subscribers.pop(channel, None)


def _deliver(channel: str, payload: dict[str, Any]) -> None:
    for queue in list(_subscribers.get(channel, ())):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def publish(channel: str, payload: dict[str, Any]) -> None:
    if _loop is None or _loop.is_closed():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _deliver(channel, payload)
    else:
        _loop.call_soon_threadsafe(_deliver, channel, payload)


def listener_count(channel: str) -> int:
    return len(_subscribers.get(channel, ()))
