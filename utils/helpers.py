import asyncio
import re
from functools import wraps
from typing import Callable, TypeVar, Any
from bs4 import BeautifulSoup

from config.logging_config import get_logger

T = TypeVar("T")


def retry_async(
    max_retries: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        delay_seconds: Initial delay between retries.
        backoff_factor: Multiplier for delay after each retry.
        exceptions: Tuple of exceptions to catch and retry.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            logger = get_logger()
            last_exception = None
            current_delay = delay_seconds

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


def clean_html(html: str) -> str:
    """
    Clean HTML content by removing scripts, styles, and excessive whitespace.

    Args:
        html: Raw HTML string.

    Returns:
        Cleaned HTML string.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove script and style elements
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    # Get cleaned HTML
    cleaned = str(soup)

    # Remove excessive whitespace
    cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    return cleaned.strip()


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.

    Args:
        text: String to truncate.
        max_length: Maximum length including suffix.
        suffix: Suffix to add if truncated.

    Returns:
        Truncated string.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def extract_domain(url: str) -> str:
    """
    Extract domain from URL.

    Args:
        url: Full URL string.

    Returns:
        Domain string.
    """
    match = re.search(r"https?://([^/]+)", url)
    return match.group(1) if match else ""


def normalize_url(url: str) -> str:
    """
    Normalize URL by removing trailing slashes and query parameters.

    Args:
        url: URL to normalize.

    Returns:
        Normalized URL.
    """
    # Remove query string and fragment
    url = re.sub(r"[?#].*$", "", url)
    # Remove trailing slash
    url = url.rstrip("/")
    return url


def parse_read_time(text: str) -> int:
    """
    Parse read time string to minutes.

    Args:
        text: Read time text like "5 min read" or "5 minutes".

    Returns:
        Number of minutes as integer.
    """
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 0
