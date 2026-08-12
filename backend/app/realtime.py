import asyncio
from collections import defaultdict

from fastapi import WebSocket


class RoomBroadcaster:
    def __init__(self) -> None:
        self._clients: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, room_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients[room_id].add(websocket)

    async def disconnect(self, room_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._clients.get(room_id)
            if not clients:
                return
            clients.discard(websocket)
            if not clients:
                self._clients.pop(room_id, None)

    async def publish(self, room_id: int, message: dict) -> None:
        async with self._lock:
            clients = list(self._clients.get(room_id, set()))
        if not clients:
            return
        results = await asyncio.gather(
            *(client.send_json(message) for client in clients),
            return_exceptions=True,
        )
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                await self.disconnect(room_id, client)
