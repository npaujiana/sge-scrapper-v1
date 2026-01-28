"""FastAPI application for SGE Scraper API."""
import sys
import asyncio
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Fix Windows asyncio subprocess issue for Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from api.routes import scraper_router, articles_router, sessions_router, auth_router
from api.schemas import HealthResponse, ErrorResponse
from config.logging_config import get_logger

logger = get_logger()

# FastAPI app instance with OpenAPI metadata
app = FastAPI(
    title="SGE Scraper API",
    description="""
## SGE Scraper REST API

API untuk mengelola dan menjalankan web scraper untuk Social Growth Engineers.

### Fitur Utama:
- **Authentication**: Login ke SGE dengan email dan verification code
- **Scraper**: Trigger dan monitor scraping tasks
- **Articles**: CRUD operations untuk artikel yang sudah di-scrape
- **Sessions**: Lihat history dan statistik scraping sessions

### Login Flow:
1. POST `/api/auth/request-code` dengan email
2. Cek email untuk verification code
3. POST `/api/auth/verify-code` dengan code
4. Session tersimpan otomatis untuk scraping
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "SGE Scraper",
    },
    license_info={
        "name": "MIT",
    },
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )


# Health check endpoint
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health Check",
    description="Check if the API server is running and healthy.",
)
async def health_check():
    """
    Health check endpoint.

    Returns the current health status, timestamp, and API version.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
    )


# Include routers
app.include_router(auth_router)
app.include_router(scraper_router)
app.include_router(articles_router)
app.include_router(sessions_router)


# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("SGE Scraper API starting up...")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("SGE Scraper API shutting down...")
