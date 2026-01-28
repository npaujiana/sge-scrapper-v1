"""Add date tracking fields to scrape_sessions

Revision ID: 002
Revises: 001
Create Date: 2024-01-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to scrape_sessions
    op.add_column('scrape_sessions', sa.Column('target_date', sa.Date(), nullable=True))
    op.add_column('scrape_sessions', sa.Column('articles_scraped', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('scrape_sessions', sa.Column('articles_success', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('scrape_sessions', sa.Column('articles_failed', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('scrape_sessions', sa.Column('articles_skipped', sa.Integer(), nullable=False, server_default='0'))

    # Create index for target_date
    op.create_index('idx_scrape_sessions_target_date', 'scrape_sessions', ['target_date'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_scrape_sessions_target_date', table_name='scrape_sessions')
    op.drop_column('scrape_sessions', 'articles_skipped')
    op.drop_column('scrape_sessions', 'articles_failed')
    op.drop_column('scrape_sessions', 'articles_success')
    op.drop_column('scrape_sessions', 'articles_scraped')
    op.drop_column('scrape_sessions', 'target_date')
