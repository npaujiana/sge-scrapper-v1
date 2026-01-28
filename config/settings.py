import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = Field(
        default="postgresql://user:password@localhost:5432/sge_scraper",
        alias="DATABASE_URL"
    )

    # Scraping
    scrape_interval_hours: int = Field(default=24, alias="SCRAPE_INTERVAL_HOURS")
    scrape_time: str = Field(default="00:00", alias="SCRAPE_TIME")
    max_concurrent_pages: int = Field(default=3, alias="MAX_CONCURRENT_PAGES")
    page_timeout_ms: int = Field(default=30000, alias="PAGE_TIMEOUT_MS")
    delay_between_articles_ms: int = Field(default=2000, alias="DELAY_BETWEEN_ARTICLES_MS")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/scraper.log", alias="LOG_FILE")

    # Base URL
    base_url: str = "https://www.socialgrowthengineers.com"
    sitemap_urls: list[str] = [
        "https://www.socialgrowthengineers.com/sitemap-1.xml",
        "https://www.socialgrowthengineers.com/sitemap-2.xml",
        "https://www.socialgrowthengineers.com/sitemap-3.xml",
        "https://www.socialgrowthengineers.com/sitemap-4.xml",
    ]

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: int = 5

    # API settings
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def logs_dir(self) -> Path:
        logs_path = self.project_root / "logs"
        logs_path.mkdir(exist_ok=True)
        return logs_path


settings = Settings()
