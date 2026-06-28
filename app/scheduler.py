"""APScheduler — รัน scraper ตาม interval.

- job A: Groups ทุก SCRAPER_A_INTERVAL_HOURS
- job B: Marketplace ทุก SCRAPER_B_INTERVAL_HOURS

error ใน job ถูก catch ไม่ให้ล้ม scheduler/process
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .scrapers import GroupsScraper, MarketplaceScraper, run_pipeline

log = logging.getLogger(__name__)


def run_groups() -> None:
    try:
        result = run_pipeline(GroupsScraper())
        log.info("job groups: %s", result)
    except Exception as e:
        log.exception("job groups ล้มเหลว: %s", e)


def run_marketplace() -> None:
    try:
        result = run_pipeline(MarketplaceScraper())
        log.info("job marketplace: %s", result)
    except Exception as e:
        log.exception("job marketplace ล้มเหลว: %s", e)


def build_scheduler(run_now: bool = False) -> BackgroundScheduler:
    """สร้าง scheduler พร้อม 2 job. run_now=True ให้ยิงครั้งแรกทันที."""
    scheduler = BackgroundScheduler(timezone="Asia/Bangkok")

    scheduler.add_job(
        run_groups,
        "interval",
        hours=settings.scraper_a_interval_hours,
        id="scraper_groups",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_marketplace,
        "interval",
        hours=settings.scraper_b_interval_hours,
        id="scraper_marketplace",
        max_instances=1,
        coalesce=True,
    )

    if run_now:
        # ยิงครั้งแรกเร็วๆ (หลัง start 5 วิ) ไม่ต้องรอครบ interval
        from datetime import datetime, timedelta

        soon = datetime.now() + timedelta(seconds=5)
        scheduler.add_job(run_groups, "date", run_date=soon, id="groups_initial")
        scheduler.add_job(
            run_marketplace, "date", run_date=soon + timedelta(seconds=10), id="market_initial"
        )

    return scheduler


if __name__ == "__main__":
    import time

    from .config import setup_logging

    setup_logging()
    sched = build_scheduler()
    sched.start()
    log.info("scheduler เริ่มแล้ว (Ctrl+C เพื่อหยุด)")
    try:
        for job in sched.get_jobs():
            log.info("job %s → next run: %s", job.id, job.next_run_time)
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
