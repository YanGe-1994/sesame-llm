"""add encrypted mcp credentials

Revision ID: d7e1f5a9b3c4
Revises: c6d0e4f8a2b3
Create Date: 2026-07-24 00:00:03.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "d7e1f5a9b3c4"
down_revision = "c6d0e4f8a2b3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_server",
        sa.Column("encrypted_secret", sa.Text(), server_default=sa.text("''::text"), nullable=False),
    )
    op.add_column(
        "mcp_server",
        sa.Column(
            "secret_hint",
            sa.String(length=32),
            server_default=sa.text("''::character varying"),
            nullable=False,
        ),
    )
    op.execute("UPDATE mcp_server SET secret_ref = '' WHERE secret_ref <> ''")


def downgrade():
    op.drop_column("mcp_server", "secret_hint")
    op.drop_column("mcp_server", "encrypted_secret")
