import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from .db import SessionLocal
from .models import Room


async def delete_expired_rooms() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with SessionLocal() as db:
        await db.execute(delete(Room).where(
            Room.game_status.in_(["completed", "canceled"]),
            Room.status_changed_at < cutoff,
        ))
        await db.commit()


async def retention_loop() -> None:
    while True:
        await delete_expired_rooms()
        await asyncio.sleep(3600)
