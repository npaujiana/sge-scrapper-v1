# SGE Scraper

Sistem otomatis untuk scraping artikel dari SocialGrowthEngineers (SGE), mengekstrak konten sosial media, dan menyimpan ke database PostgreSQL.

## Features

- Scrape artikel dari sitemap SGE
- Ekstrak konten sosial media (TikTok, Instagram, Twitter/X, YouTube)
- Simpan ke PostgreSQL dengan SQLAlchemy ORM
- Scheduled scraping dengan APScheduler
- Support headless browser dengan Playwright

## Tech Stack

- Python 3.11+
- Playwright (headless browser)
- PostgreSQL + SQLAlchemy
- APScheduler
- BeautifulSoup4 + lxml

## Installation

1. Clone repository dan masuk ke folder:
```bash
cd sge-scraper
```

2. Buat virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install chromium
```

5. Setup environment variables:
```bash
cp .env.example .env
# Edit .env dengan konfigurasi database Anda
```

6. Run database migrations:
```bash
python main.py --migrate
# atau langsung dengan alembic:
alembic upgrade head
```

## Usage

### Start API Server (Swagger UI)
```bash
# Start API server
python main.py --api

# Custom host/port
python main.py --api --api-host 127.0.0.1 --api-port 3000

# Swagger UI available at:
# http://localhost:8000/docs

# Alternative (direct uvicorn):
# uvicorn api.main:app --reload
```

### Database Migrations
```bash
# Run migrations
python main.py --migrate

# Check migration status
python main.py --migrate-status

# Atau menggunakan alembic langsung:
alembic upgrade head          # Apply all migrations
alembic downgrade -1          # Rollback 1 migration
alembic current               # Show current revision
alembic history               # Show migration history
alembic revision --autogenerate -m "description"  # Generate new migration
```

### Run Scheduled Scraper
```bash
python main.py
# atau
python main.py --scheduled
```

### Run Once
```bash
# Scrape semua artikel baru
python main.py --run-once

# Scrape dengan limit
python main.py --run-once --limit 10
```

### Test Single URL
```bash
python main.py --test-url "https://www.socialgrowthengineers.com/some-article"
```

## Configuration

Edit `.env` file:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/sge_scraper

# Scraping
SCRAPE_INTERVAL_HOURS=24
SCRAPE_TIME=00:00
MAX_CONCURRENT_PAGES=3
PAGE_TIMEOUT_MS=30000
DELAY_BETWEEN_ARTICLES_MS=2000

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/scraper.log
```

## Database Schema

### scrape_sessions
Log setiap sesi scraping.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| started_at | TIMESTAMP | Waktu mulai |
| finished_at | TIMESTAMP | Waktu selesai |
| status | VARCHAR(20) | running/completed/failed |
| articles_found | INTEGER | Total artikel ditemukan |
| articles_new | INTEGER | Artikel baru |
| articles_updated | INTEGER | Artikel diupdate |
| error_message | TEXT | Pesan error |

### articles
Menyimpan artikel SGE.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| sge_id | VARCHAR(100) | ID artikel dari SGE |
| url | VARCHAR(500) | URL lengkap |
| slug | VARCHAR(300) | Slug URL |
| title | VARCHAR(500) | Judul |
| subtitle | TEXT | Subjudul/excerpt |
| content | TEXT | Konten HTML |
| content_text | TEXT | Konten plain text |
| category | VARCHAR(100) | Kategori |
| tags | JSONB | Array of tags |
| author_name | VARCHAR(200) | Nama author |
| featured_image_url | VARCHAR(500) | URL gambar |
| published_at | TIMESTAMP | Tanggal publikasi |

### social_contents
Konten sosial media dari artikel.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| article_id | INTEGER FK | Referensi ke artikel |
| platform | VARCHAR(50) | tiktok/instagram/twitter/youtube |
| content_type | VARCHAR(50) | video/post/tweet/embed/screenshot |
| url | VARCHAR(500) | URL konten |
| embed_html | TEXT | HTML embed |
| username | VARCHAR(200) | Username creator |
| position_in_article | INTEGER | Urutan dalam artikel |

## Project Structure

```
sge-scraper/
├── config/
│   ├── settings.py          # Konfigurasi aplikasi
│   └── logging_config.py    # Setup logging
├── database/
│   ├── models.py            # SQLAlchemy models
│   ├── connection.py        # Database connection
│   └── migrations/          # Alembic migrations
├── scraper/
│   ├── browser.py           # Playwright browser manager
│   ├── sitemap_parser.py    # Parse sitemap XML
│   ├── article_scraper.py   # Scrape artikel
│   └── social_extractor.py  # Ekstrak konten sosmed
├── services/
│   ├── scrape_service.py    # Orchestrator utama
│   └── session_service.py   # Manage scrape sessions
├── utils/
│   └── helpers.py           # Utility functions
├── logs/                    # Log files
├── main.py                  # Entry point
├── scheduler.py             # APScheduler setup
├── requirements.txt
├── alembic.ini              # Alembic configuration
└── .env.example
```

## License

MIT
