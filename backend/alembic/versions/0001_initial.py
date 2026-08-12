"""Create the initial PostgreSQL schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("game_status", sa.String(length=20), nullable=False, server_default="in_progress"),
        sa.Column("last_activity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("room_key", sa.String(length=32), nullable=False),
        sa.Column("invite_code", sa.String(length=32), nullable=False),
        sa.Column("viewer_code", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("room_key"),
        sa.UniqueConstraint("invite_code"),
        sa.UniqueConstraint("viewer_code"),
    )
    op.create_index("ix_rooms_archived", "rooms", ["archived"])
    op.create_index("ix_rooms_room_key", "rooms", ["room_key"])
    op.create_index("ix_rooms_invite_code", "rooms", ["invite_code"])
    op.create_index("ix_rooms_viewer_code", "rooms", ["viewer_code"])

    op.create_table(
        "room_members",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "player_boxes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("""'{"order":["checks","hints","deaths","completion","actions"],"visible":["checks","hints"]}'::jsonb"""),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_name", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255)),
        sa.Column("game", sa.String(length=255)),
        sa.Column("team", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("slot_number", sa.Integer()),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="connecting"),
        sa.Column("error_message", sa.Text()),
        sa.Column("checks_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checks_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hint_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_override", sa.Boolean()),
        sa.Column("hints", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("locations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("deathlink_listener", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("manual_deaths", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_slots_room_id", "slots", ["room_id"])

    op.create_table(
        "deaths",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("slots.id", ondelete="SET NULL")),
        sa.Column("source_name", sa.String(length=255)),
        sa.Column("cause", sa.Text()),
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_deaths_room_id", "deaths", ["room_id"])
    op.create_index("ix_deaths_slot_id", "deaths", ["slot_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("html", sa.Text()),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_events_room_id_id", "events", ["room_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_events_room_id_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_deaths_slot_id", table_name="deaths")
    op.drop_index("ix_deaths_room_id", table_name="deaths")
    op.drop_table("deaths")
    op.drop_index("ix_slots_room_id", table_name="slots")
    op.drop_table("slots")
    op.drop_table("user_preferences")
    op.drop_table("room_members")
    op.drop_index("ix_rooms_viewer_code", table_name="rooms")
    op.drop_index("ix_rooms_invite_code", table_name="rooms")
    op.drop_index("ix_rooms_room_key", table_name="rooms")
    op.drop_index("ix_rooms_archived", table_name="rooms")
    op.drop_table("rooms")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
