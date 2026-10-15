"""Add optimistic concurrency revision to projects."""
from alembic import op
import sqlalchemy as sa


revision = "002_project_revision"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("projects", "revision")