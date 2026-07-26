"""add mcp auth header name

Revision ID: e8f2a6b0c4d5
Revises: d7e1f5a9b3c4
Create Date: 2026-07-24 00:00:04.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "e8f2a6b0c4d5"
down_revision = "d7e1f5a9b3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_server",
        sa.Column(
            "auth_header_name",
            sa.String(length=100),
            server_default=sa.text("''::character varying"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("mcp_server", "auth_header_name")
