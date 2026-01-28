"""Sessions API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc

from api.schemas import SessionResponse, SessionListResponse
from database.connection import get_session
from database.models import ScrapeSession

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List Sessions",
    description="Get paginated list of scrape sessions.",
)
async def list_sessions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """
    List all scrape sessions with pagination.

    Returns scrape sessions ordered by start time (newest first).
    """
    with get_session() as db:
        query = db.query(ScrapeSession)

        total = query.count()
        total_pages = (total + page_size - 1) // page_size

        sessions = (
            query
            .order_by(desc(ScrapeSession.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return SessionListResponse(
            items=[SessionResponse.model_validate(s) for s in sessions],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


@router.get(
    "/latest",
    response_model=SessionResponse,
    summary="Get Latest Session",
    description="Get the most recent scrape session.",
)
async def get_latest_session():
    """
    Get the most recent scrape session.

    Returns the latest session regardless of its status.
    """
    with get_session() as db:
        session = (
            db.query(ScrapeSession)
            .order_by(desc(ScrapeSession.started_at))
            .first()
        )

        if not session:
            raise HTTPException(status_code=404, detail="No sessions found")

        return SessionResponse.model_validate(session)


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get Session by ID",
    description="Retrieve a single scrape session by its ID.",
)
async def get_session_by_id(session_id: int):
    """
    Get scrape session details by ID.

    Returns full session data including statistics.
    """
    with get_session() as db:
        session = db.query(ScrapeSession).filter(ScrapeSession.id == session_id).first()

        if not session:
            raise HTTPException(status_code=404, detail=f"Session with ID {session_id} not found")

        return SessionResponse.model_validate(session)
