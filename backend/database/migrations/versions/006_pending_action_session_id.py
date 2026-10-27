"""Add session_id column to pending_actions for strict call session isolation

Revision ID: 006_pending_action_session_id
Revises: 005_password_auth
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '006_pending_action_session_id'
down_revision: Union[str, None] = '005_password_auth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pending_actions', sa.Column('session_id', sa.String(length=64), nullable=True))
    op.create_index('ix_pending_session_status', 'pending_actions', ['session_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pending_session_status', table_name='pending_actions')
    op.drop_column('pending_actions', 'session_id')
