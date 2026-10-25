"""Add password_hash column to businesses for email+password authentication

Revision ID: 005_password_auth
Revises: 004_owner_email
Create Date: 2026-10-25 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005_password_auth'
down_revision: Union[str, None] = '004_owner_email'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('businesses', sa.Column('password_hash', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('businesses', 'password_hash')
