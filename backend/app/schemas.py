from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    created_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=4, max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str


class RoomCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    host: str
    port: int
    game_status: str
    room_key: str
    invite_code: str
    viewer_code: str
    players: int = 0
    checks_done: int = 0
    checks_total: int = 0
    checks_pct: float = 0
    player_names: list[str] = Field(default_factory=list)


class RoomStatusRequest(BaseModel):
    status: Literal["in_progress", "completed", "canceled"]


class ViewerSlotResponse(BaseModel):
    id: int
    slot_name: str
    game: str | None
    checks_done: int
    checks_total: int
    checks_pct: float
    remaining_checks: int
    completed: bool
    hints: list[dict]
    locations: list[dict]
    total_deaths: int


class ViewerRoomStateResponse(BaseModel):
    id: int
    label: str
    game_status: str
    room_key: str
    sleeping: bool
    totals: dict[str, float]
    slots: list[ViewerSlotResponse]


class JoinRoomRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=64)


class SlotCreateRequest(BaseModel):
    slot_name: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    deathlink_listener: bool = False


class CompletionRequest(BaseModel):
    value: bool | None


class HintRequest(BaseModel):
    item_name: str = Field(default="", max_length=255)


class SlotResponse(BaseModel):
    id: int
    slot_name: str
    game: str | None
    status: str
    error_message: str | None
    checks_done: int
    checks_total: int
    checks_pct: float
    remaining_checks: int
    hint_points: int
    completed: bool
    hints: list[dict]
    locations: list[dict]
    auto_deaths: int
    manual_deaths: int
    total_deaths: int
    status_label: str


class RoomStateResponse(RoomResponse):
    sleeping: bool
    totals: dict[str, float]
    slots: list[SlotResponse]


class EventResponse(BaseModel):
    id: int
    event_type: str | None
    text: str
    html: str | None
    ts: datetime


class PlayerBoxPreferences(BaseModel):
    order: list[str]
    visible: list[str]
