"""Merge heads 004_esai_phase2 and 004_merge_team_category.

Revision ID: 005_merge_esai_team_heads
Revises: 004_esai_phase2, 004_merge_team_category
Create Date: 2026-10-22
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '005_merge_esai_team_heads'
down_revision: Union[str, Sequence[str], None] = ('004_esai_phase2', '004_merge_team_category')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
