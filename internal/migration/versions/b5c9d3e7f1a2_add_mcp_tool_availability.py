"""add mcp tool availability

Revision ID: b5c9d3e7f1a2
Revises: a4b8c2d6e0f1
Create Date: 2026-07-24 00:00:01.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "b5c9d3e7f1a2"
down_revision = "a4b8c2d6e0f1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_tool",
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade():
    op.drop_column("mcp_tool", "is_available")