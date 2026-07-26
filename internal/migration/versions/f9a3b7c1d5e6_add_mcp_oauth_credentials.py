"""add mcp oauth credentials

Revision ID: f9a3b7c1d5e6
Revises: e8f2a6b0c4d5
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f9a3b7c1d5e6"
down_revision = "e8f2a6b0c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mcp_server", sa.Column("oauth_authorization_url", sa.String(2048), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("oauth_token_url", sa.String(2048), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("oauth_client_id", sa.String(255), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("encrypted_oauth_client_secret", sa.Text(), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("oauth_client_secret_hint", sa.String(32), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("oauth_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("mcp_server", sa.Column("oauth_token_endpoint_auth_method", sa.String(32), nullable=False, server_default="client_secret_post"))
    op.add_column("mcp_server", sa.Column("encrypted_access_token", sa.Text(), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("encrypted_refresh_token", sa.Text(), nullable=False, server_default=""))
    op.add_column("mcp_server", sa.Column("oauth_token_type", sa.String(32), nullable=False, server_default="Bearer"))
    op.add_column("mcp_server", sa.Column("oauth_expires_at", sa.DateTime(), nullable=True))
    op.add_column("mcp_server", sa.Column("oauth_granted_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("mcp_server", sa.Column("oauth_authorized_at", sa.DateTime(), nullable=True))
    op.add_column("mcp_server", sa.Column("oauth_last_error", sa.Text(), nullable=False, server_default=""))


def downgrade():
    for column in [
        "oauth_last_error", "oauth_authorized_at", "oauth_granted_scopes",
        "oauth_expires_at", "oauth_token_type", "encrypted_refresh_token",
        "encrypted_access_token", "oauth_token_endpoint_auth_method", "oauth_scopes",
        "oauth_client_secret_hint", "encrypted_oauth_client_secret",
        "oauth_client_id", "oauth_token_url", "oauth_authorization_url",
    ]:
        op.drop_column("mcp_server", column)
