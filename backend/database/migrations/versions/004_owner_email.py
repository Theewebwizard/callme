"""Add owner_email and owner_name columns to businesses for Google/Gmail sign-in

Revision ID: 004_owner_email
Revises: 003_tool_demands
Create Date: 2026-10-25 02:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004_owner_email'
down_revision: Union[str, None] = '003_tool_demands'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('businesses', sa.Column('owner_email', sa.String(length=255), nullable=True))
    op.add_column('businesses', sa.Column('owner_name', sa.String(length=255), nullable=True))
    op.create_index('ix_businesses_owner_email', 'businesses', ['owner_email'])


def downgrade() -> None:
    op.drop_index('ix_businesses_owner_email', table_name='businesses')
    op.drop_column('businesses', 'owner_name')
    op.drop_column('businesses', 'owner_email')
