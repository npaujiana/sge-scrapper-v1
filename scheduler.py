import asyncio
from datetime import datetime, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings
from config.logging_config import get_logger
from services.scrape_service import ScrapeService


class ScraperScheduler:
    """Scheduler for running scrape jobs."""

    def __init__(self):
        self.logger = get_logger()
        self.scheduler = AsyncIOScheduler()
        self.scrape_service = ScrapeService()

    async def _run_scrape_job(self) -> None:
        """Execute the scrape job for today's date."""
        today = date.today()
        self.logger.info(f"Scheduled scrape job started at {datetime.utcnow()} for date {today}")
        try:
            result = await self.scrape_service.run_scrape(target_date=today)

            if result.get("status") == "skipped":
                self.logger.info(
                    f"Scheduled scrape job skipped - already has successful scrape for {today}. "
                    f"Previous success: {result.get('articles_success', 0)} articles."
                )
            elif result.get("status") == "completed":
                self.logger.info(
                    f"Scheduled scrape job completed for {today}: "
                    f"success={result.get('articles_success', 0)}, "
                    f"failed={result.get('articles_failed', 0)}, "
                    f"new={result.get('articles_new', 0)}"
                )
            else:
                self.logger.error(f"Scheduled scrape job result: {result}")

        except Exception as e:
            self.logger.error(f"Scheduled scrape job failed: {e}")

    def _sync_run_scrape_job(self) -> None:
        """Synchronous wrapper for the async scrape job."""
        asyncio.create_task(self._run_scrape_job())

    def schedule_daily(self, time_str: str = None) -> None:
        """
        Schedule daily scrape job.

        Args:
            time_str: Time in HH:MM format (default from settings).
        """
        time_str = time_str or settings.scrape_time
        hour, minute = map(int, time_str.split(":"))

        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            self._sync_run_scrape_job,
            trigger=trigger,
            id="daily_scrape",
            name="Daily SGE Scrape",
            replace_existing=True,
        )
        self.logger.info(f"Scheduled daily scrape at {time_str}")

    def schedule_interval(self, hours: int = None) -> None:
        """
        Schedule scrape job at regular intervals.

        Args:
            hours: Interval in hours (default from settings).
        """
        hours = hours or settings.scrape_interval_hours

        self.scheduler.add_job(
            self._sync_run_scrape_job,
            "interval",
            hours=hours,
            id="interval_scrape",
            name="Interval SGE Scrape",
            replace_existing=True,
        )
        self.logger.info(f"Scheduled scrape every {hours} hours")

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            self.logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            self.logger.info("Scheduler stopped")

    def get_jobs(self) -> list:
        """Get list of scheduled jobs."""
        return self.scheduler.get_jobs()


def create_scheduler() -> ScraperScheduler:
    """Create and configure the scheduler."""
    scheduler = ScraperScheduler()
    scheduler.schedule_daily()
    return scheduler
