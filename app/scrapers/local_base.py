"""Base class for local Playwright scraping with GraphQL interception."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

from playwright.sync_api import sync_playwright, Page

from ..config import settings
from ..models import RawPost
from .base import ScrapeResult, _process_posts, _save_raw

log = logging.getLogger(__name__)

USER_DATA_DIR = settings.db_path.parent / "playwright_user_data"


def deep_find(obj, key):
    """ค้นหา key ที่ต้องการใน JSON object ซ้อนทับหลายชั้น"""
    results = []
    if isinstance(obj, dict):
        if key in obj:
            results.append(obj[key])
        for k, v in obj.items():
            results.extend(deep_find(v, key))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(deep_find(item, key))
    return results


class LocalBaseScraper(ABC):
    source: str = ""

    @abstractmethod
    def run_scrape(self, page: Page) -> list[dict]:
        """รันสคริปต์หน้าเว็บ คืนค่า raw items"""

    @abstractmethod
    def normalize(self, item: dict) -> Optional[RawPost]:
        """แปลง 1 item → RawPost"""

    def fetch(self) -> list[RawPost]:
        log.info("[%s] เริ่มต้น Local Scraper", self.source)
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        with sync_playwright() as p:
            is_logged_in = (USER_DATA_DIR / "Default").exists() or (USER_DATA_DIR / "Local State").exists()
            headless = is_logged_in
            
            browser = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=headless,
                args=["--disable-notifications"],
                viewport={"width": 1280, "height": 800}
            )
            
            page = browser.pages[0] if browser.pages else browser.new_page()
            
            if not is_logged_in:
                log.info("[%s] ครั้งแรก: กรุณาล็อกอิน Facebook ในหน้าต่างที่เปิดขึ้นมา", self.source)
                page.goto("https://www.facebook.com/")
                # รอจนกว่าจะล็อกอินสำเร็จ (สังเกตจากไอคอนโปรไฟล์ หรือช่องค้นหา)
                page.wait_for_selector("div[aria-label='Facebook'], input[type='search']", timeout=300000)
                log.info("[%s] ล็อกอินสำเร็จ เริ่มดึงข้อมูลได้", self.source)
                
            raw_items = self.run_scrape(page)
            browser.close()
            
        _save_raw(self.source, raw_items)
        
        posts: list[RawPost] = []
        for item in raw_items:
            try:
                post = self.normalize(item)
            except Exception as e:
                log.warning("[%s] normalize ล้มเหลว: %s", self.source, e)
                post = None
            if post:
                posts.append(post)
                
        log.info("[%s] ได้ %d โพสหลัง normalize (จาก %d รายการ)",
                 self.source, len(posts), len(raw_items))
        return posts


def run_local_pipeline(scraper: LocalBaseScraper) -> ScrapeResult:
    posts = scraper.fetch()
    return _process_posts(posts, scraper.source)
