"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create scrape_sessions table
    op.create_table(
        'scrape_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('articles_found', sa.Integer(), nullable=False),
        sa.Column('articles_new', sa.Integer(), nullable=False),
        sa.Column('articles_updated', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create articles table
    op.create_table(
        'articles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sge_id', sa.String(length=100), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('slug', sa.String(length=300), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('subtitle', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('author_name', sa.String(length=200), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.Column('featured_image_url', sa.String(length=500), nullable=True),
        sa.Column('read_time', sa.String(length=50), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sge_id')
    )
    op.create_index('idx_articles_slug', 'articles', ['slug'], unique=False)
    op.create_index('idx_articles_category', 'articles', ['category'], unique=False)
    op.create_index('idx_articles_published_at', 'articles', ['published_at'], unique=False)

    # Create social_contents table
    op.create_table(
        'social_contents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('embed_html', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
        sa.Column('username', sa.String(length=200), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('position_in_article', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_social_contents_article_id', 'social_contents', ['article_id'], unique=False)
    op.create_index('idx_social_contents_platform', 'social_contents', ['platform'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_social_contents_platform', table_name='social_contents')
    op.drop_index('idx_social_contents_article_id', table_name='social_contents')
    op.drop_table('social_contents')
    op.drop_index('idx_articles_published_at', table_name='articles')
    op.drop_index('idx_articles_category', table_name='articles')
    op.drop_index('idx_articles_slug', table_name='articles')
    op.drop_table('articles')
    op.drop_table('scrape_sessions')
