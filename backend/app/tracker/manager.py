import asyncio
import html
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import websockets
from sqlalchemy import func, select

from ..db import SessionLocal
from ..models import Death, Event, Room, Slot
from ..realtime import RoomBroadcaster


log = logging.getLogger("ap-tracker.tracker")

RECV_WAKE_SECONDS = 10
HINT_POLL_SECONDS = 3
CHECK_SYNC_SECONDS = 15
IDLE_SLEEP_SECONDS = 110 * 60
RECONNECT_BACKOFF = (2, 5, 10, 20, 30, 60)


class TrackerManager:
    def __init__(self, broadcaster: RoomBroadcaster) -> None:
        self.broadcaster = broadcaster
        self._tasks: dict[int, asyncio.Task] = {}
        self._sockets: dict[int, Any] = {}
        self._packages: dict[int, dict[str, dict[str, dict[int, str]]]] = defaultdict(dict)
        self._sleeping_rooms: set[int] = set()
        self._hint_boost_until: dict[int, float] = {}
        self._room_restarts: dict[int, asyncio.Lock] = {}
        self._recent_events: dict[tuple[int, str], float] = {}

    async def start(self) -> None:
        async with SessionLocal() as db:
            slot_ids = list((await db.scalars(select(Slot.id).where(Slot.archived.is_(False)))).all())
        for slot_id in slot_ids:
            self.ensure_slot(slot_id)

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._sockets.clear()

    def ensure_slot(self, slot_id: int) -> None:
        task = self._tasks.get(slot_id)
        if task and not task.done():
            return
        self._tasks[slot_id] = asyncio.create_task(self._slot_worker(slot_id))

    def stop_slot(self, slot_id: int) -> None:
        task = self._tasks.pop(slot_id, None)
        self._sockets.pop(slot_id, None)
        if task:
            task.cancel()

    async def restart_room(self, room_id: int) -> None:
        self._sleeping_rooms.discard(room_id)
        lock = self._room_restarts.setdefault(room_id, asyncio.Lock())
        async with lock:
            async with SessionLocal() as db:
                slots = list((await db.scalars(select(Slot).where(Slot.room_id == room_id, Slot.archived.is_(False)))).all())
                slot_ids = [slot.id for slot in slots]
                for slot in slots:
                    slot.status = "connecting"
                    slot.error_message = None
                await db.commit()
            for slot_id in slot_ids:
                task = self._tasks.pop(slot_id, None)
                self._sockets.pop(slot_id, None)
                if task:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                self.ensure_slot(slot_id)
        await self.publish_room(room_id)

    async def publish_room(self, room_id: int, event: str = "room.updated") -> None:
        await self.broadcaster.publish(room_id, {"type": event, "room_id": room_id})

    async def send_hint(self, slot_id: int, item_name: str) -> tuple[bool, str]:
        item_name = item_name.strip()
        if not item_name:
            return True, ""
        websocket = self._sockets.get(slot_id)
        if websocket is None:
            return False, "That slot is not currently connected."
        try:
            await websocket.send(json.dumps([{"cmd": "Say", "text": f"!hint {item_name}"}]))
        except Exception as exc:
            return False, str(exc)
        self._hint_boost_until[slot_id] = time.monotonic() + 8
        return True, "Hint request sent."

    async def item_names(self, slot_id: int) -> list[str]:
        async with SessionLocal() as db:
            slot = await db.get(Slot, slot_id)
            if not slot:
                return []
            package = self._packages.get(slot.room_id, {}).get(slot.game or "", {})
        return sorted(package.get("items", {}).values(), key=str.casefold)

    async def _slot_worker(self, slot_id: int) -> None:
        backoff_index = 0
        while True:
            async with SessionLocal() as db:
                slot = await db.get(Slot, slot_id)
                room = await db.get(Room, slot.room_id) if slot else None
                if not slot or slot.archived or not room or room.archived:
                    return
                if room.id in self._sleeping_rooms:
                    return
                host, port, slot_data = room.host, room.port, self._slot_data(slot)
            connected = False
            for scheme in ("wss", "ws"):
                try:
                    async with websockets.connect(
                        f"{scheme}://{host}:{port}",
                        ping_interval=20,
                        ping_timeout=20,
                        open_timeout=10,
                    ) as websocket:
                        connected = await self._run_connection(websocket, slot_id, room.id, slot_data)
                        if connected:
                            backoff_index = 0
                        break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._save_slot(slot_id, status="error", error_message=str(exc))
            async with SessionLocal() as db:
                slot = await db.get(Slot, slot_id)
                if not slot or slot.archived:
                    return
            await asyncio.sleep(RECONNECT_BACKOFF[min(backoff_index, len(RECONNECT_BACKOFF) - 1)])
            backoff_index += 1

    @staticmethod
    def _slot_data(slot: Slot) -> dict[str, Any]:
        return {
            "password": slot.password,
            "slot_name": slot.slot_name,
            "deathlink_listener": slot.deathlink_listener,
        }

    async def _run_connection(
        self,
        websocket: Any,
        slot_id: int,
        room_id: int,
        slot_data: dict[str, Any],
    ) -> bool:
        first = json.loads(await websocket.recv())
        room_info = next((packet for packet in first if packet.get("cmd") == "RoomInfo"), None)
        if not room_info:
            await self._save_slot(slot_id, status="error", error_message="No RoomInfo received")
            return False
        tags = ["Tracker"]
        if slot_data["deathlink_listener"]:
            tags.append("DeathLink")
        await websocket.send(json.dumps([{
            "cmd": "Connect",
            "password": slot_data["password"] or None,
            "game": "",
            "name": slot_data["slot_name"],
            "uuid": str(uuid.uuid4()),
            "version": {"major": 0, "minor": 6, "build": 0, "class": "Version"},
            "items_handling": 0,
            "tags": tags,
            "slot_data": False,
        }]))
        self._sockets[slot_id] = websocket
        checked: set[int] = set()
        slot_info: dict[str, Any] = {}
        team = 0
        slot_number: int | None = None
        game = ""
        last_poll = 0.0
        last_sync = 0.0
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=RECV_WAKE_SECONDS)
                except asyncio.TimeoutError:
                    raw = None
                if raw is not None:
                    for packet in json.loads(raw):
                        command = packet.get("cmd")
                        if command == "ConnectionRefused":
                            await self._save_slot(
                                slot_id,
                                status="error",
                                error_message=", ".join(packet.get("errors", ["connection refused"])),
                            )
                            return False
                        if command == "Connected":
                            team = packet.get("team", 0)
                            slot_number = packet.get("slot")
                            slot_info = packet.get("slot_info", {}) or {}
                            checked = set(packet.get("checked_locations", []))
                            game = slot_info.get(str(slot_number), {}).get("game", "")
                            total = len(checked) + len(packet.get("missing_locations", []))
                            await self._save_slot(
                                slot_id,
                                status="connected",
                                error_message=None,
                                game=game,
                                team=team,
                                slot_number=slot_number,
                                checks_done=len(checked),
                                checks_total=total,
                                hint_points=packet.get("hint_points", 0),
                                client_status=packet.get("client_status", 0),
                                last_seen=datetime.now(timezone.utc),
                            )
                            await self._fetch_packages(websocket, room_id, slot_info)
                            await self._save_locations(slot_id, room_id, game, checked, packet.get("missing_locations", []))
                            await self.publish_room(room_id)
                        elif command == "RoomUpdate":
                            changed = False
                            if "checked_locations" in packet:
                                new_checks = set(packet["checked_locations"])
                                checked = new_checks
                                await self._save_slot(
                                    slot_id,
                                    checks_done=len(checked),
                                    last_seen=datetime.now(timezone.utc),
                                )
                                await self._save_locations(slot_id, room_id, game, checked, [])
                                changed = True
                            if "hint_points" in packet:
                                await self._save_slot(slot_id, hint_points=packet["hint_points"])
                                changed = True
                            if changed:
                                await self.publish_room(room_id)
                        elif command == "Bounce" and "DeathLink" in (packet.get("tags") or []):
                            data = packet.get("data", {}) or {}
                            await self._save_death(room_id, slot_id, data.get("source"), data.get("cause"))
                            await self.publish_room(room_id)
                        elif command == "PrintJSON":
                            if not await self._is_primary(room_id, slot_id):
                                continue
                            text, rendered = self._render_printjson(packet.get("data"), slot_info, room_id)
                            if text.strip():
                                await self._save_event(room_id, packet.get("type", "Text"), text, rendered)
                                await self.publish_room(room_id, "room.event")
                        elif command == "Retrieved":
                            await self._save_retrieved(slot_id, room_id, packet.get("keys", {}), team, slot_number, slot_info)
                async with SessionLocal() as db:
                    room = await db.get(Room, room_id)
                    if room and room.last_activity and time.time() - room.last_activity >= IDLE_SLEEP_SECONDS:
                        self._sleeping_rooms.add(room_id)
                        await self._save_room_slots_sleeping(db, room_id)
                        await db.commit()
                        await self.publish_room(room_id)
                        return False
                now = time.monotonic()
                if slot_number is not None and now - last_sync >= CHECK_SYNC_SECONDS:
                    await websocket.send(json.dumps([{"cmd": "Sync"}]))
                    last_sync = now
                poll_seconds = 1 if now < self._hint_boost_until.get(slot_id, 0) else HINT_POLL_SECONDS
                if slot_number is not None and now - last_poll >= poll_seconds:
                    await websocket.send(json.dumps([{
                        "cmd": "Get",
                        "keys": [f"_read_hints_{team}_{slot_number}", f"_read_client_status_{team}_{slot_number}"],
                    }]))
                    last_poll = now
        finally:
            self._sockets.pop(slot_id, None)
            await self._save_slot(slot_id, status="disconnected")
            await self.publish_room(room_id)

    async def _fetch_packages(self, websocket: Any, room_id: int, slot_info: dict[str, Any]) -> None:
        games = sorted({info.get("game") for info in slot_info.values() if info.get("game")})
        cache = self._packages[room_id]
        needed = [game for game in games if game not in cache]
        if not needed:
            return
        await websocket.send(json.dumps([{"cmd": "GetDataPackage", "games": needed}]))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=deadline - time.monotonic())
            except asyncio.TimeoutError:
                return
            for packet in json.loads(raw):
                if packet.get("cmd") != "DataPackage":
                    continue
                for game, data in packet.get("data", {}).get("games", {}).items():
                    cache[game] = {
                        "items": {int(value): key for key, value in data.get("item_name_to_id", {}).items()},
                        "locations": {int(value): key for key, value in data.get("location_name_to_id", {}).items()},
                    }
                return

    async def _save_locations(
        self,
        slot_id: int,
        room_id: int,
        game: str,
        checked: set[int],
        missing: list[int],
    ) -> None:
        names = self._packages[room_id].get(game, {}).get("locations", {})
        async with SessionLocal() as db:
            slot = await db.get(Slot, slot_id)
            existing = slot.locations if slot and slot.locations else []
        existing_ids = {location["id"] for location in existing}
        ids = set(checked) | set(missing) | existing_ids
        locations = []
        for location_id in ids:
            existing_location = next(
                (location for location in existing if location.get("id") == location_id),
                {},
            )
            locations.append({
                "id": location_id,
                "name": names.get(location_id, existing_location.get("name", f"#{location_id}")),
                "checked": location_id in checked or (
                    existing_location.get("checked", False) and location_id not in missing
                ),
            })
        locations.sort(key=lambda location: location["name"].lower())
        await self._save_slot(slot_id, locations=locations)

    async def _save_retrieved(
        self,
        slot_id: int,
        room_id: int,
        values: dict[str, Any],
        team: int,
        slot_number: int | None,
        slot_info: dict[str, Any],
    ) -> None:
        if slot_number is None:
            return
        hints = values.get(f"_read_hints_{team}_{slot_number}")
        status = values.get(f"_read_client_status_{team}_{slot_number}")
        fields: dict[str, Any] = {}
        if hints is not None:
            fields["hints"] = [self._resolve_hint(hint, slot_info, room_id) for hint in hints]
        if status is not None:
            fields["client_status"] = status
        if fields:
            await self._save_slot(slot_id, **fields)
            await self.publish_room(room_id)

    def _resolve_hint(self, hint: dict[str, Any], slot_info: dict[str, Any], room_id: int) -> dict[str, Any]:
        finding = str(hint.get("finding_player"))
        receiving = str(hint.get("receiving_player"))
        finding_info = slot_info.get(finding, {})
        receiving_info = slot_info.get(receiving, {})
        finding_game = finding_info.get("game", "")
        receiving_game = receiving_info.get("game", "")
        packages = self._packages[room_id]
        location = packages.get(finding_game, {}).get("locations", {}).get(hint.get("location"), f"#{hint.get('location')}")
        item = packages.get(receiving_game, {}).get("items", {}).get(hint.get("item"), f"#{hint.get('item')}")
        return {
            "finding_player": finding_info.get("name", finding),
            "receiving_player": receiving_info.get("name", receiving),
            "finding_game": finding_game,
            "receiving_game": receiving_game,
            "location": location,
            "item": item,
            "key_item": bool(hint.get("item_flags", hint.get("flags", 0)) & 1),
            "found": bool(hint.get("found")),
        }

    def _render_printjson(
        self,
        parts: list[dict[str, Any]] | None,
        slot_info: dict[str, Any],
        room_id: int,
    ) -> tuple[str, str]:
        text_parts: list[str] = []
        html_parts: list[str] = []
        packages = self._packages[room_id]
        for part in parts or []:
            part_type = part.get("type", "text")
            value: Any = part.get("text", "")
            css = ""
            try:
                if part_type == "player_id":
                    value = slot_info.get(str(int(value)), {}).get("name", value)
                    css = "log-player"
                elif part_type == "item_id":
                    game = slot_info.get(str(part.get("player")), {}).get("game", "")
                    value = packages.get(game, {}).get("items", {}).get(int(value), value)
                    css = "log-key" if int(part.get("flags", 0)) & 1 else "log-item"
                elif part_type == "location_id":
                    game = slot_info.get(str(part.get("player")), {}).get("game", "")
                    value = packages.get(game, {}).get("locations", {}).get(int(value), value)
                    css = "log-location"
            except (TypeError, ValueError):
                pass
            text_parts.append(str(value))
            escaped = html.escape(str(value))
            html_parts.append(f'<span class="{css}">{escaped}</span>' if css else escaped)
        return "".join(text_parts), "".join(html_parts)

    async def _save_slot(self, slot_id: int, **fields: Any) -> None:
        async with SessionLocal() as db:
            slot = await db.get(Slot, slot_id)
            if not slot:
                return
            for key, value in fields.items():
                setattr(slot, key, value)
            await self._refresh_room_completion(db, slot.room_id)
            await db.commit()

    @staticmethod
    async def _refresh_room_completion(db: Any, room_id: int) -> None:
        room = await db.get(Room, room_id)
        slots = list((await db.scalars(
            select(Slot).where(Slot.room_id == room_id, Slot.archived.is_(False))
        )).all())
        if not room or not slots or room.game_status in {"completed", "canceled"}:
            return
        completed = all(
            bool(slot.completed_override)
            if slot.completed_override is not None
            else slot.client_status >= 30
            for slot in slots
        )
        new_status = "completed" if completed else "in_progress"
        if room.game_status != new_status:
            room.game_status = new_status
            room.status_changed_at = datetime.now(timezone.utc)

    async def _save_death(self, room_id: int, slot_id: int, source: str | None, cause: str | None) -> None:
        async with SessionLocal() as db:
            db.add(Death(room_id=room_id, slot_id=slot_id, source_name=source, cause=cause, manual=False))
            await db.commit()

    async def _save_event(self, room_id: int, event_type: str, text: str, rendered: str) -> None:
        event_key = (room_id, text)
        now = time.monotonic()
        previous = self._recent_events.get(event_key, 0)
        if now - previous < 3:
            return
        self._recent_events[event_key] = now
        async with SessionLocal() as db:
            db.add(Event(room_id=room_id, event_type=event_type, text=text, html=rendered))
            room = await db.get(Room, room_id)
            if room:
                room.last_activity = time.time()
            await db.commit()

    async def _is_primary(self, room_id: int, slot_id: int) -> bool:
        async with SessionLocal() as db:
            primary_id = await db.scalar(
                select(func.min(Slot.id)).where(
                    Slot.room_id == room_id,
                    Slot.archived.is_(False),
                    Slot.status == "connected",
                )
            )
        return primary_id == slot_id

    async def _save_room_slots_sleeping(self, db: Any, room_id: int) -> None:
        slots = list((await db.scalars(select(Slot).where(Slot.room_id == room_id, Slot.archived.is_(False)))).all())
        for slot in slots:
            slot.status = "sleeping"
            slot.error_message = "Paused after 1h 50m without room activity"
