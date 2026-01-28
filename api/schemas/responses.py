"""Pydantic response models for API endpoints."""
from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., example="healthy")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field(default="1.0.0")


class ScrapeTaskResponse(BaseModel):
    """Response when triggering a scrape task."""
    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., example="started", description="Task status")
    message: str = Field(..., description="Status message")
    target_date: Optional[str] = Field(None, description="Target date for scraping")


class ScrapeStatusResponse(BaseModel):
    """Response for scrape task status check."""
    task_id: str = Field(..., description="Task identifier")
    status: str = Field(..., example="running", description="Current status: pending, running, completed, failed")
    progress: Optional[dict] = Field(None, description="Progress information if available")
    result: Optional[dict] = Field(None, description="Result data when completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Task start time")
    finished_at: Optional[datetime] = Field(None, description="Task completion time")


class SingleScrapeResponse(BaseModel):
    """Response for single article scrape."""
    status: str = Field(..., example="success")
    article: Optional[dict] = Field(None, description="Scraped article data")
    error: Optional[str] = Field(None, description="Error message if failed")


class SocialContentResponse(BaseModel):
    """Social content embedded in article."""
    id: int
    platform: str = Field(..., example="tiktok")
    content_type: str = Field(..., example="video")
    url: Optional[str] = None
    embed_html: Optional[str] = None
    thumbnail_url: Optional[str] = None
    username: Optional[str] = None
    caption: Optional[str] = None
    position_in_article: int = 0

    class Config:
        from_attributes = True


class ArticleResponse(BaseModel):
    """Article detail response."""
    id: int
    sge_id: str
    url: str
    slug: str
    title: str
    subtitle: Optional[str] = None
    content: Optional[str] = None
    content_text: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    featured_image_url: Optional[str] = None
    read_time: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    social_contents: List[SocialContentResponse] = []

    class Config:
        from_attributes = True


class ArticleListResponse(BaseModel):
    """Paginated article list response."""
    items: List[ArticleResponse]
    total: int = Field(..., description="Total number of articles")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


class SessionResponse(BaseModel):
    """Scrape session detail response."""
    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    target_date: Optional[date] = Field(None, description="Target date for this scrape session")
    status: str = Field(..., example="completed")
    articles_found: int = 0
    articles_scraped: int = Field(0, description="Total articles attempted to scrape")
    articles_success: int = Field(0, description="Successfully scraped articles (counted)")
    articles_failed: int = Field(0, description="Failed articles (not counted)")
    articles_new: int = 0
    articles_updated: int = 0
    articles_skipped: int = Field(0, description="Skipped articles (wrong date)")
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class DateStatusResponse(BaseModel):
    """Status response for a specific date."""
    date: str = Field(..., description="The target date")
    has_successful_scrape: bool = Field(..., description="Whether there's a successful scrape for this date")
    session_id: Optional[int] = Field(None, description="Session ID if exists")
    articles_success: int = Field(0, description="Number of successful articles")
    articles_failed: int = Field(0, description="Number of failed articles")
    articles_new: int = Field(0, description="Number of new articles")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")


class ExportResponse(BaseModel):
    """Response for export request."""
    status: str = Field(..., example="success", description="Export status: success or failed")
    message: str = Field(..., description="Status message")
    file_path: Optional[str] = Field(None, description="Full path to the exported file")
    filename: Optional[str] = Field(None, description="Filename for download")


class ExportFileInfo(BaseModel):
    """Information about an export file."""
    filename: str = Field(..., description="File name")
    path: str = Field(..., description="Full file path")
    size_kb: float = Field(..., description="File size in KB")
    created_at: str = Field(..., description="Creation timestamp")


class ExportListResponse(BaseModel):
    """Response for listing export files."""
    total: int = Field(..., description="Total number of export files")
    files: List[ExportFileInfo] = Field(default_factory=list, description="List of export files")


class SessionListResponse(BaseModel):
    """Paginated session list response."""
    items: List[SessionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code if applicable")
