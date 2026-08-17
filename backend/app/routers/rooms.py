import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import current_user, require_admin, require_user
from ..db import get_db
from ..models import Death, Event, Room, RoomMember, Slot, User
from ..schemas import (
    CompletionRequest,
    EventResponse,
    HintRequest,
    JoinRoomRequest,
    RoomCreateRequest,
    RoomConnectionUpdateRequest,
    RoomResponse,
    RoomStatusRequest,
    RoomStateResponse,
    SlotCreateRequest,
    SlotResponse,
)


router = APIRouter(prefix="/api/v1/rooms", tags=["rooms"])


def new_code(length: int = 12) -> str:
    return secrets.token_urlsafe(length).replace("-", "").replace("_", "")[:length]


async def can_access_room(room: Room, user: User, db: AsyncSession) -> bool:
    if user.role == "admin":
        return True
    return bool(await db.scalar(select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.user_id == user.id)))


async def accessible_room(room_key: str, user: User, db: AsyncSession) -> Room:
    room = await db.scalar(select(Room).where(Room.room_key == room_key, Room.archived.is_(False)))
    if not room or not await can_access_room(room, user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="room not found")
    return room


async def editable_room(room_key: str, user: User, db: AsyncSession) -> Room:
    return await accessible_room(room_key, user, db)


async def slot_state(slot: Slot, auto_deaths: int) -> SlotResponse:
    total = slot.checks_total or 0
    done = slot.checks_done or 0
    completed = bool(slot.completed_override) if slot.completed_override is not None else slot.client_status >= 30
    return SlotResponse(
        id=slot.id,
        slot_name=slot.slot_name,
        game=slot.game,
        status=slot.status,
        error_message=slot.error_message,
        checks_done=done,
        checks_total=total,
        checks_pct=round(done / total * 100, 2) if total else 0.0,
        remaining_checks=max(total - done, 0),
        hint_points=slot.hint_points,
        completed=completed,
        hints=slot.hints or [],
        locations=slot.locations or [],
        auto_deaths=auto_deaths,
        manual_deaths=slot.manual_deaths,
        total_deaths=auto_deaths + slot.manual_deaths,
        status_label={0: "Unknown", 5: "Connected", 10: "Ready", 20: "Playing", 30: "Goal complete"}.get(slot.client_status, "Unknown"),
    )


async def refresh_room_completion(db: AsyncSession, room_id: int) -> bool:
    room = await db.get(Room, room_id)
    slots = list((await db.scalars(
        select(Slot).where(Slot.room_id == room_id, Slot.archived.is_(False))
    )).all())
    if not room or not slots or room.game_status in {"completed", "canceled"}:
        return False
    completed = all(
        bool(slot.completed_override)
        if slot.completed_override is not None
        else slot.client_status >= 30
        for slot in slots
    )
    new_status = "completed" if completed else "in_progress"
    if room.game_status == new_status:
        return False
    if new_status != room.game_status:
        room.game_status = new_status
        room.status_changed_at = datetime.now(timezone.utc)
        return True
    return False


async def build_room_state(db: AsyncSession, room: Room) -> RoomStateResponse:
    slots = list((await db.scalars(
        select(Slot).where(Slot.room_id == room.id, Slot.archived.is_(False)).order_by(Slot.id)
    )).all())
    death_counts = dict(
        (row.slot_id, row.count)
        for row in (await db.execute(
            select(Death.slot_id, func.count(Death.id).label("count"))
            .where(Death.room_id == room.id, Death.manual.is_(False))
            .group_by(Death.slot_id)
        )).all()
    )
    slot_responses = [await slot_state(slot, death_counts.get(slot.id, 0)) for slot in slots]
    completed_count = sum(1 for slot in slot_responses if slot.completed)
    return RoomStateResponse(
        id=room.id,
        label=room.label,
        host=room.host,
        port=room.port,
        game_status=room.game_status,
        room_key=room.room_key,
        invite_code=room.invite_code,
        viewer_code=room.viewer_code,
        sleeping=any(slot.status == "sleeping" for slot in slot_responses),
        totals={
            "checks_done": sum(slot.checks_done for slot in slot_responses),
            "checks_total": sum(slot.checks_total for slot in slot_responses),
            "checks_pct": round(
                sum(slot.checks_done for slot in slot_responses)
                / sum(slot.checks_total for slot in slot_responses)
                * 100,
                2,
            ) if sum(slot.checks_total for slot in slot_responses) else 0.0,
            "completed": completed_count,
            "deaths": sum(slot.total_deaths for slot in slot_responses),
        },
        slots=slot_responses,
    )


@router.get("", response_model=list[RoomResponse])
async def list_rooms(user: User | None = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[Room]:
    if not user:
        return []
    query = select(Room).where(Room.archived.is_(False)).options(selectinload(Room.slots)).order_by(Room.id.desc())
    if user.role != "admin":
        query = query.join(RoomMember).where(RoomMember.user_id == user.id)
    rooms = list((await db.scalars(query)).unique().all())
    summaries = []
    for room in rooms:
        slots = [slot for slot in room.slots if not slot.archived]
        summaries.append(RoomResponse.model_validate(room).model_copy(update={
            "players": len(slots),
            "checks_done": sum(slot.checks_done for slot in slots),
            "checks_total": sum(slot.checks_total for slot in slots),
            "checks_pct": round(
                sum(slot.checks_done for slot in slots)
                / sum(slot.checks_total for slot in slots)
                * 100,
                2,
            ) if sum(slot.checks_total for slot in slots) else 0.0,
            "player_names": [slot.slot_name for slot in slots],
        }))
    return summaries


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreateRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Room:
    room = Room(
        label=payload.label.strip(),
        host=payload.host.strip(),
        port=payload.port,
        owner_id=user.id,
        room_key=new_code(24),
        invite_code=new_code(),
        viewer_code=new_code(),
    )
    db.add(room)
    await db.flush()
    db.add(RoomMember(user_id=user.id, room_id=room.id))
    await db.commit()
    await db.refresh(room)
    return room


@router.post("/join", response_model=RoomResponse)
async def join_room(
    payload: JoinRoomRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Room:
    room = await db.scalar(
        select(Room).where(Room.invite_code == payload.invite_code, Room.archived.is_(False))
    )
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite code not found")
    existing = await db.scalar(select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.user_id == user.id))
    if not existing:
        db.add(RoomMember(user_id=user.id, room_id=room.id))
        await db.commit()
    return room


@router.get("/{room_key}", response_model=RoomResponse)
async def get_room(
    room_key: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Room:
    room = await db.scalar(select(Room).options(selectinload(Room.slots)).where(Room.room_key == room_key, Room.archived.is_(False)))
    if not room or not await can_access_room(room, user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="room not found")
    return room


@router.put("/{room_key}/connection", response_model=RoomResponse)
async def update_room_connection(
    room_key: str,
    payload: RoomConnectionUpdateRequest,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Room:
    room = await editable_room(room_key, user, db)
    host = payload.host.strip()
    if not host:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="host must not be blank")
    room.host = host
    room.port = payload.port
    await db.commit()
    await db.refresh(room)
    await request.app.state.tracker.restart_room(room.id)
    return room


@router.get("/{room_key}/state", response_model=RoomStateResponse)
async def room_state(
    room_key: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> RoomStateResponse:
    room = await accessible_room(room_key, user, db)
    await refresh_room_completion(db, room.id)
    await db.commit()
    return await build_room_state(db, room)


@router.post("/{room_key}/slots", response_model=SlotResponse, status_code=status.HTTP_201_CREATED)
async def add_slot(
    room_key: str,
    payload: SlotCreateRequest,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SlotResponse:
    room = await editable_room(room_key, user, db)
    if payload.deathlink_listener:
        await db.execute(
            Slot.__table__.update().where(Slot.room_id == room.id).values(deathlink_listener=False)
        )
    slot = Slot(
        room_id=room.id,
        slot_name=payload.slot_name.strip(),
        password=payload.password or None,
        deathlink_listener=payload.deathlink_listener,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    request.app.state.tracker.ensure_slot(slot.id)
    await request.app.state.tracker.publish_room(room.id)
    return await slot_state(slot, 0)


@router.delete("/{room_key}/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_slot(
    room_key: str,
    slot_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    room = await editable_room(room_key, user, db)
    slot = await db.scalar(select(Slot).where(Slot.id == slot_id, Slot.room_id == room.id))
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slot not found")
    request.app.state.tracker.stop_slot(slot.id)
    await db.delete(slot)
    await db.commit()
    await request.app.state.tracker.publish_room(room.id)


@router.post("/{room_key}/slots/{slot_id}/death", response_model=SlotResponse)
async def add_death(
    room_key: str,
    slot_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SlotResponse:
    room = await editable_room(room_key, user, db)
    slot = await db.scalar(select(Slot).where(Slot.id == slot_id, Slot.room_id == room.id))
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slot not found")
    slot.manual_deaths += 1
    db.add(Death(room_id=room.id, slot_id=slot.id, source_name=slot.slot_name, cause="manual", manual=True))
    await db.commit()
    await db.refresh(slot)
    auto_deaths = await db.scalar(select(func.count(Death.id)).where(Death.slot_id == slot.id, Death.manual.is_(False)))
    await request.app.state.tracker.publish_room(room.id)
    return await slot_state(slot, auto_deaths or 0)


@router.get("/{room_key}/events", response_model=list[EventResponse])
async def room_events(
    room_key: str,
    after_id: int = 0,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[Event]:
    room = await accessible_room(room_key, user, db)
    events = (await db.scalars(
        select(Event)
        .where(Event.room_id == room.id, Event.id > after_id)
        .order_by(Event.id)
        .limit(200)
    )).all()
    return list(events)


@router.post("/{room_key}/slots/{slot_id}/death/undo", response_model=SlotResponse)
async def undo_death(
    room_key: str,
    slot_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SlotResponse:
    room = await editable_room(room_key, user, db)
    slot = await db.scalar(select(Slot).where(Slot.id == slot_id, Slot.room_id == room.id))
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slot not found")
    if slot.manual_deaths:
        slot.manual_deaths -= 1
        latest = await db.scalar(
            select(Death).where(Death.slot_id == slot.id, Death.manual.is_(True)).order_by(Death.id.desc())
        )
        if latest:
            await db.delete(latest)
    await db.commit()
    await db.refresh(slot)
    auto_deaths = await db.scalar(select(func.count(Death.id)).where(Death.slot_id == slot.id, Death.manual.is_(False)))
    await request.app.state.tracker.publish_room(room.id)
    return await slot_state(slot, auto_deaths or 0)


@router.post("/{room_key}/slots/{slot_id}/complete", response_model=SlotResponse)
async def set_complete(
    room_key: str,
    slot_id: int,
    payload: CompletionRequest,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SlotResponse:
    room = await editable_room(room_key, user, db)
    slot = await db.scalar(select(Slot).where(Slot.id == slot_id, Slot.room_id == room.id))
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slot not found")
    slot.completed_override = payload.value
    await refresh_room_completion(db, room.id)
    await db.commit()
    await db.refresh(slot)
    auto_deaths = await db.scalar(select(func.count(Death.id)).where(Death.slot_id == slot.id, Death.manual.is_(False)))
    await request.app.state.tracker.publish_room(room.id)
    return await slot_state(slot, auto_deaths or 0)


@router.post("/{room_key}/slots/{slot_id}/hint")
async def send_hint(
    room_key: str,
    slot_id: int,
    payload: HintRequest,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    room = await editable_room(room_key, user, db)
    slot = await db.scalar(select(Slot).where(Slot.id == slot_id, Slot.room_id == room.id, Slot.archived.is_(False)))
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slot not found")
    if not payload.item_name.strip():
        return {"message": ""}
    sent, message = await request.app.state.tracker.send_hint(slot.id, payload.item_name)
    if not sent:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return {"message": message}


@router.post("/{room_key}/status", response_model=RoomResponse)
async def set_room_status(
    room_key: str,
    payload: RoomStatusRequest,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Room:
    room = await editable_room(room_key, user, db)
    room.game_status = payload.status
    room.status_changed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(room)
    await request.app.state.tracker.publish_room(room.id)
    return room


@router.post("/{room_key}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_room(
    room_key: str,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    room = await editable_room(room_key, user, db)
    room.archived = True
    await db.commit()
    await request.app.state.tracker.restart_room(room.id)


@router.delete("/{room_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_key: str,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    room = await editable_room(room_key, user, db)
    await request.app.state.tracker.restart_room(room.id)
    await db.delete(room)
    await db.commit()


@router.get("/{room_key}/slots/{slot_id}/item-names", response_model=list[str])
async def item_names(
    room_key: str,
    slot_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    room = await accessible_room(room_key, user, db)
    slot = await db.scalar(select(Slot).where(
        Slot.id == slot_id,
        Slot.room_id == room.id,
        Slot.archived.is_(False),
    ))
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slot not found")
    return await request.app.state.tracker.item_names(slot.id)


@router.post("/{room_key}/reconnect", status_code=status.HTTP_202_ACCEPTED)
async def reconnect_room(
    room_key: str,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    room = await editable_room(room_key, user, db)
    await request.app.state.tracker.restart_room(room.id)
    return {"message": "reconnect requested"}
