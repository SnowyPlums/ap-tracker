"""Track room status age for automatic cleanup."""

from alembic import op
import sqlalchemy as sa


revision = "0002_room_status_retention"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("rooms", "status_changed_at")
