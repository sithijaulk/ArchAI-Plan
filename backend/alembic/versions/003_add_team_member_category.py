"""Add category to team_members."""
from alembic import op
import sqlalchemy as sa

revision = "003_add_team_member_category"
down_revision = "002_about_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_members",
        sa.Column("category", sa.String(50), server_default="member", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("team_members", "category")
