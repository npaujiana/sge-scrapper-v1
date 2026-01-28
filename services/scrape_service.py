import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, date
from typing import Optional, Set, Callable, Awaitable, List, Dict, Any
from sqlalchemy.orm import Session

from config.settings import settings
from config.logging_config import get_logger
from database.models import Article, SocialContent, ScrapeSession
from database.connection import get_session
from scraper.browser import BrowserManager
from scraper.sitemap_parser import SitemapParser
from scraper.article_scraper import ArticleScraper, ArticleData
from scraper.sync_scraper import scrape_article_sync, scrape_articles_batch_sync
from .session_service import SessionService
from .auth_service import AuthService

# Process pool for sync scraping
_scrape_executor = None

def _get_scrape_executor():
    global _scrape_executor
    if _scrape_executor is None:
        _scrape_executor = ProcessPoolExecutor(max_workers=1)
    return _scrape_executor


class ScrapeService:
    """Main orchestrator for the scraping process."""

    def __init__(self):
        self.logger = get_logger()
        self.sitemap_parser = SitemapParser()
        self.article_scraper = ArticleScraper()
        self.auth_service = AuthService()

    async def login(
        self,
        wait_callback: Callable[[], Awaitable[None]],
    ) -> dict:
        """
        Open browser for manual login.

        Args:
            wait_callback: Async function to wait for user to complete login

        Returns:
            Dict with login result
        """
        self.logger.info("Starting manual login process...")

        browser = BrowserManager(headless=False)  # Always visible for manual login
        try:
            await browser.start(load_session=False)
            page = await browser.new_page()

            # Open login page and wait for user
            success = await self.auth_service.login_manual(
                page=page,
                wait_callback=wait_callback,
            )

            if success:
                # Save session
                await browser.save_session()
                await page.close()

                return {
                    "status": "success",
                    "message": "Login successful! Session saved.",
                }
            else:
                await page.close()
                return {
                    "status": "failed",
                    "message": "Login not completed. Please try again.",
                }

        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return {
                "status": "error",
                "message": str(e),
            }
        finally:
            await browser.stop()

    def check_session(self) -> dict:
        """Check if there's a valid saved session."""
        has_session, email = self.auth_service.has_valid_session()

        # Also check storage state file
        session_file = settings.project_root / "session" / "storage_state.json"
        has_storage = session_file.exists()

        return {
            "has_session": has_session and has_storage,
            "email": email,
            "message": f"Session exists for {email}" if (has_session and has_storage) else "No valid session found",
        }

    def clear_session(self) -> dict:
        """Clear saved session."""
        self.auth_service.clear_session()

        # Also clear storage state
        session_file = settings.project_root / "session" / "storage_state.json"
        if session_file.exists():
            session_file.unlink()

        return {
            "status": "success",
            "message": "Session cleared",
        }

    async def run_scrape(
        self,
        limit: Optional[int] = None,
        target_date: Optional[date] = None,
        force: bool = False
    ) -> dict:
        """
        Run a complete scrape session for a specific date.

        Args:
            limit: Optional limit on number of articles to scrape.
            target_date: The date to scrape articles for (default: today).
            force: Force scrape even if already has successful scrape for the date.

        Returns:
            Dict with scrape statistics.
        """
        target_date = target_date or date.today()
        self.logger.info(f"Starting scrape session for date: {target_date}...")

        with get_session() as db:
            session_service = SessionService(db)

            # Check if already has successful scrape for this date
            if not force and session_service.has_successful_scrape_for_date(target_date):
                self.logger.info(
                    f"Already has successful scrape for {target_date}. "
                    "Use force=True to scrape again."
                )
                existing_session = session_service.get_session_for_date(target_date)
                return {
                    "status": "skipped",
                    "message": f"Already has successful scrape for {target_date}",
                    "session_id": existing_session.id if existing_session else None,
                    "articles_success": existing_session.articles_success if existing_session else 0,
                }

            scrape_session = session_service.create_session(target_date=target_date)

            try:
                # Get article URLs - try date-filtered first, fallback to all
                article_urls = await self.sitemap_parser.get_article_urls_for_date(target_date)

                # If no date-filtered URLs, get all and filter by published_at after scraping
                if not article_urls:
                    self.logger.info(
                        "No URLs found via sitemap date filter. "
                        "Will filter by published_at after scraping."
                    )
                    article_urls = await self.sitemap_parser.get_all_article_urls()

                session_service.update_session(
                    scrape_session, articles_found=len(article_urls)
                )

                # Filter out already scraped articles
                existing_slugs = self._get_existing_slugs(db)
                new_urls = [
                    url for url in article_urls
                    if self.sitemap_parser.extract_slug_from_url(url) not in existing_slugs
                ]

                self.logger.info(
                    f"Found {len(article_urls)} total URLs, "
                    f"{len(new_urls)} are new"
                )

                # Apply limit if specified
                urls_to_scrape = new_urls[:limit] if limit else new_urls

                # Check if we have valid session
                session_status = self.check_session()
                if not session_status["has_session"]:
                    self.logger.warning("No valid session found. Please login first using --login")
                    return {
                        "status": "auth_required",
                        "message": "No valid session found. Please login first.",
                        "session_id": scrape_session.id,
                        "target_date": str(target_date),
                    }

                # Scrape articles - track success/failure separately
                articles_scraped = 0
                articles_success = 0
                articles_failed = 0
                articles_new = 0
                articles_updated = 0
                articles_skipped = 0

                # Use sync scraper in separate process (Windows compatibility)
                session_dir = str(settings.project_root / "session")
                loop = asyncio.get_running_loop()
                executor = _get_scrape_executor()

                for i, url in enumerate(urls_to_scrape):
                    self.logger.info(
                        f"Processing {i + 1}/{len(urls_to_scrape)}: {url}"
                    )
                    articles_scraped += 1

                    try:
                        # Run sync scraper in separate process
                        article_dict = await loop.run_in_executor(
                            executor,
                            scrape_article_sync,
                            url,
                            session_dir,
                            settings.base_url
                        )

                        if article_dict:
                            # Convert dict to ArticleData-like object for validation
                            article_data = self._dict_to_article_data(article_dict)

                            # Validate article date matches target date
                            if not self._is_article_for_date(article_data, target_date):
                                self.logger.info(
                                    f"Skipping article - not from target date {target_date}: "
                                    f"{article_data.title[:50] if article_data.title else url}"
                                )
                                articles_skipped += 1
                                continue

                            # Save article
                            is_new = self._save_article_from_dict(db, article_dict)
                            articles_success += 1

                            if is_new:
                                articles_new += 1
                            else:
                                articles_updated += 1

                            self.logger.info(
                                f"SUCCESS: {article_data.title[:50] if article_data.title else url}"
                            )
                        else:
                            articles_failed += 1
                            self.logger.warning(f"FAILED: Could not scrape {url}")

                        # Delay between articles
                        await asyncio.sleep(
                            settings.delay_between_articles_ms / 1000
                        )

                    except Exception as e:
                        articles_failed += 1
                        self.logger.error(f"FAILED: Error processing {url}: {e}")
                        continue

                # Complete session
                session_service.complete_session(
                    scrape_session,
                    articles_found=len(article_urls),
                    articles_scraped=articles_scraped,
                    articles_success=articles_success,
                    articles_failed=articles_failed,
                    articles_new=articles_new,
                    articles_updated=articles_updated,
                    articles_skipped=articles_skipped,
                )

                return {
                    "status": "completed",
                    "session_id": scrape_session.id,
                    "target_date": str(target_date),
                    "articles_found": len(article_urls),
                    "articles_scraped": articles_scraped,
                    "articles_success": articles_success,
                    "articles_failed": articles_failed,
                    "articles_new": articles_new,
                    "articles_updated": articles_updated,
                    "articles_skipped": articles_skipped,
                }

            except Exception as e:
                self.logger.error(f"Scrape session failed: {e}")
                session_service.fail_session(scrape_session, str(e))
                return {
                    "status": "failed",
                    "session_id": scrape_session.id,
                    "target_date": str(target_date),
                    "error": str(e),
                }

    def _is_article_for_date(self, article_data: ArticleData, target_date: date) -> bool:
        """
        Check if article was published on the target date.

        Args:
            article_data: The scraped article data.
            target_date: The date to match against.

        Returns:
            True if article is from target date, False otherwise.
        """
        if article_data.published_at is None:
            # If no published date, assume it's valid (can't verify)
            self.logger.warning(
                f"Article has no published_at date: {article_data.title[:50] if article_data.title else 'Unknown'}"
            )
            return True

        article_date = article_data.published_at.date()
        return article_date == target_date

    async def scrape_single_article(
        self,
        url: str,
        target_date: Optional[date] = None,
        save_to_db: bool = False
    ) -> Optional[dict]:
        """
        Scrape a single article (for testing).

        Args:
            url: The article URL to scrape.
            target_date: Optional date to validate against.
            save_to_db: Whether to save to database.

        Returns:
            Dict with article data or None if failed.
        """
        self.logger.info(f"Scraping single article: {url}")

        # Use sync scraper in separate process (Windows compatibility)
        session_dir = str(settings.project_root / "session")
        loop = asyncio.get_running_loop()
        executor = _get_scrape_executor()

        article_dict = await loop.run_in_executor(
            executor,
            scrape_article_sync,
            url,
            session_dir,
            settings.base_url
        )

        if article_dict:
            # Convert to ArticleData for date validation
            article_data = self._dict_to_article_data(article_dict)

            # Check date if target_date specified
            date_valid = True
            if target_date:
                date_valid = self._is_article_for_date(article_data, target_date)

            result = {
                "sge_id": article_dict.get("sge_id"),
                "url": article_dict.get("url"),
                "title": article_dict.get("title"),
                "subtitle": article_dict.get("subtitle"),
                "category": article_dict.get("category"),
                "tags": article_dict.get("tags"),
                "author_name": article_dict.get("author_name"),
                "published_at": article_dict.get("published_at"),
                "date_valid": date_valid,
                "target_date": str(target_date) if target_date else None,
                "social_contents_count": len(article_dict.get("social_contents", [])),
                "social_contents": [
                    {
                        "platform": sc.get("platform"),
                        "content_type": sc.get("content_type"),
                        "url": sc.get("url"),
                    }
                    for sc in article_dict.get("social_contents", [])
                ],
            }

            # Save to database if requested
            if save_to_db and date_valid:
                with get_session() as db:
                    is_new = self._save_article_from_dict(db, article_dict)
                    result["saved"] = True
                    result["is_new"] = is_new

            return result

        return None

    async def run_scrape_for_date_range(
        self,
        start_date: date,
        end_date: date,
        limit_per_day: Optional[int] = None
    ) -> dict:
        """
        Run scrape for a range of dates (for backfilling).

        Args:
            start_date: Start date of range.
            end_date: End date of range.
            limit_per_day: Optional limit per day.

        Returns:
            Dict with combined statistics.
        """
        from datetime import timedelta

        results = []
        current_date = start_date

        while current_date <= end_date:
            self.logger.info(f"Processing date: {current_date}")
            result = await self.run_scrape(
                limit=limit_per_day,
                target_date=current_date,
                force=False  # Skip if already done
            )
            results.append({
                "date": str(current_date),
                "result": result
            })
            current_date += timedelta(days=1)

        # Summarize results
        total_success = sum(
            r["result"].get("articles_success", 0)
            for r in results
            if r["result"].get("status") == "completed"
        )
        total_failed = sum(
            r["result"].get("articles_failed", 0)
            for r in results
            if r["result"].get("status") == "completed"
        )
        dates_completed = sum(
            1 for r in results
            if r["result"].get("status") == "completed"
        )
        dates_skipped = sum(
            1 for r in results
            if r["result"].get("status") == "skipped"
        )

        return {
            "status": "completed",
            "date_range": f"{start_date} to {end_date}",
            "dates_processed": len(results),
            "dates_completed": dates_completed,
            "dates_skipped": dates_skipped,
            "total_success": total_success,
            "total_failed": total_failed,
            "details": results,
        }

    def get_scrape_status_for_date(self, target_date: date) -> dict:
        """Get scrape status for a specific date."""
        with get_session() as db:
            session_service = SessionService(db)
            session = session_service.get_session_for_date(target_date)

            if session:
                return {
                    "date": str(target_date),
                    "has_successful_scrape": True,
                    "session_id": session.id,
                    "articles_success": session.articles_success,
                    "articles_failed": session.articles_failed,
                    "articles_new": session.articles_new,
                    "completed_at": str(session.finished_at) if session.finished_at else None,
                }
            else:
                return {
                    "date": str(target_date),
                    "has_successful_scrape": False,
                    "session_id": None,
                    "articles_success": 0,
                }

    def _dict_to_article_data(self, article_dict: Dict[str, Any]) -> ArticleData:
        """Convert article dict from sync scraper to ArticleData object."""
        published_at = None
        if article_dict.get("published_at"):
            try:
                published_at = datetime.fromisoformat(article_dict["published_at"])
            except:
                pass

        return ArticleData(
            sge_id=article_dict.get("sge_id", ""),
            url=article_dict.get("url", ""),
            slug=article_dict.get("slug", ""),
            title=article_dict.get("title", ""),
            subtitle=article_dict.get("subtitle"),
            content=article_dict.get("content"),
            content_text=article_dict.get("content_text"),
            category=article_dict.get("category"),
            tags=article_dict.get("tags"),
            author_name=article_dict.get("author_name"),
            author_email=article_dict.get("author_email"),
            featured_image_url=article_dict.get("featured_image_url"),
            read_time=article_dict.get("read_time"),
            published_at=published_at,
            raw_json=article_dict.get("raw_json"),
            social_contents=[],
        )

    def _save_article_from_dict(self, db: Session, article_dict: Dict[str, Any]) -> bool:
        """
        Save or update article from dict in database.

        Returns:
            True if article is new, False if updated.
        """
        sge_id = article_dict.get("sge_id", "")

        # Parse published_at
        published_at = None
        if article_dict.get("published_at"):
            try:
                published_at = datetime.fromisoformat(article_dict["published_at"])
            except:
                pass

        # Check if article exists
        existing = db.query(Article).filter(Article.sge_id == sge_id).first()

        if existing:
            # Update existing article
            existing.url = article_dict.get("url", "")
            existing.slug = article_dict.get("slug", "")
            existing.title = article_dict.get("title", "")
            existing.subtitle = article_dict.get("subtitle")
            existing.content = article_dict.get("content")
            existing.content_text = article_dict.get("content_text")
            existing.category = article_dict.get("category")
            existing.tags = article_dict.get("tags")
            existing.author_name = article_dict.get("author_name")
            existing.author_email = article_dict.get("author_email")
            existing.featured_image_url = article_dict.get("featured_image_url")
            existing.read_time = article_dict.get("read_time")
            existing.published_at = published_at
            existing.raw_json = article_dict.get("raw_json")
            existing.updated_at = datetime.utcnow()

            # Update social contents
            self._update_social_contents_from_dict(db, existing.id, article_dict.get("social_contents", []))

            self.logger.debug(f"Updated article: {article_dict.get('title', '')}")
            return False
        else:
            # Create new article
            article = Article(
                sge_id=sge_id,
                url=article_dict.get("url", ""),
                slug=article_dict.get("slug", ""),
                title=article_dict.get("title", ""),
                subtitle=article_dict.get("subtitle"),
                content=article_dict.get("content"),
                content_text=article_dict.get("content_text"),
                category=article_dict.get("category"),
                tags=article_dict.get("tags"),
                author_name=article_dict.get("author_name"),
                author_email=article_dict.get("author_email"),
                featured_image_url=article_dict.get("featured_image_url"),
                read_time=article_dict.get("read_time"),
                published_at=published_at,
                raw_json=article_dict.get("raw_json"),
            )
            db.add(article)
            db.flush()

            # Add social contents
            self._add_social_contents_from_dict(db, article.id, article_dict.get("social_contents", []))

            self.logger.debug(f"Created new article: {article_dict.get('title', '')}")
            return True

    def _add_social_contents_from_dict(
        self,
        db: Session,
        article_id: int,
        social_contents: List[Dict]
    ) -> None:
        """Add social content records from dict list."""
        for sc_data in social_contents:
            # Build extra_data with stats and additional info
            extra_data = {}
            if sc_data.get("stats"):
                extra_data["stats"] = sc_data["stats"]
            if sc_data.get("video_id"):
                extra_data["video_id"] = sc_data["video_id"]
            if sc_data.get("embed_id"):
                extra_data["embed_id"] = sc_data["embed_id"]

            social_content = SocialContent(
                article_id=article_id,
                platform=sc_data.get("platform", "unknown"),
                content_type=sc_data.get("content_type", "unknown"),
                url=sc_data.get("url"),
                embed_html=sc_data.get("embed_html"),
                thumbnail_url=sc_data.get("thumbnail_url"),
                username=sc_data.get("username"),
                caption=sc_data.get("caption"),
                position_in_article=sc_data.get("position_in_article", 0),
                extra_data=extra_data if extra_data else None,
            )
            db.add(social_content)

    def _update_social_contents_from_dict(
        self,
        db: Session,
        article_id: int,
        social_contents: List[Dict]
    ) -> None:
        """Update social contents from dict list."""
        # Delete existing
        db.query(SocialContent).filter(SocialContent.article_id == article_id).delete()
        # Add new
        self._add_social_contents_from_dict(db, article_id, social_contents)

    def _get_existing_slugs(self, db: Session) -> Set[str]:
        """Get set of slugs already in the database."""
        results = db.query(Article.slug).all()
        return {row[0] for row in results}

    def _save_article(self, db: Session, article_data: ArticleData) -> bool:
        """
        Save or update article in database.

        Returns:
            True if article is new, False if updated.
        """
        # Check if article exists
        existing = db.query(Article).filter(
            Article.sge_id == article_data.sge_id
        ).first()

        if existing:
            # Update existing article
            existing.url = article_data.url
            existing.slug = article_data.slug
            existing.title = article_data.title
            existing.subtitle = article_data.subtitle
            existing.content = article_data.content
            existing.content_text = article_data.content_text
            existing.category = article_data.category
            existing.tags = article_data.tags
            existing.author_name = article_data.author_name
            existing.author_email = article_data.author_email
            existing.featured_image_url = article_data.featured_image_url
            existing.read_time = article_data.read_time
            existing.published_at = article_data.published_at
            existing.raw_json = article_data.raw_json
            existing.updated_at = datetime.utcnow()

            # Update social contents
            self._update_social_contents(db, existing.id, article_data.social_contents)

            self.logger.debug(f"Updated article: {article_data.title}")
            return False
        else:
            # Create new article
            article = Article(
                sge_id=article_data.sge_id,
                url=article_data.url,
                slug=article_data.slug,
                title=article_data.title,
                subtitle=article_data.subtitle,
                content=article_data.content,
                content_text=article_data.content_text,
                category=article_data.category,
                tags=article_data.tags,
                author_name=article_data.author_name,
                author_email=article_data.author_email,
                featured_image_url=article_data.featured_image_url,
                read_time=article_data.read_time,
                published_at=article_data.published_at,
                raw_json=article_data.raw_json,
            )
            db.add(article)
            db.flush()

            # Add social contents
            self._add_social_contents(db, article.id, article_data.social_contents)

            self.logger.debug(f"Created new article: {article_data.title}")
            return True

    def _add_social_contents(
        self,
        db: Session,
        article_id: int,
        social_contents: list
    ) -> None:
        """Add social content records for an article."""
        for sc_data in social_contents:
            social_content = SocialContent(
                article_id=article_id,
                platform=sc_data.platform,
                content_type=sc_data.content_type,
                url=sc_data.url,
                embed_html=sc_data.embed_html,
                thumbnail_url=sc_data.thumbnail_url,
                username=sc_data.username,
                caption=sc_data.caption,
                extra_data=sc_data.metadata,
                position_in_article=sc_data.position_in_article,
            )
            db.add(social_content)

    def _update_social_contents(
        self,
        db: Session,
        article_id: int,
        social_contents: list
    ) -> None:
        """Update social contents for an existing article."""
        # Delete existing social contents
        db.query(SocialContent).filter(
            SocialContent.article_id == article_id
        ).delete()

        # Add new social contents
        self._add_social_contents(db, article_id, social_contents)
