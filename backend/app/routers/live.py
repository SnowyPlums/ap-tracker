from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Room, RoomMember, User
from ..routers.viewer import viewer_room


router = APIRouter()


@router.websocket("/ws/rooms/{room_key}")
async def room_stream(websocket: WebSocket, room_key: str) -> None:
    user_id = websocket.scope.get("session", {}).get("user_id")
    if not user_id:
        await websocket.close(code=1008)
        return
    async with SessionLocal() as db:
        user = await db.get(User, int(user_id))
        room = await db.scalar(select(Room).where(Room.room_key == room_key, Room.archived.is_(False)))
        member = await db.scalar(
            select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.user_id == user.id)
        ) if room and user and user.role != "admin" else True
    if not user or not room or not member:
        await websocket.close(code=1008)
        return
    broadcaster = websocket.app.state.broadcaster
    await broadcaster.connect(room.id, websocket)
    await websocket.send_json({"type": "room.connected", "room_id": room.id})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(room.id, websocket)


@router.websocket("/ws/view/{viewer_code}")
async def viewer_stream(websocket: WebSocket, viewer_code: str) -> None:
    try:
        async with SessionLocal() as db:
            room = await viewer_room(viewer_code, db)
    except HTTPException:
        await websocket.close(code=1008)
        return
    broadcaster = websocket.app.state.broadcaster
    await broadcaster.connect(room.id, websocket)
    await websocket.send_json({"type": "room.connected", "room_id": room.id, "viewer": True})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(room.id, websocket)
