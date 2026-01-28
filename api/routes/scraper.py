"""Scraper API endpoints."""
import asyncio
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse

from api.schemas import ScrapeTaskResponse, ScrapeStatusResponse, SingleScrapeResponse, DateStatusResponse, ExportResponse, ExportListResponse
from services.scrape_service import ScrapeService
from services.export_service import ExportService
from config.logging_config import get_logger

router = APIRouter(prefix="/api/scraper", tags=["Scraper"])
logger = get_logger()

# In-memory task storage (for production, use Redis or database)
scrape_tasks: dict = {}


async def run_scrape_task(
    task_id: str,
    limit: Optional[int] = None,
    target_date: Optional[date] = None,
    force: bool = False
):
    """Background task to run the scraper for a specific date."""
    scrape_tasks[task_id]["status"] = "running"
    scrape_tasks[task_id]["started_at"] = datetime.utcnow()

    try:
        service = ScrapeService()
        result = await service.run_scrape(
            limit=limit,
            target_date=target_date,
            force=force
        )

        scrape_tasks[task_id]["status"] = "completed"
        scrape_tasks[task_id]["result"] = result
        scrape_tasks[task_id]["finished_at"] = datetime.utcnow()

    except Exception as e:
        logger.error(f"Scrape task {task_id} failed: {e}")
        scrape_tasks[task_id]["status"] = "failed"
        scrape_tasks[task_id]["error"] = str(e)
        scrape_tasks[task_id]["finished_at"] = datetime.utcnow()


@router.post(
    "/run",
    response_model=ScrapeTaskResponse,
    summary="Trigger Scraper",
    description="Start a background scraping task for a specific date. Only scrapes articles from that date.",
)
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    limit: Optional[int] = Query(None, description="Limit number of articles to scrape", ge=1),
    target_date: Optional[date] = Query(None, description="Target date for scraping (YYYY-MM-DD, default: today)"),
    force: bool = Query(False, description="Force scrape even if already has successful scrape for the date"),
):
    """
    Trigger a scraping session for a specific date.

    This endpoint starts a background task that:
    1. Fetches article URLs from configured sitemaps for the target date
    2. Filters out already scraped articles
    3. Validates article published_at matches target date
    4. Only counts successfully scraped articles (failed ones are NOT counted)
    5. Skips if already has successful scrape for the date (unless force=True)

    Use the returned task_id to check progress via `/api/scraper/status/{task_id}`.
    """
    task_id = str(uuid.uuid4())
    target = target_date or date.today()

    scrape_tasks[task_id] = {
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
        "limit": limit,
        "target_date": str(target),
        "force": force,
    }

    background_tasks.add_task(run_scrape_task, task_id, limit, target, force)

    return ScrapeTaskResponse(
        task_id=task_id,
        status="started",
        target_date=str(target),
        message=f"Scrape task started for date {target}{' with limit ' + str(limit) if limit else ''}. Check status at /api/scraper/status/{task_id}",
    )


@router.post(
    "/run-single",
    response_model=SingleScrapeResponse,
    summary="Scrape Single Article",
    description="Scrape a single article by URL. Useful for testing or on-demand scraping.",
)
async def scrape_single(
    url: str = Query(..., description="The article URL to scrape"),
    target_date: Optional[date] = Query(None, description="Optional target date to validate article against"),
    save: bool = Query(False, description="Save to database if scrape successful and date valid"),
):
    """
    Scrape a single article by its URL.

    This is a synchronous operation that will scrape the article and return
    the extracted data directly. Optionally validates against target_date and saves to database.
    """
    try:
        service = ScrapeService()
        result = await service.scrape_single_article(
            url,
            target_date=target_date,
            save_to_db=save
        )

        if result:
            return SingleScrapeResponse(status="success", article=result)
        else:
            return SingleScrapeResponse(
                status="failed",
                error="Failed to extract article data from URL",
            )

    except Exception as e:
        logger.error(f"Single scrape failed for {url}: {e}")
        return SingleScrapeResponse(status="failed", error=str(e))


@router.get(
    "/session",
    summary="Check Login Session",
    description="Check if there's a valid login session.",
)
async def check_session_status():
    """
    Check if user is logged in (has valid session).

    Login harus dilakukan via CLI: python main.py --login
    """
    try:
        service = ScrapeService()
        result = service.check_session()

        return {
            "logged_in": result.get("has_session", False),
            "email": result.get("email"),
            "message": result.get("message"),
        }
    except Exception as e:
        logger.error(f"Failed to check session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/session",
    summary="Clear Login Session",
    description="Clear saved login session.",
)
async def clear_session():
    """Clear the saved login session."""
    try:
        service = ScrapeService()
        result = service.clear_session()

        return {
            "status": result.get("status"),
            "message": result.get("message"),
        }
    except Exception as e:
        logger.error(f"Failed to clear session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/date-status",
    response_model=DateStatusResponse,
    summary="Check Date Status",
    description="Check if there's already a successful scrape for a specific date.",
)
async def get_date_status(
    target_date: Optional[date] = Query(None, description="Date to check (YYYY-MM-DD, default: today)"),
):
    """
    Check scrape status for a specific date.

    Returns whether there's a successful scrape for the date and the statistics.
    """
    target = target_date or date.today()

    try:
        service = ScrapeService()
        result = service.get_scrape_status_for_date(target)

        return DateStatusResponse(
            date=result.get("date"),
            has_successful_scrape=result.get("has_successful_scrape", False),
            session_id=result.get("session_id"),
            articles_success=result.get("articles_success", 0),
            articles_failed=result.get("articles_failed", 0),
            articles_new=result.get("articles_new", 0),
            completed_at=result.get("completed_at"),
        )

    except Exception as e:
        logger.error(f"Failed to get date status for {target}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/status/{task_id}",
    response_model=ScrapeStatusResponse,
    summary="Check Task Status",
    description="Check the status of a running or completed scraping task.",
)
async def get_scrape_status(task_id: str):
    """
    Get the current status of a scrape task.

    Possible statuses:
    - `pending`: Task is queued but not yet started
    - `running`: Task is currently executing
    - `completed`: Task finished successfully
    - `failed`: Task encountered an error
    """
    if task_id not in scrape_tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task = scrape_tasks[task_id]

    return ScrapeStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress={"limit": task.get("limit")} if task["status"] == "running" else None,
        result=task.get("result"),
        error=task.get("error"),
        started_at=task.get("started_at"),
        finished_at=task.get("finished_at"),
    )


@router.post(
    "/export",
    response_model=ExportResponse,
    summary="Export Articles to Excel",
    description="Export articles to an Excel file with optional date filtering.",
)
async def export_articles(
    target_date: Optional[date] = Query(None, description="Export articles for specific date"),
    start_date: Optional[date] = Query(None, description="Start date for range export"),
    end_date: Optional[date] = Query(None, description="End date for range export"),
    include_content: bool = Query(False, description="Include full article content (larger file)"),
):
    """
    Export articles to Excel file.

    Returns the path to the generated file which can be downloaded via /api/scraper/export/download.
    """
    try:
        export_service = ExportService()
        output_path = export_service.export_articles_to_excel(
            target_date=target_date,
            start_date=start_date,
            end_date=end_date,
            include_content=include_content,
        )

        return ExportResponse(
            status="success",
            message="Export completed successfully",
            file_path=output_path,
            filename=output_path.split("\\")[-1].split("/")[-1],
        )

    except ValueError as e:
        return ExportResponse(
            status="failed",
            message=str(e),
            file_path=None,
            filename=None,
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/export/download/{filename}",
    summary="Download Export File",
    description="Download a previously generated export file.",
)
async def download_export(filename: str):
    """Download an export file by filename."""
    from config.settings import settings

    file_path = settings.project_root / "exports" / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get(
    "/export/list",
    response_model=ExportListResponse,
    summary="List Export Files",
    description="List all available export files.",
)
async def list_export_files():
    """List all export files."""
    try:
        export_service = ExportService()
        exports = export_service.list_exports()

        return ExportListResponse(
            total=len(exports),
            files=exports,
        )

    except Exception as e:
        logger.error(f"Failed to list exports: {e}")
        raise HTTPException(status_code=500, detail=str(e))
