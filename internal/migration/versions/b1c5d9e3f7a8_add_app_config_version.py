"""add app config version

Revision ID: b1c5d9e3f7a8
Revises: a0b4c8d2e6f7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b1c5d9e3f7a8"
down_revision = "a0b4c8d2e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_config_version",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("mcp_servers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(0)")),
        sa.PrimaryKeyConstraint("id", name="pk_app_config_version_id"),
        sa.UniqueConstraint("app_id", "version", name="uq_app_config_version_app_version"),
    )
    op.create_index("idx_app_config_version_app_created", "app_config_version", ["app_id", "created_at"])


def downgrade():
    op.drop_index("idx_app_config_version_app_created", table_name="app_config_version")
    op.drop_table("app_config_version")
