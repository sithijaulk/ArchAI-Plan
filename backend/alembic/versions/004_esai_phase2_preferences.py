"""ESAI Phase 2: per-room and per-floor client preference tables

Revision ID: 004_esai_phase2
Revises: 003_merge_heads
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "004_esai_phase2"
down_revision = "003_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-floor preference overrides (override building defaults)
    op.create_table(
        "esai_floor_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("floor_id", sa.String(255), nullable=False),
        sa.Column("preferences_json", sa.JSON, nullable=False),
        sa.Column("geometry_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("project_id", "floor_id", name="uq_esai_floor_preferences_project_floor"),
    )

    # Per-room full preference records (highest priority)
    op.create_table(
        "esai_room_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("floor_id", sa.String(255), nullable=False),
        sa.Column("room_id", sa.String(255), nullable=False),
        sa.Column("room_type", sa.String(64), nullable=False),
        sa.Column("preferences_json", sa.JSON, nullable=False),
        sa.Column("preference_revision", sa.Integer, default=1, nullable=False),
        sa.Column("geometry_fingerprint", sa.String(64), nullable=True),
        sa.Column("is_orphaned", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("project_id", "room_id", name="uq_esai_room_preferences_project_room"),
    )


def downgrade() -> None:
    op.drop_table("esai_room_preferences")
    op.drop_table("esai_floor_preferences")
