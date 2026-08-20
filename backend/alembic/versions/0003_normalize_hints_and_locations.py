"""Store hints, favorites, and locations in normalized tables."""

from alembic import op
import sqlalchemy as sa


revision = "0003_normalized_hints"
down_revision = "0002_room_status_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_room_members_room_id_user_id", "room_members", ["room_id", "user_id"])
    op.add_column("rooms", sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "hints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=False),
        sa.Column("team", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finder_slot_id", sa.Integer(), sa.ForeignKey("slots.id", ondelete="SET NULL")),
        sa.Column("receiver_slot_id", sa.Integer(), sa.ForeignKey("slots.id", ondelete="SET NULL")),
        sa.Column("finding_player", sa.Integer(), nullable=False),
        sa.Column("receiving_player", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_flags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finding_player_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("receiving_player_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("finding_game", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("receiving_game", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("location_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("item_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("found", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="automatic"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("room_id", "external_key", name="uq_hints_room_external_key"),
    )
    op.create_index("ix_hints_room_id", "hints", ["room_id"])
    op.create_index("ix_hints_room_id_id", "hints", ["room_id", "id"])
    op.create_index("ix_hints_finder_slot_id", "hints", ["finder_slot_id"])
    op.create_index("ix_hints_receiver_slot_id", "hints", ["receiver_slot_id"])

    op.create_table(
        "slot_hints",
        sa.Column("hint_id", sa.Integer(), sa.ForeignKey("hints.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_slot_hints_slot_id_favorite_id", "slot_hints", ["slot_id", "favorite", "hint_id"])

    op.create_table(
        "slot_locations",
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("slots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_slot_locations_slot_id_checked_id", "slot_locations", ["slot_id", "checked", "location_id"])

    op.create_table(
        "hint_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_slot_id", sa.Integer(), sa.ForeignKey("slots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matched_hint_id", sa.Integer(), sa.ForeignKey("hints.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_hint_requests_room_id", "hint_requests", ["room_id"])
    op.create_index("ix_hint_requests_requester_slot_id", "hint_requests", ["requester_slot_id"])
    op.create_index("ix_hint_requests_room_id_created_at", "hint_requests", ["room_id", "created_at"])

    # Staging is intentionally disposable, so the old denormalized values are
    # removed instead of being copied into a format that cannot preserve the
    # per-slot favorite state correctly.
    op.drop_column("slots", "hints")
    op.drop_column("slots", "locations")


def downgrade() -> None:
    op.add_column("slots", sa.Column("locations", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("slots", sa.Column("hints", sa.JSON(), nullable=False, server_default="[]"))
    op.drop_index("ix_hint_requests_room_id_created_at", table_name="hint_requests")
    op.drop_index("ix_hint_requests_requester_slot_id", table_name="hint_requests")
    op.drop_index("ix_hint_requests_room_id", table_name="hint_requests")
    op.drop_table("hint_requests")
    op.drop_index("ix_slot_locations_slot_id_checked_id", table_name="slot_locations")
    op.drop_table("slot_locations")
    op.drop_index("ix_slot_hints_slot_id_favorite_id", table_name="slot_hints")
    op.drop_table("slot_hints")
    op.drop_index("ix_hints_receiver_slot_id", table_name="hints")
    op.drop_index("ix_hints_finder_slot_id", table_name="hints")
    op.drop_index("ix_hints_room_id_id", table_name="hints")
    op.drop_index("ix_hints_room_id", table_name="hints")
    op.drop_table("hints")
    op.drop_column("rooms", "state_version")
    op.drop_index("ix_room_members_room_id_user_id", table_name="room_members")
