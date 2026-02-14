"""TikTok screenshot capture with oEmbed fallback."""
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import requests


def fetch_oembed_data(url: str) -> Optional[dict]:
    """
    Fetch TikTok oEmbed data.
    
    Args:
        url: TikTok video URL
        
    Returns:
        Dict with title, author_name, thumbnail_url, etc. or None if failed
    """
    try:
        oembed_url = f"https://www.tiktok.com/oembed?url={url}"
        response = requests.get(oembed_url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[TIKTOK] oEmbed fetch error: {e}")
    return None


def download_oembed_thumbnail(
    url: str,
    output_dir: str,
    article_slug: str,
    index: int
) -> Optional[str]:
    """
    Download thumbnail from TikTok oEmbed.
    
    Returns:
        Path to downloaded thumbnail or None if failed
    """
    oembed_data = fetch_oembed_data(url)
    if not oembed_data:
        return None
    
    thumbnail_url = oembed_data.get("thumbnail_url")
    if not thumbnail_url:
        return None
    
    try:
        response = requests.get(thumbnail_url, timeout=15)
        if response.status_code == 200:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_slug = re.sub(r'[^\w\-]', '_', article_slug)[:50]
            filename = f"{safe_slug}_{index}_{timestamp}_oembed.jpg"
            filepath = output_path / filename
            
            with open(filepath, "wb") as f:
                f.write(response.content)
            
            print(f"[TIKTOK] Downloaded oEmbed thumbnail: {filename}")
            return str(filepath)
    except Exception as e:
        print(f"[TIKTOK] Thumbnail download error: {e}")
    
    return None


def capture_tiktok_screenshot_sync(
    url: str,
    output_dir: str,
    article_slug: str,
    index: int,
    session_dir: str
) -> Tuple[Optional[str], str]:
    """
    Capture TikTok video page screenshot.
    Falls back to oEmbed thumbnail if screenshot fails.
    
    Args:
        url: TikTok video URL
        output_dir: Directory to save screenshots
        article_slug: Article slug for filename
        index: Position index for filename
        session_dir: Path to session directory with TikTok cookies
        
    Returns:
        Tuple of (path, source) where source is 'screenshot' or 'oembed' or 'failed'
    """
    from playwright.sync_api import sync_playwright
    
    # Check for TikTok session
    storage_state_file = Path(session_dir) / "tiktok_storage_state.json"
    has_session = storage_state_file.exists()
    
    if not has_session:
        print(f"[TIKTOK] No session found, falling back to oEmbed for: {url}")
        thumbnail_path = download_oembed_thumbnail(url, output_dir, article_slug, index)
        if thumbnail_path:
            return thumbnail_path, "oembed"
        return None, "failed"
    
    print(f"[TIKTOK] Capturing screenshot: {url}")
    
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            try:
                context = browser.new_context(
                    viewport={"width": 375, "height": 667},  # Mobile viewport
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                    storage_state=str(storage_state_file),
                )
                page = context.new_page()
                
                # Random delay to avoid detection
                delay = random.uniform(2, 5)
                time.sleep(delay)
                
                # Navigate to TikTok video
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                except Exception as e:
                    print(f"[TIKTOK] Navigation timeout, retrying: {e}")
                    page.goto(url, wait_until="load", timeout=30000)
                
                # Wait for video content to load
                page.wait_for_timeout(3000)
                
                # Check for captcha or login wall
                page_content = page.content().lower()
                if "captcha" in page_content or "verify" in page_content:
                    print(f"[TIKTOK] Captcha detected, falling back to oEmbed")
                    thumbnail_path = download_oembed_thumbnail(url, output_dir, article_slug, index)
                    if thumbnail_path:
                        return thumbnail_path, "oembed"
                    return None, "failed"
                
                # Wait for video card
                try:
                    page.wait_for_selector(
                        '[data-e2e="browse-video"], video, .video-card, .tiktok-web-player',
                        timeout=10000
                    )
                except:
                    pass  # Continue anyway
                
                # Create output directory
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)
                
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_slug = re.sub(r'[^\w\-]', '_', article_slug)[:50]
                filename = f"{safe_slug}_{index}_{timestamp}.webp"
                filepath = output_path / filename
                
                # Take screenshot
                page.screenshot(path=str(filepath), type="webp", quality=85)
                print(f"[TIKTOK] Screenshot saved: {filename}")
                
                return str(filepath), "screenshot"
                
            finally:
                browser.close()
                
    except Exception as e:
        print(f"[TIKTOK] Screenshot error: {e}, falling back to oEmbed")
        import traceback
        traceback.print_exc()
        
        # Fallback to oEmbed
        thumbnail_path = download_oembed_thumbnail(url, output_dir, article_slug, index)
        if thumbnail_path:
            return thumbnail_path, "oembed"
        
    return None, "failed"


def capture_tiktok_screenshots_for_article(
    social_contents: list,
    output_dir: str,
    article_slug: str,
    session_dir: str
) -> list:
    """
    Capture screenshots for all TikTok content in an article.
    
    Args:
        social_contents: List of social content dicts
        output_dir: Directory to save screenshots
        article_slug: Article slug for filenames
        session_dir: Session directory path
        
    Returns:
        Updated social_contents list with screenshot paths
    """
    screenshot_count = 0
    
    for i, sc in enumerate(social_contents):
        if sc.get("platform") != "tiktok":
            continue
        
        url = sc.get("url")
        if not url:
            continue
        
        # Skip non-video URLs
        if "/video/" not in url and "/embed/" not in url:
            continue
        
        # Capture screenshot
        path, source = capture_tiktok_screenshot_sync(
            url=url,
            output_dir=output_dir,
            article_slug=article_slug,
            index=i,
            session_dir=session_dir
        )
        
        if path:
            sc["screenshot_path"] = path
            sc["screenshot_source"] = source
            screenshot_count += 1
        else:
            sc["screenshot_path"] = None
            sc["screenshot_source"] = "failed"
        
        # Delay between screenshots
        time.sleep(random.uniform(1, 3))
    
    return social_contents
