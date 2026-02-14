

import argparse
import asyncio
import signal
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from config.settings import settings
from config.logging_config import setup_logging
from services.scrape_service import ScrapeService
from services.export_service import ExportService
from scheduler import create_scheduler


# Global flag for graceful shutdown
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print(f"\nReceived signal {signum}, shutting down gracefully...")
    shutdown_event.set()


def run_alembic_command(command: list[str]) -> int:
    """Run an alembic command."""
    project_root = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic"] + command,
        cwd=project_root,
        capture_output=False
    )
    return result.returncode


def migrate_db() -> None:
    """Run database migrations using Alembic."""
    logger = setup_logging(settings.log_level, settings.log_file)
    logger.info("Running database migrations...")

    print("Running: alembic upgrade head")
    returncode = run_alembic_command(["upgrade", "head"])

    if returncode == 0:
        print("\nDatabase migrations completed successfully!")
        logger.info("Database migrations complete")
    else:
        print("\nDatabase migrations failed!")
        logger.error("Database migrations failed")
        sys.exit(1)


def migrate_status() -> None:
    """Check current migration status."""
    logger = setup_logging(settings.log_level, settings.log_file)
    logger.info("Checking migration status...")

    print("Current migration status:")
    run_alembic_command(["current"])
    print("\nMigration history:")
    run_alembic_command(["history", "--verbose"])


async def run_once(
    limit: int = None,
    target_date: date = None,
    force: bool = False
) -> None:
    """Run scraper once for a specific date and exit."""
    logger = setup_logging(settings.log_level, settings.log_file)
    target_date = target_date or date.today()
    logger.info(f"Running scraper once for date: {target_date}...")

    # Run scrape
    scrape_service = ScrapeService()
    result = await scrape_service.run_scrape(
        limit=limit,
        target_date=target_date,
        force=force
    )

    logger.info(f"Scrape completed: {result}")
    print(f"\n{'='*50}")
    print(f"SCRAPE RESULT FOR DATE: {target_date}")
    print(f"{ '='*50}")
    print(f"  Status: {result.get('status')}")
    print(f"  Session ID: {result.get('session_id')}")

    if result.get('status') == 'skipped':
        print(f"\n  [SKIPPED] Already has successful scrape for this date")
        print(f"  Previous Success Count: {result.get('articles_success', 0)}")
        print(f"\n  Use --force to scrape again.")
    elif result.get('status') == 'completed':
        print(f"\n  Articles Found: {result.get('articles_found', 0)}")
        print(f"  Articles Scraped: {result.get('articles_scraped', 0)}")
        print(f"  ---------------------")
        print(f"  SUCCESS: {result.get('articles_success', 0)} (counted)")
        print(f"  FAILED: {result.get('articles_failed', 0)} (not counted)")
        print(f"  SKIPPED: {result.get('articles_skipped', 0)} (wrong date)")
        print(f"  ---------------------")
        print(f"  New Articles: {result.get('articles_new', 0)}")
        print(f"  Updated Articles: {result.get('articles_updated', 0)}")
    else:
        print(f"  Error: {result.get('error')}")

    print(f"{ '='*50}\n")


async def test_single_url(url: str, target_date: date = None) -> None:
    """Test scraping a single URL."""
    logger = setup_logging(settings.log_level, settings.log_file)
    logger.info(f"Testing single URL: {url}")

    scrape_service = ScrapeService()
    result = await scrape_service.scrape_single_article(url, target_date=target_date)

    if result:
        print(f"\n{'='*50}")
        print(f"ARTICLE DATA")
        print(f"{ '='*50}")
        print(f"  ID: {result.get('sge_id')}")
        print(f"  Title: {result.get('title')}")
        print(f"  Subtitle: {(result.get('subtitle') or '')[:100]}...")
        print(f"  Category: {result.get('category')}")
        print(f"  Tags: {result.get('tags')}")
        print(f"  Author: {result.get('author_name')}")
        print(f"  Published: {result.get('published_at')}")

        if target_date:
            date_valid = result.get('date_valid', False)
            print(f"\n  Target Date: {target_date}")
            print(f"  Date Valid: {'YES' if date_valid else 'NO'}")

        print(f"\nSocial Media Content ({result.get('social_contents_count', 0)} items):")
        for sc in result.get('social_contents', []):
            print(f"  - {sc.get('platform')}: {sc.get('content_type')} - {sc.get('url', 'N/A')}")
        print(f"{ '='*50}\n")
    else:
        print("Failed to scrape article")


async def check_status(target_date: date = None) -> None:
    """Check scrape status for a specific date."""
    logger = setup_logging(settings.log_level, settings.log_file)
    target_date = target_date or date.today()
    logger.info(f"Checking status for date: {target_date}")

    scrape_service = ScrapeService()
    result = scrape_service.get_scrape_status_for_date(target_date)

    print(f"\n{'='*50}")
    print(f"SCRAPE STATUS FOR: {target_date}")
    print(f"{ '='*50}")

    if result.get('has_successful_scrape'):
        print(f"  Status: COMPLETED")
        print(f"  Session ID: {result.get('session_id')}")
        print(f"  Articles Success: {result.get('articles_success', 0)}")
        print(f"  Articles Failed: {result.get('articles_failed', 0)}")
        print(f"  Articles New: {result.get('articles_new', 0)}")
        print(f"  Completed At: {result.get('completed_at')}")
    else:
        print(f"  Status: NOT SCRAPED")
        print(f"  No successful scrape for this date yet.")

    print(f"{ '='*50}\n")


def export_to_excel(
    target_date: date = None,
    start_date: date = None,
    end_date: date = None,
    output_path: str = None,
    include_content: bool = False,
) -> None:
    """Export articles to Excel file."""
    logger = setup_logging(settings.log_level, settings.log_file)

    # Determine filter description
    if target_date:
        filter_desc = f"date {target_date}"
    elif start_date and end_date:
        filter_desc = f"date range {start_date} to {end_date}"
    elif start_date:
        filter_desc = f"from {start_date}"
    elif end_date:
        filter_desc = f"until {end_date}"
    else:
        filter_desc = "all articles"

    logger.info(f"Exporting articles to Excel ({filter_desc})...")
    print(f"\n{'='*50}")
    print(f"EXPORT TO EXCEL")
    print(f"{ '='*50}")
    print(f"  Filter: {filter_desc}")
    print(f"  Include Content: {'Yes' if include_content else 'No'}")

    try:
        export_service = ExportService()
        output_file = export_service.export_articles_to_excel(
            output_path=output_path,
            target_date=target_date,
            start_date=start_date,
            end_date=end_date,
            include_content=include_content,
        )

        print(f"\n  Status: SUCCESS")
        print(f"  Output File: {output_file}")
        print(f"{ '='*50}\n")
        logger.info(f"Export completed: {output_file}")

    except ValueError as e:
        print(f"\n  Status: FAILED")
        print(f"  Error: {e}")
        print(f"{ '='*50}\n")
        logger.error(f"Export failed: {e}")

    except Exception as e:
        print(f"\n  Status: ERROR")
        print(f"  Error: {e}")
        print(f"{ '='*50}\n")
        logger.error(f"Export error: {e}")


def list_exports() -> None:
    """List all export files."""
    logger = setup_logging(settings.log_level, settings.log_file)
    logger.info("Listing export files...")

    export_service = ExportService()
    exports = export_service.list_exports()

    print(f"\n{'='*50}")
    print(f"EXPORT FILES")
    print(f"{ '='*50}")

    if not exports:
        print("  No export files found.")
    else:
        print(f"  Total: {len(exports)} files\n")
        for i, exp in enumerate(exports, 1):
            print(f"  {i}. {exp['filename']}")
            print(f"     Size: {exp['size_kb']} KB")
            print(f"     Created: {exp['created_at']}")
            print(f"     Path: {exp['path']}")
            print()

    print(f"{ '='*50}\n")


async def run_scheduled() -> None:
    """Run scraper with scheduler."""
    logger = setup_logging(settings.log_level, settings.log_file)
    logger.info("Starting scheduled scraper...")

    # Create and start scheduler
    scheduler = create_scheduler()
    scheduler.start()

    print(f"Scheduler started. Daily scrape scheduled at {settings.scrape_time}")
    print("Press Ctrl+C to stop...")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cleanup
    scheduler.stop()
    logger.info("Scraper shutdown complete")


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: {date_str}. Use YYYY-MM-DD (e.g., 2024-01-15)"
        )


async def run_manual_login() -> None:
    """Run manual login flow."""
    logger = setup_logging(settings.log_level, settings.log_file)
    logger.info("Starting manual login...")

    scrape_service = ScrapeService()

    async def wait_for_login():
        print("\n" + "="*50)
        print("A browser window has been opened.")
        print("Please log in to the website.")
        print("After you have successfully logged in, please return to this terminal and press Enter.")
        print("="*50 + "\n")
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, sys.stdin.readline)

    result = await scrape_service.login(wait_callback=wait_for_login)
    print(f"\nLogin result: {result.get('message')}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SGE Scraper - Scrape articles from SocialGrowthEngineers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --login
  python main.py --run-once
  python main.py --status
  python main.py --export
        """
    )
    # Scrape options
    parser.add_argument(
        "--login",
        action="store_true",
        help="Run manual login flow to save session"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run scraper once for a specific date and exit"
    )
    parser.add_argument(
        "--date",
        type=parse_date,
        default=None,
        help="Target date for scraping/export (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force scrape even if already has successful scrape for the date"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of articles to scrape (use with --run-once)"
    )
    parser.add_argument(
        "--test-url",
        type=str,
        default=None,
        help="Test scraping a single URL"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check scrape status for a date"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export articles to Excel file"
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        default=None,
        help="Start date for export range (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        default=None,
        help="End date for export range (YYYY-MM-DD format)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for export (default: exports/articles_TIMESTAMP.xlsx)"
    )
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Include full article content in export (can make file large)"
    )
    parser.add_argument(
        "--list-exports",
        action="store_true",
        help="List all export files"
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run database migrations (alembic upgrade head)"
    )
    parser.add_argument(
        "--migrate-status",
        action="store_true",
        help="Check current migration status"
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Run with scheduler (default mode)"
    )
    # API server
    parser.add_argument(
        "--api",
        action="store_true",
        help="Start the API server with Swagger UI"
    )
    parser.add_argument(
        "--api-host",
        default="0.0.0.0",
        help="API host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="API port (default: 8000)"
    )

    args = parser.parse_args()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Handle different modes
    if args.api:
        import uvicorn
        setup_logging(settings.log_level, settings.log_file)
        print(f"Starting SGE Scraper API server on {args.api_host}:{args.api_port}")
        print(f"Swagger UI: http://localhost:{args.api_port}/docs")
        uvicorn.run("api.main:app", host=args.api_host, port=args.api_port, reload=True)
        sys.exit(0)
    elif args.login:
        asyncio.run(run_manual_login())
    elif args.migrate:
        migrate_db()
    elif args.migrate_status:
        migrate_status()
    elif args.list_exports:
        list_exports()
    elif args.export:
        export_to_excel(
            target_date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
            output_path=args.output,
            include_content=args.include_content,
        )
    elif args.status:
        asyncio.run(check_status(target_date=args.date))
    elif args.test_url:
        asyncio.run(test_single_url(args.test_url, target_date=args.date))
    elif args.run_once:
        asyncio.run(run_once(
            limit=args.limit,
            target_date=args.date,
            force=args.force
        ))
    else:
        # Default: run scheduled
        asyncio.run(run_scheduled())


if __name__ == "__main__":
    main()
