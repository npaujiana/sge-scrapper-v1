import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup

from config.logging_config import get_logger


@dataclass
class SocialContentData:
    """Data class for social media content."""
    platform: str  # tiktok/instagram/twitter/youtube
    content_type: str  # video/post/tweet/embed/screenshot
    url: Optional[str] = None
    embed_html: Optional[str] = None
    thumbnail_url: Optional[str] = None
    username: Optional[str] = None
    caption: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    position_in_article: int = 0


class SocialExtractor:
    """Extract social media content from article HTML."""

    def __init__(self):
        self.logger = get_logger()

    def _regex_urls(self, html: str, pattern: str) -> List[str]:
        """Find unique URLs in raw HTML/text using regex."""
        urls = []
        seen = set()
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(0)
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def extract_all(self, html_content: str) -> List[SocialContentData]:
        """Extract all social media content from HTML."""
        # Use lxml when available; fall back gracefully so scraping doesn't stop.
        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception:
            soup = BeautifulSoup(html_content, "html.parser")

        contents: List[SocialContentData] = []
        position = 0
        raw_html = html_content  # keep original string for regex-based URL discovery

        # Extract TikTok
        tiktok_contents = self._extract_tiktok(soup, raw_html)
        for content in tiktok_contents:
            content.position_in_article = position
            contents.append(content)
            position += 1

        # Extract Instagram
        instagram_contents = self._extract_instagram(soup, raw_html)
        for content in instagram_contents:
            content.position_in_article = position
            contents.append(content)
            position += 1

        # Extract Twitter/X
        twitter_contents = self._extract_twitter(soup, raw_html)
        for content in twitter_contents:
            content.position_in_article = position
            contents.append(content)
            position += 1

        # Extract YouTube
        youtube_contents = self._extract_youtube(soup, raw_html)
        for content in youtube_contents:
            content.position_in_article = position
            contents.append(content)
            position += 1

        # Extract social media screenshots
        screenshot_contents = self._extract_screenshots(soup)
        for content in screenshot_contents:
            content.position_in_article = position
            contents.append(content)
            position += 1

        self.logger.debug(f"Extracted {len(contents)} social media contents")
        return contents

    def _extract_tiktok(self, soup: BeautifulSoup, raw_html: str) -> List[SocialContentData]:
        """Extract TikTok embeds and links."""
        contents: List[SocialContentData] = []
        seen_urls = set()

        # TikTok iframes
        tiktok_iframes = soup.find_all("iframe", src=re.compile(r"tiktok\.com", re.I))
        for iframe in tiktok_iframes:
            src = iframe.get("src", "")
            if src in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="tiktok",
                content_type="embed",
                url=src,
                embed_html=str(iframe),
                username=self._extract_tiktok_username(src),
            ))
            seen_urls.add(src)

        # TikTok blockquotes
        tiktok_blockquotes = soup.find_all("blockquote", class_=re.compile(r"tiktok-embed", re.I))
        for blockquote in tiktok_blockquotes:
            cite = blockquote.get("cite", "")
            data_video_id = blockquote.get("data-video-id", "")
            url = cite or (f"https://www.tiktok.com/video/{data_video_id}" if data_video_id else None)
            if url and url in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="tiktok",
                content_type="embed",
                url=url,
                embed_html=str(blockquote),
                username=self._extract_tiktok_username(url or ""),
                metadata={"video_id": data_video_id} if data_video_id else None,
            ))
            if url:
                seen_urls.add(url)

        # TikTok links in content
        tiktok_links = soup.find_all("a", href=re.compile(r"tiktok\.com/@[\w.-]+/video/", re.I))
        for link in tiktok_links:
            href = link.get("href", "")
            # Avoid duplicates from iframes/blockquotes
            if href and href not in seen_urls:
                contents.append(SocialContentData(
                    platform="tiktok",
                    content_type="video",
                    url=href,
                    username=self._extract_tiktok_username(href),
                    caption=link.get_text(strip=True) or None,
                ))
                seen_urls.add(href)

        # Regex scan across raw HTML/JSON to catch URLs embedded in scripts (__NEXT_DATA__)
        regex_urls = self._regex_urls(
            raw_html,
            r"https?://(?:www\.)?tiktok\.com/(?:@[\w\.-]+/video/\d+|embed/[\w/-]+|t/[\w\d]+)"
        )
        for url in regex_urls:
            if url in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="tiktok",
                content_type="video",
                url=url,
                username=self._extract_tiktok_username(url),
            ))
            seen_urls.add(url)

        return contents

    def _extract_tiktok_username(self, url: str) -> Optional[str]:
        """Extract username from TikTok URL."""
        match = re.search(r"tiktok\.com/@([\w.-]+)", url)
        return match.group(1) if match else None

    def _extract_instagram(self, soup: BeautifulSoup, raw_html: str) -> List[SocialContentData]:
        """Extract Instagram embeds and links."""
        contents: List[SocialContentData] = []
        seen_urls = set()

        # Instagram blockquotes
        ig_blockquotes = soup.find_all("blockquote", class_=re.compile(r"instagram-media", re.I))
        for blockquote in ig_blockquotes:
            data_instgrm_permalink = blockquote.get("data-instgrm-permalink", "")
            # Find link inside blockquote
            link = blockquote.find("a", href=re.compile(r"instagram\.com/p/", re.I))
            url = data_instgrm_permalink or (link.get("href") if link else None)
            if url in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="instagram",
                content_type="embed",
                url=url,
                embed_html=str(blockquote),
                username=self._extract_instagram_username(url or ""),
            ))
            if url:
                seen_urls.add(url)

        # Instagram iframes
        ig_iframes = soup.find_all("iframe", src=re.compile(r"instagram\.com", re.I))
        for iframe in ig_iframes:
            src = iframe.get("src", "")
            if src in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="instagram",
                content_type="embed",
                url=src,
                embed_html=str(iframe),
                username=self._extract_instagram_username(src),
            ))
            seen_urls.add(src)

        # Instagram links in content
        ig_patterns = [
            r"instagram\.com/p/[\w-]+",
            r"instagram\.com/reel/[\w-]+",
            r"instagram\.com/tv/[\w-]+",
        ]
        for pattern in ig_patterns:
            ig_links = soup.find_all("a", href=re.compile(pattern, re.I))
            for link in ig_links:
                href = link.get("href", "")
                if href and href not in seen_urls:
                    content_type = "video" if "/reel/" in href or "/tv/" in href else "post"
                    contents.append(SocialContentData(
                        platform="instagram",
                        content_type=content_type,
                        url=href,
                        username=self._extract_instagram_username(href),
                        caption=link.get_text(strip=True) or None,
                    ))
                    seen_urls.add(href)

        # Regex scan across raw HTML/JSON for stray instagram links (e.g., inside scripts)
        regex_urls = self._regex_urls(
            raw_html,
            r"https?://(?:www\.)?instagram\.com/(?:reel|p|tv)/[\w-]+"
        )
        for url in regex_urls:
            if url in seen_urls:
                continue
            content_type = "video" if any(seg in url for seg in ["/reel/", "/tv/"]) else "post"
            contents.append(SocialContentData(
                platform="instagram",
                content_type=content_type,
                url=url,
                username=self._extract_instagram_username(url),
            ))
            seen_urls.add(url)

        return contents

    def _extract_instagram_username(self, url: str) -> Optional[str]:
        """Extract username from Instagram URL (limited)."""
        # Instagram post URLs don't always contain username
        match = re.search(r"instagram\.com/([\w.-]+)/", url)
        if match and match.group(1) not in ["p", "reel", "tv", "stories"]:
            return match.group(1)
        return None

    def _extract_twitter(self, soup: BeautifulSoup, raw_html: str) -> List[SocialContentData]:
        """Extract Twitter/X embeds and links."""
        contents: List[SocialContentData] = []
        seen_urls = set()

        # Twitter blockquotes
        twitter_blockquotes = soup.find_all("blockquote", class_=re.compile(r"twitter-tweet", re.I))
        for blockquote in twitter_blockquotes:
            # Find the tweet link
            link = blockquote.find("a", href=re.compile(r"(twitter|x)\.com/.+/status/", re.I))
            url = link.get("href") if link else None
            if url in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="twitter",
                content_type="tweet",
                url=url,
                embed_html=str(blockquote),
                username=self._extract_twitter_username(url or ""),
                caption=blockquote.get_text(strip=True)[:500] if blockquote.get_text(strip=True) else None,
            ))
            if url:
                seen_urls.add(url)

        # Twitter iframes
        twitter_iframes = soup.find_all("iframe", src=re.compile(r"platform\.(twitter|x)\.com", re.I))
        for iframe in twitter_iframes:
            src = iframe.get("src", "")
            if src in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="twitter",
                content_type="embed",
                url=src,
                embed_html=str(iframe),
            ))
            seen_urls.add(src)

        # Twitter/X links in content
        twitter_links = soup.find_all("a", href=re.compile(r"(twitter|x)\.com/.+/status/\d+", re.I))
        for link in twitter_links:
            href = link.get("href", "")
            if href and href not in seen_urls:
                contents.append(SocialContentData(
                    platform="twitter",
                    content_type="tweet",
                    url=href,
                    username=self._extract_twitter_username(href),
                    caption=link.get_text(strip=True) or None,
                ))
                seen_urls.add(href)

        # Regex scan raw HTML/JSON
        regex_urls = self._regex_urls(
            raw_html,
            r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[\w]+/status/\d+"
        )
        for url in regex_urls:
            if url in seen_urls:
                continue
            contents.append(SocialContentData(
                platform="twitter",
                content_type="tweet",
                url=url,
                username=self._extract_twitter_username(url),
            ))
            seen_urls.add(url)

        return contents

    def _extract_twitter_username(self, url: str) -> Optional[str]:
        """Extract username from Twitter/X URL."""
        match = re.search(r"(twitter|x)\.com/([\w]+)/status/", url)
        return match.group(2) if match else None

    def _extract_youtube(self, soup: BeautifulSoup, raw_html: str) -> List[SocialContentData]:
        """Extract YouTube embeds and links."""
        contents: List[SocialContentData] = []
        seen_video_ids = set()
        seen_urls = set()

        # YouTube iframes
        yt_iframes = soup.find_all("iframe", src=re.compile(r"youtube\.com/embed/", re.I))
        for iframe in yt_iframes:
            src = iframe.get("src", "")
            video_id = self._extract_youtube_video_id(src)
            if src in seen_urls or (video_id and video_id in seen_video_ids):
                continue
            contents.append(SocialContentData(
                platform="youtube",
                content_type="video",
                url=f"https://www.youtube.com/watch?v={video_id}" if video_id else src,
                embed_html=str(iframe),
                thumbnail_url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else None,
                metadata={"video_id": video_id} if video_id else None,
            ))
            seen_urls.add(src)
            if video_id:
                seen_video_ids.add(video_id)

        # YouTube links
        yt_patterns = [
            r"youtube\.com/watch\?v=[\w-]+",
            r"youtu\.be/[\w-]+",
            r"youtube\.com/shorts/[\w-]+",
        ]
        for pattern in yt_patterns:
            yt_links = soup.find_all("a", href=re.compile(pattern, re.I))
            for link in yt_links:
                href = link.get("href", "")
                video_id = self._extract_youtube_video_id(href)
                if href and href not in seen_urls and (video_id not in seen_video_ids):
                    content_type = "short" if "/shorts/" in href else "video"
                    contents.append(SocialContentData(
                        platform="youtube",
                        content_type=content_type,
                        url=href,
                        thumbnail_url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else None,
                        caption=link.get_text(strip=True) or None,
                        metadata={"video_id": video_id} if video_id else None,
                    ))
                    seen_urls.add(href)
                    if video_id:
                        seen_video_ids.add(video_id)

        # Regex scan raw HTML/JSON
        regex_urls = self._regex_urls(
            raw_html,
            r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+"
        )
        for url in regex_urls:
            video_id = self._extract_youtube_video_id(url)
            if url in seen_urls or (video_id and video_id in seen_video_ids):
                continue
            content_type = "short" if "/shorts/" in url else "video"
            contents.append(SocialContentData(
                platform="youtube",
                content_type=content_type,
                url=url,
                thumbnail_url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg" if video_id else None,
                metadata={"video_id": video_id} if video_id else None,
            ))
            seen_urls.add(url)
            if video_id:
                seen_video_ids.add(video_id)

        return contents

    def _extract_youtube_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL."""
        patterns = [
            r"youtube\.com/embed/([\w-]+)",
            r"youtube\.com/watch\?v=([\w-]+)",
            r"youtu\.be/([\w-]+)",
            r"youtube\.com/shorts/([\w-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _extract_screenshots(self, soup: BeautifulSoup) -> List[SocialContentData]:
        """Extract social media screenshots from images."""
        contents = []

        # Look for images that might be social media screenshots
        images = soup.find_all("img")
        for img in images:
            alt = (img.get("alt") or "").lower()
            src = img.get("src") or img.get("data-src") or ""

            # Check if alt text or filename suggests social media screenshot
            platform = None
            if any(kw in alt for kw in ["tiktok", "tik tok"]):
                platform = "tiktok"
            elif any(kw in alt for kw in ["instagram", "ig ", "insta"]):
                platform = "instagram"
            elif any(kw in alt for kw in ["twitter", "tweet", " x "]):
                platform = "twitter"
            elif any(kw in alt for kw in ["youtube", "yt "]):
                platform = "youtube"
            elif any(kw in alt for kw in ["facebook", "fb "]):
                platform = "facebook"
            elif any(kw in alt for kw in ["linkedin"]):
                platform = "linkedin"

            # Also check src/filename
            if not platform:
                src_lower = src.lower()
                if "tiktok" in src_lower:
                    platform = "tiktok"
                elif "instagram" in src_lower or "insta" in src_lower:
                    platform = "instagram"
                elif "twitter" in src_lower or "tweet" in src_lower:
                    platform = "twitter"

            if platform:
                contents.append(SocialContentData(
                    platform=platform,
                    content_type="screenshot",
                    thumbnail_url=src,
                    caption=img.get("alt"),
                ))

        return contents
