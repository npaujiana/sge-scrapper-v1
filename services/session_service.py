from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session

from database.models import ScrapeSession
from config.logging_config import get_logger


class SessionService:
    """Manage scrape sessions in the database."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.logger = get_logger()

    def create_session(self, target_date: Optional[date] = None) -> ScrapeSession:
        """Create a new scrape session for a specific date."""
        session = ScrapeSession(
            started_at=datetime.utcnow(),
            target_date=target_date or date.today(),
            status="running",
            articles_found=0,
            articles_scraped=0,
            articles_success=0,
            articles_failed=0,
            articles_new=0,
            articles_updated=0,
            articles_skipped=0,
        )
        self.db.add(session)
        self.db.flush()
        self.logger.info(f"Created scrape session {session.id} for date {session.target_date}")
        return session

    def update_session(
        self,
        session: ScrapeSession,
        status: Optional[str] = None,
        articles_found: Optional[int] = None,
        articles_scraped: Optional[int] = None,
        articles_success: Optional[int] = None,
        articles_failed: Optional[int] = None,
        articles_new: Optional[int] = None,
        articles_updated: Optional[int] = None,
        articles_skipped: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> ScrapeSession:
        """Update scrape session statistics."""
        if status:
            session.status = status
        if articles_found is not None:
            session.articles_found = articles_found
        if articles_scraped is not None:
            session.articles_scraped = articles_scraped
        if articles_success is not None:
            session.articles_success = articles_success
        if articles_failed is not None:
            session.articles_failed = articles_failed
        if articles_new is not None:
            session.articles_new = articles_new
        if articles_updated is not None:
            session.articles_updated = articles_updated
        if articles_skipped is not None:
            session.articles_skipped = articles_skipped
        if error_message:
            session.error_message = error_message

        self.db.flush()
        return session

    def complete_session(
        self,
        session: ScrapeSession,
        articles_found: int,
        articles_scraped: int,
        articles_success: int,
        articles_failed: int,
        articles_new: int,
        articles_updated: int,
        articles_skipped: int = 0,
    ) -> ScrapeSession:
        """Mark session as completed."""
        session.status = "completed"
        session.finished_at = datetime.utcnow()
        session.articles_found = articles_found
        session.articles_scraped = articles_scraped
        session.articles_success = articles_success
        session.articles_failed = articles_failed
        session.articles_new = articles_new
        session.articles_updated = articles_updated
        session.articles_skipped = articles_skipped
        self.db.flush()

        self.logger.info(
            f"Session {session.id} for {session.target_date} completed: "
            f"found={articles_found}, scraped={articles_scraped}, "
            f"success={articles_success}, failed={articles_failed}, "
            f"new={articles_new}, updated={articles_updated}, skipped={articles_skipped}"
        )
        return session

    def fail_session(self, session: ScrapeSession, error_message: str) -> ScrapeSession:
        """Mark session as failed."""
        session.status = "failed"
        session.finished_at = datetime.utcnow()
        session.error_message = error_message
        self.db.flush()

        self.logger.error(f"Session {session.id} failed: {error_message}")
        return session

    def get_latest_session(self) -> Optional[ScrapeSession]:
        """Get the most recent scrape session."""
        return (
            self.db.query(ScrapeSession)
            .order_by(ScrapeSession.started_at.desc())
            .first()
        )

    def get_running_sessions(self) -> list[ScrapeSession]:
        """Get all currently running sessions."""
        return (
            self.db.query(ScrapeSession)
            .filter(ScrapeSession.status == "running")
            .all()
        )

    def get_session_for_date(self, target_date: date) -> Optional[ScrapeSession]:
        """Get successful session for a specific date."""
        return (
            self.db.query(ScrapeSession)
            .filter(
                ScrapeSession.target_date == target_date,
                ScrapeSession.status == "completed",
                ScrapeSession.articles_success > 0  # Hanya yang ada artikel sukses
            )
            .order_by(ScrapeSession.started_at.desc())
            .first()
        )

    def has_successful_scrape_for_date(self, target_date: date) -> bool:
        """Check if there's already a successful scrape for a specific date."""
        session = self.get_session_for_date(target_date)
        return session is not None

    def get_sessions_by_date_range(
        self, start_date: date, end_date: date
    ) -> list[ScrapeSession]:
        """Get all sessions within a date range."""
        return (
            self.db.query(ScrapeSession)
            .filter(
                ScrapeSession.target_date >= start_date,
                ScrapeSession.target_date <= end_date
            )
            .order_by(ScrapeSession.target_date.desc())
            .all()
        )
