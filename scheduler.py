"""
Scheduler — runs daily at 8 AM IST
Pipeline: scrape VAHAN → process → refresh Amazon data
Run once:      python scheduler.py --now
Run as daemon: python scheduler.py
"""

import logging
import sys
import yaml
from datetime import datetime
from pathlib import Path

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    filename="logs/scheduler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)


def run_pipeline():
    start = datetime.now()
    log.info("=== Pipeline started ===")
    print(f"\n[{start.strftime('%Y-%m-%d %H:%M:%S')}] Starting VAHAN pipeline...")

    # ── Step 1: Scrape VAHAN ──────────────────────────────────────────────
    scrape_ok = False
    try:
        from scraper import scrape_vahan, save_raw
        df_raw = scrape_vahan()
        if not df_raw.empty:
            save_raw(df_raw)
            scrape_ok = True
            print(f"[OK] Scraped {len(df_raw)} rows")
        else:
            log.warning("Scraper returned empty data")
            print("[WARN] Scraper returned no data — keeping existing data")
    except Exception as e:
        log.error(f"Scraper failed: {e}", exc_info=True)
        print(f"[ERROR] Scraper: {e}")

    # ── Step 2: Process ───────────────────────────────────────────────────
    try:
        from processor import process, generate_sample_data
        df_proc = process()
        if df_proc.empty and not scrape_ok:
            generate_sample_data()
    except Exception as e:
        log.error(f"Processor failed: {e}", exc_info=True)
        print(f"[ERROR] Processor: {e}")

    # ── Step 3: Refresh Amazon data ───────────────────────────────────────
    try:
        from amazon_data import get_amazon_data
        get_amazon_data(force_refresh=True)
        print("[OK] Amazon data refreshed")
    except Exception as e:
        log.warning(f"Amazon refresh skipped: {e}")

    elapsed = (datetime.now() - start).seconds
    log.info(f"=== Pipeline complete in {elapsed}s ===")
    print(f"[DONE] Pipeline complete in {elapsed}s\n")


if __name__ == "__main__":
    if "--now" in sys.argv:
        run_pipeline()
        sys.exit(0)

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("[ERROR] apscheduler not installed. Run: python -m pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    hour   = CFG["scheduler"]["hour"]
    minute = CFG["scheduler"]["minute"]

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Kolkata"),
        id="vahan_daily",
        name="VAHAN Daily Scrape",
        replace_existing=True,
    )

    print(f"Scheduler running (IST). Pipeline fires daily at {hour:02d}:{minute:02d}.")
    print("Run 'python scheduler.py --now' to trigger immediately.")
    print("Press Ctrl+C to stop.\n")

    # Run once immediately on start
    run_pipeline()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")
