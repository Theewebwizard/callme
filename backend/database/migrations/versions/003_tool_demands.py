"""Add tool_demands table for custom receptionist features and integrations

Revision ID: 003_tool_demands
Revises: 002_voice_sessions
Create Date: 2026-10-25 01:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '003_tool_demands'
down_revision: Union[str, None] = '002_voice_sessions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tool_demands',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False, server_default='Custom Integration'),
        sa.Column('integration_target', sa.String(length=100), nullable=True),
        sa.Column('priority', sa.String(length=30), nullable=False, server_default='Important'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='Under Review'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tool_demands_business_id', 'tool_demands', ['business_id'])
    op.create_index('ix_tool_demands_status', 'tool_demands', ['status'])
    op.create_index('ix_tool_demands_business_status', 'tool_demands', ['business_id', 'status'])


def downgrade() -> None:
    op.drop_table('tool_demands')
