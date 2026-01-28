#!/usr/bin/env python3
"""
SGE Scraper - Run All Script

Script ini akan:
1. Load environment variables
2. Run database migrations (alembic upgrade head)
3. Install Playwright browser jika belum ada
4. Menjalankan API server

Usage:
    python run_all.py                    # Run API server
    python run_all.py --skip-migrate     # Skip database migration
    python run_all.py --skip-browser-check  # Skip Playwright check
"""

import subprocess
import sys
import asyncio
from pathlib import Path

# Fix Windows asyncio subprocess issue
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def print_header():
    """Print application header."""
    print("=" * 60)
    print("        SGE SCRAPER - Social Growth Engineers")
    print("=" * 60)
    print()


def run_migrations():
    """Run database migrations using Alembic."""
    print("[1/3] Running database migrations (alembic upgrade head)...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("      Database migrations: OK")
        if result.stdout:
            # Show migration output if any
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    print(f"      {line}")
        return True
    else:
        print(f"      Database migrations: FAILED")
        print(f"      Error: {result.stderr}")
        return False


def install_playwright():
    """Install Playwright browsers."""
    print("      Installing Playwright browsers...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("      Playwright install: OK")
        return True
    else:
        print(f"      Playwright install: FAILED")
        print(f"      Error: {result.stderr}")
        return False


def check_playwright():
    """Check if Playwright browsers are installed."""
    print("[2/3] Checking Playwright browser...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Just check if chromium is available
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("      Playwright browser: OK")
        return True
    except Exception as e:
        error_msg = str(e)
        if "Executable doesn't exist" in error_msg or "install" in error_msg.lower():
            print("      Playwright browser: NOT FOUND, installing...")
            return None  # Signal to install
        else:
            print(f"      Playwright browser: ERROR")
            print(f"      Error: {e}")
            return False


def run_api_server():
    """Run the API server."""
    import uvicorn
    from config.settings import settings
    from config.logging_config import setup_logging

    # Ensure Windows event loop policy is set
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    setup_logging()

    print()
    print("=" * 60)
    print("                   SGE Scraper API")
    print("=" * 60)
    print(f"  Server starting on http://{settings.api_host}:{settings.api_port}")
    print()
    print("  Documentation:")
    print(f"  - Swagger UI: http://localhost:{settings.api_port}/docs")
    print(f"  - ReDoc:      http://localhost:{settings.api_port}/redoc")
    print(f"  - OpenAPI:    http://localhost:{settings.api_port}/openapi.json")
    print("=" * 60)
    print()

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,  # Disabled for Windows subprocess compatibility
        log_level="info",
        loop="asyncio",
    )


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="SGE Scraper - Run All")
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Skip database migration"
    )
    parser.add_argument(
        "--skip-browser-check",
        action="store_true",
        help="Skip Playwright browser check"
    )

    args = parser.parse_args()

    print_header()

    # Step 1: Run migrations
    if not args.skip_migrate:
        if not run_migrations():
            print("\nFailed to run migrations. Exiting.")
            sys.exit(1)
    else:
        print("[1/3] Skipping migrations (--skip-migrate)")

    # Step 2 & 3: Check and install Playwright
    if not args.skip_browser_check:
        check_result = check_playwright()

        if check_result is None:
            # Need to install
            if not install_playwright():
                print("\nFailed to install Playwright. Try manually: playwright install chromium")
                sys.exit(1)

            # Re-check after install
            print("[2/3] Re-checking Playwright browser...")
            if not check_playwright():
                print("\nPlaywright still not working after install. Exiting.")
                sys.exit(1)
        elif check_result is False:
            print("\nPlaywright check failed. Use --skip-browser-check to skip.")
            sys.exit(1)
    else:
        print("[2/3] Skipping Playwright check (--skip-browser-check)")

    # Run API server
    run_api_server()


if __name__ == "__main__":
    main()
