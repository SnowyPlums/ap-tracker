from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Death, Event, Room, Slot
from ..schemas import EventResponse, ViewerRoomStateResponse, ViewerSlotResponse
from .rooms import slot_state


router = APIRouter(prefix="/api/v1/view", tags=["viewer"])


async def viewer_room(code: str, db: AsyncSession) -> Room:
    room = await db.scalar(select(Room).where(Room.viewer_code == code, Room.archived.is_(False)))
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="viewer link not found")
    return room


async def build_viewer_state(room: Room, db: AsyncSession) -> ViewerRoomStateResponse:
    slots = list((await db.scalars(
        select(Slot).where(Slot.room_id == room.id, Slot.archived.is_(False)).order_by(Slot.id)
    )).all())
    auto_deaths = dict((row.slot_id, row.count) for row in (await db.execute(
        select(Death.slot_id, func.count(Death.id).label("count"))
        .where(Death.room_id == room.id, Death.manual.is_(False))
        .group_by(Death.slot_id)
    )).all())
    result = []
    for slot in slots:
        state = await slot_state(slot, auto_deaths.get(slot.id, 0))
        result.append(ViewerSlotResponse(
            id=state.id,
            slot_name=state.slot_name,
            game=state.game,
            checks_done=state.checks_done,
            checks_total=state.checks_total,
            checks_pct=state.checks_pct,
            remaining_checks=state.remaining_checks,
            completed=state.completed,
            hints=state.hints,
            locations=state.locations,
            total_deaths=state.total_deaths,
        ))
    return ViewerRoomStateResponse(
        id=room.id,
        label=room.label,
        game_status=room.game_status,
        room_key=room.room_key,
        sleeping=any(slot.status == "sleeping" for slot in slots),
        totals={
            "checks_done": sum(slot.checks_done for slot in result),
            "checks_total": sum(slot.checks_total for slot in result),
            "checks_pct": round(
                sum(slot.checks_done for slot in result)
                / sum(slot.checks_total for slot in result)
                * 100,
                2,
            ) if sum(slot.checks_total for slot in result) else 0.0,
            "completed": sum(1 for slot in result if slot.completed),
            "deaths": sum(slot.total_deaths for slot in result),
        },
        slots=result,
    )


@router.get("/{viewer_code}", response_model=ViewerRoomStateResponse)
async def view_room(viewer_code: str, db: AsyncSession = Depends(get_db)) -> ViewerRoomStateResponse:
    room = await viewer_room(viewer_code, db)
    return await build_viewer_state(room, db)


@router.get("/{viewer_code}/events", response_model=list[EventResponse])
async def viewer_events(viewer_code: str, after_id: int = 0, db: AsyncSession = Depends(get_db)) -> list[Event]:
    room = await viewer_room(viewer_code, db)
    events = (await db.scalars(
        select(Event).where(Event.room_id == room.id, Event.id > after_id).order_by(Event.id).limit(200)
    )).all()
    return list(events)
