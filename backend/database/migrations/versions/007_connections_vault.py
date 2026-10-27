"""Create integration_connections and expand integration_credentials with lease and fencing columns

Revision ID: 007_connections_vault
Revises: 006_pending_action_session_id
Create Date: 2026-10-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '007_connections_vault'
down_revision: Union[str, None] = '006_pending_action_session_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create integration_connections table
    op.create_table(
        'integration_connections',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('business_id', sa.String(length=64), nullable=False),
        sa.Column('provider_id', sa.String(length=64), nullable=False),
        sa.Column('connection_slug', sa.String(length=64), server_default='default', nullable=False),
        sa.Column('external_account_id', sa.String(length=255), nullable=True),
        sa.Column('display_label', sa.String(length=255), nullable=True),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('metadata_json', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'provider_id', 'connection_slug', name='uq_biz_provider_slug'),
    )
    op.create_index(op.f('ix_integration_connections_business_id'), 'integration_connections', ['business_id'], unique=False)
    op.create_index(op.f('ix_integration_connections_provider_id'), 'integration_connections', ['provider_id'], unique=False)

    # Partial unique index: at most one default connection per (business_id, provider_id)
    op.create_index(
        'ix_uq_biz_provider_default',
        'integration_connections',
        ['business_id', 'provider_id'],
        unique=True,
        postgresql_where=sa.text('is_default = true'),
        sqlite_where=sa.text('is_default = 1'),
    )

    # Partial unique index: unique non-null external_account_id per (business_id, provider_id)
    op.create_index(
        'ix_uq_biz_provider_external_acct',
        'integration_connections',
        ['business_id', 'provider_id', 'external_account_id'],
        unique=True,
        postgresql_where=sa.text('external_account_id IS NOT NULL'),
        sqlite_where=sa.text('external_account_id IS NOT NULL'),
    )

    # 2. Add additive columns to integration_credentials
    op.add_column('integration_credentials', sa.Column('connection_id', sa.String(length=64), nullable=True))
    op.add_column('integration_credentials', sa.Column('lease_owner_id', sa.String(length=64), nullable=True))
    op.add_column('integration_credentials', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('integration_credentials', sa.Column('fencing_token', sa.BigInteger(), server_default='0', nullable=False))
    op.add_column('integration_credentials', sa.Column('schema_version', sa.Integer(), server_default='1', nullable=False))

    op.create_foreign_key(
        'fk_cred_connection_id',
        'integration_credentials',
        'integration_connections',
        ['connection_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_index(
        op.f('ix_integration_credentials_connection_id'),
        'integration_credentials',
        ['connection_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_integration_credentials_connection_id'), table_name='integration_credentials')
    op.drop_constraint('fk_cred_connection_id', 'integration_credentials', type_='foreignkey')
    op.drop_column('integration_credentials', 'schema_version')
    op.drop_column('integration_credentials', 'fencing_token')
    op.drop_column('integration_credentials', 'lease_expires_at')
    op.drop_column('integration_credentials', 'lease_owner_id')
    op.drop_column('integration_credentials', 'connection_id')

    op.drop_index('ix_uq_biz_provider_external_acct', table_name='integration_connections')
    op.drop_index('ix_uq_biz_provider_default', table_name='integration_connections')
    op.drop_index(op.f('ix_integration_connections_provider_id'), table_name='integration_connections')
    op.drop_index(op.f('ix_integration_connections_business_id'), table_name='integration_connections')
    op.drop_table('integration_connections')
