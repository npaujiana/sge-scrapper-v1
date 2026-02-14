"""API routes module."""
from .scraper import router as scraper_router
from .articles import router as articles_router
from .sessions import router as sessions_router
from .auth import router as auth_router
from .tiktok import router as tiktok_router

__all__ = ["scraper_router", "articles_router", "sessions_router", "auth_router", "tiktok_router"]
