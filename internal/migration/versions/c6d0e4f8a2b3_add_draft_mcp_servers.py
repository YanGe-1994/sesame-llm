"""add draft mcp servers

Revision ID: c6d0e4f8a2b3
Revises: b5c9d3e7f1a2
Create Date: 2026-07-24 00:00:02.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c6d0e4f8a2b3"
down_revision = "b5c9d3e7f1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "draft_app_config",
        sa.Column(
            "mcp_servers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("draft_app_config", "mcp_servers")