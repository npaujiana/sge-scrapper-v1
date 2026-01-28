"""Articles API endpoints."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, desc

from api.schemas import ArticleResponse, ArticleListResponse
from database.connection import get_session
from database.models import Article

router = APIRouter(prefix="/api/articles", tags=["Articles"])


@router.get(
    "",
    response_model=ArticleListResponse,
    summary="List Articles",
    description="Get paginated list of articles with optional filtering.",
)
async def list_articles(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in title"),
):
    """
    List all articles with pagination.

    Supports filtering by category and searching by title.
    Results are ordered by publication date (newest first).
    """
    with get_session() as db:
        query = db.query(Article)

        if category:
            query = query.filter(Article.category == category)

        if search:
            query = query.filter(Article.title.ilike(f"%{search}%"))

        total = query.count()
        total_pages = (total + page_size - 1) // page_size

        articles = (
            query
            .order_by(desc(Article.published_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return ArticleListResponse(
            items=[ArticleResponse.model_validate(a) for a in articles],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


@router.get(
    "/{article_id}",
    response_model=ArticleResponse,
    summary="Get Article by ID",
    description="Retrieve a single article by its database ID.",
)
async def get_article(article_id: int):
    """
    Get article details by ID.

    Returns full article data including social content embeds.
    """
    with get_session() as db:
        article = db.query(Article).filter(Article.id == article_id).first()

        if not article:
            raise HTTPException(status_code=404, detail=f"Article with ID {article_id} not found")

        return ArticleResponse.model_validate(article)


@router.get(
    "/slug/{slug}",
    response_model=ArticleResponse,
    summary="Get Article by Slug",
    description="Retrieve a single article by its URL slug.",
)
async def get_article_by_slug(slug: str):
    """
    Get article details by slug.

    The slug is derived from the article URL path.
    """
    with get_session() as db:
        article = db.query(Article).filter(Article.slug == slug).first()

        if not article:
            raise HTTPException(status_code=404, detail=f"Article with slug '{slug}' not found")

        return ArticleResponse.model_validate(article)
