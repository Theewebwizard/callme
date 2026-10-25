"""Initial schema migration for AI Receptionist Platform

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Businesses Table
    op.create_table(
        'businesses',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('industry', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('assigned_number_status', sa.String(length=50), nullable=True),
        sa.Column('opening_time', sa.String(length=10), nullable=False),
        sa.Column('closing_time', sa.String(length=10), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('greeting_message', sa.Text(), nullable=False),
        sa.Column('languages', sa.JSON(), nullable=False),
        sa.Column('transfer_instructions', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Business FAQs Table
    op.create_table(
        'business_faqs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_business_faqs_business_id'), 'business_faqs', ['business_id'], unique=False)

    # 3. Business Tool Configs Table
    op.create_table(
        'business_tool_configs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('tool_id', sa.String(length=64), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'tool_id', name='uq_business_tool')
    )
    op.create_index(op.f('ix_business_tool_configs_business_id'), 'business_tool_configs', ['business_id'], unique=False)
    op.create_index(op.f('ix_business_tool_configs_tool_id'), 'business_tool_configs', ['tool_id'], unique=False)

    # 4. Call Records Table
    op.create_table(
        'call_records',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('caller_number', sa.String(length=50), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('duration_formatted', sa.String(length=20), nullable=False),
        sa.Column('outcome', sa.String(length=100), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('tools_used', sa.JSON(), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_call_records_business_id'), 'call_records', ['business_id'], unique=False)
    op.create_index(op.f('ix_call_records_outcome'), 'call_records', ['outcome'], unique=False)
    op.create_index(op.f('ix_call_records_timestamp'), 'call_records', ['timestamp'], unique=False)
    op.create_index('ix_call_business_timestamp', 'call_records', ['business_id', 'timestamp'], unique=False)

    # 5. Conversation Messages Table
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversation_messages_business_id'), 'conversation_messages', ['business_id'], unique=False)
    op.create_index(op.f('ix_conversation_messages_timestamp'), 'conversation_messages', ['timestamp'], unique=False)
    op.create_index('ix_msg_business_timestamp', 'conversation_messages', ['business_id', 'timestamp'], unique=False)

    # 6. Pending Actions Table
    op.create_table(
        'pending_actions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('arguments', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('execution_reference', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pending_actions_business_id'), 'pending_actions', ['business_id'], unique=False)
    op.create_index(op.f('ix_pending_actions_status'), 'pending_actions', ['status'], unique=False)
    op.create_index('ix_pending_business_status', 'pending_actions', ['business_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_table('pending_actions')
    op.drop_table('conversation_messages')
    op.drop_table('call_records')
    op.drop_table('business_tool_configs')
    op.drop_table('business_faqs')
    op.drop_table('businesses')
