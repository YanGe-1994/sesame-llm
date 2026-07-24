"""add draft app config

Revision ID: f2c9d7a4e8b1
Revises: 812d7091a5ab
Create Date: 2026-07-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f2c9d7a4e8b1'
down_revision = '812d7091a5ab'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('draft_app_config',
    sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
    sa.Column('app_id', sa.UUID(), nullable=False),
    sa.Column('model_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('dialog_round', sa.Integer(), server_default=sa.text('3'), nullable=False),
    sa.Column('preset_prompt', sa.Text(), server_default=sa.text("''::text"), nullable=False),
    sa.Column('tools', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('workflows', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('datasets', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('retrieval_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('long_term_memory', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('opening_statement', sa.Text(), server_default=sa.text("''::text"), nullable=False),
    sa.Column('opening_questions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('speech_to_text', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('text_to_speech', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('suggested_after_answer', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('review_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP(0)'), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP(0)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name='pk_draft_app_config_id')
    )
    with op.batch_alter_table('draft_app_config', schema=None) as batch_op:
        batch_op.create_index('idx_draft_app_config_app_id', ['app_id'], unique=False)


def downgrade():
    with op.batch_alter_table('draft_app_config', schema=None) as batch_op:
        batch_op.drop_index('idx_draft_app_config_app_id')
    op.drop_table('draft_app_config')
