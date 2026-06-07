"""add location change requests

Revision ID: f2b1a7c9d4e6
Revises: 21591b024328
Create Date: 2026-06-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b1a7c9d4e6"
down_revision: str | None = "21591b024328"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column(
            "change_type",
            sa.Enum(
                "CREATE",
                "UPDATE",
                name="location_change_request_type",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "MERGED",
                "REJECTED",
                "CANCELLED",
                name="location_change_request_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("original_snapshot", sa.JSON(), nullable=True),
        sa.Column("original_location_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_location_id", sa.Integer(), nullable=True),
        sa.Column("merged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["merged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["merged_location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("location_change_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_location_change_requests_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_location_change_requests_location_id"),
            ["location_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_location_change_requests_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_location_change_requests_status_type",
            ["status", "change_type"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("location_change_requests", schema=None) as batch_op:
        batch_op.drop_index("ix_location_change_requests_status_type")
        batch_op.drop_index(batch_op.f("ix_location_change_requests_status"))
        batch_op.drop_index(batch_op.f("ix_location_change_requests_location_id"))
        batch_op.drop_index(batch_op.f("ix_location_change_requests_created_by_user_id"))

    op.drop_table("location_change_requests")
