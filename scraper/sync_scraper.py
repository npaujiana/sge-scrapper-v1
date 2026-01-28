"""
Synchronous scraper that runs in a separate process.
This avoids Windows asyncio subprocess issues with Playwright.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

# Process pool executor for scraping
_scraper_executor = None


def _get_scraper_executor():
    """Get or create process pool executor for scraping."""
    global _scraper_executor
    if _scraper_executor is None:
        _scraper_executor = ProcessPoolExecutor(max_workers=1)
    return _scraper_executor


def scrape_article_sync(
    url: str,
    session_dir: str,
    base_url: str = "https://www.socialgrowthengineers.com"
) -> Optional[Dict[str, Any]]:
    """
    Scrape a single article synchronously using Playwright.
    This function runs in a separate process.

    Args:
        url: Article URL to scrape
        session_dir: Path to session directory containing storage_state.json
        base_url: Base URL of the site

    Returns:
        Dict with article data or None if failed
    """
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup

    print(f"[SCRAPER] Scraping: {url}")

    try:
        with sync_playwright() as playwright:
            # Check for storage state
            storage_state_file = Path(session_dir) / "storage_state.json"
            storage_state = str(storage_state_file) if storage_state_file.exists() else None

            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
            )

            try:
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    storage_state=storage_state,
                )
                page = context.new_page()

                # Navigate to page - use domcontentloaded for faster loading
                # networkidle can timeout on pages with video embeds
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    print(f"[SCRAPER] Warning: domcontentloaded failed, retrying with load: {e}")
                    page.goto(url, wait_until="load", timeout=60000)

                # Wait for Next.js data to be available
                try:
                    page.wait_for_selector("#__NEXT_DATA__", timeout=10000)
                except:
                    pass

                # Wait for content container
                try:
                    page.wait_for_selector("article, .article-content, .post-content, main", timeout=5000)
                except:
                    pass

                # Extract __NEXT_DATA__
                next_data = None
                try:
                    next_data_elem = page.query_selector("#__NEXT_DATA__")
                    if next_data_elem:
                        json_text = next_data_elem.inner_text()
                        next_data = json.loads(json_text)
                except Exception as e:
                    print(f"[SCRAPER] Warning: Could not extract __NEXT_DATA__: {e}")

                # Get HTML content
                html_content = page.content()
                soup = BeautifulSoup(html_content, "lxml")

                # Parse article data
                article_data = _parse_article_sync(url, soup, next_data, base_url)

                # Extract social content
                extra_content_html = _extract_content_from_json(next_data)
                social_html = "\n".join([part for part in [html_content, extra_content_html] if part])
                article_data["social_contents"] = _extract_social_contents(social_html)

                print(f"[SCRAPER] Success: {article_data.get('title', url)[:50]}")
                return article_data

            finally:
                browser.close()

    except Exception as e:
        import traceback
        print(f"[SCRAPER] Error scraping {url}: {e}")
        traceback.print_exc()
        return None


def _parse_article_sync(
    url: str,
    soup: "BeautifulSoup",
    next_data: Optional[Dict],
    base_url: str
) -> Dict[str, Any]:
    """Parse article data from HTML and JSON."""
    slug = url.replace(base_url, "").strip("/")

    # Get pageProps from __NEXT_DATA__
    page_props = {}
    if next_data:
        page_props = next_data.get("props", {}).get("pageProps", {})

    post = page_props.get("post") or page_props.get("article") or {}

    # Extract ID
    sge_id = str(post.get("id", slug))

    # Extract title
    title = post.get("title")
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "Untitled"

    # Extract subtitle
    subtitle = post.get("excerpt") or post.get("subtitle")
    if not subtitle:
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            subtitle = meta_desc["content"]

    # Extract content
    content_html, content_text = _extract_content_sync(soup, page_props)

    # Extract category
    category = None
    cat = post.get("category")
    if isinstance(cat, dict):
        category = cat.get("name") or cat.get("title")
    elif cat:
        category = str(cat)
    if not category:
        cat_link = soup.select_one("a[href*='/category/']")
        if cat_link:
            category = cat_link.get_text(strip=True)

    # Extract tags
    tags = []
    raw_tags = post.get("tags", [])
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if isinstance(tag, dict):
                tags.append(tag.get("name") or tag.get("title", ""))
            else:
                tags.append(str(tag))

    # Extract author
    author_name = None
    author_email = None
    author = post.get("author")
    if isinstance(author, dict):
        author_name = author.get("name") or author.get("displayName")
        author_email = author.get("email")
    elif author:
        author_name = str(author)

    # Extract featured image
    featured_image_url = None
    if "featuredImage" in post:
        img = post["featuredImage"]
        if isinstance(img, dict):
            featured_image_url = img.get("url") or img.get("src")
        else:
            featured_image_url = str(img)
    if not featured_image_url:
        og_image = soup.find("meta", {"property": "og:image"})
        if og_image and og_image.get("content"):
            featured_image_url = og_image["content"]

    # Extract read time
    read_time = post.get("readTime")

    # Extract published date
    published_at = None
    date_str = post.get("publishedAt") or post.get("createdAt")
    if not date_str:
        time_elem = soup.find("time")
        if time_elem:
            date_str = time_elem.get("datetime") or time_elem.get_text(strip=True)

    if date_str:
        try:
            published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            try:
                from dateutil import parser
                published_at = parser.parse(date_str)
            except:
                pass

    return {
        "sge_id": sge_id,
        "url": url,
        "slug": slug,
        "title": title,
        "subtitle": subtitle,
        "content": content_html,
        "content_text": content_text,
        "category": category,
        "tags": tags if tags else None,
        "author_name": author_name,
        "author_email": author_email,
        "featured_image_url": featured_image_url,
        "read_time": read_time,
        "published_at": published_at.isoformat() if published_at else None,
        "raw_json": next_data,
        "social_contents": [],
    }


def _extract_content_sync(soup: "BeautifulSoup", page_props: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract article content as HTML and plain text."""
    from bs4 import BeautifulSoup as BS

    # Try raw HTML from __NEXT_DATA__
    post = page_props.get("post") or page_props.get("article") or {}
    candidates = [
        post.get("content"),
        post.get("contentRendered"),
        post.get("contentHtml"),
        post.get("body"),
        post.get("html"),
    ]

    for candidate in candidates:
        if isinstance(candidate, dict) and "rendered" in candidate:
            content_html = candidate["rendered"]
            content_text = BS(content_html, "lxml").get_text(separator="\n", strip=True)
            return content_html, content_text
        if isinstance(candidate, str) and candidate.strip():
            content_text = BS(candidate, "lxml").get_text(separator="\n", strip=True)
            return candidate, content_text

    # Fallback to DOM
    selectors = [
        "article .content",
        ".article-content",
        ".post-content",
        "article",
        "main .content",
    ]

    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            return str(elem), elem.get_text(separator="\n", strip=True)

    return None, None


def _extract_content_from_json(next_data: Optional[Dict]) -> Optional[str]:
    """Extract raw article HTML from __NEXT_DATA__."""
    if not next_data:
        return None

    page_props = next_data.get("props", {}).get("pageProps", {})
    post = page_props.get("post") or page_props.get("article") or {}

    candidates = [
        post.get("content"),
        post.get("contentRendered"),
        post.get("contentHtml"),
        post.get("body"),
    ]

    for candidate in candidates:
        if isinstance(candidate, dict) and "rendered" in candidate:
            return candidate["rendered"]
        if isinstance(candidate, str) and candidate.strip():
            return candidate

    return None


def _fetch_sge_embed_details(embed_id: str) -> Optional[Dict[str, Any]]:
    """Fetch video details from SGE embed API."""
    import requests

    try:
        api_url = f"https://www.socialgrowthengineers.com/api/embed/video/{embed_id}"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[SCRAPER] Warning: Could not fetch embed details for {embed_id}: {e}")
    return None


def _extract_social_contents(html: str) -> List[Dict[str, Any]]:
    """Extract social media content from HTML."""
    from bs4 import BeautifulSoup as BS
    import re

    social_contents = []
    soup = BS(html, "lxml")
    position = 0
    seen_urls = set()  # Avoid duplicates

    # SGE Custom Video Embeds (TikTok videos hosted on SGE)
    sge_video_iframes = soup.find_all("iframe", src=re.compile(r"/embed/video/", re.I))
    for iframe in sge_video_iframes:
        src = iframe.get("src", "")
        if src and src not in seen_urls:
            seen_urls.add(src)

            # Extract embed ID and fetch real video details
            embed_id_match = re.search(r"/embed/video/([a-f0-9-]+)", src, re.I)
            if embed_id_match:
                embed_id = embed_id_match.group(1)
                embed_details = _fetch_sge_embed_details(embed_id)

                if embed_details:
                    # Use actual TikTok URL and details
                    video_url = embed_details.get("video_url", src)
                    video_id = embed_details.get("video_id")
                    platform = embed_details.get("platform", "tiktok")
                    video_details = embed_details.get("video_details", {})

                    # Extract stats from video_details
                    item_struct = video_details.get("itemInfo", {}).get("itemStruct", {})
                    stats = item_struct.get("stats", {})
                    author = item_struct.get("author", {})

                    social_contents.append({
                        "platform": platform,
                        "content_type": "video",
                        "url": video_url,
                        "video_id": video_id,
                        "embed_id": embed_id,
                        "embed_html": str(iframe),
                        "username": author.get("uniqueId"),
                        "caption": item_struct.get("desc"),
                        "thumbnail_url": item_struct.get("video", {}).get("cover"),
                        "stats": {
                            "views": stats.get("playCount"),
                            "likes": stats.get("diggCount"),
                            "comments": stats.get("commentCount"),
                            "shares": stats.get("shareCount"),
                        } if stats else None,
                        "position_in_article": position,
                    })
                    position += 1
                    continue

            # Fallback if API fetch fails
            social_contents.append({
                "platform": "tiktok",
                "content_type": "video",
                "url": src,
                "embed_html": str(iframe),
                "position_in_article": position,
            })
            position += 1

    # TikTok iframes (direct embeds)
    tiktok_iframes = soup.find_all("iframe", src=re.compile(r"tiktok\.com", re.I))
    for iframe in tiktok_iframes:
        src = iframe.get("src", "")
        if src and src not in seen_urls:
            seen_urls.add(src)
            social_contents.append({
                "platform": "tiktok",
                "content_type": "video",
                "url": src,
                "embed_html": str(iframe),
                "position_in_article": position,
            })
            position += 1

    # TikTok links (in <a> tags)
    tiktok_links = soup.find_all("a", href=re.compile(r"tiktok\.com", re.I))
    for link in tiktok_links:
        href = link.get("href", "")
        if href and href not in seen_urls:
            seen_urls.add(href)
            # Determine content type from URL
            content_type = "video"
            if "/music/" in href:
                content_type = "sound"
            elif "/@" in href and "/video/" not in href:
                content_type = "profile"
            social_contents.append({
                "platform": "tiktok",
                "content_type": content_type,
                "url": href,
                "embed_html": str(link),
                "position_in_article": position,
            })
            position += 1

    # Instagram blockquotes (embeds)
    ig_blockquotes = soup.find_all("blockquote", class_=re.compile(r"instagram", re.I))
    for bq in ig_blockquotes:
        link = bq.find("a", href=re.compile(r"instagram\.com", re.I))
        url = link.get("href") if link else None
        if url and url not in seen_urls:
            seen_urls.add(url)
            social_contents.append({
                "platform": "instagram",
                "content_type": "post",
                "url": url,
                "embed_html": str(bq),
                "position_in_article": position,
            })
            position += 1

    # Instagram links (in <a> tags)
    ig_links = soup.find_all("a", href=re.compile(r"instagram\.com/(p|reel|tv)/", re.I))
    for link in ig_links:
        href = link.get("href", "")
        if href and href not in seen_urls:
            seen_urls.add(href)
            content_type = "post"
            if "/reel/" in href:
                content_type = "reel"
            elif "/tv/" in href:
                content_type = "igtv"
            social_contents.append({
                "platform": "instagram",
                "content_type": content_type,
                "url": href,
                "embed_html": str(link),
                "position_in_article": position,
            })
            position += 1

    # Twitter/X blockquotes (embeds)
    twitter_blockquotes = soup.find_all("blockquote", class_=re.compile(r"twitter", re.I))
    for bq in twitter_blockquotes:
        link = bq.find("a", href=re.compile(r"(twitter|x)\.com", re.I))
        url = link.get("href") if link else None
        if url and url not in seen_urls:
            seen_urls.add(url)
            social_contents.append({
                "platform": "twitter",
                "content_type": "tweet",
                "url": url,
                "embed_html": str(bq),
                "position_in_article": position,
            })
            position += 1

    # Twitter/X links (in <a> tags)
    twitter_links = soup.find_all("a", href=re.compile(r"(twitter|x)\.com/\w+/status/", re.I))
    for link in twitter_links:
        href = link.get("href", "")
        if href and href not in seen_urls:
            seen_urls.add(href)
            social_contents.append({
                "platform": "twitter",
                "content_type": "tweet",
                "url": href,
                "embed_html": str(link),
                "position_in_article": position,
            })
            position += 1

    # YouTube iframes
    yt_iframes = soup.find_all("iframe", src=re.compile(r"youtube\.com|youtu\.be", re.I))
    for iframe in yt_iframes:
        src = iframe.get("src", "")
        if src and src not in seen_urls:
            seen_urls.add(src)
            social_contents.append({
                "platform": "youtube",
                "content_type": "video",
                "url": src,
                "embed_html": str(iframe),
                "position_in_article": position,
            })
            position += 1

    # YouTube links (in <a> tags)
    yt_links = soup.find_all("a", href=re.compile(r"(youtube\.com/watch|youtu\.be/)", re.I))
    for link in yt_links:
        href = link.get("href", "")
        if href and href not in seen_urls:
            seen_urls.add(href)
            social_contents.append({
                "platform": "youtube",
                "content_type": "video",
                "url": href,
                "embed_html": str(link),
                "position_in_article": position,
            })
            position += 1

    return social_contents


def scrape_articles_batch_sync(
    urls: List[str],
    session_dir: str,
    base_url: str = "https://www.socialgrowthengineers.com",
    delay_ms: int = 2000
) -> List[Dict[str, Any]]:
    """
    Scrape multiple articles synchronously.

    Args:
        urls: List of article URLs to scrape
        session_dir: Path to session directory
        base_url: Base URL of the site
        delay_ms: Delay between articles in milliseconds

    Returns:
        List of article data dicts (or None for failed articles)
    """
    import time

    results = []

    for i, url in enumerate(urls):
        print(f"[SCRAPER] Processing {i+1}/{len(urls)}: {url}")

        result = scrape_article_sync(url, session_dir, base_url)
        results.append(result)

        # Delay between articles
        if i < len(urls) - 1:
            time.sleep(delay_ms / 1000)

    return results
