"""Manual scrape triggers — ใช้ร่วมกันระหว่าง tray, web button, CLI."""
from __future__ import annotations

import logging

from .scrapers import GroupsScraper, MarketplaceScraper, run_pipeline

log = logging.getLogger(__name__)

_SCRAPERS = {
    "groups": GroupsScraper,
    "marketplace": MarketplaceScraper,
}


def scrape(source: str):
    """รัน scrape 1 รอบตาม source ('groups'|'marketplace'). คืน ScrapeResult หรือ None."""
    cls = _SCRAPERS.get(source)
    if cls is None:
        log.warning("ไม่รู้จัก source: %s", source)
        return None
    try:
        return run_pipeline(cls())
    except Exception as e:
        log.exception("scrape %s ล้มเหลว: %s", source, e)
        return None
