"""Social media screenshot/thumbnail capture for all platforms."""
import re
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import requests


def fetch_tiktok_oembed(url: str) -> Optional[dict]:
    """Fetch TikTok oEmbed data."""
    try:
        oembed_url = f"https://www.tiktok.com/oembed?url={url}"
        response = requests.get(oembed_url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[SOCIAL] TikTok oEmbed error: {e}")
    return None


def fetch_instagram_oembed(url: str) -> Optional[dict]:
    """Fetch Instagram oEmbed data (requires access token for full data)."""
    # Instagram oEmbed requires access token, try basic approach
    try:
        # Try to get from URL pattern
        # Instagram thumbnail pattern: https://www.instagram.com/p/{shortcode}/media/?size=m
        # Also supports reels: https://www.instagram.com/reel/{shortcode}/
        match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
        if match:
            shortcode = match.group(1)
            # Try media endpoint (may not always work)
            media_url = f"https://www.instagram.com/p/{shortcode}/media/?size=m"
            return {"thumbnail_url": media_url, "shortcode": shortcode}
    except Exception as e:
        print(f"[SOCIAL] Instagram parse error: {e}")
    return None


def fetch_twitter_oembed(url: str) -> Optional[dict]:
    """Fetch Twitter/X oEmbed data."""
    try:
        # Twitter oEmbed endpoint
        oembed_url = f"https://publish.twitter.com/oembed?url={url}"
        response = requests.get(oembed_url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[SOCIAL] Twitter oEmbed error: {e}")
    return None


def fetch_youtube_thumbnail(url: str) -> Optional[str]:
    """Get YouTube video thumbnail URL."""
    try:
        # Extract video ID from various YouTube URL formats
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})',
            r'youtube\.com/shorts/([A-Za-z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                # YouTube thumbnail URLs
                # maxresdefault is highest quality, fallback to hqdefault
                return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    except Exception as e:
        print(f"[SOCIAL] YouTube parse error: {e}")
    return None


def download_thumbnail(
    thumbnail_url: str,
    output_dir: str,
    article_slug: str,
    platform: str,
    index: int
) -> Optional[str]:
    """Download thumbnail image from URL."""
    try:
        response = requests.get(thumbnail_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if response.status_code == 200:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_slug = re.sub(r'[^\w\-]', '_', article_slug)[:50]
            
            # Determine file extension
            content_type = response.headers.get('content-type', '')
            ext = 'jpg'
            if 'png' in content_type:
                ext = 'png'
            elif 'webp' in content_type:
                ext = 'webp'
            
            filename = f"{safe_slug}_{platform}_{index}_{timestamp}.{ext}"
            filepath = output_path / filename
            
            with open(filepath, "wb") as f:
                f.write(response.content)
            
            print(f"[SOCIAL] Downloaded {platform} thumbnail: {filename}")
            return str(filepath)
    except Exception as e:
        print(f"[SOCIAL] Download error for {platform}: {e}")
    return None


def get_screenshot_for_content(
    platform: str,
    url: str,
    output_dir: str,
    article_slug: str,
    index: int
) -> Tuple[Optional[str], str]:
    """
    Get screenshot/thumbnail for any social platform.
    
    Returns:
        Tuple of (path, source) where source is platform name or 'failed'
    """
    if not url:
        return None, "no_url"
    
    platform = platform.lower()
    thumbnail_url = None
    
    # TikTok
    if platform == "tiktok":
        if "/video/" in url or "/embed/" in url:
            data = fetch_tiktok_oembed(url)
            if data:
                thumbnail_url = data.get("thumbnail_url")
    
    # Instagram
    elif platform == "instagram":
        data = fetch_instagram_oembed(url)
        if data:
            thumbnail_url = data.get("thumbnail_url")
    
    # Twitter/X
    elif platform in ["twitter", "x"]:
        # Twitter oEmbed doesn't provide thumbnail, skip
        # Could use card image parsing but complex
        return None, "twitter_no_thumbnail"
    
    # YouTube
    elif platform == "youtube":
        thumbnail_url = fetch_youtube_thumbnail(url)
    
    # Unknown platform
    else:
        return None, "unsupported_platform"
    
    # Download thumbnail if found
    if thumbnail_url:
        path = download_thumbnail(
            thumbnail_url=thumbnail_url,
            output_dir=output_dir,
            article_slug=article_slug,
            platform=platform,
            index=index
        )
        if path:
            return path, platform
    
    return None, "failed"


def capture_screenshots_for_article(
    social_contents: list,
    output_dir: str,
    article_slug: str
) -> list:
    """
    Capture screenshots/thumbnails for all social content in an article.
    
    Args:
        social_contents: List of social content dicts
        output_dir: Directory to save screenshots
        article_slug: Article slug for filenames
        
    Returns:
        Updated social_contents list with screenshot paths
    """
    for i, sc in enumerate(social_contents):
        platform = sc.get("platform", "").lower()
        url = sc.get("url")
        
        if not platform or not url:
            continue
        
        # Get screenshot/thumbnail
        path, source = get_screenshot_for_content(
            platform=platform,
            url=url,
            output_dir=output_dir,
            article_slug=article_slug,
            index=i
        )
        
        sc["screenshot_path"] = path
        sc["screenshot_source"] = source
        
        # Small delay between downloads
        if path:
            time.sleep(random.uniform(0.5, 1.5))
    
    return social_contents
