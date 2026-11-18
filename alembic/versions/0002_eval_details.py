"""evaluation timing and per-conversation details

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eval_run", sa.Column("conversations_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("eval_run", sa.Column("conversations_done", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("eval_run", sa.Column("details", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("eval_run", "details")
    op.drop_column("eval_run", "conversations_done")
    op.drop_column("eval_run", "conversations_total")
