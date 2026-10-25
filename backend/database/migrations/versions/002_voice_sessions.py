"""Add voice_sessions table and conversation_messages.session_id

Revision ID: 002_voice_sessions
Revises: 001_initial_schema
Create Date: 2026-10-24 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_voice_sessions'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Voice Sessions Table
    op.create_table(
        'voice_sessions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('provider_call_id', sa.String(length=128), nullable=False),
        sa.Column('provider_name', sa.String(length=50), nullable=False, server_default='mock'),
        sa.Column('called_number', sa.String(length=50), nullable=False),
        sa.Column('caller_number', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='initiated'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_turn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('call_record_id', sa.String(length=64), nullable=True),
        sa.Column('session_metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['call_record_id'], ['call_records.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_voice_sessions_business_id', 'voice_sessions', ['business_id'])
    op.create_index('ix_voice_sessions_provider_call_id', 'voice_sessions', ['provider_call_id'])
    op.create_index('ix_voice_sessions_status', 'voice_sessions', ['status'])
    op.create_index('ix_voice_session_business_status', 'voice_sessions', ['business_id', 'status'])
    op.create_index('ix_voice_session_provider_call', 'voice_sessions', ['provider_name', 'provider_call_id'])

    # 2. Add session_id to conversation_messages
    op.add_column(
        'conversation_messages',
        sa.Column('session_id', sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        'fk_conversation_messages_session_id',
        'conversation_messages',
        'voice_sessions',
        ['session_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_conversation_messages_session_id', 'conversation_messages', ['session_id'])
    op.create_index('ix_msg_session_timestamp', 'conversation_messages', ['session_id', 'timestamp'])


def downgrade() -> None:
    op.drop_index('ix_msg_session_timestamp', table_name='conversation_messages')
    op.drop_index('ix_conversation_messages_session_id', table_name='conversation_messages')
    op.drop_constraint('fk_conversation_messages_session_id', 'conversation_messages', type_='foreignkey')
    op.drop_column('conversation_messages', 'session_id')

    op.drop_index('ix_voice_session_provider_call', table_name='voice_sessions')
    op.drop_index('ix_voice_session_business_status', table_name='voice_sessions')
    op.drop_index('ix_voice_sessions_status', table_name='voice_sessions')
    op.drop_index('ix_voice_sessions_provider_call_id', table_name='voice_sessions')
    op.drop_index('ix_voice_sessions_business_id', table_name='voice_sessions')
    op.drop_table('voice_sessions')
