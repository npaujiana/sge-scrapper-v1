"""Authentication service for SGE website login."""
import asyncio
import json
import os
import sys
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
from playwright.async_api import Page, BrowserContext

from config.settings import settings
from config.logging_config import get_logger

# Process pool for running Playwright in separate process (Windows compatibility)
_executor = None

def _get_executor():
    """Get or create process pool executor."""
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=2)
    return _executor


def _run_playwright_request_code(email: str, login_url: str, session_dir: str) -> Tuple[bool, str]:
    """
    Run Playwright in separate process to request login code.
    This function runs in a separate process to avoid Windows asyncio issues.
    """
    from playwright.sync_api import sync_playwright
    import json
    from datetime import datetime
    from pathlib import Path

    print(f"[PROCESS] Starting Playwright for {email}...")

    try:
        with sync_playwright() as playwright:
            print("[PROCESS] Playwright started, launching browser...")
            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
            )
            try:
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = context.new_page()

                # Navigate to login page
                print(f"[PROCESS] Navigating to {login_url}...")
                page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # Find and fill email input
                email_input = page.query_selector('input[type="email"], input[name="email"], input[placeholder*="email" i]')
                if not email_input:
                    email_input = page.query_selector('input[type="text"]')

                if not email_input:
                    return False, "Could not find email input field on login page"

                # Clear and fill email
                print(f"[PROCESS] Filling email: {email}")
                email_input.fill("")
                email_input.fill(email)
                page.wait_for_timeout(500)

                # Find and click submit button
                submit_button = page.query_selector('button[type="submit"], input[type="submit"], button:has-text("Continue"), button:has-text("Send"), button:has-text("Login"), button:has-text("Sign in")')

                if not submit_button:
                    return False, "Could not find submit button on login page"

                # Click submit
                print("[PROCESS] Clicking submit button...")
                submit_button.click()
                page.wait_for_timeout(3000)

                # Check if we're now on code verification page
                code_input = page.query_selector('input[name="code"], input[type="text"][maxlength="6"], input[placeholder*="code" i], input[placeholder*="verification" i]')

                page_text = page.content()
                is_code_page = (
                    code_input is not None or
                    "verification" in page_text.lower() or
                    "code" in page_text.lower() or
                    "check your email" in page_text.lower()
                )

                if is_code_page:
                    # Save login state
                    state_file = Path(session_dir) / "login_state.json"
                    state = {
                        "email": email,
                        "status": "code_requested",
                        "timestamp": datetime.now().isoformat()
                    }
                    with open(state_file, "w") as f:
                        json.dump(state, f)

                    print(f"[PROCESS] Login code requested successfully for {email}")
                    return True, f"Verification code has been sent to {email}. Please check your email."
                else:
                    # Check for error messages
                    error_elem = page.query_selector('.error, .alert-error, [role="alert"], .text-red-500, .text-danger')
                    if error_elem:
                        error_text = error_elem.text_content()
                        return False, f"Login error: {error_text}"

                    return False, "Could not verify if login code was sent. Please check login page."
            finally:
                browser.close()

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[PROCESS] Error: {e}\n{error_detail}")
        return False, f"Error requesting login code: {type(e).__name__}: {str(e)}"


def _run_playwright_verify_code(code: str, email: str, login_url: str, session_dir: str) -> Tuple[bool, str]:
    """
    Run Playwright in separate process to verify login code.
    This function runs in a separate process to avoid Windows asyncio issues.
    """
    from playwright.sync_api import sync_playwright
    import json
    from datetime import datetime, timedelta
    from pathlib import Path

    print(f"[PROCESS] Starting Playwright to verify code for {email}...")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
            )
            try:
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = context.new_page()

                # Navigate to login page and enter email first
                print(f"[PROCESS] Navigating to {login_url}...")
                page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                email_input = page.query_selector('input[type="email"], input[name="email"], input[placeholder*="email" i]')
                if email_input:
                    print(f"[PROCESS] Filling email: {email}")
                    email_input.fill(email)
                    submit_button = page.query_selector('button[type="submit"], input[type="submit"], button:has-text("Continue"), button:has-text("Send")')
                    if submit_button:
                        print("[PROCESS] Clicking submit to get code page...")
                        submit_button.click()
                        page.wait_for_timeout(4000)

                # Debug: print current URL and page content snippet
                print(f"[PROCESS] Current URL: {page.url}")

                # Try multiple selectors for code input
                code_selectors = [
                    'input[name="code"]',
                    'input[name="token"]',
                    'input[name="otp"]',
                    'input[name="verification"]',
                    'input[type="text"][maxlength="6"]',
                    'input[type="text"][maxlength="4"]',
                    'input[type="number"][maxlength="6"]',
                    'input[type="number"]',
                    'input[placeholder*="code" i]',
                    'input[placeholder*="verification" i]',
                    'input[placeholder*="otp" i]',
                    'input[placeholder*="token" i]',
                    'input[autocomplete="one-time-code"]',
                    # Generic fallbacks
                    'input[type="text"]:not([name="email"]):not([type="email"])',
                    'input[type="tel"]',
                ]

                code_input = None
                for selector in code_selectors:
                    code_input = page.query_selector(selector)
                    if code_input:
                        print(f"[PROCESS] Found code input with selector: {selector}")
                        break

                # If still not found, try to find any visible input
                if not code_input:
                    all_inputs = page.query_selector_all('input:visible')
                    print(f"[PROCESS] Found {len(all_inputs)} visible inputs")
                    for inp in all_inputs:
                        inp_type = inp.get_attribute('type') or 'text'
                        inp_name = inp.get_attribute('name') or ''
                        inp_placeholder = inp.get_attribute('placeholder') or ''
                        print(f"[PROCESS] Input: type={inp_type}, name={inp_name}, placeholder={inp_placeholder}")
                        if inp_type not in ['email', 'hidden', 'submit', 'button'] and inp_name != 'email':
                            code_input = inp
                            print(f"[PROCESS] Using input: {inp_name or inp_placeholder}")
                            break

                if not code_input:
                    # Save screenshot for debugging
                    screenshot_path = Path(session_dir) / "debug_verify_page.png"
                    page.screenshot(path=str(screenshot_path))
                    print(f"[PROCESS] Screenshot saved to {screenshot_path}")
                    return False, f"Could not find code input field. Screenshot saved for debugging. URL: {page.url}"

                # Fill code
                print(f"[PROCESS] Filling verification code...")
                code_input.fill("")
                code_input.fill(code)
                page.wait_for_timeout(500)

                # Find and click verify/submit button
                verify_button_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Verify")',
                    'button:has-text("Submit")',
                    'button:has-text("Login")',
                    'button:has-text("Sign in")',
                    'button:has-text("Continue")',
                    # Generic fallback
                    'button',
                ]
                verify_button = None
                for selector in verify_button_selectors:
                    verify_button = page.query_selector(selector)
                    if verify_button:
                        print(f"[PROCESS] Found verify button with selector: {selector}")
                        break

                if not verify_button:
                    return False, "Could not find verify button"

                # Click verify
                verify_button.click()
                page.wait_for_timeout(10000) # Increased delay to 10 seconds

                # Check if login was successful
                current_url = page.url

                def check_login_status():
                    indicators = [
                        'button:has-text("Logout")',
                        'button:has-text("Sign out")',
                        'a:has-text("Logout")',
                        'a:has-text("Sign out")',
                        '[data-testid="user-menu"]',
                        '.user-avatar',
                        '.user-profile',
                        'a[href*="dashboard"]',
                        'a[href*="account"]',
                    ]
                    for selector in indicators:
                        if page.query_selector(selector):
                            return True
                    if "/login" not in current_url.lower() and "/signin" not in current_url.lower():
                        if not page.query_selector('input[type="email"], form[action*="login"]'):
                            return True
                    return False

                def save_session():
                    storage_state = context.storage_state()
                    session_path = Path(session_dir)
                    session_path.mkdir(exist_ok=True)

                    # Save storage state
                    with open(session_path / "storage_state.json", "w") as f:
                        json.dump(storage_state, f, indent=2)

                    # Save session data
                    session_data = {
                        "email": email,
                        "cookies": storage_state.get("cookies", []),
                        "storage_state": storage_state,
                        "saved_at": datetime.now().isoformat(),
                        "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
                    }
                    with open(session_path / "session_data.json", "w") as f:
                        json.dump(session_data, f, indent=2)

                    # Clear login state
                    login_state_file = session_path / "login_state.json"
                    if login_state_file.exists():
                        login_state_file.unlink()

                # Check if we're redirected away from login page
                if "/login" not in current_url.lower() and "/signin" not in current_url.lower():
                    save_session()
                    return True, f"Login successful for {email}"

                # Double check login status
                if check_login_status():
                    save_session()
                    return True, f"Login successful for {email}"

                # Check for error messages
                error_elem = page.query_selector('.error, .alert-error, [role="alert"], .text-red-500, .text-danger')
                if error_elem:
                    error_text = error_elem.text_content()
                    return False, f"Verification failed: {error_text}"

                return False, "Could not verify login. Please try again."
            finally:
                browser.close()

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[PROCESS] Error: {e}\n{error_detail}")
        return False, f"Error verifying login code: {type(e).__name__}: {str(e)}"


class AuthService:
    """Handle authentication with SGE website."""

    LOGIN_URL = "https://www.socialgrowthengineers.com/login"
    SESSION_FILE = "session_data.json"
    LOGIN_STATE_FILE = "login_state.json"

    def __init__(self):
        self.logger = get_logger()
        self.session_dir = settings.project_root / "session"
        self.session_dir.mkdir(exist_ok=True)
        self.session_file = self.session_dir / self.SESSION_FILE
        self.login_state_file = self.session_dir / self.LOGIN_STATE_FILE
        self._pending_email: Optional[str] = None
        self._browser_manager = None
        self._page: Optional[Page] = None

    def _save_login_state(self, email: str, status: str) -> None:
        """Save login state to file for persistence."""
        state = {
            "email": email,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        with open(self.login_state_file, "w") as f:
            json.dump(state, f)

    def _load_login_state(self) -> Optional[dict]:
        """Load login state from file."""
        if not self.login_state_file.exists():
            return None
        try:
            with open(self.login_state_file, "r") as f:
                state = json.load(f)
            # Check if state is still fresh (within 10 minutes)
            timestamp = datetime.fromisoformat(state["timestamp"])
            if datetime.now() - timestamp > timedelta(minutes=10):
                self._clear_login_state()
                return None
            return state
        except Exception:
            return None

    def _clear_login_state(self) -> None:
        """Clear login state file."""
        if self.login_state_file.exists():
            self.login_state_file.unlink()
        self._pending_email = None

    async def request_login_code(self, email: str) -> Tuple[bool, str]:
        """
        Request login code by submitting email to SGE login page.

        Args:
            email: User's email address

        Returns:
            Tuple of (success, message)
        """
        self.logger.info(f"Requesting login code for {email}...")
        print(f"[DEBUG] request_login_code called for {email}")

        loop = asyncio.get_running_loop()
        executor = _get_executor()

        result = await loop.run_in_executor(
            executor,
            _run_playwright_request_code,
            email,
            self.LOGIN_URL,
            str(self.session_dir)
        )

        print(f"[DEBUG] Result: {result}")
        return result

    async def verify_login_code(self, code: str, email: Optional[str] = None) -> Tuple[bool, str]:
        """
        Verify login code and complete authentication.

        Args:
            code: Verification code from email
            email: Email address (optional, uses pending email if not provided)

        Returns:
            Tuple of (success, message)
        """
        # Get email from parameter, pending state, or saved state
        target_email = email or self._pending_email
        if not target_email:
            state = self._load_login_state()
            if state:
                target_email = state.get("email")

        if not target_email:
            return False, "No pending login session. Please request a login code first."

        self.logger.info(f"Verifying login code for {target_email}...")

        loop = asyncio.get_running_loop()
        executor = _get_executor()

        result = await loop.run_in_executor(
            executor,
            _run_playwright_verify_code,
            code,
            target_email,
            self.LOGIN_URL,
            str(self.session_dir)
        )

        return result

    def get_login_status(self) -> dict:
        """Get current login/session status."""
        has_session, email = self.has_valid_session()

        # Check if there's a pending login
        pending_state = self._load_login_state()

        return {
            "logged_in": has_session,
            "email": email,
            "pending_login": pending_state is not None,
            "pending_email": pending_state.get("email") if pending_state else None,
        }

    async def login_manual(
        self,
        page: Page,
        wait_callback,
    ) -> bool:
        """
        Open login page and let user login manually.

        Args:
            page: Playwright page instance
            wait_callback: Async function to wait for user to complete login

        Returns:
            True if login successful, False otherwise
        """
        self.logger.info("Opening login page for manual login...")

        try:
            # Navigate to login page
            await page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            self.logger.info("Login page opened. Waiting for user to complete login...")

            # Wait for user to complete login
            await wait_callback()

            # Check if login successful
            await asyncio.sleep(2)
            current_url = page.url

            # If not on login page anymore, consider success
            if "/login" not in current_url.lower() and "/signin" not in current_url.lower():
                self.logger.info("Login successful!")
                return True

            # Double check with page content
            is_logged_in = await self._check_login_status(page)
            if is_logged_in:
                self.logger.info("Login successful!")
                return True

            self.logger.warning("Could not verify login. Current URL: " + current_url)
            return False

        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return False

    async def _check_login_status(self, page: Page) -> bool:
        """Check if user is logged in."""
        try:
            # Check for common logged-in indicators
            # Look for logout button, user menu, dashboard, etc.
            indicators = [
                'button:has-text("Logout")',
                'button:has-text("Sign out")',
                'a:has-text("Logout")',
                'a:has-text("Sign out")',
                '[data-testid="user-menu"]',
                '.user-avatar',
                '.user-profile',
                'a[href*="dashboard"]',
                'a[href*="account"]',
            ]

            for selector in indicators:
                element = await page.query_selector(selector)
                if element:
                    return True

            # Check if we're NOT on login page anymore
            current_url = page.url
            if "/login" not in current_url.lower() and "/signin" not in current_url.lower():
                # Additional check - see if there's no login form
                login_form = await page.query_selector('input[type="email"], form[action*="login"]')
                if not login_form:
                    return True

            return False

        except Exception as e:
            self.logger.warning(f"Error checking login status: {e}")
            return False

    async def save_session(self, context: BrowserContext, email: str) -> bool:
        """Save browser session/cookies for later use."""
        try:
            # Get cookies
            cookies = await context.cookies()

            # Get storage state
            storage_state = await context.storage_state()

            session_data = {
                "email": email,
                "cookies": cookies,
                "storage_state": storage_state,
                "saved_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
            }

            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            self.logger.info(f"Session saved for {email}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save session: {e}")
            return False

    async def load_session(self, context: BrowserContext) -> Optional[str]:
        """
        Load saved session into browser context.

        Returns:
            Email if session loaded successfully, None otherwise
        """
        if not self.session_file.exists():
            self.logger.info("No saved session found")
            return None

        try:
            with open(self.session_file, "r") as f:
                session_data = json.load(f)

            # Check if session expired
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.now() > expires_at:
                self.logger.info("Session expired")
                self.clear_session()
                return None

            # Load cookies
            cookies = session_data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)

            self.logger.info(f"Session loaded for {session_data['email']}")
            return session_data["email"]

        except Exception as e:
            self.logger.error(f"Failed to load session: {e}")
            return None

    def save_token_session(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: int,
        email: Optional[str] = None
    ) -> bool:
        """
        Save token-based session (from localStorage).

        Args:
            access_token: JWT access token
            refresh_token: Refresh token
            expires_at: Token expiration timestamp
            email: User's email (optional, will be extracted from token if not provided)

        Returns:
            True if saved successfully
        """
        try:
            import base64

            # Extract email from token if not provided
            if not email:
                try:
                    # JWT format: header.payload.signature
                    payload = access_token.split('.')[1]
                    # Add padding if needed
                    payload += '=' * (4 - len(payload) % 4)
                    decoded = base64.b64decode(payload)
                    token_data = json.loads(decoded)
                    email = token_data.get('email', 'unknown@email.com')
                except Exception:
                    email = 'unknown@email.com'

            # Create token data structure (matching localStorage format)
            token_data = {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 3600,
                "expires_at": expires_at,
                "refresh_token": refresh_token,
            }

            # Create storage state with localStorage
            storage_state = {
                "cookies": [],
                "origins": [
                    {
                        "origin": "https://www.socialgrowthengineers.com",
                        "localStorage": [
                            {
                                "name": "sge-auth-token",
                                "value": json.dumps(token_data)
                            }
                        ]
                    }
                ]
            }

            # Save storage state file
            self.session_dir.mkdir(exist_ok=True)
            storage_file = self.session_dir / "storage_state.json"
            with open(storage_file, "w") as f:
                json.dump(storage_state, f, indent=2)

            # Save session data
            session_data = {
                "email": email,
                "auth_type": "token",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "storage_state": storage_state,
                "saved_at": datetime.now().isoformat(),
                "expires_at_iso": datetime.fromtimestamp(expires_at).isoformat(),
            }

            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            self.logger.info(f"Token session saved for {email}, expires at {datetime.fromtimestamp(expires_at)}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save token session: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_manual_session(self, email: str, cookies: list) -> bool:
        """
        Save session manually from browser cookies.

        Args:
            email: User's email address
            cookies: List of cookie dicts from browser

        Returns:
            True if saved successfully
        """
        try:
            # Ensure cookies have required fields
            processed_cookies = []
            for cookie in cookies:
                processed_cookie = {
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain", ".www.socialgrowthengineers.com"),
                    "path": cookie.get("path", "/"),
                }
                # Optional fields
                if "expires" in cookie:
                    processed_cookie["expires"] = cookie["expires"]
                if "httpOnly" in cookie:
                    processed_cookie["httpOnly"] = cookie["httpOnly"]
                if "secure" in cookie:
                    processed_cookie["secure"] = cookie["secure"]
                if "sameSite" in cookie:
                    processed_cookie["sameSite"] = cookie["sameSite"]

                processed_cookies.append(processed_cookie)

            # Create storage state format
            storage_state = {
                "cookies": processed_cookies,
                "origins": []
            }

            # Save storage state file
            self.session_dir.mkdir(exist_ok=True)
            storage_file = self.session_dir / "storage_state.json"
            with open(storage_file, "w") as f:
                json.dump(storage_state, f, indent=2)

            # Save session data
            session_data = {
                "email": email,
                "cookies": processed_cookies,
                "storage_state": storage_state,
                "saved_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
            }

            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            self.logger.info(f"Manual session saved for {email} with {len(processed_cookies)} cookies")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save manual session: {e}")
            return False

    def clear_session(self) -> None:
        """Clear saved session."""
        if self.session_file.exists():
            self.session_file.unlink()
            self.logger.info("Session cleared")

    def has_valid_session(self) -> Tuple[bool, Optional[str]]:
        """Check if there's a valid saved session."""
        if not self.session_file.exists():
            return False, None

        try:
            with open(self.session_file, "r") as f:
                session_data = json.load(f)

            # Check for token-based session
            if session_data.get("auth_type") == "token":
                expires_at = session_data.get("expires_at")
                if expires_at and datetime.now().timestamp() > expires_at:
                    return False, None
                return True, session_data.get("email")

            # Check for cookie-based session (old format)
            expires_at_str = session_data.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now() > expires_at:
                        return False, None
                except (ValueError, TypeError):
                    pass

            return True, session_data.get("email")

        except Exception:
            return False, None

    async def verify_session(self, page: Page) -> bool:
        """Verify if current session is still valid by checking login status."""
        try:
            # Navigate to a page that requires login
            await page.goto(settings.base_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            return await self._check_login_status(page)

        except Exception as e:
            self.logger.error(f"Session verification failed: {e}")
            return False
