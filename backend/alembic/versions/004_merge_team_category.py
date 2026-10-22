"""Merge heads 003_merge_heads (dev) and 003_add_team_member_category (main).

Revision ID: 004_merge_team_category
Revises: 003_merge_heads, 003_add_team_member_category
Create Date: 2026-10-21
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '004_merge_team_category'
down_revision: Union[str, Sequence[str], None] = ('003_merge_heads', '003_add_team_member_category')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
