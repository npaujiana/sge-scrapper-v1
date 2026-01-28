import asyncio
import json
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from config.settings import settings
from config.logging_config import get_logger


class BrowserManager:
    """Manage Playwright browser instance."""

    def __init__(self, headless: bool = True):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._headless = headless
        self.logger = get_logger()

    async def start(self, load_session: bool = False) -> None:
        """Start the browser."""
        if self._browser is not None:
            return

        self.logger.info("Starting Playwright browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-sandbox",
            ]
        )

        # Check if we should load existing session
        session_file = settings.project_root / "session" / "storage_state.json"
        storage_state = None

        if load_session and session_file.exists():
            try:
                storage_state = str(session_file)
                self.logger.info("Loading saved session...")
            except Exception as e:
                self.logger.warning(f"Could not load session: {e}")

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=storage_state,
        )
        self.logger.info("Browser started successfully")

    async def save_session(self) -> bool:
        """Save current browser session."""
        if self._context is None:
            return False

        try:
            session_dir = settings.project_root / "session"
            session_dir.mkdir(exist_ok=True)
            session_file = session_dir / "storage_state.json"

            await self._context.storage_state(path=str(session_file))
            self.logger.info("Session saved successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save session: {e}")
            return False

    @property
    def context(self) -> Optional[BrowserContext]:
        """Get the browser context."""
        return self._context

    async def stop(self) -> None:
        """Stop the browser."""
        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self.logger.info("Browser stopped")

    async def new_page(self) -> Page:
        """Create a new page in the browser context."""
        if self._context is None:
            await self.start()
        return await self._context.new_page()

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
