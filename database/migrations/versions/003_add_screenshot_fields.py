"""Add screenshot fields to social_contents

Revision ID: 003
Revises: 002
Create Date: 2026-02-01
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add screenshot_path column
    op.add_column(
        'social_contents',
        sa.Column('screenshot_path', sa.String(500), nullable=True)
    )
    # Add screenshot_source column
    op.add_column(
        'social_contents',
        sa.Column('screenshot_source', sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('social_contents', 'screenshot_source')
    op.drop_column('social_contents', 'screenshot_path')
