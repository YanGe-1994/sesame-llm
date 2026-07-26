"""add mcp server and tool

Revision ID: a4b8c2d6e0f1
Revises: f2c9d7a4e8b1
Create Date: 2026-07-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a4b8c2d6e0f1"
down_revision = "f2c9d7a4e8b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_server",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("icon", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("transport", sa.String(length=32), server_default=sa.text("'streamable_http'::character varying"), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("auth_type", sa.String(length=32), server_default=sa.text("'none'::character varying"), nullable=False),
        sa.Column("secret_ref", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'::character varying"), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("tool_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tools_hash", sa.String(length=128), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("last_error", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_server_id"),
        sa.UniqueConstraint("account_id", "name", name="uq_mcp_server_account_name"),
    )
    op.create_index("idx_mcp_server_account_id", "mcp_server", ["account_id"])
    op.create_index("idx_mcp_server_status", "mcp_server", ["status"])
    op.create_table(
        "mcp_tool",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("server_id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("annotations", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("risk_level", sa.String(length=32), server_default=sa.text("'normal'::character varying"), nullable=False),
        sa.Column("approval_mode", sa.String(length=32), server_default=sa.text("'auto'::character varying"), nullable=False),
        sa.Column("schema_hash", sa.String(length=128), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_tool_id"),
        sa.UniqueConstraint("server_id", "tool_name", name="uq_mcp_tool_server_name"),
    )
    op.create_index("idx_mcp_tool_server_id", "mcp_tool", ["server_id"])


def downgrade():
    op.drop_index("idx_mcp_tool_server_id", table_name="mcp_tool")
    op.drop_table("mcp_tool")
    op.drop_index("idx_mcp_server_status", table_name="mcp_server")
    op.drop_index("idx_mcp_server_account_id", table_name="mcp_server")
    op.drop_table("mcp_server")