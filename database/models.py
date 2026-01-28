from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    JSON, UniqueConstraint, Index, Date
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    pass


class ScrapeSession(Base):
    """Log setiap sesi scraping harian."""

    __tablename__ = "scrape_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # Tanggal target scraping
    status: Mapped[str] = mapped_column(String(20), default="running")  # running/completed/failed
    articles_found: Mapped[int] = mapped_column(Integer, default=0)
    articles_scraped: Mapped[int] = mapped_column(Integer, default=0)  # Total yang di-scrape
    articles_success: Mapped[int] = mapped_column(Integer, default=0)  # Hanya yang berhasil
    articles_failed: Mapped[int] = mapped_column(Integer, default=0)  # Yang gagal
    articles_new: Mapped[int] = mapped_column(Integer, default=0)
    articles_updated: Mapped[int] = mapped_column(Integer, default=0)
    articles_skipped: Mapped[int] = mapped_column(Integer, default=0)  # Skipped karena bukan tanggal target
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_scrape_sessions_target_date", "target_date"),
    )

    def __repr__(self) -> str:
        return f"<ScrapeSession(id={self.id}, target_date={self.target_date}, status={self.status})>"


class Article(Base):
    """Menyimpan artikel SGE."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sge_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # HTML/markdown
    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Plain text
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Array of tags
    author_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    author_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    featured_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    read_time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationship to social contents
    social_contents: Mapped[List["SocialContent"]] = relationship(
        "SocialContent", back_populates="article", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_articles_slug", "slug"),
        Index("idx_articles_category", "category"),
        Index("idx_articles_published_at", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title={self.title[:50] if self.title else None})>"


class SocialContent(Base):
    """Menyimpan konten sosial media dari dalam artikel."""

    __tablename__ = "social_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("articles.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # tiktok/instagram/twitter/youtube
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # video/post/tweet/embed/screenshot
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    embed_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    position_in_article: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship to article
    article: Mapped["Article"] = relationship("Article", back_populates="social_contents")

    __table_args__ = (
        Index("idx_social_contents_article_id", "article_id"),
        Index("idx_social_contents_platform", "platform"),
    )

    def __repr__(self) -> str:
        return f"<SocialContent(id={self.id}, platform={self.platform})>"
