"""add mcp audit log

Revision ID: a0b4c8d2e6f7
Revises: f9a3b7c1d5e6
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a0b4c8d2e6f7"
down_revision = "f9a3b7c1d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_audit_log",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("server_id", sa.UUID(), nullable=True),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("approval_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("server_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("tool_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("tool_display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("request_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("response_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("latency", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(0)")),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_audit_log_id"),
    )
    op.create_index("idx_mcp_audit_log_account_created", "mcp_audit_log", ["account_id", "created_at"])
    op.create_index("idx_mcp_audit_log_server_created", "mcp_audit_log", ["server_id", "created_at"])
    op.create_index("idx_mcp_audit_log_task_id", "mcp_audit_log", ["task_id"])
    op.create_index("idx_mcp_audit_log_event_status", "mcp_audit_log", ["event_type", "status"])


def downgrade():
    op.drop_index("idx_mcp_audit_log_event_status", table_name="mcp_audit_log")
    op.drop_index("idx_mcp_audit_log_task_id", table_name="mcp_audit_log")
    op.drop_index("idx_mcp_audit_log_server_created", table_name="mcp_audit_log")
    op.drop_index("idx_mcp_audit_log_account_created", table_name="mcp_audit_log")
    op.drop_table("mcp_audit_log")
