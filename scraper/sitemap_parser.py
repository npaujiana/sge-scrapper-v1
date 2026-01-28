import asyncio
from datetime import datetime, date
from typing import List, Set, Dict, Optional, Tuple
from xml.etree import ElementTree
import httpx

from config.settings import settings
from config.logging_config import get_logger


class SitemapParser:
    """Parse sitemap XML files to extract article URLs."""

    SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def __init__(self):
        self.logger = get_logger()

    async def fetch_sitemap(self, url: str) -> str:
        """Fetch sitemap XML content from URL."""
        self.logger.debug(f"Fetching sitemap: {url}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def parse_urls(self, xml_content: str) -> List[str]:
        """Parse URLs from sitemap XML content."""
        urls = []
        try:
            root = ElementTree.fromstring(xml_content)

            # Handle regular sitemap
            for url_elem in root.findall(".//sm:url/sm:loc", self.SITEMAP_NS):
                if url_elem.text:
                    urls.append(url_elem.text.strip())

            # Handle sitemap index (nested sitemaps)
            for sitemap_elem in root.findall(".//sm:sitemap/sm:loc", self.SITEMAP_NS):
                if sitemap_elem.text:
                    urls.append(sitemap_elem.text.strip())

        except ElementTree.ParseError as e:
            self.logger.error(f"Failed to parse sitemap XML: {e}")

        return urls

    def parse_urls_with_dates(self, xml_content: str) -> List[Tuple[str, Optional[datetime]]]:
        """Parse URLs with their lastmod dates from sitemap XML content."""
        url_data = []
        try:
            root = ElementTree.fromstring(xml_content)

            # Handle regular sitemap
            for url_elem in root.findall(".//sm:url", self.SITEMAP_NS):
                loc_elem = url_elem.find("sm:loc", self.SITEMAP_NS)
                lastmod_elem = url_elem.find("sm:lastmod", self.SITEMAP_NS)

                if loc_elem is not None and loc_elem.text:
                    url = loc_elem.text.strip()
                    lastmod = None

                    if lastmod_elem is not None and lastmod_elem.text:
                        lastmod = self._parse_date(lastmod_elem.text.strip())

                    url_data.append((url, lastmod))

            # Handle sitemap index (nested sitemaps)
            for sitemap_elem in root.findall(".//sm:sitemap", self.SITEMAP_NS):
                loc_elem = sitemap_elem.find("sm:loc", self.SITEMAP_NS)
                if loc_elem is not None and loc_elem.text:
                    url_data.append((loc_elem.text.strip(), None))

        except ElementTree.ParseError as e:
            self.logger.error(f"Failed to parse sitemap XML: {e}")

        return url_data

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from sitemap."""
        try:
            # Try ISO format with timezone
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        try:
            # Try date only format (YYYY-MM-DD)
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            pass

        return None

    def filter_article_urls(self, urls: List[str]) -> List[str]:
        """Filter URLs to only include article pages."""
        article_urls = []
        exclude_patterns = [
            "/category/",
            "/tag/",
            "/author/",
            "/page/",
            "/sitemap",
            ".xml",
        ]
        # Exact paths to exclude (non-article pages)
        exclude_exact = [
            "/apps",
            "/resources",
            "/reports",
            "/join",
            "/about",
            "/advertise",
            "/formats",
            "/privacy-policy",
            "/terms-of-service",
            "/mysge",
        ]

        for url in urls:
            # Skip non-article URLs
            if any(pattern in url.lower() for pattern in exclude_patterns):
                continue

            # Only include URLs from the main domain
            if settings.base_url in url:
                # Skip homepage
                if url.rstrip("/") == settings.base_url:
                    continue
                # Skip exact non-article pages
                path = url.replace(settings.base_url, "").rstrip("/")
                if path in exclude_exact:
                    continue
                article_urls.append(url)

        return article_urls

    async def get_all_article_urls(self) -> List[str]:
        """Fetch and parse all sitemaps to get article URLs."""
        all_urls: Set[str] = set()

        for sitemap_url in settings.sitemap_urls:
            try:
                xml_content = await self.fetch_sitemap(sitemap_url)
                urls = self.parse_urls(xml_content)
                article_urls = self.filter_article_urls(urls)
                all_urls.update(article_urls)
                self.logger.info(f"Found {len(article_urls)} article URLs in {sitemap_url}")
            except httpx.HTTPError as e:
                self.logger.warning(f"Failed to fetch sitemap {sitemap_url}: {e}")
            except Exception as e:
                self.logger.error(f"Error processing sitemap {sitemap_url}: {e}")

        self.logger.info(f"Total unique article URLs found: {len(all_urls)}")
        return list(all_urls)

    async def get_article_urls_for_date(self, target_date: date) -> List[str]:
        """
        Fetch and parse all sitemaps to get article URLs for a specific date.

        Args:
            target_date: The date to filter articles by.

        Returns:
            List of article URLs that were published/modified on the target date.
        """
        all_urls: Set[str] = set()

        for sitemap_url in settings.sitemap_urls:
            try:
                xml_content = await self.fetch_sitemap(sitemap_url)
                url_data = self.parse_urls_with_dates(xml_content)

                for url, lastmod in url_data:
                    # Skip non-article URLs
                    if not self._is_article_url(url):
                        continue

                    # If we have lastmod date, filter by target date
                    if lastmod is not None:
                        if lastmod.date() == target_date:
                            all_urls.add(url)
                    # If no lastmod, we'll need to check article's published date after scraping

                self.logger.info(f"Found URLs with date filter from {sitemap_url}")

            except httpx.HTTPError as e:
                self.logger.warning(f"Failed to fetch sitemap {sitemap_url}: {e}")
            except Exception as e:
                self.logger.error(f"Error processing sitemap {sitemap_url}: {e}")

        self.logger.info(f"Total article URLs for {target_date}: {len(all_urls)}")
        return list(all_urls)

    def _is_article_url(self, url: str) -> bool:
        """Check if URL is an article page."""
        exclude_patterns = [
            "/category/",
            "/tag/",
            "/author/",
            "/page/",
            "/sitemap",
            ".xml",
        ]
        # Exact paths to exclude (non-article pages)
        exclude_exact = [
            "/apps",
            "/resources",
            "/reports",
            "/join",
            "/about",
            "/advertise",
            "/formats",
            "/privacy-policy",
            "/terms-of-service",
            "/mysge",
        ]

        # Check exclusion patterns
        if any(pattern in url.lower() for pattern in exclude_patterns):
            return False

        # Only include URLs from the main domain
        if settings.base_url not in url:
            return False

        # Skip homepage
        if url.rstrip("/") == settings.base_url:
            return False

        # Skip exact non-article pages
        path = url.replace(settings.base_url, "").rstrip("/")
        if path in exclude_exact:
            return False

        return True

    def extract_slug_from_url(self, url: str) -> str:
        """Extract the slug from an article URL."""
        # Remove base URL and trailing slash
        slug = url.replace(settings.base_url, "").strip("/")
        return slug
