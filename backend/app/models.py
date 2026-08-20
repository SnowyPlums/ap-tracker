from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["RoomMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    preferences: Mapped["UserPreference | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    game_status: Mapped[str] = mapped_column(String(20), default="in_progress")
    last_activity: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    room_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    viewer_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    slots: Mapped[list["Slot"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    members: Mapped[list["RoomMember"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    deaths: Mapped[list["Death"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    hints: Mapped[list["Hint"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    hint_requests: Mapped[list["HintRequest"]] = relationship(back_populates="room", cascade="all, delete-orphan")


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (Index("ix_room_members_room_id_user_id", "room_id", "user_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="memberships")
    room: Mapped[Room] = relationship(back_populates="members")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    player_boxes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {"order": ["checks", "hints", "deaths", "completion", "actions"], "visible": ["checks", "hints"]},
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="preferences")


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    slot_name: Mapped[str] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(String(255))
    game: Mapped[str | None] = mapped_column(String(255))
    team: Mapped[int] = mapped_column(Integer, default=0)
    slot_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="connecting")
    error_message: Mapped[str | None] = mapped_column(Text)
    checks_done: Mapped[int] = mapped_column(Integer, default=0)
    checks_total: Mapped[int] = mapped_column(Integer, default=0)
    hint_points: Mapped[int] = mapped_column(Integer, default=0)
    client_status: Mapped[int] = mapped_column(Integer, default=0)
    completed_override: Mapped[bool | None] = mapped_column(Boolean)
    deathlink_listener: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_deaths: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    room: Mapped[Room] = relationship(back_populates="slots")
    deaths: Mapped[list["Death"]] = relationship(back_populates="slot")
    hint_links: Mapped[list["SlotHint"]] = relationship(back_populates="slot", cascade="all, delete-orphan")
    location_rows: Mapped[list["SlotLocation"]] = relationship(back_populates="slot", cascade="all, delete-orphan")
    found_hints: Mapped[list["Hint"]] = relationship(
        foreign_keys="Hint.finder_slot_id", back_populates="finder_slot"
    )
    received_hints: Mapped[list["Hint"]] = relationship(
        foreign_keys="Hint.receiver_slot_id", back_populates="receiver_slot"
    )


class Hint(Base):
    __tablename__ = "hints"
    __table_args__ = (
        Index("ix_hints_room_id_id", "room_id", "id"),
        UniqueConstraint("room_id", "external_key", name="uq_hints_room_external_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    external_key: Mapped[str] = mapped_column(String(255))
    team: Mapped[int] = mapped_column(Integer, default=0)
    finder_slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id", ondelete="SET NULL"), index=True)
    receiver_slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id", ondelete="SET NULL"), index=True)
    finding_player: Mapped[int] = mapped_column(Integer)
    receiving_player: Mapped[int] = mapped_column(Integer)
    location_id: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(Integer)
    item_flags: Mapped[int] = mapped_column(Integer, default=0)
    finding_player_name: Mapped[str] = mapped_column(String(255), default="")
    receiving_player_name: Mapped[str] = mapped_column(String(255), default="")
    finding_game: Mapped[str] = mapped_column(String(255), default="")
    receiving_game: Mapped[str] = mapped_column(String(255), default="")
    location_name: Mapped[str] = mapped_column(String(255), default="")
    item_name: Mapped[str] = mapped_column(String(255), default="")
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    origin: Mapped[str] = mapped_column(String(20), default="automatic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(back_populates="hints")
    finder_slot: Mapped[Slot | None] = relationship(
        foreign_keys=[finder_slot_id], back_populates="found_hints"
    )
    receiver_slot: Mapped[Slot | None] = relationship(
        foreign_keys=[receiver_slot_id], back_populates="received_hints"
    )
    slot_links: Mapped[list["SlotHint"]] = relationship(back_populates="hint", cascade="all, delete-orphan")


class SlotHint(Base):
    __tablename__ = "slot_hints"
    __table_args__ = (
        Index("ix_slot_hints_slot_id_favorite_id", "slot_id", "favorite", "hint_id"),
    )

    hint_id: Mapped[int] = mapped_column(ForeignKey("hints.id", ondelete="CASCADE"), primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    hint: Mapped[Hint] = relationship(back_populates="slot_links")
    slot: Mapped[Slot] = relationship(back_populates="hint_links")


class SlotLocation(Base):
    __tablename__ = "slot_locations"
    __table_args__ = (
        Index("ix_slot_locations_slot_id_checked_id", "slot_id", "checked", "location_id"),
    )

    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True)
    location_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    checked: Mapped[bool] = mapped_column(Boolean, default=False)

    slot: Mapped[Slot] = relationship(back_populates="location_rows")


class HintRequest(Base):
    __tablename__ = "hint_requests"
    __table_args__ = (Index("ix_hint_requests_room_id_created_at", "room_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    requester_slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id", ondelete="CASCADE"), index=True)
    item_name: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    matched_hint_id: Mapped[int | None] = mapped_column(ForeignKey("hints.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(back_populates="hint_requests")


class Death(Base):
    __tablename__ = "deaths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id", ondelete="SET NULL"), index=True)
    source_name: Mapped[str | None] = mapped_column(String(255))
    cause: Mapped[str | None] = mapped_column(Text)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(back_populates="deaths")
    slot: Mapped[Slot | None] = relationship(back_populates="deaths")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_room_id_id", "room_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    event_type: Mapped[str | None] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room: Mapped[Room] = relationship(back_populates="events")
