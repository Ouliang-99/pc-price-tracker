"""Scraper A — Facebook Groups (apify/facebook-groups-scraper).

รันทุก SCRAPER_A_INTERVAL_HOURS (default 6 ชม.) เก็บทุกโพส
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import settings
from ..models import RawPost
from .base import BaseScraper, _extract_first

log = logging.getLogger(__name__)


class GroupsScraper(BaseScraper):
    source = "groups"

    def __init__(self, client=None):
        super().__init__(client)
        self.actor_id = settings.actor_groups

    def build_input(self) -> dict:
        payload: dict = {
            "startUrls": [{"url": u} for u in settings.fb_group_urls],
            "resultsLimit": settings.max_posts_per_run,
            "viewOption": "CHRONOLOGICAL",  # โพสใหม่สุดก่อน
        }
        from .. import db
        latest_date = db.get_latest_date(self.source)
        
        if latest_date:
            payload["onlyPostsNewerThan"] = latest_date
        elif settings.posts_newer_than:
            payload["onlyPostsNewerThan"] = settings.posts_newer_than
            
        return payload

    def normalize(self, item: dict) -> Optional[RawPost]:
        # actor groups-scraper: text มักอยู่ใน "text" หรือ "postText"
        text = _extract_first(item, ["text", "postText", "message", "content"])
        url = _extract_first(item, ["url", "postUrl", "facebookUrl", "link"])
        if not text or not url:
            return None
        posted_at = _extract_first(item, ["time", "timestamp", "date", "publishedTime"])
        location = _extract_first(item, ["location", "place"])
        return RawPost(
            text=text,
            source=self.source,
            source_url=url,
            posted_at=posted_at,
            location_hint=location,
        )


if __name__ == "__main__":
    from ..config import setup_logging
    from .base import run_pipeline

    setup_logging()
    print(run_pipeline(GroupsScraper()))
