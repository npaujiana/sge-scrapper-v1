"""TikTok authentication service for screenshot feature."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from config.settings import settings
from config.logging_config import get_logger


def _run_tiktok_manual_login(session_dir: str) -> Tuple[bool, str]:
    """
    Run Playwright for manual TikTok login.
    Opens browser for user to login manually.
    """
    from playwright.sync_api import sync_playwright

    print("[TIKTOK] Starting manual login...")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=False,  # Must be visible for manual login
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
            )
            try:
                context = browser.new_context(
                    viewport={"width": 375, "height": 667},  # Mobile viewport
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                )
                page = context.new_page()

                # Navigate to TikTok login
                print("[TIKTOK] Opening TikTok login page...")
                page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                print("[TIKTOK] Please login manually in the browser window.")
                print("[TIKTOK] After login, the browser will close automatically.")
                print("[TIKTOK] Waiting for login (max 5 minutes)...")

                # Wait for successful login (check for profile/avatar)
                max_wait = 300  # 5 minutes
                check_interval = 2  # Check every 2 seconds
                waited = 0

                while waited < max_wait:
                    page.wait_for_timeout(check_interval * 1000)
                    waited += check_interval

                    # Check if logged in by looking for profile indicators
                    current_url = page.url

                    # If redirected away from login page
                    if "/login" not in current_url.lower():
                        # Check for avatar or profile elements
                        profile_indicators = [
                            '[data-e2e="profile-icon"]',
                            'div[data-e2e="nav-avatar"]',
                            'a[href*="/profile"]',
                            'button[aria-label*="Profile"]',
                        ]

                        for selector in profile_indicators:
                            if page.query_selector(selector):
                                print(f"[TIKTOK] Login detected! Saving session...")

                                # Save session
                                session_path = Path(session_dir)
                                session_path.mkdir(exist_ok=True)

                                storage_state = context.storage_state()
                                with open(session_path / "tiktok_storage_state.json", "w") as f:
                                    json.dump(storage_state, f, indent=2)

                                # Save session metadata
                                session_data = {
                                    "logged_in": True,
                                    "saved_at": datetime.now().isoformat(),
                                    "expires_at": (datetime.now() + timedelta(days=14)).isoformat(),
                                }
                                with open(session_path / "tiktok_session.json", "w") as f:
                                    json.dump(session_data, f, indent=2)

                                return True, "TikTok login successful! Session saved."

                    # Also check on login page if already logged in
                    if page.query_selector('[data-e2e="profile-icon"]'):
                        print("[TIKTOK] Already logged in!")
                        storage_state = context.storage_state()
                        session_path = Path(session_dir)
                        session_path.mkdir(exist_ok=True)
                        with open(session_path / "tiktok_storage_state.json", "w") as f:
                            json.dump(storage_state, f, indent=2)
                        session_data = {
                            "logged_in": True,
                            "saved_at": datetime.now().isoformat(),
                            "expires_at": (datetime.now() + timedelta(days=14)).isoformat(),
                        }
                        with open(session_path / "tiktok_session.json", "w") as f:
                            json.dump(session_data, f, indent=2)
                        return True, "TikTok login successful! Session saved."

                return False, "Login timeout. Please try again."

            finally:
                browser.close()

    except Exception as e:
        import traceback
        print(f"[TIKTOK] Error: {e}")
        traceback.print_exc()
        return False, f"Login error: {str(e)}"


class TikTokAuthService:
    """Handle TikTok authentication for screenshot feature."""

    SESSION_FILE = "tiktok_session.json"
    STORAGE_STATE_FILE = "tiktok_storage_state.json"

    def __init__(self):
        self.logger = get_logger()
        self.session_dir = settings.project_root / "session"
        self.session_dir.mkdir(exist_ok=True)
        self.session_file = self.session_dir / self.SESSION_FILE
        self.storage_state_file = self.session_dir / self.STORAGE_STATE_FILE

    def login_manual(self) -> Tuple[bool, str]:
        """
        Start manual login process for TikTok.
        Opens browser for user to login.

        Returns:
            Tuple of (success, message)
        """
        self.logger.info("Starting TikTok manual login...")
        return _run_tiktok_manual_login(str(self.session_dir))

    def has_valid_session(self) -> Tuple[bool, Optional[str]]:
        """
        Check if there's a valid TikTok session.

        Returns:
            Tuple of (has_session, expires_at)
        """
        if not self.session_file.exists() or not self.storage_state_file.exists():
            return False, None

        try:
            with open(self.session_file, "r") as f:
                session_data = json.load(f)

            expires_at_str = session_data.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() > expires_at:
                    self.logger.info("TikTok session expired")
                    return False, None
                return True, expires_at_str

            return session_data.get("logged_in", False), None

        except Exception as e:
            self.logger.warning(f"Error checking TikTok session: {e}")
            return False, None

    def get_storage_state_path(self) -> Optional[str]:
        """Get path to storage state file if session is valid."""
        has_session, _ = self.has_valid_session()
        if has_session and self.storage_state_file.exists():
            return str(self.storage_state_file)
        return None

    def clear_session(self) -> None:
        """Clear TikTok session."""
        if self.session_file.exists():
            self.session_file.unlink()
        if self.storage_state_file.exists():
            self.storage_state_file.unlink()
        self.logger.info("TikTok session cleared")

    def get_status(self) -> dict:
        """Get TikTok session status."""
        has_session, expires_at = self.has_valid_session()
        return {
            "has_session": has_session,
            "expires_at": expires_at,
            "storage_state_exists": self.storage_state_file.exists(),
        }
