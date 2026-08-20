import asyncio
from collections import defaultdict

from fastapi import WebSocket


class RoomBroadcaster:
    def __init__(self) -> None:
        self._clients: dict[int, dict[WebSocket, asyncio.Queue[dict]]] = defaultdict(dict)
        self._send_tasks: dict[WebSocket, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=8)
        async with self._lock:
            self._clients[room_id][websocket] = queue
            self._send_tasks[websocket] = asyncio.create_task(self._send_loop(websocket, queue))

    async def disconnect(self, room_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._clients.get(room_id)
            if not clients:
                return
            clients.pop(websocket, None)
            if not clients:
                self._clients.pop(room_id, None)
            task = self._send_tasks.pop(websocket, None)
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def publish(self, room_id: int, message: dict) -> None:
        async with self._lock:
            queues = list(self._clients.get(room_id, {}).items())
        for websocket, queue in queues:
            # The websocket is an invalidation channel; a newer message makes
            # older refresh messages redundant. Never let a slow browser
            # block tracker/database work or grow memory without a bound.
            if queue.full():
                try:
                    while True:
                        queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                await self.disconnect(room_id, websocket)

    async def _send_loop(self, websocket: WebSocket, queue: asyncio.Queue[dict]) -> None:
        try:
            while True:
                await websocket.send_json(await queue.get())
        except asyncio.CancelledError:
            raise
        except Exception:
            # The receive loop owns the websocket lifecycle. Removing the
            # sender here prevents a dead client from receiving future work.
            async with self._lock:
                self._send_tasks.pop(websocket, None)
                for room_id, clients in list(self._clients.items()):
                    clients.pop(websocket, None)
                    if not clients:
                        self._clients.pop(room_id, None)
            try:
                await websocket.close()
            except Exception:
                pass
