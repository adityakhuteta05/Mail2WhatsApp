"""Initial database schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-29 09:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. gmail_accounts
    op.create_table(
        'gmail_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('refresh_token_ref', sa.Text(), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('token_expiry', sa.DateTime(), nullable=True),
        sa.Column('history_id', sa.String(length=128), nullable=True),
        sa.Column('watch_expiry', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gmail_accounts_email', 'gmail_accounts', ['email'], unique=True)
    op.create_index('ix_gmail_accounts_id', 'gmail_accounts', ['id'], unique=False)

    # 2. emails
    op.create_table(
        'emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('gmail_message_id', sa.String(length=128), nullable=False),
        sa.Column('thread_id', sa.String(length=128), nullable=True),
        sa.Column('sender', sa.String(length=512), nullable=True),
        sa.Column('recipients', sa.Text(), nullable=True),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('body_ref', sa.String(length=512), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=False, server_default='DISCOVERED'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['gmail_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_emails_gmail_message_id', 'emails', ['gmail_message_id'], unique=True)
    op.create_index('ix_emails_received_at', 'emails', ['received_at'], unique=False)
    op.create_index('ix_emails_status', 'emails', ['status'], unique=False)
    op.create_index('ix_emails_id', 'emails', ['id'], unique=False)

    # 3. attachments
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_id', sa.Integer(), nullable=False),
        sa.Column('gmail_attachment_id', sa.String(length=512), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('mime_type', sa.String(length=128), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('whatsapp_media_id', sa.String(length=256), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=False, server_default='PENDING'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['email_id'], ['emails.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_attachments_email_id', 'attachments', ['email_id'], unique=False)
    op.create_index('ix_attachments_id', 'attachments', ['id'], unique=False)

    # 4. delivery_logs
    op.create_table(
        'delivery_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_id', sa.Integer(), nullable=False),
        sa.Column('whatsapp_message_id', sa.String(length=256), nullable=True),
        sa.Column('recipient', sa.String(length=64), nullable=False),
        sa.Column('message_type', sa.String(length=32), nullable=False, server_default='text'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='sent'),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['email_id'], ['emails.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_delivery_logs_whatsapp_message_id', 'delivery_logs', ['whatsapp_message_id'], unique=True)
    op.create_index('ix_delivery_logs_status', 'delivery_logs', ['status'], unique=False)
    op.create_index('ix_delivery_logs_email_id', 'delivery_logs', ['email_id'], unique=False)
    op.create_index('ix_delivery_logs_id', 'delivery_logs', ['id'], unique=False)

    # 5. sync_runs
    op.create_table(
        'sync_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('history_start', sa.String(length=128), nullable=True),
        sa.Column('history_end', sa.String(length=128), nullable=True),
        sa.Column('messages_discovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('messages_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='RUNNING'),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['gmail_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sync_runs_account_id', 'sync_runs', ['account_id'], unique=False)
    op.create_index('ix_sync_runs_id', 'sync_runs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('sync_runs')
    op.drop_table('delivery_logs')
    op.drop_table('attachments')
    op.drop_table('emails')
    op.drop_table('gmail_accounts')
