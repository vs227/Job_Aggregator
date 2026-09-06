import os
import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent.parent))

from scrapers.main import refresh_and_import_jobs
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_scheduled_scraper():
    logger.info("Starting scheduled job scraper (refreshing 50 jobs)...")
    try:
        refresh_and_import_jobs(target_jobs=50)
        logger.info("Scheduled job scraper completed successfully!")
    except Exception as e:
        logger.error(f"Error running scheduled scraper: {e}", exc_info=True)

if __name__ == "__main__":
    interval_days = int(os.getenv("SCRAPER_INTERVAL_DAYS", "3"))
    logger.info(f"Starting APScheduler with {interval_days} day interval...")
    logger.info(f"First job will run now, then every {interval_days} days.")

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_scheduled_scraper,
        trigger=IntervalTrigger(days=interval_days),
        id='job_scraper',
        name='Job Scraper (3-day refresh)',
        replace_existing=True,
        next_run_time=datetime.now()
    )

    try:
        logger.info("Scheduler started. Press Ctrl+C to stop.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")

