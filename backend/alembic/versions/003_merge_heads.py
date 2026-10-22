"""Merge heads 002_about_content, 002_esai_engine, 002_project_revision.

Revision ID: 003_merge_heads
Revises: 002_about_content, 002_esai_engine, 002_project_revision
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_merge_heads'
down_revision: Union[str, Sequence[str], None] = ('003_add_team_member_category', '002_esai_engine', '002_project_revision')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
