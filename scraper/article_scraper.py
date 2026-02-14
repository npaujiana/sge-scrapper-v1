import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from config.settings import settings
from config.logging_config import get_logger
from .social_extractor import SocialExtractor, SocialContentData


@dataclass
class ArticleData:
    """Data class for scraped article."""
    sge_id: str
    url: str
    slug: str
    title: str
    subtitle: Optional[str] = None
    content: Optional[str] = None
    content_text: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    featured_image_url: Optional[str] = None
    read_time: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_json: Optional[Dict[str, Any]] = None
    social_contents: List[SocialContentData] = field(default_factory=list)


class ArticleScraper:
    """Scrape individual articles from SGE."""

    def __init__(self):
        self.logger = get_logger()
        self.social_extractor = SocialExtractor()

    async def scrape_article(self, page: Page, url: str) -> Optional[ArticleData]:
        """Scrape a single article from the given URL."""
        self.logger.info(f"Scraping article: {url}")

        try:
            # Navigate to the page
            await page.goto(url, wait_until="networkidle", timeout=settings.page_timeout_ms)

            # Wait for content to load
            await self._wait_for_content(page)

            # Extract __NEXT_DATA__ JSON
            next_data = await self._extract_next_data(page)

            # Extract article content from rendered HTML
            html_content = await page.content()
            soup = BeautifulSoup(html_content, "lxml")

            # Parse article data
            article_data = self._parse_article(url, soup, next_data)

            # Build a richer HTML blob for social extraction:
            #  - full page HTML (includes iframes/blockquotes already rendered)
            #  - raw content HTML from __NEXT_DATA__ if present (often contains embeds even when paywalled)
            extra_content_html = self._extract_content_from_json(next_data)
            social_html = "\n".join(
                [part for part in [html_content, extra_content_html] if part]
            )

            # Extract social media content
            article_data.social_contents = self.social_extractor.extract_all(social_html)

            self.logger.info(f"Successfully scraped: {article_data.title[:50] if article_data.title else url}")
            return article_data

        except PlaywrightTimeout:
            self.logger.error(f"Timeout scraping article: {url}")
            return None
        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}")
            return None

    async def _wait_for_content(self, page: Page) -> None:
        """Wait for the article content to be loaded."""
        try:
            # Wait for article content container
            await page.wait_for_selector(
                "article, .article-content, .post-content, main",
                timeout=10000
            )
        except PlaywrightTimeout:
            self.logger.warning("Content selector not found, proceeding anyway")

    async def _extract_next_data(self, page: Page) -> Optional[Dict[str, Any]]:
        """Extract __NEXT_DATA__ JSON from the page."""
        try:
            next_data_element = await page.query_selector("#__NEXT_DATA__")
            if next_data_element:
                json_text = await next_data_element.inner_text()
                return json.loads(json_text)
        except Exception as e:
            self.logger.warning(f"Failed to extract __NEXT_DATA__: {e}")
        return None

    def _parse_article(
        self,
        url: str,
        soup: BeautifulSoup,
        next_data: Optional[Dict[str, Any]]
    ) -> ArticleData:
        """Parse article data from HTML and JSON."""
        slug = url.replace(settings.base_url, "").strip("/")

        # Try to get data from __NEXT_DATA__ first
        page_props = {}
        if next_data:
            page_props = next_data.get("props", {}).get("pageProps", {})

        # Extract article ID
        sge_id = self._extract_id(page_props, slug)

        # Extract title
        title = self._extract_title(soup, page_props)

        # Extract subtitle/excerpt
        subtitle = self._extract_subtitle(soup, page_props)

        # Extract content
        content, content_text = self._extract_content(soup, page_props)

        # Extract category
        category = self._extract_category(soup, page_props)

        # Extract tags
        tags = self._extract_tags(soup, page_props)

        # Extract author info
        author_name, author_email = self._extract_author(soup, page_props)

        # Extract featured image
        featured_image_url = self._extract_featured_image(soup, page_props)

        # Extract read time
        read_time = self._extract_read_time(soup, page_props)

        # Extract published date
        published_at = self._extract_published_date(soup, page_props)

        return ArticleData(
            sge_id=sge_id,
            url=url,
            slug=slug,
            title=title,
            subtitle=subtitle,
            content=content,
            content_text=content_text,
            category=category,
            tags=tags,
            author_name=author_name,
            author_email=author_email,
            featured_image_url=featured_image_url,
            read_time=read_time,
            published_at=published_at,
            raw_json=next_data,
        )

    def _extract_id(self, page_props: Dict, slug: str) -> str:
        """Extract article ID."""
        if "post" in page_props and "id" in page_props["post"]:
            return str(page_props["post"]["id"])
        if "article" in page_props and "id" in page_props["article"]:
            return str(page_props["article"]["id"])
        # Use slug as fallback ID
        return slug

    def _extract_title(self, soup: BeautifulSoup, page_props: Dict) -> str:
        """Extract article title."""
        # From JSON
        if "post" in page_props and "title" in page_props["post"]:
            return page_props["post"]["title"]
        if "article" in page_props and "title" in page_props["article"]:
            return page_props["article"]["title"]

        # From HTML
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)

        return "Untitled"

    def _extract_subtitle(self, soup: BeautifulSoup, page_props: Dict) -> Optional[str]:
        """Extract article subtitle/excerpt."""
        if "post" in page_props:
            return page_props["post"].get("excerpt") or page_props["post"].get("subtitle")
        if "article" in page_props:
            return page_props["article"].get("excerpt") or page_props["article"].get("subtitle")

        # From HTML meta description
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"]

        return None

    def _extract_content(self, soup: BeautifulSoup, page_props: Dict) -> tuple[Optional[str], Optional[str]]:
        """Extract article content as HTML and plain text."""
        content_html = None
        content_text = None

        # 1) Use raw HTML delivered in __NEXT_DATA__ when present (bypasses paywall/hide-on-render issues)
        raw_content = self._extract_content_from_page_props(page_props)
        if raw_content:
            content_html = raw_content
            try:
                content_text = BeautifulSoup(raw_content, "lxml").get_text(separator="\n", strip=True)
            except Exception:
                # Fall back to html.parser if lxml missing in runtime
                content_text = BeautifulSoup(raw_content, "html.parser").get_text(separator="\n", strip=True)
            return content_html, content_text

        # 2) Fallback to rendered DOM selectors
        selectors = [
            "article .content",
            ".article-content",
            ".post-content",
            "article",
            "main .content",
            ".entry-content",
        ]

        for selector in selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content_html = str(content_elem)
                content_text = content_elem.get_text(separator="\n", strip=True)
                break

        return content_html, content_text

    def _extract_content_from_page_props(self, page_props: Dict) -> Optional[str]:
        """
        Pull the raw HTML body from Next.js pageProps if available.

        The site often puts the full article HTML in post.content / article.content /
        {content, contentRendered, body, html} keys. Use whichever exists first.
        """
        candidates = []
        post = page_props.get("post") or page_props.get("article") or {}
        if isinstance(post, dict):
            candidates.extend([
                post.get("content"),
                post.get("contentRendered"),
                post.get("contentHtml"),
                post.get("body"),
                post.get("html"),
            ])

        # unwrap WP-like rendered object: {"rendered": "<p>...</p>"}
        for candidate in candidates:
            if isinstance(candidate, dict) and "rendered" in candidate:
                return candidate["rendered"]
            if isinstance(candidate, str) and candidate.strip():
                return candidate

        return None

    def _extract_content_from_json(self, next_data: Optional[Dict[str, Any]]) -> Optional[str]:
        """
        Extract the raw article HTML from __NEXT_DATA__ for social extraction.
        """
        if not next_data:
            return None
        page_props = next_data.get("props", {}).get("pageProps", {})
        return self._extract_content_from_page_props(page_props)

    def _extract_category(self, soup: BeautifulSoup, page_props: Dict) -> Optional[str]:
        """Extract article category."""
        if "post" in page_props and "category" in page_props["post"]:
            cat = page_props["post"]["category"]
            if isinstance(cat, dict):
                return cat.get("name") or cat.get("title")
            return str(cat)

        # From HTML
        category_link = soup.select_one("a[href*='/category/']")
        if category_link:
            return category_link.get_text(strip=True)

        return None

    def _extract_tags(self, soup: BeautifulSoup, page_props: Dict) -> Optional[List[str]]:
        """Extract article tags."""
        tags = []

        if "post" in page_props and "tags" in page_props["post"]:
            raw_tags = page_props["post"]["tags"]
            if isinstance(raw_tags, list):
                for tag in raw_tags:
                    if isinstance(tag, dict):
                        tags.append(tag.get("name") or tag.get("title", ""))
                    else:
                        tags.append(str(tag))

        # From HTML
        tag_links = soup.select("a[href*='/tag/']")
        for tag_link in tag_links:
            tag_text = tag_link.get_text(strip=True)
            if tag_text and tag_text not in tags:
                tags.append(tag_text)

        return tags if tags else None

    def _extract_author(self, soup: BeautifulSoup, page_props: Dict) -> tuple[Optional[str], Optional[str]]:
        """Extract author name and email."""
        author_name = None
        author_email = None

        if "post" in page_props and "author" in page_props["post"]:
            author = page_props["post"]["author"]
            if isinstance(author, dict):
                author_name = author.get("name") or author.get("displayName")
                author_email = author.get("email")
            else:
                author_name = str(author)

        # From HTML
        if not author_name:
            author_elem = soup.select_one(".author-name, .author, [rel='author']")
            if author_elem:
                author_name = author_elem.get_text(strip=True)

        return author_name, author_email

    def _extract_featured_image(self, soup: BeautifulSoup, page_props: Dict) -> Optional[str]:
        """Extract featured image URL."""
        if "post" in page_props:
            post = page_props["post"]
            if "featuredImage" in post:
                img = post["featuredImage"]
                if isinstance(img, dict):
                    return img.get("url") or img.get("src")
                return str(img)
            if "image" in post:
                return post["image"]

        # From HTML og:image
        og_image = soup.find("meta", {"property": "og:image"})
        if og_image and og_image.get("content"):
            return og_image["content"]

        return None

    def _extract_read_time(self, soup: BeautifulSoup, page_props: Dict) -> Optional[str]:
        """Extract estimated read time."""
        if "post" in page_props and "readTime" in page_props["post"]:
            return page_props["post"]["readTime"]

        # From HTML
        read_time_elem = soup.select_one(".read-time, .reading-time")
        if read_time_elem:
            return read_time_elem.get_text(strip=True)

        return None

    def _extract_published_date(self, soup: BeautifulSoup, page_props: Dict) -> Optional[datetime]:
        """Extract published date."""
        date_str = None

        # 1. From __NEXT_DATA__ props
        if "post" in page_props:
            date_str = page_props["post"].get("publishedAt") or page_props["post"].get("createdAt") or page_props["post"].get("date")

        # 2. From JSON-LD script tag
        if not date_str:
            try:
                json_ld_script = soup.find("script", {"type": "application/ld+json"})
                if json_ld_script:
                    json_data = json.loads(json_ld_script.string)
                    date_str = json_data.get("datePublished") or json_data.get("publishedDate")
            except Exception:
                pass # Ignore if JSON-LD is malformed or not present

        # 3. From HTML meta tags
        if not date_str:
            meta_selectors = [
                "meta[property='article:published_time']",
                "meta[property='og:published_time']",
                "meta[name='pubdate']",
                "meta[name='date']",
            ]
            for selector in meta_selectors:
                meta_tag = soup.select_one(selector)
                if meta_tag and meta_tag.get("content"):
                    date_str = meta_tag["content"]
                    break
        
        # 4. From <time> element
        if not date_str:
            time_elem = soup.find("time")
            if time_elem:
                date_str = time_elem.get("datetime") or time_elem.get_text(strip=True)

        # 5. Fallback: search for date-like text in the article body (less reliable)
        if not date_str:
            article_body = soup.select_one("article, .post-content")
            if article_body:
                # Regex for YYYY-MM-DD or Month Day, Year
                date_pattern = re.compile(r'\b(\d{4}-\d{2}-\d{2})|((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},\s+\d{4})\b')
                match = date_pattern.search(article_body.get_text())
                if match:
                    date_str = match.group(0)

        if date_str:
            try:
                # Try ISO format
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

            # Try common formats using dateutil.parser
            from dateutil import parser
            try:
                return parser.parse(date_str)
            except (parser.ParserError, TypeError, ValueError):
                self.logger.warning(f"Could not parse date string: {date_str}")
                pass

        self.logger.warning("Could not extract any published date.")
        return None
